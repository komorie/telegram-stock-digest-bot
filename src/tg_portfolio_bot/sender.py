from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request


TELEGRAM_LIMIT = 4096


def send_digest(bot_token: str, chat_id: str, digest: str) -> None:
    for part in split_telegram_message(digest):
        _send_message(bot_token, chat_id, part)


def split_telegram_message(text: str, limit: int = TELEGRAM_LIMIT) -> tuple[str, ...]:
    if len(text) <= limit:
        return (text,)
    chunks: list[str] = []
    current = ""
    for line in text.splitlines():
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = line
        while len(current) > limit:
            chunks.append(current[:limit])
            current = current[limit:]
    if current:
        chunks.append(current)
    return tuple(chunks)


def _send_message(bot_token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = urllib.parse.urlencode(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Telegram sendMessage failed: {exc}") from exc
    if not body.get("ok"):
        raise RuntimeError(f"Telegram sendMessage failed: {body}")

