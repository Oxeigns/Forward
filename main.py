import asyncio
import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple

from motor.motor_asyncio import AsyncIOMotorClient
from pyrogram import Client, filters
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import (
    FloodWait,
    InviteHashExpired,
    InviteHashInvalid,
    UserAlreadyParticipant,
    UserNotParticipant,
)
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import config

TME_REGEX = re.compile(r"https?://t\.me/(?:c/(\d+)/(\d+)|([A-Za-z0-9_]{4,})/(\d+))")
INVITE_REGEX = re.compile(r"https?://t\.me/(?:\+|joinchat/).+")

bot = Client(
    "restricted_saver_bot",
    api_id=config.api_id,
    api_hash=config.api_hash,
    bot_token=config.bot_token,
)

userbot = Client(
    "restricted_saver_userbot",
    api_id=config.api_id,
    api_hash=config.api_hash,
    session_string=config.string_session or None,
)

mongo = AsyncIOMotorClient(config.mongo_url)
db = mongo["restricted_saver"]
users_col = db["users"]
stats_col = db["stats"]


@dataclass
class Job:
    user_id: int
    source_link: str
    progress_chat_id: int
    progress_message_id: int


work_queue: asyncio.Queue[Job] = asyncio.Queue()
pending_join: dict[int, Job] = {}


def dashboard_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔗 Save Restricted Link", callback_data="help_save")],
            [InlineKeyboardButton("⚡ Queue Status", callback_data="queue_status")],
            [InlineKeyboardButton("🛡️ Force Sub Verified", callback_data="fsub_ok")],
        ]
    )


def fsub_markup() -> InlineKeyboardMarkup:
    channel = config.fsub_id if str(config.fsub_id).startswith("@") else f"@{config.fsub_id}"
    url = f"https://t.me/{channel.lstrip('@')}"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📢 Join Channel", url=url)],
            [InlineKeyboardButton("✅ Verify", callback_data="verify_fsub")],
        ]
    )


async def safe_call(coro):
    while True:
        try:
            return await coro
        except FloodWait as e:
            await asyncio.sleep(e.value)


async def ensure_user(chat_id: int) -> None:
    await users_col.update_one({"_id": chat_id}, {"$set": {"_id": chat_id}}, upsert=True)


async def increment_stat(key: str, amount: int = 1) -> None:
    await stats_col.update_one({"_id": "global"}, {"$inc": {key: amount}}, upsert=True)


async def get_counts() -> Tuple[int, int]:
    total_users = await users_col.count_documents({})
    stats = await stats_col.find_one({"_id": "global"}) or {}
    total_files = stats.get("files_saved", 0)
    return total_users, total_files


async def check_force_sub(user_id: int) -> bool:
    member = await safe_call(bot.get_chat_member(config.fsub_id, user_id))
    return member.status not in {ChatMemberStatus.LEFT, ChatMemberStatus.BANNED}


def parse_link(link: str) -> Optional[Tuple[str, str, int]]:
    m = TME_REGEX.search(link)
    if not m:
        return None
    if m.group(1) and m.group(2):
        chat_id = int(f"-100{m.group(1)}")
        return "private", str(chat_id), int(m.group(2))
    return "public", m.group(3), int(m.group(4))


async def update_progress(message: Message, percent: int, note: str) -> None:
    bar = "█" * (percent // 10) + "░" * (10 - (percent // 10))
    text = f"📥 **Processing... [{percent}%]**\n`{bar}`\n{note}"
    await safe_call(message.edit_text(text))


async def process_job(job: Job) -> None:
    progress_message = await bot.get_messages(job.progress_chat_id, job.progress_message_id)
    parsed = parse_link(job.source_link)
    if not parsed:
        await safe_call(progress_message.edit_text("❌ Invalid Telegram link."))
        return

    link_type, chat_ref, msg_id = parsed

    try:
        await update_progress(progress_message, 25, "Fetching source message...")

        if link_type == "public":
            source_msg = await safe_call(bot.get_messages(chat_ref, msg_id))
        else:
            source_msg = await safe_call(userbot.get_messages(int(chat_ref), msg_id))

        if not source_msg:
            await safe_call(progress_message.edit_text("❌ Source message not found."))
            return

        await update_progress(progress_message, 50, "Downloading media...")
        if not source_msg.media:
            copied = await safe_call(
                bot.copy_message(
                    chat_id=job.user_id,
                    from_chat_id=source_msg.chat.id,
                    message_id=source_msg.id,
                    protect_content=True,
                )
            )
            await increment_stat("files_saved", 1)
            await update_progress(progress_message, 100, f"✅ Completed: `{copied.id}`")
            return

        file_path = await safe_call(source_msg.download())
        await update_progress(progress_message, 75, "Uploading with protection...")

        caption = source_msg.caption or "📥 Saved by Restricted Content Saver"
        await safe_call(
            bot.send_document(
                chat_id=job.user_id,
                document=file_path,
                caption=caption,
                protect_content=True,
            )
        )
        await increment_stat("files_saved", 1)
        await update_progress(progress_message, 100, "✅ File delivered successfully.")

        if file_path and os.path.exists(file_path):
            os.remove(file_path)

    except UserNotParticipant:
        pending_join[job.user_id] = job
        await safe_call(
            progress_message.edit_text(
                "⚠️ UserBot is not in this private chat.\n"
                "Please send a valid **Join Link** (`https://t.me/+...`) now."
            )
        )
    except Exception as e:
        await safe_call(progress_message.edit_text(f"❌ Failed: `{str(e)[:180]}`"))


async def worker() -> None:
    while True:
        job = await work_queue.get()
        try:
            await process_job(job)
        finally:
            work_queue.task_done()


@bot.on_message(filters.command("start") & filters.private)
async def start_handler(_, message: Message):
    await ensure_user(message.from_user.id)
    await increment_stat("starts", 1)

    if not await check_force_sub(message.from_user.id):
        await message.reply_text(
            "💠 **𝐒𝐀𝐕𝐄𝐑 𝐌𝐄𝐍𝐔**\n\n"
            "To continue, join our updates channel first.",
            reply_markup=fsub_markup(),
            disable_web_page_preview=True,
        )
        return

    await message.reply_text(
        "💠 **𝐒𝐀𝐕𝐄𝐑 𝐌𝐄𝐍𝐔**\n\n"
        "Send any Telegram post link to save it securely.\n"
        "Supports 🔗 public + private links, ⚡ queued processing, and 🛡️ protected re-upload.",
        reply_markup=dashboard_markup(),
    )


@bot.on_callback_query(filters.regex("^verify_fsub$"))
async def verify_fsub(_, cq):
    if await check_force_sub(cq.from_user.id):
        await cq.message.edit_text(
            "✅ Verified successfully. Welcome to your Premium Dashboard.",
            reply_markup=dashboard_markup(),
        )
    else:
        await cq.answer("Join channel first.", show_alert=True)


@bot.on_callback_query(filters.regex("^queue_status$"))
async def queue_status(_, cq):
    await cq.answer(f"Pending jobs: {work_queue.qsize()}", show_alert=True)


@bot.on_callback_query(filters.regex("^help_save$|^fsub_ok$"))
async def help_ui(_, cq):
    await cq.answer("Send a Telegram message link to begin ⚡")


@bot.on_message(filters.private & filters.text & ~filters.command(["start", "stats", "broadcast"]))
async def inbound_handler(_, message: Message):
    user_id = message.from_user.id
    if not await check_force_sub(user_id):
        await message.reply_text("❌ Access blocked. Join channel and tap Verify.", reply_markup=fsub_markup())
        return

    if user_id in pending_join and INVITE_REGEX.search(message.text or ""):
        job = pending_join[user_id]
        try:
            await safe_call(userbot.join_chat(message.text.strip()))
        except UserAlreadyParticipant:
            pass
        except (InviteHashInvalid, InviteHashExpired):
            await message.reply_text("❌ Invalid/expired join link. Send a fresh invite link.")
            return

        pending_join.pop(user_id, None)
        status = await message.reply_text("🔄 Join successful. Re-queuing your task...")
        await work_queue.put(
            Job(
                user_id=job.user_id,
                source_link=job.source_link,
                progress_chat_id=status.chat.id,
                progress_message_id=status.id,
            )
        )
        return

    if not parse_link(message.text or ""):
        await message.reply_text("⚠️ Send a valid Telegram post link (`t.me/.../...`).")
        return

    status = await message.reply_text("📥 **Processing... [0%]**\n`░░░░░░░░░░`")
    await work_queue.put(
        Job(user_id=user_id, source_link=message.text.strip(), progress_chat_id=status.chat.id, progress_message_id=status.id)
    )


@bot.on_message(filters.command("stats") & filters.private)
async def stats_handler(_, message: Message):
    if message.from_user.id != config.owner_id:
        return
    total_users, total_files = await get_counts()
    await message.reply_text(f"📊 Users: **{total_users}**\n📁 Files Saved: **{total_files}**")


@bot.on_message(filters.command("broadcast") & filters.private)
async def broadcast_handler(_, message: Message):
    if message.from_user.id != config.owner_id:
        return
    if not message.reply_to_message:
        await message.reply_text("Reply to a message with /broadcast")
        return

    sent = failed = 0
    users = users_col.find({}, {"_id": 1})
    async for user in users:
        try:
            await safe_call(message.reply_to_message.copy(user["_id"]))
            sent += 1
        except Exception:
            failed += 1
        if (sent + failed) % 25 == 0:
            await asyncio.sleep(2)

    await message.reply_text(f"✅ Broadcast done. Sent: {sent}, Failed: {failed}")


async def bootstrap() -> None:
    await bot.start()
    if config.string_session:
        await userbot.start()
    asyncio.create_task(worker())
    print("Restricted Saver Bot started.")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(bootstrap())
