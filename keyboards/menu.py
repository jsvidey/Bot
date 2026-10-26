from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from utils.admin_access import admin_access

# These two destinations are intentionally shown as regular reply-keyboard buttons.
from config import TRANSACTION_CHANNEL_URL, NOTICE_CHANNEL_URL
CHANNEL_ADMIN_URL = __import__("os").getenv("CHANNEL_ADMIN_URL", TRANSACTION_CHANNEL_URL).strip()
CHANNEL_UPDATE_URL = __import__("os").getenv("CHANNEL_UPDATE_URL", NOTICE_CHANNEL_URL).strip()

async def channel_reply_kb(lang: str = "id"):
    en = lang == "en"
    return ReplyKeyboardMarkup(
        keyboard=[[
            KeyboardButton(text="📣 Channel Admin" if not en else "📣 Admin Channel"),
            KeyboardButton(text="📢 Channel Update" if not en else "📢 Updates Channel"),
        ]],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Pilih menu / Choose a menu"
    )

async def home_kb(uid: int, lang: str = "id"):
    en = lang == "en"
    admin = await admin_access(uid)
    labels = {
        "review": "⭐ Review" if not en else "⭐ Review",
        "getfile": "📥 Buka Media" if not en else "📥 Open Media",
        "vip": "💎 VIP",
        "code": "🔑 Daftar Code" if not en else "🔑 Browse Codes",
        "help": "❓ Bantuan" if not en else "❓ Help",
        "upfile": "📤 Upload Media" if not en else "📤 Upload Media",
    }
    rows = []
    if admin:
        rows.append([InlineKeyboardButton(text=labels["upfile"], callback_data="upfile"), InlineKeyboardButton(text=labels["getfile"], callback_data="getfile")])
    else:
        rows.append([InlineKeyboardButton(text=labels["review"], callback_data="review"), InlineKeyboardButton(text=labels["getfile"], callback_data="getfile")])
    rows.append([InlineKeyboardButton(text=labels["vip"], callback_data="buy_vip"), InlineKeyboardButton(text=labels["code"], callback_data="code_all"), InlineKeyboardButton(text=labels["help"], callback_data="help")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

