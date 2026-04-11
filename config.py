import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    api_id: int = int(os.getenv("API_ID", "0"))
    api_hash: str = os.getenv("API_HASH", "")
    bot_token: str = os.getenv("BOT_TOKEN", "")
    owner_id: int = int(os.getenv("OWNER_ID", "0"))
    string_session: str = os.getenv("STRING_SESSION", "")
    force_sub_id: str = os.getenv("FORCE_SUB_ID", "aghoris")
    mongo_url: str = os.getenv("MONGO_URL", "")
    downloads_dir: str = os.getenv("DOWNLOADS_DIR", "downloads")
    worker_count: int = int(os.getenv("WORKER_COUNT", "2"))


config = Config()
