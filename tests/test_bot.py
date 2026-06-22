
import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from unittest.mock import ANY, AsyncMock, Mock, PropertyMock, call, patch

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


class SystemPromptTests(unittest.TestCase):
    def test_pkla_slang_definition_is_in_system_prompt(self):
        self.assertIn('"pkla" is versatile slang', bot.SYSTEM_PROMPT)
        self.assertIn('high-quality, cool, great, fire, clean', bot.SYSTEM_PROMPT)
        self.assertIn('effortless confidence and undeniable swag', bot.SYSTEM_PROMPT)


class VoiceReceiveDependencyTests(unittest.TestCase):
    def test_voice_receive_dependency_includes_dave_fix(self):
        requirements = Path("requirements.txt").read_text()

        self.assertIn("discord-ext-voice-recv", requirements)
        self.assertIn("vocolboy/discord-ext-voice-recv", requirements)
        self.assertIn("/ee160c0f36516927b6214bc9d6babe524016770f.zip", requirements)
        self.assertNotIn("/ddd28601fe556f585b869e215f29c8236b95f88f.zip", requirements)
        self.assertNotIn("discord-ext-voice-recv==0.5.2a179", requirements)


class DiscordIntentTests(unittest.TestCase):
    def test_member_and_message_content_intents_are_enabled(self):
        self.assertTrue(bot.intents.members)
        self.assertTrue(bot.intents.message_content)


class BirthdayRyanCommandTests(unittest.IsolatedAsyncioTestCase):
    def test_command_is_registered(self):
        command = bot.command_tree.get_command("birthdayryan")

        self.assertIsNotNone(command)
        self.assertEqual(command.description, "Send Ryan's birthday embed.")
        self.assertEqual(command.parameters, [])

    async def test_sends_public_embed_with_local_image_attachment(self):
        interaction = SimpleNamespace(
            response=SimpleNamespace(send_message=AsyncMock())
        )

        await bot.handle_birthdayryan(interaction)

        interaction.response.send_message.assert_awaited_once()
        args = interaction.response.send_message.await_args.args
        kwargs = interaction.response.send_message.await_args.kwargs
        self.assertEqual(
            args, ("Yo Ryan, PKLA Dog pulled up for your birthday 🎂",)
        )
        self.assertNotIn("ephemeral", kwargs)

        embed = kwargs["embed"]
        self.assertEqual(embed.title, "🎉 HAPPY BIRTHDAY RYAN 🎉")
        self.assertIn("Roblox", embed.description)
        self.assertIn("Valorant", embed.description)
        self.assertIn("Playboi Carti", embed.description)
        self.assertIn("Surron", embed.description)
        self.assertEqual(embed.image.url, "attachment://ryan-birthday.png")
        self.assertEqual(embed.footer.text, "PKLA Dog birthday delivery 🐶")

        birthday_image = kwargs["file"]
        try:
            self.assertEqual(birthday_image.filename, "ryan-birthday.png")
            self.assertEqual(birthday_image.fp.read(8), b"\x89PNG\r\n\x1a\n")
        finally:
            birthday_image.close()

    def test_birthday_image_is_stored_as_text_base64(self):
        encoded_image = bot.RYAN_BIRTHDAY_IMAGE_BASE64_PATH.read_text()

        self.assertTrue(encoded_image.isascii())
        self.assertFalse(Path("assets/ryan-birthday.png").exists())
        self.assertTrue(
            bot.base64.b64decode(encoded_image, validate=False).startswith(
                b"\x89PNG\r\n\x1a\n"
            )
        )

    async def test_external_birthday_send_uses_requested_channel_payload(self):
        channel = SimpleNamespace(send=AsyncMock())

        with patch.object(bot.client, "get_channel", return_value=channel) as get_channel:
            await bot.send_external_ryan_birthday(bot.RYAN_BIRTHDAY_CHANNEL_ID)

        get_channel.assert_called_once_with(1491165529837277355)
        channel.send.assert_awaited_once()
        args = channel.send.await_args.args
        kwargs = channel.send.await_args.kwargs
        self.assertEqual(
            args, ("Yo Ryan, PKLA Dog pulled up for your birthday 🎂",)
        )
        self.assertEqual(kwargs["embed"].image.url, "attachment://ryan-birthday.png")
        try:
            self.assertEqual(kwargs["file"].filename, "ryan-birthday.png")
        finally:
            kwargs["file"].close()


class DiscordStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_rate_limited_login_retries_with_bounded_backoff(self):
        rate_limit_error = bot.discord.HTTPException(
            Mock(status=429, reason="Too Many Requests"),
            "temporarily rate limited",
        )

        with (
            patch.object(
                bot.client,
                "start",
                new=AsyncMock(side_effect=[rate_limit_error, rate_limit_error, None]),
            ) as start,
            patch.object(bot.client, "is_closed", return_value=False),
            patch.object(bot.client, "close", new=AsyncMock()) as close,
            patch.object(bot.asyncio, "sleep", new=AsyncMock()) as sleep,
        ):
            await bot.run_discord_client("test-token")

        self.assertEqual(
            start.await_args_list,
            [call("test-token"), call("test-token"), call("test-token")],
        )
        self.assertEqual(
            sleep.await_args_list,
            [
                call(bot.DISCORD_LOGIN_RETRY_INITIAL_SECONDS),
                call(bot.DISCORD_LOGIN_RETRY_INITIAL_SECONDS * 2),
            ],
        )
        close.assert_awaited_once_with()

    async def test_non_rate_limit_login_failure_is_not_retried(self):
        login_error = bot.discord.HTTPException(
            Mock(status=401, reason="Unauthorized"),
            "invalid token",
        )

        with (
            patch.object(
                bot.client, "start", new=AsyncMock(side_effect=login_error)
            ) as start,
            patch.object(bot.client, "is_closed", return_value=False),
            patch.object(bot.client, "close", new=AsyncMock()) as close,
            patch.object(bot.asyncio, "sleep", new=AsyncMock()) as sleep,
        ):
            with self.assertRaises(bot.discord.HTTPException):
                await bot.run_discord_client("test-token")

        start.assert_awaited_once_with("test-token")
        sleep.assert_not_awaited()
        close.assert_awaited_once_with()

    async def test_login_retry_delay_stops_growing_at_cap(self):
        rate_limit_error = bot.discord.HTTPException(
            Mock(status=429, reason="Too Many Requests"),
            "temporarily rate limited",
        )
        attempts = [rate_limit_error] * 6 + [None]

        with (
            patch.object(bot.client, "start", new=AsyncMock(side_effect=attempts)),
            patch.object(bot.client, "is_closed", return_value=True),
            patch.object(bot.client, "close", new=AsyncMock()) as close,
            patch.object(bot.asyncio, "sleep", new=AsyncMock()) as sleep,
        ):
            await bot.run_discord_client("test-token")

        self.assertEqual(
            [args.args[0] for args in sleep.await_args_list],
            [60, 120, 240, 480, 900, 900],
        )
        close.assert_not_awaited()


class PingDeafCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bot.last_pingdeaf_at.clear()
        bot.pingdeaf_tasks.clear()
        bot.pingdeaf_senders.clear()
        bot.pingdeaf_sender_views.clear()
        bot.pingdeaf_messages.clear()
        bot.pingdeaf_cleanup_tasks.clear()

    async def asyncTearDown(self):
        tasks = list(bot.pingdeaf_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        cleanup_tasks = list(bot.pingdeaf_cleanup_tasks)
        for task in cleanup_tasks:
            task.cancel()
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)

        bot.pingdeaf_tasks.clear()
        bot.pingdeaf_senders.clear()
        bot.pingdeaf_sender_views.clear()
        bot.pingdeaf_messages.clear()
        bot.pingdeaf_cleanup_tasks.clear()

    @staticmethod
    def interaction():
        notification = SimpleNamespace(id=789, delete=AsyncMock())
        return SimpleNamespace(
            user=SimpleNamespace(
                id=999,
                mention="<@999>",
                send=AsyncMock(return_value=notification),
                sent_notification=notification,
            ),
            response=SimpleNamespace(
                send_message=AsyncMock(), edit_message=AsyncMock()
            ),
            edit_original_response=AsyncMock(),
        )

    @staticmethod
    def button_interaction(user_id):
        return SimpleNamespace(
            user=SimpleNamespace(id=user_id),
            response=SimpleNamespace(
                send_message=AsyncMock(), edit_message=AsyncMock()
            ),
        )

    @staticmethod
    def member(*, channel=None, self_deaf=False, deaf=False):
        voice = None
        if channel is not None:
            voice = SimpleNamespace(channel=channel, self_deaf=self_deaf, deaf=deaf)
        message = SimpleNamespace(id=456, delete=AsyncMock())
        return SimpleNamespace(
            id=123,
            mention="<@123>",
            voice=voice,
            send=AsyncMock(return_value=message),
            sent_message=message,
        )

    def test_pingdeaf_is_registered_with_required_member_option(self):
        command = bot.command_tree.get_command("pingdeaf")

        self.assertIsNotNone(command)
        self.assertEqual(command.description, "DM a deafened voice member to undeafen.")
        self.assertEqual(len(command.parameters), 1)
        self.assertEqual(command.parameters[0].name, "user")
        self.assertTrue(command.parameters[0].required)

    async def test_sync_keeps_global_command_and_clears_guild_commands(self):
        guilds = [SimpleNamespace(id=1), SimpleNamespace(id=2)]

        with (
            patch.object(
                type(bot.client),
                "guilds",
                new_callable=PropertyMock,
                return_value=guilds,
            ),
            patch.object(bot.command_tree, "sync", new=AsyncMock()) as sync,
            patch.object(bot.command_tree, "clear_commands") as clear_commands,
        ):
            synced = await bot.sync_slash_commands()

        self.assertTrue(synced)
        self.assertEqual(
            sync.await_args_list,
            [call(), call(guild=guilds[0]), call(guild=guilds[1])],
        )
        self.assertEqual(
            clear_commands.call_args_list,
            [call(guild=guilds[0]), call(guild=guilds[1])],
        )

    async def test_sync_failure_is_reported_for_retry(self):
        with patch.object(
            bot.command_tree,
            "sync",
            new=AsyncMock(
                side_effect=bot.discord.HTTPException(
                    Mock(status=500, reason="Server Error"), "sync failed"
                )
            ),
        ):
            synced = await bot.sync_slash_commands()

        self.assertFalse(synced)

    async def test_rejects_member_not_in_voice(self):
        interaction = self.interaction()
        member = self.member()

        await bot.handle_pingdeaf(interaction, member)

        member.send.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once_with(
            "That user is not in a voice channel.", ephemeral=True
        )

    async def test_rejects_member_who_is_not_deafened(self):
        interaction = self.interaction()
        member = self.member(channel=SimpleNamespace(name="General"))

        await bot.handle_pingdeaf(interaction, member)

        member.send.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once_with(
            "That user is not deafened.", ephemeral=True
        )

    async def test_dms_self_deafened_member_and_starts_cooldown(self):
        interaction = self.interaction()
        member = self.member(
            channel=SimpleNamespace(name="General"), self_deaf=True
        )

        with patch.object(bot.time, "monotonic", return_value=100.0):
            await bot.handle_pingdeaf(interaction, member)

        member.send.assert_awaited_once_with(
            "🔇 People are trying to talk to you in **General**. "
            "Undeafen RIGHT NOW 😠. I won't stop DMing you until you undeafen.",
            view=ANY,
        )
        interaction.response.send_message.assert_awaited_once_with(
            "DMing <@123> every 2 seconds until they undeafen.\n"
            "Messages sent: **1**",
            ephemeral=True,
            view=ANY,
        )
        self.assertIsInstance(
            member.send.await_args.kwargs["view"], bot.PingDeafReceiverView
        )
        self.assertIsInstance(
            interaction.response.send_message.await_args.kwargs["view"],
            bot.PingDeafSenderView,
        )
        self.assertEqual(bot.last_pingdeaf_at[123], 100.0)
        self.assertIn(member.id, bot.pingdeaf_tasks)
        self.assertEqual(bot.pingdeaf_messages[member.id], [member.sent_message])

    async def test_repeats_every_two_seconds_until_member_undeafens(self):
        member = self.member(
            channel=SimpleNamespace(name="General"), self_deaf=True
        )
        sleep_count = 0

        async def sleep_then_update_voice_state(seconds):
            nonlocal sleep_count
            self.assertEqual(seconds, 2)
            sleep_count += 1
            if sleep_count == 2:
                member.voice.self_deaf = False

        interaction = self.interaction()
        messages = [SimpleNamespace(id=1, delete=AsyncMock())]
        sender_view = bot.PingDeafSenderView(
            member, interaction.user.id, messages
        )
        with patch.object(
            bot.asyncio, "sleep", new=AsyncMock(side_effect=sleep_then_update_voice_state)
        ):
            await bot.pingdeaf_until_undeafened(
                member, messages, interaction, sender_view
            )

        member.send.assert_awaited_once_with(
            "🔇 People are trying to talk to you in **General**. "
            "Undeafen RIGHT NOW 😠. I won't stop DMing you until you undeafen.",
            view=ANY,
        )
        interaction.edit_original_response.assert_awaited_once_with(
            content="DMing <@123> every 2 seconds until they undeafen.\n"
            "Messages sent: **2**",
            view=sender_view,
        )

    async def test_deletes_reminder_messages_two_minutes_after_stopping(self):
        messages = [
            SimpleNamespace(id=1, delete=AsyncMock()),
            SimpleNamespace(id=2, delete=AsyncMock()),
        ]

        with patch.object(bot.asyncio, "sleep", new=AsyncMock()) as sleep:
            await bot.delete_pingdeaf_messages(messages)

        sleep.assert_awaited_once_with(2 * 60)
        for message in messages:
            message.delete.assert_awaited_once_with()

    async def test_cleanup_continues_if_one_reminder_was_already_deleted(self):
        failed_message = SimpleNamespace(id=1, delete=AsyncMock())
        failed_message.delete.side_effect = bot.discord.NotFound(
            Mock(status=404, reason="Not Found"),
            {"message": "Unknown Message", "code": 10008},
        )
        remaining_message = SimpleNamespace(id=2, delete=AsyncMock())

        with patch.object(bot.asyncio, "sleep", new=AsyncMock()):
            await bot.delete_pingdeaf_messages(
                [failed_message, remaining_message]
            )

        failed_message.delete.assert_awaited_once_with()
        remaining_message.delete.assert_awaited_once_with()

    async def test_sender_stop_button_stops_reminders(self):
        interaction = self.interaction()
        member = self.member(
            channel=SimpleNamespace(name="General"), self_deaf=True
        )
        await bot.handle_pingdeaf(interaction, member)
        sender_view = interaction.response.send_message.await_args.kwargs["view"]
        button_interaction = self.button_interaction(interaction.user.id)

        await sender_view.children[0].callback(button_interaction)

        self.assertNotIn(member.id, bot.pingdeaf_tasks)
        self.assertNotIn(member.id, bot.pingdeaf_senders)
        button_interaction.response.edit_message.assert_awaited_once_with(
            content="Stopped DMing <@123>.\nMessages sent: **1**", view=None
        )

    async def test_receiver_stop_button_stops_and_notifies_sender(self):
        interaction = self.interaction()
        member = self.member(
            channel=SimpleNamespace(name="General"), self_deaf=True
        )
        await bot.handle_pingdeaf(interaction, member)
        receiver_view = member.send.await_args.kwargs["view"]
        tracked_messages = bot.pingdeaf_messages[member.id]
        button_interaction = self.button_interaction(member.id)

        await receiver_view.children[0].callback(button_interaction)

        self.assertNotIn(member.id, bot.pingdeaf_tasks)
        button_interaction.response.edit_message.assert_awaited_once_with(
            content="You stopped the undeafen DM reminders.", view=None
        )
        interaction.user.send.assert_awaited_once_with(
            "<@123> used **Stop the spam**, so the undeafen DMs stopped. "
            "Messages sent: **1**"
        )
        self.assertIn(interaction.user.sent_notification, tracked_messages)

    async def test_receiver_stop_button_rejects_other_users(self):
        member = self.member(
            channel=SimpleNamespace(name="General"), self_deaf=True
        )
        receiver_view = bot.PingDeafReceiverView(member)
        button_interaction = self.button_interaction(456)

        await receiver_view.children[0].callback(button_interaction)

        button_interaction.response.send_message.assert_awaited_once_with(
            "Only the person receiving these DMs can use this button.",
            ephemeral=True,
        )

    async def test_does_not_start_a_duplicate_reminder_loop(self):
        interaction = self.interaction()
        member = self.member(
            channel=SimpleNamespace(name="General"), self_deaf=True
        )
        active_task = asyncio.create_task(asyncio.sleep(60))
        bot.pingdeaf_tasks[member.id] = active_task

        await bot.handle_pingdeaf(interaction, member)

        member.send.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once_with(
            "<@123> is already being DM'd every 2 seconds.", ephemeral=True
        )

    async def test_dms_server_deafened_member(self):
        interaction = self.interaction()
        member = self.member(channel=SimpleNamespace(name="General"), deaf=True)

        await bot.handle_pingdeaf(interaction, member)

        member.send.assert_awaited_once()

    async def test_enforces_per_target_cooldown(self):
        interaction = self.interaction()
        member = self.member(
            channel=SimpleNamespace(name="General"), self_deaf=True
        )
        bot.last_pingdeaf_at[member.id] = 100.0

        with patch.object(bot.time, "monotonic", return_value=120.0):
            await bot.handle_pingdeaf(interaction, member)

        member.send.assert_not_awaited()
        interaction.response.send_message.assert_awaited_once_with(
            "<@123> was already pinged recently. Try again in 40s.", ephemeral=True
        )

    async def test_allows_ping_after_cooldown_expires(self):
        interaction = self.interaction()
        member = self.member(
            channel=SimpleNamespace(name="General"), self_deaf=True
        )
        bot.last_pingdeaf_at[member.id] = 100.0

        with patch.object(bot.time, "monotonic", return_value=160.0):
            await bot.handle_pingdeaf(interaction, member)

        member.send.assert_awaited_once()
        self.assertEqual(bot.last_pingdeaf_at[member.id], 160.0)

    async def test_closed_dms_report_error_without_starting_cooldown(self):
        interaction = self.interaction()
        member = self.member(
            channel=SimpleNamespace(name="General"), self_deaf=True
        )
        member.send.side_effect = bot.discord.Forbidden(
            Mock(status=403, reason="Forbidden"),
            {"message": "Cannot send", "code": 50007},
        )

        with patch.object(bot.time, "monotonic", return_value=100.0):
            await bot.handle_pingdeaf(interaction, member)

        interaction.response.send_message.assert_awaited_once_with(
            "I could not DM that user. Their DMs may be closed.", ephemeral=True
        )
        self.assertNotIn(member.id, bot.last_pingdeaf_at)


class DeleteDmMessagesTests(unittest.IsolatedAsyncioTestCase):
    class FakeDMChannel:
        def __init__(self, channel_id, messages):
            self.id = channel_id
            self._messages = messages

        def history(self, *, limit):
            if limit is not None:
                raise AssertionError("DM cleanup must request the complete history")

            async def iterate_messages():
                for message in self._messages:
                    yield message

            return iterate_messages()

    async def test_deletes_bot_messages_from_all_dm_channels(self):
        first_bot_message = SimpleNamespace(
            id=1, author=SimpleNamespace(id=999), delete=AsyncMock()
        )
        user_message = SimpleNamespace(
            id=2, author=SimpleNamespace(id=123), delete=AsyncMock()
        )
        second_bot_message = SimpleNamespace(
            id=3, author=SimpleNamespace(id=999), delete=AsyncMock()
        )
        channels = [
            self.FakeDMChannel(10, [first_bot_message, user_message]),
            self.FakeDMChannel(20, [second_bot_message]),
        ]

        result = await bot.delete_bot_dm_messages(channels, 999)

        self.assertEqual(result, (2, 0, 0))
        first_bot_message.delete.assert_awaited_once_with()
        second_bot_message.delete.assert_awaited_once_with()
        user_message.delete.assert_not_awaited()

    async def test_continues_after_message_and_channel_failures(self):
        failed_message = SimpleNamespace(
            id=1, author=SimpleNamespace(id=999), delete=AsyncMock()
        )
        failed_message.delete.side_effect = bot.discord.Forbidden(
            Mock(status=403, reason="Forbidden"),
            {"message": "Cannot delete", "code": 50013},
        )
        remaining_message = SimpleNamespace(
            id=2, author=SimpleNamespace(id=999), delete=AsyncMock()
        )
        failed_channel = self.FakeDMChannel(20, [])
        failed_channel.history = Mock(
            side_effect=bot.discord.Forbidden(
                Mock(status=403, reason="Forbidden"),
                {"message": "Cannot read", "code": 50013},
            )
        )
        channels = [
            self.FakeDMChannel(10, [failed_message]),
            failed_channel,
            self.FakeDMChannel(30, [remaining_message]),
        ]

        result = await bot.delete_bot_dm_messages(channels, 999)

        self.assertEqual(result, (1, 1, 1))
        remaining_message.delete.assert_awaited_once_with()

    def test_cleanup_channels_include_all_cached_dms_and_invoking_dm_once(self):
        invoking_channel = self.FakeDMChannel(10, [])
        another_channel = self.FakeDMChannel(20, [])

        with (
            patch.object(bot.discord, "DMChannel", self.FakeDMChannel),
            patch.object(
                type(bot.client),
                "private_channels",
                new_callable=PropertyMock,
                return_value=[invoking_channel, another_channel, SimpleNamespace(id=30)],
            ),
        ):
            channels = bot.dm_channels_for_cleanup(invoking_channel)

        self.assertEqual(channels, [invoking_channel, another_channel])

    async def test_authorized_user_cleans_all_available_dms(self):
        channel = self.FakeDMChannel(10, [])
        other_channel = self.FakeDMChannel(20, [])
        message = SimpleNamespace(
            author=SimpleNamespace(
                id=bot.DEFAULT_OWNER_ID,
                display_name="Owner",
            ),
            channel=channel,
            content="!deletedms",
            add_reaction=AsyncMock(),
        )

        with (
            patch.object(bot.discord, "DMChannel", self.FakeDMChannel),
            patch.object(bot.client._connection, "user", SimpleNamespace(id=999)),
            patch.object(
                bot,
                "dm_channels_for_cleanup",
                return_value=[channel, other_channel],
            ),
            patch.object(
                bot,
                "delete_bot_dm_messages",
                new=AsyncMock(return_value=(25, 0, 0)),
            ) as delete_messages,
            patch.object(bot, "call_model", new_callable=AsyncMock) as call_model,
        ):
            await bot.on_message(message)

        delete_messages.assert_awaited_once_with([channel, other_channel], 999)
        message.add_reaction.assert_awaited_once_with("✅")
        call_model.assert_not_awaited()

    async def test_delete_command_is_ignored_for_every_other_user(self):
        channel = self.FakeDMChannel(10, [])
        message = SimpleNamespace(
            author=SimpleNamespace(id=123, display_name="Other"),
            channel=channel,
            content="!deletedms",
            add_reaction=AsyncMock(),
        )

        with (
            patch.object(bot.discord, "DMChannel", self.FakeDMChannel),
            patch.object(
                bot, "delete_bot_dm_messages", new_callable=AsyncMock
            ) as delete_messages,
            patch.object(bot, "call_model", new_callable=AsyncMock) as call_model,
        ):
            await bot.on_message(message)

        delete_messages.assert_not_awaited()
        message.add_reaction.assert_not_awaited()
        call_model.assert_not_awaited()


class BarkAudioTests(unittest.IsolatedAsyncioTestCase):
    def test_bark_audio_file_exists(self):
        self.assertTrue(bot.BARK_AUDIO_PATH.is_file())
        self.assertEqual(bot.BARK_AUDIO_PATH.name, "pkla-dog-bark.mp3")

    def test_external_bark_audio_files_exist(self):
        self.assertEqual(
            {sound["path"].name for sound in bot.EXTERNAL_BARK_SOUNDS.values()},
            {
                "wolf-bark.mp3",
                "minecraft-bark.mp3",
                "bark-fart.mp3",
            },
        )
        self.assertTrue(
            all(sound["path"].is_file() for sound in bot.EXTERNAL_BARK_SOUNDS.values())
        )

    def test_play_bark_starts_mp3_audio(self):
        voice_client = SimpleNamespace(is_playing=lambda: False, play=Mock())
        audio_source = Mock()

        with patch.object(bot.discord, "FFmpegPCMAudio", return_value=audio_source) as ffmpeg_audio:
            played = bot.play_bark(voice_client)

        self.assertTrue(played)
        ffmpeg_audio.assert_called_once_with(str(bot.BARK_AUDIO_PATH), options="-vn")
        voice_client.play.assert_called_once()
        self.assertIs(voice_client.play.call_args.args[0], audio_source)
        self.assertIn("after", voice_client.play.call_args.kwargs)

    def test_play_bark_does_not_interrupt_existing_audio(self):
        voice_client = SimpleNamespace(is_playing=lambda: True, play=Mock())

        played = bot.play_bark(voice_client)

        self.assertFalse(played)
        voice_client.play.assert_not_called()

    def test_temporary_audio_is_deleted_after_playback(self):
        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "speech.mp3"
            audio_path.write_bytes(b"mp3")
            voice_client = SimpleNamespace(is_playing=lambda: False, play=Mock())

            with patch.object(bot.discord, "FFmpegPCMAudio", return_value=Mock()):
                played = bot.play_audio(
                    voice_client,
                    audio_path,
                    activity_type="tts",
                    label="test speech",
                    delete_after=True,
                )
                after_playback = voice_client.play.call_args.kwargs["after"]
                after_playback(None)

            self.assertTrue(played)
            self.assertFalse(audio_path.exists())


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
        bot.channel_conversation_history.pop(channel_id, None)
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
        self.assertEqual(
            bot.get_active_history(channel_id, 123, is_dm=False),
            [
                {"role": "user", "content": "Tester: !bark"},
                {"role": "assistant", "content": "woof"},
            ],
        )


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

    async def test_join_falls_back_when_receive_enabled_connect_fails(self):
        voice_client = SimpleNamespace()
        voice_channel = SimpleNamespace(
            mention="#General",
            connect=AsyncMock(
                side_effect=[
                    bot.discord.DiscordException("receive failed"),
                    voice_client,
                ]
            ),
        )
        message = SimpleNamespace(
            guild=SimpleNamespace(voice_client=None),
            author=SimpleNamespace(voice=SimpleNamespace(channel=voice_channel)),
        )

        with (
            patch.object(bot, "EXTERNAL_SAY_CONTROL_TOKEN", "secret"),
            patch.object(bot, "env_bool", return_value=True),
            patch.object(bot, "voice_receive_client_class", return_value=object),
            patch.object(bot, "start_bark_task") as start_bark_task,
            patch.object(bot.asyncio, "sleep", new=AsyncMock()) as sleep,
            patch.object(bot, "play_bark", return_value=True) as play_bark,
        ):
            response = await bot.join_author_voice(message)

        self.assertEqual(voice_channel.connect.await_count, 2)
        voice_channel.connect.assert_has_awaits(
            [
                call(self_deaf=False, self_mute=False, cls=object),
                call(self_deaf=False, self_mute=False),
            ]
        )
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


class VoiceTextToSpeechCommandTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bot.last_tts_at.clear()
        bot.chat_tts_queues.clear()
        bot.chat_tts_tasks.clear()
        bot.chat_tts_command_enabled = True

    async def test_tts_command_queues_following_message(self):
        channel_id = next(iter(bot.TARGET_CHANNEL_IDS))
        voice_client = SimpleNamespace(is_connected=lambda: True)
        text_channel = SimpleNamespace(id=channel_id, send=AsyncMock())
        guild = SimpleNamespace(id=456, voice_client=voice_client)
        bot.last_tts_at[guild.id] = 100.0
        message = SimpleNamespace(
            author=SimpleNamespace(id=123, display_name="Tester"),
            channel=text_channel,
            content="!tts Hello from Discord",
            guild=guild,
        )

        with (
            patch.object(bot, "call_model", new_callable=AsyncMock) as call_model,
            patch.object(bot, "enqueue_chat_tts") as enqueue_chat_tts,
        ):
            await bot.on_message(message)

        enqueue_chat_tts.assert_called_once_with(guild, "Hello from Discord")
        text_channel.send.assert_not_awaited()
        call_model.assert_not_awaited()
        self.assertEqual(bot.last_tts_at[guild.id], 100.0)

    async def test_chat_tts_queue_processes_messages_without_overlap(self):
        voice_client = SimpleNamespace(is_connected=lambda: True)
        guild = SimpleNamespace(id=456, voice_client=voice_client)
        first_started = asyncio.Event()
        allow_first_to_finish = asyncio.Event()
        playback_order = []

        async def play_speech(_guild, text):
            playback_order.append(f"start:{text}")
            if text == "first":
                first_started.set()
                await allow_first_to_finish.wait()
            playback_order.append(f"finish:{text}")

        with patch.object(bot, "play_chat_tts", side_effect=play_speech):
            bot.enqueue_chat_tts(guild, "first")
            queue = bot.chat_tts_queues[guild.id]
            await first_started.wait()
            bot.enqueue_chat_tts(guild, "second")
            await asyncio.sleep(0)

            self.assertEqual(playback_order, ["start:first"])

            allow_first_to_finish.set()
            await queue.join()

        self.assertEqual(
            playback_order,
            ["start:first", "finish:first", "start:second", "finish:second"],
        )

    async def test_chat_tts_waits_for_discord_playback_to_finish(self):
        callbacks = []
        voice_client = SimpleNamespace(
            is_connected=lambda: True,
            is_playing=lambda: False,
        )
        guild = SimpleNamespace(id=456, voice_client=voice_client)
        speech_path = Path("generated-speech.mp3")

        def start_playback(*args, **kwargs):
            callbacks.append(kwargs["after"])
            return True

        with (
            patch.object(
                bot.asyncio, "to_thread", new=AsyncMock(return_value=speech_path)
            ) as to_thread,
            patch.object(bot, "play_audio", side_effect=start_playback),
        ):
            playback = asyncio.create_task(bot.play_chat_tts(guild, "hello"))
            await asyncio.sleep(0)
            self.assertFalse(playback.done())
            to_thread.assert_awaited_once_with(
                bot.synthesize_speech, "hello", "onyx"
            )

            callbacks[0](None)
            await playback

    async def test_disabled_tts_command_does_not_queue_speech(self):
        channel_id = next(iter(bot.TARGET_CHANNEL_IDS))
        text_channel = SimpleNamespace(id=channel_id, send=AsyncMock())
        guild = SimpleNamespace(id=456, voice_client=SimpleNamespace(is_connected=lambda: True))
        message = SimpleNamespace(
            author=SimpleNamespace(id=123, display_name="Tester"),
            channel=text_channel,
            content="!tts This should not play",
            guild=guild,
        )
        bot.chat_tts_command_enabled = False

        with patch.object(bot, "enqueue_chat_tts") as enqueue_chat_tts:
            await bot.on_message(message)

        enqueue_chat_tts.assert_not_called()
        text_channel.send.assert_awaited_once_with(
            "!tts is currently disabled from the /say control page"
        )

    async def test_tts_command_requires_message_text(self):
        channel_id = next(iter(bot.TARGET_CHANNEL_IDS))
        text_channel = SimpleNamespace(id=channel_id, send=AsyncMock())
        message = SimpleNamespace(
            author=SimpleNamespace(id=123, display_name="Tester"),
            channel=text_channel,
            content="!tts",
            guild=SimpleNamespace(id=456, voice_client=None),
        )

        with patch.object(bot, "enqueue_chat_tts") as enqueue_chat_tts:
            await bot.on_message(message)

        enqueue_chat_tts.assert_not_called()
        text_channel.send.assert_awaited_once_with("add a message after !tts")

    async def test_tts_command_reports_when_bot_is_not_connected(self):
        message = SimpleNamespace(
            guild=SimpleNamespace(id=456, voice_client=None),
        )

        response = await bot.speak_message(message, "hello")

        self.assertEqual(response, "Join me to a voice channel first with !join")

    async def test_tts_command_rejects_overlong_text(self):
        message = SimpleNamespace(guild=SimpleNamespace(id=456, voice_client=None))

        response = await bot.speak_message(message, "x" * (bot.TTS_TEXT_LIMIT + 1))

        self.assertEqual(
            response, f"TTS messages cannot exceed {bot.TTS_TEXT_LIMIT} characters"
        )


class ExternalVoiceControlTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        bot.last_tts_at.clear()

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

    async def test_external_stop_stops_playing_audio_in_selected_channel(self):
        class FakeVoiceChannel:
            mention = "#General"

        channel = FakeVoiceChannel()
        voice_client = SimpleNamespace(
            channel=channel,
            is_connected=lambda: True,
            is_playing=lambda: True,
            stop=Mock(),
        )
        channel.guild = SimpleNamespace(voice_client=voice_client)
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
        ):
            response = await bot.control_external_voice("stop", 1447148315312521256)

        self.assertEqual(response, "stopped audio in #General")
        voice_client.stop.assert_called_once_with()

    async def test_external_stop_reports_when_nothing_is_playing(self):
        class FakeVoiceChannel:
            mention = "#General"

        channel = FakeVoiceChannel()
        voice_client = SimpleNamespace(
            channel=channel,
            is_connected=lambda: True,
            is_playing=lambda: False,
            stop=Mock(),
        )
        channel.guild = SimpleNamespace(voice_client=voice_client)
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
        ):
            response = await bot.control_external_voice("stop", 1447148315312521256)

        self.assertEqual(response, "nothing is playing")
        voice_client.stop.assert_not_called()

    async def test_external_stop_requires_connected_voice_client(self):
        class FakeVoiceChannel:
            mention = "#General"

        channel = FakeVoiceChannel()
        channel.guild = SimpleNamespace(voice_client=None)
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
        ):
            with self.assertRaisesRegex(RuntimeError, "Join the selected voice call"):
                await bot.control_external_voice("stop", 1447148315312521256)

    async def test_external_stop_requires_selected_voice_channel_connection(self):
        class FakeVoiceChannel:
            mention = "#General"

        channel = FakeVoiceChannel()
        voice_client = SimpleNamespace(
            channel=object(),
            is_connected=lambda: True,
            is_playing=lambda: True,
            stop=Mock(),
        )
        channel.guild = SimpleNamespace(voice_client=voice_client)
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
        ):
            with self.assertRaisesRegex(RuntimeError, "different voice channel"):
                await bot.control_external_voice("stop", 1447148315312521256)

        voice_client.stop.assert_not_called()

    async def test_external_server_mute_toggles_bot_member_voice_state(self):
        class FakeVoiceChannel:
            pass

        channel = FakeVoiceChannel()
        voice_client = SimpleNamespace(channel=channel, is_connected=lambda: True)
        bot_member = SimpleNamespace(
            voice=SimpleNamespace(mute=False),
            edit=AsyncMock(),
        )
        channel.guild = SimpleNamespace(voice_client=voice_client, me=bot_member)
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
        ):
            response = await bot.control_external_voice(
                "server_mute", 1447148315312521256
            )

        self.assertEqual(response, "server mute enabled")
        bot_member.edit.assert_awaited_once_with(mute=True)

    async def test_external_server_deafen_toggles_bot_member_voice_state(self):
        class FakeVoiceChannel:
            pass

        channel = FakeVoiceChannel()
        voice_client = SimpleNamespace(channel=channel, is_connected=lambda: True)
        bot_member = SimpleNamespace(
            voice=SimpleNamespace(deaf=True),
            edit=AsyncMock(),
        )
        channel.guild = SimpleNamespace(voice_client=voice_client, me=bot_member)
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
        ):
            response = await bot.control_external_voice(
                "server_deafen", 1447148315312521256
            )

        self.assertEqual(response, "server deafen disabled")
        bot_member.edit.assert_awaited_once_with(deafen=False)

    async def test_member_voice_moderation_edits_target_in_selected_channel(self):
        class FakeVoiceChannel:
            pass

        channel = FakeVoiceChannel()
        target = SimpleNamespace(
            id=42,
            display_name="Coolxng",
            voice=SimpleNamespace(channel=channel),
            edit=AsyncMock(),
        )
        guild = SimpleNamespace(
            me=SimpleNamespace(id=99),
            get_member=lambda user_id: target if user_id == 42 else None,
        )
        channel.guild = guild
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
        ):
            response = await bot.control_external_member_voice(
                "server_deafen_member", 1447148315312521256, 42
            )

        self.assertEqual(response, "server deafened Coolxng")
        target.edit.assert_awaited_once_with(
            deafen=True, reason="PKLA /say voice moderation"
        )

    async def test_member_voice_moderation_rejects_user_in_other_channel(self):
        class FakeVoiceChannel:
            pass

        channel = FakeVoiceChannel()
        target = SimpleNamespace(
            id=42,
            display_name="Coolxng",
            voice=SimpleNamespace(channel=object()),
        )
        channel.guild = SimpleNamespace(
            me=SimpleNamespace(id=99),
            get_member=lambda _user_id: target,
        )
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
        ):
            with self.assertRaisesRegex(ValueError, "not in the selected voice channel"):
                await bot.control_external_member_voice(
                    "server_mute_member", 1447148315312521256, 42
                )

    async def test_external_sound_plays_selected_audio(self):
        class FakeVoiceChannel:
            pass

        voice_client = SimpleNamespace(is_connected=lambda: True)
        channel = FakeVoiceChannel()
        channel.guild = SimpleNamespace(voice_client=voice_client)
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
            patch.object(bot, "play_audio", return_value=True) as play_audio,
        ):
            response = await bot.control_external_voice(
                "play_sound", 1447148315312521256, "minecraft"
            )

        self.assertEqual(response, "playing Minecraft bark")
        play_audio.assert_called_once_with(
            voice_client,
            bot.EXTERNAL_BARK_SOUNDS["minecraft"]["path"],
            activity_type="sound",
            label="Minecraft bark",
        )

    async def test_external_sound_requires_joined_voice_client(self):
        class FakeVoiceChannel:
            pass

        channel = FakeVoiceChannel()
        channel.guild = SimpleNamespace(voice_client=None)
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
        ):
            with self.assertRaisesRegex(RuntimeError, "Join the voice call"):
                await bot.control_external_voice(
                    "play_sound", 1447148315312521256, "wolf"
                )

    async def test_external_speech_requires_joined_voice_client(self):
        class FakeVoiceChannel:
            pass

        channel = FakeVoiceChannel()
        channel.guild = SimpleNamespace(id=456, voice_client=None)
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
        ):
            with self.assertRaisesRegex(RuntimeError, "Join the selected voice call"):
                await bot.control_external_speech(
                    1447148315312521256, "hello", "onyx"
                )

    async def test_external_speech_synthesizes_off_loop_and_plays_temporary_audio(self):
        class FakeVoiceChannel:
            pass

        speech_path = Path("generated-speech.mp3")
        voice_client = SimpleNamespace(
            is_connected=lambda: True, is_playing=lambda: False
        )
        channel = FakeVoiceChannel()
        channel.mention = "#General"
        channel.guild = SimpleNamespace(id=456, voice_client=voice_client)
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
            patch.object(
                bot.asyncio, "to_thread", new=AsyncMock(return_value=speech_path)
            ) as to_thread,
            patch.object(bot, "play_audio", return_value=True) as play_audio,
        ):
            response = await bot.control_external_speech(
                1447148315312521256, "hello", "onyx"
            )

        self.assertEqual(response, "speaking in #General")
        to_thread.assert_awaited_once_with(bot.synthesize_speech, "hello", "onyx")
        play_audio.assert_called_once_with(
            voice_client,
            speech_path,
            activity_type="tts",
            label='TTS: “hello”',
            delete_after=True,
        )
        self.assertNotIn(456, bot.last_tts_at)

    async def test_external_speech_failure_does_not_start_cooldown(self):
        class FakeVoiceChannel:
            pass

        voice_client = SimpleNamespace(
            is_connected=lambda: True, is_playing=lambda: False
        )
        channel = FakeVoiceChannel()
        channel.guild = SimpleNamespace(id=456, voice_client=voice_client)
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
            patch.object(
                bot.asyncio,
                "to_thread",
                new=AsyncMock(side_effect=RuntimeError("speech failed")),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "speech failed"):
                await bot.control_external_speech(
                    1447148315312521256, "hello", "onyx"
                )

        self.assertNotIn(456, bot.last_tts_at)

    async def test_external_speech_cancellation_does_not_start_cooldown(self):
        class FakeVoiceChannel:
            pass

        voice_client = SimpleNamespace(
            is_connected=lambda: True, is_playing=lambda: False
        )
        channel = FakeVoiceChannel()
        channel.guild = SimpleNamespace(id=456, voice_client=voice_client)
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
            patch.object(
                bot.asyncio,
                "to_thread",
                new=AsyncMock(side_effect=asyncio.CancelledError),
            ),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await bot.control_external_speech(
                    1447148315312521256, "hello", "onyx"
                )

        self.assertNotIn(456, bot.last_tts_at)

    async def test_external_speech_allows_repeat_requests_without_cooldown(self):
        class FakeVoiceChannel:
            pass

        voice_client = SimpleNamespace(
            is_connected=lambda: True, is_playing=lambda: False
        )
        channel = FakeVoiceChannel()
        channel.mention = "#General"
        channel.guild = SimpleNamespace(id=456, voice_client=voice_client)
        speech_path = Path("generated-speech.mp3")
        bot.last_tts_at[456] = 100.0
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
            patch.object(
                bot.asyncio, "to_thread", new=AsyncMock(return_value=speech_path)
            ) as to_thread,
            patch.object(bot, "play_audio", return_value=True),
        ):
            await bot.control_external_speech(
                1447148315312521256, "hello", "onyx"
            )

        to_thread.assert_awaited_once_with(bot.synthesize_speech, "hello", "onyx")
        self.assertEqual(bot.last_tts_at[456], 100.0)

    async def test_external_speech_rejects_busy_playback_before_synthesis(self):
        class FakeVoiceChannel:
            pass

        voice_client = SimpleNamespace(
            is_connected=lambda: True, is_playing=lambda: True
        )
        channel = FakeVoiceChannel()
        channel.guild = SimpleNamespace(id=456, voice_client=voice_client)
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
            patch.object(bot.asyncio, "to_thread", new=AsyncMock()) as to_thread,
        ):
            with self.assertRaisesRegex(RuntimeError, "already playing"):
                await bot.control_external_speech(
                    1447148315312521256, "hello", "onyx"
                )

        to_thread.assert_not_awaited()

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


class TextToSpeechTests(unittest.TestCase):
    def test_disabled_api_calls_block_tts_before_openai_request(self):
        with (
            patch.object(bot, "ai_api_calls_enabled", False),
            patch.object(bot, "urlopen") as urlopen,
        ):
            with self.assertRaisesRegex(RuntimeError, "API calls are disabled"):
                bot.synthesize_speech("hello", "onyx")

        urlopen.assert_not_called()

    def test_openai_request_contains_configured_speech_values(self):
        class FakeResponse:
            def __enter__(self):
                return io.BytesIO(b"mp3-data")

            def __exit__(self, *_args):
                return False

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(bot.tempfile, "tempdir", directory),
            patch.dict(bot.os.environ, {"OPENAI_API_KEY": "openai-secret"}),
            patch.object(bot, "OPENAI_TTS_API_URL", "https://openai.test/v1/audio/speech"),
            patch.object(bot, "OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
            patch.object(bot, "urlopen", return_value=FakeResponse()) as urlopen,
        ):
            speech_path = bot.synthesize_speech("hello", "onyx")

            request = urlopen.call_args.args[0]
            self.assertEqual(request.full_url, "https://openai.test/v1/audio/speech")
            self.assertEqual(request.headers["Authorization"], "Bearer openai-secret")
            self.assertEqual(request.headers["Accept"], "audio/mpeg")
            self.assertEqual(
                json.loads(request.data.decode("utf-8")),
                {"model": "gpt-4o-mini-tts", "voice": "onyx", "input": "hello", "response_format": "mp3"},
            )
            self.assertEqual(speech_path.read_bytes(), b"mp3-data")
            speech_path.unlink()

    def test_openai_tts_voices_are_supported(self):
        self.assertEqual(bot.OPENAI_TTS_VOICE, "alloy")
        self.assertEqual(bot.CHAT_TTS_VOICE, "onyx")
        self.assertIn("onyx", bot.OPENAI_TTS_VOICES)
        self.assertIn("alloy", bot.OPENAI_TTS_VOICES)

    def test_openai_errors_do_not_leave_temporary_files(self):
        error = bot.URLError("failed")
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(bot.tempfile, "tempdir", directory),
            patch.dict(bot.os.environ, {"OPENAI_API_KEY": "openai-secret"}),
            patch.object(bot, "urlopen", side_effect=error),
        ):
            with self.assertRaisesRegex(RuntimeError, "request failed"):
                bot.synthesize_speech("hello", "onyx")

            self.assertEqual(list(Path(directory).iterdir()), [])


class CasualReplyStyleTests(unittest.TestCase):
    def test_emoji_only_message_gets_strict_plain_reply_guidance(self):
        guidance = bot.short_casual_reply_guidance("🦦")

        self.assertIn("one emoji or at most four plain words", guidance)
        self.assertIn("Do not describe, caption, rate, or invent a story", guidance)

    def test_short_statement_gets_single_line_reply_guidance(self):
        guidance = bot.short_casual_reply_guidance("couldnt get radiant")

        self.assertIn("one line and at most twelve words", guidance)
        self.assertIn("without narration", guidance)

    def test_questions_and_requests_keep_normal_reply_behavior(self):
        self.assertIsNone(bot.short_casual_reply_guidance("how do I fix this"))
        self.assertIsNone(bot.short_casual_reply_guidance("explain the voice commands"))
        self.assertIsNone(bot.short_casual_reply_guidance("can you help me"))
        self.assertIsNone(bot.short_casual_reply_guidance("please help me"))
        self.assertIsNone(bot.short_casual_reply_guidance("pls explain this"))

    def test_casual_reply_keeps_reaction_and_drops_generated_followup_bit(self):
        reply = "🦦\n\notter detected.\n\nlevel of silliness: maximum"

        self.assertEqual(bot.keep_first_reply_line(reply), "🦦")


class GroqConfigTests(unittest.TestCase):
    def test_default_chat_model_is_cheap_fast_groq_model(self):
        self.assertEqual(bot.DEFAULT_GROQ_CHAT_MODEL, "llama-3.1-8b-instant")

    def test_chat_completion_uses_groq_api(self):
        response = {"choices": [{"message": {"content": "hello"}}]}
        with (
            patch.dict(
                bot.os.environ,
                {"GROQ_API_KEY": "secret", "GROQ_CHAT_MODEL": "llama-3.1-8b-instant"},
            ),
            patch.object(bot, "post_json", return_value=response) as post_json,
        ):
            result = bot.create_chat_completion(
                [{"role": "user", "content": "hi"}], max_tokens=25
            )

        self.assertEqual(result, "hello")
        post_json.assert_called_once_with(
            "https://api.groq.com/openai/v1/chat/completions",
            {
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": "hi"}],
                "max_completion_tokens": 25,
            },
            headers={"Authorization": "Bearer secret", "User-Agent": "pkla-dog/1.0"},
        )

    def test_groq_trims_railway_env_values(self):
        response = {"choices": [{"message": {"content": "hello"}}]}
        with (
            patch.dict(
                bot.os.environ,
                {
                    "GROQ_API_KEY": " secret\n",
                    "GROQ_CHAT_MODEL": " llama-3.1-8b-instant ",
                },
                clear=True,
            ),
            patch.object(bot, "post_json", return_value=response) as post_json,
        ):
            bot.create_groq_chat_completion([], max_tokens=25)

        self.assertEqual(
            post_json.call_args.kwargs["headers"]["Authorization"], "Bearer secret"
        )
        self.assertEqual(post_json.call_args.args[1]["model"], "llama-3.1-8b-instant")

    def test_groq_retries_transient_rate_limit(self):
        response = {"choices": [{"message": {"content": "hello"}}]}
        rate_limit = bot.JsonHTTPError(
            "https://api.groq.com/openai/v1/chat/completions",
            429,
            "Too Many Requests",
            '{"error":{"message":"rate limit"}}',
        )
        with (
            patch.dict(bot.os.environ, {"GROQ_API_KEY": "secret"}, clear=True),
            patch.object(bot, "post_json", side_effect=[rate_limit, response]) as post_json,
            patch.object(bot.time, "sleep") as sleep,
        ):
            result = bot.create_groq_chat_completion([], max_tokens=25)

        self.assertEqual(result, "hello")
        self.assertEqual(post_json.call_count, 2)
        sleep.assert_called_once_with(0.5)

    def test_groq_context_keeps_system_and_recent_messages_within_budget(self):
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "old" * 100},
            {"role": "assistant", "content": "recent reply"},
            {"role": "user", "content": "latest question"},
        ]

        trimmed = bot.trim_chat_messages(messages, char_budget=45)

        self.assertEqual(trimmed[0], messages[0])
        self.assertEqual(trimmed[-2:], messages[-2:])
        self.assertNotIn(messages[1], trimmed)

    def test_disabled_api_calls_block_chat_before_provider_requests(self):
        with (
            patch.object(bot, "ai_api_calls_enabled", False),
            patch.object(bot, "create_groq_chat_completion") as groq_chat,
            patch.object(bot, "create_openai_chat_completion") as openai_chat,
        ):
            with self.assertRaisesRegex(RuntimeError, "API calls are disabled"):
                bot.create_chat_completion([], max_tokens=25)

        groq_chat.assert_not_called()
        openai_chat.assert_not_called()

    def test_chat_completion_does_not_fallback_to_openai_by_default(self):
        with (
            patch.dict(bot.os.environ, {"OPENAI_API_KEY": "secret"}, clear=True),
            patch.object(bot, "create_openai_chat_completion") as openai_chat,
        ):
            with self.assertRaisesRegex(RuntimeError, "OPENAI_CHAT_FALLBACK is disabled"):
                bot.create_chat_completion([], max_tokens=25)

        openai_chat.assert_not_called()

    def test_chat_completion_uses_openai_only_when_fallback_is_enabled(self):
        with (
            patch.dict(
                bot.os.environ,
                {
                    "OPENAI_API_KEY": "secret",
                    "OPENAI_CHAT_FALLBACK": "true",
                },
                clear=True,
            ),
            patch.object(
                bot, "create_openai_chat_completion", return_value="fallback"
            ) as openai_chat,
        ):
            result = bot.create_chat_completion([], max_tokens=25)

        self.assertEqual(result, "fallback")
        openai_chat.assert_called_once_with([], max_tokens=25)

    def test_legacy_groq_model_env_is_still_supported(self):
        response = {"choices": [{"message": {"content": "hello"}}]}
        with (
            patch.dict(
                bot.os.environ,
                {"GROQ_API_KEY": "secret", "GROQ_MODEL": "legacy-model"},
                clear=True,
            ),
            patch.object(bot, "post_json", return_value=response) as post_json,
        ):
            bot.create_chat_completion([], max_tokens=25)

        self.assertEqual(post_json.call_args.args[1]["model"], "legacy-model")

    def test_listen_in_and_transcription_flags_default_safely(self):
        with patch.dict(bot.os.environ, {}, clear=True):
            self.assertTrue(bot.env_bool("ENABLE_LISTEN_IN", True))
            self.assertFalse(bot.env_bool("ENABLE_TRANSCRIPTION", False))

    def test_openai_web_search_is_disabled_by_default(self):
        with (
            patch.dict(bot.os.environ, {"OPENAI_API_KEY": "secret"}, clear=True),
            patch.object(bot, "post_json") as post_json,
        ):
            self.assertEqual(bot.openai_web_search("query", recent=False), [])

        post_json.assert_not_called()

    def test_missing_groq_key_returns_configuration_guidance(self):
        groq_error = RuntimeError("GROQ_API_KEY is not set")
        error = RuntimeError("Groq chat failed")
        error.__cause__ = groq_error

        self.assertEqual(
            bot.error_reply(error),
            "AI chat isn't configured. Set GROQ_API_KEY in Variables, then redeploy.",
        )

    def test_rejected_groq_key_returns_key_guidance(self):
        groq_error = bot.JsonHTTPError(
            "https://api.groq.com/openai/v1/chat/completions",
            401,
            "Unauthorized",
            '{"error":{"message":"invalid API key"}}',
        )
        error = RuntimeError("Groq chat failed")
        error.__cause__ = groq_error

        self.assertEqual(
            bot.error_reply(error),
            "Groq rejected the API key. Check GROQ_API_KEY in Variables, then redeploy.",
        )

    def test_groq_rate_limit_returns_retry_guidance(self):
        groq_error = bot.JsonHTTPError(
            "https://api.groq.com/openai/v1/chat/completions",
            429,
            "Too Many Requests",
            '{"error":{"message":"rate limit"}}',
        )
        error = RuntimeError("Groq chat failed")
        error.__cause__ = groq_error

        self.assertEqual(
            bot.error_reply(error),
            "Groq is rate-limited right now. Try again in a minute.",
        )

    def test_other_groq_failure_returns_safe_provider_guidance(self):
        self.assertEqual(
            bot.error_reply(RuntimeError("Groq chat failed")),
            "Groq couldn't return a response right now. Check the deployment logs.",
        )

    def test_system_prompt_uses_natural_discord_conversation_style(self):
        self.assertIn("real person participating in a Discord conversation", bot.SYSTEM_PROMPT)
        self.assertIn("usually reply with one short sentence", bot.SYSTEM_PROMPT)
        self.assertIn("not as a template for your wording", bot.SYSTEM_PROMPT)

    def test_system_prompt_requests_rude_profane_style_with_safety_limits(self):
        self.assertIn("rude, sarcastic, and casually profane", bot.SYSTEM_PROMPT)
        self.assertIn("use slurs, threats, and insults based on protected traits", bot.SYSTEM_PROMPT)

    def test_system_prompt_avoids_repetitive_meme_post_style(self):
        self.assertIn("Do not write like a meme account or a viral post", bot.SYSTEM_PROMPT)
        self.assertIn("Do not merely echo the user's words and add a scripted punchline", bot.SYSTEM_PROMPT)
        self.assertIn("Treat emoji-only messages like a person would", bot.SYSTEM_PROMPT)
        self.assertIn("Usually use zero or one", bot.SYSTEM_PROMPT)

    def test_system_prompt_describes_current_bot_capabilities_without_overstating_them(self):
        self.assertIn("`!join`", bot.SYSTEM_PROMPT)
        self.assertIn("every five minutes", bot.SYSTEM_PROMPT)
        self.assertIn("Joining never starts recording", bot.SYSTEM_PROMPT)
        self.assertIn("listen to live call audio in the browser", bot.SYSTEM_PROMPT)
        self.assertNotIn("transcription", bot.SYSTEM_PROMPT.lower())
        self.assertIn("external `/say` web page", bot.SYSTEM_PROMPT)
        self.assertIn("Wolf bark", bot.SYSTEM_PROMPT)
        self.assertIn("Minecraft bark", bot.SYSTEM_PROMPT)
        self.assertIn("normal AI reply does not itself execute", bot.SYSTEM_PROMPT)

class ExternalSayTests(unittest.TestCase):
    def setUp(self):
        self.client = bot.app.test_client()

    def test_page_is_available_without_a_control_token(self):
        response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Say it your way.", response.data)
        self.assertIn(b'/favicon.ico?v=1', response.data)
        self.assertNotIn(b'name="token"', response.data)

    def test_page_has_voice_controls_with_default_channel(self):
        response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Voice call", response.data)
        self.assertIn(b'name="action" value="join"', response.data)
        self.assertIn(b'name="action" value="stop"', response.data)
        self.assertIn(b"Stop audio", response.data)
        self.assertIn(b'name="action" value="leave"', response.data)
        self.assertIn(b'name="action" value="server_mute">Server Mute', response.data)
        self.assertIn(
            b'name="action" value="server_deafen">Server Deafen', response.data
        )
        self.assertIn(b"Member voice moderation", response.data)
        self.assertIn(b'name="target_user_id"', response.data)
        self.assertIn(b'value="server_mute_member">Server Mute Member', response.data)
        self.assertIn(
            b'value="server_deafen_member">Server Deafen Member', response.data
        )
        self.assertIn(
            b'value="1447148315312521256"',
            response.data,
        )

    def test_page_has_buttons_for_each_sound_clip(self):
        response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Sound clips", response.data)
        self.assertIn(b'value="wolf">Wolf bark</button>', response.data)
        self.assertIn(b'value="minecraft">Minecraft bark</button>', response.data)
        self.assertIn(b'value="fart">Bark fart</button>', response.data)
        self.assertNotIn(b'value="jamal">', response.data)
        self.assertNotIn(b'value="evan">', response.data)

    def test_page_has_text_to_speech_controls(self):
        response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Text to speech", response.data)
        self.assertIn(b'name="speech_text"', response.data)
        self.assertIn(b'name="voice"', response.data)
        self.assertIn(b'value="onyx"', response.data)
        self.assertNotIn(b'value="default"', response.data)
        self.assertIn(b'name="action" value="speak"', response.data)
        self.assertIn(f"up to {bot.TTS_TEXT_LIMIT} characters".encode(), response.data)

    def test_page_can_show_custom_openai_voice(self):
        with (
            patch.object(
                bot,
                "OPENAI_TTS_VOICES",
                {"default": "OpenAI default", "manly": "Manly OpenAI"},
            ),
            patch.object(bot, "OPENAI_TTS_VOICE", "manly"),
        ):
            response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'value="manly" selected', response.data)
        self.assertIn(b"Manly OpenAI", response.data)

    def test_page_has_ryan_birthday_button_with_target_channel(self):
        response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Ryan's birthday card", response.data)
        self.assertIn(b'name="action" value="birthday_ryan"', response.data)
        self.assertIn(b"Send Ryan's birthday card", response.data)
        self.assertIn(str(bot.RYAN_BIRTHDAY_CHANNEL_ID).encode(), response.data)
        self.assertGreater(
            response.data.index(b"Ryan's birthday card"),
            response.data.index(b"Upload audio"),
        )

    def test_birthday_button_sends_to_configured_ryan_channel(self):
        with patch.object(bot, "submit_external_ryan_birthday") as submit_birthday:
            response = self.client.post(
                "/say",
                data={"action": "birthday_ryan"},
            )

        self.assertEqual(response.status_code, 303)
        self.assertIn(
            "status=Ryan's+birthday+card+sent",
            response.headers["Location"],
        )
        submit_birthday.assert_called_once_with()

    def test_birthday_button_fetch_returns_success_status(self):
        with patch.object(bot, "submit_external_ryan_birthday") as submit_birthday:
            response = self.client.post(
                "/say",
                data={"action": "birthday_ryan"},
                headers={"X-Requested-With": "fetch"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "Ryan's birthday card sent."})
        submit_birthday.assert_called_once_with()

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

    def test_empty_speech_is_rejected(self):
        response = self.client.post(
            "/say",
            data={
                "action": "speak",
                "voice_channel_id": "1447148315312521256",
                "speech_text": "   ",
                "voice": "onyx",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Enter text to speak first", response.data)

    def test_over_limit_speech_is_rejected(self):
        response = self.client.post(
            "/say",
            data={
                "action": "speak",
                "voice_channel_id": "1447148315312521256",
                "speech_text": "x" * (bot.TTS_TEXT_LIMIT + 1),
                "voice": "onyx",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Speech text cannot exceed", response.data)

    def test_unknown_speech_voice_is_rejected(self):
        response = self.client.post(
            "/say",
            data={
                "action": "speak",
                "voice_channel_id": "1447148315312521256",
                "speech_text": "hello",
                "voice": "arbitrary",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Unknown text-to-speech voice", response.data)

    def test_previous_default_speech_voice_is_rejected(self):
        response = self.client.post(
            "/say",
            data={
                "action": "speak",
                "voice_channel_id": "1447148315312521256",
                "speech_text": "hello",
                "voice": "default",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Unknown text-to-speech voice", response.data)

    def test_valid_speech_form_submits_selected_values(self):
        with patch.object(
            bot, "submit_external_speech", return_value="speaking in #General"
        ) as submit_speech:
            response = self.client.post(
                "/say",
                data={
                    "action": "speak",
                    "voice_channel_id": "1447148315312521256",
                    "speech_text": "  hello there  ",
                    "voice": "onyx",
                },
            )

        self.assertEqual(response.status_code, 303)
        self.assertIn("status=speaking+in+%23General", response.headers["Location"])
        submit_speech.assert_called_once_with(
            1447148315312521256, "hello there", "onyx"
        )

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

    def test_stop_audio_form_uses_selected_channel(self):
        with patch.object(
            bot,
            "submit_external_voice_action",
            return_value="stopped audio in #General",
        ) as submit_voice:
            response = self.client.post(
                "/say",
                data={
                    "action": "stop",
                    "voice_channel_id": "1447148315312521256",
                },
            )

        self.assertEqual(response.status_code, 303)
        self.assertIn("status=stopped+audio+in+%23General", response.headers["Location"])
        submit_voice.assert_called_once_with("stop", 1447148315312521256)

    def test_server_mute_form_uses_selected_channel(self):
        with patch.object(
            bot,
            "submit_external_voice_action",
            return_value="server mute enabled",
        ) as submit_voice:
            response = self.client.post(
                "/say",
                data={
                    "action": "server_mute",
                    "voice_channel_id": "1447148315312521256",
                },
            )

        self.assertEqual(response.status_code, 303)
        submit_voice.assert_called_once_with("server_mute", 1447148315312521256)

    def test_server_deafen_form_uses_selected_channel(self):
        with patch.object(
            bot,
            "submit_external_voice_action",
            return_value="server deafen enabled",
        ) as submit_voice:
            response = self.client.post(
                "/say",
                data={
                    "action": "server_deafen",
                    "voice_channel_id": "1447148315312521256",
                },
            )

        self.assertEqual(response.status_code, 303)
        submit_voice.assert_called_once_with("server_deafen", 1447148315312521256)

    def test_member_mute_form_uses_selected_channel_and_target_user(self):
        with patch.object(
            bot,
            "submit_external_member_voice_action",
            return_value="server muted Coolxng",
        ) as submit_member_voice:
            response = self.client.post(
                "/say",
                data={
                    "action": "server_mute_member",
                    "voice_channel_id": "1447148315312521256",
                    "target_user_id": "575057023046123520",
                },
            )

        self.assertEqual(response.status_code, 303)
        submit_member_voice.assert_called_once_with(
            "server_mute_member", 1447148315312521256, 575057023046123520
        )

    def test_member_mute_form_requires_numeric_user_id(self):
        response = self.client.post(
            "/say",
            data={
                "action": "server_mute_member",
                "voice_channel_id": "1447148315312521256",
                "target_user_id": "not-a-user",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Enter a valid numeric Discord user ID.", response.data)

    def test_sound_button_plays_selected_sound(self):
        with patch.object(
            bot,
            "submit_external_voice_action",
            return_value="playing Wolf bark",
        ) as submit_voice:
            response = self.client.post(
                "/say",
                data={
                    "action": "play_sound",
                    "sound": "wolf",
                    "voice_channel_id": "1447148315312521256",
                },
            )

        self.assertEqual(response.status_code, 303)
        self.assertIn("status=playing+Wolf+bark", response.headers["Location"])
        submit_voice.assert_called_once_with(
            "play_sound", 1447148315312521256, "wolf"
        )

    def test_unknown_sound_is_rejected(self):
        response = self.client.post(
            "/say",
            data={
                "action": "play_sound",
                "sound": "unknown",
                "voice_channel_id": "1447148315312521256",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Unknown bark sound", response.data)

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


class ExternalUploadedAudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_requires_connected_voice_client(self):
        class FakeVoiceChannel:
            mention = "#General"

        channel = FakeVoiceChannel()
        channel.guild = SimpleNamespace(voice_client=None)
        with tempfile.TemporaryDirectory() as temporary_directory:
            audio_path = Path(temporary_directory, "clip.mp3")
            audio_path.write_bytes(b"ID3audio")
            with (
                patch.object(bot, "client", SimpleNamespace(get_channel=lambda _channel_id: channel)),
                patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
            ):
                with self.assertRaisesRegex(RuntimeError, "Join the selected voice call"):
                    await bot.control_external_uploaded_audio(123, audio_path)

            self.assertFalse(audio_path.exists())

    async def test_upload_requires_exact_selected_voice_channel(self):
        class FakeVoiceChannel:
            mention = "#General"

        channel = FakeVoiceChannel()
        voice_client = SimpleNamespace(
            channel=object(),
            is_connected=lambda: True,
            is_playing=lambda: False,
        )
        channel.guild = SimpleNamespace(voice_client=voice_client)
        with tempfile.TemporaryDirectory() as temporary_directory:
            audio_path = Path(temporary_directory, "clip.mp3")
            audio_path.write_bytes(b"ID3audio")
            with (
                patch.object(bot, "client", SimpleNamespace(get_channel=lambda _channel_id: channel)),
                patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
            ):
                with self.assertRaisesRegex(RuntimeError, "different voice channel"):
                    await bot.control_external_uploaded_audio(123, audio_path)

            self.assertFalse(audio_path.exists())

    async def test_upload_rejects_audio_while_another_clip_is_playing(self):
        class FakeVoiceChannel:
            mention = "#General"

        channel = FakeVoiceChannel()
        voice_client = SimpleNamespace(
            channel=channel,
            is_connected=lambda: True,
            is_playing=lambda: True,
        )
        channel.guild = SimpleNamespace(voice_client=voice_client)
        with tempfile.TemporaryDirectory() as temporary_directory:
            audio_path = Path(temporary_directory, "clip.mp3")
            audio_path.write_bytes(b"ID3audio")
            with (
                patch.object(bot, "client", SimpleNamespace(get_channel=lambda _channel_id: channel)),
                patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
            ):
                with self.assertRaisesRegex(RuntimeError, "already playing"):
                    await bot.control_external_uploaded_audio(123, audio_path)

            self.assertFalse(audio_path.exists())

    async def test_upload_passes_delete_after_to_play_audio(self):
        class FakeVoiceChannel:
            mention = "#General"

        channel = FakeVoiceChannel()
        voice_client = SimpleNamespace(
            channel=channel,
            is_connected=lambda: True,
            is_playing=lambda: False,
        )
        channel.guild = SimpleNamespace(voice_client=voice_client)
        with tempfile.TemporaryDirectory() as temporary_directory:
            audio_path = Path(temporary_directory, "clip.mp3")
            audio_path.write_bytes(b"ID3audio")
            with (
                patch.object(bot, "client", SimpleNamespace(get_channel=lambda _channel_id: channel)),
                patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
                patch.object(bot, "play_audio", return_value=True) as play_audio,
            ):
                response = await bot.control_external_uploaded_audio(123, audio_path)

            self.assertEqual(response, "playing uploaded audio in #General")
            play_audio.assert_called_once_with(
                voice_client,
                audio_path,
                activity_type="uploaded_audio",
                label="uploaded audio",
                delete_after=True,
            )
            audio_path.unlink()

    async def test_upload_removes_file_when_playback_start_raises(self):
        class FakeVoiceChannel:
            mention = "#General"

        channel = FakeVoiceChannel()
        voice_client = SimpleNamespace(
            channel=channel,
            is_connected=lambda: True,
            is_playing=lambda: False,
        )
        channel.guild = SimpleNamespace(voice_client=voice_client)
        with tempfile.TemporaryDirectory() as temporary_directory:
            audio_path = Path(temporary_directory, "clip.mp3")
            audio_path.write_bytes(b"ID3audio")
            with (
                patch.object(bot, "client", SimpleNamespace(get_channel=lambda _channel_id: channel)),
                patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
                patch.object(bot, "play_audio", side_effect=RuntimeError("ffmpeg failed")),
            ):
                with self.assertRaisesRegex(RuntimeError, "ffmpeg failed"):
                    await bot.control_external_uploaded_audio(123, audio_path)

            self.assertFalse(audio_path.exists())

    def test_submit_upload_removes_file_on_discord_error_or_timeout(self):
        for message in ("Discord failed", "Discord took too long"):
            with self.subTest(message=message), tempfile.TemporaryDirectory() as temporary_directory:
                audio_path = Path(temporary_directory, "clip.mp3")
                audio_path.write_bytes(b"ID3audio")
                with (
                    patch.object(bot, "control_external_uploaded_audio", new=Mock(return_value=Mock())),
                    patch.object(bot, "run_discord_coroutine", side_effect=RuntimeError(message)),
                ):
                    with self.assertRaisesRegex(RuntimeError, message):
                        bot.submit_external_uploaded_audio(123, audio_path)
                self.assertFalse(audio_path.exists())

    def test_browser_talk_start_uses_extended_discord_timeout(self):
        def run_result(coroutine, *_args, **_kwargs):
            coroutine.close()
            return {"session_id": "abc"}

        with patch.object(bot, "run_discord_coroutine", side_effect=run_result) as run:
            result = bot.submit_browser_talk_start(123, "audio/webm;codecs=opus")

        self.assertEqual(result, {"session_id": "abc"})
        self.assertEqual(run.call_args.kwargs["timeout_seconds"], 30)
        self.assertIn("fully connected", run.call_args.args[1])


class ExternalSayUploadFormTests(unittest.TestCase):
    def setUp(self):
        self.client = bot.app.test_client()

    @staticmethod
    def upload_data(content=b"ID3audio", filename="clip.mp3", channel_id="123"):
        return {
            "action": "upload_audio",
            "voice_channel_id": channel_id,
            "audio_file": (io.BytesIO(content), filename),
        }

    def test_page_renders_right_side_multipart_upload_panel(self):
        response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'class="control-grid"', response.data)
        self.assertIn(b'class="panel upload-panel"', response.data)
        self.assertIn(b'enctype="multipart/form-data"', response.data)
        self.assertIn(b'name="action" value="upload_audio"', response.data)
        self.assertIn(b'name="audio_file"', response.data)
        self.assertIn(b'accept=".mp3,.mp4,audio/mpeg,video/mp4"', response.data)
        self.assertIn(b"The bot must already be connected", response.data)
        self.assertIn(str(bot.MAX_UPLOADED_AUDIO_BYTES // (1024 * 1024)).encode(), response.data)

    def test_valid_upload_submits_channel_and_redirects(self):
        for content, filename in (
            (b"ID3audio", "clip.mp3"),
            (b"\x00\x00\x00\x18ftypisom", "clip.mp4"),
        ):
            with self.subTest(filename=filename):
                submitted = []

                def submit(channel_id, audio_path):
                    submitted.append((channel_id, audio_path))
                    return "playing uploaded audio in #General"

                with patch.object(bot, "submit_external_uploaded_audio", side_effect=submit):
                    response = self.client.post(
                        "/say",
                        data=self.upload_data(content=content, filename=filename),
                        content_type="multipart/form-data",
                    )

                self.assertEqual(response.status_code, 303)
                self.assertIn(
                    "status=playing+uploaded+audio+in+%23General",
                    response.headers["Location"],
                )
                self.assertEqual(submitted[0][0], 123)
                self.assertEqual(submitted[0][1].suffix, Path(filename).suffix)
                self.assertTrue(submitted[0][1].is_file())
                submitted[0][1].unlink()

    def test_missing_empty_unsupported_malformed_and_oversized_uploads_are_rejected(self):
        cases = (
            (None, b"Choose an MP3 or MP4 file"),
            (self.upload_data(content=b""), b"empty"),
            (self.upload_data(filename="clip.wav"), b".mp3 or .mp4 extension"),
            (self.upload_data(content=b"not an mp3"), b"does not appear"),
            (
                self.upload_data(content=b"not an mp4", filename="clip.mp4"),
                b"does not appear",
            ),
        )
        for data, expected in cases:
            with self.subTest(expected=expected):
                response = self.client.post(
                    "/say",
                    data=data or {"action": "upload_audio", "voice_channel_id": "123"},
                    content_type="multipart/form-data",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(expected, response.data)

        with patch.object(bot, "MAX_UPLOADED_AUDIO_BYTES", 4):
            response = self.client.post(
                "/say",
                data=self.upload_data(content=b"ID3too large"),
                content_type="multipart/form-data",
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"cannot exceed", response.data)

    def test_submitted_filename_cannot_choose_temporary_path(self):
        submitted_paths = []
        with patch.object(
            bot,
            "submit_external_uploaded_audio",
            side_effect=lambda _channel_id, path: submitted_paths.append(path) or "playing",
        ):
            response = self.client.post(
                "/say",
                data=self.upload_data(filename="../../chosen-by-user.mp3"),
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 303)
        self.assertNotEqual(submitted_paths[0].name, "chosen-by-user.mp3")
        self.assertTrue(submitted_paths[0].name.endswith(".mp3"))
        submitted_paths[0].unlink()

    def test_validation_failure_removes_generated_temporary_file(self):
        original_named_temporary_file = tempfile.NamedTemporaryFile
        with tempfile.TemporaryDirectory() as temporary_directory:
            def local_temporary_file(*args, **kwargs):
                kwargs["dir"] = temporary_directory
                return original_named_temporary_file(*args, **kwargs)

            with patch.object(bot.tempfile, "NamedTemporaryFile", side_effect=local_temporary_file):
                response = self.client.post(
                    "/say",
                    data=self.upload_data(content=b"invalid"),
                    content_type="multipart/form-data",
                )

            self.assertEqual(response.status_code, 400)
            self.assertEqual(list(Path(temporary_directory).iterdir()), [])

    def test_flask_request_limit_returns_readable_413(self):
        original_limit = bot.app.config["MAX_CONTENT_LENGTH"]
        bot.app.config["MAX_CONTENT_LENGTH"] = 100
        try:
            response = self.client.post(
                "/say",
                data=self.upload_data(content=b"ID3" + b"x" * 200),
                content_type="multipart/form-data",
            )
        finally:
            bot.app.config["MAX_CONTENT_LENGTH"] = original_limit

        self.assertEqual(response.status_code, 413)
        self.assertIn(b"Upload request is too large", response.data)

    def test_control_token_popup_authenticates_browser_with_cookie(self):
        with patch.object(bot, "EXTERNAL_SAY_CONTROL_TOKEN", "secret-token"):
            locked_page = self.client.get("/say")
            invalid_login = self.client.post(
                "/say/login", json={"token": "wrong-token"}
            )
            valid_login = self.client.post(
                "/say/login", json={"token": "secret-token"}
            )
            unlocked_page = self.client.get("/say")

        self.assertEqual(locked_page.status_code, 200)
        self.assertIn(b'id="control-token-dialog"', locked_page.data)
        self.assertIn(b'id="control-token-form"', locked_page.data)
        self.assertEqual(invalid_login.status_code, 401)
        self.assertEqual(valid_login.status_code, 200)
        self.assertIn(bot.EXTERNAL_SAY_AUTH_COOKIE, valid_login.headers["Set-Cookie"])
        self.assertIn("HttpOnly", valid_login.headers["Set-Cookie"])
        self.assertNotIn(b'id="control-token-dialog"', unlocked_page.data)

    def test_control_posts_still_require_authentication(self):
        with patch.object(bot, "EXTERNAL_SAY_CONTROL_TOKEN", "secret-token"):
            response = self.client.post(
                "/say", data={"action": "join", "voice_channel_id": "123"}
            )

        self.assertEqual(response.status_code, 401)
        self.assertIn("Basic", response.headers["WWW-Authenticate"])

    def test_missing_server_token_shows_setup_popup(self):
        with patch.object(bot, "EXTERNAL_SAY_CONTROL_TOKEN", ""):
            response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="control-token-dialog"', response.data)
        self.assertIn(b"External control token not configured", response.data)
        self.assertNotIn(b'id="control-token-form"', response.data)


class ExternalVoiceStatusRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = bot.app.test_client()

    def test_say_page_contains_activity_panel_and_polling_ui(self):
        response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b">Activity<", response.data)
        self.assertIn(b"/say/status?voice_channel_id=", response.data)
        self.assertIn(b"Connected \xe2\x80\x94 nothing is playing", response.data)
        self.assertIn(b"Playing: ${status.label", response.data)
        self.assertIn(b"Could not refresh activity", response.data)
        self.assertIn(b"pollActivity();", response.data)
        self.assertIn(b"window.setTimeout(pollActivity, 3000)", response.data)
        self.assertIn(b'document.addEventListener("visibilitychange"', response.data)

    def test_say_page_contains_chat_tts_command_toggle(self):
        bot.chat_tts_command_enabled = True
        response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="tts-command-toggle"', response.data)
        self.assertIn(b'value="toggle_tts_command"', response.data)
        self.assertIn(b'class="toggle-track"', response.data)
        self.assertIn(b'<span class="toggle-state">On</span>', response.data)
        self.assertIn(b'aria-pressed="true"', response.data)

    def test_chat_tts_command_toggle_updates_server_state(self):
        bot.chat_tts_command_enabled = True

        response = self.client.post(
            "/say",
            data={"action": "toggle_tts_command"},
            headers={"X-Requested-With": "fetch"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.get_json(),
            {"status": "!tts command disabled.", "tts_command_enabled": False},
        )
        self.assertFalse(bot.chat_tts_command_enabled)

    def test_say_page_contains_api_calls_toggle_below_tts_toggle(self):
        with patch.object(bot, "ai_api_calls_enabled", True):
            response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="api-calls-toggle"', response.data)
        self.assertIn(b'value="toggle_api_calls"', response.data)
        self.assertLess(
            response.data.index(b'id="tts-command-toggle"'),
            response.data.index(b'id="api-calls-toggle"'),
        )
        self.assertIn(b"avoid using provider credits", response.data)

    def test_api_calls_toggle_updates_server_state(self):
        with patch.object(bot, "ai_api_calls_enabled", True):
            response = self.client.post(
                "/say",
                data={"action": "toggle_api_calls"},
                headers={"X-Requested-With": "fetch"},
            )

            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.get_json(),
                {"status": "AI API calls disabled.", "api_calls_enabled": False},
            )
            self.assertFalse(bot.ai_api_calls_enabled)

    def test_say_page_submits_controls_without_reloading(self):
        response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="control-status"', response.data)
        self.assertIn(b'document.querySelectorAll(\'main form[method="post"]\')', response.data)
        self.assertIn(b'headers: { "X-Requested-With": "fetch" }', response.data)
        self.assertIn(b'event.preventDefault()', response.data)

    def test_fetch_control_request_returns_json_without_redirect(self):
        with patch.object(
            bot,
            "submit_external_voice_action",
            return_value="joined #General",
        ):
            response = self.client.post(
                "/say",
                data={"action": "join", "voice_channel_id": "123"},
                headers={"X-Requested-With": "fetch"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "joined #General"})
        self.assertNotIn("Location", response.headers)

    def test_invalid_fetch_control_request_returns_json_error(self):
        response = self.client.post(
            "/say",
            data={"action": "join", "voice_channel_id": "not-a-channel"},
            headers={"X-Requested-With": "fetch"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {"status": "Enter a valid numeric voice channel ID."},
        )

    def test_say_page_uses_dark_discord_dashboard_styles(self):
        response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'class="page-header"', response.data)
        self.assertIn(b'class="panel message-panel"', response.data)
        self.assertIn(b'class="voice-tools"', response.data)
        self.assertIn(b"color-scheme: dark", response.data)
        self.assertIn(b"--canvas: #0f0f0f", response.data)
        self.assertIn(b"--surface: #1a1a1a", response.data)
        self.assertIn(b"--accent: #5865f2", response.data)
        self.assertIn(b"font-family: Inter, ui-sans-serif, system-ui", response.data)
        self.assertNotIn(b"linear-gradient", response.data)
        self.assertNotIn(b"box-shadow", response.data)
        self.assertNotIn(b"fonts.googleapis.com", response.data)

    def test_status_route_requires_numeric_channel_and_uses_discord_loop(self):
        invalid = self.client.get("/say/status?voice_channel_id=nope")
        self.assertEqual(invalid.status_code, 400)
        self.assertEqual(invalid.get_json()["state"], "unavailable")

        with patch.object(
            bot,
            "run_discord_coroutine",
            return_value={
                "state": "playing",
                "voice_channel_id": 123,
                "voice_channel_name": "General",
                "connection_state": "connected",
                "activity_type": "sound",
                "label": "Minecraft bark",
                "started_at": "2026-06-11T00:00:00+00:00",
            },
        ) as run_coroutine:
            response = self.client.get("/say/status?voice_channel_id=123")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["label"], "Minecraft bark")
        coroutine = run_coroutine.call_args.args[0]
        self.assertEqual(coroutine.cr_frame.f_locals["channel_id"], 123)
        coroutine.close()

    def test_status_route_uses_same_authentication_as_say_page(self):
        def status_result(coroutine, _timeout_message):
            coroutine.close()
            return {"state": "unavailable", "voice_channel_id": 123}

        with (
            patch.object(bot, "EXTERNAL_SAY_CONTROL_TOKEN", "secret-token"),
            patch.object(bot, "run_discord_coroutine", side_effect=status_result),
        ):
            unauthorized = self.client.get("/say/status?voice_channel_id=123")
            authorized = self.client.get(
                "/say/status?voice_channel_id=123",
                headers={"Authorization": "Basic dXNlcjpzZWNyZXQtdG9rZW4="},
            )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)


class VoiceActivityTransitionTests(unittest.IsolatedAsyncioTestCase):
    class FakeVoiceChannel:
        pass

    def setUp(self):
        bot.voice_activity_by_guild.clear()
        bot.last_tts_at.clear()

    def voice_context(self, *, playing=False):
        channel = self.FakeVoiceChannel()
        channel.id = 123
        channel.name = "General"
        channel.mention = "#General"
        callbacks = []
        guild = SimpleNamespace(id=456)
        voice_client = SimpleNamespace(
            guild=guild,
            channel=channel,
            is_connected=lambda: True,
            is_playing=lambda: playing,
            play=Mock(side_effect=lambda _source, after: callbacks.append(after)),
            stop=Mock(),
            disconnect=AsyncMock(),
        )
        guild.voice_client = voice_client
        channel.guild = guild
        return guild, channel, voice_client, callbacks

    async def test_join_idle_and_leave_disconnected_transitions(self):
        guild, channel, voice_client, _callbacks = self.voice_context()
        guild.voice_client = None
        channel.connect = AsyncMock(return_value=voice_client)

        with (
            patch.object(bot, "start_bark_task"),
            patch.object(bot.asyncio, "sleep", new=AsyncMock()),
            patch.object(bot, "play_bark", return_value=False),
        ):
            await bot.join_voice_channel(channel, guild)

        self.assertEqual(bot.voice_activity_by_guild[guild.id]["connection_state"], "connected")
        self.assertIsNone(bot.voice_activity_by_guild[guild.id]["activity_type"])

        guild.voice_client = voice_client
        with patch.object(bot, "stop_bark_task"):
            await bot.leave_guild_voice(guild)

        activity = bot.voice_activity_by_guild[guild.id]
        self.assertEqual(activity["connection_state"], "disconnected")
        self.assertEqual(activity["voice_channel_id"], channel.id)

    async def test_sound_playback_and_completion_transition(self):
        guild, channel, voice_client, callbacks = self.voice_context()
        with (
            patch.object(bot.discord, "VoiceChannel", self.FakeVoiceChannel),
            patch.object(bot.client, "get_channel", return_value=channel),
            patch.object(bot.discord, "FFmpegPCMAudio", return_value=Mock()),
        ):
            response = await bot.control_external_voice("play_sound", channel.id, "minecraft")

        self.assertEqual(response, "playing Minecraft bark")
        activity = bot.voice_activity_by_guild[guild.id]
        self.assertEqual(activity["activity_type"], "sound")
        self.assertEqual(activity["label"], "Minecraft bark")
        self.assertIsNotNone(activity["started_at"])

        callbacks[0](None)
        self.assertIsNone(bot.voice_activity_by_guild[guild.id]["activity_type"])

    async def test_tts_and_uploaded_audio_use_visible_labels(self):
        guild, channel, voice_client, callbacks = self.voice_context()
        speech_path = Path("speech.mp3")
        with (
            patch.object(bot.asyncio, "to_thread", new=AsyncMock(return_value=speech_path)),
            patch.object(bot.discord, "FFmpegPCMAudio", return_value=Mock()),
        ):
            await bot.speak_in_guild(
                guild,
                "This is a concise TTS preview",
                "onyx",
                not_connected_message="not connected",
            )

        self.assertEqual(bot.voice_activity_by_guild[guild.id]["activity_type"], "tts")
        self.assertEqual(
            bot.voice_activity_by_guild[guild.id]["label"],
            "TTS: \u201cThis is a concise TTS preview\u201d",
        )
        callbacks.pop(0)(None)

        with tempfile.TemporaryDirectory() as directory:
            audio_path = Path(directory) / "clip.mp3"
            audio_path.write_bytes(b"ID3audio")
            with (
                patch.object(bot.discord, "VoiceChannel", self.FakeVoiceChannel),
                patch.object(bot.client, "get_channel", return_value=channel),
                patch.object(bot.discord, "FFmpegPCMAudio", return_value=Mock()),
            ):
                await bot.control_external_uploaded_audio(channel.id, audio_path)

            self.assertEqual(
                bot.voice_activity_by_guild[guild.id]["activity_type"],
                "uploaded_audio",
            )
            self.assertEqual(bot.voice_activity_by_guild[guild.id]["label"], "uploaded audio")
            callbacks.pop(0)(None)

    async def test_stop_restores_idle_without_stale_completion(self):
        guild, channel, voice_client, callbacks = self.voice_context()
        with patch.object(bot.discord, "FFmpegPCMAudio", return_value=Mock()):
            bot.play_audio(
                voice_client,
                bot.BARK_AUDIO_PATH,
                activity_type="sound",
                label="Wolf bark",
            )

        voice_client.is_playing = lambda: True
        with (
            patch.object(bot.discord, "VoiceChannel", self.FakeVoiceChannel),
            patch.object(bot.client, "get_channel", return_value=channel),
        ):
            await bot.control_external_voice("stop", channel.id)

        idle_record = bot.voice_activity_by_guild[guild.id]
        self.assertIsNone(idle_record["activity_type"])
        callbacks[0](None)
        self.assertIs(bot.voice_activity_by_guild[guild.id], idle_record)

    def test_playback_failure_restores_idle(self):
        guild, _channel, voice_client, _callbacks = self.voice_context()
        voice_client.play.side_effect = RuntimeError("ffmpeg failed")

        with patch.object(bot.discord, "FFmpegPCMAudio", return_value=Mock()):
            with self.assertRaisesRegex(RuntimeError, "ffmpeg failed"):
                bot.play_audio(
                    voice_client,
                    bot.BARK_AUDIO_PATH,
                    activity_type="sound",
                    label="Dog bark",
                )

        activity = bot.voice_activity_by_guild[guild.id]
        self.assertEqual(activity["connection_state"], "connected")
        self.assertIsNone(activity["activity_type"])

    async def test_status_reports_unavailable_disconnected_idle_and_playing(self):
        guild, channel, voice_client, _callbacks = self.voice_context()
        with (
            patch.object(bot.discord, "VoiceChannel", self.FakeVoiceChannel),
            patch.object(bot.client, "get_channel", return_value=None),
        ):
            self.assertEqual((await bot.external_voice_status(channel.id))["state"], "unavailable")

        guild.voice_client = None
        with (
            patch.object(bot.discord, "VoiceChannel", self.FakeVoiceChannel),
            patch.object(bot.client, "get_channel", return_value=channel),
        ):
            self.assertEqual((await bot.external_voice_status(channel.id))["state"], "disconnected")

        guild.voice_client = voice_client
        with (
            patch.object(bot.discord, "VoiceChannel", self.FakeVoiceChannel),
            patch.object(bot.client, "get_channel", return_value=channel),
        ):
            self.assertEqual((await bot.external_voice_status(channel.id))["state"], "idle")
            voice_client.is_playing = lambda: True
            bot.set_voice_activity(
                guild,
                channel,
                connection_state="connected",
                activity_type="tts",
                label="TTS: \u201chello\u201d",
                queued_tts_count=2,
            )
            playing = await bot.external_voice_status(channel.id)

        self.assertEqual(playing["state"], "playing")
        self.assertEqual(playing["queued_tts_count"], 2)

    def test_browser_talk_cleanup_restores_idle_only_when_talk_was_active(self):
        guild, channel, voice_client, _callbacks = self.voice_context()
        bot.voice_activity_by_guild[guild.id] = {
            "activity_type": "browser_talk",
            "voice_channel_id": channel.id,
        }
        session = SimpleNamespace(voice_channel=channel)
        bot.active_browser_talk_session = session

        with patch.object(bot, "set_voice_idle") as set_voice_idle:
            bot._clear_browser_talk_session(session)

        self.assertIsNone(bot.active_browser_talk_session)
        set_voice_idle.assert_called_once_with(guild, channel)


if __name__ == "__main__":
    unittest.main()


class ExternalListeningFeatureTests(unittest.TestCase):
    def setUp(self):
        self.client = bot.app.test_client()

    def test_page_keeps_browser_listening_without_transcription_controls(self):
        response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Listen in browser", response.data)
        self.assertIn(b"Listen In", response.data)
        self.assertIn(b"Stop Listening", response.data)
        self.assertIn(b"Play Test Tone", response.data)
        self.assertNotIn(b"Call transcription", response.data)
        self.assertNotIn(b"/say/transcript", response.data)
        self.assertNotIn(b'value="start_transcription"', response.data)

    def test_transcript_route_is_removed(self):
        response = self.client.get("/say/transcript?voice_channel_id=123")

        self.assertEqual(response.status_code, 404)
