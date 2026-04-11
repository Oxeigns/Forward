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


# Replace these IDs with real values copied from https://t.me/addemoji/RestrictedEmoji
PREMIUM_EMOJI_IDS = {
    "join": "5368324170671202286",
    "verify": "5368324170671202287",
    "save": "5368324170671202288",
    "clear": "5368324170671202289",
    "settings": "5368324170671202290",
}


def _styled_button(text: str, callback_data: str | None = None, url: str | None = None, style: str = "secondary"):
    """InlineKeyboardButton wrapper for Bot API 9.4 colored button styles."""
    payload = {
        "text": text,
        "callback_data": callback_data,
        "url": url,
    }
    payload = {k: v for k, v in payload.items() if v is not None}
    payload["style"] = style
    return InlineKeyboardButton(**payload)


async def start_menu(message, force_sub_id: str):
    """Send neon/mono premium welcome card with API 9.4 styled buttons."""
    channel = force_sub_id if str(force_sub_id).startswith("@") else f"@{force_sub_id}"
    channel_url = f"https://t.me/{channel.lstrip('@')}"

    welcome_text = (
        "<b>𝑵𝒆𝒐𝒏 𝑴𝒐𝒏𝒐 𝑫𝒂𝒔𝒉𝒃𝒐𝒂𝒓𝒅</b>\n"
        "<i>Premium Telegram Saver • Smooth callback transitions</i>\n\n"
        "<code>[ SYSTEM ] Ready for secure save operations.</code>"
    )

    markup = InlineKeyboardMarkup(
        [
            [
                _styled_button(
                    f"<emoji id='{PREMIUM_EMOJI_IDS['join']}'>💠</emoji> 𝐉𝐨𝐢𝐧 𝐀𝐠𝐡𝐨𝐫𝐢𝐬",
                    url=channel_url,
                    style="primary",
                ),
                _styled_button(
                    f"<emoji id='{PREMIUM_EMOJI_IDS['verify']}'>⚡</emoji> 𝐕𝐞𝐫𝐢𝐟𝐲 𝐀𝐜𝐜𝐞𝐬𝐬",
                    callback_data="verify",
                    style="success",
                ),
            ],
            [
                _styled_button(
                    f"<emoji id='{PREMIUM_EMOJI_IDS['save']}'>📥</emoji> 𝐒𝐚𝐯𝐞 𝐂𝐨𝐧𝐭𝐞𝐧𝐭",
                    callback_data="save_help",
                    style="success",
                ),
                _styled_button(
                    f"<emoji id='{PREMIUM_EMOJI_IDS['settings']}'>🛠️</emoji> 𝐒𝐞𝐭𝐭𝐢𝐧𝐠𝐬",
                    callback_data="my_profile",
                    style="secondary",
                ),
            ],
            [
                _styled_button(
                    f"<emoji id='{PREMIUM_EMOJI_IDS['clear']}'>🗑️</emoji> 𝐂𝐥𝐞𝐚𝐫 / 𝐂𝐚𝐧𝐜𝐞𝐥",
                    callback_data="clear_panel",
                    style="danger",
                )
            ],
        ]
    )

    await message.reply_photo(
        photo="https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=1280&q=80",
        caption=welcome_text,
        reply_markup=markup,
    )


async def is_user_verified(bot: Client, force_sub_id: str, user_id: int) -> bool:
    member = await safe_call(bot.get_chat_member(force_sub_id, user_id))
    return member.status not in {ChatMemberStatus.LEFT, ChatMemberStatus.BANNED}
