import unittest

import bot


class PingResponseTests(unittest.TestCase):
    def test_exact_ping_matches_case_insensitively(self):
        self.assertEqual(bot.ping_response_for("ping Jamal"), "<@1247415021080678452>")

    def test_ping_with_bot_mention_matches(self):
        self.assertEqual(bot.ping_response_for("<@1234567890> ping jamal"), "<@1247415021080678452>")

    def test_polite_ping_request_matches(self):
        self.assertEqual(bot.ping_response_for("can you ping jamal please"), "<@1247415021080678452>")

    def test_multiple_ping_targets_match(self):
        self.assertEqual(
            bot.ping_response_for("ping ozzy and jamal"),
            "<@586732970283630633> <@1247415021080678452>",
        )

    def test_ping_with_message_matches_without_model_fallback(self):
        self.assertEqual(
            bot.ping_response_for("ping jamal and say he finna go back to jail"),
            "<@1247415021080678452>, you finna go back to jail",
        )

    def test_multiple_ping_targets_with_message_match(self):
        self.assertEqual(
            bot.ping_response_for("ping ozzy and jamal and say get on"),
            "<@586732970283630633> <@1247415021080678452>, get on",
        )

    def test_short_j_ping_still_matches_jaedon(self):
        self.assertEqual(bot.ping_response_for("ping j"), "<@1149829095958528020>")

    def test_unrelated_text_does_not_ping(self):
        self.assertIsNone(bot.ping_response_for("why did you ping jamal"))


class ConversationHistoryTests(unittest.TestCase):
    def setUp(self):
        bot.conversation_history.clear()
        bot.channel_conversation_history.clear()

    def test_channel_history_is_shared_and_labels_speakers(self):
        bot.add_to_active_history(123, 1, "user", "remember this", is_dm=False, display_name="Alice")
        bot.add_to_active_history(123, 1, "assistant", "got it", is_dm=False)

        history = bot.get_active_history(123, 2, is_dm=False)

        self.assertEqual(
            history,
            [
                {"role": "user", "content": "Alice: remember this"},
                {"role": "assistant", "content": "got it"},
            ],
        )

    def test_dm_history_stays_per_user_without_speaker_label(self):
        bot.add_to_active_history(999, 1, "user", "private context", is_dm=True, display_name="Alice")

        self.assertEqual(
            bot.get_active_history(999, 1, is_dm=True),
            [{"role": "user", "content": "private context"}],
        )
        self.assertEqual(bot.get_active_history(999, 2, is_dm=True), [])

    def test_clear_active_history_clears_only_current_channel(self):
        bot.add_to_active_history(123, 1, "user", "first", is_dm=False, display_name="Alice")
        bot.add_to_active_history(456, 2, "user", "second", is_dm=False, display_name="Bob")

        bot.clear_active_history(123, 1, is_dm=False)

        self.assertEqual(bot.get_active_history(123, 1, is_dm=False), [])
        self.assertEqual(
            bot.get_active_history(456, 2, is_dm=False),
            [{"role": "user", "content": "Bob: second"}],
        )


class OpenAIConfigTests(unittest.TestCase):
    def test_default_model_uses_chatgpt_like_alias(self):
        self.assertEqual(bot.DEFAULT_OPENAI_MODEL, "chat-latest")

    def test_gpt5_reasoning_effort_defaults_to_none(self):
        self.assertEqual(bot.default_reasoning_effort("gpt-5.5"), "none")

    def test_system_prompt_keeps_chatgpt_like_behavior(self):
        self.assertIn("Respond like ChatGPT", bot.SYSTEM_PROMPT)
        self.assertIn("Discord chat", bot.SYSTEM_PROMPT)

class ExternalSayTests(unittest.TestCase):
    def setUp(self):
        self.client = bot.app.test_client()

    def test_page_is_available_without_a_control_token(self):
        response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Make the bot say something", response.data)
        self.assertIn(b'/favicon.ico?v=1', response.data)
        self.assertNotIn(b'name="token"', response.data)

    def test_page_lists_ping_members_with_copyable_mentions(self):
        response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Ping a member", response.data)
        self.assertIn(b"Ozzy", response.data)
        self.assertIn(b"586732970283630633", response.data)
        self.assertIn(b'data-mention="&lt;@586732970283630633&gt;"', response.data)
        jaedon_members = [
            member
            for member in bot.external_ping_members()
            if member["user_id"] == "1149829095958528020"
        ]
        self.assertEqual(len(jaedon_members), 1)

    def test_favicon_is_available_at_browser_default_path(self):
        response = self.client.get("/favicon.ico")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "image/png")
        self.assertTrue(response.data.startswith(b"\x89PNG\r\n\x1a\n"))
        response.close()

    def test_empty_message_is_rejected(self):
        response = self.client.post("/say", data={"message": "   "})

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Enter a message first", response.data)

    def test_valid_form_redirects_and_refresh_does_not_resubmit(self):
        submitted_messages = []
        original_submit = bot.submit_external_message
        bot.submit_external_message = submitted_messages.append
        try:
            response = self.client.post(
                "/say", data={"message": "hello Discord"}
            )
            redirected_response = self.client.get(response.headers["Location"])
            refreshed_response = self.client.get(response.headers["Location"])
        finally:
            bot.submit_external_message = original_submit

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["Location"], "/say?sent=1")
        self.assertEqual(redirected_response.status_code, 200)
        self.assertIn(b"Message sent", redirected_response.data)
        self.assertEqual(refreshed_response.status_code, 200)
        self.assertEqual(submitted_messages, ["hello Discord"])


if __name__ == "__main__":
    unittest.main()
