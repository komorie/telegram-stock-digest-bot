from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .collector import collect_messages
from .config import load_config, load_env_file, validate_config
from .digest import build_digest, digest_hash
from .sender import send_digest
from .storage import MessageStore


def main(argv: list[str] | None = None) -> int:
    """명령줄 실행 진입점.

    이 함수는 앱의 교통정리 역할을 한다.
    - collect: Telegram -> SQLite
    - digest: SQLite -> 터미널 출력
    - run: Telegram -> SQLite -> 다이제스트 -> 선택적으로 텔레그램 봇 발송
    """
    _configure_console_encoding()
    parser = _build_parser()
    args = parser.parse_args(argv)
    _log("Loading configuration...")
    load_env_file(args.env_file)
    config = load_config(args.config)
    store = MessageStore(config.database_path)
    _log(f"Initializing database: {config.database_path}")
    store.init()

    if args.command == "init-db":
        print(f"Initialized database: {config.database_path}")
        return 0
    if args.command == "collect":
        validate_config(config, require_telegram=True)
        start_utc, _end_utc, _start_local, _end_local = _period(config.timezone, config.lookback_hours, args.date)
        _log("Collecting Telegram messages. First run may ask for phone/code/password...")
        inserted = asyncio.run(_collect(config, store, start_utc))
        print(f"Inserted {inserted} new messages.")
        return 0
    if args.command == "digest":
        start_utc, end_utc, start_local, end_local = _period(config.timezone, config.lookback_hours, args.date)
        digest = _render(config, store, start_utc, end_utc, start_local, end_local)
        print(digest)
        return 0
    if args.command == "run":
        start_utc, end_utc, start_local, end_local = _period(config.timezone, config.lookback_hours, args.date)
        if not args.skip_collect:
            validate_config(config, require_telegram=True)
            _log("Collecting Telegram messages. First run may ask for phone/code/password...")
            inserted = asyncio.run(_collect(config, store, start_utc))
            print(f"Inserted {inserted} new messages.")
        _log("Building digest...")
        digest = _render(config, store, start_utc, end_utc, start_local, end_local)
        digest_id = digest_hash(digest)
        if args.dry_run or args.no_send:
            print(digest)
            return 0
        validate_config(config, require_bot=True)
        if store.has_sent_digest(digest_id) and not args.force_send:
            print("Digest already sent. Use --force-send to send again.")
            return 0
        _log("Sending digest to Telegram bot chat...")
        send_digest(config.bot.token, config.bot.chat_id, digest)
        store.record_sent_digest(digest_id, start_utc, end_utc)
        print("Digest sent.")
        return 0
    parser.error(f"Unknown command: {args.command}")
    return 2


def _configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _log(message: str) -> None:
    print(f"[tg-portfolio-bot] {message}", flush=True)


async def _collect(config, store: MessageStore, start_utc: datetime) -> int:
    # 텔레그램 통신은 collector.py에 맡기고, 여기서는 정규화된 메시지만 DB에 저장한다.
    messages = await collect_messages(
        config.telegram,
        config.sources,
        start_utc=start_utc,
        max_messages_per_channel=config.max_messages_per_channel,
    )
    return store.upsert_messages(messages)


def _render(
    config,
    store: MessageStore,
    start_utc: datetime,
    end_utc: datetime,
    start_local: datetime,
    end_local: datetime,
) -> str:
    # digest.py는 텔레그램과 통신하지 않고, 저장된 메시지를 보기 좋게 포맷만 한다.
    messages = store.list_messages(start_utc, end_utc)
    return build_digest(messages, config, start_local=start_local, end_local=end_local)


def _period(
    timezone_name: str,
    lookback_hours: int,
    selected_date: str | None,
) -> tuple[datetime, datetime, datetime, datetime]:
    # 사용자는 로컬 날짜로 생각하지만, 텔레그램 타임스탬프와 DB 필터는 UTC를 쓴다.
    # 그래서 각 계층이 필요한 표현을 쓰도록 로컬 시간과 UTC 시간을 모두 돌려준다.
    tz = _load_timezone(timezone_name)
    if selected_date:
        day = date.fromisoformat(selected_date)
        start_local = datetime.combine(day, time.min, tzinfo=tz)
        end_local = start_local + timedelta(days=1)
    else:
        end_local = datetime.now(tz)
        start_local = end_local - timedelta(hours=lookback_hours)
    return (
        start_local.astimezone(UTC),
        end_local.astimezone(UTC),
        start_local,
        end_local,
    )


def _load_timezone(timezone_name: str):
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        if timezone_name == "Asia/Seoul":
            return timezone(timedelta(hours=9), name="Asia/Seoul")
        raise


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", default="config.toml")
    common.add_argument("--env-file", default=".env")

    parser = argparse.ArgumentParser(prog="tg-portfolio-bot", parents=[common])
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init-db", parents=[common])

    collect_parser = subparsers.add_parser("collect", parents=[common])
    collect_parser.add_argument("--date", help="Local date to collect from, YYYY-MM-DD")

    digest_parser = subparsers.add_parser("digest", parents=[common])
    digest_parser.add_argument("--date", help="Local date to render, YYYY-MM-DD")

    run_parser = subparsers.add_parser("run", parents=[common])
    run_parser.add_argument("--date", help="Local date to render, YYYY-MM-DD")
    run_parser.add_argument("--dry-run", action="store_true", help="Print digest instead of sending")
    run_parser.add_argument("--no-send", action="store_true", help="Do not send; print digest")
    run_parser.add_argument("--force-send", action="store_true", help="Send even if same digest was sent")
    run_parser.add_argument("--skip-collect", action="store_true", help="Use existing DB messages only")

    return parser


if __name__ == "__main__":
    raise SystemExit(main())
