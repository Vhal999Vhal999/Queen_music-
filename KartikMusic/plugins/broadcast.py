# -----------------------------------------------
# Broadcast Module
# Direct Text Broadcast
# -----------------------------------------------

import asyncio
import os

from pyrogram import errors, filters, types

from KartikMusic import app, db, lang


broadcasting = asyncio.Lock()


@app.on_message(filters.command("broadcast") & app.sudoers)
@lang.language()
async def _broadcast(_, message: types.Message):

    # -------------------------------------------
    # Get broadcast text from /broadcast <text>
    # -------------------------------------------
    if len(message.command) < 2:
        return await message.reply_text(
            "❌ <b>Usage:</b>\n\n"
            "<code>/broadcast Your message here</code>"
        )

    broadcast_text = message.text.split(None, 1)[1].strip()

    if not broadcast_text:
        return await message.reply_text(
            "❌ <b>Please enter a broadcast message.</b>\n\n"
            "<code>/broadcast Your message here</code>"
        )

    # -------------------------------------------
    # Prevent multiple broadcasts
    # -------------------------------------------
    if broadcasting.locked():
        return await message.reply_text(
            message.lang["gcast_active"]
        )

    # -------------------------------------------
    # Get users and groups
    # -------------------------------------------
    groups = set(await db.get_chats())
    users = set(await db.get_users())

    chats = list(groups | users)

    count = 0
    ucount = 0
    failed = None

    sent = await message.reply_text(
        message.lang["gcast_start"]
    )

    # -------------------------------------------
    # Start broadcast
    # -------------------------------------------
    async with broadcasting:

        for chat in chats:
            try:
                await app.send_message(
                    chat_id=chat,
                    text=broadcast_text,
                    disable_web_page_preview=True,
                )

                # Count groups/users
                if chat in groups:
                    count += 1
                elif chat in users:
                    ucount += 1

                # Small delay to reduce FloodWait
                await asyncio.sleep(0.2)

            # -----------------------------------
            # FloodWait
            # -----------------------------------
            except errors.FloodWait as fw:

                await asyncio.sleep(fw.value + 5)

                try:
                    await app.send_message(
                        chat_id=chat,
                        text=broadcast_text,
                        disable_web_page_preview=True,
                    )

                    if chat in groups:
                        count += 1
                    elif chat in users:
                        ucount += 1

                except Exception as ex:

                    if not failed:
                        failed = open(
                            "errors.txt",
                            "w",
                            encoding="utf-8"
                        )

                    failed.write(
                        f"{chat} - {ex}\n"
                    )

            # -----------------------------------
            # Other errors
            # -----------------------------------
            except Exception as ex:

                if not failed:
                    failed = open(
                        "errors.txt",
                        "w",
                        encoding="utf-8"
                    )

                failed.write(
                    f"{chat} - {ex}\n"
                )

    # -------------------------------------------
    # Broadcast result
    # -------------------------------------------
    text = message.lang["gcast_end"].format(
        count,
        ucount,
    )

    # -------------------------------------------
    # Send error file if any
    # -------------------------------------------
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

    # -------------------------------------------
    # Update broadcast status
    # -------------------------------------------
    await sent.edit_text(text)
