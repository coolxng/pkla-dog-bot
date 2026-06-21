"""Bounded in-memory PCM mixing and FFmpeg fan-out for browser listeners."""

from __future__ import annotations

import queue
import subprocess
import threading
import time
import uuid
from array import array
from collections import deque
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
MAX_SOURCE_BUFFER_FRAMES = 50
JITTER_BUFFER_FRAMES = 3
JITTER_DRAIN_SECONDS = FRAME_MILLISECONDS / 1000 * JITTER_BUFFER_FRAMES
MIX_HEADROOM = 0.85
_STOP = object()


class RelayError(RuntimeError):
    """The relay could not start or stopped unexpectedly."""


class SlowClientError(RelayError):
    """A listener could not consume the bounded stream quickly enough."""


@dataclass(frozen=True)
class RelayState:
    listener_count: int
    running: bool
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
        self._pending_pcm: dict[object | None, bytes] = {}
        self._pending_lock = threading.Lock()
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._process = None
        self._mixer_thread: threading.Thread | None = None
        self._reader_thread: threading.Thread | None = None
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
            if removed is not None and not self._listeners:
                self._stop_locked()
                became_idle = True
        if became_idle and self._on_idle:
            self._on_idle()

    def submit_pcm(self, pcm: bytes, *, source_id: object | None = None) -> bool:
        if not pcm:
            return True

        accepted_all_frames = True
        with self._pending_lock:
            buffered_pcm = self._pending_pcm.get(source_id, b"") + pcm
            offset = 0
            while len(buffered_pcm) - offset >= PCM_FRAME_BYTES:
                frame = buffered_pcm[offset: offset + PCM_FRAME_BYTES]
                try:
                    self._input_frames.put_nowait((source_id, frame))
                except queue.Full:
                    accepted_all_frames = False
                    break
                offset += PCM_FRAME_BYTES
            self._pending_pcm[source_id] = buffered_pcm[offset:]
        return accepted_all_frames

    def disconnect(self, reason: str | None = None) -> None:
        with self._lock:
            if reason:
                self._encoder_error = reason
            listeners = list(self._listeners.values())
            self._listeners.clear()
            with self._pending_lock:
                self._pending_pcm.clear()
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
        with self._pending_lock:
            self._pending_pcm.clear()
        self._stop_event = threading.Event()
        command = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
            "-f", "s16le", "-ar", str(PCM_RATE), "-ac", str(PCM_CHANNELS),
            "-i", "pipe:0", "-vn", "-c:a", "libmp3lame", "-b:a", "128k",
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
        source_buffers = {}
        last_received_at = {}
        while not self._stop_event.is_set():
            self._fill_source_buffers(
                source_buffers, last_received_at, timeout=frame_seconds
            )
            now = time.monotonic()
            frames = []
            empty_sources = []
            for source_id, frames_buffer in source_buffers.items():
                if should_play_source_frame(
                    frames_buffer, last_received_at.get(source_id, 0), now
                ):
                    frames.append(frames_buffer.popleft())
                if not frames_buffer:
                    empty_sources.append(source_id)
            for source_id in empty_sources:
                source_buffers.pop(source_id, None)
                last_received_at.pop(source_id, None)
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

    def _fill_source_buffers(
        self,
        source_buffers: dict[object | None, deque[bytes]],
        last_received_at: dict[object | None, float],
        *,
        timeout: float,
    ) -> None:
        try:
            source_id, frame = self._input_frames.get(timeout=timeout)
            self._append_source_frame(source_buffers, source_id, frame)
            last_received_at[source_id] = time.monotonic()
        except queue.Empty:
            return

        while True:
            try:
                source_id, frame = self._input_frames.get_nowait()
                self._append_source_frame(source_buffers, source_id, frame)
                last_received_at[source_id] = time.monotonic()
            except queue.Empty:
                return

    @staticmethod
    def _append_source_frame(
        source_buffers: dict[object | None, deque[bytes]],
        source_id: object | None,
        frame: bytes,
    ) -> None:
        frames_buffer = source_buffers.setdefault(
            source_id, deque(maxlen=MAX_SOURCE_BUFFER_FRAMES)
        )
        frames_buffer.append(frame)

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
            should_stop = not self._listeners
            if should_stop:
                self._stop_locked()
        for _listener_id, chunks in slow_listeners:
            self._force_put(chunks, SlowClientError("Audio stream closed because the client was too slow"))

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


def chunk_pcm_frames(pcm: bytes) -> Iterator[bytes]:
    """Yield fixed-size 20 ms PCM frames, padding the final partial frame."""
    for offset in range(0, len(pcm), PCM_FRAME_BYTES):
        frame = pcm[offset: offset + PCM_FRAME_BYTES]
        if len(frame) < PCM_FRAME_BYTES:
            frame += bytes(PCM_FRAME_BYTES - len(frame))
        yield frame


def should_play_source_frame(
    frames_buffer: deque[bytes], last_received_at: float, now: float
) -> bool:
    """Keep a small jitter cushion, then drain when a speaker stops."""
    if len(frames_buffer) >= JITTER_BUFFER_FRAMES:
        return True
    return bool(frames_buffer) and now - last_received_at >= JITTER_DRAIN_SECONDS - 1e-9


def mix_pcm_frames(frames: list[bytes]) -> bytes:
    """Mix signed 16-bit little-endian PCM with headroom and saturation."""
    if not frames:
        return bytes(PCM_FRAME_BYTES)
    mixed = [0] * (PCM_FRAME_BYTES // PCM_SAMPLE_BYTES)
    for frame in frames:
        samples = array("h")
        samples.frombytes(frame[:PCM_FRAME_BYTES])
        for index, sample in enumerate(samples):
            mixed[index] += sample
    gain = MIX_HEADROOM / max(1, len(frames))
    output = array(
        "h", (max(-32768, min(32767, round(sample * gain))) for sample in mixed)
    )
    return output.tobytes()
