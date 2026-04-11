import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    api_id: int = int(os.getenv("API_ID", "0"))
    api_hash: str = os.getenv("API_HASH", "")
    bot_token: str = os.getenv("BOT_TOKEN", "")
    owner_id: int = int(os.getenv("OWNER_ID", "0"))
    fsub_id: str = os.getenv("FSUB_ID", "aghoris")
    string_session: str = os.getenv("STRING_SESSION", "")
    mongo_url: str = os.getenv("MONGO_URL", "")


config = Config()
