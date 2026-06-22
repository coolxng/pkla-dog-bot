"""Live browser microphone sessions that feed Discord voice playback."""

from __future__ import annotations

import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable

import discord

from audio_relay import PCM_CHANNELS, PCM_FRAME_BYTES, PCM_RATE


DEFAULT_BROWSER_TALK_CONTAINER = "webm"


@dataclass(frozen=True)
class BrowserTalkState:
    session_id: str | None
    channel_id: int | None
    channel_name: str | None
    active: bool
    closing: bool
    container_format: str | None
    error: str | None


@dataclass(frozen=True)
class BrowserTalkDebug:
    chunks_received: int
    bytes_received: int
    last_chunk_size: int


def container_format_for_mime_type(mime_type: str | None) -> str:
    mime_type = (mime_type or "").lower()
    if "ogg" in mime_type:
        return "ogg"
    return DEFAULT_BROWSER_TALK_CONTAINER


class LivePCMSource(discord.AudioSource):
    def __init__(self):
        self._condition = threading.Condition()
        self._buffer = bytearray()
        self._closed = False
        self._error: str | None = None

    def feed(self, pcm: bytes) -> None:
        if not pcm:
            return
        with self._condition:
            if self._closed:
                return
            self._buffer.extend(pcm)
            self._condition.notify_all()

    def close(self, error: str | None = None) -> None:
        with self._condition:
            self._closed = True
            if error and not self._error:
                self._error = error
            self._condition.notify_all()

    def read(self) -> bytes:
        deadline = time.monotonic() + 0.15
        with self._condition:
            while len(self._buffer) < PCM_FRAME_BYTES and not self._closed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(timeout=remaining)

            if len(self._buffer) >= PCM_FRAME_BYTES:
                frame = bytes(self._buffer[:PCM_FRAME_BYTES])
                del self._buffer[:PCM_FRAME_BYTES]
                return frame

            if self._closed:
                if not self._buffer:
                    return b""
                frame = bytes(self._buffer)
                self._buffer.clear()
                return frame.ljust(PCM_FRAME_BYTES, b"\x00")

            return b"\x00" * PCM_FRAME_BYTES

    def is_opus(self) -> bool:
        return False


class BrowserTalkSession:
    def __init__(
        self,
        *,
        voice_client,
        voice_channel,
        mime_type: str | None = None,
        process_factory: Callable[..., subprocess.Popen] = subprocess.Popen,
        on_finished: Callable[["BrowserTalkSession"], None] | None = None,
    ):
        self.session_id = uuid.uuid4().hex
        self.voice_client = voice_client
        self.voice_channel = voice_channel
        self.container_format = container_format_for_mime_type(mime_type)
        self._process_factory = process_factory
        self._on_finished = on_finished
        self._source = LivePCMSource()
        self._process: subprocess.Popen | None = None
        self._stdin_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._reader_thread: threading.Thread | None = None
        self._active = False
        self._closing = False
        self._finished = False
        self._error: str | None = None
        self._chunks_received = 0
        self._bytes_received = 0
        self._last_chunk_size = 0

    @property
    def active(self) -> bool:
        with self._state_lock:
            return self._active and not self._closing and not self._finished

    def start(self) -> None:
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-f",
            self.container_format,
            "-i",
            "pipe:0",
            "-vn",
            "-ac",
            str(PCM_CHANNELS),
            "-ar",
            str(PCM_RATE),
            "-f",
            "s16le",
            "pipe:1",
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
            raise RuntimeError(f"FFmpeg could not start: {error}") from error

        if process.stdin is None or process.stdout is None or process.stderr is None:
            process.terminate()
            raise RuntimeError("FFmpeg did not provide streaming pipes")

        self._process = process
        with self._state_lock:
            self._active = True

        try:
            self.voice_client.play(self._source, after=self._after_playback)
        except Exception:
            self._finalize("Discord could not start browser microphone playback")
            raise

        self._reader_thread = threading.Thread(
            target=self._read_loop,
            name=f"browser-talk-reader-{self.session_id}",
            daemon=True,
        )
        self._reader_thread.start()

    def submit_chunk(self, pcm_chunk: bytes) -> None:
        if not pcm_chunk:
            return
        with self._state_lock:
            if not self.active:
                raise RuntimeError("Browser talk is not active")
            process = self._process
            if process is None or process.stdin is None:
                raise RuntimeError("Browser talk is not ready")
            self._chunks_received += 1
            self._bytes_received += len(pcm_chunk)
            self._last_chunk_size = len(pcm_chunk)
        with self._stdin_lock:
            try:
                process.stdin.write(pcm_chunk)
                process.stdin.flush()
            except OSError as error:
                self._finalize(f"Browser microphone stream failed: {error}")
                raise RuntimeError("Browser microphone stream failed") from error

    def stop(self, reason: str | None = None) -> None:
        with self._state_lock:
            if self._finished or self._closing:
                return
            self._closing = True
            if reason and self._error is None:
                self._error = reason
            process = self._process
        if process is None or process.stdin is None:
            self._finalize(reason)
            return
        try:
            process.stdin.close()
        except OSError:
            pass

    def state(self) -> BrowserTalkState:
        with self._state_lock:
            return BrowserTalkState(
                session_id=self.session_id if self._active or self._closing else None,
                channel_id=getattr(self.voice_channel, "id", None),
                channel_name=getattr(self.voice_channel, "name", None),
                active=self._active and not self._closing and not self._finished,
                closing=self._closing,
                container_format=self.container_format,
                error=self._error,
            )

    def debug_state(self) -> BrowserTalkDebug:
        with self._state_lock:
            return BrowserTalkDebug(
                chunks_received=self._chunks_received,
                bytes_received=self._bytes_received,
                last_chunk_size=self._last_chunk_size,
            )

    def _after_playback(self, error) -> None:
        if error:
            self._finalize(f"Discord microphone playback stopped: {error}")
            return
        self._finalize(None)

    def _read_loop(self) -> None:
        process = self._process
        if process is None or process.stdout is None:
            self._finalize("FFmpeg stopped before browser talk started")
            return

        try:
            while True:
                chunk = process.stdout.read(4096)
                if not chunk:
                    break
                self._source.feed(chunk)
        finally:
            stderr_text = ""
            try:
                stderr = process.stderr
                if stderr is not None:
                    stderr_text = stderr.read().decode("utf-8", errors="replace").strip()
            except Exception:
                stderr_text = ""
            process.poll()
            error = stderr_text or (
                f"FFmpeg exited with code {process.returncode}"
                if process.returncode not in (None, 0)
                else None
            )
            self._finalize(error)

    def _finalize(self, error: str | None) -> None:
        with self._state_lock:
            if self._finished:
                return
            self._finished = True
            self._active = False
            self._closing = True
            if error and not self._error:
                self._error = error
            process = self._process
            self._process = None
        self._source.close(self._error)
        if process is not None:
            try:
                if process.stdin is not None and not process.stdin.closed:
                    process.stdin.close()
            except OSError:
                pass
            try:
                process.terminate()
            except OSError:
                pass
        if self._on_finished is not None:
            self._on_finished(self)

