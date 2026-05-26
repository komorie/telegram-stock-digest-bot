from __future__ import annotations

import getpass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import TelegramConfig
from .models import CollectedMessage


async def collect_messages(
    telegram: TelegramConfig,
    sources: tuple[str, ...],
    *,
    start_utc: datetime,
    max_messages_per_channel: int,
) -> tuple[CollectedMessage, ...]:
    """사용자 계정 세션으로 최근 텔레그램 메시지를 읽는다.

    Bot API는 봇이 들어가 있지 않은 비공개 채널이나 파일 단독 게시물을 안정적으로 읽기 어렵다.
    Telethon은 사용자의 실제 텔레그램 세션을 사용하므로, 사용자가 볼 수 있는 채널과 PDF 업로드를
    동일하게 볼 수 있다.
    """
    try:
        from telethon import TelegramClient
        from telethon.errors import SessionPasswordNeededError
    except ImportError as exc:
        raise RuntimeError("Telethon is not installed. Run: pip install -e .") from exc

    Path(telegram.session_path).parent.mkdir(parents=True, exist_ok=True)
    client = TelegramClient(str(telegram.session_path), telegram.api_id, telegram.api_hash)
    await client.connect()
    try:
        # 첫 실행 때 data/telegram.session을 만들고, 이후 실행에서는 이 세션을 재사용해 로그인을 건너뛴다.
        if not await client.is_user_authorized():
            phone = input("Telegram phone number with country code, e.g. +821012345678: ").strip()
            if not phone:
                raise RuntimeError("Telegram phone number is required for first login.")
            await client.send_code_request(phone)
            code = input("Telegram login code: ").strip()
            try:
                await client.sign_in(phone=phone, code=code)
            except SessionPasswordNeededError:
                password = getpass.getpass("Telegram 2FA password: ")
                await client.sign_in(password=password)

        collected: list[CollectedMessage] = []
        for source in sources:
            print(f"[tg-portfolio-bot] Reading source: {source}", flush=True)
            entity = await client.get_entity(source)
            async for message in client.iter_messages(entity, limit=max_messages_per_channel):
                date_utc = _as_utc(message.date)
                if date_utc < start_utc.astimezone(UTC):
                    break
                collected_message = _to_collected_message(entity, message, date_utc)
                # 빈 시스템 메시지는 버리고, 파일 단독 게시물은 file_name이 있으므로 보존한다.
                if collected_message.text.strip() or collected_message.file_name:
                    collected.append(collected_message)
        return tuple(collected)
    finally:
        await client.disconnect()


def _to_collected_message(entity: Any, message: Any, date_utc: datetime) -> CollectedMessage:
    # Telethon의 복잡한 Message 객체를 이 앱에서 쓰는 작은 모델로 변환한다.
    file_name = _file_name(message)
    mime_type = _mime_type(message)
    is_document = bool(getattr(message, "document", None) or file_name)
    is_pdf = bool(
        (file_name and file_name.casefold().endswith(".pdf"))
        or (mime_type and mime_type.casefold() == "application/pdf")
    )
    username = getattr(entity, "username", None)
    channel_id = str(getattr(entity, "id", getattr(message, "chat_id", "")))
    return CollectedMessage(
        channel_id=channel_id,
        message_id=int(message.id),
        channel_title=str(getattr(entity, "title", None) or getattr(entity, "first_name", None) or channel_id),
        channel_username=username,
        date_utc=date_utc,
        text=str(getattr(message, "message", None) or ""),
        url=_message_url(entity, int(message.id)),
        file_name=file_name,
        mime_type=mime_type,
        is_document=is_document,
        is_pdf=is_pdf,
    )


def _file_name(message: Any) -> str | None:
    file_obj = getattr(message, "file", None)
    name = getattr(file_obj, "name", None)
    if name:
        return str(name)
    document = getattr(message, "document", None)
    for attr in getattr(document, "attributes", ()) or ():
        file_name = getattr(attr, "file_name", None)
        if file_name:
            return str(file_name)
    return None


def _mime_type(message: Any) -> str | None:
    file_obj = getattr(message, "file", None)
    mime_type = getattr(file_obj, "mime_type", None)
    if mime_type:
        return str(mime_type)
    document = getattr(message, "document", None)
    mime_type = getattr(document, "mime_type", None)
    return str(mime_type) if mime_type else None


def _message_url(entity: Any, message_id: int) -> str | None:
    username = getattr(entity, "username", None)
    if username:
        return f"https://t.me/{username}/{message_id}"
    entity_id = getattr(entity, "id", None)
    if entity_id:
        return f"https://t.me/c/{entity_id}/{message_id}"
    return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
