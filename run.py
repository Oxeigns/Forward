import os

# 🔥 MUST BE FIRST LINE
os.environ["PYROGRAM_DISABLE_SYNC"] = "1"

# optional but recommended
import uvloop
uvloop.install()

import asyncio
asyncio.set_event_loop(asyncio.new_event_loop())

# NOW import your bot
import main
