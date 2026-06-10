import asyncio
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
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

    def test_external_bark_audio_files_exist(self):
        self.assertEqual(
            {sound["path"].name for sound in bot.EXTERNAL_BARK_SOUNDS.values()},
            {
                "wolf-bark.mp3",
                "minecraft-bark.mp3",
                "bark-fart.mp3",
                "jamalcrazyidek.mp3",
                "evan-crash.mp4",
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
                played = bot.play_audio(voice_client, audio_path, delete_after=True)
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
            voice_client, bot.EXTERNAL_BARK_SOUNDS["minecraft"]["path"]
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
                    1447148315312521256, "hello", "alloy"
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
            patch.object(bot.time, "monotonic", return_value=100.0),
            patch.object(
                bot.asyncio, "to_thread", new=AsyncMock(return_value=speech_path)
            ) as to_thread,
            patch.object(bot, "play_audio", return_value=True) as play_audio,
        ):
            response = await bot.control_external_speech(
                1447148315312521256, "hello", "nova"
            )

        self.assertEqual(response, "speaking in #General")
        to_thread.assert_awaited_once_with(bot.synthesize_speech, "hello", "nova")
        play_audio.assert_called_once_with(voice_client, speech_path, delete_after=True)
        self.assertEqual(bot.last_tts_at[456], 100.0)

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
            patch.object(bot.time, "monotonic", return_value=100.0),
            patch.object(
                bot.asyncio,
                "to_thread",
                new=AsyncMock(side_effect=RuntimeError("speech failed")),
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "speech failed"):
                await bot.control_external_speech(
                    1447148315312521256, "hello", "alloy"
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
            patch.object(bot.time, "monotonic", return_value=100.0),
            patch.object(
                bot.asyncio,
                "to_thread",
                new=AsyncMock(side_effect=asyncio.CancelledError),
            ),
        ):
            with self.assertRaises(asyncio.CancelledError):
                await bot.control_external_speech(
                    1447148315312521256, "hello", "alloy"
                )

        self.assertNotIn(456, bot.last_tts_at)

    async def test_external_speech_failure_preserves_newer_cooldown(self):
        class FakeVoiceChannel:
            pass

        voice_client = SimpleNamespace(
            is_connected=lambda: True, is_playing=lambda: False
        )
        channel = FakeVoiceChannel()
        channel.guild = SimpleNamespace(id=456, voice_client=voice_client)

        async def fail_after_newer_request(*args):
            bot.last_tts_at[456] = 200.0
            raise RuntimeError("speech failed")

        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
            patch.object(bot.time, "monotonic", return_value=100.0),
            patch.object(bot.asyncio, "to_thread", side_effect=fail_after_newer_request),
        ):
            with self.assertRaisesRegex(RuntimeError, "speech failed"):
                await bot.control_external_speech(
                    1447148315312521256, "hello", "alloy"
                )

        self.assertEqual(bot.last_tts_at[456], 200.0)

    async def test_external_speech_enforces_server_cooldown_before_synthesis(self):
        class FakeVoiceChannel:
            pass

        voice_client = SimpleNamespace(
            is_connected=lambda: True, is_playing=lambda: False
        )
        channel = FakeVoiceChannel()
        channel.guild = SimpleNamespace(id=456, voice_client=voice_client)
        bot.last_tts_at[456] = 100.0
        with (
            patch.object(bot, "client", SimpleNamespace(get_channel=lambda channel_id: channel)),
            patch.object(bot.discord, "VoiceChannel", FakeVoiceChannel),
            patch.object(bot.time, "monotonic", return_value=110.0),
            patch.object(bot.asyncio, "to_thread", new=AsyncMock()) as to_thread,
        ):
            with self.assertRaisesRegex(RuntimeError, "cooldown"):
                await bot.control_external_speech(
                    1447148315312521256, "hello", "alloy"
                )

        to_thread.assert_not_awaited()

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
                    1447148315312521256, "hello", "alloy"
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
    def test_openai_request_contains_configured_speech_values(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b"mp3-data"

        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(bot.os.environ, {"OPENAI_API_KEY": "secret"}),
            patch.object(bot.tempfile, "tempdir", directory),
            patch.object(bot, "urlopen", return_value=FakeResponse()) as urlopen,
        ):
            speech_path = bot.synthesize_speech("hello", "nova")
            speech_request = urlopen.call_args.args[0]
            payload = json.loads(speech_request.data.decode("utf-8"))

            self.assertEqual(speech_request.full_url, "https://api.openai.com/v1/audio/speech")
            self.assertEqual(payload["model"], bot.OPENAI_TTS_MODEL)
            self.assertEqual(payload["voice"], "nova")
            self.assertEqual(payload["input"], "hello")
            self.assertEqual(payload["response_format"], "mp3")
            self.assertEqual(speech_path.read_bytes(), b"mp3-data")
            speech_path.unlink()

    def test_api_errors_do_not_leave_temporary_files(self):
        error = HTTPError(
            "https://api.openai.com/v1/audio/speech",
            429,
            "Too Many Requests",
            {},
            io.BytesIO(b'{"error":"rate limited"}'),
        )
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(bot.os.environ, {"OPENAI_API_KEY": "secret"}),
            patch.object(bot.tempfile, "tempdir", directory),
            patch.object(bot, "urlopen", side_effect=error),
        ):
            with self.assertRaisesRegex(RuntimeError, "could not generate speech"):
                bot.synthesize_speech("hello", "alloy")

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


class OpenAIConfigTests(unittest.TestCase):
    def test_default_model_uses_chatgpt_like_alias(self):
        self.assertEqual(bot.DEFAULT_OPENAI_MODEL, "chat-latest")

    def test_gpt5_reasoning_effort_defaults_to_none(self):
        self.assertEqual(bot.default_reasoning_effort("gpt-5.5"), "none")

    def test_system_prompt_uses_natural_discord_conversation_style(self):
        self.assertIn("real person participating in a Discord conversation", bot.SYSTEM_PROMPT)
        self.assertIn("usually reply with one short sentence", bot.SYSTEM_PROMPT)
        self.assertIn("not as a template for your wording", bot.SYSTEM_PROMPT)

    def test_system_prompt_avoids_repetitive_meme_post_style(self):
        self.assertIn("Do not write like a meme account or a viral post", bot.SYSTEM_PROMPT)
        self.assertIn("Do not merely echo the user's words and add a scripted punchline", bot.SYSTEM_PROMPT)
        self.assertIn("Treat emoji-only messages like a person would", bot.SYSTEM_PROMPT)
        self.assertIn("Usually use zero or one", bot.SYSTEM_PROMPT)

    def test_system_prompt_describes_current_bot_capabilities_without_overstating_them(self):
        self.assertIn("`!join`", bot.SYSTEM_PROMPT)
        self.assertIn("every five minutes", bot.SYSTEM_PROMPT)
        self.assertIn("does not listen to, record, or process incoming voice audio", bot.SYSTEM_PROMPT)
        self.assertIn("external `/say` web page", bot.SYSTEM_PROMPT)
        self.assertIn("Jamal crazy idek", bot.SYSTEM_PROMPT)
        self.assertIn("Evan crash", bot.SYSTEM_PROMPT)
        self.assertIn("normal AI reply does not itself execute", bot.SYSTEM_PROMPT)

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
        self.assertIn(b'name="action" value="stop"', response.data)
        self.assertIn(b"Stop audio", response.data)
        self.assertIn(b'name="action" value="leave"', response.data)
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
        self.assertIn(b'value="jamal">Jamal crazy idek</button>', response.data)
        self.assertIn(b'value="evan">Evan crash</button>', response.data)

    def test_page_has_text_to_speech_controls(self):
        response = self.client.get("/say")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Text to speech", response.data)
        self.assertIn(b'name="speech_text"', response.data)
        self.assertIn(b'name="voice"', response.data)
        self.assertIn(b'value="alloy"', response.data)
        self.assertIn(b'name="action" value="speak"', response.data)
        self.assertIn(f"up to {bot.TTS_TEXT_LIMIT} characters".encode(), response.data)

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
                "voice": "alloy",
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
                "voice": "alloy",
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
                    "voice": "nova",
                },
            )

        self.assertEqual(response.status_code, 303)
        self.assertIn("status=speaking+in+%23General", response.headers["Location"])
        submit_speech.assert_called_once_with(
            1447148315312521256, "hello there", "nova"
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
            play_audio.assert_called_once_with(voice_client, audio_path, delete_after=True)
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
        self.assertIn(b'class="upload-panel"', response.data)
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

    def test_authentication_is_required_when_control_token_is_enabled(self):
        with patch.object(bot, "EXTERNAL_SAY_CONTROL_TOKEN", "secret-token"):
            unauthorized = self.client.get("/say")
            authorized = self.client.get(
                "/say",
                headers={"Authorization": "Basic dXNlcjpzZWNyZXQtdG9rZW4="},
            )

        self.assertEqual(unauthorized.status_code, 401)
        self.assertIn("Basic", unauthorized.headers["WWW-Authenticate"])
        self.assertEqual(authorized.status_code, 200)


if __name__ == "__main__":
    unittest.main()
