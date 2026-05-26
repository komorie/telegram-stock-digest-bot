from __future__ import annotations

import re

from .models import CollectedMessage, PortfolioHolding, PortfolioMatch


def classify_message(
    message: CollectedMessage,
    holdings: tuple[PortfolioHolding, ...],
) -> tuple[PortfolioMatch, ...]:
    """메시지 하나를 보유 종목 별칭과 관련 섹터 키워드에 매칭한다.

    텍스트와 파일명을 모두 검사하므로, PDF 본문을 읽지 않아도
    PDF 단독 리포트를 관련 종목에 붙일 수 있다.
    """
    haystack = message.searchable_text
    if not haystack.strip():
        return ()

    matches: list[PortfolioMatch] = []
    for holding in holdings:
        direct_terms = _matched_terms(haystack, holding.aliases)
        keyword_terms = _matched_terms(haystack, holding.keywords)
        terms = tuple(dict.fromkeys((*direct_terms, *keyword_terms)))
        if terms:
            matches.append(
                PortfolioMatch(
                    holding=holding,
                    matched_terms=terms,
                    is_direct=bool(direct_terms),
                )
            )
    return tuple(matches)


def _matched_terms(text: str, terms: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(term for term in terms if _contains_term(text, term))


def _contains_term(text: str, term: str) -> bool:
    if not term:
        return False
    normalized_text = text.casefold()
    normalized_term = term.casefold()
    if _is_ascii_token(normalized_term):
        pattern = rf"(?<![a-z0-9]){re.escape(normalized_term)}(?![a-z0-9])"
        return re.search(pattern, normalized_text) is not None
    return normalized_term in normalized_text


def _is_ascii_token(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9.+_-]*", value))
