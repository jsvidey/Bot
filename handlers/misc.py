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


def _code_link(code: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?start={code}"

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

def _code_link(code):
    return f"https://t.me/Jsshowbot?start={code}"

def _code_text_row(r, prefix=""):
    title=html.escape((r['title'] or 'Untitled')[:60])
    href=html.escape(_code_link(r['code']),quote=True)
    price=int(r['price_idr'] or 0)
    paid=f" • 💰 Rp{price:,}".replace(',','.') if price else " • 🆓"
    return (
        f"{prefix}<a href=\"{href}\">📝 {title}</a>{paid}\n"
        f"👁 {r['views']} • 👍 {r['likes']} • 👎 {r['hates']} • ⭐ {r['favorites']}\n\n"
    )

async def _render_code_command(m: Message, mode: str = "top"):
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
            body += _code_text_row(row, f"{i}. ")
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
            text+=_code_text_row(r, f"{i}. " if mode!="all" else "")
        text+="Klik <b>Judul</b> untuk mencari/membuka media yang terhubung dengan CODE tersebut."
    await c.message.edit_text(text,parse_mode='HTML',reply_markup=await _code_nav(page,total,mode,c.from_user.id))

@router.callback_query(F.data=='code_all')
async def code_all(c):
    await loading(c); await _render_code_list(c,0,"all")

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
    f=await p.fetchrow("SELECT code,title,media_count,views,likes,hates,favorites,price_idr FROM files WHERE lower(code)=lower($1) AND active=TRUE", code)
    if not f: return await c.answer(await _t(c.from_user.id,'not_found'),show_alert=True)
    price=int(f['price_idr'] or 0)
    paid=f"💰 Harga: <b>Rp{price:,}</b>".replace(',','.') if price else "🆓 <b>FREE CODE</b>"
    href=html.escape(_code_link(f['code']),quote=True)
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
            [InlineKeyboardButton(text=await _t(c.from_user.id,'all_code'),callback_data='code_all')]
        ])
    )

HELP_TEXTS={
"id": """PANDUAN BOT DECODER

START & BAHASA
Tekan /start. Saat pertama kali menggunakan bot, bergabunglah dengan Channel Notifikasi dan Channel Backup, lalu tekan Verifikasi Join. Setelah itu pilih Indonesia atau English. Pilihan bahasa tersimpan dan dapat diganti kapan saja melalui /setting.

GET FILE
Tekan Getfile atau kirim CODE yang ingin dibuka. Media dikirim ke chat pribadi, bukan ke grup. Pastikan CODE benar dan masih aktif.

FREE CODE
Code gratis dapat dibuka sesuai aturan akses yang berlaku.

PAID CODE
Paid Code memiliki harga dalam Rupiah. Pilih salah satu metode QR yang tersedia. Jumlah pembayaran mengikuti harga Code. Akses akan aktif setelah pembayaran berhasil diverifikasi.

PEMBAYARAN QR
QR 1 adalah Cashi dan QR 2 adalah BayarGG. QR Manual dapat dipakai jika admin telah memasang QR dan mengaktifkan metode tersebut. Untuk QR Manual, bayar sesuai nominal lalu kirim bukti pembayaran agar admin dapat memeriksanya.

VIP
VIP memberikan akses sesuai durasi, kuota, dan ketentuan paket yang dibeli. Tekan VIP untuk melihat paket yang tersedia. Akses tetap mengikuti aturan paket aktif.

CODE & REVIEW
Tekan Code atau gunakan /codetop untuk melihat daftar Code populer. Gunakan /searchcode CODE untuk mencari Code tertentu. Pada halaman Code, gunakan Like, Hate, atau Favorite untuk memberikan penilaian.

RIWAYAT PEMBELIAN
Gunakan /mypurchases untuk melihat riwayat akses Paid Code yang pernah dibeli.

UPLOAD (ADMIN/OWNER)
Fitur Upfile hanya tersedia bagi admin/owner. Kirim media, judul, tag, lalu masukkan 0 untuk Code gratis atau harga untuk Paid Code.

MASALAH AKSES
Akses sementara dapat kedaluwarsa sesuai aturan Code. Jika pembayaran berhasil tetapi akses belum terbuka, hubungi admin dan sertakan Code serta bukti transaksi. Jangan bagikan invoice atau informasi pembayaran kepada orang lain.

Jika masih membutuhkan bantuan, tekan Help atau kembali ke menu utama.""",
"en": """BOT DECODER GUIDE

START & LANGUAGE
Press /start. On your first use, join the Notification Channel and Backup Channel, then tap Verify Join. Choose Indonesian or English. Your choice is saved and can be changed anytime with /setting.

GET FILE
Tap Getfile or send the CODE you want to open. Media is delivered to your private chat, not to a group. Make sure the CODE is correct and still active.

FREE CODE
Free Codes can be opened according to the applicable access rules.

PAID CODE
Paid Codes have a price in Indonesian Rupiah. Choose an available QR payment method. The payment amount matches the Code price. Access becomes active after payment is verified successfully.

QR PAYMENTS
QR 1 is Cashi and QR 2 is BayarGG. Manual QR is available if the admin has configured and enabled it. For Manual QR, pay the exact amount and submit proof so the admin can review it.

VIP
VIP provides access according to the purchased package duration, quota, and terms. Tap VIP to see available packages. Access remains subject to the active package rules.

CODE & REVIEWS
Tap Code or use /codetop to view popular Codes. Use /searchcode CODE to find a specific Code. On a Code page, use Like, Hate, or Favorite to rate it.

PURCHASE HISTORY
Use /mypurchases to view your previously purchased Paid Code access.

UPLOAD (ADMIN/OWNER)
Upfile is available only to admins/owner. Send media, title, and tags, then enter 0 for a free Code or a price for a Paid Code.

ACCESS ISSUES
Temporary access may expire according to the Code rules. If payment succeeds but access does not open, contact the admin and include the Code and transaction proof. Do not share invoices or payment details with others.

For more help, tap Help or return to the main menu."""
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


@router.message(F.chat.type=='private', F.text, ~F.text.startswith('/'))
async def keyword_help(m:Message):
    text=(m.text or '').strip().lower()
    if text in {'group','vip','video'}:
        rows=await quick_links(m.from_user.id)
        await m.answer(await _t(m.from_user.id,"bot_links"),parse_mode='HTML',
                       reply_markup=InlineKeyboardMarkup(inline_keyboard=rows or [[InlineKeyboardButton(text='🏠 Menu',callback_data='home')]]))
        return

    from utils.admin_access import admin_access
    if await admin_access(m.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=await _t(m.from_user.id,'upfile'),callback_data='upfile')]])
    else:
        kb = None
    await m.answer(await _t(m.from_user.id,'media_hint'),parse_mode='HTML',reply_markup=kb)

async def media_hint(m):
    from utils.admin_access import admin_access
    if await admin_access(m.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=await _t(m.from_user.id,'upfile'),callback_data='upfile')]])
    else:
        kb = None
    await m.answer(await _t(m.from_user.id,'media_hint'),parse_mode='HTML',reply_markup=kb)

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
