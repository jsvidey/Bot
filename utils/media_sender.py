from __future__ import annotations
import os
import logging
from aiogram.types import FSInputFile
from aiogram.exceptions import TelegramBadRequest
from utils.b2_storage import b2_pool

logger = logging.getLogger(__name__)

def _value(media, *keys):
    """Read media fields safely from dict-like JSONB records."""
    for key in keys:
        try:
            value = media.get(key)
        except Exception:
            value = None
        if value not in (None, ""):
            return value
    return None

async def deliver_one(bot, chat_id, media, caption=None, reply_markup=None, protect_content=False):
    """Download from B2 and send. If Telegram rejects video encoding, send as document."""
    account = _value(media, "drive_account", "b2_account")
    key = _value(media, "drive_file_id", "b2_file_id", "storage_key")
    if account is None or not key:
        raise RuntimeError("Backblaze metadata tidak tersedia")

    path, meta = await b2_pool.download(int(account), str(key))
    try:
        typ = str(_value(media, "type", "media_type") or "document").lower().strip()
        inp = FSInputFile(path)
        common = dict(caption=caption, parse_mode="HTML", reply_markup=reply_markup,
                      protect_content=protect_content)
        try:
            if typ in ("photo", "image", "jpg", "jpeg", "png"):
                return await bot.send_photo(chat_id, inp, **common)
            if typ in ("video", "mp4", "mov", "mkv", "webm"):
                try:
                    return await bot.send_video(chat_id, inp, **common)
                except TelegramBadRequest as exc:
                    # Some MP4s are valid files but Telegram cannot process them as video.
                    logger.warning("send_video rejected B2 file; retrying as document: account=%s key=%s error=%s",
                                   account, key, str(exc)[:500])
                    return await bot.send_document(chat_id, FSInputFile(path), **common)
            if typ in ("audio", "mp3", "m4a", "ogg", "wav"):
                try:
                    return await bot.send_audio(chat_id, inp, **common)
                except TelegramBadRequest as exc:
                    logger.warning("send_audio rejected B2 file; retrying as document: account=%s key=%s error=%s",
                                   account, key, str(exc)[:500])
                    return await bot.send_document(chat_id, FSInputFile(path), **common)
            return await bot.send_document(chat_id, inp, **common)
        except Exception:
            logger.exception("B2 file downloaded but Telegram delivery failed: chat_id=%s account=%s key=%s type=%s size=%s",
                              chat_id, account, key, typ, meta.get("ContentLength"))
            raise
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

async def deliver_telegram_file_id(bot, chat_id, media, caption=None, reply_markup=None, protect_content=False):
    """Fallback to a Telegram file_id, if it belongs to the current bot."""
    fid = _value(media, "telegram_file_id", "file_id", "telegram_id", "telegram_file")
    if not fid:
        raise RuntimeError("Telegram file_id tidak tersedia")
    typ = str(_value(media, "type", "media_type") or "document").lower().strip()
    common = dict(caption=caption, parse_mode="HTML", reply_markup=reply_markup,
                  protect_content=protect_content)
    if typ in ("photo", "image", "jpg", "jpeg", "png"):
        return await bot.send_photo(chat_id, fid, **common)
    if typ in ("video", "mp4", "mov", "mkv", "webm"):
        return await bot.send_video(chat_id, fid, **common)
    if typ in ("audio", "mp3", "m4a", "ogg", "wav"):
        return await bot.send_audio(chat_id, fid, **common)
    return await bot.send_document(chat_id, fid, **common)
