import unittest

from browser_talk import BrowserTalkSession


class BrowserTalkSessionTests(unittest.TestCase):
    def test_submit_chunk_writes_to_ffmpeg_without_reentering_state_lock(self):
        class FakeInput:
            def __init__(self):
                self.closed = False
                self.written = b""
                self.flush_count = 0

            def write(self, data):
                self.written += data

            def flush(self):
                self.flush_count += 1

        class FakeProcess:
            def __init__(self):
                self.stdin = FakeInput()

        session = BrowserTalkSession(voice_client=object(), voice_channel=object())
        process = FakeProcess()
        session._process = process
        session._active = True

        session.submit_chunk(b"browser-microphone-audio")

        self.assertEqual(process.stdin.written, b"browser-microphone-audio")
        self.assertEqual(process.stdin.flush_count, 1)
        self.assertEqual(session.debug_state().chunks_received, 1)
