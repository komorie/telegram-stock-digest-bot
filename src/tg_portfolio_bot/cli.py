from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timedelta

from .collector import collect_messages
from .config import load_config, load_env_file, validate_config
from .digest import DigestBuildError, build_digest, digest_hash
from .periods import (
    DigestPeriod,
    latest_completed_daily_end,
    load_timezone,
    make_cursor_period,
    make_lookback_period,
    period_label,
)
from .sender import send_digest
from .storage import MessageStore


def main(argv: list[str] | None = None) -> int:
    """명령줄 실행 진입점.

    이 함수는 앱의 교통정리 역할을 한다.
    - collect: Telegram -> SQLite
    - digest: SQLite -> 터미널 출력
    - run: Telegram -> SQLite -> 다이제스트 -> 선택적으로 텔레그램 봇 발송
    - catch-up: 11시 기준으로 누락된 daily digest를 순서대로 처리
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
        period = _period(config.timezone, config.lookback_hours, args.date)
        _log("Collecting Telegram messages. First run may ask for phone/code/password...")
        inserted = asyncio.run(_collect(config, store, period.start_utc))
        print(f"Inserted {inserted} new messages.")
        return 0
    if args.command == "digest":
        period = _period(config.timezone, config.lookback_hours, args.date)
        try:
            digest = _render(config, store, period)
        except DigestBuildError as exc:
            print(f"Digest was not generated: {exc}")
            return 1
        print(digest)
        return 0
    if args.command == "run":
        period = _period(config.timezone, config.lookback_hours, args.date)
        if not args.skip_collect:
            validate_config(config, require_telegram=True)
            _log("Collecting Telegram messages. First run may ask for phone/code/password...")
            inserted = asyncio.run(_collect(config, store, period.start_utc))
            print(f"Inserted {inserted} new messages.")
        _log("Building digest...")
        try:
            digest = _render(config, store, period)
        except DigestBuildError as exc:
            print(f"Digest was not generated: {exc}")
            return 1
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
        store.record_sent_digest(digest_id, period.start_utc, period.end_utc)
        print("Digest sent.")
        return 0
    if args.command == "catch-up":
        return _catch_up(config, store, args)
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
    period: DigestPeriod,
    *,
    label: str | None = None,
) -> str:
    # digest.py는 텔레그램과 통신하지 않고, 저장된 메시지를 보기 좋게 포맷만 한다.
    messages = store.list_messages(period.start_utc, period.end_utc)
    return build_digest(
        messages,
        config,
        start_local=period.start_local,
        end_local=period.end_local,
        period_label_override=label,
    )


def _period(
    timezone_name: str,
    lookback_hours: int,
    selected_date: str | None,
) -> DigestPeriod:
    # 사용자는 로컬 날짜로 생각하지만, 텔레그램 타임스탬프와 DB 필터는 UTC를 쓴다.
    # make_lookback_period가 로컬 시간과 UTC 시간을 함께 가진 값으로 돌려준다.
    return make_lookback_period(timezone_name, lookback_hours, selected_date)


def _catch_up(config, store: MessageStore, args) -> int:
    periods = _daily_periods_to_run(config, store, max_days=args.max_days, force=args.force_send)
    if not periods:
        print("No catch-up periods to process.")
        return 0

    if not args.skip_collect:
        validate_config(config, require_telegram=True)
        _log(f"Collecting Telegram messages from {periods[0].start_local.isoformat()}...")
        inserted = asyncio.run(_collect(config, store, periods[0].start_utc))
        print(f"Inserted {inserted} new messages.")

    if not (args.dry_run or args.no_send):
        validate_config(config, require_bot=True)

    for index, period in enumerate(periods, start=1):
        label = period_label(period)
        _log(f"Building digest {index}/{len(periods)}: {label}")
        try:
            digest = _render(config, store, period, label=label)
        except DigestBuildError as exc:
            print(f"Digest was not generated for {label}: {exc}")
            return 1
        digest_id = digest_hash(digest)

        if args.dry_run or args.no_send:
            print("")
            print("=" * 80)
            print(digest)
            continue

        _log(f"Sending digest {index}/{len(periods)}...")
        send_digest(config.bot.token, config.bot.chat_id, digest)
        store.record_daily_digest(
            period_key=period.key,
            digest_hash=digest_id,
            start_utc=period.start_utc,
            end_utc=period.end_utc,
        )
        print(f"Sent daily digest: {label}")

    return 0


def _daily_periods_to_run(
    config,
    store: MessageStore,
    *,
    max_days: int | None,
    force: bool,
    now: datetime | None = None,
) -> list[DigestPeriod]:
    now_local = (now or datetime.now(load_timezone(config.timezone))).astimezone(load_timezone(config.timezone))
    latest_end_local = latest_completed_daily_end(config.timezone, config.daily_digest_hour, now=now_local)
    limit = max_days or config.catch_up_max_days

    last_sent_end = None if force else store.latest_daily_period_end()
    if last_sent_end is None:
        start_local = latest_end_local - timedelta(days=1)
    else:
        start_local = last_sent_end.astimezone(now_local.tzinfo)

    candidates = _split_cursor_periods(start_local, now_local, config.daily_digest_hour)
    selected = candidates[:limit]
    if force:
        return selected
    return [period for period in selected if not store.has_sent_daily_period(period.key)]


def _split_cursor_periods(start_local: datetime, now_local: datetime, cutoff_hour: int) -> list[DigestPeriod]:
    """마지막 발송 이후의 기간을 필요한 만큼만 쪼갠다.

    11시 경계가 아직 안 지났으면 보낼 것이 없다.
    경계가 1개만 지났으면 늦게 실행된 것으로 보고 현재 시각까지 한 덩어리로 보낸다.
    경계가 2개 이상 지났으면 오래된 구간만 11시 기준으로 끊고 마지막 구간은 현재까지 묶는다.
    """

    boundaries = _cutoff_boundaries_after(start_local, now_local, cutoff_hour)
    if not boundaries:
        return []

    cut_points = [start_local]
    if len(boundaries) >= 2:
        cut_points.extend(boundaries[:-1])
    cut_points.append(now_local)

    periods: list[DigestPeriod] = []
    for start, end in zip(cut_points, cut_points[1:]):
        if end > start:
            periods.append(make_cursor_period(start, end))
    return periods


def _cutoff_boundaries_after(start_local: datetime, now_local: datetime, cutoff_hour: int) -> list[datetime]:
    first = start_local.replace(hour=cutoff_hour, minute=0, second=0, microsecond=0)
    if first <= start_local:
        first += timedelta(days=1)

    boundaries: list[datetime] = []
    current = first
    while current <= now_local:
        boundaries.append(current)
        current += timedelta(days=1)
    return boundaries


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

    catch_up_parser = subparsers.add_parser("catch-up", parents=[common])
    catch_up_parser.add_argument("--dry-run", action="store_true", help="Print digests instead of sending")
    catch_up_parser.add_argument("--no-send", action="store_true", help="Do not send; print digests")
    catch_up_parser.add_argument("--force-send", action="store_true", help="Ignore daily sent-period history")
    catch_up_parser.add_argument("--skip-collect", action="store_true", help="Use existing DB messages only")
    catch_up_parser.add_argument("--max-days", type=int, help="Maximum daily periods to process")

    return parser


if __name__ == "__main__":
    raise SystemExit(main())
