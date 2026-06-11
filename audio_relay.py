"""Bounded in-memory PCM mixing and FFmpeg fan-out for browser listeners."""

from __future__ import annotations

import queue
import subprocess
import threading
import time
import uuid
from array import array
from collections.abc import Callable, Iterator
from dataclasses import dataclass


PCM_RATE = 48_000
PCM_CHANNELS = 2
PCM_SAMPLE_BYTES = 2
FRAME_MILLISECONDS = 20
PCM_FRAME_BYTES = PCM_RATE * PCM_CHANNELS * PCM_SAMPLE_BYTES * FRAME_MILLISECONDS // 1000
DEFAULT_INPUT_FRAMES = 100
DEFAULT_CLIENT_CHUNKS = 32
STREAM_CHUNK_BYTES = 4096
_STOP = object()


class RelayError(RuntimeError):
    """The relay could not start or stopped unexpectedly."""


class SlowClientError(RelayError):
    """A listener could not consume the bounded stream quickly enough."""


@dataclass(frozen=True)
class RelayState:
    listener_count: int
    running: bool
    transcription_active: bool
    encoder_error: str | None


class RelayListener:
    def __init__(self, relay: "AudioRelay", listener_id: str, chunks: queue.Queue):
        self._relay = relay
        self._listener_id = listener_id
        self._chunks = chunks
        self._closed = False

    def iter_chunks(self) -> Iterator[bytes]:
        try:
            while True:
                chunk = self._chunks.get()
                if chunk is _STOP:
                    error = self._relay.encoder_error
                    if error:
                        raise RelayError(error)
                    return
                if isinstance(chunk, SlowClientError):
                    raise chunk
                yield chunk
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._relay.remove_listener(self._listener_id)


class AudioRelay:
    """Mixes PCM frames and broadcasts one FFmpeg stream through bounded queues."""

    def __init__(
        self,
        *,
        process_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
        input_frame_limit: int = DEFAULT_INPUT_FRAMES,
        client_chunk_limit: int = DEFAULT_CLIENT_CHUNKS,
        on_idle: Callable[[], None] | None = None,
    ):
        self._process_factory = process_factory
        self._input_frames: queue.Queue[tuple[object | None, bytes]] = queue.Queue(
            maxsize=input_frame_limit
        )
        self._client_chunk_limit = client_chunk_limit
        self._on_idle = on_idle
        self._listeners: dict[str, queue.Queue] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._process = None
        self._mixer_thread: threading.Thread | None = None
        self._reader_thread: threading.Thread | None = None
        self._transcription_active = False
        self._encoder_error: str | None = None

    @property
    def encoder_error(self) -> str | None:
        with self._lock:
            return self._encoder_error

    def state(self) -> RelayState:
        with self._lock:
            return RelayState(
                listener_count=len(self._listeners),
                running=self._process is not None,
                transcription_active=self._transcription_active,
                encoder_error=self._encoder_error,
            )

    def add_listener(self) -> RelayListener:
        chunks: queue.Queue = queue.Queue(maxsize=self._client_chunk_limit)
        listener_id = uuid.uuid4().hex
        with self._lock:
            self._listeners[listener_id] = chunks
            try:
                if self._process is None:
                    self._start_locked()
            except Exception:
                self._listeners.pop(listener_id, None)
                raise
        return RelayListener(self, listener_id, chunks)

    def remove_listener(self, listener_id: str) -> None:
        became_idle = False
        with self._lock:
            removed = self._listeners.pop(listener_id, None)
            if removed is not None and not self._listeners and not self._transcription_active:
                self._stop_locked()
                became_idle = True
        if became_idle and self._on_idle:
            self._on_idle()

    def set_transcription_active(self, active: bool) -> None:
        became_idle = False
        with self._lock:
            self._transcription_active = active
            if not active and not self._listeners:
                self._stop_locked()
                became_idle = True
        if became_idle and self._on_idle:
            self._on_idle()

    def submit_pcm(self, pcm: bytes, *, source_id: object | None = None) -> bool:
        if not pcm:
            return True
        frame = pcm[:PCM_FRAME_BYTES]
        if len(frame) < PCM_FRAME_BYTES:
            frame += bytes(PCM_FRAME_BYTES - len(frame))
        try:
            self._input_frames.put_nowait((source_id, frame))
            return True
        except queue.Full:
            return False

    def disconnect(self, reason: str | None = None) -> None:
        with self._lock:
            if reason:
                self._encoder_error = reason
            listeners = list(self._listeners.values())
            self._listeners.clear()
            self._transcription_active = False
            self._stop_locked()
        for chunks in listeners:
            self._force_put(chunks, _STOP)

    def _start_locked(self) -> None:
        self._encoder_error = None
        while True:
            try:
                self._input_frames.get_nowait()
            except queue.Empty:
                break
        self._stop_event = threading.Event()
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
            "-f", "s16le", "-ar", str(PCM_RATE), "-ac", str(PCM_CHANNELS),
            "-i", "pipe:0", "-vn", "-c:a", "libmp3lame", "-b:a", "64k",
            "-f", "mp3", "-flush_packets", "1", "pipe:1",
        ]
        try:
            process = self._process_factory(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
        except OSError as error:
            raise RelayError(f"FFmpeg could not start: {error}") from error
        if process.stdin is None or process.stdout is None:
            process.terminate()
            raise RelayError("FFmpeg did not provide streaming pipes")
        self._process = process
        self._mixer_thread = threading.Thread(target=self._mix_loop, daemon=True)
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._mixer_thread.start()
        self._reader_thread.start()

    def _stop_locked(self) -> None:
        process = self._process
        self._process = None
        self._stop_event.set()
        if process is None:
            return
        try:
            if process.stdin:
                process.stdin.close()
        except OSError:
            pass
        process.terminate()

    def _mix_loop(self) -> None:
        frame_seconds = FRAME_MILLISECONDS / 1000
        next_frame_at = time.monotonic()
        while not self._stop_event.is_set():
            frames_by_source = {}
            try:
                source_id, frame = self._input_frames.get(timeout=frame_seconds)
                frames_by_source[source_id] = frame
            except queue.Empty:
                pass
            while len(frames_by_source) < 32:
                try:
                    source_id, frame = self._input_frames.get_nowait()
                    frames_by_source[source_id] = frame
                except queue.Empty:
                    break
            frames = list(frames_by_source.values())
            mixed = mix_pcm_frames(frames) if frames else bytes(PCM_FRAME_BYTES)
            with self._lock:
                process = self._process
            if process is None or process.stdin is None:
                return
            try:
                process.stdin.write(mixed)
            except (BrokenPipeError, OSError) as error:
                self._fail_encoder(f"FFmpeg encoder input failed: {error}")
                return
            next_frame_at += frame_seconds
            self._stop_event.wait(max(0, next_frame_at - time.monotonic()))

    def _read_loop(self) -> None:
        with self._lock:
            process = self._process
        if process is None or process.stdout is None:
            return
        while not self._stop_event.is_set():
            try:
                chunk = process.stdout.read(STREAM_CHUNK_BYTES)
            except OSError as error:
                self._fail_encoder(f"FFmpeg encoder output failed: {error}")
                return
            if not chunk:
                if not self._stop_event.is_set():
                    self._fail_encoder("FFmpeg encoder stopped unexpectedly")
                return
            self._broadcast(chunk)

    def _broadcast(self, chunk: bytes) -> None:
        slow_listeners = []
        with self._lock:
            for listener_id, chunks in self._listeners.items():
                try:
                    chunks.put_nowait(chunk)
                except queue.Full:
                    slow_listeners.append((listener_id, chunks))
            for listener_id, _chunks in slow_listeners:
                self._listeners.pop(listener_id, None)
            should_stop = not self._listeners and not self._transcription_active
            if should_stop:
                self._stop_locked()
        for _listener_id, chunks in slow_listeners:
            self._force_put(chunks, SlowClientError("Audio stream closed because the client was too slow"))
        if slow_listeners and should_stop and self._on_idle:
            self._on_idle()

    def _fail_encoder(self, message: str) -> None:
        with self._lock:
            if self._encoder_error is not None:
                return
            self._encoder_error = message
            listeners = list(self._listeners.values())
            self._listeners.clear()
            self._stop_locked()
        for chunks in listeners:
            self._force_put(chunks, _STOP)
        if self._on_idle:
            self._on_idle()

    @staticmethod
    def _force_put(chunks: queue.Queue, item) -> None:
        try:
            chunks.put_nowait(item)
        except queue.Full:
            try:
                chunks.get_nowait()
            except queue.Empty:
                pass
            chunks.put_nowait(item)


def mix_pcm_frames(frames: list[bytes]) -> bytes:
    """Mix signed 16-bit little-endian PCM with saturation."""
    if not frames:
        return bytes(PCM_FRAME_BYTES)
    mixed = [0] * (PCM_FRAME_BYTES // PCM_SAMPLE_BYTES)
    for frame in frames:
        samples = array("h")
        samples.frombytes(frame[:PCM_FRAME_BYTES])
        for index, sample in enumerate(samples):
            mixed[index] += sample
    output = array("h", (max(-32768, min(32767, sample)) for sample in mixed))
    return output.tobytes()
