from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import PortfolioHolding


@dataclass(frozen=True)
class TelegramConfig:
    api_id: int
    api_hash: str
    session_path: Path


@dataclass(frozen=True)
class BotConfig:
    token: str
    chat_id: str


@dataclass(frozen=True)
class LlmConfig:
    enabled: bool
    api_key: str
    base_url: str
    model: str
    temperature: float
    timeout_sec: int
    max_messages: int
    max_chars_per_message: int


@dataclass(frozen=True)
class AppConfig:
    database_path: Path
    timezone: str
    lookback_hours: int
    daily_digest_hour: int
    catch_up_max_days: int
    max_messages_per_channel: int
    sources: tuple[str, ...]
    telegram: TelegramConfig
    bot: BotConfig
    llm: LlmConfig
    portfolio: tuple[PortfolioHolding, ...]


def load_env_file(path: str | Path = ".env") -> None:
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def default_portfolio() -> tuple[PortfolioHolding, ...]:
    # 보유 종목은 코드가 아니라 config.toml의 [[portfolio.holdings]]에 두는 것이 기본 설계다.
    # 이 함수는 portfolio 설정이 없을 때 앱이 깨지지 않도록 빈 목록만 제공한다.
    return ()


def load_config(path: str | Path = "config.toml") -> AppConfig:
    config_path = Path(path)
    raw: dict[str, Any] = {}
    if config_path.exists():
        raw = tomllib.loads(config_path.read_text(encoding="utf-8"))

    telegram_raw = raw.get("telegram", {})
    bot_raw = raw.get("bot", {})
    llm_raw = raw.get("llm", {})

    sources = _env_list("TELEGRAM_SOURCES") or tuple(raw.get("sources", ()))
    api_id = int(os.getenv("TELEGRAM_API_ID") or telegram_raw.get("api_id") or 0)

    return AppConfig(
        database_path=Path(os.getenv("DATABASE_PATH") or raw.get("database_path", "data/bot.sqlite3")),
        timezone=str(os.getenv("APP_TIMEZONE") or raw.get("timezone", "Asia/Seoul")),
        lookback_hours=int(os.getenv("LOOKBACK_HOURS") or raw.get("lookback_hours", 24)),
        daily_digest_hour=int(os.getenv("DAILY_DIGEST_HOUR") or raw.get("daily_digest_hour", 11)),
        catch_up_max_days=int(os.getenv("CATCH_UP_MAX_DAYS") or raw.get("catch_up_max_days", 7)),
        max_messages_per_channel=int(os.getenv("MAX_MESSAGES_PER_CHANNEL") or raw.get("max_messages_per_channel", 500)),
        sources=tuple(str(source).strip() for source in sources if str(source).strip()),
        telegram=TelegramConfig(
            api_id=api_id,
            api_hash=str(os.getenv("TELEGRAM_API_HASH") or telegram_raw.get("api_hash") or ""),
            session_path=Path(os.getenv("TELEGRAM_SESSION_PATH") or telegram_raw.get("session_path", "data/telegram.session")),
        ),
        bot=BotConfig(
            token=str(os.getenv("TELEGRAM_BOT_TOKEN") or bot_raw.get("token") or ""),
            chat_id=str(os.getenv("TELEGRAM_CHAT_ID") or bot_raw.get("chat_id") or ""),
        ),
        llm=LlmConfig(
            enabled=_env_bool("LLM_ENABLED", bool(llm_raw.get("enabled", False))),
            api_key=str(os.getenv("LLM_API_KEY") or llm_raw.get("api_key") or ""),
            base_url=str(os.getenv("LLM_BASE_URL") or llm_raw.get("base_url") or "https://api.openai.com/v1"),
            model=str(os.getenv("LLM_MODEL") or llm_raw.get("model") or "gpt-4.1-mini"),
            temperature=float(os.getenv("LLM_TEMPERATURE") or llm_raw.get("temperature", 0.2)),
            timeout_sec=int(os.getenv("LLM_TIMEOUT_SEC") or llm_raw.get("timeout_sec", 60)),
            max_messages=int(os.getenv("LLM_MAX_MESSAGES") or llm_raw.get("max_messages", 60)),
            max_chars_per_message=int(os.getenv("LLM_MAX_CHARS_PER_MESSAGE") or llm_raw.get("max_chars_per_message", 500)),
        ),
        portfolio=_load_portfolio(raw),
    )


def validate_config(config: AppConfig, *, require_telegram: bool = False, require_bot: bool = False) -> None:
    errors: list[str] = []
    if require_telegram:
        if not config.telegram.api_id:
            errors.append("telegram.api_id or TELEGRAM_API_ID is required")
        if not config.telegram.api_hash:
            errors.append("telegram.api_hash or TELEGRAM_API_HASH is required")
        if not config.sources:
            errors.append("sources or TELEGRAM_SOURCES is required")
    if require_bot:
        if not config.bot.token:
            errors.append("bot.token or TELEGRAM_BOT_TOKEN is required")
        if not config.bot.chat_id:
            errors.append("bot.chat_id or TELEGRAM_CHAT_ID is required")
    if not config.portfolio:
        errors.append("portfolio.holdings must contain at least one holding")
    if not 0 <= config.daily_digest_hour <= 23:
        errors.append("daily_digest_hour must be between 0 and 23")
    if config.catch_up_max_days < 1:
        errors.append("catch_up_max_days must be at least 1")
    if errors:
        raise ValueError("; ".join(errors))


def _load_portfolio(raw: dict[str, Any]) -> tuple[PortfolioHolding, ...]:
    holdings = raw.get("portfolio", {}).get("holdings") if isinstance(raw.get("portfolio"), dict) else None
    if not holdings:
        return default_portfolio()
    result: list[PortfolioHolding] = []
    for item in holdings:
        result.append(
            PortfolioHolding(
                ticker=str(item["ticker"]),
                display_name=str(item.get("display_name") or item["ticker"]),
                emoji=str(item.get("emoji") or "📌"),
                aliases=tuple(str(value) for value in item.get("aliases", ())),
                keywords=tuple(str(value) for value in item.get("keywords", ())),
            )
        )
    return tuple(result)


def _env_list(name: str) -> tuple[str, ...]:
    value = os.getenv(name, "")
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}
