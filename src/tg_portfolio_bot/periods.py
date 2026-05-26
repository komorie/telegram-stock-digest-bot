from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class DigestPeriod:
    """다이제스트 하나가 담당하는 로컬/UTC 시간 구간."""

    key: str
    start_local: datetime
    end_local: datetime
    start_utc: datetime
    end_utc: datetime


def load_timezone(timezone_name: str):
    """Windows에서 tzdata가 없을 때 Asia/Seoul만 안전하게 대체한다."""

    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        if timezone_name == "Asia/Seoul":
            return timezone(timedelta(hours=9), name="Asia/Seoul")
        raise


def make_lookback_period(
    timezone_name: str,
    lookback_hours: int,
    selected_date: str | None,
) -> DigestPeriod:
    """기존 run/digest 명령용 기간을 만든다.

    selected_date가 있으면 해당 로컬 날짜의 00:00~24:00을 사용하고,
    없으면 지금부터 lookback_hours만큼 뒤를 본다.
    """

    tz = load_timezone(timezone_name)
    if selected_date:
        day = date.fromisoformat(selected_date)
        start_local = datetime.combine(day, time.min, tzinfo=tz)
        end_local = start_local + timedelta(days=1)
        key = day.isoformat()
    else:
        end_local = datetime.now(tz)
        start_local = end_local - timedelta(hours=lookback_hours)
        key = f"lookback-{int(start_local.timestamp())}-{int(end_local.timestamp())}"
    return _period_from_local(key, start_local, end_local)


def make_daily_period(
    timezone_name: str,
    end_date: date,
    cutoff_hour: int,
) -> DigestPeriod:
    """전날 cutoff_hour부터 end_date의 cutoff_hour 직전까지의 기간을 만든다."""

    tz = load_timezone(timezone_name)
    end_local = datetime.combine(end_date, time(hour=cutoff_hour), tzinfo=tz)
    start_local = end_local - timedelta(days=1)
    return _period_from_local(end_date.isoformat(), start_local, end_local)


def make_cursor_period(start_local: datetime, end_local: datetime) -> DigestPeriod:
    """마지막 발송 시각부터 현재 실행 시각까지의 유동 기간을 만든다."""

    key = f"cursor-{start_local.isoformat()}-{end_local.isoformat()}"
    return _period_from_local(key, start_local, end_local)


def latest_completed_daily_end(
    timezone_name: str,
    cutoff_hour: int,
    *,
    now: datetime | None = None,
) -> datetime:
    """현재 시각 기준으로 이미 닫힌 가장 최근 daily 기간의 end_local을 반환한다."""

    tz = load_timezone(timezone_name)
    now_local = (now or datetime.now(tz)).astimezone(tz)
    today_cutoff = datetime.combine(now_local.date(), time(hour=cutoff_hour), tzinfo=tz)
    if now_local >= today_cutoff:
        return today_cutoff
    return today_cutoff - timedelta(days=1)


def period_label(period: DigestPeriod) -> str:
    """사용자에게 보여줄 기간 라벨.

    end_local은 DB 필터에서 제외되는 경계값이다. 정각 11:00처럼 daily 경계로 끝나는
    기간은 사람이 보기 좋게 10:59까지로 표시하고, 늦게 실행되어 현재 시각으로 끝나는
    기간은 그 시각을 그대로 보여준다.
    """

    display_end = period.end_local
    if period.end_local.minute == 0 and period.end_local.second == 0 and period.end_local.microsecond == 0:
        display_end = period.end_local - timedelta(minutes=1)
    return f"{_datetime_label(period.start_local)} ~ {_datetime_label(display_end)}"


def _period_from_local(key: str, start_local: datetime, end_local: datetime) -> DigestPeriod:
    return DigestPeriod(
        key=key,
        start_local=start_local,
        end_local=end_local,
        start_utc=start_local.astimezone(UTC),
        end_utc=end_local.astimezone(UTC),
    )


def _datetime_label(value: datetime) -> str:
    return f"{value.year}년 {value.month}월 {value.day}일 {value.hour:02d}:{value.minute:02d}"
