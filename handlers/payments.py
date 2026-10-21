
from aiogram import Router,F
from aiogram.filters import Command
from aiogram.types import CallbackQuery,InlineKeyboardMarkup,InlineKeyboardButton,Message
import html
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup,State
from config import OWNER_ID,ADMIN_IDS
from database import get_pool
from utils.admin_access import admin_access
router=Router()

class ManualProofState(StatesGroup):
    proof=State()
    qris=State()

def admin(uid): return uid==OWNER_ID or uid in ADMIN_IDS
def fmt(n): return f"Rp{int(n):,}".replace(',','.')


@router.callback_query(F.data.startswith('paycheck:'))
async def paycheck(c):
    invoice = c.data.split(':',1)[1].strip()
    if not invoice:
        return await c.answer('❌ ID pembayaran tidak valid.', show_alert=True)
    p=await get_pool()
    row=await p.fetchrow("SELECT * FROM purchases WHERE invoice_id=$1 AND user_id=$2", invoice, c.from_user.id)
    if not row:
        return await c.answer('❌ Pembayaran tidak ditemukan.', show_alert=True)
    if row['status']=='paid':
        return await c.answer('✅ Pembayaran sudah berhasil diproses.', show_alert=True)
    if row['status'] in {'cancelled','canceled','failed','expired'}:
        return await c.answer(f'❌ Pembayaran sudah {row["status"]}.', show_alert=True)
    from utils.bayargg import BayarGG
    from utils.cashi import Cashi
    result = await (BayarGG.check_payment(invoice) if row['provider']=='bayargg' else Cashi.check_payment(invoice))
    if not result:
        return await c.answer('⚠️ Gagal mengecek pembayaran. Coba lagi.', show_alert=True)
    status=str(result.get('status') or '').lower()
    if status in {'paid','success','completed','settled'}:
        from utils.payments import finalize_purchase
        ok=await finalize_purchase(invoice, result.get('amount') or result.get('paid_amount') or result.get('final_amount'))
        if ok:
            return await c.answer('✅ Pembayaran berhasil diproses!', show_alert=True)
        return await c.answer('⚠️ Pembayaran terdeteksi berhasil, tetapi aktivasi akses belum selesai. Coba cek lagi.', show_alert=True)
    if status in {'cancelled','canceled','failed','expired'}:
        await p.execute("UPDATE purchases SET status=$1 WHERE invoice_id=$2 AND status='pending'", status, invoice)
        return await c.answer(f'❌ Pembayaran {status}.', show_alert=True)
    return await c.answer('⏳ Pembayaran belum diterima. Setelah transfer, tekan Cek Pembayaran lagi.', show_alert=True)

@router.callback_query(F.data.startswith('paycancel:'))
async def paycancel(c):
    invoice = c.data.split(':',1)[1].strip()
    p=await get_pool()
    row=await p.fetchrow("SELECT id,status FROM purchases WHERE invoice_id=$1 AND user_id=$2",invoice,c.from_user.id)
    if not row:
        return await c.answer('❌ Pembayaran tidak ditemukan.', show_alert=True)
    if row['status']=='paid':
        return await c.answer('✅ Pembayaran sudah berhasil, tidak bisa dibatalkan.', show_alert=True)
    if row['status']!='pending':
        return await c.answer(f'❌ Pembayaran sudah {row["status"]}.', show_alert=True)
    # Do not invalidate the provider invoice. We only hide/remove the QR
    # message; a later Buy action can reuse the same still-valid QR/invoice.
    await c.answer('❌ Pembayaran dibatalkan. Jika QR belum expired, pembelian berikutnya akan memakai QR yang sama.', show_alert=True)
    try:
        await c.bot.delete_message(c.message.chat.id,c.message.message_id)
    except Exception:
        try: await c.message.edit_reply_markup(reply_markup=None)
        except Exception: pass

@router.callback_query(F.data.startswith('mancheck:'))
async def mancheck(c,state:FSMContext):
    did=int(c.data.split(':',1)[1]); p=await get_pool()
    row=await p.fetchrow("SELECT * FROM manual_payments WHERE id=$1 AND user_id=$2",did,c.from_user.id)
    if not row: return await c.answer('❌ Pembayaran manual tidak ditemukan.',show_alert=True)
    if row['status']!='pending': return await c.answer(f'❌ Status pembayaran: {row["status"]}.',show_alert=True)
    await state.set_state(ManualProofState.proof)
    await state.update_data(kind=row['target_type'] or 'file',quantity=row['quantity'] or 0,amount=int(row['amount']),target_code=row['target_code'],manual_id=did)
    await c.answer('📸 Kirim screenshot bukti pembayaran sekarang.',show_alert=True)
    try:
        await c.message.edit_caption(
            caption=f'🧾 <b>QR MANUAL</b>\n\n💰 {fmt(row["amount"])}\n🧾 ID: <code>{did}</code>\n\n📸 Silakan kirim screenshot bukti pembayaran.',
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='❌ Batal',callback_data=f'mancancel:{did}')]])
        )
    except Exception:
        pass

@router.callback_query(F.data.startswith('mancancel:'))
async def mancancel(c,state:FSMContext):
    did=int(c.data.split(':',1)[1]); p=await get_pool()
    row=await p.fetchrow("SELECT * FROM manual_payments WHERE id=$1 AND user_id=$2",did,c.from_user.id)
    if not row: return await c.answer('❌ Pembayaran tidak ditemukan.',show_alert=True)
    if row['status']=='approved': return await c.answer('✅ Pembayaran sudah disetujui.',show_alert=True)
    await p.execute("UPDATE manual_payments SET status='cancelled',processed_at=NOW() WHERE id=$1 AND status='pending'",did)
    await state.clear()
    if row['qr_message_id']:
        try: await c.bot.delete_message(c.message.chat.id,row['qr_message_id'])
        except Exception: pass
    await c.answer('❌ Pembayaran manual dibatalkan dan QR dihapus.',show_alert=True)


@router.message(ManualProofState.proof)
async def proof(m:Message,state:FSMContext):
    if not (m.photo or m.document):
        return await m.answer('❌ Kirim screenshot/foto bukti pembayaran.')
    d=await state.get_data(); p=await get_pool()
    fid=m.photo[-1].file_id if m.photo else m.document.file_id
    ftype='photo' if m.photo else 'document'
    manual_id=d.get('manual_id')
    if manual_id:
        row=await p.fetchrow("SELECT * FROM manual_payments WHERE id=$1 AND user_id=$2 AND status='pending'",int(manual_id),m.from_user.id)
    else:
        row=await p.fetchrow("""SELECT * FROM manual_payments WHERE user_id=$1 AND amount=$2 AND status='pending' AND proof_file_id IS NULL
          AND COALESCE(target_code,'')=COALESCE($3,'') ORDER BY id DESC LIMIT 1""",
          m.from_user.id,int(d.get('amount',0)),d.get('target_code'))
    if not row:
        return await m.answer('❌ Pembayaran manual tidak ditemukan atau sudah diproses.')
    await p.execute("""UPDATE manual_payments SET proof_file_id=$1,proof_type=$2,proof_message_id=$3,target_type=$4,quantity=$5 WHERE id=$6""",
                    fid,ftype,m.message_id,d.get('kind') or row['target_type'],d.get('quantity',row['quantity'] or 0),row['id'])
    await state.clear()
    await m.answer(f'✅ Bukti pembayaran diterima.\n🧾 ID: <code>{row["id"]}</code>\n\nMenunggu persetujuan admin.',parse_mode='HTML')
    for aid in [OWNER_ID,*ADMIN_IDS]:
        try:
            cap=(f'🔔 <b>MANUAL PAYMENT PROOF</b>\n\n'
                 f'🧾 ID: <code>{row["id"]}</code>\n'
                 f'🆔 User: <code>{m.from_user.id}</code>\n'
                 f'💰 {fmt(row["amount"])}\n'
                 f'📦 Type: <b>{html.escape(str(d.get("kind") or row["target_type"] or "Paid Code"))}</b>')
            buttons=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text='✅ Approve',callback_data=f'manapprove:{row["id"]}'),
                InlineKeyboardButton(text='❌ Reject',callback_data=f'manreject:{row["id"]}')
            ]])
            if ftype=='photo':
                await m.bot.send_photo(aid,fid,caption=cap,parse_mode='HTML',reply_markup=buttons)
            else:
                await m.bot.send_document(aid,fid,caption=cap,parse_mode='HTML',reply_markup=buttons)
        except Exception:
            pass

@router.message(Command('getqrisid'))
async def getqrisid(m,state:FSMContext):
 if not await admin_access(m.from_user.id): return
 await state.set_state(ManualProofState.qris)
 await m.answer('🧾 <b>SET QR MANUAL</b>\n\nKirim gambar QR yang ingin digunakan sebagai pembayaran manual.',parse_mode='HTML')

@router.message(ManualProofState.qris)
async def save_qris(m,state:FSMContext):
 if not await admin_access(m.from_user.id): return
 if not m.photo:return await m.answer('❌ Kirim gambar QR.')
 fid=m.photo[-1].file_id
 await (await get_pool()).execute("UPDATE settings SET value=$1 WHERE key='manual_qr_file_id'",fid)
 await state.clear(); await m.answer('✅ QR manual berhasil disimpan.')

@router.callback_query(F.data.startswith('manapprove:'))
async def approve(c):
 if not await admin_access(c.from_user.id): return await c.answer('No access',show_alert=True)
 did=int(c.data.split(':')[1]); p=await get_pool()
 async with p.acquire() as conn:
  async with conn.transaction():
   r=await conn.fetchrow("SELECT * FROM manual_payments WHERE id=$1 FOR UPDATE",did)
   if not r or r['status']!='pending': return await c.answer('Sudah diproses.',show_alert=True)
   await conn.execute("UPDATE manual_payments SET status='approved',admin_id=$1,processed_at=NOW() WHERE id=$2",c.from_user.id,did)
   if r['target_code']:
    f=await conn.fetchrow("SELECT owner_id,price_idr FROM files WHERE code=$1 AND active=TRUE",r['target_code'])
    if f:
     await conn.execute("UPDATE files SET views=views+1 WHERE code=$1",r['target_code'])
     await conn.execute("UPDATE users SET total_unlocks=total_unlocks+1 WHERE user_id=$2",r['user_id'])
     await conn.execute("""INSERT INTO unlock_transactions(user_id,code,payment_type,amount,expires_at)
        VALUES($1,$2,'qr',$3,NOW()+INTERVAL '24 hours')""",r['user_id'],r['target_code'],r['amount'])
   elif r['target_type'] in ('points','stars'):
    raise ValueError('Legacy points/stars purchases are disabled')
   elif r['target_type']=='vip':
    await conn.execute("""
     UPDATE users
     SET vip=TRUE,
         vip_until=GREATEST(COALESCE(vip_until,NOW()),NOW())+($1||' days')::interval,
         vip_plan_days=$1,
         vip_daily_limit=CASE
             WHEN $1=1 THEN 2
             WHEN $1=3 THEN 4
             WHEN $1=5 THEN 6
             WHEN $1=7 THEN 7
             WHEN $1=10 THEN 10
             WHEN $1=15 THEN 15
             WHEN $1=30 THEN 30
             ELSE GREATEST($1,1)
         END
     WHERE user_id=$2
    """,int(r['quantity']),r['user_id'])
 # Remove the user's manual QR after approval.
 try:
  if r['qr_message_id']:
   await c.bot.delete_message(int(r['user_id']),int(r['qr_message_id']))
 except Exception:
  pass
 await c.answer('Approved')
 try:
  await c.message.edit_reply_markup(reply_markup=None)
 except Exception:
  pass
 try:
  from config import TRANSACTION_CHAT_ID
  if TRANSACTION_CHAT_ID:
   await c.bot.send_message(TRANSACTION_CHAT_ID,
     f'💳 <b>TRANSACTION SUCCESS</b>\n\n👤 User ID: <code>{r["user_id"]}</code>\n📦 Type: <b>Manual {html.escape(str(r["target_type"] or "Paid Code"))}</b>\n🔢 Quantity: <b>{float(r["quantity"] or 0):g}</b>\n💰 Amount: <b>{fmt(r["amount"])}</b>\n🏦 Provider: <b>QR MANUAL</b>',
     parse_mode='HTML')
 except Exception:
  pass
 try:
  from aiogram.types import InlineKeyboardMarkup,InlineKeyboardButton
  if r['target_code']:
   await c.bot.send_message(r['user_id'],f'✅ Pembayaran manual disetujui.\n🔑 Code: <code>{r["target_code"]}</code>',parse_mode='HTML',reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='📥 Buka Code',callback_data=f'getcode:{r["target_code"]}')]]))
  elif r['target_type']=='vip':
   await c.bot.send_message(r['user_id'],'✅ Pembayaran manual disetujui. VIP telah diaktifkan.')
  else:
   await c.bot.send_message(r['user_id'],'✅ Pembayaran manual disetujui.')
 except: pass

@router.callback_query(F.data.startswith('manreject:'))
async def reject(c):
 if not await admin_access(c.from_user.id): return await c.answer('No access',show_alert=True)
 did=int(c.data.split(':')[1]); p=await get_pool()
 r=await p.fetchrow("UPDATE manual_payments SET status='rejected',admin_id=$1,processed_at=NOW() WHERE id=$2 AND status='pending' RETURNING user_id",c.from_user.id,did)
 await c.answer('Rejected' if r else 'Sudah diproses.'); 
 if r:
  try:
   full=await p.fetchrow("SELECT qr_message_id FROM manual_payments WHERE id=$1",did)
   if full and full['qr_message_id']:
    await c.bot.delete_message(int(r['user_id']),int(full['qr_message_id']))
  except: pass
  try: await c.bot.send_message(r['user_id'],'❌ Pembayaran manual ditolak. Silakan lakukan pembayaran baru jika diperlukan.')
  except: pass
