from __future__ import annotations

import json
import urllib.error
import urllib.request

from .classifier import classify_message
from .config import LlmConfig
from .models import CollectedMessage, PortfolioHolding


def generate_general_digest(
    config: LlmConfig,
    messages: tuple[CollectedMessage, ...],
    *,
    period_label: str,
) -> str | None:
    """OpenAI 호환 Chat API에 일반 뉴스 요약을 요청한다.

    이 함수는 일부러 일반 뉴스 다이제스트에만 쓴다.
    포트폴리오 매칭은 Python 코드에 남겨서 PDF 단독 메시지에 대한 환각 요약을 막는다.
    """
    if not config.enabled or not config.api_key:
        return None
    payload = {
        "model": config.model,
        "temperature": config.temperature,
        "messages": [
            {
                "role": "system",
                "content": (
                    "당신은 경험 많은 뉴스 분석가입니다. 텔레그램 메시지를 한국어로 요약합니다. "
                    "출력은 Telegram HTML 형식만 사용합니다. 투자 조언, 매수/매도 판단, 자체 시사점은 쓰지 않습니다. "
                    "PDF 파일명만 있는 항목은 일반 뉴스 요약에 억지로 해석하지 않습니다."
                ),
            },
            {
                "role": "user",
                "content": _build_user_prompt(messages, period_label, config),
            },
        ],
    }
    body = _post_chat_completion(config, payload)
    return body["choices"][0]["message"]["content"].strip()


def generate_full_digest(
    config: LlmConfig,
    messages: tuple[CollectedMessage, ...],
    holdings: tuple[PortfolioHolding, ...],
    *,
    period_label: str,
) -> str | None:
    """LLM이 일반 뉴스와 포트폴리오 섹션을 함께 요약하게 한다.

    단, PDF 단독 파일은 LLM이 내용을 안다고 꾸미지 않도록 입력에서 파일명/URL만 제공한다.
    실제 첨부 파일 목록은 digest.py가 코드로 다시 보강한다.
    """
    if not config.enabled or not config.api_key:
        return None

    payload = {
        "model": config.model,
        "temperature": config.temperature,
        "messages": [
            {
                "role": "system",
                "content": (
                    "당신은 텔레그램 투자/뉴스 채널을 요약하는 한국어 뉴스 분석가입니다. "
                    "출력은 Telegram HTML 형식만 사용합니다. "
                    "중요하지 않거나 보유 종목과 관련 없는 세부사항은 과감히 생략합니다. "
                    "모든 메시지를 다 넣으려 하지 말고, 실제로 의미 있는 뉴스만 고릅니다. "
                    "투자 조언, 매수/매도 판단, 당신 자신의 시사점은 쓰지 않습니다. "
                    "원문에 있는 애널리스트/회사/언론의 견해는 출처를 밝혀 전달할 수 있습니다. "
                    "PDF 파일명만 있는 항목은 내용을 추정하지 말고, 파일명 수준에서만 언급합니다."
                ),
            },
            {
                "role": "user",
                "content": _build_full_digest_prompt(messages, holdings, period_label, config),
            },
        ],
    }
    body = _post_chat_completion(config, payload)
    return body["choices"][0]["message"]["content"].strip()


def _build_user_prompt(messages: tuple[CollectedMessage, ...], period_label: str, config: LlmConfig) -> str:
    lines = [
        f"기간: {period_label}",
        "아래 메시지에서 중요한 뉴스를 주제별로 묶어 간결하게 요약하세요.",
        "형식:",
        "<b>주요 뉴스 다이제스트</b>",
        "",
        "<b>이모지 주제명</b>",
        "한 문장 요지.",
        "— 세부사항 <a href=\"원문URL\">원문</a>",
        "",
        "메시지:",
    ]
    for index, message in enumerate(messages[-config.max_messages :], start=1):
        text = (message.text or "").replace("\n", " ").strip()
        file_note = f" FILE={message.file_name}" if message.file_name else ""
        if len(text) > config.max_chars_per_message:
            text = text[: config.max_chars_per_message] + "..."
        lines.append(
            f"[{index}] {message.date_utc.isoformat()} {message.channel_title} "
            f"URL={message.url or ''}{file_note} TEXT={text}"
        )
    return "\n".join(lines)


def _build_full_digest_prompt(
    messages: tuple[CollectedMessage, ...],
    holdings: tuple[PortfolioHolding, ...],
    period_label: str,
    config: LlmConfig,
) -> str:
    portfolio_lines = []
    for holding in holdings:
        aliases = ", ".join(holding.aliases)
        keywords = ", ".join(holding.keywords)
        portfolio_lines.append(
            f"- {holding.display_name} ({holding.ticker}): aliases=[{aliases}], keywords=[{keywords}]"
        )

    lines = [
        f"기간: {period_label}",
        "",
        "목표:",
        "1. 먼저 <b>주요 뉴스 다이제스트</b>를 만든다.",
        "2. 그 아래에 <b>📊 내 포트폴리오</b> 섹션을 만든다.",
        "3. 관련 뉴스가 없는 보유 종목은 쓰지 않는다.",
        "4. 일반 뉴스든 포트폴리오든 중요하지 않은 내용은 생략한다.",
        "",
        "출력 형식:",
        "<b>주요 뉴스 다이제스트</b>",
        "",
        "<b>이모지 주제명</b>",
        "한 문장 요지.",
        "— 핵심 세부사항 <a href=\"원문URL\">원문</a>",
        "",
        "<b>📊 내 포트폴리오</b>",
        "",
        "<b>이모지 회사명 (티커)</b>",
        "한 문장 요지.",
        "— 핵심 세부사항 <a href=\"원문URL\">원문</a>",
        "",
        "분량 규칙:",
        "- 주요 뉴스는 최대 4개 주제.",
        "- 주제당 불릿은 최대 3개.",
        "- 포트폴리오 종목당 불릿은 최대 3개.",
        "- 단순 링크, 중복 뉴스, 약한 관련성은 생략.",
        "",
        "보유 종목:",
        *portfolio_lines,
        "",
        "메시지:",
    ]

    for index, message in enumerate(messages[-config.max_messages :], start=1):
        text = (message.text or "").replace("\n", " ").strip()
        file_note = f" FILE={message.file_name}" if message.file_name else ""
        matches = classify_message(message, holdings)
        match_note = ""
        if matches:
            match_note = " MATCH=" + ",".join(match.holding.ticker for match in matches)
        if len(text) > config.max_chars_per_message:
            text = text[: config.max_chars_per_message] + "..."
        lines.append(
            f"[{index}] {message.date_utc.isoformat()} {message.channel_title} "
            f"URL={message.url or ''}{file_note}{match_note} TEXT={text}"
        )
    return "\n".join(lines)


def _post_chat_completion(config: LlmConfig, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        config.base_url.rstrip("/") + "/chat/completions",
        data=data,
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_sec) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"LLM request failed: {exc}") from exc
