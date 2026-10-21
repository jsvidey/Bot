from __future__ import annotations
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from typing import Any, Awaitable, Callable, Dict
from config import FORCE_CHANNEL_ID, NOTICE_SUB_CHANNEL_ID, FORCE_CHANNEL_URL, NOTICE_SUB_CHANNEL_URL, FORCE_CHANNEL_USERNAME, NOTICE_SUB_CHANNEL_USERNAME
from utils.admin_access import admin_access


def _url(explicit: str, username: str, fallback_id: int = 0) -> str:
    if explicit:
        return explicit
    if username:
        return f"https://t.me/{username.lstrip('@')}"
    return ""

async def _joined(bot, chat_id, user_id: int, username: str = "") -> bool:
    target = chat_id or (f"@{username.lstrip('@')}" if username else None)
    if not target:
        return True
    try:
        member = await bot.get_chat_member(target, user_id)
        status = getattr(member, "status", "")
        if status in {"creator", "administrator", "member"}:
            return True
        if status == "restricted":
            return bool(getattr(member, "is_member", False))
        return False
    except (TelegramBadRequest, TelegramForbiddenError):
        return False
    except Exception:
        return False

async def _channels_from_settings():
    """Allow owner/admin to manage required channels from the admin panel.

    Environment variables remain the fallback for existing installations.
    Empty/0 database values do not accidentally disable the environment config
    unless the corresponding key has explicitly been set to a meaningful value.
    """
    values = {}
    try:
        from database import get_pool
        rows = await (await get_pool()).fetch("SELECT key,value FROM settings WHERE key IN ('force_channel_id','force_channel_username','force_channel_url','notice_sub_channel_id','notice_sub_channel_username','notice_sub_channel_url')")
        values = {str(r['key']): str(r['value'] or '').strip() for r in rows}
    except Exception:
        pass
    def integer(key, fallback):
        raw = values.get(key, '')
        if not raw: return fallback
        try: return int(raw)
        except ValueError: return fallback
    def text(key, fallback):
        raw = values.get(key, '')
        if not raw: return fallback
        if raw == '-': return ''
        return raw
    return (
        integer('force_channel_id', FORCE_CHANNEL_ID),
        text('force_channel_username', FORCE_CHANNEL_USERNAME),
        text('force_channel_url', FORCE_CHANNEL_URL),
        integer('notice_sub_channel_id', NOTICE_SUB_CHANNEL_ID),
        text('notice_sub_channel_username', NOTICE_SUB_CHANNEL_USERNAME),
        text('notice_sub_channel_url', NOTICE_SUB_CHANNEL_URL),
    )

async def missing_subscription_channels(bot, user_id: int):
    missing=[]
    force_id, force_user, force_url, notice_id, notice_user, notice_url = await _channels_from_settings()
    channels = [
        (force_id, force_user, "📢 Channel Notifikasi", "Notification Channel", _url(force_url, force_user)),
        (notice_id, notice_user, "💾 Channel Backup", "Backup Channel", _url(notice_url, notice_user)),
    ]
    for cid, username, label_id, label_en, url in channels:
        if (cid or username) and not await _joined(bot, cid, user_id, username):
            missing.append((label_id, url))
    return missing

async def subscription_prompt(bot, chat_id: int, user_id: int):
    missing=await missing_subscription_channels(bot,user_id)
    if not missing: return True
    rows=[]
    force_id, force_user, force_url, notice_id, notice_user, notice_url = await _channels_from_settings()
    channels=[
        (force_id, force_user, "📢 Channel Notifikasi", _url(force_url, force_user)),
        (notice_id, notice_user, "💾 Channel Backup", _url(notice_url, notice_user)),
    ]
    for cid, username, label, url in channels:
        if (cid or username) and url:
            rows.append([InlineKeyboardButton(text=label, url=url)])
    rows.append([InlineKeyboardButton(text="🔄 Verifikasi Join / Verify Join", callback_data="verify_join")])
    await bot.send_message(chat_id,
        "⚠️ <b>Wajib bergabung terlebih dahulu</b>\nSilakan join kedua channel di bawah, lalu tekan Verifikasi Join.\n\n"
        "⚠️ <b>Please join first</b>\nJoin both channels below, then tap Verify Join.",
        parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    return False

class SubscriptionMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable[[Any, Dict[str, Any]], Awaitable[Any]], event: Any, data: Dict[str, Any]):
        user=getattr(event,"from_user",None)
        if not user: return await handler(event,data)
        # Admin operations bypass Force-Join, but /start and language selection
        # still follow the required two-channel onboarding for every account.
        is_admin = await admin_access(user.id)
        if is_admin:
            if isinstance(event, Message):
                token=(event.text or "").strip().split()[0].lower() if event.text else ""
                if token.split("@",1)[0] != "/start":
                    return await handler(event,data)
            elif isinstance(event, CallbackQuery):
                if event.data != "verify_join" and not str(event.data or "").startswith("lang:"):
                    return await handler(event,data)
        if isinstance(event,Message):
            token=(event.text or "").strip().split()[0].lower() if event.text else ""
            command=token.split("@",1)[0]
            if command in {"/admin","/panel","/getqrisid"}:
                return await handler(event,data)
        chat=getattr(event,"chat",None)
        if chat is not None and getattr(chat,"type",None)!="private":
            return await handler(event,data)
        if isinstance(event,CallbackQuery) and event.data=="verify_join":
            return await handler(event,data)
        if await subscription_prompt(event.bot,user.id,user.id):
            return await handler(event,data)
        return None
