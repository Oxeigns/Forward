import os
from dataclasses import dataclass


def _require(name: str) -> str:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ValueError(f"Missing required env: {name}")
    return value


@dataclass(frozen=True)
class Config:
    api_id: int = int(_require("API_ID"))
    api_hash: str = _require("API_HASH")
    bot_token: str = _require("BOT_TOKEN")
    owner_id: int = int(_require("OWNER_ID"))

    string_session: str = os.getenv("STRING_SESSION", "").strip()
    force_sub_id: str = os.getenv("FORCE_SUB_ID", "").strip()
    mongo_url: str = _require("MONGO_URL")

    worker_count: int = int(os.getenv("WORKER_COUNT", "2"))
    job_timeout: int = int(os.getenv("JOB_TIMEOUT", "300"))
    max_retries: int = int(os.getenv("MAX_RETRIES", "3"))
    downloads_dir: str = os.getenv("DOWNLOADS_DIR", "downloads").strip()


config = Config()
