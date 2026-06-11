import base64
import queue
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import bot
from audio_relay import AudioRelay, RelayError, SlowClientError, mix_pcm_frames


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

    def test_transcription_reference_keeps_encoder_alive(self):
        relay = StubRelay()
        listener = relay.add_listener()
        relay.set_transcription_active(True)

        listener.close()
        self.assertTrue(relay.state().running)
        relay.set_transcription_active(False)
        self.assertFalse(relay.state().running)

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

    def test_input_queue_is_bounded(self):
        relay = StubRelay(input_frame_limit=1)
        self.assertTrue(relay.submit_pcm(b"\x00\x00"))
        self.assertFalse(relay.submit_pcm(b"\x00\x00"))

    def test_encoder_failure_closes_all_listeners(self):
        idle = Mock()
        relay = StubRelay(on_idle=idle)
        listener = relay.add_listener()
        relay._fail_encoder("encoder failed")

        with self.assertRaisesRegex(RelayError, "encoder failed"):
            next(listener.iter_chunks())
        self.assertEqual(relay.state().listener_count, 0)
        idle.assert_called_once_with()

    def test_fake_frames_are_mixed_with_saturation(self):
        positive = (20_000).to_bytes(2, "little", signed=True) * 1920
        mixed = mix_pcm_frames([positive, positive])
        self.assertEqual(int.from_bytes(mixed[:2], "little", signed=True), 32767)


class AudioAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.client = bot.app.test_client()

    def test_audio_stream_refuses_to_start_without_control_token(self):
        with patch.object(bot, "EXTERNAL_SAY_CONTROL_TOKEN", ""):
            response = self.client.get("/say/audio/123")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["Cache-Control"], "no-store, no-cache, must-revalidate, private")

    def test_listening_controls_do_not_embed_control_token(self):
        encoded = base64.b64encode(b"user:secret-token").decode()
        with patch.object(bot, "EXTERNAL_SAY_CONTROL_TOKEN", "secret-token"):
            response = self.client.get(
                "/say", headers={"Authorization": f"Basic {encoded}"}
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Start listening", response.data)
        self.assertIn(b"Mute", response.data)
        self.assertIn(b"Stop listening", response.data)
        self.assertNotIn(b"secret-token", response.data)
        self.assertEqual(
            response.headers["Cache-Control"],
            "no-store, no-cache, must-revalidate, private",
        )

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
        voice_client = SimpleNamespace(
            channel=channel,
            is_connected=lambda: True,
            is_listening=Mock(side_effect=[False, True]),
            listen=Mock(),
            is_playing=lambda: False,
        )
        channel.guild = SimpleNamespace(voice_client=voice_client)
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

    async def test_idle_receive_session_stops_discord_listener(self):
        voice_client = SimpleNamespace(is_listening=lambda: True, stop_listening=Mock())
        channel = SimpleNamespace(guild=SimpleNamespace(voice_client=voice_client))
        bot.active_receive_channel_id = 123
        with (
            patch.object(bot.browser_audio_relay, "state") as state,
            patch.object(bot.client, "get_channel", return_value=channel),
        ):
            state.return_value = SimpleNamespace(listener_count=0, transcription_active=False)
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
