from __future__ import annotations

import asyncio
from typing import Any

from pyrogram import Client
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import ChatAdminRequired, FloodWait, UserNotParticipant
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


async def safe_call(coro):
    while True:
        try:
            return await coro
        except FloodWait as e:
            await asyncio.sleep(e.value + 1)


def styled_button(
    text: str,
    callback_data: str | None = None,
    url: str | None = None,
    style: str | None = None,
) -> InlineKeyboardButton:
    kwargs: dict[str, Any] = {}
    if callback_data:
        kwargs["callback_data"] = callback_data
    if url:
        kwargs["url"] = url

    if style:
        try:
            return InlineKeyboardButton(text=text, style=style, **kwargs)
        except TypeError:
            pass

    return InlineKeyboardButton(text=text, **kwargs)


def premium_fsub_markup(force_sub_id: str) -> InlineKeyboardMarkup:
    url = f"https://t.me/{force_sub_id.lstrip('@')}"
    return InlineKeyboardMarkup(
        [
            [styled_button("Join Channel", url=url, style="primary")],
            [styled_button("Verify Access", callback_data="verify", style="success")],
        ]
    )


def premium_dashboard_markup(force_sub_id: str) -> InlineKeyboardMarkup:
    url = f"https://t.me/{force_sub_id.lstrip('@')}"
    return InlineKeyboardMarkup(
        [
            [
                styled_button("Join Channel", url=url, style="secondary"),
                styled_button("Verify Access", callback_data="verify", style="success"),
            ],
            [styled_button("Save Content", callback_data="save_help", style="primary")],
            [styled_button("Profile", callback_data="my_profile", style="secondary")],
            [styled_button("Clear Panel", callback_data="clear_panel", style="danger")],
        ]
    )


async def start_menu(message, force_sub_id: str):
    text = (
        "<b>RESTRICTED 🚫 MESSAGE SAVER 💾</b>\n"
        "<i>Premium Telegram Content Backup System</i>\n\n"
        "<code>Paste a post link from public/private channel. "
        "Queue workers will process it securely.</code>"
    )
    await message.reply_text(
        text,
        disable_web_page_preview=True,
        reply_markup=premium_dashboard_markup(force_sub_id),
    )


async def is_user_verified(bot: Client, force_sub_id: str, user_id: int) -> bool:
    if not force_sub_id:
        return True

    try:
        member = await safe_call(bot.get_chat_member(force_sub_id, user_id))
        if not member:
            return False
        return member.status not in {ChatMemberStatus.LEFT, ChatMemberStatus.BANNED}
    except UserNotParticipant:
        return False
    except ChatAdminRequired:
        return False
    except Exception:
        return False
