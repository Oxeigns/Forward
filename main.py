from __future__ import annotations

import asyncio

from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters
from pyrogram.types import Message

from config import config
from plugins.fsub import is_user_verified, premium_dashboard_markup, premium_fsub_markup, safe_call
from plugins.saver import Job, SaveWorker

try:
    import uvloop
except Exception:  # pragma: no cover
    uvloop = None

bot = Client(
    "forward_saver_bot",
    api_id=config.api_id,
    api_hash=config.api_hash,
    bot_token=config.bot_token,
)

userbot = None
if config.string_session:
    userbot = Client(
        "forward_saver_userbot",
        api_id=config.api_id,
        api_hash=config.api_hash,
        session_string=config.string_session,
    )

mongo = AsyncIOMotorClient(config.mongo_url)
db = mongo["forward_saver"]
users_col = db["users"]

save_worker = SaveWorker(bot=bot, userbot=userbot, downloads_dir=config.downloads_dir)


async def add_user(user_id: int):
    await users_col.update_one({"_id": user_id}, {"$set": {"_id": user_id}}, upsert=True)


@bot.on_message(filters.command("start") & filters.private)
async def start_handler(_, message: Message):
    await add_user(message.from_user.id)

    if not await is_user_verified(bot, config.force_sub_id, message.from_user.id):
        await message.reply_text(
            "`[ ACCESS REQUIRED ] Join updates channel, then verify.`",
            reply_markup=premium_fsub_markup(config.force_sub_id),
            disable_web_page_preview=True,
        )
        return

    await message.reply_text(
        "`[ READY ] Send a Telegram post link to save content to DM.`",
        reply_markup=premium_dashboard_markup(),
    )


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


@bot.on_callback_query(filters.regex("^save_help$"))
async def save_help_callback(_, query):
    await query.answer("Send any Telegram message link.", show_alert=True)


@bot.on_callback_query(filters.regex("^my_profile$"))
async def profile_callback(_, query):
    pending_count = save_worker.queue.qsize()
    await query.answer(f"Queued jobs: {pending_count}", show_alert=True)


@bot.on_message(filters.private & filters.text & ~filters.command(["start", "stats", "broadcast"]))
async def save_incoming(_, message: Message):
    user_id = message.from_user.id
    if not await is_user_verified(bot, config.force_sub_id, user_id):
        await message.reply_text(
            "`[ ACCESS DENIED ] Join channel and verify.`",
            reply_markup=premium_fsub_markup(config.force_sub_id),
        )
        return

    if not save_worker.parse_link(message.text or ""):
        await message.reply_text("`[ ERROR ] Send a valid Telegram post link (t.me/.../...).`")
        return

    status = await message.reply_text("`[ QUEUED ]`\n`▱▱▱▱▱▱▱▱▱▱ [0%]`")
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
        "`[ BOT STATS ]`\n"
        f"`users: {total_users}`\n"
        f"`queued_jobs: {queue_count}`"
    )


@bot.on_message(filters.command("clearqueue") & filters.private)
async def clear_queue_handler(_, message: Message):
    if message.from_user.id != config.owner_id:
        return

    cleared = 0
    while not save_worker.queue.empty():
        try:
            save_worker.queue.get_nowait()
            save_worker.queue.task_done()
            cleared += 1
        except asyncio.QueueEmpty:
            break

    await message.reply_text(f"`[ QUEUE CLEARED ] removed={cleared}`")


@bot.on_message(filters.command("broadcast") & filters.private)
async def broadcast_handler(_, message: Message):
    if message.from_user.id != config.owner_id:
        return

    if not message.reply_to_message:
        await message.reply_text("`[ ERROR ] Reply to any message with /broadcast.`")
        return

    sent = 0
    failed = 0
    async for user in users_col.find({}, {"_id": 1}):
        try:
            await safe_call(message.reply_to_message.copy(user["_id"]))
            sent += 1
        except Exception:
            failed += 1
        if (sent + failed) % 25 == 0:
            await asyncio.sleep(1)

    await message.reply_text(f"`[ BROADCAST ] sent={sent} failed={failed}`")


async def main():
    if uvloop is not None:
        uvloop.install()

    await bot.start()
    if userbot is not None:
        await userbot.start()

    for _ in range(max(1, config.worker_count)):
        asyncio.create_task(save_worker.run())
    print("Bot started.")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
