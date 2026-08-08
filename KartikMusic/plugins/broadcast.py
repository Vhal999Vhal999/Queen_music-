#
# Copyright (C) 2025-present by TheAloneTeam@Github, < https://github.com/TheAloneTeam >.
#

import asyncio
import os

from pyrogram import errors, filters, types

from KartikMusic import app, db, lang


broadcasting = asyncio.Lock()


@app.on_message(filters.command("broadcast") & app.sudoers)
@lang.language()
async def _broadcast(_, message: types.Message):

    # Broadcast must be a reply
    if not message.reply_to_message:
        return await message.reply_text(
            message.lang["gcast_usage"]
        )

    # Prevent multiple broadcasts
    if broadcasting.locked():
        return await message.reply_text(
            message.lang["gcast_active"]
        )

    msg = message.reply_to_message

    count = 0
    ucount = 0

    # Always get both groups and users
    groups = set(await db.get_chats())
    users = set(await db.get_users())

    chats = list(groups | users)

    failed = None

    sent = await message.reply_text(
        message.lang["gcast_start"]
    )

    async with broadcasting:

        for chat in chats:
            try:

                # -------------------------
                # TEXT
                # -------------------------
                if msg.text:
                    await app.send_message(
                        chat,
                        msg.text,
                        entities=msg.entities,
                        disable_web_page_preview=True,
                    )

                # -------------------------
                # PHOTO
                # -------------------------
                elif msg.photo:
                    await app.send_photo(
                        chat,
                        msg.photo.file_id,
                        caption=msg.caption,
                        caption_entities=msg.caption_entities,
                    )

                # -------------------------
                # VIDEO
                # -------------------------
                elif msg.video:
                    await app.send_video(
                        chat,
                        msg.video.file_id,
                        caption=msg.caption,
                        caption_entities=msg.caption_entities,
                    )

                # -------------------------
                # DOCUMENT
                # -------------------------
                elif msg.document:
                    await app.send_document(
                        chat,
                        msg.document.file_id,
                        caption=msg.caption,
                        caption_entities=msg.caption_entities,
                    )

                # -------------------------
                # AUDIO
                # -------------------------
                elif msg.audio:
                    await app.send_audio(
                        chat,
                        msg.audio.file_id,
                        caption=msg.caption,
                        caption_entities=msg.caption_entities,
                    )

                # -------------------------
                # VOICE
                # -------------------------
                elif msg.voice:
                    await app.send_voice(
                        chat,
                        msg.voice.file_id,
                        caption=msg.caption,
                        caption_entities=msg.caption_entities,
                    )

                # -------------------------
                # VIDEO NOTE
                # -------------------------
                elif msg.video_note:
                    await app.send_video_note(
                        chat,
                        msg.video_note.file_id,
                    )

                # -------------------------
                # ANIMATION / GIF
                # -------------------------
                elif msg.animation:
                    await app.send_animation(
                        chat,
                        msg.animation.file_id,
                        caption=msg.caption,
                        caption_entities=msg.caption_entities,
                    )

                # -------------------------
                # STICKER
                # -------------------------
                elif msg.sticker:
                    await app.send_sticker(
                        chat,
                        msg.sticker.file_id,
                    )

                # -------------------------
                # CONTACT
                # -------------------------
                elif msg.contact:
                    await app.send_contact(
                        chat,
                        phone_number=msg.contact.phone_number,
                        first_name=msg.contact.first_name,
                        last_name=msg.contact.last_name,
                        vcard=msg.contact.vcard,
                    )

                else:
                    continue

                # Count users/groups
                if chat in groups:
                    count += 1
                elif chat in users:
                    ucount += 1

                await asyncio.sleep(0.2)

            except errors.FloodWait as fw:
                await asyncio.sleep(fw.value + 5)

                try:
                    # Retry after FloodWait
                    if msg.text:
                        await app.send_message(
                            chat,
                            msg.text,
                            entities=msg.entities,
                            disable_web_page_preview=True,
                        )

                    elif msg.photo:
                        await app.send_photo(
                            chat,
                            msg.photo.file_id,
                            caption=msg.caption,
                            caption_entities=msg.caption_entities,
                        )

                    elif msg.video:
                        await app.send_video(
                            chat,
                            msg.video.file_id,
                            caption=msg.caption,
                            caption_entities=msg.caption_entities,
                        )

                    elif msg.document:
                        await app.send_document(
                            chat,
                            msg.document.file_id,
                            caption=msg.caption,
                            caption_entities=msg.caption_entities,
                        )

                    elif msg.audio:
                        await app.send_audio(
                            chat,
                            msg.audio.file_id,
                            caption=msg.caption,
                            caption_entities=msg.caption_entities,
                        )

                    elif msg.voice:
                        await app.send_voice(
                            chat,
                            msg.voice.file_id,
                            caption=msg.caption,
                            caption_entities=msg.caption_entities,
                        )

                    elif msg.animation:
                        await app.send_animation(
                            chat,
                            msg.animation.file_id,
                            caption=msg.caption,
                            caption_entities=msg.caption_entities,
                        )

                    elif msg.sticker:
                        await app.send_sticker(
                            chat,
                            msg.sticker.file_id,
                        )

                    if chat in groups:
                        count += 1
                    elif chat in users:
                        ucount += 1

                except Exception as ex:
                    if not failed:
                        failed = open("errors.txt", "w")

                    failed.write(f"{chat} - {ex}\n")

            except Exception as ex:

                if not failed:
                    failed = open("errors.txt", "w")

                failed.write(f"{chat} - {ex}\n")

    # -------------------------
    # BROADCAST RESULT
    # -------------------------

    text = message.lang["gcast_end"].format(
        count,
        ucount,
    )

    if failed:
        failed.close()

        await message.reply_document(
            document="errors.txt",
            caption=text,
        )

        try:
            os.remove("errors.txt")
        except Exception:
            pass

    await sent.edit_text(text)
