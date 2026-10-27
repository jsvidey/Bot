from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from database import get_pool
from utils.payments import create_purchase, qr_bytes, enabled
from utils.callback_loading import loading
from utils.i18n import get_lang, translate

router = Router()


async def _lang(user_id: int) -> str:
    try:
        return await get_lang(user_id) or "id"
    except Exception:
        return "id"


def _t(lang: str, key: str, **kwargs) -> str:
    texts = {
        "buy_vip": {
            "id": "💎 <b>BUY VIP</b>\n\nPilih paket:",
            "en": "💎 <b>BUY VIP</b>\n\nChoose a package:",
            "zh": "💎 <b>购买 VIP</b>\n\n请选择套餐：",
        },
        "back": {"id": "🔙 Kembali", "en": "🔙 Back", "zh": "🔙 返回"},
        "unavailable": {
            "id": "Paket tidak tersedia.",
            "en": "Package is not available.",
            "zh": "套餐不可用。",
        },
        "payment_failed": {
            "id": "❌ Pembayaran ditutup atau gagal.",
            "en": "❌ Payment is closed or failed.",
            "zh": "❌ 支付已关闭或失败。",
        },
        "check_payment": {
            "id": "🔄 Cek Pembayaran",
            "en": "🔄 Check Payment",
            "zh": "🔄 检查支付",
        },
        "cancel": {"id": "❌ Batal", "en": "❌ Cancel", "zh": "❌ 取消"},
        "after_pay": {
            "id": "Setelah membayar, tekan Cek Pembayaran.",
            "en": "After paying, press Check Payment.",
            "zh": "完成支付后，请点击“检查支付”。",
        },
        "manual_qr_missing": {
            "id": "❌ QR manual belum dipasang.",
            "en": "❌ Manual QR has not been configured yet.",
            "zh": "❌ 手动 QR 尚未配置。",
        },
        "manual_title": {
            "id": "🧾 <b>QR MANUAL VIP</b>",
            "en": "🧾 <b>VIP MANUAL QR</b>",
            "zh": "🧾 <b>VIP 手动 QR</b>",
        },
        "send_proof": {
            "id": "Kirim screenshot bukti pembayaran.",
            "en": "Send a screenshot of your payment proof.",
            "zh": "请发送支付凭证截图。",
        },
    }
    return texts.get(key, {}).get(lang, texts.get(key, {}).get("id", key)).format(**kwargs)


def _package_name(row, lang):
    # Respect the package name configured by the admin (e.g. PREMIUM ACCES).
    return str(row["name"] or "VIP")


@router.callback_query(F.data.startswith("buy_vip"))
async def listvip(c):
    lang = await _lang(c.from_user.id)
    rows = await (await get_pool()).fetch(
        "SELECT code,name,price,duration_days FROM vip_packages WHERE active ORDER BY price"
    )
    kb = [
        [
            InlineKeyboardButton(
                text=f'💎 {_package_name(r, lang)} • Rp{int(r["price"]):,}'.replace(",", "."),
                callback_data=f'vip:{r["code"]}',
            )
        ]
        for r in rows
    ]
    kb.extend([[InlineKeyboardButton(text='🛍️ Ambil Sebagian',callback_data='vipsome')],[InlineKeyboardButton(text='🛒 Ambil Semua',callback_data='vipall')],[InlineKeyboardButton(text='ℹ️ About',callback_data='vipabout'),InlineKeyboardButton(text='🎁 Donasi',url='https://t.me/+ezE2-f-YtEo4NzU1')],[InlineKeyboardButton(text=_t(lang, "back"), callback_data="home")]])
    await c.message.edit_text(
        _t(lang, "buy_vip"),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb),
    )


@router.callback_query(F.data.startswith("vipbuy:"))
async def choose(c):
    lang = await _lang(c.from_user.id)
    code = c.data.split(":", 1)[1]
    r = await (await get_pool()).fetchrow(
        "SELECT * FROM vip_packages WHERE code=$1 AND active", code
    )
    if not r:
        return await c.answer(_t(lang, "unavailable"), show_alert=True)

    rows = []
    if await enabled("bayargg"):
        rows.append([
            InlineKeyboardButton(
                text="⚡ BayarGG",
                callback_data=f"vip_provider:{code}:bayargg",
            )
        ])
    if await enabled("cashi"):
        rows.append([
            InlineKeyboardButton(
                text="💳 Cashi",
                callback_data=f"vip_provider:{code}:cashi",
            )
        ])
    if await enabled("manual"):
        rows.append([
            InlineKeyboardButton(
                text=("🧾 QR Manual" if lang == "id" else "🧾 Manual QR"),
                callback_data=f"vip_manual:{code}",
            )
        ])
    rows.append([
        InlineKeyboardButton(
            text=_t(lang, "back"),
            callback_data="buy_vip",
        )
    ])

    await c.message.edit_text(
        f'💎 {_package_name(r, lang)}\n💵 Rp{int(r["price"]):,}'.replace(",", "."),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("vip:"))
async def package_detail(c):
    lang = await _lang(c.from_user.id)
    code = c.data.split(":", 1)[1]
    r = await (await get_pool()).fetchrow("SELECT * FROM vip_packages WHERE code=$1 AND active", code)
    if not r: return await c.answer(_t(lang, "unavailable"), show_alert=True)
    price = f"Rp{int(r['price']):,}".replace(',', '.')
    text = ("✨ <b>Detail Paket VVIP</b>\n\n📦 Nama Paket: <b>" + str(r['name']) + "</b>\n📝 Deskripsi: Dapatkan akses ke konten dan grup eksklusif setelah pembayaran berhasil.\n💰 Harga Normal: <b>" + price + "</b>\n\nSilakan klik tombol Bayar di bawah untuk melanjutkan!")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Bayar Sekarang", callback_data=f"vipbuy:{code}")],
        [InlineKeyboardButton(text="🔙 Kembali", callback_data="buy_vip")]
    ])
    await c.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await c.answer()

@router.callback_query(F.data == "vipabout")
async def vip_about(c):
    await c.message.edit_text("💳 <b>CARA MELAKUKAN PEMBAYARAN</b>\n\n🔹 Tekan /start\n🔹 Tekan Lihat Daftar VIP\n🔹 Pilih daftar yang diinginkan\n🔹 Tekan tombol Bayar Sekarang\n🔹 Lakukan pembayaran dan link akan dikirim setelah pembayaran terverifikasi.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Kembali",callback_data="buy_vip")]]))
    await c.answer()

@router.callback_query(F.data.startswith("vipsome"))
async def vip_some(c):
    selected = []
    if ":" in c.data:
        selected = [x for x in c.data.split(":",1)[1].split(",") if x]
    rows = await (await get_pool()).fetch("SELECT code,name,price FROM vip_packages WHERE active ORDER BY price")
    buttons=[]
    total=0
    for r in rows:
        code=str(r['code']); is_selected=code in selected
        if is_selected: total += int(r['price'])
        nxt=[x for x in selected if x != code]
        if not is_selected: nxt.append(code)
        callback='vipsome:'+','.join(nxt)
        buttons.append([InlineKeyboardButton(text=f"{'✅' if is_selected else '⬜'} {r['name']} • Rp{int(r['price']):,}".replace(',', '.'), callback_data=callback[:64])])
    buttons.append([InlineKeyboardButton(text=f"💰 Total: Rp{total:,} ({len(selected)} paket)".replace(',', '.'), callback_data='vipselectedpay:cashi:'+','.join(selected) if selected else 'vipsome')])
    buttons.append([InlineKeyboardButton(text="🔙 Kembali ke daftar VIP",callback_data="buy_vip")])
    await c.message.edit_text("🛍️ <b>Pilih Paket VIP/PREMIUM</b>\n\nPaket Harga Status\nPilih satu atau beberapa paket. Tekan tombol total untuk lanjut membayar.",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await c.answer()

@router.callback_query(F.data.startswith("vipselectedpay:"))
async def vip_selected_pay(c):
    parts=c.data.split(":",2)
    if len(parts)!=3 or not parts[2]: return await c.answer("Pilih minimal satu paket dulu.",show_alert=True)
    provider,codes=parts[1],parts[2]
    selected=[x for x in codes.split(',') if x]
    p=await get_pool(); rows=await p.fetch("SELECT code,name,price,duration_days FROM vip_packages WHERE active AND code=ANY($1::text[])",selected)
    if len(rows)!=len(selected): return await c.answer("Paket tidak tersedia lagi.",show_alert=True)
    amount=sum(int(r['price']) for r in rows); days=sum(int(r['duration_days']) for r in rows)
    result,status=await create_purchase(c.from_user.id,"vip",days,amount,provider,c.from_user.full_name,metadata={"vip_package_codes":selected})
    if not result:
        alternate="bayargg" if provider=="cashi" else "cashi"
        if await enabled(alternate): result,status=await create_purchase(c.from_user.id,"vip",days,amount,alternate,c.from_user.full_name,metadata={"vip_package_codes":selected})
        if not result: return await c.answer("Pembayaran tidak tersedia untuk total tersebut. Coba pilih paket lain.",show_alert=True)
        provider=alternate
    data=qr_bytes(result.get("qr_string")); text=f"🛒 <b>Pembelian {len(rows)} Paket VIP</b>\n💰 Total: <b>Rp{amount:,}</b>\n🏦 {provider.upper()}\n🧾 <code>{result['invoice_id']}</code>\n\nBayar lalu tekan Cek Pembayaran.".replace(',', '.')
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Cek Pembayaran",callback_data=f"paycheck:{result['invoice_id']}")],[InlineKeyboardButton(text="❌ Batal",callback_data=f"paycancel:{result['invoice_id']}")]])
    await c.answer()
    if data: await c.message.answer_photo(BufferedInputFile(data,filename="vip.png"),caption=text,parse_mode="HTML",reply_markup=kb)
    else: await c.message.answer(text,parse_mode="HTML",reply_markup=kb)

@router.callback_query(F.data == "vipdonate")
async def vip_donate(c):
    await c.message.edit_text("🎁 <b>Donasi</b>\n\nTerima kasih telah mendukung pengembangan bot. Untuk informasi donasi, silakan hubungi admin bot.",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 Chat Admin",callback_data="adm:chat")],[InlineKeyboardButton(text="🔙 Kembali",callback_data="buy_vip")]]))
    await c.answer()

@router.callback_query(F.data == "vipall")
async def vip_all(c):
    rows = await (await get_pool()).fetch("SELECT code,name,price FROM vip_packages WHERE active ORDER BY price")
    if not rows: return await c.answer("Belum ada paket aktif.",show_alert=True)
    total=sum(int(r['price']) for r in rows)
    lines=["🛒 <b>Ringkasan Ambil Semua VIP</b>",""]
    for r in rows: lines.append(f"• {r['name']} — Rp{int(r['price']):,}".replace(',', '.'))
    lines += ["",f"💰 Total: <b>Rp{total:,}</b> ({len(rows)} paket)".replace(',', '.')]
    codes=','.join(str(r['code']) for r in rows)
    kb=InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text="💳 Bayar Sekarang",callback_data=f"vipallpay:cashi:{codes}")],
      [InlineKeyboardButton(text="🔙 Kembali ke daftar VIP",callback_data="buy_vip")]
    ])
    await c.message.edit_text("\n".join(lines),parse_mode="HTML",reply_markup=kb)
    await c.answer()

@router.callback_query(F.data.startswith("vipallpay:"))
async def vip_all_pay(c):
    parts=c.data.split(":",2)
    if len(parts)!=3: return await c.answer("Data paket tidak valid.",show_alert=True)
    provider,codes=parts[1],parts[2]
    p=await get_pool(); selected=[x for x in codes.split(',') if x]
    rows=await p.fetch("SELECT code,name,price,duration_days FROM vip_packages WHERE active AND code=ANY($1::text[])",selected)
    if len(rows)!=len(selected): return await c.answer("Paket berubah/tidak tersedia. Muat ulang daftar VIP.",show_alert=True)
    amount=sum(int(r['price']) for r in rows); days=sum(int(r['duration_days']) for r in rows)
    result,status=await create_purchase(c.from_user.id,"vip",days,amount,provider,c.from_user.full_name,metadata={"vip_package_codes":selected})
    if not result:
        alternate="bayargg" if provider=="cashi" else "cashi"
        if await enabled(alternate): result,status=await create_purchase(c.from_user.id,"vip",days,amount,alternate,c.from_user.full_name,metadata={"vip_package_codes":selected})
        if not result: return await c.answer("Pembayaran belum tersedia untuk total paket ini.",show_alert=True)
        provider=alternate
    data=qr_bytes(result.get("qr_string")); price=f"Rp{amount:,}".replace(',', '.')
    text=f"💎 <b>Pembelian {len(rows)} Paket VIP</b>\n💰 Total: <b>{price}</b>\n🏦 Provider: {provider.upper()}\n🧾 Invoice: <code>{result['invoice_id']}</code>\n\nSetelah membayar, tekan Cek Pembayaran."
    kb=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 Cek Pembayaran",callback_data=f"paycheck:{result['invoice_id']}")],[InlineKeyboardButton(text="❌ Batal",callback_data=f"paycancel:{result['invoice_id']}")]])
    await c.answer()
    if data: await c.message.answer_photo(BufferedInputFile(data,filename="vip.png"),caption=text,parse_mode="HTML",reply_markup=kb)
    else: await c.message.answer(text,parse_mode="HTML",reply_markup=kb)

@router.callback_query(F.data.startswith("vip_provider:"))
async def pay(c, state):
    lang = await _lang(c.from_user.id)
    _, code, provider = c.data.split(":")
    r = await (await get_pool()).fetchrow(
        "SELECT * FROM vip_packages WHERE code=$1 AND active", code
    )

    result, status = await create_purchase(
        c.from_user.id,
        "vip",
        r["duration_days"],
        r["price"],
        provider,
        c.from_user.full_name,
        metadata={"vip_package_codes": [code]},
    )
    used_provider = provider
    # Automatically try the other configured provider before giving up.
    if not result:
        alternate = "cashi" if provider == "bayargg" else "bayargg"
        if await enabled(alternate):
            result, status = await create_purchase(
                c.from_user.id, "vip", r["duration_days"], r["price"],
                alternate, c.from_user.full_name, metadata={"vip_package_codes": [code]},
            )
            if result:
                used_provider = alternate
    if not result:
        # Both gateways failed: if manual QR is enabled and configured, create a
        # real pending manual payment and let the normal proof/approval workflow run.
        p = await get_pool()
        qr = await p.fetchval("SELECT value FROM settings WHERE key='manual_qr_file_id'")
        if await enabled("manual") and qr:
            from handlers.payments import ManualProofState
            manual = await p.fetchrow("""
                INSERT INTO manual_payments(user_id,amount,target_code,target_type,quantity,status)
                VALUES($1,$2,NULL,'vip',$3,'pending') RETURNING id
            """, c.from_user.id, int(r["price"]), int(r["duration_days"]))
            manual_id = int(manual["id"])
            await state.set_state(ManualProofState.proof)
            await state.update_data(kind="vip", quantity=int(r["duration_days"]), amount=int(r["price"]), target_code=None, manual_id=manual_id)
            caption = (f"🧾 <b>QR MANUAL VIP</b>\n\n{_package_name(r, lang)}\n💰 Rp{int(r['price']):,}\n\n".replace(",", ".")
                       + "Kedua provider otomatis gagal. Silakan bayar dengan QR ini lalu kirim screenshot bukti.")
            qr_message = await c.message.answer_photo(qr, caption=caption + f"\n\n🧾 ID: <code>{manual_id}</code>", parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Batal", callback_data=f"mancancel:{manual_id}")]]))
            await p.execute("UPDATE manual_payments SET qr_message_id=$1 WHERE id=$2", qr_message.message_id, manual_id)
            await c.answer("Provider gagal; dialihkan ke QR manual.", show_alert=True)
            return
        return await c.answer(_t(lang, "payment_failed"), show_alert=True)

    provider = used_provider
    data = qr_bytes(result.get("qr_string"))
    await c.answer()

    text = (
        f'💎 <b>{_package_name(r, lang)}</b>\n'
        f'💵 Rp{int(r["price"]):,}\n'
        f'🏦 {provider.upper()}\n'
        f'🧾 <code>{result["invoice_id"]}</code>\n\n'
        f'{_t(lang, "after_pay")}'
    ).replace(",", ".")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=_t(lang, "check_payment"),
                    callback_data=f'paycheck:{result["invoice_id"]}',
                )
            ],
            [
                InlineKeyboardButton(
                    text=_t(lang, "cancel"),
                    callback_data=f'paycancel:{result["invoice_id"]}',
                )
            ],
        ]
    )

    if data:
        await c.message.answer_photo(
            BufferedInputFile(data, filename="vip.png"),
            caption=text,
            parse_mode="HTML",
            reply_markup=kb,
        )
    else:
        await c.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=kb,
        )


@router.callback_query(F.data.startswith("vip_manual:"))
async def vip_manual(c, state):
    from handlers.payments import ManualProofState

    lang = await _lang(c.from_user.id)
    code = c.data.split(":", 1)[1]
    r = await (await get_pool()).fetchrow(
        "SELECT * FROM vip_packages WHERE code=$1 AND active", code
    )
    qr = await (await get_pool()).fetchval(
        "SELECT value FROM settings WHERE key='manual_qr_file_id'"
    )

    if not qr:
        return await c.answer(_t(lang, "manual_qr_missing"), show_alert=True)

    p = await get_pool()
    # Create the pending manual-payment row before asking for proof. The proof
    # handler only accepts proofs linked to an existing pending row.
    manual = await p.fetchrow("""
        INSERT INTO manual_payments(user_id,amount,target_code,target_type,quantity,status)
        VALUES($1,$2,NULL,'vip',$3,'pending') RETURNING id
    """, c.from_user.id, int(r["price"]), int(r["duration_days"]))
    manual_id = int(manual["id"])
    await state.set_state(ManualProofState.proof)
    await state.update_data(
        kind="vip",
        quantity=int(r["duration_days"]),
        amount=int(r["price"]),
        target_code=None,
        manual_id=manual_id,
    )

    caption = (
        f'{_t(lang, "manual_title")}\n\n'
        f'{_package_name(r, lang)}\n'
        f'💰 Rp{int(r["price"]):,}\n\n'
        f'{_t(lang, "send_proof")}'
    ).replace(",", ".")

    qr_message = await c.message.answer_photo(
        qr,
        caption=caption + f"\n\n🧾 ID pembayaran: <code>{manual_id}</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="❌ Batal", callback_data=f"mancancel:{manual_id}")
        ]]),
    )
    await p.execute("UPDATE manual_payments SET qr_message_id=$1 WHERE id=$2", qr_message.message_id, manual_id)


@router.message(F.text.in_({"💎 VIP Access", "Lihat Daftar VIP", "💳 VIP Access"}))
async def vip_access_menu(m: Message):
    lang=await _lang(m.from_user.id)
    rows=await (await get_pool()).fetch("SELECT code,name,price FROM vip_packages WHERE active ORDER BY price")
    buttons=[[InlineKeyboardButton(text=f"{r['name']} • Rp{int(r['price']):,}".replace(',', '.'),callback_data=f"vip:{r['code']}")] for r in rows]
    buttons += [[InlineKeyboardButton(text="🛍️ Ambil Sebagian",callback_data="vipsome")],[InlineKeyboardButton(text="🛒 Ambil Semua",callback_data="vipall")],[InlineKeyboardButton(text="ℹ️ About",callback_data="vipabout"),InlineKeyboardButton(text="🎁 Donasi",callback_data="vipdonate")]]
    await m.answer("📚 <b>Daftar VVIP Bot</b>\n\nInfo Nilai\n<b>ALL VIP GROUP</b>\nKeterangan: Daftar paket eksklusif. Klik paket untuk detail lengkap dan penawaran spesial.",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
