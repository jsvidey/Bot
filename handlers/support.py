import json, html, logging
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from database import get_pool
from config import ADMIN_IDS, OWNER_ID
from utils.admin_access import admin_access
from utils.i18n import get_lang

router = Router()
DEFAULT_VIP_CHANNELS = [
    {"title":"👑 PREMIUM", "subtitle":"", "url":"https://showlink.my.id/p/8e1b49"},
    {"title":"💎 VIP OXCIE", "subtitle":"Murah untuk 10 orang tercepat dan jika lebih maka harga naik", "url":"https://showlink.my.id/p/5243f6"},
    {"title":"💠 VIP VGK", "subtitle":"", "url":"https://showlink.my.id/p/c7e035"},
]

class SupportState(StatesGroup):
    chatting = State()

async def setting(key, default=""):
    p=await get_pool()
    return await p.fetchval("SELECT value FROM settings WHERE key=$1", key) or default

async def vip_channels():
    raw=await setting("vip_channels_json", "")
    if raw:
        try:
            rows=json.loads(raw)
            if isinstance(rows,list): return [r for r in rows if isinstance(r,dict) and r.get('title') and r.get('url')]
        except Exception: pass
    return DEFAULT_VIP_CHANNELS

async def vip_markup(rows):
    buttons=[]
    for r in rows:
        title=str(r.get('title','VIP'))[:60]
        url=str(r.get('url',''))
        if url.startswith(('https://','http://','tg://')):
            buttons.append([InlineKeyboardButton(text=title, url=url)])
    updates_url=await setting('vip_updates_url','https://t.me/+ezE2-f-YtEo4NzU1')
    if updates_url.startswith(('https://t.me/','https://telegram.me/')):
        buttons.append([InlineKeyboardButton(text='📢 Join Updates / Pantau Update', url=updates_url)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

async def render_channelvip(m: Message):
    rows=await vip_channels()
    lines=['💎 <b>VIP ACCESS</b>','⚡ <b>𝐈 𝐀𝐌 𝐏𝐑𝐎𝐆𝐑𝐀𝐌𝐄𝐑𝐒</b>','']
    for r in rows:
        lines.append(str(r.get('title','VIP')))
        if r.get('subtitle'): lines.append(f"└ {html.escape(str(r['subtitle']))}")
        lines.append(f"└ {html.escape(str(r['url']))}")
    lines += ['', '━━━━━━━━━━━━━━━━', '🚀 More VIP Groups Coming Soon!', '📢 Pantau update terbaru &amp; bantu share channel.', '🔗 ' + html.escape(str(await setting('vip_updates_url','https://t.me/+ezE2-f-YtEo4NzU1'))), '❤️‍🔥 Drop Your Reaction!', '⚡ LEARN • SHARE • GROW']
    await m.answer('\n'.join(lines), parse_mode='HTML', reply_markup=await vip_markup(rows))

@router.message(F.chat.type == 'private', Command('channelvip'))
async def channelvip_command(m: Message):
    await render_channelvip(m)

@router.message(F.chat.type == 'private', F.text.in_({'💎 VIP Access'}))
async def channelvip_button(m: Message):
    await render_channelvip(m)

@router.message(F.chat.type == 'private', Command('msg'))
async def msg_start(m: Message, state: FSMContext):
    if str(await setting('admin_chat_enabled','on')).lower() in {'off','0','false','no'}:
        return await m.answer('💬 Chat admin sedang ditutup. Silakan coba lagi nanti.')
    await state.set_state(SupportState.chatting)
    await m.answer('💬 <b>Chat Admin</b>\n\nKirim pertanyaan, request, atau pesanmu di sini. Admin akan membalas lewat bot.\nKetik /cancel untuk mengakhiri chat.', parse_mode='HTML')

@router.message(F.chat.type == 'private', F.text.in_({'💬 Chat Admin','💬 Message Admin'}))
async def msg_button(m: Message, state: FSMContext):
    await msg_start(m, state)

@router.message(SupportState.chatting, F.chat.type == 'private')
async def relay_to_admin(m: Message, state: FSMContext):
    if (m.text or '').strip().lower() == '/cancel':
        await state.clear()
        return await m.answer('✅ Chat admin ditutup. /msg untuk menghubungi admin lagi.')
    if str(await setting('admin_chat_enabled','on')).lower() in {'off','0','false','no'}:
        await state.clear()
        return await m.answer('Chat admin baru saja ditutup oleh admin.')
    p=await get_pool()
    rows=await p.fetch('SELECT user_id FROM users WHERE is_admin=TRUE')
    ids={int(r['user_id']) for r in rows}
    ids.update(ADMIN_IDS)
    if OWNER_ID: ids.add(OWNER_ID)
    ids.discard(m.from_user.id)
    if not ids:
        return await m.answer('Admin belum tersedia. Pesan belum terkirim; coba lagi nanti.')
    name=html.escape(m.from_user.full_name or 'User')
    username=('@'+html.escape(m.from_user.username)) if m.from_user.username else 'tanpa username'
    delivered=0
    for aid in ids:
        try:
            await m.bot.send_message(aid, f'💬 <b>PESAN USER</b>\nNama: {name}\nUsername: {username}\nID: <code>{m.from_user.id}</code>\n\nBalas dengan: <code>/reply {m.from_user.id} pesan</code>', parse_mode='HTML')
            await m.bot.copy_message(aid, m.chat.id, m.message_id)
            delivered+=1
        except Exception as e:
            logging.warning('Admin chat relay failed for %s: %s', aid, e)
    await m.answer('✅ Pesanmu sudah dikirim ke admin.' if delivered else '⚠️ Pesan belum terkirim. Coba lagi nanti.')

@router.message(F.chat.type == 'private', Command('reply'))
async def admin_reply(m: Message):
    if not await admin_access(m.from_user.id): return await m.answer('Akses ditolak.')
    parts=(m.text or '').split(maxsplit=2)
    if len(parts)<3 or not parts[1].isdigit():
        return await m.answer('Format: /reply USER_ID pesan balasan')
    uid=int(parts[1]); body=parts[2].strip()
    if not body: return await m.answer('Pesan balasan tidak boleh kosong.')
    try:
        await m.bot.send_message(uid, '💬 <b>Balasan Admin</b>\n\n'+html.escape(body), parse_mode='HTML')
        await m.answer('✅ Balasan terkirim.')
    except Exception as e:
        await m.answer('❌ Balasan gagal dikirim. User mungkin belum membuka bot atau telah memblokir bot.')
        logging.warning('Admin reply failed for %s: %s', uid, e)
