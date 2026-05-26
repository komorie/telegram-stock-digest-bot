from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tg_portfolio_bot.classifier import classify_message
from tg_portfolio_bot.models import PortfolioHolding
from tg_portfolio_bot.models import CollectedMessage


TEST_PORTFOLIO = (
    PortfolioHolding(
        ticker="000660.KS",
        display_name="SK하이닉스",
        emoji="🚀",
        aliases=("SK하이닉스", "SK hynix", "SK Hynix", "하이닉스", "Hynix", "000660"),
        keywords=("HBM", "DRAM", "메모리", "memory", "삼성", "Samsung", "마이크론", "Micron", "eSSD", "LPDDR"),
    ),
    PortfolioHolding(
        ticker="SNDK",
        display_name="샌디스크",
        emoji="💾",
        aliases=("SNDK", "SanDisk", "Sandisk", "샌디스크"),
        keywords=("NAND", "SSD", "스토리지", "storage", "flash memory", "플래시", "eSSD"),
    ),
    PortfolioHolding(
        ticker="GOOG",
        display_name="구글/알파벳",
        emoji="🌐",
        aliases=("GOOG", "GOOGL", "Google", "Alphabet", "구글", "알파벳"),
        keywords=("TPU", "GCP", "Google Cloud", "클라우드", "검색", "search", "YouTube", "유튜브", "Waymo", "웨이모", "Gemini", "Anthropic", "앤트로픽"),
    ),
)


def _message(text: str = "", file_name: str | None = None) -> CollectedMessage:
    return CollectedMessage(
        channel_id="1",
        message_id=1,
        channel_title="test",
        channel_username="test",
        date_utc=datetime(2026, 5, 1, tzinfo=UTC),
        text=text,
        url="https://t.me/test/1",
        file_name=file_name,
        mime_type="application/pdf" if file_name and file_name.endswith(".pdf") else None,
        is_document=bool(file_name),
        is_pdf=bool(file_name and file_name.endswith(".pdf")),
    )


class ClassifierTests(unittest.TestCase):
    def test_korean_direct_and_sector_keywords_match(self) -> None:
        matches = classify_message(_message("SK하이닉스 HBM 수요가 강합니다."), TEST_PORTFOLIO)
        tickers = {match.holding.ticker for match in matches}
        self.assertIn("000660.KS", tickers)

    def test_pdf_filename_matches_sandisk(self) -> None:
        matches = classify_message(_message(file_name="Melius_SanDisk_NAND_Initiation.pdf"), TEST_PORTFOLIO)
        tickers = {match.holding.ticker for match in matches}
        self.assertIn("SNDK", tickers)

    def test_ascii_ticker_uses_token_boundary(self) -> None:
        matches = classify_message(_message("The company uses googlecloudlike wording but not ticker."), TEST_PORTFOLIO)
        tickers = {match.holding.ticker for match in matches}
        self.assertNotIn("GOOG", tickers)


if __name__ == "__main__":
    unittest.main()
