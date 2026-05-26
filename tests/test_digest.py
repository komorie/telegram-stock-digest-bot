from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tg_portfolio_bot.digest import build_pdf_attachment_section, build_portfolio_section
from tg_portfolio_bot.models import CollectedMessage, PortfolioHolding


TEST_PORTFOLIO = (
    PortfolioHolding(
        ticker="000660.KS",
        display_name="SK하이닉스",
        emoji="🚀",
        aliases=("SK하이닉스", "SK hynix", "SK Hynix", "하이닉스", "Hynix", "000660"),
        keywords=("HBM", "DRAM", "메모리", "memory", "삼성", "Samsung", "마이크론", "Micron", "eSSD", "LPDDR"),
    ),
    PortfolioHolding(
        ticker="GOOG",
        display_name="구글/알파벳",
        emoji="🌐",
        aliases=("GOOG", "GOOGL", "Google", "Alphabet", "구글", "알파벳"),
        keywords=("TPU", "GCP", "Google Cloud", "클라우드", "검색", "search", "YouTube", "유튜브", "Waymo", "웨이모", "Gemini", "Anthropic", "앤트로픽"),
    ),
)


def _message(message_id: int, text: str = "", file_name: str | None = None) -> CollectedMessage:
    return CollectedMessage(
        channel_id="1",
        message_id=message_id,
        channel_title="리서치",
        channel_username="research",
        date_utc=datetime(2026, 5, 1, tzinfo=UTC),
        text=text,
        url=f"https://t.me/research/{message_id}",
        file_name=file_name,
        mime_type="application/pdf" if file_name else None,
        is_document=bool(file_name),
        is_pdf=bool(file_name),
    )


class DigestTests(unittest.TestCase):
    def test_pdf_only_message_goes_to_attachment_section(self) -> None:
        section = build_portfolio_section(
            (
                _message(1, file_name="JP모건_SK하이닉스_1Q26_실적분석.pdf"),
                _message(2, "GOOG TPU 투자 확대"),
            ),
            TEST_PORTFOLIO,
        )
        self.assertIn("📎 <b>첨부 파일</b>", section)
        self.assertIn("JP모건_SK하이닉스_1Q26_실적분석.pdf", section)
        self.assertIn('<a href="https://t.me/research/1">', section)
        self.assertNotIn("시사점:", section)

    def test_text_message_is_not_listed_as_attachment(self) -> None:
        section = build_portfolio_section(
            (_message(1, "SK하이닉스 HBM 공급 부족 전망"),),
            TEST_PORTFOLIO,
        )
        self.assertNotIn("📎 <b>첨부 파일</b>", section)
        self.assertIn("HBM", section)

    def test_pdf_attachment_section_only_lists_pdf_only_messages(self) -> None:
        section = build_pdf_attachment_section(
            (
                _message(1, file_name="GOOG_TPU_report.pdf"),
                _message(
                    2,
                    "GOOG TPU 투자 확대와 GCP 인프라 수요에 대한 본문 설명이 충분히 포함된 일반 뉴스 메시지입니다.",
                    file_name="GOOG_text_with_pdf.pdf",
                ),
                _message(3, "SK하이닉스 HBM 공급 부족 전망"),
            ),
            TEST_PORTFOLIO,
        )
        self.assertIn("GOOG_TPU_report.pdf", section)
        self.assertNotIn("GOOG_text_with_pdf.pdf", section)
        self.assertNotIn("SK하이닉스 HBM", section)


if __name__ == "__main__":
    unittest.main()
