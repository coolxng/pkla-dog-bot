import unittest

import bot


class PingResponseTests(unittest.TestCase):
    def test_exact_ping_matches_case_insensitively(self):
        self.assertEqual(bot.ping_response_for("ping Jamal"), "<@1247415021080678452>")

    def test_ping_with_bot_mention_matches(self):
        self.assertEqual(bot.ping_response_for("<@1234567890> ping jamal"), "<@1247415021080678452>")

    def test_polite_ping_request_matches(self):
        self.assertEqual(bot.ping_response_for("can you ping jamal please"), "<@1247415021080678452>")

    def test_short_j_ping_still_matches_jaedon(self):
        self.assertEqual(bot.ping_response_for("ping j"), "<@1149829095958528020>")

    def test_unrelated_text_does_not_ping(self):
        self.assertIsNone(bot.ping_response_for("why did you ping jamal"))


if __name__ == "__main__":
    unittest.main()
