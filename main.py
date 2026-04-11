from __future__ import annotations

import asyncio
import os
import signal

from motor.motor_asyncio import AsyncIOMotorClient
try:
    import uvloop
except Exception:
    uvloop = None

if uvloop is not None:
    uvloop.install()

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

from config import config
from plugins.fsub import (
    is_user_verified,
    premium_dashboard_markup,
    premium_fsub_markup,
    safe_call,
    start_menu,
)
from plugins.saver import INVITE_LINK_RE, Job, SaveWorker

# These are initialized inside main()
bot: Client | None = None
userbot: Client | None = None
mongo: AsyncIOMotorClient | None = None
db = None
users_col = None
save_worker: SaveWorker | None = None


async def add_user(user_id: int):
    await users_col.update_one({"_id": user_id}, {"$set": {"_id": user_id}}, upsert=True)


@Client.on_message(filters.command("start") & filters.private)
async def start_handler(_, message: Message):
    await add_user(message.from_user.id)

    if not await is_user_verified(bot, config.force_sub_id, message.from_user.id):
        await message.reply_text(
            "<b>Access Locked</b>\n<i>Join required channel, then verify access.</i>",
            reply_markup=premium_fsub_markup(config.force_sub_id),
        )
        return

    await start_menu(message, config.force_sub_id)


@Client.on_callback_query(filters.regex(r"^verify$"))
async def verify_handler(_, query):
    if await is_user_verified(bot, config.force_sub_id, query.from_user.id):
        await safe_call(
            query.message.edit_text(
                "<b>Verification complete ✅</b>\n<i>Dashboard unlocked.</i>",
                reply_markup=premium_dashboard_markup(config.force_sub_id),
            )
        )
        await query.answer("Access verified", show_alert=False)
    else:
        await query.answer("You still need to join the channel.", show_alert=True)


@Client.on_callback_query(filters.regex(r"^save_help$"))
async def save_help_handler(_, query):
    await query.answer("Send t.me/username/id or t.me/c/id/id link.", show_alert=True)


@Client.on_callback_query(filters.regex(r"^my_profile$"))
async def profile_handler(_, query):
    queued = save_worker.queue.qsize()
    await query.answer(f"Queue size: {queued}", show_alert=True)


@Client.on_callback_query(filters.regex(r"^clear_panel$"))
async def clear_panel_handler(_, query):
    await safe_call(query.message.edit_text("<b>Panel cleared.</b>\nUse /start to open again."))


@Client.on_message(filters.command("stats") & filters.private)
async def stats_handler(_, message: Message):
    if message.from_user.id != config.owner_id:
        return

    total_users = await users_col.count_documents({})
    queue_size = save_worker.queue.qsize()
    await message.reply_text(
        "<b>Bot Stats</b>\n"
        f"<code>Total users:</code> {total_users}\n"
        f"<code>Queue size:</code> {queue_size}"
    )


@Client.on_message(filters.command("clearqueue") & filters.private)
async def clear_queue_handler(_, message: Message):
    if message.from_user.id != config.owner_id:
        return

    removed = 0
    while not save_worker.queue.empty():
        try:
            save_worker.queue.get_nowait()
            save_worker.queue.task_done()
            removed += 1
        except asyncio.QueueEmpty:
            break

    await message.reply_text(f"<b>Queue cleared.</b> Removed: <code>{removed}</code>")


@Client.on_message(filters.command("broadcast") & filters.private)
async def broadcast_handler(_, message: Message):
    if message.from_user.id != config.owner_id:
        return

    payload = None
    if message.reply_to_message:
        payload = message.reply_to_message
    elif len(message.command) > 1:
        payload = " ".join(message.command[1:]).strip()

    if payload is None:
        await message.reply_text("Reply to a message with /broadcast OR use /broadcast your_text")
        return

    sent, failed = 0, 0
    async for user in users_col.find({}, {"_id": 1}):
        try:
            if isinstance(payload, str):
                result = await safe_call(bot.send_message(user["_id"], payload))
            else:
                result = await safe_call(payload.copy(user["_id"]))

            if result:
                sent += 1
            else:
                failed += 1
        except Exception:
            failed += 1

        if (sent + failed) % 25 == 0:
            await asyncio.sleep(1)

    await message.reply_text(
        f"<b>Broadcast done.</b>\nSent: <code>{sent}</code>\nFailed: <code>{failed}</code>"
    )


@Client.on_message(
    filters.private & filters.text & ~filters.command(["start", "stats", "broadcast", "clearqueue"])
)
async def inbox_handler(_, message: Message):
    user_id = message.from_user.id
    await add_user(user_id)

    if not await is_user_verified(bot, config.force_sub_id, user_id):
        await message.reply_text(
            "<b>Access denied</b>\nJoin channel and tap verify.",
            reply_markup=premium_fsub_markup(config.force_sub_id),
        )
        return

    text = (message.text or "").strip()

    if INVITE_LINK_RE.match(text):
        ok, info = await save_worker.requeue_after_invite(user_id, text)
        await message.reply_text(f"<code>{info}</code>")
        return

    parsed = save_worker.parse_link(text)
    if not parsed:
        await message.reply_text("Send a valid Telegram message link.")
        return

    queue_position = save_worker.queue.qsize() + 1
    status = await message.reply_text(
        "<b>RESTRICTED 🚫 MESSAGE SAVER 💾</b>\n"
        "<code>[▱▱▱▱▱▱▱▱▱▱] 0%</code>\n"
        f"<i>🕓 queued</i>\n<code>Queue position: {queue_position}</code>"
    )
    await save_worker.queue.put(
        Job(
            user_id=user_id,
            source_link=text,
            status_chat_id=status.chat.id,
            status_message_id=status.id,
        )
    )


async def main():
    global bot, userbot, mongo, db, users_col, save_worker

    bot = Client(
        "restricted_message_saver_bot",
        api_id=config.api_id,
        api_hash=config.api_hash,
        bot_token=config.bot_token,
        parse_mode=ParseMode.HTML,
    )

    userbot = None
    if config.string_session:
        userbot = Client(
            "restricted_message_saver_userbot",
            api_id=config.api_id,
            api_hash=config.api_hash,
            session_string=config.string_session,
        )

    mongo = AsyncIOMotorClient(config.mongo_url)
    db = mongo["restricted_message_saver"]
    users_col = db["users"]

    save_worker = SaveWorker(
        bot=bot,
        userbot=userbot,
        downloads_dir=config.downloads_dir,
        job_timeout=config.job_timeout,
        max_retries=config.max_retries,
    )

    await db.command("ping")

    await bot.start()
    if userbot is not None:
        await userbot.start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _trigger_shutdown():
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _trigger_shutdown)
        except NotImplementedError:
            pass

    workers = [
        asyncio.create_task(save_worker.run_worker(f"worker-{i + 1}"))
        for i in range(max(1, config.worker_count))
    ]

    try:
        print("Bot started.")
        await stop_event.wait()
    finally:
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

        if userbot is not None:
            await userbot.stop()
        await bot.stop()
        mongo.close()


if __name__ == "__main__":
    asyncio.run(main())
