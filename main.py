from __future__ import annotations

import asyncio
import signal
from contextlib import suppress

from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.handlers import CallbackQueryHandler, MessageHandler
from pyrogram.types import CallbackQuery, Message

from config import config
from plugins.fsub import (
    is_user_verified,
    premium_dashboard_markup,
    premium_fsub_markup,
    safe_call,
    start_menu,
)
from plugins.saver import INVITE_LINK_RE, Job, SaveWorker


async def main() -> None:
    bot = Client(
        "restricted_message_saver_bot",
        api_id=config.api_id,
        api_hash=config.api_hash,
        bot_token=config.bot_token,
        parse_mode=ParseMode.HTML,
    )

    userbot: Client | None = None
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

    async def add_user(user_id: int) -> None:
        await users_col.update_one({"_id": user_id}, {"$set": {"_id": user_id}}, upsert=True)

    async def start_handler(_: Client, message: Message) -> None:
        user = message.from_user
        if user is None:
            return
        await add_user(user.id)

        if not await is_user_verified(bot, config.force_sub_id, user.id):
            await message.reply_text(
                "<b>Access Locked</b>\n<i>Join required channel, then verify access.</i>",
                reply_markup=premium_fsub_markup(config.force_sub_id),
            )
            return

        await start_menu(message, config.force_sub_id)

    async def verify_handler(_: Client, query: CallbackQuery) -> None:
        user = query.from_user
        if user is None:
            await query.answer("Invalid user.", show_alert=True)
            return

        if await is_user_verified(bot, config.force_sub_id, user.id):
            if query.message is not None:
                await safe_call(
                    lambda: query.message.edit_text(
                        "<b>Verification complete ✅</b>\n<i>Dashboard unlocked.</i>",
                        reply_markup=premium_dashboard_markup(config.force_sub_id),
                    )
                )
            await query.answer("Access verified", show_alert=False)
        else:
            await query.answer("You still need to join the channel.", show_alert=True)

    async def save_help_handler(_: Client, query: CallbackQuery) -> None:
        await query.answer("Send t.me/username/id or t.me/c/id/id link.", show_alert=True)

    async def profile_handler(_: Client, query: CallbackQuery) -> None:
        queued = save_worker.queue.qsize()
        await query.answer(f"Queue size: {queued}", show_alert=True)

    async def clear_panel_handler(_: Client, query: CallbackQuery) -> None:
        if query.message is None:
            await query.answer("Nothing to clear.", show_alert=False)
            return
        await safe_call(lambda: query.message.edit_text("<b>Panel cleared.</b>\nUse /start to open again."))
        await query.answer("Panel cleared", show_alert=False)

    async def stats_handler(_: Client, message: Message) -> None:
        user = message.from_user
        if user is None or user.id != config.owner_id:
            return

        total_users = await users_col.count_documents({})
        queue_size = save_worker.queue.qsize()
        await message.reply_text(
            "<b>Bot Stats</b>\n"
            f"<code>Total users:</code> {total_users}\n"
            f"<code>Queue size:</code> {queue_size}"
        )

    async def clear_queue_handler(_: Client, message: Message) -> None:
        user = message.from_user
        if user is None or user.id != config.owner_id:
            return

        removed = 0
        while True:
            try:
                save_worker.queue.get_nowait()
                save_worker.queue.task_done()
                removed += 1
            except asyncio.QueueEmpty:
                break

        await message.reply_text(f"<b>Queue cleared.</b> Removed: <code>{removed}</code>")

    async def broadcast_handler(_: Client, message: Message) -> None:
        user = message.from_user
        if user is None or user.id != config.owner_id:
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
        async for doc in users_col.find({}, {"_id": 1}):
            try:
                if isinstance(payload, str):
                    result = await safe_call(lambda: bot.send_message(doc["_id"], payload))
                else:
                    result = await safe_call(lambda: payload.copy(doc["_id"]))

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

    async def inbox_handler(_: Client, message: Message) -> None:
        user = message.from_user
        if user is None:
            return

        user_id = user.id
        await add_user(user_id)

        if not await is_user_verified(bot, config.force_sub_id, user_id):
            await message.reply_text(
                "<b>Access denied</b>\nJoin channel and tap verify.",
                reply_markup=premium_fsub_markup(config.force_sub_id),
            )
            return

        text = (message.text or "").strip()

        if INVITE_LINK_RE.match(text):
            if user_id != config.owner_id:
                await message.reply_text("Private-channel backups are available only to the bot owner.")
                return
            _, info = await save_worker.requeue_after_invite(user_id, text)
            await message.reply_text(f"<code>{info}</code>")
            return

        parsed = save_worker.parse_link(text)
        if not parsed:
            await message.reply_text("Send a valid Telegram message link.")
            return

        if parsed.is_private and user_id != config.owner_id:
            await message.reply_text("Private-channel backups are available only to the bot owner.")
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

    # Register handlers only after clients/resources are created.
    bot.add_handler(MessageHandler(start_handler, filters.command("start") & filters.private))
    bot.add_handler(CallbackQueryHandler(verify_handler, filters.regex(r"^verify$")))
    bot.add_handler(CallbackQueryHandler(save_help_handler, filters.regex(r"^save_help$")))
    bot.add_handler(CallbackQueryHandler(profile_handler, filters.regex(r"^my_profile$")))
    bot.add_handler(CallbackQueryHandler(clear_panel_handler, filters.regex(r"^clear_panel$")))
    bot.add_handler(MessageHandler(stats_handler, filters.command("stats") & filters.private))
    bot.add_handler(MessageHandler(clear_queue_handler, filters.command("clearqueue") & filters.private))
    bot.add_handler(MessageHandler(broadcast_handler, filters.command("broadcast") & filters.private))
    bot.add_handler(
        MessageHandler(
            inbox_handler,
            filters.private
            & filters.text
            & ~filters.command(["start", "stats", "broadcast", "clearqueue"]),
        )
    )

    await db.command("ping")

    await bot.start()
    if userbot is not None:
        await userbot.start()

    stop_event = asyncio.Event()
    workers: list[asyncio.Task] = []

    def _trigger_shutdown() -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(sig, _trigger_shutdown)

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
