import base64
import queue
import unittest
from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock, patch

import bot
from audio_relay import (
    PCM_FRAME_BYTES,
    AudioRelay,
    JITTER_BUFFER_FRAMES,
    JITTER_DRAIN_SECONDS,
    MAX_SOURCE_BUFFER_FRAMES,
    MIX_HEADROOM,
    RelayError,
    SlowClientError,
    chunk_pcm_frames,
    mix_pcm_frames,
    should_play_source_frame,
)


class StubRelay(AudioRelay):
    def _start_locked(self):
        self._encoder_error = None
        self._process = object()

    def _stop_locked(self):
        self._process = None
        self._stop_event.set()


class RelayLifecycleTests(unittest.TestCase):
    def test_listener_reference_count_starts_once_and_stops_after_final_listener(self):
        idle = Mock()
        relay = StubRelay(on_idle=idle)

        first = relay.add_listener()
        second = relay.add_listener()
        self.assertEqual(relay.state().listener_count, 2)
        self.assertTrue(relay.state().running)

        first.close()
        self.assertTrue(relay.state().running)
        second.close()
        self.assertFalse(relay.state().running)
        idle.assert_called_once_with()

    def test_client_close_removes_listener(self):
        relay = StubRelay()
        listener = relay.add_listener()
        listener.close()
        listener.close()
        self.assertEqual(relay.state().listener_count, 0)

    def test_slow_client_is_disconnected_when_bounded_queue_fills(self):
        relay = StubRelay(client_chunk_limit=1)
        listener = relay.add_listener()
        relay._broadcast(b"first")
        relay._broadcast(b"second")

        with self.assertRaises(SlowClientError):
            next(listener.iter_chunks())
        self.assertEqual(relay.state().listener_count, 0)

    def test_encoder_uses_higher_quality_mp3_settings(self):
        started_commands = []

        class FakeProcess:
            stdin = SimpleNamespace(close=Mock())
            stdout = SimpleNamespace(read=Mock(return_value=b""))
            stderr = SimpleNamespace()
            terminate = Mock()

        def process_factory(command, **_kwargs):
            started_commands.append(command)
            return FakeProcess()

        relay = AudioRelay(process_factory=process_factory)
        listener = relay.add_listener()
        listener.close()

        command = started_commands[0]
        self.assertIn("libmp3lame", command)
        self.assertIn("128k", command)

    def test_input_queue_is_bounded(self):
        relay = StubRelay(input_frame_limit=1)
        self.assertTrue(relay.submit_pcm(b"\x00" * PCM_FRAME_BYTES))
        self.assertFalse(relay.submit_pcm(b"\x00" * PCM_FRAME_BYTES))

    def test_debug_state_tracks_browser_relay_counters(self):
        relay = StubRelay(input_frame_limit=3)

        relay.submit_pcm(b"x" * 123, source_id=42)

        debug = relay.debug_state()
        self.assertEqual(debug.frames_received, 1)
        self.assertEqual(debug.bytes_received, 123)
        self.assertEqual(debug.last_frame_size, 123)
        self.assertEqual(debug.frames_queued, 0)
        self.assertEqual(debug.active_speakers, 1)

    def test_larger_pcm_chunks_are_split_into_20_ms_frames(self):
        pcm = b"\x01\x02" * (PCM_FRAME_BYTES // 2 + 100)
        frames = list(chunk_pcm_frames(pcm))

        self.assertEqual(len(frames), 2)
        self.assertEqual(len(frames[0]), PCM_FRAME_BYTES)
        self.assertEqual(len(frames[1]), PCM_FRAME_BYTES)
        self.assertEqual(frames[0], pcm[:PCM_FRAME_BYTES])
        self.assertTrue(frames[1].startswith(pcm[PCM_FRAME_BYTES:]))

    def test_submit_pcm_queues_complete_frames_and_buffers_partial_tail(self):
        relay = StubRelay(input_frame_limit=3)
        pcm = b"\x01\x02" * (PCM_FRAME_BYTES // 2 + 100)

        self.assertTrue(relay.submit_pcm(pcm, source_id=42))
        self.assertEqual(relay._input_frames.qsize(), 1)
        self.assertEqual(relay._pending_pcm[42], pcm[PCM_FRAME_BYTES:])

        first_source, first_frame = relay._input_frames.get_nowait()
        self.assertEqual(first_source, 42)
        self.assertEqual(first_frame, pcm[:PCM_FRAME_BYTES])

    def test_submit_pcm_combines_partial_chunks_before_queueing_frame(self):
        relay = StubRelay(input_frame_limit=3)
        first = b"a" * 100
        second = b"b" * (PCM_FRAME_BYTES - len(first))

        self.assertTrue(relay.submit_pcm(first, source_id=42))
        self.assertEqual(relay._input_frames.qsize(), 0)

        self.assertTrue(relay.submit_pcm(second, source_id=42))
        queued_source, queued_frame = relay._input_frames.get_nowait()
        self.assertEqual(queued_source, 42)
        self.assertEqual(queued_frame, first + second)
        self.assertEqual(relay._pending_pcm[42], b"")

    def test_source_buffer_keeps_bursty_frames_in_order(self):
        relay = StubRelay()
        source_buffers = {}
        first = b"a" * PCM_FRAME_BYTES
        second = b"b" * PCM_FRAME_BYTES

        relay._append_source_frame(source_buffers, 42, first)
        relay._append_source_frame(source_buffers, 42, second)

        self.assertEqual(list(source_buffers[42]), [first, second])

    def test_source_buffer_drops_oldest_frames_when_backlogged(self):
        relay = StubRelay()
        source_buffers = {42: deque(maxlen=MAX_SOURCE_BUFFER_FRAMES)}

        for frame_number in range(MAX_SOURCE_BUFFER_FRAMES + 1):
            frame = frame_number.to_bytes(2, "little") * (PCM_FRAME_BYTES // 2)
            relay._append_source_frame(source_buffers, 42, frame)

        oldest_frame = source_buffers[42][0]
        self.assertEqual(
            int.from_bytes(oldest_frame[:2], "little"),
            1,
        )

    def test_jitter_buffer_waits_for_a_small_cushion_before_playing(self):
        frames_buffer = deque([b"a" * PCM_FRAME_BYTES] * (JITTER_BUFFER_FRAMES - 1))
        now = 10.0

        self.assertFalse(
            should_play_source_frame(frames_buffer, now, now + JITTER_DRAIN_SECONDS / 2)
        )
        frames_buffer.append(b"b" * PCM_FRAME_BYTES)
        self.assertTrue(should_play_source_frame(frames_buffer, now, now))

    def test_jitter_buffer_drains_tail_after_source_goes_quiet(self):
        frames_buffer = deque([b"a" * PCM_FRAME_BYTES])
        now = 10.0

        self.assertTrue(
            should_play_source_frame(frames_buffer, now, now + JITTER_DRAIN_SECONDS)
        )

    def test_encoder_failure_closes_all_listeners(self):
        idle = Mock()
        relay = StubRelay(on_idle=idle)
        listener = relay.add_listener()
        relay._fail_encoder("encoder failed")

        with self.assertRaisesRegex(RelayError, "encoder failed"):
            next(listener.iter_chunks())
        self.assertEqual(relay.state().listener_count, 0)
        idle.assert_called_once_with()

    def test_fake_frames_are_mixed_with_headroom(self):
        positive = (20_000).to_bytes(2, "little", signed=True) * 1920
        mixed = mix_pcm_frames([positive, positive])
        self.assertEqual(
            int.from_bytes(mixed[:2], "little", signed=True),
            round(20_000 * MIX_HEADROOM),
        )

    def test_extreme_frames_are_mixed_with_saturation(self):
        positive = (32767).to_bytes(2, "little", signed=True) * 1920
        mixed = mix_pcm_frames([positive, positive, positive])
        self.assertLessEqual(int.from_bytes(mixed[:2], "little", signed=True), 32767)


class AudioAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.client = bot.app.test_client()

    def test_audio_stream_refuses_to_start_without_control_token(self):
        with patch.object(bot, "EXTERNAL_SAY_CONTROL_TOKEN", ""):
            response = self.client.get("/say/audio/123")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["Cache-Control"], "no-store, no-cache, must-revalidate, private")

    def test_page_shows_browser_listening_controls_without_control_token(self):
        encoded = base64.b64encode(b"user:secret-token").decode()
        with patch.object(bot, "EXTERNAL_SAY_CONTROL_TOKEN", "secret-token"):
            response = self.client.get(
                "/say", headers={"Authorization": f"Basic {encoded}"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Start listening", response.data)
        self.assertIn(b"WebSocket", response.data)
        self.assertIn(b"Test sound", response.data)
        self.assertIn(
            b'new WebSocket(`${protocol}://${window.location.host}/say/listen?', response.data
        )
        self.assertIn(
            b'const startListening = document.getElementById("start-listening")',
            response.data,
        )
        self.assertNotIn(b"secret-token", response.data)
        self.assertEqual(
            response.headers["Cache-Control"],
            "no-store, no-cache, must-revalidate, private",
        )


class BrowserTalkAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.client = bot.app.test_client()

    def test_page_shows_browser_talk_controls(self):
        encoded = base64.b64encode(b"user:secret-token").decode()
        with patch.object(bot, "EXTERNAL_SAY_CONTROL_TOKEN", "secret-token"):
            response = self.client.get(
                "/say", headers={"Authorization": f"Basic {encoded}"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Talk from browser", response.data)
        self.assertIn(b"Start talking", response.data)
        self.assertIn(b"Microphone diagnostics", response.data)
        self.assertIn(b"/say/talk/start", response.data)
        self.assertIn(b"/say/talk/chunk/", response.data)
        self.assertIn(b"/say/talk/stop", response.data)

    def test_talk_routes_require_authentication(self):
        with patch.object(bot, "EXTERNAL_SAY_CONTROL_TOKEN", "secret-token"):
            start = self.client.post("/say/talk/start", json={"voice_channel_id": "123"})
            chunk = self.client.post("/say/talk/chunk/abc", data=b"abc")
            stop = self.client.post("/say/talk/stop", json={"session_id": "abc"})
            status = self.client.get("/say/talk-status")

        self.assertEqual(start.status_code, 401)
        self.assertEqual(chunk.status_code, 401)
        self.assertEqual(stop.status_code, 401)
        self.assertEqual(status.status_code, 401)

    def test_talk_routes_forward_payloads(self):
        encoded = base64.b64encode(b"user:secret-token").decode()
        with (
            patch.object(bot, "EXTERNAL_SAY_CONTROL_TOKEN", "secret-token"),
            patch.object(bot, "submit_browser_talk_start", return_value={
                "session_id": "session-1",
                "voice_channel_id": 123,
                "voice_channel_name": "General",
            }) as start,
            patch.object(bot, "submit_browser_talk_chunk") as chunk,
            patch.object(bot, "submit_browser_talk_stop", return_value={
                "state": "stopping",
                "session_id": "session-1",
            }) as stop,
            patch.object(
                bot, "browser_talk_state_payload", return_value={"state": "recording"}
            ) as state_payload,
        ):
            start_response = self.client.post(
                "/say/talk/start",
                json={"voice_channel_id": 123, "mime_type": "audio/webm;codecs=opus"},
                headers={"Authorization": f"Basic {encoded}"},
            )
            chunk_response = self.client.post(
                "/say/talk/chunk/session-1",
                data=b"audio-bytes",
                headers={"Authorization": f"Basic {encoded}"},
            )
            stop_response = self.client.post(
                "/say/talk/stop",
                json={"session_id": "session-1"},
                headers={"Authorization": f"Basic {encoded}"},
            )
            status_response = self.client.get(
                "/say/talk-status", headers={"Authorization": f"Basic {encoded}"}
            )

        self.assertEqual(start_response.status_code, 200)
        self.assertEqual(chunk_response.status_code, 204)
        self.assertEqual(stop_response.status_code, 200)
        self.assertEqual(status_response.status_code, 200)
        start.assert_called_once_with(123, "audio/webm;codecs=opus")
        chunk.assert_called_once_with("session-1", b"audio-bytes")
        stop.assert_called_once_with("session-1")
        state_payload.assert_called_once_with()

    def test_audio_status_requires_authentication_and_returns_debug_counters(self):
        wrong = base64.b64encode(b"user:wrong").decode()
        correct = base64.b64encode(b"user:secret-token").decode()
        relay_state = SimpleNamespace(listener_count=1)
        debug_state = SimpleNamespace(
            frames_received=12,
            bytes_received=3456,
            last_frame_size=7680,
            frames_queued=2,
            active_speakers=1,
        )
        with (
            patch.object(bot, "EXTERNAL_SAY_CONTROL_TOKEN", "secret-token"),
            patch.object(bot.browser_pcm_relay, "state", return_value=relay_state),
            patch.object(bot.browser_pcm_relay, "debug_state", return_value=debug_state),
        ):
            denied = self.client.get(
                "/say/audio-status", headers={"Authorization": f"Basic {wrong}"}
            )
            allowed = self.client.get(
                "/say/audio-status", headers={"Authorization": f"Basic {correct}"}
            )

        self.assertEqual(denied.status_code, 401)
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.json["frames_received"], 12)
        self.assertEqual(allowed.json["active_speakers"], 1)

    def test_stream_listener_closes_when_discord_receive_start_fails(self):
        correct = base64.b64encode(b"user:secret-token").decode()
        fake_listener = SimpleNamespace(close=Mock())
        with (
            patch.object(bot, "EXTERNAL_SAY_CONTROL_TOKEN", "secret-token"),
            patch.object(
                bot,
                "submit_browser_audio_session",
                side_effect=RuntimeError("receive unavailable"),
            ),
            patch.object(
                bot.browser_audio_relay, "add_listener", return_value=fake_listener
            ),
        ):
            response = self.client.get(
                "/say/audio/123", headers={"Authorization": f"Basic {correct}"}
            )

        self.assertEqual(response.status_code, 503)
        fake_listener.close.assert_called_once_with()

    def test_every_audio_stream_request_requires_valid_basic_auth(self):
        wrong = base64.b64encode(b"user:wrong").decode()
        correct = base64.b64encode(b"user:secret-token").decode()
        fake_listener = SimpleNamespace(iter_chunks=lambda: iter([b"audio"]), close=Mock())
        with (
            patch.object(bot, "EXTERNAL_SAY_CONTROL_TOKEN", "secret-token"),
            patch.object(bot, "submit_browser_audio_session") as start,
            patch.object(bot.browser_audio_relay, "add_listener", return_value=fake_listener),
        ):
            unauthorized = self.client.get("/say/audio/123")
            invalid = self.client.get(
                "/say/audio/123", headers={"Authorization": f"Basic {wrong}"}
            )
            authorized = self.client.get(
                "/say/audio/123", headers={"Authorization": f"Basic {correct}"}
            )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(authorized.status_code, 200)
        self.assertEqual(authorized.data, b"audio")
        start.assert_called_once_with(123)
        self.assertEqual(authorized.headers["X-Accel-Buffering"], "no")
        self.assertEqual(authorized.headers["Cache-Control"], "no-store, no-cache, must-revalidate, private")


class ReceiveSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        bot.active_receive_channel_id = None
        bot.active_receive_sink = None

    async def test_multiple_browser_starts_reuse_one_discord_listener(self):
        class FakeVoiceChannel:
            pass

        channel = FakeVoiceChannel()
        channel.id = 123
        voice_client = SimpleNamespace(
            channel=channel,
            is_connected=lambda: True,
            is_listening=Mock(side_effect=[False, True]),
            listen=Mock(),
            is_playing=lambda: False,
        )
        channel.guild = SimpleNamespace(id=9, voice_client=voice_client)
        sink = object()
        with (
            patch.object(bot, "EXTERNAL_SAY_CONTROL_TOKEN", "secret"),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
            patch.object(bot.client, "get_channel", return_value=channel),
            patch.object(bot, "create_browser_audio_sink", return_value=sink),
        ):
            await bot.start_browser_audio_session(123)
            await bot.start_browser_audio_session(123)

        voice_client.listen.assert_called_once_with(sink)
        self.assertEqual(bot.active_receive_channel_id, 123)

    async def test_shared_sink_forwards_pcm_to_browser(self):
        class FakeAudioSink:
            def __init__(self):
                pass

        channel = SimpleNamespace(id=123, guild=SimpleNamespace(id=9))
        voice_client = SimpleNamespace(channel=channel, is_playing=lambda: False)
        user = SimpleNamespace(id=42)
        data = SimpleNamespace(pcm=b"\x01\x02" * 1920)
        with (
            patch.object(bot, "voice_recv", SimpleNamespace(AudioSink=FakeAudioSink)),
            patch.object(bot, "client", SimpleNamespace(user=None)),
            patch.object(bot.browser_pcm_relay, "submit_pcm") as submit_pcm,
        ):
            sink = bot.create_browser_audio_sink(voice_client)
            sink.write(user, data)

        submit_pcm.assert_called_once_with(data.pcm, source_id=42)

    async def test_shared_sink_relays_participants_while_bot_is_playing(self):
        class FakeAudioSink:
            def __init__(self):
                pass

        channel = SimpleNamespace(id=123, guild=SimpleNamespace(id=9))
        voice_client = SimpleNamespace(channel=channel, is_playing=lambda: True)
        user = SimpleNamespace(id=42)
        data = SimpleNamespace(pcm=b"\x01\x02" * 1920)
        with (
            patch.object(bot, "voice_recv", SimpleNamespace(AudioSink=FakeAudioSink)),
            patch.object(bot, "client", SimpleNamespace(user=None)),
            patch.object(bot.browser_pcm_relay, "submit_pcm") as submit_pcm,
        ):
            sink = bot.create_browser_audio_sink(voice_client)
            sink.write(user, data)

        submit_pcm.assert_called_once_with(data.pcm, source_id=42)

    async def test_idle_receive_session_stops_discord_listener(self):
        voice_client = SimpleNamespace(is_listening=lambda: True, stop_listening=Mock())
        channel = SimpleNamespace(guild=SimpleNamespace(voice_client=voice_client))
        bot.active_receive_channel_id = 123
        with (
            patch.object(bot.browser_pcm_relay, "state") as state,
            patch.object(bot.client, "get_channel", return_value=channel),
        ):
            state.return_value = SimpleNamespace(listener_count=0)
            await bot.stop_receive_session_if_idle()

        voice_client.stop_listening.assert_called_once_with()
        self.assertIsNone(bot.active_receive_channel_id)


class DiscordReceiveCleanupTests(unittest.TestCase):
    def test_discord_disconnect_closes_browser_streams(self):
        with patch.object(bot.browser_audio_relay, "disconnect") as disconnect:
            bot.close_receive_session("Discord voice connection closed")

        disconnect.assert_called_once_with("Discord voice connection closed")
        self.assertIsNone(bot.active_receive_channel_id)
        self.assertIsNone(bot.active_receive_sink)


if __name__ == "__main__":
    unittest.main()
