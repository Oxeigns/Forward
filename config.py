import os
from dataclasses import dataclass


REQUIRED_ENV_VARS = [
    "API_ID",
    "API_HASH",
    "BOT_TOKEN",
    "OWNER_ID",
    "MONGO_URL",
]


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"Missing required env: {name}")
    return value


def _get_int(name: str, default: str | None = None) -> int:
    raw = os.getenv(name, default if default is not None else "")
    raw = (raw or "").strip()
    if not raw:
        raise ValueError(f"Missing required env: {name}")
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer") from exc


for _env in REQUIRED_ENV_VARS:
    _require(_env)


@dataclass(frozen=True)
class Config:
    api_id: int = _get_int("API_ID")
    api_hash: str = _require("API_HASH")
    bot_token: str = _require("BOT_TOKEN")
    owner_id: int = _get_int("OWNER_ID")

    string_session: str = os.getenv("STRING_SESSION", "").strip()
    force_sub_id: str = os.getenv("FORCE_SUB_ID", "aghoris").strip() or "aghoris"
    mongo_url: str = _require("MONGO_URL")

    worker_count: int = _get_int("WORKER_COUNT", "2")
    job_timeout: int = _get_int("JOB_TIMEOUT", "300")
    max_retries: int = _get_int("MAX_RETRIES", "3")
    downloads_dir: str = os.getenv("DOWNLOADS_DIR", "downloads").strip() or "downloads"


config = Config()
