from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from utils.admin_access import admin_access

ADMIN_CHANNEL_URL = "https://t.me/+ezE2-f-YtEo4NzU1"
UPDATE_CHANNEL_URL = "https://t.me/+JUGpWnRLT8ljNGZk"

async def home_kb(uid: int, lang: str = "id"):
    """Inline buttons shown directly under the welcome message: channel links only."""
    en = lang == "en"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📣 Admin Channel" if en else "📣 Channel Admin", url=ADMIN_CHANNEL_URL),
         InlineKeyboardButton(text="📢 Updates Channel" if en else "📢 Channel Update", url=UPDATE_CHANNEL_URL)]
    ])

def channel_reply_kb(lang: str = "id", is_admin: bool = False):
    """Persistent keyboard under the chat input: main menu actions."""
    en = lang == "en"
    labels = [
        KeyboardButton(text="⭐ Review"),
        KeyboardButton(text="📥 Buka Media" if not en else "📥 Open Media"),
        KeyboardButton(text="💎 VIP"),
        KeyboardButton(text="🔑 Code"),
        KeyboardButton(text="❓ Bantuan" if not en else "❓ Help"),
    ]
    rows = [[labels[0], labels[1]], [labels[2], labels[3]], [labels[4]]]
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Pilih menu atau kirim kode…" if not en else "Choose a menu or send a code…",
    )
