from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

from .models import CollectedMessage


SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_id TEXT NOT NULL,
  message_id INTEGER NOT NULL,
  channel_title TEXT NOT NULL,
  channel_username TEXT,
  date_utc TEXT NOT NULL,
  text TEXT NOT NULL,
  url TEXT,
  file_name TEXT,
  mime_type TEXT,
  is_document INTEGER NOT NULL,
  is_pdf INTEGER NOT NULL,
  inserted_at_utc TEXT NOT NULL,
  UNIQUE(channel_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_messages_date_utc ON messages(date_utc);
CREATE INDEX IF NOT EXISTS idx_messages_file_name ON messages(file_name);

CREATE TABLE IF NOT EXISTS digest_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  digest_hash TEXT NOT NULL UNIQUE,
  period_start_utc TEXT NOT NULL,
  period_end_utc TEXT NOT NULL,
  sent_at_utc TEXT NOT NULL
);
"""


class MessageStore:
    """수집 메시지와 발송 이력을 다루는 작은 SQLite 래퍼."""

    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    def init(self) -> None:
        with closing(self.connect()) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        return conn

    def upsert_messages(self, messages: Iterable[CollectedMessage]) -> int:
        # INSERT OR IGNORE 덕분에 같은 채널/메시지 id는 한 번만 저장된다.
        now = datetime.now(UTC).isoformat()
        inserted = 0
        with closing(self.connect()) as conn:
            for message in messages:
                cursor = conn.execute(
                    """
                    INSERT OR IGNORE INTO messages (
                      channel_id, message_id, channel_title, channel_username,
                      date_utc, text, url, file_name, mime_type,
                      is_document, is_pdf, inserted_at_utc
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message.channel_id,
                        message.message_id,
                        message.channel_title,
                        message.channel_username,
                        message.date_utc.astimezone(UTC).isoformat(),
                        message.text,
                        message.url,
                        message.file_name,
                        message.mime_type,
                        int(message.is_document),
                        int(message.is_pdf),
                        now,
                    ),
                )
                inserted += cursor.rowcount
            conn.commit()
        return inserted

    def list_messages(self, start_utc: datetime, end_utc: datetime) -> tuple[CollectedMessage, ...]:
        with closing(self.connect()) as conn:
            rows = conn.execute(
                """
                SELECT * FROM messages
                WHERE date_utc >= ? AND date_utc < ?
                ORDER BY date_utc ASC, channel_title ASC, message_id ASC
                """,
                (start_utc.astimezone(UTC).isoformat(), end_utc.astimezone(UTC).isoformat()),
            ).fetchall()
        return tuple(_row_to_message(row) for row in rows)

    def has_sent_digest(self, digest_hash: str) -> bool:
        # 다이제스트 해시로 같은 내용을 실수로 중복 발송하는 일을 막는다.
        with closing(self.connect()) as conn:
            row = conn.execute(
                "SELECT 1 FROM digest_runs WHERE digest_hash = ?",
                (digest_hash,),
            ).fetchone()
        return row is not None

    def record_sent_digest(self, digest_hash: str, start_utc: datetime, end_utc: datetime) -> None:
        with closing(self.connect()) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO digest_runs (
                  digest_hash, period_start_utc, period_end_utc, sent_at_utc
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    digest_hash,
                    start_utc.astimezone(UTC).isoformat(),
                    end_utc.astimezone(UTC).isoformat(),
                    datetime.now(UTC).isoformat(),
                ),
            )
            conn.commit()


def _row_to_message(row: sqlite3.Row) -> CollectedMessage:
    return CollectedMessage(
        channel_id=row["channel_id"],
        message_id=int(row["message_id"]),
        channel_title=row["channel_title"],
        channel_username=row["channel_username"],
        date_utc=datetime.fromisoformat(row["date_utc"]).astimezone(UTC),
        text=row["text"],
        url=row["url"],
        file_name=row["file_name"],
        mime_type=row["mime_type"],
        is_document=bool(row["is_document"]),
        is_pdf=bool(row["is_pdf"]),
    )
