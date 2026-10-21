from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.admin_access import admin_access

NOTIFY_URL = "https://t.me/noticsaluran"
BACKUP_URL = "https://t.me/channeljsshow"

async def home_kb(uid: int, lang: str = "id"):
    en = lang == "en"
    admin = await admin_access(uid)
    labels = {
        "review": "⭐ Review" if not en else "⭐ Review",
        "getfile": "📥 Getfile" if not en else "📥 Getfile",
        "vip": "💎 VIP",
        "code": "🔑 Code",
        "help": "❓ Help",
        "upfile": "📤 Upfile",
        "notify": "📢 Channel Notifikasi" if not en else "📢 Notification Channel",
        "backup": "💾 Channel Backup" if not en else "💾 Backup Channel",
    }
    rows = []
    if admin:
        rows.append([InlineKeyboardButton(text=labels["upfile"], callback_data="upfile"), InlineKeyboardButton(text=labels["getfile"], callback_data="getfile")])
    else:
        rows.append([InlineKeyboardButton(text=labels["review"], callback_data="review"), InlineKeyboardButton(text=labels["getfile"], callback_data="getfile")])
    rows.append([InlineKeyboardButton(text=labels["vip"], callback_data="buy_vip"), InlineKeyboardButton(text=labels["code"], callback_data="code_all"), InlineKeyboardButton(text=labels["help"], callback_data="help")])
    rows.append([InlineKeyboardButton(text=labels["notify"], url=NOTIFY_URL), InlineKeyboardButton(text=labels["backup"], url=BACKUP_URL)])
    return InlineKeyboardMarkup(inline_keyboard=rows)

