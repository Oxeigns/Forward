import os

# Must be set before importing pyrogram anywhere.
os.environ["PYROGRAM_DISABLE_SYNC"] = "1"

try:
    import uvloop

    uvloop.install()
except Exception:
    pass

import asyncio
import main


if __name__ == "__main__":
    asyncio.run(main.main())
