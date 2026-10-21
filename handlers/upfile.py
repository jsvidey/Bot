
from __future__ import annotations
import asyncio,json,os,secrets,tempfile,html,re
from aiogram import Router,F
from aiogram.types import Message,CallbackQuery,InlineKeyboardMarkup,InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup,State
from database import get_pool
from config import MAX_MEDIA,BOT_USERNAME,PAID_CODE_MIN_IDR,PAID_CODE_MAX_IDR
from utils.b2_storage import b2_pool
from utils.callback_loading import loading
from utils.i18n import get_lang, translate
from utils.admin_access import admin_access
router=Router()
_LOCKS={}
class U(StatesGroup):
    media=State(); title=State(); tags=State(); price=State(); server=State(); access=State(); auto_delete=State(); forward=State(); watermark=State()

def rnd(n=14): return ''.join(secrets.choice('123456789XxYy') for _ in range(n))

async def new_code(counts=None):
    """Generate a unique public media code."""
    p=await get_pool()
    while True:
        code=f"JSShow_{rnd(14)}"
        if not await p.fetchval('SELECT 1 FROM files WHERE code=$1 OR lower(review_code)=lower($1)',code):
            return code

async def new_review_code():
    p=await get_pool()
    while True:
        code=f"JSShowreview_{rnd(10)}"
        if not await p.fetchval('SELECT 1 FROM files WHERE lower(code)=lower($1) OR lower(review_code)=lower($1)',code):
            return code


async def _lang(uid):
    return (await get_lang(uid) or "id").lower()

def _t(lang, key, **kw):
    T = {
        "up_title": {
            "id": "📤 <b>UP FILE</b>",
            "en": "📤 <b>UPLOAD FILE</b>",
            "zh": "📤 <b>上传文件</b>",
        },
        "up_start": {
            "id": "Kirim maksimal <b>{max}</b> media.\nMedia sampai 20 MB disimpan ke Backblaze B2. Media di atas 20 MB otomatis memakai Telegram file_id.\nSetelah selesai tekan <b>✅ Selesai Upload</b>.",
            "en": "Send up to <b>{max}</b> media files.\nMedia up to 20 MB is stored in Backblaze B2. Media above 20 MB automatically uses the Telegram file_id.\nWhen finished, press <b>✅ Finish Upload</b>.",
            "zh": "最多发送 <b>{max}</b> 个媒体文件。\n20 MB 以内的媒体会保存到 Backblaze B2。超过 20 MB 的媒体会自动使用 Telegram file_id。\n完成后点击 <b>✅ 完成上传</b>。",
        },
        "finish": {"id":"✅ Selesai Upload","en":"✅ Finish Upload","zh":"✅ 完成上传"},
        "cancel": {"id":"❌ Batal","en":"❌ Cancel","zh":"❌ 取消"},
        "received": {
            "id":"✅ <b>{n}/{max}</b> media diterima.",
            "en":"✅ <b>{n}/{max}</b> media received.",
            "zh":"✅ 已接收 <b>{n}/{max}</b> 个媒体。",
        },
        "size": {"id":"📎 Ukuran: <b>{size:.1f} MB</b>","en":"📎 Size: <b>{size:.1f} MB</b>","zh":"📎 大小：<b>{size:.1f} MB</b>"},
        "storage": {"id":"💾 Storage: <b>Telegram file_id</b>","en":"💾 Storage: <b>Telegram file_id</b>","zh":"💾 存储：<b>Telegram file_id</b>"},
        "large": {
            "id":"ℹ️ Media di atas 20 MB tidak dikirim ke B2.",
            "en":"ℹ️ Media above 20 MB is not uploaded to B2.",
            "zh":"ℹ️ 超过 20 MB 的媒体不会上传到 B2。",
        },
        "continue": {
            "id":"Tekan <b>✅ Selesai Upload</b> untuk lanjut.",
            "en":"Press <b>✅ Finish Upload</b> to continue.",
            "zh":"点击 <b>✅ 完成上传</b> 继续。",
        },
        "b2_unavailable": {
            "id":"⚠️ B2 tidak tersedia. Media disimpan menggunakan <b>Telegram file_id</b>。",
            "en":"⚠️ B2 is unavailable. The media is stored using the <b>Telegram file_id</b>.",
            "zh":"⚠️ B2 不可用。媒体将使用 <b>Telegram file_id</b> 保存。",
        },
        "loading": {
            "id":"⏳ <b>Loading…</b>\n\n📤 Menyimpan media <b>{n}/{max}</b>",
            "en":"⏳ <b>Loading…</b>\n\n📤 Saving media <b>{n}/{max}</b>",
            "zh":"⏳ <b>加载中…</b>\n\n📤 正在保存媒体 <b>{n}/{max}</b>",
        },
        "saved": {
            "id":"Tekan <b>✅ Selesai Upload</b> untuk lanjut.",
            "en":"Press <b>✅ Finish Upload</b> to continue.",
            "zh":"点击 <b>✅ 完成上传</b> 继续。",
        },
        "failed": {
            "id":"❌ <b>Gagal memproses media.</b>\n\n📦 Tersimpan: <b>{n}/{max}</b>",
            "en":"❌ <b>Failed to process media.</b>\n\n📦 Saved: <b>{n}/{max}</b>",
            "zh":"❌ <b>处理媒体失败。</b>\n\n📦 已保存：<b>{n}/{max}</b>",
        },
        "no_media": {"id":"❌ Belum ada media.","en":"❌ No media uploaded yet.","zh":"❌ 尚未上传媒体。"},
        "title_prompt": {
            "id":"📝 <b>MASUKKAN JUDUL</b>\n\n📦 {n} media siap disimpan.\n\nKirim judul code:",
            "en":"📝 <b>ENTER TITLE</b>\n\n📦 {n} media ready to save.\n\nSend the code title:",
            "zh":"📝 <b>输入标题</b>\n\n📦 {n} 个媒体已准备保存。\n\n请输入 Code 标题：",
        },
        "title_empty": {"id":"❌ Judul tidak boleh kosong.","en":"❌ Title cannot be empty.","zh":"❌ 标题不能为空。"},
        "tag_prompt": {
            "id":"🏷 <b>MASUKKAN TAG</b>\n\nContoh: <code>movie action 2026</code>\nKirim maksimal 10 tag. Jika tidak ada, kirim <code>-</code>.",
            "en":"🏷 <b>ENTER TAGS</b>\n\nExample: <code>movie action 2026</code>\nSend up to 10 tags. If none, send <code>-</code>.",
            "zh":"🏷 <b>输入标签</b>\n\n示例：<code>movie action 2026</code>\n最多发送 10 个标签。如果没有，请发送 <code>-</code>。",
        },
        "price_prompt": {
            "id":"💰 <b>MASUKKAN HARGA CODE</b>\n\nAdmin dapat membuat paid code.\nMinimal Rp{min} • Maksimal Rp{max} • kelipatan Rp1.000\nKirim <code>0</code> untuk FREE.",
            "en":"💰 <b>ENTER CODE PRICE</b>\n\nAdmins can create paid codes.\nMinimum Rp{min} • Maximum Rp{max} • increments of Rp1,000\nSend <code>0</code> for FREE.",
            "zh":"💰 <b>输入 CODE 价格</b>\n\n创作者可以创建付费 Code。\n最低 Rp{min} • 最高 Rp{max} • 必须为 Rp1,000 的倍数\n发送 <code>0</code> 表示免费。",
        },
        "media_missing": {"id":"❌ Media tidak ditemukan. Silakan mulai UP FILE lagi.","en":"❌ Media not found. Please start UP FILE again.","zh":"❌ 找不到媒体。请重新开始上传。"},
        "price_invalid": {"id":"❌ Harga tidak valid.","en":"❌ Invalid price.","zh":"❌ 价格无效。"},
        "price_range": {
            "id":"❌ Harga harus Rp{min} s/d Rp{max}.",
            "en":"❌ Price must be between Rp{min} and Rp{max}.",
            "zh":"❌ 价格必须在 Rp{min} 至 Rp{max} 之间。",
        },
        "cancelled": {"id":"❌ Upload dibatalkan.","en":"❌ Upload cancelled.","zh":"❌ 上传已取消。"},
    }
    lang = lang if lang in ("id","en","zh") else "id"
    return T[key][lang].format(**kw)

def _media_kb(lang):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=_t(lang, "finish"), callback_data="up_finish")],
        [InlineKeyboardButton(text=_t(lang, "cancel"), callback_data="up_cancel")]
    ])

def media_kb(lang='id'):
    return _media_kb(lang)

def clean_tags(s):
    parts=[re.sub(r'[,\n#]+',' ',x).strip() for x in (s or '').split()]
    return [x[:30] for x in parts if x][:10]

@router.callback_query(F.data=='upfile')
async def start(c,state):
    if not await admin_access(c.from_user.id):
        lang = await _lang(c.from_user.id)
        return await c.answer("Fitur ini khusus admin/owner." if lang == "id" else "This feature is for admins/owner only.", show_alert=True)
    await loading(c); await state.clear(); await state.set_state(U.media)
    lang = await _lang(c.from_user.id)
    await state.update_data(media=[],status_message_id=None, lang=lang)
    try:
        msg=await c.message.edit_text(
            _t(lang, "up_title") + "\n\n" + _t(lang, "up_start", max=MAX_MEDIA),
            parse_mode='HTML',reply_markup=_media_kb(lang))
    except Exception:
        msg=await c.message.answer(
            _t(lang, "up_title") + "\n\n" + _t(lang, "up_start", max=MAX_MEDIA),
            parse_mode='HTML',reply_markup=_media_kb(lang))
    await state.update_data(status_message_id=msg.message_id)

@router.message(F.chat.type == "private", U.media)
async def receive(m,state):
    uid=m.from_user.id
    lock=_LOCKS.setdefault(uid,asyncio.Lock())
    async with lock:
        d=await state.get_data()
        media=list(d.get('media',[]))
        status_id=d.get('status_message_id')
        lang = d.get('lang') or await _lang(uid)
        path=None

        if len(media)>=MAX_MEDIA:
            try: await m.delete()
            except: pass
            return

        typ=fid=name=mime=None
        size=0
        obj=None
        if m.photo:
            obj=m.photo[-1]
            typ='photo'; fid=obj.file_id; name=f'{obj.file_unique_id}.jpg'; mime='image/jpeg'; size=obj.file_size or 0
        elif m.video:
            obj=m.video
            typ='video'; fid=obj.file_id; name=obj.file_name or f'{obj.file_unique_id}.mp4'; mime=obj.mime_type or 'video/mp4'; size=obj.file_size or 0
        elif m.document:
            obj=m.document
            typ='document'; fid=obj.file_id; name=obj.file_name or obj.file_unique_id; mime=obj.mime_type or 'application/octet-stream'; size=obj.file_size or 0
        elif m.audio:
            obj=m.audio
            typ='audio'; fid=obj.file_id; name=obj.file_name or f'{obj.file_unique_id}.mp3'; mime=obj.mime_type or 'audio/mpeg'; size=obj.file_size or 0
        else:
            try: await m.delete()
            except: pass
            return

        file_unique_id=getattr(obj,'file_unique_id',None)
        # Backblaze path is limited to 20 MiB in this bot. Larger Telegram media
        # must NEVER be downloaded; Telegram file_id is already enough to send it.
        B2_MAX_BYTES=20*1024*1024

        def file_id_record():
            return {
                'telegram_file_id':fid,
                'telegram_file_unique_id':file_unique_id,
                'drive_account':None,
                'drive_file_id':None,
                'type':typ,
                'file_name':name,
                'file_size':size,
                'mime_type':mime,
                'storage_status':'telegram_file_id_only',
            }

        try:
            # IMPORTANT: no getFile/download for >20 MiB.
            if size > B2_MAX_BYTES:
                media.append(file_id_record())
                await state.update_data(media=media)
                if status_id:
                    try:
                        await m.bot.edit_message_text(
                            chat_id=m.chat.id,
                            message_id=status_id,
                            text=(_t(lang, "up_title") + "\n\n" +
                                  _t(lang, "received", n=len(media), max=MAX_MEDIA) + "\n\n" +
                                  _t(lang, "size", size=size / 1024 / 1024) + "\n" +
                                  _t(lang, "storage") + "\n" +
                                  _t(lang, "large") + "\n\n" +
                                  _t(lang, "continue")),
                            parse_mode='HTML',reply_markup=_media_kb(lang))
                    except: pass
                try: await m.delete()
                except: pass
                return

            # Small media still goes to B2 when available. If B2 is unavailable,
            # keep the Telegram file_id instead of rejecting the upload.
            if not b2_pool.available:
                media.append(file_id_record())
                await state.update_data(media=media)
                if status_id:
                    try:
                        await m.bot.edit_message_text(
                            chat_id=m.chat.id,message_id=status_id,
                            text=(_t(lang, "up_title") + "\n\n" +
                                  _t(lang, "received", n=len(media), max=MAX_MEDIA) + "\n\n" +
                                  _t(lang, "b2_unavailable")),
                            parse_mode='HTML',reply_markup=_media_kb(lang))
                    except: pass
                try: await m.delete()
                except: pass
                return

            if status_id:
                try:
                    await m.bot.edit_message_text(
                        chat_id=m.chat.id,message_id=status_id,
                        text=_t(lang, "loading", n=len(media)+1, max=MAX_MEDIA),
                        parse_mode='HTML',reply_markup=_media_kb(lang))
                except: pass

            fd,path=tempfile.mkstemp(prefix='pastele_')
            os.close(fd)
            try:
                f=await m.bot.get_file(fid)
                await m.bot.download_file(f.file_path,path)
                account,key,_=await b2_pool.upload(path,name,mime)
                media.append({
                    'telegram_file_id':fid,
                    'telegram_file_unique_id':file_unique_id,
                    'drive_account':account,
                    'drive_file_id':key,
                    'type':typ,
                    'file_name':name,
                    'file_size':size,
                    'mime_type':mime,
                    'storage_status':'b2_available'
                })
            except Exception as exc:
                # B2 failure is non-fatal. Preserve the media through file_id.
                media.append(file_id_record())
                await state.update_data(media=media)
                try:
                    await (await get_pool()).execute(
                        "INSERT INTO error_logs(source,message,user_id) VALUES($1,$2,$3)",
                        'upfile_b2_fallback',str(exc)[:1000],uid)
                except: pass
                try:
                    from utils.notify_channel import notify
                    await notify(m.bot,
                        f'⚠️ <b>UP FILE — B2 FALLBACK</b>\n\n'
                        f'🆔 User: <code>{uid}</code>\n'
                        f'📎 File: <code>{html.escape(name)}</code>\n'
                        f'❌ <code>{html.escape(str(exc)[:700])}</code>')
                except: pass
            finally:
                try: os.remove(path)
                except: pass
                path=None

            await state.update_data(media=media)
            if status_id:
                try:
                    await m.bot.edit_message_text(
                        chat_id=m.chat.id,message_id=status_id,
                        text=(_t(lang, "up_title") + "\n\n" +
                              _t(lang, "received", n=len(media), max=MAX_MEDIA) + "\n\n" +
                              _t(lang, "saved")),
                        parse_mode='HTML',reply_markup=_media_kb(lang))
                except: pass
            try: await m.delete()
            except: pass

        except Exception as exc:
            try: await m.delete()
            except: pass
            try:
                await (await get_pool()).execute(
                    "INSERT INTO error_logs(source,message,user_id) VALUES($1,$2,$3)",
                    'upfile',str(exc)[:1000],uid)
            except: pass
            if status_id:
                try:
                    await m.bot.edit_message_text(
                        chat_id=m.chat.id,message_id=status_id,
                        text=_t(lang, "failed", n=len(media), max=MAX_MEDIA),
                        parse_mode='HTML',reply_markup=_media_kb(lang))
                except: pass
        finally:
            if path:
                try: os.remove(path)
                except: pass

@router.callback_query(F.data=='up_finish')
async def finish(c,state):
    d=await state.get_data(); media=d.get('media',[])
    lang = d.get('lang') or await _lang(c.from_user.id)
    if not media:return await c.answer(_t(lang, "no_media"),show_alert=True)
    await state.set_state(U.title)
    await c.message.edit_text(_t(lang, "title_prompt", n=len(media)),parse_mode='HTML')

@router.message(U.title)
async def title(m,state):
    title=(m.text or '').strip()
    lang = (await state.get_data()).get('lang') or await _lang(m.from_user.id)
    if not title:return await m.answer(_t(lang, "title_empty"))
    await state.update_data(title=title[:150]); await state.set_state(U.tags)
    await m.answer(_t(lang, "tag_prompt"),parse_mode='HTML')

@router.message(U.tags)
async def tags(m,state):
    raw=(m.text or '').strip()
    tags=[] if raw=='-' else clean_tags(raw)
    await state.update_data(tags=tags)

    if not await admin_access(m.from_user.id):
        await state.clear()
        return await m.answer("Fitur upload hanya untuk admin/owner." if (await _lang(m.from_user.id)) == "id" else "Upload is available to admins/owner only.")
    await state.set_state(U.price)
    lang = (await state.get_data()).get('lang') or await _lang(m.from_user.id)
    await m.answer(
        _t(lang, "price_prompt", min=f"{PAID_CODE_MIN_IDR:,}".replace(",", "."), max=f"{PAID_CODE_MAX_IDR:,}".replace(",", ".")),
        parse_mode='HTML')


async def create_code(m,state,price:int):
    d=await state.get_data()
    media=d.get('media',[])
    title=d.get('title','Untitled')
    tags=d.get('tags',[])
    if not media:
        lang = await _lang(m.from_user.id)
        await state.clear()
        return await m.answer(_t(lang, "media_missing"))

    counts=[
        sum(x['type']=='photo' for x in media),
        sum(x['type']=='video' for x in media),
        sum(x['type']=='document' for x in media),
    ]
    code=await new_code(counts)
    review_code=await new_review_code()
    p=await get_pool()
    # Make sure the owner row exists before inserting files (FK-safe on fresh DBs).
    await p.execute("""INSERT INTO users(user_id,username,full_name)
        VALUES($1,$2,$3) ON CONFLICT(user_id) DO UPDATE SET
        username=COALESCE(EXCLUDED.username,users.username),
        full_name=COALESCE(EXCLUDED.full_name,users.full_name)""",
        m.from_user.id, m.from_user.username,
        (m.from_user.full_name or '').strip()[:200])
    # Critical: previously the handler generated a code but never persisted its
    # media record, so Getfile could not resolve the generated code.
    server_name=d.get('server_name','Server 1 — Media 5th ke bawah')
    access_mode=d.get('access_mode','all')
    auto_delete=bool(d.get('auto_delete',False))
    allow_forward=bool(d.get('allow_forward',True))
    watermark_enabled=bool(d.get('watermark_enabled', str(await p.fetchval("SELECT value FROM settings WHERE key='default_watermark_enabled'") or 'on').lower() == 'on'))
    # The first photo is the intentionally free review/preview. If no photo was
    # uploaded, use the first item as a fallback preview (video/document/audio).
    # The full media list remains the purchased content; the preview is shown only
    # through the review-code flow, which is the intended free review feature.
    review_preview = next((item for item in media if item.get('type') == 'photo'), None)
    if review_preview is None and media:
        review_preview = media[0]
    review_items = [review_preview] if review_preview else []
    await p.execute("""INSERT INTO files
        (code,review_code,code_type,owner_id,title,media,review_media,media_count,photo_count,video_count,document_count,audio_count,
         code_value_idr,price_idr,tags,server_name,access_mode,auto_delete,allow_forward,watermark_enabled,active)
        VALUES($1,$2,'media',$3,$4,$5::jsonb,$6::jsonb,$7,$8,$9,$10,$11,$12,$12,$13,$14,$15,$16,$17,$18,TRUE)""",
        code, review_code, m.from_user.id, title[:150], json.dumps(media,ensure_ascii=False),
        json.dumps(review_items,ensure_ascii=False), len(media), counts[0], counts[1], counts[2],
        sum(x.get('type')=='audio' for x in media), price, tags, server_name, access_mode, auto_delete, allow_forward, watermark_enabled)

    await state.clear()
    tagtext=' '.join('#'+html.escape(t) for t in tags) or '-'
    lang = await get_lang(m.from_user.id) or 'id'
    labels = {
        'id': ('Save Successful', 'Judul', 'Tag', 'Tipe', 'Bot', 'media', 'gratis', 'berbayar'),
        'en': ('Save Successful', 'Title', 'Tag', 'Type', 'Bot', 'media', 'free', 'paid'),
        'zh': ('创建成功', '标题', '标签', '类型', '机器人', '媒体', '免费', '付费'),
    }
    success, lbl_title, lbl_tag, lbl_type, lbl_bot, lbl_media, free_txt, paid_txt = labels.get(lang, labels['id'])
    type_text = paid_txt if price > 0 else free_txt
    bot_name = str(BOT_USERNAME or '').strip().lstrip('@')
    bot_text = f'@{html.escape(bot_name)}' if bot_name else '-'
    media_summary = f"{counts[1]}v{counts[0]}p" if counts[1] or counts[0] else f"{len(media)} media"
    price_summary = f"Rp{price:,}".replace(',', '.') if price else 'GRATIS'
    # Keep a convenient deep link so admin can immediately verify the free review.
    review_url = f"https://t.me/{bot_name}?start={review_code}" if bot_name else None
    media_url = f"https://t.me/{bot_name}?start={code}" if bot_name else None
    summary_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='👁 Lihat Review Gratis', url=review_url)] if review_url else [InlineKeyboardButton(text='⭐ Code Review', callback_data=f'getcode:{review_code}')],
        [InlineKeyboardButton(text='🔑 Buka Code Media', url=media_url)] if media_url else [InlineKeyboardButton(text='🔑 Code Media', callback_data=f'getcode:{code}')],
    ])
    await m.answer(
        f'✅ <b>{success}</b>\n'
        f'📝 Judul: {html.escape(title)}\n'
        f'⭐ Code review: <code>{html.escape(review_code)}</code>\n'
        f'🔑 Code media: <code>{html.escape(code)}</code>\n'
        f'💰 Price: <b>{html.escape(price_summary)}</b>\n'
        f'📦 Media: <b>{html.escape(media_summary)}</b> ({len(media)} total)\n'
        f'🗑 Hapus: <b>{"Ya" if auto_delete else "Tidak"}</b>\n'
        f'🚫 Batas forward: <b>{"Ya" if not allow_forward else "Tidak"}</b>\n'
        f'🗂 Server: <b>{html.escape(server_name)}</b>\n'
        f'🤖 Bot: {bot_text}\n'
        f'🏷 Tag: {tagtext}\n'
        f'🔐 Akses: {html.escape(access_mode.upper())}\n'
        f'💧 Watermark: {"ON" if watermark_enabled else "OFF"}\n'
        f'🏷 Tipe: {type_text}',
        parse_mode='HTML', reply_markup=summary_kb)


@router.message(U.price)
async def price(m,state):
    d=await state.get_data()
    try:
        price=int(re.sub(r'\D','',m.text or ''))
    except:
        price=-1
    if not await admin_access(m.from_user.id):
        await state.clear()
        return await m.answer("Fitur upload hanya untuk admin/owner." if (await _lang(m.from_user.id)) == "id" else "Upload is available to admins/owner only.")
    if price<0:return await m.answer(_t(await _lang(m.from_user.id), 'price_invalid'))
    if price and not (PAID_CODE_MIN_IDR<=price<=PAID_CODE_MAX_IDR):
        return await m.answer(_t(await _lang(m.from_user.id), 'price_range', min=f'{PAID_CODE_MIN_IDR:,}'.replace(',', '.'), max=f'{PAID_CODE_MAX_IDR:,}'.replace(',', '.')))
    await state.update_data(price=price)
    await state.set_state(U.server)
    await m.answer(
        "🗂 <b>PILIH SERVER</b>\n\n1 — Media 5th ke bawah\n2 — Media SMP\n3 — Tante/Janda/STW\n\nKirim angka 1, 2, atau 3.",
        parse_mode='HTML')

@router.message(U.server)
async def server(m,state):
    value=(m.text or '').strip().lower()
    options={
        '1':'Server 1 — Media 5th ke bawah', 'server 1':'Server 1 — Media 5th ke bawah',
        '2':'Server 2 — Media SMP', 'server 2':'Server 2 — Media SMP',
        '3':'Server 3 — Tante/Janda/STW', 'server 3':'Server 3 — Tante/Janda/STW',
    }
    if value not in options:
        return await m.answer('Pilihan tidak valid. Kirim angka 1, 2, atau 3.')
    await state.update_data(server_name=options[value])
    await state.set_state(U.access)
    await m.answer('🔐 <b>AKSES CODE</b>\nKirim salah satu: <code>all</code>, <code>free</code>, atau <code>vip</code>.',parse_mode='HTML')

@router.message(U.access)
async def access(m,state):
    value=(m.text or '').strip().lower()
    if value not in {'all','free','vip'}:
        return await m.answer('Pilihan tidak valid. Kirim all, free, atau vip.')
    d=await state.get_data()
    if value=='free': await state.update_data(access_mode=value,price=0)
    else: await state.update_data(access_mode=value)
    await state.set_state(U.auto_delete)
    await m.answer('🗑 <b>AUTO-DELETE</b>\nKirim <code>ya</code> atau <code>tidak</code>.',parse_mode='HTML')

@router.message(U.auto_delete)
async def auto_delete(m,state):
    value=(m.text or '').strip().lower()
    if value not in {'ya','tidak','yes','no','on','off'}:
        return await m.answer('Kirim ya/tidak (yes/no).')
    await state.update_data(auto_delete=value in {'ya','yes','on'})
    await state.set_state(U.forward)
    await m.answer('↗️ <b>IZINKAN FORWARD MEDIA?</b>\nKirim <code>ya</code> atau <code>tidak</code>.',parse_mode='HTML')

@router.message(U.forward)
async def forward(m,state):
    value=(m.text or '').strip().lower()
    if value not in {'ya','tidak','yes','no','on','off'}:
        return await m.answer('Kirim ya/tidak (yes/no).')
    await state.update_data(allow_forward=value in {'ya','yes','on'})
    await state.set_state(U.watermark)
    default_wm = str(await (await get_pool()).fetchval("SELECT value FROM settings WHERE key='default_watermark_enabled'") or 'on').lower()
    await m.answer(f'💧 <b>AKTIFKAN WATERMARK CAPTION?</b>\nDefault admin: <b>{"ON" if default_wm == "on" else "OFF"}</b>.\nKirim <code>ya</code>, <code>tidak</code>, atau <code>default</code>.',parse_mode='HTML')

@router.message(U.watermark)
async def watermark(m,state):
    value=(m.text or '').strip().lower()
    if value not in {'ya','tidak','yes','no','on','off','default'}:
        return await m.answer('Kirim ya/tidak/default (yes/no/default).')
    if value == 'default':
        value = str(await (await get_pool()).fetchval("SELECT value FROM settings WHERE key='default_watermark_enabled'") or 'on').lower()
    await state.update_data(watermark_enabled=value in {'ya','yes','on'})
    d=await state.get_data()
    await create_code(m,state,int(d.get('price') or 0))

@router.callback_query(F.data=='up_cancel')
async def cancel(c,state):
    await loading(c); await state.clear(); await c.message.edit_text(_t(await _lang(c.from_user.id), 'cancelled'))
