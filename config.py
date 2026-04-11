import os
from dataclasses import dataclass


def _require(value: str, name: str):
    if not value:
        raise ValueError(f"Missing required env: {name}")
    return value


@dataclass(frozen=True)
class Config:
    # -------- TELEGRAM -------- #
    api_id: int = int(_require(os.getenv("API_ID"), "API_ID"))
    api_hash: str = _require(os.getenv("API_HASH"), "API_HASH")
    bot_token: str = _require(os.getenv("BOT_TOKEN"), "BOT_TOKEN")

    # -------- OWNER -------- #
    owner_id: int = int(_require(os.getenv("OWNER_ID"), "OWNER_ID"))

    # -------- OPTIONAL -------- #
    string_session: str = os.getenv("STRING_SESSION", "")

    # -------- FORCE SUB -------- #
    force_sub_id: str = os.getenv("FORCE_SUB_ID", "aghoris").replace("@", "")

    # -------- DATABASE -------- #
    mongo_url: str = _require(os.getenv("MONGO_URL"), "MONGO_URL")

    # -------- STORAGE -------- #
    downloads_dir: str = os.getenv("DOWNLOADS_DIR", "downloads")

    # -------- WORKERS -------- #
    worker_count: int = int(os.getenv("WORKER_COUNT", "2"))

    # -------- NEW (IMPORTANT) -------- #
    job_timeout: int = int(os.getenv("JOB_TIMEOUT", "300"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))


config = Config()
