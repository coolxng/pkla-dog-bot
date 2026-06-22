import unittest

from pcm_relay import PcmRelay


class PcmRelayTests(unittest.TestCase):
    def test_broadcasts_raw_pcm_with_the_original_speaker_id(self):
        relay = PcmRelay()
        listener = relay.add_listener()

        relay.submit_pcm(b"decoded-discord-pcm", source_id=42)

        self.assertEqual(listener.get(), (42, b"decoded-discord-pcm"))
        debug = relay.debug_state()
        self.assertEqual(debug.frames_received, 1)
        self.assertEqual(debug.active_speakers, 1)

    def test_last_listener_runs_idle_cleanup(self):
        calls = []
        relay = PcmRelay(on_idle=lambda: calls.append("idle"))
        listener = relay.add_listener()

        listener.close()

        self.assertEqual(calls, ["idle"])
        self.assertEqual(relay.state().listener_count, 0)
