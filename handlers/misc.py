from aiogram import Router,F
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
import html
import re
from decimal import Decimal
from database import get_pool
from utils.i18n import get_lang
from config import CODE_GROUP_ID, CODE_GROUP_URL, NOTICE_CHANNEL_URL, CODE_GROUP_TITLE, NOTIF_CHANNEL_ID, BOT_USERNAME, ALL_CODE_CHANNEL_URL, BACKUP_CHANNEL_URL

from utils.callback_loading import loading
router=Router()


# Direct Group & Channel links
DIRECT_GROUP_CODE_URL = "https://t.me/+WeFUnjG8ojQzOWQ5"
DIRECT_ALL_CODE_URL = "https://t.me/+NrHk5eHAiTFiNzc1"
DIRECT_BACKUP_URL = "https://t.me/+g3t3JY6ft8xhYTE1"
DIRECT_NOTICE_URL = "https://t.me/noticsaluran"


async def _lang(uid: int) -> str:
    try:
        lang = await get_lang(uid)
        return lang if lang in UI_TEXT else "id"
    except Exception:
        return "id"

UI_TEXT = {
    "id": {
        "back":"🔙 Kembali", "mycode":"📋 <b>MY CODE</b>\n\n", "no_code":"Belum ada code.",
        "top":"🔝 Top 10", "recommend":"⭐ Rekomendasi", "all":"🔑 Semua Code", "all_title":"🔑 <b>SEMUA CODE</b>",
        "top_title":"🔝 <b>TOP 10 CODE</b>", "rec_title":"⭐ <b>REKOMENDASI</b>", "no_codes":"Belum ada Code yang dibuat.",
        "click_title":"Klik <b>Judul</b> untuk mencari atau membuka media yang terhubung dengan CODE tersebut.",
        "not_found":"❌ Code tidak ditemukan.", "all_code":"🔙 Semua Code", "like":"👍 Like", "hate":"👎 Hate", "fav":"⭐ Favorit",
        "buy_vip":"💎 <b>BELI VIP</b>\n\nPilih paket:", "group_channel":"👥 <b>GRUP & CHANNEL CODE</b>\n\nPilih tujuan:",
        "group":"👥 Grup Code", "all_channel":"📚 Channel Semua Code", "backup":"💾 Channel Backup", "notice":"🔔 Channel Notifikasi",
        "bot_links":"🔗 <b>LINK BOT</b>\n\nPilih tujuan yang diperlukan:",
        "media_hint":"📎 <b>Media terdeteksi</b>\n\nFitur upload hanya tersedia untuk admin/owner.", "upfile":"📤 Upfile",
        "start_first":"Tekan /start di bot terlebih dahulu, lalu tekan GET FILE.", "inactive":"Code tidak ditemukan atau sudah tidak aktif.",
        "sent_get":"GET FILE dikirim ke chat pribadi.", "open_private":"Buka chat pribadi dengan bot lalu tekan /start."
    },
    "en": {
        "back":"🔙 Back", "mycode":"📋 <b>MY CODE</b>\n\n", "no_code":"No codes yet.",
        "top":"🔝 Top 10", "recommend":"⭐ Recommended", "all":"🔑 All Codes", "all_title":"🔑 <b>ALL CODES</b>",
        "top_title":"🔝 <b>TOP 10 CODES</b>", "rec_title":"⭐ <b>RECOMMENDED</b>", "no_codes":"No Codes have been created yet.",
        "click_title":"Tap a <b>title</b> to find or open the media linked to that CODE.",
        "not_found":"❌ Code not found.", "all_code":"🔙 All Codes", "like":"👍 Like", "hate":"👎 Hate", "fav":"⭐ Favorite",
        "buy_vip":"💎 <b>BUY VIP</b>\n\nChoose a package:", "group_channel":"👥 <b>CODE GROUPS & CHANNELS</b>\n\nChoose a destination:",
        "group":"👥 Code Group", "all_channel":"📚 All Codes Channel", "backup":"💾 Backup Channel", "notice":"🔔 Notification Channel",
        "bot_links":"🔗 <b>BOT LINKS</b>\n\nChoose a destination:",
        "media_hint":"📎 <b>Media detected</b>\n\nUploads are available to admins/owner only.", "upfile":"📤 Upfile",
        "start_first":"Press /start in the bot first, then tap GET FILE.", "inactive":"Code not found or no longer active.",
        "sent_get":"GET FILE was sent to your private chat.", "open_private":"Open the bot's private chat and press /start."
    }
}

async def _t(uid, key, **kwargs):
    lang=await _lang(uid)
    return UI_TEXT.get(lang, UI_TEXT["id"]).get(key, UI_TEXT["id"].get(key, key)).format(**kwargs)


async def _code_link(code: str) -> str:
    from utils.bot_identity import get_bot_username
    bot_name = await get_bot_username()
    return f"https://t.me/{bot_name}?start={code}" if bot_name else ""

def _safe_url(s: str) -> str:
    return html.escape(s, quote=True)

@router.callback_query(F.data=='my_code')
async def my(c):
    rows=await (await get_pool()).fetch(
        "SELECT code,title,media_count,views,likes,hates,favorites FROM files "
        "WHERE owner_id=$1 AND active=TRUE ORDER BY id DESC LIMIT 30", c.from_user.id
    )
    text=await _t(c.from_user.id,'mycode')
    kb=[]
    if rows:
        for r in rows:
            title=html.escape((r['title'] or 'Untitled')[:45])
            text += f"📝 <b>{title}</b>\n🔑 <code>{html.escape(r['code'])}</code> • {r['media_count']} media\n"
            text += f"👁 {r['views']} • 👍 {r['likes']} • 👎 {r['hates']} • ⭐ {r['favorites']}\n\n"
            kb.append([InlineKeyboardButton(text=f"📝 {title}", callback_data=f"browsecode:{r['code']}")])
    else:
        text+=await _t(c.from_user.id,'no_code')
    kb.append([InlineKeyboardButton(text=await _t(c.from_user.id,'back'),callback_data='menu_lainnya')])
    await loading(c)
    await c.message.edit_text(text,parse_mode='HTML',reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


async def _paged_codes(page:int=0, mode:str="all", per_page:int=10):
    p=await get_pool()
    page=max(0,int(page)); offset=page*per_page
    if mode=="top":
        order="views DESC, likes DESC, favorites DESC, id DESC"
    elif mode=="recommend":
        order="(likes*3 + favorites*2 + views) DESC, views DESC, id DESC"
    else:
        order="id DESC"
    rows=await p.fetch(f"""
        SELECT id,code,title,media_count,views,likes,hates,favorites,price_idr
        FROM files WHERE active=TRUE ORDER BY {order} LIMIT $1 OFFSET $2
    """,per_page,offset)
    total=int(await p.fetchval("SELECT COUNT(*) FROM files WHERE active=TRUE") or 0)
    return rows,total

async def _code_link(code):
    from utils.bot_identity import get_bot_username
    bot_name = await get_bot_username()
    return f"https://t.me/{bot_name}?start={code}" if bot_name else ""

async def _code_text_row(r, prefix=""):
    title=html.escape((r['title'] or 'Untitled')[:60])
    href=html.escape(await _code_link(r['code']),quote=True)
    price=int(r['price_idr'] or 0)
    paid=f" • 💰 Rp{price:,}".replace(',','.') if price else " • 🆓"
    return (
        f"{prefix}<a href=\"{href}\">📝 {title}</a>{paid}\n"
        f"👁 {r['views']} • 👍 {r['likes']} • 👎 {r['hates']} • ⭐ {r['favorites']}\n\n"
    )

async def _render_code_command(m: Message, mode: str = "top"):
    if mode == "all":
        lang = await get_lang(m.from_user.id) or "id"
        text = ("🗂 <b>PILIH SERVER</b>\nPilih server untuk mencari code media:"
                if lang == "id" else
                "🗂 <b>CHOOSE A SERVER</b>\nChoose a server to search media codes:")
        await m.answer(text, parse_mode="HTML", reply_markup=await _server_keyboard(m.from_user.id))
        return
    rows, total = await _paged_codes(0, mode, 10)
    lang = await get_lang(m.from_user.id) or "id"
    title = "🔝 <b>TOP 10 CODE</b>" if mode == "top" else "🔑 <b>ALL CODE</b>"
    if lang == "en":
        title = "🔝 <b>TOP 10 CODES</b>" if mode == "top" else "🔑 <b>ALL CODES</b>"
    body = title + "\n\n"
    if not rows:
        body += "Belum ada Code." if lang == "id" else "No codes are available yet."
    else:
        for i, row in enumerate(rows, 1):
            body += await _code_text_row(row, f"{i}. ")
    await m.answer(body, parse_mode="HTML", disable_web_page_preview=True)

async def _code_nav(page,total,mode,uid=0):
    pages=max(1,(total+9)//10)
    nav=[]
    if page>0: nav.append(InlineKeyboardButton(text='⬅️',callback_data=f'{mode}page:{page-1}'))
    nav.append(InlineKeyboardButton(text=f'📄 {page+1}/{pages}',callback_data='noop'))
    if page<pages-1: nav.append(InlineKeyboardButton(text='➡️',callback_data=f'{mode}page:{page+1}'))
    rows=[nav]
    if mode=="all":
        rows.append([
            InlineKeyboardButton(text=await _t(uid,'top'),callback_data='top_codes'),
            InlineKeyboardButton(text=await _t(uid,'recommend'),callback_data='recommendation')
        ])
    elif mode=="top":
        rows.append([InlineKeyboardButton(text=await _t(uid,'recommend'),callback_data='recommendation'),
                     InlineKeyboardButton(text=await _t(uid,'all'),callback_data='code_all')])
    else:
        rows.append([InlineKeyboardButton(text=await _t(uid,'top'),callback_data='top_codes'),
                     InlineKeyboardButton(text=await _t(uid,'all'),callback_data='code_all')])
    rows.append([InlineKeyboardButton(text=await _t(uid,'back'),callback_data='home')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def _render_code_list(c,page=0,mode="all"):
    rows,total=await _paged_codes(page,mode,10)
    heading={"all":await _t(c.from_user.id,"all_title"),"top":await _t(c.from_user.id,"top_title"),"recommend":await _t(c.from_user.id,"rec_title")}[mode]
    text=heading+"\n\n"
    if not rows:
        text+="Belum ada code yang dibuat."
    else:
        for i,r in enumerate(rows, page*10+1):
            text+=await _code_text_row(r, f"{i}. " if mode!="all" else "")
        text+="Klik <b>Judul</b> untuk mencari/membuka media yang terhubung dengan CODE tersebut."
    await c.message.edit_text(text,parse_mode='HTML',reply_markup=await _code_nav(page,total,mode,c.from_user.id))

async def _server_keyboard(uid=0):
    p=await get_pool()
    rows=await p.fetch("SELECT server_no,name FROM server_categories WHERE enabled=TRUE ORDER BY server_no")
    if not rows:
        rows=[{"server_no":i,"name":f"Server {i}"} for i in range(1,11)]
    buttons=[[InlineKeyboardButton(text=f"🗂 Server {r['server_no']} • {r['name']}",callback_data=f"serverbrowse:{r['server_no']}:0")] for r in rows]
    buttons.append([InlineKeyboardButton(text=await _t(uid,'back'),callback_data='home')])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

@router.callback_query(F.data=='code_all')
async def code_all(c):
    await loading(c)
    lang=await _lang(c.from_user.id)
    text="🗂 <b>PILIH SERVER</b>\nPilih server untuk mencari code media:" if lang == 'id' else "🗂 <b>CHOOSE A SERVER</b>\nChoose a server to search media codes:"
    await c.message.edit_text(text,parse_mode='HTML',reply_markup=await _server_keyboard(c.from_user.id))

@router.callback_query(F.data.startswith('serverbrowse:'))
async def serverbrowse(c):
    await loading(c)
    try:
        _, no, page = c.data.split(':',2); no=int(no); page=max(0,int(page))
    except Exception:
        return await c.answer("Server tidak valid.",show_alert=True)
    p=await get_pool()
    server=await p.fetchrow("SELECT name FROM server_categories WHERE server_no=$1 AND enabled=TRUE",no)
    if not server:
        return await c.answer("Server belum tersedia.",show_alert=True)
    full_name=f"Server {no} — {server['name']}"
    rows=await p.fetch("""SELECT code,title,price_idr,views,likes,hates,favorites
        FROM files WHERE active=TRUE AND server_name=$1 ORDER BY id DESC LIMIT 10 OFFSET $2""",full_name,page*10)
    total=int(await p.fetchval("SELECT COUNT(*) FROM files WHERE active=TRUE AND server_name=$1",full_name) or 0)
    buttons=[]
    nav=[]
    if page>0: nav.append(InlineKeyboardButton(text="⬅️",callback_data=f"serverbrowse:{no}:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {page+1}/{max(1,(total+9)//10)}",callback_data="noop"))
    if (page+1)*10<total: nav.append(InlineKeyboardButton(text="➡️",callback_data=f"serverbrowse:{no}:{page+1}"))
    buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="🔙 Pilih Server",callback_data="code_all")])
    lang=await _lang(c.from_user.id)
    text=f"🗂 <b>SERVER {no} • {html.escape(server['name'])}</b>\n\n"
    if rows:
        for i,r in enumerate(rows,page*10+1):
            text += await _code_text_row(r, f"{i}. ")
        text += ("Klik judul Code untuk membuka review gratis dan tombol pembelian." if lang=='id' else
                 "Tap a Code title to open its free review and purchase buttons.")
    else:
        text += "Belum ada code di server ini." if lang=='id' else "No codes in this server yet."
    await c.message.edit_text(text,parse_mode='HTML',disable_web_page_preview=True,reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith('codepage:'))
async def codepage(c):
    await loading(c)
    try: page=int(c.data.split(':',1)[1])
    except: page=0
    await _render_code_list(c,page,"all")

@router.callback_query(F.data=='top_codes')
async def top_codes(c):
    await loading(c); await _render_code_list(c,0,"top")

@router.callback_query(F.data.startswith('toppage:'))
async def toppage(c):
    await loading(c)
    try: page=int(c.data.split(':',1)[1])
    except: page=0
    await _render_code_list(c,page,"top")

@router.callback_query(F.data=='recommendation')
async def recommendation(c):
    await loading(c); await _render_code_list(c,0,"recommend")

@router.callback_query(F.data.startswith('recommendpage:'))
async def recommendpage(c):
    await loading(c)
    try: page=int(c.data.split(':',1)[1])
    except: page=0
    await _render_code_list(c,page,"recommend")

@router.callback_query(F.data.startswith('browsecode:'))
async def browsecode(c):
    await loading(c)
    code=c.data.split(':',1)[1]
    p=await get_pool()
    f=await p.fetchrow("SELECT code,title,media_count,views,likes,hates,favorites,price_idr,review_media,server_name FROM files WHERE lower(code)=lower($1) AND active=TRUE", code)
    if not f: return await c.answer(await _t(c.from_user.id,'not_found'),show_alert=True)
    try:
        previews=f['review_media'] if isinstance(f['review_media'],list) else json.loads(f['review_media'] or '[]')
    except Exception:
        previews=[]
    # Preview only; never send the paid media list from this browser action.
    try:
        if len(previews)==1 and previews[0].get('type')=='video':
            await c.bot.send_video(c.from_user.id,previews[0]['telegram_file_id'],caption="🎬 Preview video")
        elif previews and all(x.get('type')=='photo' for x in previews):
            from aiogram.types import InputMediaPhoto
            await c.bot.send_media_group(c.from_user.id,media=[InputMediaPhoto(media=x['telegram_file_id']) for x in previews[:5]])
    except Exception:
        pass
    price=int(f['price_idr'] or 0)
    paid=f"💰 Harga: <b>Rp{price:,}</b>".replace(',','.') if price else "🆓 <b>FREE CODE</b>"
    href=html.escape(await _code_link(f['code']),quote=True)
    await c.message.edit_text(
        f"📝 <a href=\"{href}\"><b>{html.escape(f['title'] or 'Untitled')}</b></a>\n\n"
        f"🔑 <code>{html.escape(f['code'])}</code>\n📦 Media: <b>{f['media_count']}</b>\n{paid}\n\n"
        f"👁 Total View: <b>{f['views']}</b>\n👍 Total Like: <b>{f['likes']}</b>\n👎 Total Hate: <b>{f['hates']}</b>\n⭐ Total Favorit: <b>{f['favorites']}</b>\n\n"
        "Klik <b>Judul</b> untuk mencari/membuka media yang terhubung dengan CODE tersebut.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=await _t(c.from_user.id,'like'),callback_data=f'react:like:{f["code"]}'),
             InlineKeyboardButton(text=await _t(c.from_user.id,'hate'),callback_data=f'react:hate:{f["code"]}'),
             InlineKeyboardButton(text=await _t(c.from_user.id,'fav'),callback_data=f'react:favorite:{f["code"]}')],
            [InlineKeyboardButton(text='🛒 Buy Now',callback_data=f'getcode:{f["code"]}')],
            [InlineKeyboardButton(text=await _t(c.from_user.id,'all_code'),callback_data='code_all')]
        ])
    )

HELP_TEXTS={
"id": """📘 <b>BANTUAN BOT</b>

<b>1. Mulai</b>
Tekan /start untuk membuka menu. Pilih bahasa Indonesia atau English. Bahasa bisa diganti kapan saja lewat /setting.

<b>2. Buka media</b>
Tekan <b>📥 Buka Media</b> atau kirim CODE yang kamu punya. Ikuti petunjuk yang muncul.

<b>3. Gratis atau berbayar</b>
Jika Code gratis, ikuti petunjuk untuk membukanya. Jika berbayar, pilih metode pembayaran dan bayar sesuai nominal yang tertera. Media dapat diakses setelah pembayaran berhasil dikonfirmasi.

<b>4. VIP</b>
Tekan <b>💎 VIP</b> untuk melihat paket VIP yang tersedia. Akses mengikuti durasi dan ketentuan paket.

<b>5. Ada masalah?</b>
Periksa kembali CODE dan status pembayaran. Jika masih bermasalah, tekan <b>💬 Chat Admin</b> untuk meminta bantuan. Jangan bagikan PIN, kata sandi, atau kode keamanan.

Pilih tombol bahasa di bawah untuk membaca panduan dalam bahasa lain.""",
"en": """📘 <b>BOT HELP</b>

<b>1. Get started</b>
Tap /start to open the menu. Choose Indonesian or English. You can change the language anytime with /setting.

<b>2. Open media</b>
Tap <b>📥 Open Media</b> or send the CODE you have. Follow the instructions shown by the bot.

<b>3. Free or paid</b>
For a free Code, follow the steps to open it. For a paid Code, choose a payment method and pay the exact amount shown. Access will be available after the payment is confirmed.

<b>4. VIP</b>
Tap <b>💎 VIP</b> to view available VIP packages. Access depends on the package duration and terms.

<b>5. Need help?</b>
Check that the CODE is correct and review your payment status. If the problem continues, tap <b>💬 Message Admin</b> for help. Never share your PIN, password, or security codes.

Use the language buttons below to read this guide in another language."""
}


def _help_pages(lang: str):
    text = HELP_TEXTS.get(lang, HELP_TEXTS["id"])
    paragraphs = [x.strip() for x in text.split("\n\n") if x.strip()]
    pages = []
    current = ""
    # Telegram message text limit is 4096 characters. Keep a safe margin
    # because HTML/entity handling and future edits can change the size.
    limit = 3400
    for paragraph in paragraphs:
        candidate = paragraph if not current else current + "\n\n" + paragraph
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                pages.append(current)
            # A single section should also never exceed the limit.
            while len(paragraph) > limit:
                cut = paragraph.rfind("\n", 0, limit)
                if cut < 1000:
                    cut = limit
                pages.append(paragraph[:cut].strip())
                paragraph = paragraph[cut:].strip()
            current = paragraph
    if current:
        pages.append(current)
    return pages or [""]

async def _help_keyboard(lang: str, page: int, uid: int = 0):
    pages = _help_pages(lang)
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text=("‹ Sebelumnya" if lang == "id" else "‹ Prev"), callback_data=f"help:page:{lang}:{page-1}"))
    if page < len(pages)-1:
        nav.append(InlineKeyboardButton(text=("Selanjutnya ›" if lang == "id" else "Next ›"), callback_data=f"help:page:{lang}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([
        InlineKeyboardButton(text='🇮🇩 Indonesia',callback_data='help:lang:id'),
        InlineKeyboardButton(text='🇬🇧 English',callback_data='help:lang:en')
    ])
    rows.append([InlineKeyboardButton(text=(f"Halaman {page+1}/{len(pages)}" if lang == "id" else f"Page {page+1}/{len(pages)}"), callback_data='help:noop')])
    rows.append([InlineKeyboardButton(text=await _t(uid,'back'),callback_data='home')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

@router.callback_query(F.data=='help')
async def help_(c):
    lang = await get_lang(c.from_user.id) or "id"
    if lang not in {"id", "en"}: lang = "id"
    await loading(c)
    await c.message.edit_text(
        _help_pages(lang)[0],
        parse_mode='HTML',
        reply_markup=await _help_keyboard(lang, 0, c.from_user.id)
    )

@router.callback_query(F.data.startswith('help:lang:'))
async def help_lang(c):
    lang=c.data.rsplit(':',1)[1]
    if lang not in {"id", "en"}: lang="id"
    await loading(c)
    await c.message.edit_text(
        _help_pages(lang)[0],
        parse_mode='HTML',
        reply_markup=await _help_keyboard(lang, 0, c.from_user.id)
    )

@router.callback_query(F.data.startswith('help:page:'))
async def help_page(c):
    parts=c.data.split(':')
    lang=parts[2] if len(parts) > 2 else 'id'
    try:
        page=int(parts[3])
    except (ValueError, IndexError):
        page=0
    if lang not in {"id", "en"}:
        lang='id'
    pages=_help_pages(lang)
    page=max(0, min(page, len(pages)-1))
    await loading(c)
    await c.message.edit_text(
        pages[page],
        parse_mode='HTML',
        reply_markup=await _help_keyboard(lang, page, c.from_user.id)
    )

@router.callback_query(F.data=='help:noop')
async def help_noop(c):
    await c.answer()

@router.callback_query(F.data=='buy_vip')
async def vip(c):
    rows=await (await get_pool()).fetch("SELECT code,name,price,duration_days FROM vip_packages WHERE active ORDER BY price")
    kb=[[InlineKeyboardButton(text=f'💎 {r["name"]} • Rp{int(r["price"]):,}'.replace(',','.'),callback_data=f'vip:{r["code"]}')] for r in rows]
    kb.append([InlineKeyboardButton(text=await _t(c.from_user.id,'back'),callback_data='home')])
    await loading(c); await c.message.edit_text(await _t(c.from_user.id,'buy_vip'),parse_mode='HTML',reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

async def quick_links(uid: int = 0):
    # Group Code opens a dedicated link menu so users can choose the
    # group/all-code/backup/notification destination.
    rows=[]
    rows.append([InlineKeyboardButton(text=await _t(uid,'group'),callback_data='open_group_info')])
    return rows

@router.callback_query(F.data=='group_code')
async def group_code(c):
    await open_group_info(c)

@router.callback_query(F.data=='open_group_info')
async def open_group_info(c):
    await loading(c)
    uid = c.from_user.id
    rows = [
        [InlineKeyboardButton(text=await _t(uid, 'group'), url=DIRECT_GROUP_CODE_URL)],
        [InlineKeyboardButton(text=await _t(uid, 'all_channel'), url=DIRECT_ALL_CODE_URL)],
        [InlineKeyboardButton(text=await _t(uid, 'backup'), url=DIRECT_BACKUP_URL)],
        [InlineKeyboardButton(text=await _t(uid, 'notice'), url=DIRECT_NOTICE_URL)],
        [InlineKeyboardButton(text=await _t(uid, 'back'), callback_data='menu_lainnya')],
    ]
    await c.message.edit_text(
        await _t(uid, 'group_channel'),
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )

@router.callback_query(F.data=='open_notice_info')
async def open_notice_info(c):
    await open_group_info(c)


async def vip_selector_menu(m: Message):
    lang = await _lang(m.from_user.id)
    text = ("💎 <b>MENU VIP</b>\n\nPilih akses yang kamu butuhkan:"
            if lang == "id" else
            "💎 <b>VIP MENU</b>\n\nChoose the access you need:")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👑 VIP Bot", callback_data="keyword_vipbot")],
        [InlineKeyboardButton(text="💎 VIP Group", callback_data="keyword_vipgroup")],
    ])
    await m.answer(text, parse_mode="HTML", reply_markup=kb)


async def vipbot_menu(m: Message):
    lang = await _lang(m.from_user.id)
    text = (
        "👑 <b>VIP BOT</b>\\n\\nPilih jenis paket di bawah ini. Daftar paket akan diurutkan dari harga termurah ke termahal.\\n\\n"
        "💎 VIP Bot: akses code dengan kuota harian standar.\\n"
        "🔥 VVIP Bot: akses code dengan kuota harian lebih besar."
        if lang == "id" else
        "👑 <b>VIP BOT</b>\\n\\nChoose a package type below. Packages are sorted from lowest to highest price.\\n\\n"
        "💎 VIP Bot: code access with the standard daily quota.\\n"
        "🔥 VVIP Bot: code access with a higher daily quota."
    )
    buttons = [
        [InlineKeyboardButton(text="💎 VIP Bot", callback_data="vipcat:vip"),
         InlineKeyboardButton(text="🔥 VVIP Bot", callback_data="vipcat:vvip")],
        [InlineKeyboardButton(text="❔ Bantuan" if lang == "id" else "❔ Help", callback_data="vipbot:help"),
         InlineKeyboardButton(text="🎁 Donasi" if lang == "id" else "🎁 Donate", callback_data="vipbot:donate")],
        [InlineKeyboardButton(text="🔙 Kembali" if lang == "id" else "🔙 Back", callback_data="home")],
    ]
    await m.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "vipbot:home")
async def vipbot_home_callback(c: CallbackQuery):
    lang = await _lang(c.from_user.id)
    text = (
        "👑 <b>VIP BOT</b>\\n\\nPilih jenis paket di bawah ini. Daftar paket akan diurutkan dari harga termurah ke termahal.\\n\\n"
        "💎 VIP Bot: akses code dengan kuota harian standar.\\n🔥 VVIP Bot: akses code dengan kuota harian lebih besar."
        if lang == "id" else
        "👑 <b>VIP BOT</b>\\n\\nChoose a package type below. Packages are sorted from lowest to highest price.\\n\\n"
        "💎 VIP Bot: standard daily code quota.\\n🔥 VVIP Bot: higher daily code quota."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 VIP Bot", callback_data="vipcat:vip"), InlineKeyboardButton(text="🔥 VVIP Bot", callback_data="vipcat:vvip")],
        [InlineKeyboardButton(text="❔ Bantuan" if lang == "id" else "❔ Help", callback_data="vipbot:help"), InlineKeyboardButton(text="🎁 Donasi" if lang == "id" else "🎁 Donate", callback_data="vipbot:donate")],
        [InlineKeyboardButton(text="🔙 Kembali" if lang == "id" else "🔙 Back", callback_data="home")],
    ])
    await c.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await c.answer()


@router.callback_query(F.data == "vipbot:help")
async def vipbot_help_callback(c: CallbackQuery):
    lang = await _lang(c.from_user.id)
    text = ("ℹ️ <b>Bantuan VIP Bot</b>\\n\\nPilih VIP Bot atau VVIP Bot, lalu pilih paket sesuai durasi dan harga. Setelah pembayaran dikonfirmasi, status aktif otomatis. Kuota buka code berlaku per hari; jeda buka code dan pengiriman media mengikuti pengaturan admin."
            if lang == "id" else
            "ℹ️ <b>VIP Bot Help</b>\\n\\nChoose VIP Bot or VVIP Bot, then select a package. Your subscription activates after payment confirmation. Daily code quotas and delays follow admin settings.")
    await c.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Kembali", callback_data="vipbot:home")]]))
    await c.answer()


@router.callback_query(F.data == "vipbot:donate")
async def vipbot_donate_callback(c: CallbackQuery):
    lang = await _lang(c.from_user.id)
    text = ("🎁 <b>Donasi</b>\\n\\nTerima kasih sudah mendukung pengembangan bot. Pilih jumlah donasi Telegram Stars:"
            if lang == "id" else "🎁 <b>Donate</b>\\n\\nThank you for supporting the bot. Choose a Telegram Stars donation amount:")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="25 ⭐", callback_data="vg:stars:25"), InlineKeyboardButton(text="50 ⭐", callback_data="vg:stars:50")],
        [InlineKeyboardButton(text="75 ⭐", callback_data="vg:stars:75"), InlineKeyboardButton(text="100 ⭐", callback_data="vg:stars:100")],
        [InlineKeyboardButton(text="🔙 Kembali", callback_data="vipbot:home")],
    ])
    await c.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await c.answer()


async def vip_group_menu(m: Message):
    lang = await _lang(m.from_user.id)
    text = ("💎 <b>VIP GROUP</b>\n\nPilih grup atau channel VIP yang ingin dibuka."
            if lang == "id" else
            "💎 <b>VIP GROUP</b>\n\nChoose the VIP group or channel you want to open.")
    buttons = [
        [InlineKeyboardButton(text="👥 Grup Code" if lang == "id" else "👥 Code Group", url=DIRECT_GROUP_CODE_URL)],
        [InlineKeyboardButton(text="📚 Channel Semua Code" if lang == "id" else "📚 All Codes Channel", url=DIRECT_ALL_CODE_URL)],
        [InlineKeyboardButton(text="💾 Channel Backup" if lang == "id" else "💾 Backup Channel", url=DIRECT_BACKUP_URL)],
        [InlineKeyboardButton(text="🔔 Channel Notifikasi" if lang == "id" else "🔔 Notification Channel", url=DIRECT_NOTICE_URL)],
    ]
    await m.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.message(F.chat.type=='private', F.text, ~F.text.startswith('/'))
async def keyword_help(m: Message):
    raw_text=(m.text or '').strip()
    text=raw_text.lower()
    lang=await _lang(m.from_user.id)

    # Save Successful notifications may contain both a media code and a review code.
    # Resolve the media code directly so the bot shows its review card, not the full code list.
    code_matches=re.findall(r'(?<![A-Za-z0-9_])JSShow_[A-Za-z0-9]{8,40}(?![A-Za-z0-9_])', raw_text, re.IGNORECASE)
    review_matches=re.findall(r'(?<![A-Za-z0-9_])JSShowreview_[A-Za-z0-9]{6,40}(?![A-Za-z0-9_])', raw_text, re.IGNORECASE)
    if code_matches or review_matches:
        from handlers.getfile import show
        # Prefer the actual media code when a save notification contains both codes.
        return await show(m, code_matches[0] if code_matches else review_matches[0])

    # Help/how-to requests take priority over other keywords.
    if any(k in text for k in ("caranya", "bantuan", "cara", "how to", "help", "how does")):
        guide = (
            "📖 <b>PANDUAN BOT</b>\\n\\n"
            "📂 <b>Cara membuka media</b>\\n"
            "1. Kirim Code media atau pilih menu Code.\\n"
            "2. Pilih Code yang ingin dibuka.\\n"
            "3. Tekan Buka Code lalu ikuti pilihan akses yang tersedia.\\n\\n"
            "💎 <b>Cara join VIP Bot</b>\\n"
            "Tekan VIP Bot, pilih paket, lalu selesaikan pembayaran.\\n\\n"
            "👥 <b>Cara join VIP Group</b>\\n"
            "Tekan VIP / VIP Group, pilih paket grup, lalu ikuti instruksi pembayaran.\\n"
            "Gunakan tombol di bawah untuk membuka menu terkait."
            if lang == "id" else
            "📖 <b>BOT GUIDE</b>\\n\\n"
            "📂 <b>Open media</b>\\nSend a media Code or choose Code, select an item, tap Open Code, and follow the access steps.\\n\\n"
            "💎 <b>Join VIP Bot</b>\\nTap VIP Bot, choose a package, and complete payment.\\n\\n"
            "👥 <b>Join VIP Group</b>\\nTap VIP / VIP Group, choose a group package, and follow payment instructions."
        )
        kb=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔑 Code", callback_data="auto:codes")],
            [InlineKeyboardButton(text="👑 VIP Bot", callback_data="keyword_vipbot"),
             InlineKeyboardButton(text="💎 VIP Group", callback_data="keyword_vipgroup")],
            [InlineKeyboardButton(text="👥 Group", callback_data="auto:group")],
            [InlineKeyboardButton(text="🏠 /start", callback_data="home")]
        ])
        return await m.answer(guide, parse_mode="HTML", reply_markup=kb)

    if "vip" in text:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👑 VIP Bot", callback_data="keyword_vipbot"),
             InlineKeyboardButton(text="💎 VIP Group", callback_data="keyword_vipgroup")],
            [InlineKeyboardButton(text="🏠 /start", callback_data="home")]
        ])
        return await m.answer("💎 <b>MENU VIP</b>\\nPilih VIP Bot atau VIP Group." if lang=="id" else
                              "💎 <b>VIP MENU</b>\\nChoose VIP Bot or VIP Group.",
                              parse_mode="HTML", reply_markup=kb)

    if "group" in text:
        return await m.answer(
            "👥 <b>MENU GROUP</b>\\nPilih grup atau channel yang dibutuhkan." if lang=="id" else
            "👥 <b>GROUP MENU</b>\\nChoose the group or channel you need.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👥 Group & Channel", callback_data="auto:group")],
                [InlineKeyboardButton(text="🏠 /start", callback_data="home")]
            ]))

    if any(k in text for k in ("code", "video", "media")):
        return await send_code_page(m, 0)

    # Unknown text: give a useful fallback instead of a dead-end response.
    kb=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 /start", callback_data="home"),
         InlineKeyboardButton(text="🔑 Code", callback_data="auto:codes")],
        [InlineKeyboardButton(text="👑 VIP Bot", callback_data="keyword_vipbot"),
         InlineKeyboardButton(text="💎 VIP", callback_data="keyword_vipgroup")],
        [InlineKeyboardButton(text="👥 Group", callback_data="auto:group"),
         InlineKeyboardButton(text="❓ Bantuan", callback_data="auto:help")]
    ])
    await m.answer(
        "Maaf, pesan itu belum dikenali. Pilih menu di bawah agar saya bisa membantu." if lang=="id" else
        "Sorry, I didn't recognize that message. Choose a menu below.",
        reply_markup=kb
    )

async def send_code_page(target, page: int = 0):
    uid=target.from_user.id
    lang=await _lang(uid)
    per_page=10
    p=await get_pool()
    total=int(await p.fetchval("SELECT COUNT(*) FROM files WHERE active=TRUE") or 0)
    page=max(0,min(int(page),max(0,(total-1)//per_page)))
    rows=await p.fetch(
        "SELECT code,title,media_count,views,price_idr FROM files WHERE active=TRUE ORDER BY id DESC LIMIT $1 OFFSET $2",
        per_page,page*per_page
    )
    if not rows:
        return await target.answer("Belum ada Code aktif." if lang=="id" else "No active Codes yet.")
    lines=["🔑 <b>DAFTAR CODE MEDIA</b>" if lang=="id" else "🔑 <b>MEDIA CODE LIST</b>"]
    buttons=[]
    for r in rows:
        title=html.escape(str(r["title"] or "Untitled")[:55])
        code=html.escape(str(r["code"]))
        price=int(r["price_idr"] or 0)
        lines.append(f"• <b>{title}</b> — <code>{code}</code> · {int(r['media_count'] or 0)} media")
        buttons.append([InlineKeyboardButton(text=f"📂 {str(r['title'] or r['code'])[:45]}", callback_data=f"browsecode:{r['code']}")])
    lines.append(f"\\nHalaman {page+1}/{max(1,(total+per_page-1)//per_page)} · Total {total} Code" if lang=="id" else
                 f"\\nPage {page+1}/{max(1,(total+per_page-1)//per_page)} · {total} Codes total")
    nav=[]
    if page>0: nav.append(InlineKeyboardButton(text="⬅️ Sebelumnya" if lang=="id" else "⬅️ Previous",callback_data=f"auto:codes:{page-1}"))
    if (page+1)*per_page<total: nav.append(InlineKeyboardButton(text="Berikutnya ➡️" if lang=="id" else "Next ➡️",callback_data=f"auto:codes:{page+1}"))
    if nav: buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="👑 VIP Bot",callback_data="keyword_vipbot"),
                    InlineKeyboardButton(text="💎 VIP",callback_data="keyword_vipgroup")])
    await target.answer("\\n".join(lines),parse_mode="HTML",reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))

@router.callback_query(F.data.startswith("auto:codes"))
async def auto_codes_page(c: CallbackQuery):
    parts=c.data.split(":")
    page=int(parts[2]) if len(parts)>2 and parts[2].isdigit() else 0
    await c.answer()
    await send_code_page(c.message,page)

@router.callback_query(F.data == "auto:group")
async def auto_group(c: CallbackQuery):
    rows=await quick_links(c.from_user.id)
    await c.answer()
    await c.message.answer(await _t(c.from_user.id,"bot_links"),parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows or [[InlineKeyboardButton(text="🏠 /start",callback_data="home")]]))

@router.callback_query(F.data == "auto:help")
async def auto_help(c: CallbackQuery):
    lang=await _lang(c.from_user.id)
    await c.answer()
    await c.message.answer("Ketik bantuan/cara untuk melihat panduan membuka media dan bergabung VIP." if lang=="id" else
                           "Type help/how to for instructions on opening media and joining VIP.")

@router.callback_query(F.data == "keyword_vipbot")
async def keyword_vipbot(c: CallbackQuery):
    lang = await _lang(c.from_user.id)
    text = ("👑 <b>VIP BOT</b>\\n\\nPilih jenis paket di bawah ini. Daftar paket diurutkan dari harga termurah ke termahal.\\n\\n💎 VIP Bot: kuota harian standar.\\n🔥 VVIP Bot: kuota harian lebih besar."
            if lang == "id" else
            "👑 <b>VIP BOT</b>\\n\\nChoose a package type. Packages are sorted from lowest to highest price.\\n\\n💎 VIP Bot: standard daily quota.\\n🔥 VVIP Bot: higher daily quota.")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 VIP Bot", callback_data="vipcat:vip"), InlineKeyboardButton(text="🔥 VVIP Bot", callback_data="vipcat:vvip")],
        [InlineKeyboardButton(text="❔ Bantuan" if lang == "id" else "❔ Help", callback_data="vipbot:help"), InlineKeyboardButton(text="🎁 Donasi" if lang == "id" else "🎁 Donate", callback_data="vipbot:donate")],
        [InlineKeyboardButton(text="🔙 Kembali" if lang == "id" else "🔙 Back", callback_data="home")],
    ])
    await c.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await c.answer()

@router.callback_query(F.data == "keyword_vipgroup")
async def keyword_vipgroup(c: CallbackQuery):
    from handlers.vip import show_vip_group_menu
    await show_vip_group_menu(c)

async def media_hint(m):
    from utils.admin_access import admin_access
    lang=await _lang(m.from_user.id)
    rows=[
        [InlineKeyboardButton(text="🔑 Code",callback_data="auto:codes"),
         InlineKeyboardButton(text="👑 VIP Bot",callback_data="keyword_vipbot")],
        [InlineKeyboardButton(text="💎 VIP Group",callback_data="keyword_vipgroup"),
         InlineKeyboardButton(text="❓ Bantuan",callback_data="auto:help")]
    ]
    if await admin_access(m.from_user.id):
        rows.insert(0,[InlineKeyboardButton(text="📤 /upload",callback_data="upfile")])
    await m.answer(
        "📎 Media diterima. Untuk melihat media yang tersedia, pilih Code. Jika ingin mengunggah media ke bot, gunakan /upload (admin)." if lang=="id" else
        "📎 Media received. Choose Code to browse available media. Uploading is available to admins with /upload.",
        parse_mode="HTML",reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

@router.message(F.chat.type == 'private', F.photo)
async def photo_hint(m): await media_hint(m)

@router.message(F.chat.type == 'private', F.video)
async def video_hint(m): await media_hint(m)

@router.message(F.chat.type == 'private', F.document)
async def document_hint(m): await media_hint(m)

@router.message(F.chat.type == 'private', F.audio)
async def audio_hint(m): await media_hint(m)

@router.message(F.chat.type.in_({'group','supergroup'}), F.chat.id == CODE_GROUP_ID, F.text.regexp(r'^[A-Za-z0-9]+_[123456789XxYy]{11}_[0-9]+p[0-9]+v[0-9]+d$'))
async def track_group_code(m):
    code=m.text.strip()
    p=await get_pool()
    row=await p.fetchrow("SELECT code FROM files WHERE lower(code)=lower($1) AND active=TRUE",code)
    if not row:
        return
    try:
        await p.execute(
            "INSERT INTO code_group_shares(code,group_id,shared_by) VALUES($1,$2,$3) "
            "ON CONFLICT(code,group_id) DO UPDATE SET last_seen_at=NOW()",
            code,m.chat.id,m.from_user.id
        )
    except Exception:
        pass
    from utils.group_notify import notify_code_detected
    await notify_code_detected(m.bot, m, row["code"])

@router.callback_query(F.data.startswith('groupget:'))
async def group_get_file(c):
    # This callback originates in the group. It must NEVER send media to the group.
    # It only sends a private control message after the user has started the bot.
    code=c.data.split(':',1)[1].strip()
    p=await get_pool()
    started=await p.fetchval("SELECT bot_started_at FROM users WHERE user_id=$1",c.from_user.id)
    if not started:
        await c.answer(await _t(c.from_user.id,"start_first"), show_alert=True)
        return

    f=await p.fetchrow(
        "SELECT code,title,media_count,price_idr,active FROM files "
        "WHERE lower(code)=lower($1) AND active=TRUE",code
    )
    if not f:
        await c.answer(await _t(c.from_user.id,"inactive"), show_alert=True)
        return

    from handlers.getfile import open_choices
    # Open the code in the user's private chat. A bot can only initiate this
    # because the user has already started the bot.
    try:
        await c.bot.send_message(
            c.from_user.id,
            f"CODE TERDETEKSI\n\n"
            f"Code: <code>{html.escape(f['code'])}</code>\n"
            f"Media: <b>{int(f['media_count'])}</b>\n\n"
            "Pilih GET FILE untuk melanjutkan.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="GET FILE", callback_data=f"getcode:{f['code']}")]
            ])
        )
        await c.answer(await _t(c.from_user.id,"sent_get"))
    except Exception:
        await c.answer(await _t(c.from_user.id,"open_private"), show_alert=True)
