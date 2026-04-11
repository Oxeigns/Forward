from __future__ import annotations

import asyncio
import os
import signal

from motor.motor_asyncio import AsyncIOMotorClient

# Disable Pyrogram sync BEFORE import
os.environ["PYROGRAM_DISABLE_SYNC"] = "1"

from pyrogram import Client, filters
from pyrogram.types import Message

from config import config
from plugins.fsub import (
    is_user_verified,
    premium_dashboard_markup,
    premium_fsub_markup,
    safe_call,
    start_menu,
)
from plugins.saver import Job, SaveWorker

try:
    import uvloop
except Exception:
    uvloop = None


# ------------------ CLIENTS ------------------ #
bot = Client(
    "forward_saver_bot",
    api_id=config.api_id,
    api_hash=config.api_hash,
    bot_token=config.bot_token,
)

userbot = None
if config.string_session:
    try:
        userbot = Client(
            "forward_saver_userbot",
            api_id=config.api_id,
            api_hash=config.api_hash,
            session_string=config.string_session,
        )
    except Exception as e:
        print(f"[USERBOT ERROR] {e}")
        userbot = None


# ------------------ DB ------------------ #
mongo = AsyncIOMotorClient(config.mongo_url)
db = mongo["forward_saver"]
users_col = db["users"]


# ------------------ WORKER ------------------ #
save_worker = SaveWorker(
    bot=bot,
    userbot=userbot,
    downloads_dir=config.downloads_dir,
)


async def worker_loop():
    """Safe worker loop (auto-restart on crash)"""
    while True:
        try:
            await save_worker.run()
        except Exception as e:
            print(f"[WORKER CRASH] {e}")
            await asyncio.sleep(2)


# ------------------ HELPERS ------------------ #
async def add_user(user_id: int):
    await users_col.update_one(
        {"_id": user_id},
        {"$set": {"_id": user_id}},
        upsert=True,
    )


# ------------------ HANDLERS ------------------ #
@bot.on_message(filters.command("start") & filters.private)
async def start_handler(_, message: Message):
    await add_user(message.from_user.id)

    if not await is_user_verified(bot, config.force_sub_id, message.from_user.id):
        return await message.reply_text(
            "`[ ACCESS REQUIRED ] Join channel, then verify.`",
            reply_markup=premium_fsub_markup(config.force_sub_id),
        )

    await message.reply_text(
        "<b>Mode Switch</b>\n<i>Loading dashboard...</i>"
    )
    await start_menu(message, config.force_sub_id)


@bot.on_callback_query(filters.regex("^verify$"))
async def verify_callback(_, query):
    if await is_user_verified(bot, config.force_sub_id, query.from_user.id):
        await safe_call(
            query.message.edit_text(
                "`[ VERIFIED ] Access granted.`",
                reply_markup=premium_dashboard_markup(),
            )
        )
    else:
        await query.answer("Join channel first.", show_alert=True)


@bot.on_message(filters.private & filters.text & ~filters.command(["start", "stats", "broadcast"]))
async def save_incoming(_, message: Message):
    user_id = message.from_user.id

    if not await is_user_verified(bot, config.force_sub_id, user_id):
        return await message.reply_text(
            "`[ ACCESS DENIED ] Join & verify.`",
            reply_markup=premium_fsub_markup(config.force_sub_id),
        )

    if not save_worker.parse_link(message.text or ""):
        return await message.reply_text(
            "`[ ERROR ] Send valid Telegram link.`"
        )

    status = await message.reply_text(
        "`[ QUEUED ]`\n▱▱▱▱▱▱▱▱▱▱ 0%"
    )

    await save_worker.queue.put(
        Job(
            user_id=user_id,
            source_link=message.text.strip(),
            status_chat_id=status.chat.id,
            status_message_id=status.id,
        )
    )


@bot.on_message(filters.command("stats") & filters.private)
async def stats_handler(_, message: Message):
    if message.from_user.id != config.owner_id:
        return

    total_users = await users_col.count_documents({})
    queue_count = save_worker.queue.qsize()

    await message.reply_text(
        f"`users: {total_users}`\n"
        f"`queued: {queue_count}`"
    )


# ------------------ MAIN ------------------ #
async def main():
    if uvloop:
        uvloop.install()

    await bot.start()

    if userbot:
        await userbot.start()

    # start workers
    for _ in range(max(1, config.worker_count)):
        asyncio.create_task(worker_loop())

    print("Bot started.")

    # graceful shutdown
    stop_event = asyncio.Event()

    def shutdown():
        print("Stopping bot...")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown)

    await stop_event.wait()

    await bot.stop()
    if userbot:
        await userbot.stop()
    mongo.close()


if __name__ == "__main__":
    asyncio.run(main())
