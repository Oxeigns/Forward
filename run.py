import os

# Must be set before importing pyrogram anywhere.
os.environ["PYROGRAM_DISABLE_SYNC"] = "1"

try:
    import uvloop

    uvloop.install()
except Exception:
    pass

import asyncio

# Pyrogram's import side effects may call asyncio.get_event_loop() when sync
# helpers are present. Python 3.11 + uvloop no longer creates one implicitly.
asyncio.set_event_loop(asyncio.new_event_loop())

import main


if __name__ == "__main__":
    asyncio.run(main.main())
