from __future__ import annotations

import asyncio
import mimetypes
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from pyrogram import Client
from pyrogram.errors import FloodWait
from pyrogram.types import InputMediaAudio, InputMediaDocument, InputMediaPhoto, InputMediaVideo, Message

POST_REGEX = re.compile(
    r"(?:https?://)?t\.me/(?:(?:c/(\d+)/(\d+))|(?:([A-Za-z0-9_]{4,})/(\d+)))"
)


@dataclass
class Job:
    user_id: int
    source_link: str
    status_chat_id: int
    status_message_id: int


@dataclass
class ParsedLink:
    link_type: str
    chat_ref: str | int
    message_id: int


class SaveWorker:
    def __init__(
        self,
        bot: Client,
        userbot: Client | None,
        downloads_dir: str = "downloads",
        job_timeout: int = 300,
        max_retries: int = 3,
    ):
        self.bot = bot
        self.userbot = userbot
        self.downloads_dir = Path(downloads_dir)
        self.job_timeout = job_timeout
        self.max_retries = max_retries
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

    async def safe_call(self, coro):
        while True:
            try:
                return await coro
            except FloodWait as e:
                await asyncio.sleep(e.value)

    def parse_link(self, link: str) -> Optional[ParsedLink]:
        match = POST_REGEX.search((link or "").strip())
        if not match:
            return None

        private_chat, private_msg, public_chat, public_msg = match.groups()

        if private_chat and private_msg:
            return ParsedLink(
                link_type="private",
                chat_ref=int(f"-100{private_chat}"),
                message_id=int(private_msg),
            )

        return ParsedLink(
            link_type="public",
            chat_ref=str(public_chat),
            message_id=int(public_msg),
        )

    @staticmethod
    def progress_line(percent: int) -> str:
        percent = max(0, min(100, percent))
        filled = percent // 10
        return f"<code>[{'▰' * filled}{'▱' * (10 - filled)}] {percent}%</code>"

    async def progress_update(self, status_message: Message, percent: int, state: str):
        icon = {
            "queued": "🕓",
            "resolving": "🔎",
            "downloading": "📥",
            "uploading": "📤",
            "completed": "✅",
            "failed": "❌",
        }.get(state.lower(), "⚙️")

        text = (
            "<b>Restricted Message Saver</b>\n"
            f"{self.progress_line(percent)}\n"
            f"<i>{icon} {state}</i>"
        )

        try:
            await self.safe_call(
                status_message.edit_text(
                    text,
                    disable_web_page_preview=True,
                )
            )
        except Exception:
            pass

    async def set_error(self, status_message: Message, error_text: str):
        try:
            await self.safe_call(
                status_message.edit_text(
                    f"<b>Restricted Message Saver</b>\n<code>[ ERROR ] {error_text[:180]}</code>",
                    disable_web_page_preview=True,
                )
            )
        except Exception:
            pass

    def _guess_media_kind(self, message: Message) -> str:
        if message.photo:
            return "photo"
        if message.video:
            return "video"
        if message.animation:
            return "animation"
        if message.audio:
            return "audio"
        if message.voice:
            return "voice"
        if message.video_note:
            return "video_note"
        if message.sticker:
            return "sticker"
        if message.document:
            return "document"
        return "unknown"

    async def _download_with_retry(self, message: Message) -> Optional[str]:
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                return await self.safe_call(
                    message.download(file_name=str(self.downloads_dir) + "/")
                )
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    await asyncio.sleep(1.5 * attempt)

        if last_error:
            raise last_error
        return None

    async def _send_single_media(self, user_id: int, source_message: Message, file_path: str):
        caption = source_message.caption or ""
        media_kind = self._guess_media_kind(source_message)

        if media_kind == "photo":
            return await self.safe_call(
                self.bot.send_photo(
                    chat_id=user_id,
                    photo=file_path,
                    caption=caption,
                    protect_content=True,
                )
            )

        if media_kind in {"video", "animation"}:
            return await self.safe_call(
                self.bot.send_video(
                    chat_id=user_id,
                    video=file_path,
                    caption=caption,
                    protect_content=True,
                )
            )

        if media_kind == "audio":
            return await self.safe_call(
                self.bot.send_audio(
                    chat_id=user_id,
                    audio=file_path,
                    caption=caption,
                    protect_content=True,
                )
            )

        if media_kind == "voice":
            return await self.safe_call(
                self.bot.send_voice(
                    chat_id=user_id,
                    voice=file_path,
                    protect_content=True,
                )
            )

        if media_kind == "video_note":
            return await self.safe_call(
                self.bot.send_video_note(
                    chat_id=user_id,
                    video_note=file_path,
                    protect_content=True,
                )
            )

        if media_kind == "sticker":
            return await self.safe_call(
                self.bot.send_sticker(
                    chat_id=user_id,
                    sticker=file_path,
                    protect_content=True,
                )
            )

        return await self.safe_call(
            self.bot.send_document(
                chat_id=user_id,
                document=file_path,
                caption=caption or "Saved securely via bot.",
                protect_content=True,
            )
        )

    async def _copy_text_message(self, job: Job, source_message: Message):
        text = source_message.text or source_message.caption
        if not text:
            text = "Empty message."
        await self.safe_call(
            self.bot.send_message(
                chat_id=job.user_id,
                text=text,
                disable_web_page_preview=False,
                protect_content=True,
            )
        )

    async def _get_source_message(self, parsed: ParsedLink) -> Optional[Message]:
        if parsed.link_type == "public":
            return await self.safe_call(self.bot.get_messages(parsed.chat_ref, parsed.message_id))

        if self.userbot is None:
            return None

        return await self.safe_call(self.userbot.get_messages(parsed.chat_ref, parsed.message_id))

    async def _get_media_group_messages(self, parsed: ParsedLink, source_message: Message) -> list[Message]:
        media_group_id = getattr(source_message, "media_group_id", None)
        if not media_group_id:
            return [source_message]

        client = self.userbot if parsed.link_type == "private" and self.userbot else self.bot
        messages = await self.safe_call(client.get_media_group(source_message.chat.id, source_message.id))
        return messages or [source_message]

    def _build_input_media(self, source_message: Message, file_path: str, caption: str = ""):
        if source_message.photo:
            return InputMediaPhoto(media=file_path, caption=caption)
        if source_message.video or source_message.animation:
            return InputMediaVideo(media=file_path, caption=caption)
        if source_message.audio:
            return InputMediaAudio(media=file_path, caption=caption)
        return InputMediaDocument(media=file_path, caption=caption)

    async def _send_media_group(self, user_id: int, messages: list[Message]):
        file_paths: list[str] = []
        try:
            media_items = []
            for index, msg in enumerate(messages[:10]):
                downloaded = await self._download_with_retry(msg)
                if not downloaded:
                    raise RuntimeError("Failed to download one of the media group items.")

                file_paths.append(downloaded)
                caption = msg.caption or ""
                if index != 0:
                    caption = ""
                media_items.append(self._build_input_media(msg, downloaded, caption))

            await self.safe_call(
                self.bot.send_media_group(
                    chat_id=user_id,
                    media=media_items,
                    protect_content=True,
                )
            )
        finally:
            for path in file_paths:
                try:
                    if path and os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass

    async def process_job(self, job: Job):
        status = await self.safe_call(
            self.bot.get_messages(job.status_chat_id, job.status_message_id)
        )
        if not status:
            return

        parsed = self.parse_link(job.source_link)
        if not parsed:
            await self.set_error(status, "Invalid Telegram post link.")
            return

        try:
            await self.progress_update(status, 10, "resolving")
            source_message = await self._get_source_message(parsed)

            if not source_message:
                await self.set_error(status, "Message not accessible.")
                return

            if getattr(source_message, "empty", False):
                await self.set_error(status, "Message not found.")
                return

            if getattr(source_message, "has_protected_content", False):
                await self.set_error(status, "Protected content cannot be saved.")
                return

            if not source_message.media:
                await self.progress_update(status, 70, "uploading")
                await self._copy_text_message(job, source_message)
                await self.progress_update(status, 100, "completed")
                return

            group_messages = await self._get_media_group_messages(parsed, source_message)

            if len(group_messages) > 1:
                await self.progress_update(status, 35, "downloading")
                await self._send_media_group(job.user_id, group_messages)
                await self.progress_update(status, 100, "completed")
                return

            await self.progress_update(status, 40, "downloading")
            local_path = await self._download_with_retry(source_message)

            if not local_path:
                await self.set_error(status, "Download failed.")
                return

            try:
                await self.progress_update(status, 82, "uploading")
                sent = await self._send_single_media(job.user_id, source_message, local_path)
                if not sent:
                    await self.set_error(status, "Upload failed.")
                    return
            finally:
                try:
                    if os.path.exists(local_path):
                        os.remove(local_path)
                except Exception:
                    pass

            await self.progress_update(status, 100, "completed")

        except Exception as e:
            await self.set_error(status, str(e))

    async def run(self):
        while True:
            job = await self.queue.get()
            try:
                await asyncio.wait_for(self.process_job(job), timeout=self.job_timeout)
            except asyncio.TimeoutError:
                status = await self.safe_call(
                    self.bot.get_messages(job.status_chat_id, job.status_message_id)
                )
                if status:
                    await self.set_error(status, "Job timed out.")
            except Exception as e:
                status = await self.safe_call(
                    self.bot.get_messages(job.status_chat_id, job.status_message_id)
                )
                if status:
                    await self.set_error(status, f"Unhandled error: {e}")
            finally:
                self.queue.task_done()
