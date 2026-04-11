from __future__ import annotations

import asyncio

from pyrogram import Client
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


async def safe_call(coro):
    while True:
        try:
            return await coro
        except FloodWait as wait_error:
            await asyncio.sleep(wait_error.value)


def premium_fsub_markup(force_sub_id: str) -> InlineKeyboardMarkup:
    channel = force_sub_id if str(force_sub_id).startswith("@") else f"@{force_sub_id}"
    channel_url = f"https://t.me/{channel.lstrip('@')}"
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💠 𝐉𝐨𝐢𝐧 𝐀𝐠𝐡𝐨𝐫𝐢𝐬 💠", url=channel_url)],
            [InlineKeyboardButton("⚡ 𝐕𝐞𝐫𝐢𝐟𝐲 𝐀𝐜𝐜𝐞𝐬𝐬", callback_data="verify")],
        ]
    )


def premium_dashboard_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📥 𝐒𝐚𝐯𝐞 𝐂𝐨𝐧𝐭𝐞𝐧𝐭", callback_data="save_help")],
            [InlineKeyboardButton("👤 𝐌𝐲 𝐏𝐫𝐨𝐟𝐢𝐥𝐞", callback_data="my_profile")],
        ]
    )


async def is_user_verified(bot: Client, force_sub_id: str, user_id: int) -> bool:
    member = await safe_call(bot.get_chat_member(force_sub_id, user_id))
    return member.status not in {ChatMemberStatus.LEFT, ChatMemberStatus.BANNED}
