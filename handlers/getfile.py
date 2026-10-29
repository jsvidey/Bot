from __future__ import annotations

import re
from datetime import datetime,timedelta,timezone
import html,json,os,tempfile,asyncio,re
from aiogram import Router,F
from aiogram.types import Message,CallbackQuery,InlineKeyboardMarkup,InlineKeyboardButton,InputMediaPhoto,InputMediaVideo,InputMediaDocument,InputMediaAudio,BufferedInputFile
from database import get_pool
from utils.economy import unlock,is_vip,vip_allowed
from utils.media_sender import deliver_one, deliver_telegram_file_id
from utils.notify_channel import notify
from utils.callback_loading import loading
from config import MEDIA_SEND_DELAY_MS,BOT_USERNAME
from utils.payments import create_purchase,qr_bytes,enabled
from handlers.payments import ManualProofState
router=Router()

# ---------------------------------------------------------------------------
# 3-LANGUAGE USER TEXT
# Language is read from the same user preference used by the Dashboard.
# ---------------------------------------------------------------------------
try:
    from utils.i18n import get_lang
except Exception:
    async def get_lang(uid):
        return "id"

def _L(lang, key, **kw):
    lang = str(lang or "id").lower()
    if lang not in ("id", "en", "zh"):
        lang = "id"
    T = {
        "back":{"id":"🔙 Kembali","en":"🔙 Back","zh":"🔙 返回"},
        "invalid_code":{"id":"❌ Code tidak valid.","en":"❌ Invalid code.","zh":"❌ Code 无效。"},
        "send_code":{"id":"📥 Kirim CODE yang ingin dibuka.","en":"📥 Send the CODE you want to open.","zh":"📥 发送你要打开的 CODE。"},
        "not_found":{"id":"❌ Code tidak ditemukan.","en":"❌ Code not found.","zh":"❌ 未找到该 Code。"},
        "like":"Like", "hate":"Hate", "favorite":{"id":"⭐ Favorit","en":"⭐ Favorite","zh":"⭐ 收藏"},
        "open_code":{"id":"📥 Buka Code","en":"📥 Open Code","zh":"📥 打开 Code"},
        "own_open":{"id":"📂 Buka Code (Gratis)","en":"📂 Open Code (Free)","zh":"📂 打开 Code（免费）"},
        "own_title":{"id":"🔓 <b>CODE MILIK SENDIRI</b>","en":"🔓 <b>YOUR OWN CODE</b>","zh":"🔓 <b>你的 Code</b>"},
        "own_desc":{"id":"Media milikmu dapat dibuka gratis.","en":"Your own media can be opened for free.","zh":"自己的媒体可以免费打开。"},
        "paid_access":{"id":"<b>CODE SUDAH DIBAYAR</b>\n\nCode: <code>{code}</code>\nNominal: {price}\n\nAkses aktif sampai 24 jam setelah pembayaran.","en":"<b>CODE ALREADY PAID</b>\n\nCode: <code>{code}</code>\nAmount: {price}\n\nAccess is active for 24 hours after payment.","zh":"<b>CODE 已付款</b>\n\nCode：<code>{code}</code>\n金额：{price}\n\n付款后访问权限有效 24 小时。"},
        "open_paid":{"id":"Buka Media","en":"Open Media","zh":"打开媒体"},
        "vip_open":{"id":"💎 Buka Gratis (VIP)","en":"💎 Open Free (VIP)","zh":"💎 免费打开（VIP）"},
        "open_title":{"id":"🔐 <b>OPEN CODE</b>","en":"🔐 <b>OPEN CODE</b>","zh":"🔐 <b>打开 CODE</b>"},
        "choose_payment":{"id":"Pilih pembayaran:","en":"Choose a payment method:","zh":"请选择支付方式："},
        "choose_open":{"id":"Pilih cara membuka:","en":"Choose how to open:","zh":"请选择打开方式："},
        "cannot_open":{"id":"❌ Tidak dapat membuka media.","en":"❌ Unable to open the media.","zh":"❌ 无法打开媒体。"},
        "success_open":{"id":"✅ Berhasil dibuka!","en":"✅ Opened successfully!","zh":"✅ 打开成功！"},
        "own_success":{"id":"✅ Membuka code milik sendiri...","en":"✅ Opening your own code...","zh":"✅ 正在打开你的 Code…"},
        "private_chat":{"id":"Buka chat pribadi dengan bot untuk menerima media.","en":"Open a private chat with the bot to receive the media.","zh":"请打开与机器人的私聊以接收媒体。"},
        "media_corrupt":{"id":"❌ Data media rusak: {err}","en":"❌ Media data is corrupted: {err}","zh":"❌ 媒体数据损坏：{err}"},
        "all_sent":{"id":"Semua media sudah terkirim.","en":"All media have already been sent.","zh":"所有媒体都已发送。"},
        "sent":{"id":"📦 <b>{sent}</b> media berhasil dikirim.","en":"📦 <b>{sent}</b> media sent successfully.","zh":"📦 已成功发送 <b>{sent}</b> 个媒体。"},
        "done":{"id":"✅ <b>Semua media selesai dikirim.</b>\n📦 Total: <b>{total}</b>","en":"✅ <b>All media have been sent.</b>\n📦 Total: <b>{total}</b>","zh":"✅ <b>所有媒体发送完成。</b>\n📦 总数：<b>{total}</b>"},
        "continue":{"id":"▶️ Lanjut kirim","en":"▶️ Continue","zh":"▶️ 继续发送"},
        "cancel":{"id":"❌ Batal","en":"❌ Cancel","zh":"❌ 取消"},
        "stopped":{"id":"Pengiriman dihentikan.","en":"Sending stopped.","zh":"发送已停止。"},
        "cancelled":{"id":"❌ Pengiriman media dibatalkan.","en":"❌ Media delivery cancelled.","zh":"❌ 媒体发送已取消。"},
        "expired":{"id":"⏳ Akses code sudah habis.","en":"⏳ Code access has expired.","zh":"⏳ Code 访问权限已过期。"},
        "not_owner":{"id":"❌ Code ini bukan milikmu.","en":"❌ This code does not belong to you.","zh":"❌ 此 Code 不属于你。"},
        "payment_success":{"id":"✅ Pembayaran berhasil!","en":"✅ Payment successful!","zh":"✅ 支付成功！"},
        "free_code":{"id":"Code ini gratis.","en":"This code is free.","zh":"此 Code 免费。"},
        "qr_min":{"id":"Tidak ada metode QR yang mendukung nominal ini.","en":"No QR payment method supports this amount.","zh":"没有支持此金额的二维码支付方式。"},
        "qr_missing":{"id":"QR manual belum dipasang admin.","en":"Manual QR has not been configured by the admin.","zh":"管理员尚未设置手动二维码。"},
        "all_payment_fail":{"id":"Semua metode pembayaran tidak tersedia.","en":"All payment methods are unavailable.","zh":"所有支付方式均不可用。"},
        "all_payment_amount":{"id":"Semua metode pembayaran tidak tersedia untuk nominal ini.","en":"No payment method is available for this amount.","zh":"此金额没有可用的支付方式。"},
        "check_payment":{"id":"Cek Pembayaran","en":"Check Payment","zh":"检查支付"},
        "cancel_payment":{"id":"Batal","en":"Cancel","zh":"取消"},
        "manual_caption":{"id":"QR MANUAL\n\nCode: <code>{code}</code>\nNominal: {amount}\n\nSetelah membayar, tekan Cek Pembayaran lalu kirim screenshot bukti.","en":"MANUAL QR\n\nCode: <code>{code}</code>\nAmount: {amount}\n\nAfter paying, tap Check Payment and send the payment screenshot.","zh":"手动二维码\n\nCode：<code>{code}</code>\n金额：{amount}\n\n付款后点击“检查支付”，然后发送付款截图。"},
        "payment_caption":{"id":"PAYMENT\n\nCode: <code>{code}</code>\nNominal: {amount}\nProvider: {provider}\nInvoice: <code>{invoice}</code>\n\nSetelah membayar, tekan Cek Pembayaran.","en":"PAYMENT\n\nCode: <code>{code}</code>\nAmount: {amount}\nProvider: {provider}\nInvoice: <code>{invoice}</code>\n\nAfter paying, tap Check Payment.","zh":"支付\n\nCode：<code>{code}</code>\n金额：{amount}\n支付商：{provider}\nInvoice：<code>{invoice}</code>\n\n付款后点击“检查支付”。"},
        "media_missing":{"id":"⚠️ <b>MEDIA TIDAK TERSEDIA</b>","en":"⚠️ <b>MEDIA UNAVAILABLE</b>","zh":"⚠️ <b>媒体不可用</b>"},
        "failed_sent":{"id":"Media gagal dikirim: <b>{n}</b>","en":"Failed to send media: <b>{n}</b>","zh":"发送失败的媒体：<b>{n}</b>"},
    }
    v=T.get(key)
    if isinstance(v,str): return v.format(**kw)
    if isinstance(v,dict): return v.get(lang,v["id"]).format(**kw)
    return key.format(**kw)

async def _lang(uid):
    try:
        v=await get_lang(uid)
        if isinstance(v,str): return v
    except Exception:
        pass
    return "id"

def _btn(lang, key):
    return _L(lang,key)


def fmt(n): return f"Rp{int(n):,}".replace(',','.')

async def code_info_kb(code,title='Code',lang='id'):
    return InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text=f'📝 {title[:40]}',callback_data=f'getcode:{code}')],
      [InlineKeyboardButton(text='👍 Like',callback_data=f'react:like:{code}'),InlineKeyboardButton(text='👎 Hate',callback_data=f'react:hate:{code}'),InlineKeyboardButton(text=_L(lang,'favorite'),callback_data=f'react:favorite:{code}')],
      [InlineKeyboardButton(text=_L(lang,'open_code'),callback_data=f'getcode:{code}')],
      [InlineKeyboardButton(text='🎁 Donasi ⭐',callback_data='vipdonate')],
      [InlineKeyboardButton(text=_L(lang,'back'),callback_data='home')]
    ])

async def get_file(code):
    return await (await get_pool()).fetchrow("SELECT * FROM files WHERE (lower(code)=lower($1) OR lower(review_code)=lower($1)) AND active=TRUE",code)

async def has_permanent_or_paid_unlock(uid,code):
    p=await get_pool()
    return bool(await p.fetchval("""SELECT 1 FROM unlock_transactions WHERE user_id=$1 AND code=$2
        AND payment_type IN ('qr','admin') AND expires_at>NOW() ORDER BY id DESC LIMIT 1""",uid,code))

async def has_permanent_access(uid,code):
    p=await get_pool()
    return bool(await p.fetchval("""SELECT 1 FROM unlock_transactions WHERE user_id=$1 AND code=$2
        AND payment_type='admin' AND expires_at>NOW() ORDER BY id DESC LIMIT 1""",uid,code))

async def show(m,code):
    f=await get_file(code)
    if not f:return await m.answer(_L(await _lang(m.from_user.id),'invalid_code'))
    p=await get_pool()
    canonical=str(f['code'])
    await p.execute("UPDATE files SET views=views+1 WHERE code=$1", canonical)
    stats=await p.fetchrow("""SELECT views,likes,hates,favorites FROM files WHERE id=$1""",f['id'])
    price=int(f['price_idr'] or 0)
    paid=f"💰 Harga: <b>{fmt(price)}</b>" if price else "🆓 FREE CODE"
    lang=await _lang(m.from_user.id)
    review_code = str(f['review_code'] or '')
    if review_code and str(code).lower() in {review_code.lower(), canonical.lower()}:
        # Review is intentionally free. Show one review/preview item plus a clear
        # notification and inline actions; never send the complete paid media here.
        kb=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='🛒 Minat? Lanjut Buy Sekarang' if lang=='id' else '🛒 Interested? Buy Now',callback_data=f'getcode:{canonical}')],
            [InlineKeyboardButton(text='🔎 Cari Code Lain' if lang=='id' else '🔎 Find Another Code',callback_data='getfile')],
            [InlineKeyboardButton(text='❌ Batal',callback_data='home')],
        ])
        server_name = str(f.get('server_name') or '—')
        from utils.bot_identity import get_bot_username
        bot_name = await get_bot_username()
        caption=(
            f"⭐ <b>REVIEW GRATIS</b>\n\n"
            f"📝 <b>{html.escape(f['title'] or 'Untitled')}</b>\n"
            f"⭐ Code review: <code>{html.escape(review_code)}</code>\n"
            f"🔑 Code media: <code>{html.escape(canonical)}</code>\n"
            f"💰 Harga: <b>{fmt(price) if price else 'GRATIS'}</b>\n"
            f"📦 Media: <b>{int(f['media_count'] or 0)}</b>\n"
            f"🗂 Server: <b>{html.escape(server_name)}</b>\n"
            + (f"🤖 Bot: @{html.escape(bot_name)}\n" if bot_name else '')
            + "\n📢 Ini adalah review gratis. Media lengkap hanya tersedia setelah akses dibuka/pembayaran berhasil.\n\n"
            + ("Penasaran dengan media ini? Tekan tombol <b>Buy Now</b> di bawah." if lang=='id' else "Interested in the full media? Tap <b>Buy Now</b> below.")
        )
        raw_review=f['review_media']
        try:
            preview_items=raw_review if isinstance(raw_review,list) else json.loads(raw_review or '[]')
        except Exception:
            preview_items=[]
        preview=preview_items[0] if preview_items else None
        if preview:
            try:
                if len(preview_items)==1 and preview.get('type')=='video':
                    await m.bot.send_video(m.chat.id,preview['telegram_file_id'],caption=caption,parse_mode='HTML',reply_markup=kb)
                    return
                if preview_items and all(x.get('type')=='photo' for x in preview_items):
                    from aiogram.types import InputMediaPhoto
                    await m.bot.send_media_group(m.chat.id,media=[InputMediaPhoto(media=x['telegram_file_id']) for x in preview_items[:5]])
                    return await m.answer(caption,parse_mode='HTML',reply_markup=kb)
                if preview.get('drive_account') is not None and preview.get('drive_file_id'):
                    await deliver_one(m.bot,m.chat.id,preview,caption=caption,reply_markup=kb)
                else:
                    await deliver_telegram_file_id(m.bot,m.chat.id,preview,caption=caption,reply_markup=kb)
                return
            except Exception as preview_error:
                try:
                    await notify(m.bot, f"⚠️ <b>Review preview gagal dikirim</b>\\nCode: <code>{html.escape(review_code)}</code>\\nError: <code>{html.escape(str(preview_error)[:400])}</code>")
                except Exception:
                    pass
        # Text fallback keeps the review information and buttons available even
        # when the preview image has been deleted or cannot be fetched.
        return await m.answer(caption,parse_mode='HTML',reply_markup=kb)
    # Show the separately uploaded preview whenever a user opens the media code.
    try:
        raw_preview=f.get('review_media') if hasattr(f,'get') else f['review_media']
        preview_items=raw_preview if isinstance(raw_preview,list) else json.loads(raw_preview or '[]')
    except Exception:
        preview_items=[]
    try:
        if len(preview_items)==1 and preview_items[0].get('type')=='video':
            await m.bot.send_video(m.chat.id,preview_items[0]['telegram_file_id'],caption=f"🎬 Preview • {html.escape(f['title'] or 'Untitled')}",parse_mode='HTML')
        elif preview_items and all(x.get('type')=='photo' for x in preview_items):
            await m.bot.send_media_group(m.chat.id,media=[InputMediaPhoto(media=x['telegram_file_id']) for x in preview_items[:5]])
    except Exception:
        pass
    await m.answer(
      f"📦 <b>{html.escape(f['title'] or 'Untitled')}</b>\n\n"
      f"🔑 <code>{html.escape(canonical)}</code>\n{paid}\n"
      f"👁 Views: <b>{stats['views']}</b>  👍 <b>{stats['likes']}</b>  👎 <b>{stats['hates']}</b>  ⭐ <b>{stats['favorites']}</b>\n\n"
      f"Bagikan code ini ke teman-teman untuk membuka media ini.",
      parse_mode='HTML',reply_markup=await code_info_kb(canonical,f['title'] or 'Code',lang))

@router.callback_query(F.data=='getfile')
async def start(c):
    lang = await _lang(c.from_user.id)
    await loading(c)
    try:
        await c.message.edit_text(
            _L(await _lang(c.from_user.id),'send_code'),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=_L(lang,'back'), callback_data='home')]
            ])
        )
    except Exception:
        await c.message.answer(
            _L(await _lang(c.from_user.id),'send_code'),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=_L(lang,'back'), callback_data='home')]
            ])
        )

# Direct CODE input.
# Do not hard-code the random part of the code: deployments may use a
# different allowed alphabet/length.  Accept the canonical suffix
# ``<p>p<v>v<d>d`` and ignore accidental spaces/backticks around the code.
_CODE_RE = re.compile(r'^(?:JSShow_[A-Za-z0-9]{8,40}|JSShowreview_[A-Za-z0-9]{6,40}|[^\s_]+_[^\s_]+_\d+p\d+v\d+d)$', re.I)

@router.message(F.chat.type == 'private', F.text.regexp(re.compile(r'^`?(?:JSShow_[A-Za-z0-9]{8,40}|JSShowreview_[A-Za-z0-9]{6,40}|[^\s_]+_[^\s_]+_\d+p\d+v\d+d)`?$', re.IGNORECASE)))
async def receive(m):
    raw=(m.text or '').strip()
    # Users often paste a code wrapped in backticks or with whitespace.
    code=raw.strip('`').strip()
    if not _CODE_RE.fullmatch(code):
        return
    await show(m,code)

@router.callback_query(F.data.startswith('getcode:'))
async def getcode(c):
    await loading(c); code=c.data.split(':',1)[1]; f=await get_file(code)
    if not f:return await c.answer(_L(await _lang(c.from_user.id),'not_found'),show_alert=True)
    await c.answer()
    canonical=str(f['code'])
    await (await get_pool()).execute("UPDATE files SET views=views+1 WHERE code=$1", canonical)
    await open_choices(c,canonical,f)

async def _show_choices_message(c, text, **kwargs):
    """Edit text-based menus, but send a new message when invoked from a photo review."""
    try:
        return await c.message.edit_text(text, **kwargs)
    except Exception:
        return await c.message.answer(text, **kwargs)


async def open_choices(c,code,f):
    lang=await _lang(c.from_user.id)
    uid=c.from_user.id; n=int(f['media_count']); price=int(f['price_idr'] or 0)
    if int(f['owner_id']) == int(uid):
        kb=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=_L(lang,'own_open'),callback_data=f'openown:{code}')],
            [InlineKeyboardButton(text=_L(lang,'back'),callback_data='home')]
        ])
        return await _show_choices_message(c, 
            f"{_L(lang,'own_title')}\n\n"
            f"📝 {html.escape(f['title'] or 'Untitled')}\n"
            f"🔑 <code>{html.escape(code)}</code>\n📦 {n} media\n\n"
            f"{_L(lang,'own_desc')}",
            parse_mode='HTML',reply_markup=kb
        )
    access_mode=str(f['access_mode'] or 'all').lower()
    if access_mode=='vip' and not await is_vip(uid):
        kb=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text='💎 Beli VIP',callback_data='buy_vip')],
            [InlineKeyboardButton(text=_L(lang,'back'),callback_data='home')]
        ])
        return await _show_choices_message(c, '🔒 Code ini khusus member VIP. Silakan aktifkan paket VIP untuk membuka media.',reply_markup=kb)
    if access_mode=='free':
        price=0
    if price>0 and await has_permanent_or_paid_unlock(uid,code):
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=_L(lang,'open_paid'),callback_data=f'openpaid:{code}')],[InlineKeyboardButton(text=_L(lang,'back'),callback_data='home')]])
        return await _show_choices_message(c, _L(lang,'paid_access',code=html.escape(code),price=fmt(price)),parse_mode='HTML',reply_markup=kb)
    if await is_vip(uid):
        kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=_L(lang,'vip_open'),callback_data=f'openvip:{code}')],[InlineKeyboardButton(text=_L(lang,'back'),callback_data='home')]])
    else:
        rows=[]
        if price>0:
            if price >= 7000:
                has_discount = await (await get_pool()).fetchval("""SELECT 1 FROM discount_codes dc JOIN user_discount_codes ud ON ud.discount_id=dc.id
                  WHERE ud.user_id=$1 AND dc.active AND dc.starts_at<=NOW() AND dc.expires_at>NOW() AND dc.used_count<dc.max_uses
                  AND dc.min_price<=$2 AND dc.tier='all' AND (cardinality(dc.package_codes)=0 OR 'media'=ANY(dc.package_codes) OR '*'=ANY(dc.package_codes)) LIMIT 1""", uid, price)
                if has_discount:
                    rows.append([InlineKeyboardButton(text='🎟 Pakai Code Discount',callback_data=f'mediadiscount:{code}')])
            if await enabled('bayargg'): rows.append([InlineKeyboardButton(text='QR 2',callback_data=f'payfile:bayargg:{code}')])
            if await enabled('cashi'): rows.append([InlineKeyboardButton(text='QR 1',callback_data=f'payfile:cashi:{code}')])
            if await enabled('manual'): rows.append([InlineKeyboardButton(text='🧾 QR Manual',callback_data=f'payfile:manual:{code}')])
        else:
            rows.append([InlineKeyboardButton(text='📥 Buka Media' if lang=='id' else '📥 Open Media',callback_data=f'openfree:{code}')])
        rows.append([InlineKeyboardButton(text=_L(lang,'back'),callback_data='home')])
        kb=InlineKeyboardMarkup(inline_keyboard=rows)
    await _show_choices_message(c, 
      f"🔐 <b>OPEN CODE</b>\n\n📝 {html.escape(f['title'] or 'Untitled')}\n🔑 <code>{html.escape(code)}</code>\n📦 {n} media\n"
      +(f"💰 {fmt(price)}\n\n{_L(lang,'choose_payment')}" if price else f"\n{_L(lang,'choose_open')}"),
      parse_mode='HTML',reply_markup=kb)

async def _send_b2(bot, chat_id, item, caption=None):
    # Keep one canonical media-delivery implementation.
    return await deliver_one(bot, chat_id, item, caption=caption)

async def _send_telegram_fallback(bot, chat_id, item, caption=None):
    from utils.media_sender import deliver_telegram_file_id
    return await deliver_telegram_file_id(bot, chat_id, item, caption=caption)

async def send_page(bot, chat_id, code, media, page, access_expires_at=None, permanent=False):
    start = page * 10
    chunk = media[start:start + 10]
    missing = []
    sent = 0
    total = len(media)
    pool=await get_pool()
    file_settings = await pool.fetchrow("SELECT auto_delete,allow_forward,watermark_enabled FROM files WHERE code=$1", code)
    try:
        user_tier = await pool.fetchval(
            "SELECT CASE WHEN vip=TRUE AND (vip_until IS NULL OR vip_until>NOW()) THEN COALESCE(vip_tier,'vip') ELSE 'free' END FROM users WHERE user_id=$1",
            chat_id,
        )
        if user_tier == 'vvip':
            delay_key = 'vvip_media_send_delay_ms'
        elif user_tier == 'vip':
            delay_key = 'vip_media_send_delay_ms'
        else:
            delay_key = 'media_send_delay_ms'
        delay_value = await pool.fetchval("SELECT value FROM settings WHERE key=$1", delay_key)
        delay_ms=max(0,min(30000,int(delay_value or MEDIA_SEND_DELAY_MS)))
    except Exception:
        delay_ms=max(0,int(MEDIA_SEND_DELAY_MS))
    auto_delete = bool(file_settings and file_settings['auto_delete'])
    allow_forward = bool(file_settings['allow_forward']) if file_settings else True
    watermark_enabled = bool(file_settings['watermark_enabled']) if file_settings else True

    for i, item in enumerate(chunk, start + 1):
        from config import ALL_CODE_CHANNEL_URL
        if watermark_enabled:
            default_caption = (
                f"🔑 Code: {html.escape(str(code))}\n"
                f"📁 Media {i}/{total}\n"
                f"🤖 Bot: @{html.escape(await __import__('utils.bot_identity', fromlist=['get_bot_username']).get_bot_username())}\n"
                f"📢 Channel: <a href=\"{html.escape(str(ALL_CODE_CHANNEL_URL), quote=True)}\">Update</a>\n"
                f"🛠 <a href=\"https://t.me/+ezE2-f-YtEo4NzU1\">Pembuatan Bot dan Website</a>"
            )
            custom_watermark = await pool.fetchval("SELECT value FROM settings WHERE key='watermark_text'")
            if custom_watermark and str(custom_watermark).strip():
                caption = html.escape(str(custom_watermark).strip())
                caption = caption.replace('{code}', html.escape(str(code))).replace('{index}', str(i)).replace('{total}', str(total))
                from utils.bot_identity import get_bot_username
                caption = caption.replace('{bot}', '@' + html.escape(await get_bot_username())).replace('{channel}', html.escape(str(ALL_CODE_CHANNEL_URL)))
            else:
                caption = default_caption
        else:
            caption = None
        delivered = False
        telegram_error = None
        b2_error = None
        last_msg = None

        # Small files are stored in B2 and MUST be served from B2 first.
        # Telegram file_id is the fallback; files above 20 MiB have no B2 key.
        has_b2 = item.get('drive_account') is not None and bool(item.get('drive_file_id'))
        if has_b2:
            try:
                last_msg = await deliver_one(bot, chat_id, item, caption=caption, protect_content=not allow_forward)
                delivered = True
            except Exception as exc:
                b2_error = str(exc)
        if not delivered:
            try:
                last_msg = await deliver_telegram_file_id(bot, chat_id, item, caption=caption, protect_content=not allow_forward)
                delivered = True
            except Exception as exc:
                telegram_error = str(exc)
        if not delivered:
            reason = (
                f"Backblaze gagal: {str(b2_error or 'tidak digunakan untuk file ini')[:180]} | "
                f"Telegram file_id gagal: {str(telegram_error or 'tidak tersedia')[:180]}"
            )
            missing.append({'index': i, 'reason': reason})

        if delivered:
            sent += 1
            try:
                mid=int(getattr(last_msg,'message_id',0) or 0)
                if mid:
                    if permanent and not auto_delete:
                        await (await get_pool()).execute("""
                            INSERT INTO delivery_messages(user_id,chat_id,message_id,code,expires_at)
                            VALUES($1,$2,$3,$4,NOW()+INTERVAL '100 years')
                            ON CONFLICT(chat_id,message_id) DO NOTHING
                        """,chat_id,chat_id,mid,code)
                    elif permanent and auto_delete:
                        await (await get_pool()).execute("""
                            INSERT INTO delivery_messages(user_id,chat_id,message_id,code,expires_at)
                            VALUES($1,$2,$3,$4,NOW()+INTERVAL '24 hours')
                            ON CONFLICT(chat_id,message_id) DO NOTHING
                        """,chat_id,chat_id,mid,code)
                    else:
                        exp = access_expires_at
                        if exp is None:
                            exp = await (await get_pool()).fetchval("""
                                SELECT expires_at FROM unlock_transactions
                                WHERE user_id=$1 AND code=$2 AND expires_at>NOW()
                                ORDER BY expires_at DESC LIMIT 1
                            """,chat_id,code)
                        if exp is not None:
                            if auto_delete:
                                exp = min(exp, datetime.now(timezone.utc) + timedelta(hours=24))
                            await (await get_pool()).execute("""
                                INSERT INTO delivery_messages(user_id,chat_id,message_id,code,expires_at)
                                VALUES($1,$2,$3,$4,$5)
                                ON CONFLICT(chat_id,message_id) DO NOTHING
                            """,chat_id,chat_id,mid,code,exp)
            except Exception:
                pass

        await asyncio.sleep(delay_ms / 1000)

    if missing:
        lines = [
            "⚠️ <b>MEDIA TIDAK TERSEDIA</b>",
            "",
            f"🔑 <code>{html.escape(code)}</code>",
            f"Media gagal dikirim: <b>{len(missing)}</b>",
        ]
        for item in missing:
            lines.append(f"📁 Media {item.get('index', '?')}: {html.escape(str(item.get('reason', 'Sumber media tidak tersedia'))[:300])}")
        try:
            await bot.send_message(chat_id, "\n".join(lines), parse_mode="HTML")
        except Exception:
            pass
    return sent, missing

async def delivery_kb(code, page, total, done=False, lang='id'):
    pages = max(1, (int(total) + 9) // 10)
    rows = []
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text='⬅️ Prev', callback_data=f'page:{code}:{page-1}'))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton(text='Next ➡️', callback_data=f'page:{code}:{page+1}'))
    if nav: rows.append(nav)
    # Quick page-jump buttons for large collections, kept within Telegram callback limits.
    if pages > 2:
        jumps = [0, max(0, page-1), min(pages-1, page+1), pages-1]
        jumps = list(dict.fromkeys(jumps))
        rows.append([InlineKeyboardButton(text=f'📄 {n+1}', callback_data=f'page:{code}:{n}') for n in jumps])
    rows.append([
        InlineKeyboardButton(text='👍 Like', callback_data=f'react:like:{code}'),
        InlineKeyboardButton(text='👎 No Hate', callback_data=f'react:hate:{code}'),
        InlineKeyboardButton(text='⭐ Favorit', callback_data=f'react:favorite:{code}')
    ])
    rows.append([InlineKeyboardButton(text='🎁 Donasi ⭐', callback_data='vipdonate')])
    rows.append([InlineKeyboardButton(text='❌ Batal', callback_data=f'cancelget:{code}')])
    return InlineKeyboardMarkup(inline_keyboard=rows)

async def _access_expiry(uid, code):
    return await (await get_pool()).fetchval("""
        SELECT expires_at FROM unlock_transactions
        WHERE user_id=$1 AND code=$2 AND expires_at>NOW()
        ORDER BY expires_at DESC LIMIT 1
    """,uid,code)

async def deliver_page(c,code,page,permanent=False,access_expires_at=None):
    if c.message.chat.type != "private":
        await c.answer("Buka chat pribadi dengan bot untuk menerima media.", show_alert=True)
        return False
    f=await get_file(code)
    if not f:
        await c.answer(_L(await _lang(c.from_user.id),'not_found'),show_alert=True)
        return False
    try:
        raw_media = f['media']
        media = raw_media if isinstance(raw_media, list) else json.loads(raw_media or '[]')
        if not isinstance(media, list):
            raise ValueError('media bukan array')
        media = [x for x in media if isinstance(x, dict)]
    except Exception as exc:
        await c.answer(_L(await _lang(c.from_user.id),'media_corrupt',err=str(exc)[:120]), show_alert=True)
        return False
    total=len(media)
    if page*10 >= total:
        await c.answer(_L(await _lang(c.from_user.id),'all_sent'),show_alert=True)
        return True
    sent,_=await send_page(
        c.bot,c.from_user.id,code,media,page,
        access_expires_at=access_expires_at,permanent=permanent
    )
    done=(page+1)*10 >= total
    text=(_L(await _lang(c.from_user.id),'sent',sent=sent)
          if not done else
          _L(await _lang(c.from_user.id),'done',total=total))
    await c.message.answer(text,parse_mode='HTML',
                           reply_markup=await delivery_kb(code,page,total,done=done,lang=await _lang(c.from_user.id)))
    return True

@router.callback_query(F.data.startswith('continue:'))
async def continue_delivery(c):
    lang = await _lang(c.from_user.id)
    await loading(c)
    _,code,pg=c.data.split(':',2)
    f=await get_file(code)
    if not f:return await c.answer(_L(await _lang(c.from_user.id),'not_found'),show_alert=True)
    permanent=int(f['owner_id'])==int(c.from_user.id)
    exp=None if permanent else await _access_expiry(c.from_user.id,code)
    if not permanent and exp is None:
        return await c.answer(_L(lang,'expired'),show_alert=True)
    await c.answer()
    await deliver_page(c,code,int(pg),permanent=permanent,access_expires_at=exp)

@router.callback_query(F.data.startswith('cancelget:'))
async def cancel_delivery(c):
    await c.answer(_L(await _lang(c.from_user.id),'stopped'))
    try: await c.message.edit_text(_L(await _lang(c.from_user.id),'cancelled'))
    except Exception:
        try: await c.message.edit_reply_markup(reply_markup=None)
        except Exception: pass

@router.callback_query(F.data.startswith('openvip:'))
async def openvip(c):
    # A CallbackQuery must be acknowledged quickly. DB/payment/unlock work can
    # take several seconds, so acknowledge it before any awaited work.
    try:
        await c.answer()
    except Exception:
        pass
    lang = await _lang(c.from_user.id)
    code=c.data.split(':',1)[1]
    f=await get_file(code)
    if not f:
        return await c.message.answer(_L(await _lang(c.from_user.id),'not_found'))
    from utils.economy import vip_allowed, vip_cooldown_remaining
    if not await vip_allowed(c.from_user.id, code):
        remaining = await vip_cooldown_remaining(c.from_user.id, code)
        return await c.message.answer(
            f"⏳ <b>Jeda buka code masih aktif.</b>\\nCoba lagi sekitar {remaining} menit lagi.",
            parse_mode="HTML",
        )
    ok,_,reason,_=await unlock(c.from_user.id,code,int(f['media_count']),'vip')
    if not ok:
        if reason=='vip_quota':
            p=await get_pool()
            user_vip=await p.fetchrow("SELECT vip_plan_days,vip_tier FROM users WHERE user_id=$1",c.from_user.id)
            days=int(user_vip["vip_plan_days"] or 1) if user_vip else 1
            tier=str(user_vip["vip_tier"] or "vip") if user_vip else "vip"
            label="VVIP Bot" if tier=="vvip" else "VIP Bot"
            cb=f"vipcat:{tier}"
            return await c.message.answer(
                f"⚠️ <b>Kuota buka CODE VIP hari ini sudah habis.</b>\n\n💎 Paket kamu: <b>{html.escape(label)}</b>",
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text=f'💎 Perpanjang {label}',callback_data=cb)],
                    [InlineKeyboardButton(text=_L(lang,'back'),callback_data='home')]
                ])
            )
        return await c.message.answer(_L(lang,'cannot_open'))
    from utils.group_notify import notify_code_opened
    await notify_code_opened(c.bot, code, c.from_user.id, c.from_user.username, c.from_user.full_name)
    exp=await _access_expiry(c.from_user.id,code)
    await deliver_page(c,code,0,permanent=False,access_expires_at=exp)

@router.callback_query(F.data.startswith('openown:'))
async def openown(c):
    lang = await _lang(c.from_user.id)
    code=c.data.split(':',1)[1]
    f=await get_file(code)
    if not f:return await c.answer(_L(await _lang(c.from_user.id),'not_found'),show_alert=True)
    if int(f['owner_id']) != int(c.from_user.id):
        return await c.answer(_L(lang,'not_owner'),show_alert=True)
    await c.answer(_L(await _lang(c.from_user.id),'own_success'))
    from utils.group_notify import notify_code_opened
    await notify_code_opened(c.bot, code, c.from_user.id, c.from_user.username, c.from_user.full_name)
    await deliver_page(c,code,0,permanent=True,access_expires_at=None)


@router.callback_query(F.data.startswith('openfree:'))
async def openfree(c):
    code=c.data.split(':',1)[1]
    f=await get_file(code)
    if not f:
        return await c.answer(_L(await _lang(c.from_user.id),'not_found'),show_alert=True)
    if int(f['owner_id'])==int(c.from_user.id):
        return await c.answer('Gunakan tombol buka code milik sendiri.',show_alert=True)
    access_mode=str(f['access_mode'] or 'all').lower()
    if access_mode=='vip' and not await is_vip(c.from_user.id):
        return await c.answer('Code ini khusus member VIP.',show_alert=True)
    if int(f['price_idr'] or 0)>0 and access_mode!='free':
        return await c.answer('Code ini tidak gratis.',show_alert=True)
    p=await get_pool()
    await p.execute("""INSERT INTO unlock_transactions(user_id,code,payment_type,amount,expires_at)
        VALUES($1,$2,'admin',0,NOW()+INTERVAL '24 hours')""",c.from_user.id,code)
    await c.answer('Membuka media…')
    from utils.group_notify import notify_code_opened
    await notify_code_opened(c.bot,code,c.from_user.id,c.from_user.username,c.from_user.full_name)
    await deliver_page(c,code,0,permanent=False,access_expires_at=await _access_expiry(c.from_user.id,code))


@router.callback_query(F.data == 'dismissnotice')
async def dismiss_payment_notice(c):
    """Remove the temporary payment notice when the user dismisses it."""
    try:
        await c.answer()
    except Exception:
        pass
    if c.message:
        try:
            await c.message.delete()
        except Exception:
            try:
                await c.message.edit_reply_markup(reply_markup=None)
            except Exception:
                pass


@router.callback_query(F.data.startswith('openpaid:'))
async def openpaid(c):
    code=c.data.split(':',1)[1]; f=await get_file(code)
    if not f:return await c.answer('Code tidak ditemukan.',show_alert=True)
    if not await has_permanent_or_paid_unlock(c.from_user.id,code):
        return await c.answer(_L(await _lang(c.from_user.id),'expired'),show_alert=True)
    await c.answer(_L(await _lang(c.from_user.id),'success_open'))
    from utils.group_notify import notify_code_opened
    await notify_code_opened(c.bot, code, c.from_user.id, c.from_user.username, c.from_user.full_name)
    await deliver_page(c,code,0,permanent=False)
    # Once Open Media has been used, remove the payment notification itself.
    if c.message:
        try:
            await c.message.delete()
        except Exception:
            pass

@router.callback_query(F.data.startswith('mediadiscount:'))
async def media_discount_list(c):
    code=c.data.split(':',1)[1]
    f=await get_file(code)
    if not f: return await c.answer('Code media tidak ditemukan.',show_alert=True)
    original=int(f['price_idr'] or 0)
    if original < 7000: return await c.answer('Code discount hanya berlaku untuk harga Rp7.000 ke atas.',show_alert=True)
    p=await get_pool()
    rows=await p.fetch("""SELECT dc.* FROM discount_codes dc JOIN user_discount_codes ud ON ud.discount_id=dc.id
      WHERE ud.user_id=$1 AND dc.active AND dc.starts_at<=NOW() AND dc.expires_at>NOW() AND dc.used_count<dc.max_uses
      AND dc.min_price<=$2 AND dc.tier='all' AND (cardinality(dc.package_codes)=0 OR 'media'=ANY(dc.package_codes) OR '*'=ANY(dc.package_codes))
      ORDER BY dc.expires_at""",c.from_user.id,original)
    if not rows:
        return await c.answer('Tidak ada code discount yang cocok untuk Code Media ini.',show_alert=True)
    buttons=[]
    for d in rows:
        off=original*int(d['discount_value'])//100 if d['discount_type']=='percent' else int(d['discount_value'])
        final=max(1000,original-min(original-1000,off))
        buttons.append([InlineKeyboardButton(text=f"🎟 {d['code']} • Rp{final:,}".replace(',','.'),callback_data=f"mediadiscapply:{code}:{d['id']}")])
    buttons.append([InlineKeyboardButton(text='🔙 Kembali',callback_data=f'getcode:{code}')])
    await c.message.answer(f"🎟 Code Media: {code}\nHarga normal: Rp{original:,}\nPilih code discount:".replace(',','.'),reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await c.answer()

@router.callback_query(F.data.startswith('mediadiscapply:'))
async def media_discount_apply(c):
    _,code,discount_id=c.data.split(':',2)
    f=await get_file(code)
    if not f: return await c.answer('Code media tidak ditemukan.',show_alert=True)
    original=int(f['price_idr'] or 0)
    p=await get_pool()
    d=await p.fetchrow("""SELECT dc.* FROM discount_codes dc JOIN user_discount_codes ud ON ud.discount_id=dc.id
      WHERE dc.id=$1 AND ud.user_id=$2 AND dc.active AND dc.starts_at<=NOW() AND dc.expires_at>NOW() AND dc.used_count<dc.max_uses
      AND dc.min_price<=$3 AND dc.tier='all' AND (cardinality(dc.package_codes)=0 OR 'media'=ANY(dc.package_codes) OR '*'=ANY(dc.package_codes))""",int(discount_id),c.from_user.id,original)
    if not d or original<7000: return await c.answer('Code discount tidak valid atau tidak berlaku untuk media ini.',show_alert=True)
    off=original*int(d['discount_value'])//100 if d['discount_type']=='percent' else int(d['discount_value'])
    final=max(1000,original-min(original-1000,off))
    buttons=[]
    for provider,label in [('bayargg','QR 2'),('cashi','QR 1'),('manual','🧾 QR Manual')]:
        if await enabled(provider): buttons.append([InlineKeyboardButton(text=label,callback_data=f'payfile:{provider}:{code}:{d["id"]}')])
    if not buttons: return await c.answer('Metode pembayaran belum tersedia.',show_alert=True)
    await c.message.answer(f"🎟 Code Discount: {d['code']}\nHarga awal: Rp{original:,}\nPotongan: Rp{original-final:,}\n💰 Total bayar: Rp{final:,}".replace(',','.'),reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await c.answer()

@router.callback_query(F.data.startswith('payfile:'))
async def payfile(c,state):
    lang = await _lang(c.from_user.id)
    parts=c.data.split(':',3)
    if len(parts)<3: return await c.answer('Permintaan pembayaran tidak valid.',show_alert=True)
    _,requested,code=parts[:3]
    discount_id=int(parts[3]) if len(parts)>3 and parts[3].isdigit() else None
    f=await get_file(code)
    if not f:return await c.answer('Code tidak ditemukan.',show_alert=True)
    code=str(f['code'])
    # Never ask a user to pay for the same code again while their paid access is active.
    if await has_permanent_or_paid_unlock(c.from_user.id, code):
        return await c.answer('✅ Code ini sudah kamu beli. Buka code dari menu sebelumnya; tidak perlu membayar lagi.' if lang == 'id' else '✅ You already purchased this code. Open it from the previous menu; no need to pay again.', show_alert=True)
    # Avoid creating a second invoice while a manual proof for this code is still pending.
    pending = await (await get_pool()).fetchval("""SELECT 1 FROM manual_payments
        WHERE user_id=$1 AND target_code=$2 AND target_type='file' AND status='pending' LIMIT 1""", c.from_user.id, code)
    if pending:
        return await c.answer('🧾 Pembayaran untuk code ini masih menunggu proses. Kirim bukti atau tunggu admin memeriksa.' if lang == 'id' else '🧾 Payment for this code is already pending. Submit proof or wait for admin review.', show_alert=True)
    original_amount=int(f['price_idr'] or 0)
    amount=original_amount
    discount_row=None
    if discount_id:
        if original_amount < 7000:
            return await c.answer('Code discount hanya berlaku untuk harga Rp7.000 ke atas.',show_alert=True)
        discount_row=await (await get_pool()).fetchrow("""SELECT dc.* FROM discount_codes dc JOIN user_discount_codes ud ON ud.discount_id=dc.id
          WHERE dc.id=$1 AND ud.user_id=$2 AND dc.active AND dc.starts_at<=NOW() AND dc.expires_at>NOW() AND dc.used_count<dc.max_uses
          AND dc.min_price<=$3 AND dc.tier='all' AND (cardinality(dc.package_codes)=0 OR 'media'=ANY(dc.package_codes) OR '*'=ANY(dc.package_codes))""",discount_id,c.from_user.id,original_amount)
        if not discount_row: return await c.answer('Code discount sudah tidak valid atau kuotanya habis.',show_alert=True)
        off=original_amount*int(discount_row['discount_value'])//100 if discount_row['discount_type']=='percent' else int(discount_row['discount_value'])
        amount=max(1000,original_amount-min(original_amount-1000,off))
    if amount<=0:return await c.answer(_L(lang,'free_code'),show_alert=True)
    requested=str(requested).lower()
    # QR 1 (BayarGG) has a provider minimum of Rp5.000. Automatically
    # reroute smaller amounts to Cashi, and if Cashi is unavailable/fails,
    # fall back to the configured manual QR.
    provider=requested
    if requested=='bayargg' and amount<5000:
        if await enabled('cashi'):
            provider='cashi'
        elif await enabled('manual'):
            provider='manual'
        else:
            return await c.answer('Tidak ada metode QR yang mendukung nominal ini.',show_alert=True)
    if provider=='manual':
        qr=await (await get_pool()).fetchval("SELECT value FROM settings WHERE key='manual_qr_file_id'")
        if not qr:return await c.answer('QR manual belum dipasang admin.',show_alert=True)
        p=await get_pool()
        row=await p.fetchrow("""INSERT INTO manual_payments(user_id,amount,target_code,target_type,quantity,status)
          VALUES($1,$2,$3,'file',1,'pending') RETURNING id""",c.from_user.id,amount,code)
        msg=await c.message.answer_photo(qr,caption=f"QR MANUAL\n\nCode: <code>{html.escape(code)}</code>\nNominal: {fmt(amount)}" + (f"\nCode Discount: {html.escape(str(discount_row['code']))}\nHarga awal: {fmt(original_amount)}" if discount_row else '') + "\n\nSetelah membayar, tekan Cek Pembayaran lalu kirim screenshot bukti.",parse_mode='HTML',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Cek Pembayaran',callback_data=f'mancheck:{row["id"]}')],[InlineKeyboardButton(text='Batal',callback_data=f'mancancel:{row["id"]}')]]))
        await p.execute("UPDATE manual_payments SET qr_message_id=$1 WHERE id=$2",msg.message_id,row['id'])
        if discount_row:
            await p.execute("UPDATE discount_codes SET used_count=used_count+1 WHERE id=$1 AND used_count<max_uses",discount_id)
            await p.execute("DELETE FROM user_discount_codes WHERE user_id=$1 AND discount_id=$2",c.from_user.id,discount_id)
        return
    meta={"code":code}
    if discount_row: meta.update({"discount_id":discount_id,"discount_code":discount_row['code'],"original_amount":original_amount,"discount_amount":original_amount-amount})
    r,status=await create_purchase(c.from_user.id,'file',1,amount,provider,c.from_user.full_name,meta)
    # Automatic failover: requested provider -> other configured provider -> manual QR.
    if not r:
        fallback = 'cashi' if provider == 'bayargg' else 'bayargg'
        if await enabled(fallback) and (fallback != 'bayargg' or amount >= 5000):
            provider=fallback
            r,status=await create_purchase(c.from_user.id,'file',1,amount,provider,c.from_user.full_name,meta)
    if not r and await enabled('manual'):
        provider='manual'
        qr=await (await get_pool()).fetchval("SELECT value FROM settings WHERE key='manual_qr_file_id'")
        if not qr:return await c.answer('Semua metode pembayaran tidak tersedia.',show_alert=True)
        p=await get_pool(); row=await p.fetchrow("INSERT INTO manual_payments(user_id,amount,target_code,target_type,quantity,status) VALUES($1,$2,$3,'file',1,'pending') RETURNING id",c.from_user.id,amount,code)
        msg=await c.message.answer_photo(qr,caption=f"QR MANUAL\n\nCode: <code>{html.escape(code)}</code>\nNominal: {fmt(amount)}" + (f"\nCode Discount: {html.escape(str(discount_row['code']))}\nHarga awal: {fmt(original_amount)}" if discount_row else '') + "\n\nSetelah membayar, tekan Cek Pembayaran lalu kirim screenshot bukti.",parse_mode='HTML',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Cek Pembayaran',callback_data=f'mancheck:{row["id"]}')],[InlineKeyboardButton(text='Batal',callback_data=f'mancancel:{row["id"]}')]]))
        await p.execute("UPDATE manual_payments SET qr_message_id=$1 WHERE id=$2",msg.message_id,row['id'])
        if discount_row:
            await p.execute("UPDATE discount_codes SET used_count=used_count+1 WHERE id=$1 AND used_count<max_uses",discount_id)
            await p.execute("DELETE FROM user_discount_codes WHERE user_id=$1 AND discount_id=$2",c.from_user.id,discount_id)
        return
    if not r:return await c.answer('Semua metode pembayaran tidak tersedia untuk nominal ini.',show_alert=True)
    if discount_row:
        p=await get_pool()
        await p.execute("UPDATE discount_codes SET used_count=used_count+1 WHERE id=$1 AND used_count<max_uses",discount_id)
        await p.execute("DELETE FROM user_discount_codes WHERE user_id=$1 AND discount_id=$2",c.from_user.id,discount_id)
    data=qr_bytes(r.get('qr_string')); text=f"PAYMENT\n\nCode: <code>{code}</code>\nNominal: {fmt(amount)}" + (f"\nCode Discount: {html.escape(str(discount_row['code']))}\nHarga awal: {fmt(original_amount)}" if discount_row else '') + f"\nProvider: {provider.upper()}\nInvoice: <code>{r['invoice_id']}</code>\n\nSetelah membayar, tekan Cek Pembayaran."
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='Cek Pembayaran',callback_data=f'paycheck:{r["invoice_id"]}')],[InlineKeyboardButton(text='Batal',callback_data=f'paycancel:{r["invoice_id"]}')]])
    if data: await c.message.answer_photo(BufferedInputFile(data,filename='payment.png'),caption=text,parse_mode='HTML',reply_markup=kb)
    else: await c.message.answer(text,parse_mode='HTML',reply_markup=kb)

@router.callback_query(F.data.startswith('page:'))
async def page(c):
    lang = await _lang(c.from_user.id)
    _,code,pg=c.data.split(':',2)
    await loading(c)
    f=await get_file(code)
    if not f:return await c.answer(_L(await _lang(c.from_user.id),'not_found'),show_alert=True)
    permanent=int(f['owner_id'])==int(c.from_user.id)
    exp=None if permanent else await _access_expiry(c.from_user.id,code)
    if not permanent and exp is None:
        return await c.answer(_L(lang,'expired'),show_alert=True)
    await c.answer()
    await deliver_page(c,code,int(pg),permanent=permanent,access_expires_at=exp)

@router.callback_query(F.data.startswith('react:'))
async def react(c):
    _,reaction,code=c.data.split(':',2); p=await get_pool()
    f=await get_file(code)
    if not f:return await c.answer(_L(await _lang(c.from_user.id),'not_found'),show_alert=True)
    row=await p.fetchrow("SELECT 1 FROM code_reactions WHERE user_id=$1 AND code=$2 AND reaction=$3",c.from_user.id,code,reaction)
    col={'like':'likes','hate':'hates','favorite':'favorites'}[reaction]
    if row:
        await p.execute("DELETE FROM code_reactions WHERE user_id=$1 AND code=$2 AND reaction=$3",c.from_user.id,code,reaction)
        await p.execute(f"UPDATE files SET {col}=GREATEST({col}-1,0) WHERE code=$1",code)
    else:
        await p.execute("INSERT INTO code_reactions(user_id,code,reaction) VALUES($1,$2,$3) ON CONFLICT DO NOTHING",c.from_user.id,code,reaction)
        await p.execute(f"UPDATE files SET {col}={col}+1 WHERE code=$1",code)
    s=await p.fetchrow("SELECT likes,hates,favorites,views FROM files WHERE code=$1",code)
    await c.answer(f"👍 {s['likes']}  👎 {s['hates']}  ⭐ {s['favorites']}")
