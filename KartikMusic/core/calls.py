#
# Copyright (C) 2025-present by TheAloneTeam@Github
#

import asyncio
import time
from collections import defaultdict

from ntgcalls import (
    ConnectionError,
    ConnectionNotFound,
    RTMPStreamingUnsupported,
    TelegramServerError,
)

from pyrogram.types import InputMediaPhoto, Message

from pytgcalls import (
    PyTgCalls,
    exceptions,
    types,
)

from pytgcalls.pytgcalls_session import (
    PyTgCallsSession,
)

from KartikMusic import (
    app,
    config,
    db,
    lang,
    logger,
    queue,
    thumb,
    userbot,
    yt,
)

from KartikMusic.helpers import (
    Media,
    Track,
    buttons,
)


class TgCall(PyTgCalls):

    def __init__(self):

        self.clients = []

        self.restarting = defaultdict(int)

        self.prefetch_tasks = {}

        self._play_locks = {}

    # =====================================================
    # PAUSE
    # =====================================================

    async def pause(
        self,
        chat_id: int,
    ) -> bool:

        client = await db.get_assistant(
            chat_id
        )

        await db.playing(
            chat_id,
            paused=True,
        )

        media = queue.get_current(
            chat_id
        )

        if media and media.played_at:

            media.time += int(
                time.time()
                - media.played_at
            )

            media.played_at = None

        return await client.pause(
            chat_id
        )

    # =====================================================
    # RESUME
    # =====================================================

    async def resume(
        self,
        chat_id: int,
    ) -> bool:

        client = await db.get_assistant(
            chat_id
        )

        await db.playing(
            chat_id,
            paused=False,
        )

        media = queue.get_current(
            chat_id
        )

        if media:

            media.played_at = time.time()

        return await client.resume(
            chat_id
        )

    # =====================================================
    # PREPARE NEXT
    # =====================================================

    async def _prepare_next(
        self,
        chat_id: int,
    ):

        try:

            while await db.get_call(
                chat_id
            ):

                if not await db.get_autoplay(
                    chat_id
                ):

                    await asyncio.sleep(8)
                    continue

                current = queue.get_current(
                    chat_id
                )

                if not current:
                    break

                played = current.time or 0

                if current.played_at:

                    played += int(
                        time.time()
                        - current.played_at
                    )

                duration = (
                    current.duration_sec
                    or 0
                )

                if not duration:
                    await asyncio.sleep(5)
                    continue

                remaining = (
                    duration - played
                )

                # Prepare around 30 sec before end
                if remaining <= 30:

                    next_media = queue.get_next(
                        chat_id,
                        check=True,
                    )

                    if (
                        not next_media
                        and isinstance(
                            current,
                            Track,
                        )
                        and await db.get_autoplay(
                            chat_id
                        )
                    ):

                        max_duration = min(
                            int(
                                current.duration_sec
                                * 1.5
                            ),
                            900,
                        )

                        try:

                            next_media = (
                                await yt.get_related(
                                    current.id,
                                    video=current.video,
                                    max_duration=max_duration,
                                )
                            )

                        except Exception as e:

                            logger.error(
                                "Autoplay error: %s",
                                e,
                            )

                            next_media = None

                        if next_media:

                            queue.add(
                                chat_id,
                                next_media,
                            )

                    # -------------------------------------
                    # FAST PREFETCH
                    # -------------------------------------

                    if (
                        next_media
                        and not next_media.file_path
                    ):

                        try:

                            next_media.file_path = (
                                await yt.download(
                                    next_media.id,
                                    video=next_media.video,
                                )
                            )

                        except Exception as e:

                            logger.warning(
                                "Next prefetch failed: %s",
                                e,
                            )

                    break

                await asyncio.sleep(5)

        except asyncio.CancelledError:
            pass

        except Exception as e:

            logger.error(
                "Prepare-next error: %s",
                e,
            )

        finally:

            self.prefetch_tasks.pop(
                chat_id,
                None,
            )

    # =====================================================
    # STOP
    # =====================================================

    async def stop(
        self,
        chat_id: int,
    ):

        task = self.prefetch_tasks.pop(
            chat_id,
            None,
        )

        if task:

            task.cancel()

        client = await db.get_assistant(
            chat_id
        )

        media = queue.get_current(
            chat_id
        )

        if (
            media
            and media.message_id
        ):

            try:

                await app.delete_messages(
                    chat_id,
                    media.message_id,
                )

            except Exception:
                pass

        queue.clear(
            chat_id
        )

        await db.remove_call(
            chat_id
        )

        await db.set_loop(
            chat_id,
            0,
        )

        try:

            await client.leave_call(
                chat_id,
                close=False,
            )

        except Exception:
            pass

    # =====================================================
    # PLAY MEDIA
    # =====================================================

    async def play_media(
        self,
        chat_id: int,
        message: Message,
        media: Media | Track,
        seek_time: int = 0,
    ):

        # Cancel old prefetch task
        task = self.prefetch_tasks.pop(
            chat_id,
            None,
        )

        if task:
            task.cancel()

        self.restarting[
            chat_id
        ] += 1

        client = await db.get_assistant(
            chat_id
        )

        _lang = await lang.get_lang(
            chat_id
        )

        _thumb_mode = await db.get_thumb_mode(
            chat_id
        )

        # =================================================
        # THUMB
        # =================================================

        _thumb = None

        if (
            config.THUMB_GEN
            and _thumb_mode
        ):

            try:

                if isinstance(
                    media,
                    Track,
                ):

                    _thumb = await thumb.generate(
                        media
                    )

                else:

                    _thumb = config.DEFAULT_THUMB

            except Exception:

                _thumb = None

        # =================================================
        # SOURCE CHECK
        # =================================================

        source = media.file_path

        if not source:

            try:

                source = await yt.download(
                    media.id,
                    video=media.video,
                )

                media.file_path = source

            except Exception as e:

                logger.error(
                    "Download source error: %s",
                    e,
                )

                source = None

        if not source:

            try:

                await message.edit_text(
                    _lang[
                        "error_no_file"
                    ].format(
                        config.SUPPORT_CHAT
                    )
                )

            except Exception:
                pass

            return await self.play_next(
                chat_id
            )

        # =================================================
        # FFMPEG
        # =================================================

        ffmpeg_parts = []

        # -re is needed for real-time playback.
        ffmpeg_parts.append(
            "-re"
        )

        if seek_time > 1:

            ffmpeg_parts.extend(
                [
                    "-ss",
                    str(seek_time),
                ]
            )

        if not media.video:

            ffmpeg_parts.append(
                "-vn"
            )

        ffmpeg_params = " ".join(
            ffmpeg_parts
        )

        # =================================================
        # MEDIA STREAM
        # =================================================

        stream = types.MediaStream(
            media_path=source,

            audio_parameters=(
                types.AudioQuality.HIGH
            ),

            video_parameters=(
                types.VideoQuality.HD_720p
            ),

            audio_flags=(
                types.MediaStream.Flags.REQUIRED
            ),

            video_flags=(
                types.MediaStream.Flags.AUTO_DETECT
                if media.video
                else types.MediaStream.Flags.IGNORE
            ),

            ffmpeg_parameters=(
                ffmpeg_params
                if ffmpeg_params
                else None
            ),
        )

        try:

            # =================================================
            # PLAY IMMEDIATELY
            # =================================================

            await client.play(
                chat_id,
                stream,
            )

            # IMPORTANT:
            # Removed old fixed 2-second sleep.
            # We update state immediately.

            media.played_at = time.time()

            if seek_time:

                media.time = seek_time

            else:

                media.time = 0

                await db.add_call(
                    chat_id
                )

                text = _lang[
                    "play_media"
                ].format(
                    media.url,
                    media.title,
                    media.duration,
                    media.user,
                )

                keyboard = buttons.controls(
                    chat_id,
                    lang=_lang,
                )

                try:

                    if _thumb:

                        await message.edit_media(
                            media=InputMediaPhoto(
                                media=_thumb,
                                caption=text,
                            ),
                            reply_markup=keyboard,
                        )

                    else:

                        await message.edit_text(
                            text,
                            reply_markup=keyboard,
                        )

                except Exception:

                    try:

                        await message.delete()

                    except Exception:
                        pass

                    try:

                        if _thumb:

                            sent = await app.send_photo(
                                chat_id=chat_id,
                                photo=_thumb,
                                caption=text,
                                reply_markup=keyboard,
                            )

                        else:

                            sent = await app.send_message(
                                chat_id=chat_id,
                                text=text,
                                reply_markup=keyboard,
                            )

                        media.message_id = sent.id

                    except Exception as e:

                        logger.warning(
                            "Now-playing message error: %s",
                            e,
                        )

            # =================================================
            # BACKGROUND NEXT-PREFETCH
            # =================================================

            self.prefetch_tasks[
                chat_id
            ] = asyncio.create_task(
                self._prepare_next(
                    chat_id
                )
            )

        except FileNotFoundError:

            try:

                await message.edit_text(
                    _lang[
                        "error_no_file"
                    ].format(
                        config.SUPPORT_CHAT
                    )
                )

            except Exception:
                pass

            await self.play_next(
                chat_id
            )

        except exceptions.NoActiveGroupCall:

            await self.stop(
                chat_id
            )

            try:

                await message.edit_text(
                    _lang[
                        "error_no_call"
                    ]
                )

            except Exception:
                pass

        except exceptions.NoAudioSourceFound:

            try:

                await message.edit_text(
                    _lang[
                        "error_no_audio"
                    ]
                )

            except Exception:
                pass

            await self.play_next(
                chat_id
            )

        except (
            asyncio.TimeoutError,
            TimeoutError,
        ):

            try:

                await message.edit_text(
                    _lang[
                        "error_tg_server"
                    ]
                )

            except Exception:
                pass

            await self.play_next(
                chat_id
            )

        except (
            ConnectionError,
            ConnectionNotFound,
            TelegramServerError,
        ):

            await self.stop(
                chat_id
            )

            try:

                await message.edit_text(
                    _lang[
                        "error_tg_server"
                    ]
                )

            except Exception:
                pass

        except RTMPStreamingUnsupported:

            await self.stop(
                chat_id
            )

            try:

                await message.edit_text(
                    _lang[
                        "error_rtmp"
                    ]
                )

            except Exception:
                pass

        except Exception as e:

            logger.exception(
                "play_media failed for %s: %s",
                chat_id,
                e,
            )

            try:

                await message.edit_text(
                    _lang[
                        "error_tg_server"
                    ]
                )

            except Exception:
                pass

            await self.play_next(
                chat_id
            )

        finally:

            self.restarting[
                chat_id
            ] -= 1

            if (
                self.restarting[
                    chat_id
                ] <= 0
            ):

                self.restarting.pop(
                    chat_id,
                    None,
                )

    # =====================================================
    # REPLAY
    # =====================================================

    async def replay(
        self,
        chat_id: int,
    ):

        if not await db.get_call(
            chat_id
        ):
            return

        media = queue.get_current(
            chat_id
        )

        if (
            media
            and media.message_id
        ):

            try:

                await app.delete_messages(
                    chat_id,
                    media.message_id,
                )

            except Exception:
                pass

        _lang = await lang.get_lang(
            chat_id
        )

        msg = await app.send_message(
            chat_id=chat_id,
            text=_lang[
                "play_again"
            ],
        )

        media.message_id = msg.id

        await self.play_media(
            chat_id,
            msg,
            media,
        )

    # =====================================================
    # PLAY NEXT
    # =====================================================

    async def play_next(
        self,
        chat_id: int,
        skip_user: str | None = None,
    ):

        # =================================================
        # LOOP
        # =================================================

        loop = await db.get_loop(
            chat_id
        )

        if loop:

            await db.set_loop(
                chat_id,
                loop - 1,
            )

            return await self.replay(
                chat_id
            )

        _lang = await lang.get_lang(
            chat_id
        )

        current = queue.get_current(
            chat_id
        )

        # =================================================
        # DELETE OLD MESSAGE
        # =================================================

        if (
            current
            and current.message_id
        ):

            try:

                await app.delete_messages(
                    chat_id,
                    current.message_id,
                )

            except Exception:
                pass

        # =================================================
        # GET NEXT
        # =================================================

        media = queue.get_next(
            chat_id
        )

        # =================================================
        # QUEUE EMPTY
        # =================================================

        if not media:

            if (
                await db.get_autoplay(
                    chat_id
                )
                and current
                and isinstance(
                    current,
                    Track,
                )
            ):

                # -----------------------------------------
                # AUTOPLAY MESSAGE
                # -----------------------------------------

                if skip_user:

                    msg = await app.send_message(
                        chat_id,
                        _lang[
                            "autoplay_skip"
                        ].format(
                            skip_user
                        ),
                    )

                else:

                    msg = await app.send_message(
                        chat_id,
                        _lang[
                            "autoplay_next"
                        ],
                    )

                # -----------------------------------------
                # GET RELATED
                # -----------------------------------------

                max_duration = min(
                    int(
                        current.duration_sec
                        * 1.5
                    ),
                    900,
                )

                try:

                    media = await yt.get_related(
                        current.id,
                        video=current.video,
                        max_duration=max_duration,
                    )

                except Exception as e:

                    logger.error(
                        "Autoplay fetch error: %s",
                        e,
                    )

                    media = None

                # -----------------------------------------
                # ADD QUEUE
                # -----------------------------------------

                if media:

                    queue.add(
                        chat_id,
                        media,
                    )

                    # get the actual queue object
                    media = queue.get_current(
                        chat_id
                    )

                # -----------------------------------------
                # FAILED
                # -----------------------------------------

                if not media:

                    await self.stop(
                        chat_id
                    )

                    try:

                        return await msg.edit_text(
                            _lang[
                                "queue_finished"
                            ]
                        )

                    except Exception:

                        return

                # -----------------------------------------
                # FAST SOURCE
                # -----------------------------------------

                if not media.file_path:

                    media.file_path = (
                        await yt.download(
                            media.id,
                            video=media.video,
                        )
                    )

                if not media.file_path:

                    try:

                        return await msg.edit_text(
                            _lang[
                                "error_no_file"
                            ].format(
                                config.SUPPORT_CHAT
                            )
                        )

                    except Exception:

                        return

                media.message_id = msg.id

                return await self.play_media(
                    chat_id,
                    msg,
                    media,
                )

            # =================================================
            # NO AUTOPLAY
            # =================================================

            await self.stop(
                chat_id
            )

            if skip_user:

                await app.send_message(
                    chat_id,
                    _lang[
                        "play_skipped"
                    ].format(
                        skip_user
                    ),
                )

            return await app.send_message(
                chat_id,
                _lang[
                    "queue_finished"
                ],
            )

        # =================================================
        # NORMAL NEXT TRACK
        # =================================================

        msg = None

        if media.message_id:

            try:

                msg = await app.get_messages(
                    chat_id,
                    media.message_id,
                )

            except Exception:

                msg = None

        # =================================================
        # MESSAGE
        # =================================================

        text = (
            (
                _lang[
                    "play_skipped"
                ].format(
                    skip_user
                )
                + "\n\n"
                + _lang[
                    "play_next"
                ]
            )
            if skip_user
            else _lang[
                "play_next"
            ]
        )

        if msg:

            try:

                await msg.edit_text(
                    text
                )

            except Exception:
                pass

        else:

            msg = await app.send_message(
                chat_id=chat_id,
                text=text,
            )

        # =================================================
        # SOURCE
        # =================================================

        if not media.file_path:

            try:

                media.file_path = (
                    await yt.download(
                        media.id,
                        video=media.video,
                    )
                )

            except Exception as e:

                logger.error(
                    "Next download failed: %s",
                    e,
                )

                media.file_path = None

        # =================================================
        # FAILED
        # =================================================

        if not media.file_path:

            try:

                await msg.edit_text(
                    _lang[
                        "error_no_file"
                    ].format(
                        config.SUPPORT_CHAT
                    )
                )

            except Exception:
                pass

            return await self.play_next(
                chat_id
            )

        media.message_id = msg.id

        return await self.play_media(
            chat_id,
            msg,
            media,
        )

    # =====================================================
    # PING
    # =====================================================

    async def ping(self) -> float:

        if not self.clients:
            return 0.0

        pings = [
            client.ping
            for client in self.clients
        ]

        return round(
            sum(pings)
            / len(pings),
            2,
        )

    # =====================================================
    # DELETE MESSAGE
    # =====================================================

    async def _delete_msg(
        self,
        message: Message,
        delay: int = 2,
    ):

        await asyncio.sleep(
            delay
        )

        try:

            await message.delete()

        except Exception:
            pass

    # =====================================================
    # DECORATORS
    # =====================================================

    async def decorators(
        self,
        client: PyTgCalls,
    ):

        @client.on_update()
        async def update_handler(
            _,
            update: types.Update,
        ):

            # =============================================
            # VC PARTICIPANT
            # =============================================

            if isinstance(
                update,
                types.UpdatedGroupCallParticipant,
            ):

                if not await db.get_vclogger(
                    update.chat_id
                ):
                    return

                try:

                    user = await app.get_users(
                        update.participant.user_id
                    )

                except Exception:

                    return

                _lang = await lang.get_lang(
                    update.chat_id
                )

                if (
                    update.action
                    == types.UpdatedGroupCallParticipant.Action.JOINED
                ):

                    text = _lang[
                        "vclog_joined"
                    ].format(
                        user.mention,
                        user.id,
                    )

                elif (
                    update.action
                    == types.UpdatedGroupCallParticipant.Action.LEFT
                ):

                    text = _lang[
                        "vclog_left"
                    ].format(
                        user.mention,
                        user.id,
                    )

                else:

                    return

                try:

                    sent = await app.send_message(
                        update.chat_id,
                        text,
                    )

                    asyncio.create_task(
                        self._delete_msg(
                            sent
                        )
                    )

                except Exception:
                    pass

            # =============================================
            # STREAM ENDED
            # =============================================

            elif isinstance(
                update,
                types.StreamEnded,
            ):

                if (
                    update.stream_type
                    == types.StreamEnded.Type.AUDIO
                ):

                    if self.restarting.get(
                        update.chat_id
                    ):

                        return

                    await self.play_next(
                        update.chat_id
                    )

            # =============================================
            # CHAT UPDATE
            # =============================================

            elif isinstance(
                update,
                types.ChatUpdate,
            ):

                if update.status in [
                    types.ChatUpdate.Status.KICKED,
                    types.ChatUpdate.Status.LEFT_GROUP,
                    types.ChatUpdate.Status.CLOSED_VOICE_CHAT,
                ]:

                    await self.stop(
                        update.chat_id
                    )

    # =====================================================
    # BOOT
    # =====================================================

    async def boot(self):

        PyTgCallsSession.notice_displayed = True

        for ub in userbot.clients:

            client = PyTgCalls(
                ub,
                cache_duration=100,
            )

            await client.start()

            self.clients.append(
                client
            )

            await self.decorators(
                client
            )

        logger.info(
            "PyTgCalls client(s) started."
                    )
