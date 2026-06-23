from __future__ import annotations

import hashlib
import html
from collections import defaultdict
from datetime import datetime

from .classifier import classify_message
from .config import AppConfig
from .llm import generate_full_digest, generate_general_digest
from .models import CollectedMessage, PortfolioHolding, PortfolioMatch


class DigestBuildError(RuntimeError):
    """다이제스트를 신뢰할 수 있게 만들지 못했을 때 사용한다."""


def build_digest(
    messages: tuple[CollectedMessage, ...],
    config: AppConfig,
    *,
    start_local: datetime,
    end_local: datetime,
    period_label_override: str | None = None,
) -> str:
    """최종 텔레그램 메시지를 만든다.

    LLM이 켜져 있으면 일반 뉴스와 포트폴리오 섹션을 한 번에 요약하게 한다.
    LLM이 꺼져 있으면 규칙 기반 요약으로 돌아간다.
    LLM이 켜져 있는데 실패하면 해당 기간을 미처리로 남기기 위해 예외를 낸다.
    PDF 단독 첨부 파일은 LLM 입력에서 제외한다.
    """
    period_label = period_label_override or format_period(start_local, end_local)
    llm_messages = tuple(message for message in messages if not _is_pdf_only(message))
    if config.llm.enabled and not config.llm.api_key:
        raise DigestBuildError("LLM is enabled, but llm.api_key is empty.")

    try:
        generated = generate_full_digest(config.llm, llm_messages, config.portfolio, period_label=period_label)
    except RuntimeError as exc:
        if config.llm.enabled:
            raise DigestBuildError(f"LLM 요약 실패: {exc}") from exc
        generated = None
        fallback_note = f"\n\n<i>LLM 요약 실패: {html.escape(str(exc))}</i>"
    else:
        fallback_note = ""

    if generated:
        return f"<b>다이제스트</b> | <b>{html.escape(period_label)}</b>\n\n{generated}".strip()

    general = _build_general_digest(messages, config, period_label, allow_llm=not fallback_note)
    portfolio = build_portfolio_section(messages, config.portfolio)
    return f"<b>다이제스트</b> | <b>{html.escape(period_label)}</b>\n\n{general}\n\n{portfolio}{fallback_note}".strip()


def digest_hash(text: str) -> str:
    """같은 다이제스트를 두 번 보내지 않기 위한 고정 식별값을 만든다."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def format_period(start_local: datetime, end_local: datetime) -> str:
    if start_local.date() == end_local.date():
        return _date_label(start_local)
    return f"{_date_label(start_local)} ~ {_date_label(end_local)}"


def build_portfolio_section(
    messages: tuple[CollectedMessage, ...],
    holdings: tuple[PortfolioHolding, ...],
) -> str:
    """수집된 메시지를 매칭된 보유 종목 아래로 묶는다.

    텍스트 메시지는 짧은 불릿으로 만든다.
    PDF 단독 메시지는 본문을 읽지 않으므로 출력에서 제외한다.
    """
    grouped: dict[str, list[tuple[CollectedMessage, PortfolioMatch]]] = defaultdict(list)
    for message in messages:
        for match in classify_message(message, holdings):
            grouped[match.holding.ticker].append((message, match))

    lines = ["<b>📊 내 포트폴리오</b>"]
    if not grouped:
        lines.append("오늘 보유 종목 관련 주요 업데이트 없음.")
        return "\n".join(lines)

    for holding in holdings:
        items = grouped.get(holding.ticker, [])
        if not items:
            continue

        # PDF 단독 메시지는 파일명만 보고 내용을 꾸미지 않도록 출력하지 않는다.
        text_items = [item for item in items if not _is_pdf_only(item[0])]
        if not text_items:
            continue

        lines.append("")
        lines.append(f"<b>{holding.emoji} {html.escape(holding.display_name)} ({html.escape(holding.ticker)})</b>")

        lead = _lead_sentence(holding, text_items)
        if lead:
            lines.append(lead)

        for message, match in text_items[:5]:
            lines.append(_message_bullet(message, match))

    return "\n".join(lines)


def _build_general_digest(
    messages: tuple[CollectedMessage, ...],
    config: AppConfig,
    period_label: str,
    *,
    allow_llm: bool = True,
) -> str:
    """설정이 있으면 LLM으로 일반 뉴스를 요약하고, 없으면 단순 요약을 쓴다."""
    if not allow_llm:
        return _fallback_general_digest(messages)

    try:
        generated = generate_general_digest(config.llm, messages, period_label=period_label)
    except RuntimeError as exc:
        generated = None
        fallback_note = f"\n\n<i>LLM 요약 실패: {html.escape(str(exc))}</i>"
    else:
        fallback_note = ""

    if generated:
        return generated
    return _fallback_general_digest(messages) + fallback_note


def _fallback_general_digest(messages: tuple[CollectedMessage, ...]) -> str:
    """LLM이 꺼져 있거나 실패했을 때 쓰는 작은 기본 요약이다."""
    text_messages = [message for message in messages if message.text.strip()]
    if not text_messages:
        return "요약할 텍스트 뉴스가 없습니다."

    lines = ["<b>주요 뉴스</b>"]
    for message in text_messages[-5:]:
        title = html.escape(message.channel_title)
        summary = html.escape(_compact_text(message.text, 130))
        lines.append(f"— <b>{title}</b>: {summary} {_link('원문', message.url)}")
    return "\n".join(lines)


def _lead_sentence(
    holding: PortfolioHolding,
    items: list[tuple[CollectedMessage, PortfolioMatch]],
) -> str:
    direct_count = sum(1 for _message, match in items if match.is_direct)
    terms: list[str] = []
    for _message, match in items:
        terms.extend(match.matched_terms[:2])

    term_label = ", ".join(dict.fromkeys(terms[:4]))
    parts: list[str] = []
    if direct_count:
        parts.append(f"직접 언급 {direct_count}건")
    if not parts:
        parts.append(f"관련 신호 {len(items)}건")

    if term_label:
        return f"{html.escape(holding.display_name)} 관련 {', '.join(parts)}이 감지됐습니다. 주요 키워드: {html.escape(term_label)}."
    return f"{html.escape(holding.display_name)} 관련 {', '.join(parts)}이 감지됐습니다."


def _message_bullet(message: CollectedMessage, match: PortfolioMatch) -> str:
    label = html.escape(match.matched_terms[0] if match.matched_terms else match.holding.display_name)
    summary = html.escape(_compact_text(message.text or message.file_name or "", 170))
    return f"— <b>{label}</b>: {summary} {_link('원문', message.url)}"


def _compact_text(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _is_pdf_only(message: CollectedMessage) -> bool:
    """텍스트 뉴스가 아니라 PDF 업로드가 중심인 메시지인지 판단한다."""
    if not message.is_pdf or not message.file_name:
        return False
    text = (message.text or "").strip()
    if not text:
        return True
    return len(text) <= 40 or text.casefold() == message.file_name.casefold()


def _link(label: str, url: str | None) -> str:
    escaped_label = html.escape(label)
    if not url:
        return escaped_label
    return f'<a href="{html.escape(url, quote=True)}">{escaped_label}</a>'


def _date_label(value: datetime) -> str:
    return f"{value.year}년 {value.month}월 {value.day}일"
