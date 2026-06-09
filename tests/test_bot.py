import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

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

    def test_reqo_ping_uses_renamed_member(self):
        self.assertEqual(bot.ping_response_for("ping reqo"), "<@375402301646700546>")
        self.assertIsNone(bot.ping_response_for("ping red"))

    def test_hayden_ping_matches(self):
        self.assertEqual(bot.ping_response_for("ping hayden"), "<@1069346669566623928>")

    def test_6uke_ping_matches(self):
        self.assertEqual(bot.ping_response_for("ping 6uke"), "<@1135595806171332760>")

    def test_tom_pearls_ping_matches(self):
        self.assertEqual(bot.ping_response_for("ping tom pearls"), "<@607667203126591509>")

    def test_unrelated_text_does_not_ping(self):
        self.assertIsNone(bot.ping_response_for("why did you ping jamal"))


class BarkAudioTests(unittest.IsolatedAsyncioTestCase):
    def test_bark_audio_file_exists(self):
        self.assertTrue(bot.BARK_AUDIO_PATH.is_file())
        self.assertEqual(bot.BARK_AUDIO_PATH.name, "pkla-dog-bark.mp3")

    def test_play_bark_starts_mp3_audio(self):
        voice_client = SimpleNamespace(is_playing=lambda: False, play=Mock())
        audio_source = Mock()

        with patch.object(bot.discord, "FFmpegPCMAudio", return_value=audio_source) as ffmpeg_audio:
            played = bot.play_bark(voice_client)

        self.assertTrue(played)
        ffmpeg_audio.assert_called_once_with(str(bot.BARK_AUDIO_PATH))
        voice_client.play.assert_called_once()
        self.assertIs(voice_client.play.call_args.args[0], audio_source)
        self.assertIn("after", voice_client.play.call_args.kwargs)

    def test_play_bark_does_not_interrupt_existing_audio(self):
        voice_client = SimpleNamespace(is_playing=lambda: True, play=Mock())

        played = bot.play_bark(voice_client)

        self.assertFalse(played)
        voice_client.play.assert_not_called()

    async def test_periodic_task_waits_then_plays_bark(self):
        voice_client = SimpleNamespace(is_connected=lambda: True)
        guild = SimpleNamespace(voice_client=voice_client)

        with (
            patch.object(
                bot.asyncio,
                "sleep",
                new=AsyncMock(side_effect=[None, asyncio.CancelledError]),
            ) as sleep,
            patch.object(bot, "play_bark") as play_bark,
        ):
            with self.assertRaises(asyncio.CancelledError):
                await bot.bark_periodically(guild)

        sleep.assert_any_await(bot.BARK_INTERVAL_SECONDS)
        play_bark.assert_called_once_with(voice_client)


class BarkCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bot.last_command_bark_at.clear()

    def test_bark_requires_an_active_voice_connection(self):
        message = SimpleNamespace(guild=SimpleNamespace(id=456, voice_client=None))

        response = bot.bark_on_command(message)

        self.assertEqual(response, "join me to a voice channel first with !join")

    def test_bark_plays_immediately_and_starts_cooldown(self):
        voice_client = SimpleNamespace(is_connected=lambda: True)
        message = SimpleNamespace(guild=SimpleNamespace(id=456, voice_client=voice_client))

        with (
            patch.object(bot.time, "monotonic", return_value=100.0),
            patch.object(bot, "play_bark", return_value=True) as play_bark,
        ):
            response = bot.bark_on_command(message)

        self.assertEqual(response, "woof")
        play_bark.assert_called_once_with(voice_client)
        self.assertEqual(bot.last_command_bark_at[456], 100.0)

    def test_bark_has_five_second_server_cooldown(self):
        voice_client = SimpleNamespace(is_connected=lambda: True)
        message = SimpleNamespace(guild=SimpleNamespace(id=456, voice_client=voice_client))
        bot.last_command_bark_at[456] = 100.0

        with (
            patch.object(bot.time, "monotonic", return_value=101.2),
            patch.object(bot, "play_bark") as play_bark,
        ):
            response = bot.bark_on_command(message)

        self.assertEqual(response, "bark cooldown — wait 4 seconds")
        play_bark.assert_not_called()

    def test_bark_can_play_again_after_five_seconds(self):
        voice_client = SimpleNamespace(is_connected=lambda: True)
        message = SimpleNamespace(guild=SimpleNamespace(id=456, voice_client=voice_client))
        bot.last_command_bark_at[456] = 100.0

        with (
            patch.object(bot.time, "monotonic", return_value=105.0),
            patch.object(bot, "play_bark", return_value=True) as play_bark,
        ):
            response = bot.bark_on_command(message)

        self.assertEqual(response, "woof")
        play_bark.assert_called_once_with(voice_client)

    async def test_bark_command_is_handled_without_calling_chat_model(self):
        channel_id = next(iter(bot.TARGET_CHANNEL_IDS))
        voice_client = SimpleNamespace(is_connected=lambda: True)
        text_channel = SimpleNamespace(id=channel_id, send=AsyncMock())
        message = SimpleNamespace(
            author=SimpleNamespace(id=123, display_name="Tester"),
            channel=text_channel,
            content="!bark",
            guild=SimpleNamespace(id=456, voice_client=voice_client),
        )

        with (
            patch.object(bot, "call_model", new_callable=AsyncMock) as call_model,
            patch.object(bot.time, "monotonic", return_value=100.0),
            patch.object(bot, "play_bark", return_value=True) as play_bark,
        ):
            await bot.on_message(message)

        play_bark.assert_called_once_with(voice_client)
        text_channel.send.assert_awaited_once_with("woof")
        call_model.assert_not_awaited()


class VoiceJoinTests(unittest.IsolatedAsyncioTestCase):
    async def test_join_connects_and_barks_immediately(self):
        voice_client = SimpleNamespace()
        voice_channel = SimpleNamespace(
            mention="#General",
            connect=AsyncMock(return_value=voice_client),
        )
        message = SimpleNamespace(
            guild=SimpleNamespace(voice_client=None),
            author=SimpleNamespace(voice=SimpleNamespace(channel=voice_channel)),
        )

        with (
            patch.object(bot, "start_bark_task") as start_bark_task,
            patch.object(bot.asyncio, "sleep", new=AsyncMock()) as sleep,
            patch.object(bot, "play_bark", return_value=True) as play_bark,
        ):
            response = await bot.join_author_voice(message)

        voice_channel.connect.assert_awaited_once_with(self_deaf=False, self_mute=False)
        start_bark_task.assert_called_once_with(message.guild)
        sleep.assert_awaited_once_with(bot.BARK_JOIN_DELAY_SECONDS)
        play_bark.assert_called_once_with(voice_client)
        self.assertEqual(response, "joined #General")

    async def test_join_requires_the_user_to_be_in_voice(self):
        message = SimpleNamespace(
            guild=SimpleNamespace(voice_client=None),
            author=SimpleNamespace(voice=None),
        )

        response = await bot.join_author_voice(message)

        self.assertEqual(response, "join a voice channel first, then send !join")

    async def test_join_moves_an_existing_voice_connection(self):
        old_channel = SimpleNamespace(mention="#Old")
        new_channel = SimpleNamespace(mention="#New")
        voice_client = SimpleNamespace(
            channel=old_channel,
            is_connected=lambda: True,
            move_to=AsyncMock(),
        )
        message = SimpleNamespace(
            guild=SimpleNamespace(voice_client=voice_client),
            author=SimpleNamespace(voice=SimpleNamespace(channel=new_channel)),
        )

        with (
            patch.object(bot, "start_bark_task") as start_bark_task,
            patch.object(bot.asyncio, "sleep", new=AsyncMock()),
            patch.object(bot, "play_bark", return_value=True) as play_bark,
        ):
            response = await bot.join_author_voice(message)

        voice_client.move_to.assert_awaited_once_with(new_channel)
        start_bark_task.assert_called_once_with(message.guild)
        play_bark.assert_called_once_with(voice_client)
        self.assertEqual(response, "joined #New")

    async def test_join_command_is_handled_without_calling_chat_model(self):
        channel_id = next(iter(bot.TARGET_CHANNEL_IDS))
        voice_client = SimpleNamespace()
        voice_channel = SimpleNamespace(
            mention="#General",
            connect=AsyncMock(return_value=voice_client),
        )
        text_channel = SimpleNamespace(id=channel_id, send=AsyncMock())
        message = SimpleNamespace(
            author=SimpleNamespace(
                id=123,
                display_name="Tester",
                voice=SimpleNamespace(channel=voice_channel),
            ),
            channel=text_channel,
            content="!join",
            guild=SimpleNamespace(voice_client=None),
        )

        with (
            patch.object(bot, "call_model", new_callable=AsyncMock) as call_model,
            patch.object(bot, "start_bark_task") as start_bark_task,
            patch.object(bot.asyncio, "sleep", new=AsyncMock()),
            patch.object(bot, "play_bark", return_value=True) as play_bark,
        ):
            await bot.on_message(message)

        voice_channel.connect.assert_awaited_once_with(self_deaf=False, self_mute=False)
        start_bark_task.assert_called_once_with(message.guild)
        play_bark.assert_called_once_with(voice_client)
        text_channel.send.assert_awaited_once_with("joined #General")
        call_model.assert_not_awaited()


class ExternalVoiceControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_external_join_uses_requested_voice_channel(self):
        class FakeVoiceChannel:
            pass

        channel = FakeVoiceChannel()
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
            patch.object(bot, "join_voice_channel", new=AsyncMock(return_value="joined #General")) as join_voice,
        ):
            response = await bot.control_external_voice("join", 1447148315312521256)

        self.assertEqual(response, "joined #General")
        join_voice.assert_awaited_once_with(channel)

    async def test_external_leave_uses_requested_channel_guild(self):
        class FakeVoiceChannel:
            pass

        guild = SimpleNamespace()
        channel = FakeVoiceChannel()
        channel.guild = guild
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
            patch.object(bot, "leave_guild_voice", new=AsyncMock(return_value="left the voice channel")) as leave_voice,
        ):
            response = await bot.control_external_voice("leave", 1447148315312521256)

        self.assertEqual(response, "left the voice channel")
        leave_voice.assert_awaited_once_with(guild)

    async def test_external_voice_rejects_unavailable_channel(self):
        with patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: None)):
            with self.assertRaisesRegex(RuntimeError, "voice channel is unavailable"):
                await bot.control_external_voice("join", 1447148315312521256)


class VoiceLeaveTests(unittest.IsolatedAsyncioTestCase):
    async def test_leave_disconnects_voice_client(self):
        voice_client = SimpleNamespace(is_connected=lambda: True, disconnect=AsyncMock())
        message = SimpleNamespace(guild=SimpleNamespace(id=456, voice_client=voice_client))
        bot.last_command_bark_at[456] = 100.0

        with patch.object(bot, "stop_bark_task") as stop_bark_task:
            response = await bot.leave_voice(message)

        voice_client.disconnect.assert_awaited_once_with()
        stop_bark_task.assert_called_once_with(456)
        self.assertNotIn(456, bot.last_command_bark_at)
        self.assertEqual(response, "left the voice channel")

    async def test_leave_reports_when_not_connected(self):
        message = SimpleNamespace(guild=SimpleNamespace(voice_client=None))

        response = await bot.leave_voice(message)

        self.assertEqual(response, "i'm not in a voice channel")

    async def test_leave_command_is_handled_without_calling_chat_model(self):
        channel_id = next(iter(bot.TARGET_CHANNEL_IDS))
        voice_client = SimpleNamespace(is_connected=lambda: True, disconnect=AsyncMock())
        text_channel = SimpleNamespace(id=channel_id, send=AsyncMock())
        message = SimpleNamespace(
            author=SimpleNamespace(id=123, display_name="Tester"),
            channel=text_channel,
            content="!leave",
            guild=SimpleNamespace(id=456, voice_client=voice_client),
        )

        with (
            patch.object(bot, "call_model", new_callable=AsyncMock) as call_model,
            patch.object(bot, "stop_bark_task") as stop_bark_task,
        ):
            await bot.on_message(message)

        voice_client.disconnect.assert_awaited_once_with()
        stop_bark_task.assert_called_once_with(456)
        text_channel.send.assert_awaited_once_with("left the voice channel")
        call_model.assert_not_awaited()


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

    def test_page_has_voice_controls_with_default_channel(self):
        response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Voice call", response.data)
        self.assertIn(b'name="action" value="join"', response.data)
        self.assertIn(b'name="action" value="leave"', response.data)
        self.assertIn(
            b'value="1447148315312521256"',
            response.data,
        )

    def test_voice_channel_default_can_be_overridden(self):
        with patch.dict(bot.os.environ, {"EXTERNAL_VOICE_CHANNEL_ID": "123456789"}):
            response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'value="123456789"', response.data)

    def test_page_lists_ping_members_with_copyable_mentions(self):
        response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Ping a member", response.data)
        self.assertIn(b"Ozzy", response.data)
        self.assertIn(b"586732970283630633", response.data)
        self.assertIn(b'data-mention="&lt;@586732970283630633&gt;"', response.data)
        self.assertIn(b"Reqo", response.data)
        self.assertIn(b"375402301646700546", response.data)
        self.assertNotIn(b">Red<", response.data)
        self.assertIn(b"Hayden", response.data)
        self.assertIn(b"1069346669566623928", response.data)
        self.assertIn(b">6uke<", response.data)
        self.assertIn(b"1135595806171332760", response.data)
        self.assertIn(b"Tom Pearls", response.data)
        self.assertIn(b"607667203126591509", response.data)
        jaedon_members = [
            member
            for member in bot.external_ping_members()
            if member["user_id"] == "1149829095958528020"
        ]
        self.assertEqual(len(jaedon_members), 1)
        self.assertLess(
            response.data.index(b"Send to Discord"),
            response.data.index(b"Ping a member"),
        )

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

    def test_join_voice_form_uses_selected_channel(self):
        with patch.object(
            bot,
            "submit_external_voice_action",
            return_value="joined General",
        ) as submit_voice:
            response = self.client.post(
                "/say",
                data={
                    "action": "join",
                    "voice_channel_id": "1447148315312521256",
                },
            )

        self.assertEqual(response.status_code, 303)
        self.assertIn("status=joined+General", response.headers["Location"])
        submit_voice.assert_called_once_with("join", 1447148315312521256)

    def test_leave_voice_form_uses_selected_channel(self):
        with patch.object(
            bot,
            "submit_external_voice_action",
            return_value="left the voice channel",
        ) as submit_voice:
            response = self.client.post(
                "/say",
                data={
                    "action": "leave",
                    "voice_channel_id": "1447148315312521256",
                },
            )

        self.assertEqual(response.status_code, 303)
        submit_voice.assert_called_once_with("leave", 1447148315312521256)

    def test_voice_form_rejects_non_numeric_channel_id(self):
        response = self.client.post(
            "/say",
            data={"action": "join", "voice_channel_id": "not-a-channel"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Enter a valid numeric voice channel ID", response.data)

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
