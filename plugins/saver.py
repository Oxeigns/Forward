from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from pathlib import Path

from pyrogram import Client
from pyrogram.errors import FloodWait, InviteHashExpired, InviteHashInvalid, UserAlreadyParticipant
from pyrogram.types import InputMediaAudio, InputMediaDocument, InputMediaPhoto, InputMediaVideo, Message

PUBLIC_LINK_RE = re.compile(r"^(?:https?://)?t\.me/([A-Za-z0-9_]{4,})/(\d+)$")
PRIVATE_LINK_RE = re.compile(r"^(?:https?://)?t\.me/c/(\d+)/(\d+)$")
INVITE_LINK_RE = re.compile(r"^(?:https?://)?t\.me/(?:\+|joinchat/)([\w-]+)$")


@dataclass(slots=True)
class Job:
    user_id: int
    source_link: str
    status_chat_id: int
    status_message_id: int


@dataclass(slots=True)
class ParsedLink:
    is_private: bool
    chat_id: int | str
    message_id: int


class PrivateAccessNeeded(Exception):
    pass


class SaveWorker:
    def __init__(
        self,
        bot: Client,
        userbot: Client | None,
        downloads_dir: str,
        job_timeout: int,
        max_retries: int,
    ):
        self.bot = bot
        self.userbot = userbot
        self.job_timeout = job_timeout
        self.max_retries = max_retries
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.downloads_dir = Path(downloads_dir)
        self.downloads_dir.mkdir(parents=True, exist_ok=True)

        self.pending_private: dict[int, Job] = {}
        self.joined_invites: set[str] = set()

    async def safe_call(self, coro):
        while True:
            try:
                return await coro
            except FloodWait as e:
                await asyncio.sleep(e.value + 1)

    def parse_link(self, link: str) -> ParsedLink | None:
        raw = (link or "").strip()
        pvt = PRIVATE_LINK_RE.match(raw)
        if pvt:
            cid, mid = pvt.groups()
            return ParsedLink(True, int(f"-100{cid}"), int(mid))

        pub = PUBLIC_LINK_RE.match(raw)
        if pub:
            username, mid = pub.groups()
            return ParsedLink(False, username, int(mid))

        return None

    @staticmethod
    def parse_invite(link: str) -> str | None:
        m = INVITE_LINK_RE.match((link or "").strip())
        if not m:
            return None
        return f"https://t.me/+{m.group(1)}"

    async def join_invite(self, invite_link: str) -> bool:
        if not self.userbot:
            return False
        if invite_link in self.joined_invites:
            return True

        try:
            await self.safe_call(self.userbot.join_chat(invite_link))
            self.joined_invites.add(invite_link)
            return True
        except UserAlreadyParticipant:
            self.joined_invites.add(invite_link)
            return True
        except (InviteHashExpired, InviteHashInvalid):
            return False
        except Exception:
            return False

    async def update_status(self, job: Job, percent: int, state: str, extra: str = ""):
        filled = max(0, min(10, percent // 10))
        bar = f"[{'▰' * filled}{'▱' * (10 - filled)}] {percent}%"
        icons = {
            "queued": "🕓",
            "resolving": "🔎",
            "downloading": "📥",
            "uploading": "📤",
            "completed": "✅",
            "failed": "❌",
        }
        text = (
            "<b>RESTRICTED 🚫 MESSAGE SAVER 💾</b>\n"
            f"<code>{bar}</code>\n"
            f"<i>{icons.get(state, '⚙️')} {state}</i>"
        )
        if extra:
            text += f"\n<code>{extra}</code>"

        await self.safe_call(
            self.bot.edit_message_text(
                chat_id=job.status_chat_id,
                message_id=job.status_message_id,
                text=text,
                disable_web_page_preview=True,
            )
        )

    async def _fetch_source(self, parsed: ParsedLink) -> Message | None:
        client = self.userbot if parsed.is_private else self.bot
        if client is None:
            raise PrivateAccessNeeded
        return await self.safe_call(client.get_messages(parsed.chat_id, parsed.message_id))

    async def _send_text(self, job: Job, msg: Message):
        try:
            await self.safe_call(
                self.bot.copy_message(
                    chat_id=job.user_id,
                    from_chat_id=msg.chat.id,
                    message_id=msg.id,
                    protect_content=True,
                )
            )
        except Exception:
            body = msg.text or msg.caption or "(empty message)"
            await self.safe_call(self.bot.send_message(job.user_id, body, protect_content=True))

    async def _download(self, msg: Message) -> str:
        path = await self.safe_call(msg.download(file_name=f"{self.downloads_dir}/"))
        if not path:
            raise RuntimeError("Download returned empty path")
        return path

    async def _send_single_media(self, user_id: int, msg: Message, local_path: str):
        caption = msg.caption or ""
        if msg.photo:
            await self.safe_call(self.bot.send_photo(user_id, local_path, caption=caption, protect_content=True))
        elif msg.video:
            await self.safe_call(self.bot.send_video(user_id, local_path, caption=caption, protect_content=True))
        elif msg.audio:
            await self.safe_call(self.bot.send_audio(user_id, local_path, caption=caption, protect_content=True))
        elif msg.voice:
            await self.safe_call(self.bot.send_voice(user_id, local_path, protect_content=True))
        elif msg.sticker:
            await self.safe_call(self.bot.send_sticker(user_id, local_path, protect_content=True))
        else:
            await self.safe_call(self.bot.send_document(user_id, local_path, caption=caption, protect_content=True))

    def _build_media(self, msg: Message, local_path: str, caption: str):
        if msg.photo:
            return InputMediaPhoto(local_path, caption=caption)
        if msg.video:
            return InputMediaVideo(local_path, caption=caption)
        if msg.audio:
            return InputMediaAudio(local_path, caption=caption)
        return InputMediaDocument(local_path, caption=caption)

    async def _send_media_group(self, job: Job, messages: list[Message]):
        local_files: list[str] = []
        try:
            items = []
            for idx, msg in enumerate(messages[:10]):
                local = await self._download(msg)
                local_files.append(local)
                items.append(self._build_media(msg, local, (msg.caption or "") if idx == 0 else ""))
            await self.safe_call(self.bot.send_media_group(job.user_id, items, protect_content=True))
        finally:
            for f in local_files:
                if os.path.exists(f):
                    os.remove(f)

    async def _process_once(self, job: Job):
        parsed = self.parse_link(job.source_link)
        if not parsed:
            await self.update_status(job, 100, "failed", "Invalid link")
            return

        await self.update_status(job, 20, "resolving")
        source = await self._fetch_source(parsed)
        if not source or getattr(source, "empty", False):
            raise RuntimeError("Message not found")

        if getattr(source, "has_protected_content", False):
            await self.update_status(job, 100, "failed", "[ POLICY ] Protected content cannot be saved")
            return

        if not source.media:
            await self.update_status(job, 80, "uploading")
            await self._send_text(job, source)
            await self.update_status(job, 100, "completed")
            return

        await self.update_status(job, 45, "downloading")
        client = self.userbot if parsed.is_private and self.userbot else self.bot
        if source.media_group_id and client:
            group = await self.safe_call(client.get_media_group(source.chat.id, source.id))
        else:
            group = [source]

        if len(group) > 1:
            await self._send_media_group(job, group)
            await self.update_status(job, 100, "completed")
            return

        local = await self._download(source)
        try:
            await self.update_status(job, 80, "uploading")
            await self._send_single_media(job.user_id, source, local)
        finally:
            if os.path.exists(local):
                os.remove(local)

        await self.update_status(job, 100, "completed")

    async def process_job(self, job: Job):
        for attempt in range(1, self.max_retries + 1):
            try:
                await self._process_once(job)
                return
            except PrivateAccessNeeded:
                self.pending_private[job.user_id] = job
                await self.update_status(
                    job,
                    100,
                    "failed",
                    "Private chat access required. Send invite link: t.me/+xxxx",
                )
                return
            except Exception as e:
                if attempt == self.max_retries:
                    await self.update_status(job, 100, "failed", str(e)[:140])
                    return
                await asyncio.sleep(attempt)

    async def run_worker(self, worker_name: str):
        while True:
            job = await self.queue.get()
            try:
                await asyncio.wait_for(self.process_job(job), timeout=self.job_timeout)
            except asyncio.TimeoutError:
                await self.update_status(job, 100, "failed", "Job timeout (300s)")
            except Exception as e:
                await self.update_status(job, 100, "failed", f"Worker error: {e}")
            finally:
                self.queue.task_done()

    async def requeue_after_invite(self, user_id: int, invite_link: str) -> tuple[bool, str]:
        pending = self.pending_private.get(user_id)
        if not pending:
            return False, "No pending private job found. Send a private t.me/c/... link first."

        joined = await self.join_invite(invite_link)
        if not joined:
            return False, "Invite link invalid/expired or join failed."

        self.pending_private.pop(user_id, None)
        await self.queue.put(pending)
        return True, "Invite accepted. Job re-queued for retry."
