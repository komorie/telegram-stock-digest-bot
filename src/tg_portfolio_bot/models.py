from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class PortfolioHolding:
    ticker: str
    display_name: str
    emoji: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    keywords: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CollectedMessage:
    channel_id: str
    message_id: int
    channel_title: str
    channel_username: str | None
    date_utc: datetime
    text: str
    url: str | None
    file_name: str | None
    mime_type: str | None
    is_document: bool
    is_pdf: bool

    @property
    def searchable_text(self) -> str:
        parts = [self.text or "", self.file_name or ""]
        return "\n".join(part for part in parts if part)


@dataclass(frozen=True)
class PortfolioMatch:
    holding: PortfolioHolding
    matched_terms: tuple[str, ...]
    is_direct: bool

