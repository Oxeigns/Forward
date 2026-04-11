from __future__ import annotations

import asyncio

from pyrogram import Client
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait, UserNotParticipant, ChatAdminRequired
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


# ------------------ SAFE CALL ------------------ #
async def safe_call(coro):
    while True:
        try:
            return await coro
        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            print(f"[SAFE_CALL ERROR] {e}")
            return None


# ------------------ MARKUPS ------------------ #
def premium_fsub_markup(force_sub_id: str) -> InlineKeyboardMarkup:
    channel = force_sub_id if str(force_sub_id).startswith("@") else f"@{force_sub_id}"
    url = f"https://t.me/{channel.lstrip('@')}"

    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💠 Join Channel", url=url)],
            [InlineKeyboardButton("⚡ Verify Access", callback_data="verify")],
        ]
    )


def premium_dashboard_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📥 Save Content", callback_data="save_help")],
            [InlineKeyboardButton("👤 My Profile", callback_data="my_profile")],
            [InlineKeyboardButton("🗑 Clear Panel", callback_data="clear_panel")],
        ]
    )


# ------------------ START MENU ------------------ #
async def start_menu(message, force_sub_id: str):
    channel = force_sub_id if str(force_sub_id).startswith("@") else f"@{force_sub_id}"
    url = f"https://t.me/{channel.lstrip('@')}"

    text = (
        "<b>Restricted Message Saver 💾</b>\n"
        "<i>Fast • Secure • Unlimited</i>\n\n"
        "<code>Send any Telegram post link to save.</code>"
    )

    markup = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("💠 Join Channel", url=url),
                InlineKeyboardButton("⚡ Verify", callback_data="verify"),
            ],
            [
                InlineKeyboardButton("📥 Save Content", callback_data="save_help"),
                InlineKeyboardButton("👤 Profile", callback_data="my_profile"),
            ],
            [
                InlineKeyboardButton("🗑 Clear Panel", callback_data="clear_panel"),
            ],
        ]
    )

    await message.reply_photo(
        photo="https://images.unsplash.com/photo-1518770660439-4636190af475",
        caption=text,
        reply_markup=markup,
    )


# ------------------ VERIFY ------------------ #
async def is_user_verified(bot: Client, force_sub_id: str, user_id: int) -> bool:
    try:
        member = await safe_call(bot.get_chat_member(force_sub_id, user_id))

        if not member:
            return False

        return member.status not in {
            ChatMemberStatus.LEFT,
            ChatMemberStatus.BANNED,
        }

    except UserNotParticipant:
        return False

    except ChatAdminRequired:
        print("[VERIFY ERROR] Bot is not admin in channel")
        return False

    except Exception as e:
        print(f"[VERIFY ERROR] {e}")
        return False
