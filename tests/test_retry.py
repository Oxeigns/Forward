import unittest
from unittest.mock import AsyncMock, patch
from pyrogram.errors import FloodWait
from plugins.fsub import safe_call
from plugins.saver import SaveWorker


class RetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_creates_fresh_coroutine(self):
        for call in (safe_call, SaveWorker.safe_call.__get__(object(), SaveWorker)):
            operation = AsyncMock(side_effect=[FloodWait(1), 'done'])
            with patch('asyncio.sleep', new_callable=AsyncMock):
                self.assertEqual(await call(operation), 'done')
            self.assertEqual(operation.await_count, 2)
