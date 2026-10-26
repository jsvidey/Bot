from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.admin_access import admin_access

ADMIN_CHANNEL_URL = "https://t.me/+ezE2-f-YtEo4NzU1"
UPDATE_CHANNEL_URL = "https://t.me/+JUGpWnRLT8ljNGZk"

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
        "admin_channel": "👑 Channel Admin" if not en else "👑 Admin Channel",
        "update_channel": "📢 Channel Update" if not en else "📢 Update Channel",
    }
    rows = []
    if admin:
        rows.append([InlineKeyboardButton(text=labels["upfile"], callback_data="upfile"), InlineKeyboardButton(text=labels["getfile"], callback_data="getfile")])
    else:
        rows.append([InlineKeyboardButton(text=labels["review"], callback_data="review"), InlineKeyboardButton(text=labels["getfile"], callback_data="getfile")])
    rows.append([InlineKeyboardButton(text=labels["vip"], callback_data="buy_vip"), InlineKeyboardButton(text=labels["code"], callback_data="code_all"), InlineKeyboardButton(text=labels["help"], callback_data="help")])
    rows.append([InlineKeyboardButton(text=labels["admin_channel"], url=ADMIN_CHANNEL_URL), InlineKeyboardButton(text=labels["update_channel"], url=UPDATE_CHANNEL_URL)])
    return InlineKeyboardMarkup(inline_keyboard=rows)



from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def bottom_menu_kb(lang: str = "id"):
    en = lang == "en"
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📥 Kirim Kode" if not en else "📥 Send Code"), KeyboardButton(text="💎 Paket VIP" if not en else "💎 VIP Packages")],
            [KeyboardButton(text="🌐 Bahasa / Language"), KeyboardButton(text="🏠 Beranda" if not en else "🏠 Home")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Pilih menu atau kirim kode…" if not en else "Choose a menu or send a code…",
    )
