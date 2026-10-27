from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_pool
from keyboards.menu import home_kb, channel_reply_kb, CHANNEL_ADMIN_URL, CHANNEL_UPDATE_URL
from utils.economy import ensure_user
from middlewares.subscription import subscription_prompt
from utils.callback_loading import loading
from utils.i18n import get_lang, set_lang, SUPPORTED
from utils.admin_access import admin_access

router = Router()

WELCOME = {
    "id": "👋 Halo, {name}!\n\n📥 Kirim kode media untuk mulai.\n💎 Ketik /channelvip untuk melihat akses VIP.\n💬 Ketik /msg untuk chat admin.",
    "en": "👋 Hello, {name}!\n\n📥 Send a media code to get started.\n💎 Use /channelvip to view VIP access.\n💬 Use /msg to chat with an admin.",
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
    # Admin can customize each language from /admin -> Pesan Sambutan.
    # The built-in message remains the fallback for fresh installs.
    p = await get_pool()
    key = "welcome_text_en" if lang == "en" else "welcome_text_id"
    custom = await p.fetchval("SELECT value FROM settings WHERE key=$1", key)
    # Custom messages are plain text so symbols like &, < and > cannot break HTML parsing.
    # Built-in defaults may use Telegram HTML formatting.
    import html
    is_custom = bool(custom and str(custom).strip())
    template = str(custom).strip() if is_custom else WELCOME.get(lang, WELCOME["id"])
    if is_custom:
        template = html.escape(template)
    name = html.escape(user.full_name or user.username or str(user.id))
    return template.replace("{name}", name)

async def show_welcome(target, user, lang, edit=False, show_channels=True):
    text = await welcome_text(user, lang)
    kb = await home_kb(user.id, lang)
    reply_kb = channel_reply_kb(lang)
    sent = None
    if edit:
        try:
            await target.edit_text(text, parse_mode="HTML", reply_markup=kb)
            sent = target
        except Exception:
            sent = await target.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        sent = await target.answer(text, parse_mode="HTML", reply_markup=kb)
    if show_channels:
        try:
            await target.bot.send_message(user.id, "⬇️ Menu" if lang == "id" else "⬇️ Menu", reply_markup=reply_kb)
        except Exception:
            pass
    # Pin the welcome message where Telegram allows it; failure is non-fatal.
    try:
        msg = sent if isinstance(sent, Message) else getattr(target, "message", None)
        if msg:
            await target.bot.pin_chat_message(chat_id=user.id, message_id=msg.message_id, disable_notification=True)
    except Exception:
        pass

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

@router.message(F.chat.type == "private", F.text.in_({"📣 Channel Admin", "📣 Admin Channel"}))
async def open_admin_channel(m: Message):
    lang = await get_lang(m.from_user.id) or "id"
    await m.answer(
        ("📣 <b>Channel Admin</b>\\nTekan tautan untuk membuka channel admin." if lang != "en" else "📣 <b>Admin Channel</b>\\nTap the link to open the admin channel."),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📣 Buka Channel Admin" if lang != "en" else "📣 Open Admin Channel", url=CHANNEL_ADMIN_URL)]
        ])
    )

@router.message(F.chat.type == "private", F.text.in_({"📢 Channel Update", "📢 Updates Channel"}))
async def open_updates_channel(m: Message):
    lang = await get_lang(m.from_user.id) or "id"
    await m.answer(
        ("📢 <b>Channel Update</b>\\nTekan tautan untuk membuka channel update." if lang != "en" else "📢 <b>Updates Channel</b>\\nTap the link to open the updates channel."),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Buka Channel Update" if lang != "en" else "📢 Open Updates Channel", url=CHANNEL_UPDATE_URL)]
        ])
    )



# Reply-keyboard menu handlers: these buttons send ordinary text, not callback queries.
@router.message(F.chat.type == "private", F.text.in_({"⭐ Review", "⭐ Review & Rating"}))
async def reply_review(m: Message):
    lang = await get_lang(m.from_user.id) or "id"
    await m.bot.send_chat_action(m.chat.id, "typing")
    await m.answer(
        "⭐ <b>Review &amp; Rating</b>\n\nPilih Code melalui menu Code, lalu gunakan tombol Like, Hate, atau Favorite pada halaman Code." if lang == "id" else
        "⭐ <b>Reviews &amp; Ratings</b>\n\nChoose a code from Code, then use Like, Hate, or Favorite on its code page.",
        parse_mode="HTML"
    )

@router.message(F.chat.type == "private", F.text.in_({"📥 Buka Media", "📥 Open Media"}))
async def reply_getfile(m: Message):
    lang = await get_lang(m.from_user.id) or "id"
    await m.bot.send_chat_action(m.chat.id, "typing")
    await m.answer("📥 Kirim kode media yang ingin dibuka." if lang == "id" else "📥 Send the media code you want to open.")

@router.message(F.chat.type == "private", F.text == "💎 VIP")
async def reply_vip(m: Message):
    from database import get_pool
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    lang = await get_lang(m.from_user.id) or "id"
    await m.bot.send_chat_action(m.chat.id, "typing")
    rows = await (await get_pool()).fetch("SELECT code,name,price FROM vip_packages WHERE active ORDER BY price")
    buttons = [[InlineKeyboardButton(text=f"{r['name']} • Rp{int(r['price']):,}".replace(',', '.'), callback_data=f"vip:{r['code']}")] for r in rows]
    buttons += [[InlineKeyboardButton(text="🛍️ Ambil Sebagian",callback_data="vipsome")], [InlineKeyboardButton(text="🛒 Ambil Semua",callback_data="vipall")], [InlineKeyboardButton(text="ℹ️ About",callback_data="vipabout"),InlineKeyboardButton(text="🎁 Donasi",callback_data="vipdonate")]]
    await m.answer("📚 <b>Daftar VVIP Bot</b>\n\nInfo Nilai\n<b>ALL VIP GROUP</b>\nKeterangan: Daftar paket eksklusif. Klik paket untuk detail lengkap dan penawaran spesial.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.message(F.chat.type == "private", F.text == "🔑 Code")
async def reply_codes(m: Message):
    from handlers.misc import _render_code_command
    await m.bot.send_chat_action(m.chat.id, "typing")
    await _render_code_command(m, "all")

@router.message(F.chat.type == "private", F.text.in_({"❓ Bantuan", "❓ Help"}))
async def reply_help(m: Message):
    from handlers.misc import _help_pages, _help_keyboard
    lang = await get_lang(m.from_user.id) or "id"
    if lang not in {"id", "en"}: lang = "id"
    await m.bot.send_chat_action(m.chat.id, "typing")
    await m.answer(_help_pages(lang)[0], parse_mode="HTML", reply_markup=await _help_keyboard(lang, 0, m.from_user.id))

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
    await show_welcome(c.message, c.from_user, await get_lang(c.from_user.id) or "id", edit=True, show_channels=False)

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
