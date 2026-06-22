"""Low-latency per-speaker PCM fan-out for browser WebSocket listeners."""

from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass


_STOP = object()
DEFAULT_LISTENER_FRAMES = 100


@dataclass(frozen=True)
class PcmRelayState:
    listener_count: int


@dataclass(frozen=True)
class PcmRelayDebug:
    frames_received: int
    bytes_received: int
    last_frame_size: int
    frames_queued: int
    active_speakers: int


class PcmRelayListener:
    def __init__(self, relay: "PcmRelay", listener_id: str, frames: queue.Queue):
        self._relay = relay
        self._listener_id = listener_id
        self._frames = frames
        self._closed = False

    def get(self):
        frame = self._frames.get()
        if frame is _STOP:
            return None
        return frame

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._relay.remove_listener(self._listener_id)


class PcmRelay:
    """Broadcasts decoded Discord PCM frames without mixing or re-encoding them."""

    def __init__(
        self,
        *,
        listener_frame_limit: int = DEFAULT_LISTENER_FRAMES,
        on_idle=None,
    ):
        self._listener_frame_limit = listener_frame_limit
        self._on_idle = on_idle
        self._listeners: dict[str, queue.Queue] = {}
        self._lock = threading.Lock()
        self._frames_received = 0
        self._bytes_received = 0
        self._last_frame_size = 0
        self._source_last_received_at: dict[object | None, float] = {}

    def state(self) -> PcmRelayState:
        with self._lock:
            return PcmRelayState(listener_count=len(self._listeners))

    def debug_state(self) -> PcmRelayDebug:
        now = time.monotonic()
        with self._lock:
            return PcmRelayDebug(
                frames_received=self._frames_received,
                bytes_received=self._bytes_received,
                last_frame_size=self._last_frame_size,
                frames_queued=sum(listener.qsize() for listener in self._listeners.values()),
                active_speakers=sum(
                    received_at >= now - 2
                    for received_at in self._source_last_received_at.values()
                ),
            )

    def add_listener(self) -> PcmRelayListener:
        listener_id = uuid.uuid4().hex
        frames: queue.Queue = queue.Queue(maxsize=self._listener_frame_limit)
        with self._lock:
            self._listeners[listener_id] = frames
        return PcmRelayListener(self, listener_id, frames)

    def remove_listener(self, listener_id: str) -> None:
        became_idle = False
        with self._lock:
            removed = self._listeners.pop(listener_id, None)
            became_idle = removed is not None and not self._listeners
        if became_idle and self._on_idle is not None:
            self._on_idle()

    def submit_pcm(self, pcm: bytes, *, source_id: object | None = None) -> None:
        if not pcm:
            return
        with self._lock:
            self._frames_received += 1
            self._bytes_received += len(pcm)
            self._last_frame_size = len(pcm)
            self._source_last_received_at[source_id] = time.monotonic()
            for frames in self._listeners.values():
                try:
                    frames.put_nowait((source_id, bytes(pcm)))
                except queue.Full:
                    # Drop stale frames instead of allowing one slow browser to delay live audio.
                    try:
                        frames.get_nowait()
                    except queue.Empty:
                        pass
                    try:
                        frames.put_nowait((source_id, bytes(pcm)))
                    except queue.Full:
                        pass

    def disconnect(self) -> None:
        with self._lock:
            listeners = list(self._listeners.values())
            self._listeners.clear()
            self._source_last_received_at.clear()
        for frames in listeners:
            try:
                frames.put_nowait(_STOP)
            except queue.Full:
                try:
                    frames.get_nowait()
                except queue.Empty:
                    pass
                frames.put_nowait(_STOP)
