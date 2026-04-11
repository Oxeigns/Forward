from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from typing import Optional, Tuple

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import Message

POST_REGEX = re.compile(r"https?://t\.me/(?:c/(\d+)/(\d+)|([A-Za-z0-9_]{4,})/(\d+))")


@dataclass
class Job:
    user_id: int
    source_link: str
    status_chat_id: int
    status_message_id: int


class SaveWorker:
    def __init__(self, bot: Client, userbot: Client | None):
        self.bot = bot
        self.userbot = userbot
        self.queue: asyncio.Queue[Job] = asyncio.Queue()

    async def safe_call(self, coro):
        while True:
            try:
                return await coro
            except FloodWait as wait_error:
                await asyncio.sleep(wait_error.value)

    def parse_link(self, link: str) -> Optional[Tuple[str, str, int]]:
        matched = POST_REGEX.search(link)
        if not matched:
            return None

        if matched.group(1) and matched.group(2):
            chat_id = int(f"-100{matched.group(1)}")
            return "private", str(chat_id), int(matched.group(2))

        return "public", matched.group(3), int(matched.group(4))

    @staticmethod
    def progress_line(percent: int) -> str:
        blocks = max(0, min(10, percent // 10))
        bar = "▰" * blocks + "▱" * (10 - blocks)
        return f"`{bar} [{percent}%]`"

    async def update_status(self, status_message: Message, percent: int, detail: str):
        await self.safe_call(
            status_message.edit_text(
                "`[ SAVER STATUS ]`\n"
                f"{self.progress_line(percent)}\n"
                f"`{detail}`"
            )
        )

    async def process_job(self, job: Job):
        status = await self.bot.get_messages(job.status_chat_id, job.status_message_id)
        parsed = self.parse_link(job.source_link)
        if not parsed:
            await self.safe_call(status.edit_text("`[ ERROR ] Invalid Telegram post link.`"))
            return

        link_type, chat_ref, message_id = parsed

        try:
            await self.update_status(status, 15, "Resolving source message")

            source_message = None
            if link_type == "public":
                source_message = await self.safe_call(self.bot.get_messages(chat_ref, message_id))
            elif self.userbot is not None:
                source_message = await self.safe_call(self.userbot.get_messages(int(chat_ref), message_id))

            if not source_message:
                await self.safe_call(status.edit_text("`[ ERROR ] Message not reachable with current access.`"))
                return

            if getattr(source_message, "has_protected_content", False):
                await self.safe_call(status.edit_text("`[ POLICY ] Protected content cannot be re-distributed.`"))
                return

            if not source_message.media:
                await self.update_status(status, 70, "Copying text content")
                await self.safe_call(
                    self.bot.copy_message(
                        chat_id=job.user_id,
                        from_chat_id=source_message.chat.id,
                        message_id=source_message.id,
                        protect_content=True,
                    )
                )
                await self.update_status(status, 100, "Completed")
                return

            await self.update_status(status, 45, "Downloading media")
            local_path = await self.safe_call(source_message.download())

            await self.update_status(status, 80, "Uploading protected file")
            await self.safe_call(
                self.bot.send_document(
                    chat_id=job.user_id,
                    document=local_path,
                    caption=source_message.caption or "`Saved securely via bot.`",
                    protect_content=True,
                )
            )
            await self.update_status(status, 100, "Delivered")

            if local_path and os.path.exists(local_path):
                os.remove(local_path)

        except Exception as save_error:
            await self.safe_call(status.edit_text(f"`[ ERROR ] {str(save_error)[:180]}`"))

    async def run(self):
        while True:
            job = await self.queue.get()
            try:
                await self.process_job(job)
            finally:
                self.queue.task_done()
