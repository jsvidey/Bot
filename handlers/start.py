from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_pool
from keyboards.menu import home_kb
from utils.economy import ensure_user
from middlewares.subscription import subscription_prompt
from utils.callback_loading import loading
from utils.i18n import get_lang, set_lang, SUPPORTED
from utils.admin_access import admin_access

router = Router()

WELCOME = {
    "id": "Halo, {name} yang terhormat.\n\nSelamat datang menggunakan <b>Bot Decoder</b>!\n📥 Kirim kode untuk membuka media.\n\n💎 <b>Gabung Anggota VIP &amp; dapatkan akses semua code secara gratis.</b>\n🏅 VIP 1 — Rp100.000/bulan\n🥇 VIP 2 — Rp50.000/15 hari\n🥈 VIP 3 — Rp35.000/7 hari\n🥉 VIP 4 — Rp25.000/2 hari\n\n• Sudah dapat akses semua media sesuai aturan paket\n• Paket aktif sesuai durasi dan ketentuan paket\n• Media bisa di-save &amp; share\n• Ada jaminan selama paket masih aktif\n\nJangan lupa gabung channel kami terlebih dahulu 🚀",
    "en": "Hello, dear {name}.\n\nWelcome to <b>Bot Decoder</b>!\n📥 Send a code to open its media.\n\n💎 <b>Join VIP and get access to all codes for free.</b>\n🏅 VIP 1 — Rp100,000/month\n🥇 VIP 2 — Rp50,000/15 days\n🥈 VIP 3 — Rp35,000/7 days\n🥉 VIP 4 — Rp25,000/2 days\n\n• Access media according to your package rules\n• Package access follows its duration and terms\n• Media can be saved and shared\n• Support is available while your package is active\n\nPlease join our channels first 🚀",
}

def language_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇮🇩 Indonesia", callback_data="lang:id"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
    ]])

async def language_prompt(target, edit=False):
    text = "🌐 <b>Pilih Bahasa / Choose Language</b>\n\nSilakan pilih bahasa bot / Please choose your bot language:"
    if edit:
        await target.edit_text(text, parse_mode="HTML", reply_markup=language_kb())
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=language_kb())

async def welcome_text(user, lang):
    name = user.full_name or user.username or str(user.id)
    import html
    return WELCOME.get(lang, WELCOME["id"]).format(name=html.escape(name))

async def show_welcome(target, user, lang, edit=False):
    text = await welcome_text(user, lang)
    kb = await home_kb(user.id, lang)
    if edit:
        try:
            await target.edit_text(text, parse_mode="HTML", reply_markup=kb)
        except Exception:
            await target.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await target.answer(text, parse_mode="HTML", reply_markup=kb)

@router.message(F.chat.type == "private", CommandStart())
async def start(m: Message):
    await ensure_user(m.from_user.id, m.from_user.username, m.from_user.full_name)
    p = await get_pool()
    await p.execute("UPDATE users SET bot_started_at=NOW() WHERE user_id=$1", m.from_user.id)
    if not await subscription_prompt(m.bot, m.chat.id, m.from_user.id):
        return
    lang = await get_lang(m.from_user.id)
    parts = (m.text or "").split(maxsplit=1)
    if not lang:
        pending = parts[1].strip() if len(parts) == 2 and parts[1].strip() else None
        await p.execute("UPDATE users SET pending_start_code=$1 WHERE user_id=$2", pending, m.from_user.id)
        return await language_prompt(m)
    if len(parts) == 2 and parts[1].strip():
        from handlers.getfile import show
        return await show(m, parts[1].strip())
    await show_welcome(m, m.from_user, lang)

@router.callback_query(F.data.startswith("lang:"))
async def choose_language(c: CallbackQuery):
    lang = c.data.split(":", 1)[1]
    if lang not in {"id", "en"}:
        return await c.answer("Language unavailable.", show_alert=True)
    if not await subscription_prompt(c.bot, c.from_user.id, c.from_user.id):
        return await c.answer("Join both required channels first.", show_alert=True)
    await set_lang(c.from_user.id, lang)
    try:
        import bot as botmod
        botmod._LANG_CACHE[c.from_user.id] = lang
    except Exception:
        pass
    p = await get_pool()
    pending = await p.fetchval("SELECT pending_start_code FROM users WHERE user_id=$1", c.from_user.id)
    await p.execute("UPDATE users SET pending_start_code=NULL WHERE user_id=$1", c.from_user.id)
    await c.answer()
    if pending:
        from handlers.getfile import show
        return await show(c.message, pending)
    await show_welcome(c.message, c.from_user, lang, edit=True)

@router.message(F.chat.type == "private", Command("setting"))
async def setting(m: Message):
    if not await subscription_prompt(m.bot, m.chat.id, m.from_user.id):
        return
    lang = await get_lang(m.from_user.id) or "id"
    title = "🌐 <b>Pengaturan Bahasa</b>\nPilih bahasa:" if lang == "id" else "🌐 <b>Language Settings</b>\nChoose your language:"
    await m.answer(title, parse_mode="HTML", reply_markup=language_kb())

@router.callback_query(F.data == "change_language")
async def change_language(c: CallbackQuery):
    await c.answer()
    await language_prompt(c.message, edit=True)

@router.callback_query(F.data == "home")
async def home(c: CallbackQuery):
    await loading(c)
    await ensure_user(c.from_user.id, c.from_user.username, c.from_user.full_name)
    await show_welcome(c.message, c.from_user, await get_lang(c.from_user.id) or "id", edit=True)

@router.callback_query(F.data == "verify_join")
async def verify_join(c: CallbackQuery):
    if not await subscription_prompt(c.bot, c.from_user.id, c.from_user.id):
        return await c.answer("Please join both channels first.", show_alert=True)
    await ensure_user(c.from_user.id, c.from_user.username, c.from_user.full_name)
    lang = await get_lang(c.from_user.id)
    await c.answer()
    if not lang:
        return await language_prompt(c.message, edit=True)
    await show_welcome(c.message, c.from_user, lang, edit=True)

@router.callback_query(F.data == "review")
async def review(c: CallbackQuery):
    lang = await get_lang(c.from_user.id) or "id"
    await c.answer()
    await c.message.answer(
        "⭐ <b>Review &amp; Rating</b>\n\nPilih Code melalui menu Code, lalu gunakan tombol Like, Hate, atau Favorite pada halaman Code." if lang == "id" else
        "⭐ <b>Reviews &amp; Ratings</b>\n\nChoose a code from Code, then use Like, Hate, or Favorite on its code page.",
        parse_mode="HTML", reply_markup=await home_kb(c.from_user.id, lang)
    )

@router.message(F.chat.type == "private", Command("codetop"))
async def codetop(m: Message):
    from handlers.misc import _render_code_command
    await _render_code_command(m, "top")

@router.message(F.chat.type == "private", Command("searchcode"))
async def searchcode(m: Message):
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        lang = await get_lang(m.from_user.id) or "id"
        await m.answer("Kirim /searchcode diikuti kode yang dicari." if lang == "id" else "Send /searchcode followed by the code to search.")
        return
    from handlers.getfile import show
    await show(m, parts[1].strip())

@router.message(F.chat.type == "private", Command("mypurchases"))
async def mypurchases(m: Message):
    lang = await get_lang(m.from_user.id) or "id"
    p = await get_pool()
    rows = await p.fetch("""SELECT code, MAX(expires_at) AS expires_at FROM unlock_transactions
        WHERE user_id=$1 AND payment_type IN ('qr','admin') GROUP BY code ORDER BY MAX(created_at) DESC LIMIT 20""", m.from_user.id)
    if not rows:
        return await m.answer("Kamu belum memiliki riwayat pembelian Code." if lang == "id" else "You have no Code purchase history yet.")
    lines = ["🧾 <b>Pembelian Saya</b>" if lang == "id" else "🧾 <b>My Purchases</b>"]
    for r in rows:
        lines.append(f"• <code>{r['code']}</code>")
    await m.answer("\n".join(lines), parse_mode="HTML")
