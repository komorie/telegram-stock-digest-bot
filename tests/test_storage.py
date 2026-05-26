from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tg_portfolio_bot.models import CollectedMessage
from tg_portfolio_bot.storage import MessageStore


class StorageTests(unittest.TestCase):
    def test_store_deduplicates_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = MessageStore(Path(tmp) / "bot.sqlite3")
            store.init()
            message = CollectedMessage(
                channel_id="1",
                message_id=10,
                channel_title="test",
                channel_username="test",
                date_utc=datetime(2026, 5, 1, tzinfo=UTC),
                text="SK하이닉스",
                url="https://t.me/test/10",
                file_name=None,
                mime_type=None,
                is_document=False,
                is_pdf=False,
            )
            self.assertEqual(store.upsert_messages([message]), 1)
            self.assertEqual(store.upsert_messages([message]), 0)
            rows = store.list_messages(datetime(2026, 5, 1, tzinfo=UTC), datetime(2026, 5, 2, tzinfo=UTC))
            self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
