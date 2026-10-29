import html
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, ChatMemberUpdated, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile, LabeledPrice, PreCheckoutQuery
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


async def _show_bot_tier(target, tier: str):
    uid = target.from_user.id
    lang = await _lang(uid)
    rows = await (await get_pool()).fetch(
        "SELECT code,name,price,duration_days,daily_limit FROM vip_packages WHERE active AND tier=$1 ORDER BY price ASC, duration_days ASC, name ASC",
        tier,
    )
    title = "💎 VIP BOT" if tier == "vip" else "🔥 VVIP BOT"
    if not rows:
        text = f"{title}\n\nBelum ada paket aktif. Silakan hubungi admin." if lang == "id" else f"{title}\n\nNo active packages are available. Please contact the admin."
        buttons = [[InlineKeyboardButton(text="🔙 Kembali", callback_data="vipbot:home")]]
    else:
        lines = [title, "", "Paket diurutkan dari harga termurah ke termahal:" if lang == "id" else "Packages are sorted from lowest to highest price:", ""]
        buttons = []
        for r in rows:
            price = f"Rp{int(r['price']):,}".replace(",", ".")
            lines.append(f"• {r['name']} — buka code {int(r['daily_limit'])}x/hari — {price}")
            buttons.append([InlineKeyboardButton(
                text=f"{r['name']} • {price} • {int(r['daily_limit'])}x/hari",
                callback_data=f"vip:{r['code']}",
            )])
        buttons.append([InlineKeyboardButton(text="🔙 Kembali", callback_data="vipbot:home")])
        text = "\n".join(lines)
    markup = InlineKeyboardMarkup(inline_keyboard=buttons)
    if isinstance(target, Message):
        await target.answer(text, parse_mode="HTML", reply_markup=markup)
    else:
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        await target.answer()


@router.callback_query(F.data == "buy_vip")
async def listvip(c):
    lang = await _lang(c.from_user.id)
    text = "👑 <b>VIP BOT</b>\n\nPilih jenis paket:" if lang == "id" else "👑 <b>VIP BOT</b>\n\nChoose a package type:"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💎 VIP Bot", callback_data="vipcat:vip"), InlineKeyboardButton(text="🔥 VVIP Bot", callback_data="vipcat:vvip")],
        [InlineKeyboardButton(text="🔙 Kembali", callback_data="home")],
    ])
    await c.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await c.answer()


@router.callback_query(F.data.startswith("vipcat:"))
async def vip_category(c):
    tier = c.data.split(":", 1)[1]
    if tier not in {"vip", "vvip"}:
        return await c.answer("Kategori tidak valid.", show_alert=True)
    await _show_bot_tier(c, tier)


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
    tier = str(r["tier"] or "vip")
    rows.append([
        InlineKeyboardButton(
            text=_t(lang, "back"),
            callback_data=f"vipcat:{tier}",
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
    if not r:
        return await c.answer(_t(lang, "unavailable"), show_alert=True)
    price = f"Rp{int(r['price']):,}".replace(",", ".")
    tier = str(r["tier"] or "vip")
    tier_name = "VVIP Bot" if tier == "vvip" else "VIP Bot"
    limit = int(r["daily_limit"] or 1)
    text = (
        f"📦 <b>{html.escape(str(r['name']))}</b>\n\n"
        f"🏷️ Jenis: <b>{tier_name}</b>\n"
        f"⏳ Durasi: <b>{int(r['duration_days'])} hari</b>\n"
        f"🔓 Kuota buka code: <b>{limit} kali per hari</b>\n"
        f"💰 Harga: <b>{price}</b>\n\n"
        "Setelah pembayaran dikonfirmasi, status aktif otomatis."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟 Code Discount Saya", callback_data=f"vipdiscount:{code}")],
        [InlineKeyboardButton(text="💳 Bayar Sekarang", callback_data=f"vipbuy:{code}")],
        [InlineKeyboardButton(text="🔙 Kembali", callback_data=f"vipcat:{tier}")],
    ])
    await c.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await c.answer()



def _vipg_text(lang, id_text, en_text):
    return id_text if lang == "id" else en_text


async def show_vip_group_menu(target):
    """Entry screen for /vip: payment instructions and VIP Group actions."""
    uid = target.from_user.id
    lang = await _lang(uid)
    text = (
        "💳 <b>CARA MELAKUKAN PEMBAYARAN</b>\n"
        "🔹 Tekan /start\n"
        "🔹 Tekan Lihat Daftar VIP\n"
        "🔹 Pilih daftar yang diinginkan\n"
        "🔹 Tekan tombol Bayar Harga Normal\n"
        "🔹 Lakukan pembayaran dan link grup akan dikirimkan secara otomatis."
        if lang == "id" else
        "💳 <b>HOW TO PAY</b>\n"
        "🔹 Press /start\n"
        "🔹 Tap View VIP List\n"
        "🔹 Choose the package you want\n"
        "🔹 Tap Pay Normal Price\n"
        "🔹 Complete the payment and the group link will be sent automatically."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Lihat Daftar VIP" if lang == "id" else "📚 View VIP List", callback_data="vg:list")],
        [InlineKeyboardButton(text="ℹ️ About", callback_data="vipabout"),
         InlineKeyboardButton(text="❤️‍🔥 Donasi" if lang == "id" else "❤️‍🔥 Donate", callback_data="vipdonate")],
    ])
    if isinstance(target, Message):
        await target.answer(text, parse_mode="HTML", reply_markup=kb)
    else:
        await target.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
        await target.answer()


def _vipg_back(lang, callback="vg:home"):
    return InlineKeyboardButton(text="🔙 Kembali ke VIP" if lang == "id" else "🔙 Back to VIP", callback_data=callback)


async def _vipg_list(c, edit=True):
    lang = await _lang(c.from_user.id)
    rows = await (await get_pool()).fetch("SELECT code,name,price FROM vip_group_packages WHERE active ORDER BY price, name")
    buttons = [[InlineKeyboardButton(
        text=f"{r['name']} {int(r['price'])//1000}k" if lang == "id" else f"{r['name']} Rp{int(r['price']):,}".replace(",", "."),
        callback_data=f"vg:detail:{r['code']}"
    )] for r in rows]
    buttons += [
        [InlineKeyboardButton(text="🛍️ Ambil sebagian" if lang == "id" else "🛍️ Select some", callback_data="vg:some")],
        [InlineKeyboardButton(text="🛒 Borong semuanya" if lang == "id" else "🛒 Get everything", callback_data="vg:all")],
        [_vipg_back(lang)],
    ]
    text = (
        "📚 <b>Daftar VIP Bot</b>\n\nKeterangan: Daftar paket eksklusif. Klik paket untuk detail lengkap dan penawaran spesial."
        if lang == "id" else
        "📚 <b>VIP Group List</b>\n\nExclusive packages. Select a package to view its details and special offer."
    )
    await c.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await c.answer()


async def _vipg_pay(c, codes):
    lang = await _lang(c.from_user.id)
    codes = list(dict.fromkeys(str(x) for x in codes if x))
    if not codes:
        return await c.answer("Pilih minimal satu paket dulu." if lang == "id" else "Choose at least one package first.", show_alert=True)
    p = await get_pool()
    rows = await p.fetch("SELECT code,name,price FROM vip_group_packages WHERE active AND code=ANY($1::text[])", codes)
    if len(rows) != len(codes):
        return await c.answer("Paket tidak tersedia lagi." if lang == "id" else "One or more packages are no longer available.", show_alert=True)
    amount = sum(int(r["price"]) for r in rows)
    days = 30
    meta = {"vip_group_package_codes": codes}
    result = None
    provider_used = None
    for provider in ("bayargg", "cashi"):
        if await enabled(provider):
            result, status = await create_purchase(c.from_user.id, "vip", days, amount, provider, c.from_user.full_name, metadata=meta)
            if result:
                provider_used = provider
                break
    if not result:
        return await c.answer(
            "Pembayaran sedang tidak tersedia. Coba lagi nanti atau hubungi admin." if lang == "id" else
            "Payment is currently unavailable. Try again later or contact the admin.",
            show_alert=True
        )
    qr = qr_bytes(result.get("qr_string"))
    title = "Pembelian VIP Group" if lang == "id" else "VIP Group purchase"
    paytext = (
        f"🛒 <b>{title}</b>\n💰 Total: <b>Rp{amount:,}</b>\n🏦 {provider_used.upper()}\n🧾 Invoice: <code>{result['invoice_id']}</code>\n\nSetelah membayar, tekan Cek Pembayaran."
        if lang == "id" else
        f"🛒 <b>{title}</b>\n💰 Total: <b>Rp{amount:,}</b>\n🏦 {provider_used.upper()}\n🧾 Invoice: <code>{result['invoice_id']}</code>\n\nAfter payment, tap Check Payment."
    ).replace(",", ".")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Cek Pembayaran" if lang == "id" else "🔄 Check Payment", callback_data=f"paycheck:{result['invoice_id']}")],
        [InlineKeyboardButton(text="❌ Batal" if lang == "id" else "❌ Cancel", callback_data=f"paycancel:{result['invoice_id']}")],
    ])
    await c.answer()
    if qr:
        await c.message.answer_photo(BufferedInputFile(qr, filename="vip-group.png"), caption=paytext, parse_mode="HTML", reply_markup=kb)
    else:
        await c.message.answer(paytext, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data == "vg:home")
async def vipg_home(c):
    await show_vip_group_menu(c)


@router.callback_query(F.data == "vg:list")
async def vipg_list(c):
    await _vipg_list(c)


@router.message(F.chat.type == "private", F.text.in_({"📚 Lihat Daftar VIP", "📚 View VIP List", "Lihat Daftar VIP", "View VIP List"}))
async def vipg_list_message(m: Message):
    lang = await _lang(m.from_user.id)
    rows = await (await get_pool()).fetch("SELECT code,name,price FROM vip_group_packages WHERE active ORDER BY price,name")
    buttons = [[InlineKeyboardButton(
        text=f"{r['name']} {int(r['price'])//1000}k" if lang == "id" else f"{r['name']} Rp{int(r['price']):,}".replace(",", "."),
        callback_data=f"vg:detail:{r['code']}"
    )] for r in rows]
    buttons += [
        [InlineKeyboardButton(text="🛍️ Ambil sebagian" if lang == "id" else "🛍️ Select some", callback_data="vg:some")],
        [InlineKeyboardButton(text="🛒 Borong semuanya" if lang == "id" else "🛒 Get everything", callback_data="vg:all")],
        [_vipg_back(lang)],
    ]
    text = ("📚 <b>Daftar VIP Bot</b>\n\nKeterangan: Daftar paket eksklusif. Klik paket untuk detail lengkap dan penawaran spesial."
            if lang == "id" else
            "📚 <b>VIP Group List</b>\n\nExclusive packages. Select a package to view its details and special offer.")
    await m.answer(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data.startswith("vg:detail:"))
async def vipg_detail(c):
    lang = await _lang(c.from_user.id)
    code = c.data.split(":", 2)[2]
    row = await (await get_pool()).fetchrow("SELECT * FROM vip_group_packages WHERE code=$1 AND active", code)
    if not row:
        return await c.answer("Paket tidak tersedia." if lang == "id" else "Package unavailable.", show_alert=True)
    price = f"Rp{int(row['price']):,}".replace(",", ".")
    name = str(row["name"])
    desc = str(row["description"] or "")
    text = (
        f"✨ <b>Detail Paket VVIP</b>\n\n📦 <b>Nama Paket:</b> {html.escape(name)}\n📝 <b>Deskripsi:</b> {html.escape(desc)}\n💰 <b>Harga Normal:</b> <b>{price}</b>\n\nSilakan klik tombol Bayar di bawah untuk melanjutkan!"
        if lang == "id" else
        f"✨ <b>VVIP Package Details</b>\n\n📦 <b>Package:</b> {html.escape(name)}\n📝 <b>Description:</b> {html.escape(desc)}\n💰 <b>Regular price:</b> <b>{price}</b>\n\nTap Pay Now below to continue."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Bayar sekarang" if lang == "id" else "💳 Pay now", callback_data=f"vg:pay:{code}")],
        [InlineKeyboardButton(text="🔙 Kembali ke list VIP" if lang == "id" else "🔙 Back to VIP list", callback_data="vg:list")],
    ])
    await c.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await c.answer()


@router.callback_query(F.data.startswith("vg:pay:"))
async def vipg_pay_one(c):
    code = c.data.split(":", 2)[2]
    await _vipg_pay(c, [code])


@router.callback_query(F.data.startswith("vg:some"))
async def vipg_some(c):
    lang = await _lang(c.from_user.id)
    selected = c.data.split(":", 2)[2].split(",") if c.data.count(":") >= 2 and c.data.split(":", 2)[2] else []
    selected = [x for x in selected if x]
    rows = await (await get_pool()).fetch("SELECT code,name,price FROM vip_group_packages WHERE active ORDER BY price,name")
    buttons, total = [], 0
    for r in rows:
        code = str(r["code"])
        is_selected = code in selected
        if is_selected:
            total += int(r["price"])
        next_codes = [x for x in selected if x != code]
        if not is_selected:
            next_codes.append(code)
        callback = "vg:some:" + ",".join(next_codes)
        buttons.append([InlineKeyboardButton(
            text=f"{'✅' if is_selected else '⬜'} {r['name']} • Rp{int(r['price']):,}".replace(",", "."),
            callback_data=callback[:64]
        )])
    buttons.append([InlineKeyboardButton(
        text=f"💰 Total: Rp{total:,} ({len(selected)} paket)".replace(",", "."),
        callback_data=("vg:paymany:" + ",".join(selected)) if selected else "vg:some"
    )])
    buttons.append([InlineKeyboardButton(text="🔙 Kembali ke daftar VIP" if lang == "id" else "🔙 Back to VIP list", callback_data="vg:list")])
    text = (
        "🛍️ <b>Pilih Paket VIP</b>\n\nPaket • Harga • Status\nPilih paket untuk mencentang atau membatalkan pilihan."
        if lang == "id" else
        "🛍️ <b>Select VIP Packages</b>\n\nPackage • Price • Status\nTap packages to select or unselect them."
    )
    await c.message.edit_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await c.answer()


@router.callback_query(F.data.startswith("vg:paymany:"))
async def vipg_pay_many(c):
    codes = c.data.split(":", 2)[2].split(",")
    await _vipg_pay(c, codes)


@router.callback_query(F.data == "vg:all")
async def vipg_all(c):
    lang = await _lang(c.from_user.id)
    rows = await (await get_pool()).fetch("SELECT code,name,price FROM vip_group_packages WHERE active ORDER BY price,name")
    if not rows:
        return await c.answer("Belum ada paket aktif." if lang == "id" else "No active packages.", show_alert=True)
    total = sum(int(r["price"]) for r in rows)
    lines = ["🛒 <b>Ringkasan ambil semua VIP</b>" if lang == "id" else "🛒 <b>Get All VIP Summary</b>", ""]
    for r in rows:
        lines.append(f"• {html.escape(str(r['name']))} — Rp{int(r['price']):,}".replace(",", "."))
    lines += ["", f"💰 <b>Total: Rp{total:,} ({len(rows)} paket)</b>".replace(",", ".") if lang == "id" else f"💰 <b>Total: Rp{total:,} ({len(rows)} packages)</b>".replace(",", ".")]
    codes = ",".join(str(r["code"]) for r in rows)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Lakukan pembayaran Ambil Semua" if lang == "id" else "💳 Pay for All", callback_data=f"vg:paymany:{codes}")],
        [InlineKeyboardButton(text="🔙 Kembali ke daftar VIP" if lang == "id" else "🔙 Back to VIP list", callback_data="vg:list")],
    ])
    await c.message.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)
    await c.answer()


@router.callback_query(F.data == "vipabout")
async def vip_about(c):
    lang = await _lang(c.from_user.id)
    text = (
        "🌟 <b>Tentang VIP Ini</b>\n\nSelamat datang! Saya adalah asisten otomatis yang dirancang untuk memberikan Anda kemudahan dalam mengakses grup VIP.\n\n"
        "🤖 <b>Fungsi Utama Saya</b>\n"
        "• Pembayaran — otomatis dan aman via QRIS\n"
        "• Akses Instan — setelah transaksi berhasil\n"
        "• Konfirmasi — tanpa menunggu konfirmasi manual\n\n"
        "🚀 <b>Alur Penggunaan</b>\n"
        "1. Pilih paket dari daftar VIP yang tersedia\n"
        "2. Scan QRIS yang diberikan untuk membayar\n"
        "3. Link undangan terkirim otomatis setelah pembayaran terkonfirmasi."
        if lang == "id" else
        "🌟 <b>About VIP</b>\n\nWelcome! I am an automated assistant designed to make accessing VIP groups easy.\n\n"
        "🤖 <b>Key Features</b>\n"
        "• Payment — automatic and secure via QRIS\n"
        "• Instant access — after a successful transaction\n"
        "• Confirmation — no manual confirmation wait\n\n"
        "🚀 <b>How it works</b>\n"
        "1. Choose a package from the VIP list\n"
        "2. Scan the provided QRIS to pay\n"
        "3. The invite link is sent automatically after payment is confirmed."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[[_vipg_back(lang)]])
    await c.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await c.answer()


@router.callback_query(F.data == "vipdonate")
async def vip_donate(c):
    lang = await _lang(c.from_user.id)
    text = (
        "❤️‍🔥 <b>Dukung Kami dengan Telegram Stars</b>\n\n"
        "25 ⭐ — Paling ringan\n50 ⭐ — Dukungan dasar\n75 ⭐ — Dukungan sedang\n100 ⭐ — Dukungan maksimal\n\n"
        "Setiap Star yang Anda berikan memberi kami semangat untuk terus berinovasi."
        if lang == "id" else
        "❤️‍🔥 <b>Support Us with Telegram Stars</b>\n\n"
        "25 ⭐ — Small support\n50 ⭐ — Basic support\n75 ⭐ — Medium support\n100 ⭐ — Maximum support\n\n"
        "Every Star you give motivates us to keep innovating."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="25 ⭐️", callback_data="vg:stars:25"), InlineKeyboardButton(text="50 ⭐️", callback_data="vg:stars:50")],
        [InlineKeyboardButton(text="75 🌟", callback_data="vg:stars:75"), InlineKeyboardButton(text="100 💫", callback_data="vg:stars:100")],
        [_vipg_back(lang)],
    ])
    await c.message.edit_text(text, parse_mode="HTML", reply_markup=kb)
    await c.answer()


@router.callback_query(F.data.startswith("vg:stars:"))
async def vipg_stars(c):
    amount = int(c.data.rsplit(":", 1)[1])
    lang = await _lang(c.from_user.id)
    await c.answer()
    await c.message.answer_invoice(
        title=f"Support bot with {amount} Telegram Stars"[:32],
        description=("Dukungan untuk pengembangan bot" if lang == "id" else "Support the development of this bot"),
        payload=f"vip_donation_{amount}_{c.from_user.id}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=f"Donation {amount} Stars", amount=amount)],
    )


@router.pre_checkout_query()
async def vipg_stars_precheckout(q: PreCheckoutQuery):
    if str(q.invoice_payload or "").startswith("vip_donation_") and q.currency == "XTR":
        await q.answer(ok=True)
    else:
        await q.answer(ok=False, error_message="Invalid donation payment.")


@router.message(F.successful_payment)
async def vipg_stars_success(m: Message):
    payment = m.successful_payment
    if not payment or not str(payment.invoice_payload or "").startswith("vip_donation_"):
        return
    lang = await _lang(m.from_user.id)
    await m.answer(
        "❤️ Terima kasih atas dukungan Telegram Stars Anda!" if lang == "id" else
        "❤️ Thank you for supporting us with Telegram Stars!"
    )

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
    parts = c.data.split(":")
    _, code, provider = parts[:3]
    discount_id = int(parts[3]) if len(parts) > 3 else None
    r = await (await get_pool()).fetchrow(
        "SELECT * FROM vip_packages WHERE code=$1 AND active", code
    )

    amount = int(r["price"])
    meta = {"vip_package_codes": [code]}
    if discount_id:
        p = await get_pool()
        d = await p.fetchrow("""SELECT dc.* FROM discount_codes dc
          JOIN user_discount_codes ud ON ud.discount_id=dc.id
          WHERE dc.id=$1 AND ud.user_id=$2 AND dc.active AND dc.starts_at<=NOW()
          AND dc.expires_at>NOW() AND dc.used_count<dc.max_uses""", discount_id, c.from_user.id)
        if not d or amount < 7000 or d["tier"] not in ("all", str(r["tier"] or "vip")) or (d["package_codes"] and code not in d["package_codes"]):
            return await c.answer("Code discount tidak valid untuk paket ini.", show_alert=True)
        off = amount * int(d["discount_value"]) // 100 if d["discount_type"] == "percent" else int(d["discount_value"])
        amount = max(1000, amount-off)
        meta.update({"discount_id": discount_id, "discount_code": d["code"], "original_amount": int(r["price"]), "discount_amount": int(r["price"])-amount})
    result, status = await create_purchase(c.from_user.id, "vip", r["duration_days"], amount, provider, c.from_user.full_name, metadata=meta)
    if result and discount_id:
        p = await get_pool()
        await p.execute("UPDATE discount_codes SET used_count=used_count+1 WHERE id=$1 AND used_count<max_uses", discount_id)
        await p.execute("DELETE FROM user_discount_codes WHERE user_id=$1 AND discount_id=$2", c.from_user.id, discount_id)
    used_provider = provider
    # Automatically try the other configured provider before giving up.
    if not result:
        alternate = "cashi" if provider == "bayargg" else "bayargg"
        if await enabled(alternate):
            result, status = await create_purchase(
                c.from_user.id, "vip", r["duration_days"], amount,
                alternate, c.from_user.full_name, metadata=meta,
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
                VALUES($1,$2,$3,'vip',$4,'pending') RETURNING id
            """, c.from_user.id, amount, code, int(r["duration_days"]))
            manual_id = int(manual["id"])
            await state.set_state(ManualProofState.proof)
            await state.update_data(kind="vip", quantity=int(r["duration_days"]), amount=amount, target_code=code, manual_id=manual_id)
            caption = (f"🧾 <b>QR MANUAL VIP</b>\n\n{_package_name(r, lang)}\n💰 Rp{amount:,}\n\n".replace(",", ".")
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
        f'💵 Rp{amount:,}\n'
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
        VALUES($1,$2,$3,'vip',$4,'pending') RETURNING id
    """, c.from_user.id, int(r["price"]), code, int(r["duration_days"]))
    manual_id = int(manual["id"])
    await state.set_state(ManualProofState.proof)
    await state.update_data(
        kind="vip",
        quantity=int(r["duration_days"]),
        amount=int(r["price"]),
        target_code=code,
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
    from handlers.misc import vipbot_menu
    await vipbot_menu(m)


@router.chat_member()
async def vip_group_member_joined(event: ChatMemberUpdated):
    """Detect a successful join from a tracked, one-person VIP Group invite."""
    new_status = str(getattr(event.new_chat_member, "status", ""))
    old_status = str(getattr(event.old_chat_member, "status", ""))
    joined_statuses = {"member", "administrator", "creator"}
    if new_status not in joined_statuses or old_status in joined_statuses:
        return
    invite_obj = getattr(event, "invite_link", None)
    invite_url = str(getattr(invite_obj, "invite_link", "") or "").strip()
    if not invite_url:
        return
    try:
        p = await get_pool()
        row = await p.fetchrow(
            """UPDATE vip_group_invites SET joined_at=NOW()
               WHERE invite_link=$1 AND chat_id=$2 AND joined_at IS NULL
               RETURNING telegram_user_id,link_chat_id,link_message_id,success_message,package_name""",
            invite_url, int(event.chat.id),
        )
        if not row:
            return
        from bot import bot
        try:
            await bot.delete_message(int(row["link_chat_id"]), int(row["link_message_id"]))
        except Exception:
            # The message may have been deleted by the user or Telegram may reject deletion.
            pass
        try:
            await bot.revoke_chat_invite_link(int(event.chat.id), invite_url)
        except Exception:
            pass
        member_name = str(getattr(event.new_chat_member.user, "full_name", "") or row["telegram_user_id"])
        notice = str(row["success_message"] or "✅ Berhasil masuk grup {group}! Terima kasih telah bergabung.")
        notice = notice.replace("{group}", str(row["package_name"] or "VIP Group")).replace("{user}", member_name)
        try:
            await bot.send_message(int(row["telegram_user_id"]), notice)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Failed to send VIP Group join confirmation to user %s", row["telegram_user_id"])
    except Exception:
        import logging
        logging.getLogger(__name__).exception("VIP Group join tracking failed")


DISCOUNT_GROUP_URL = "https://t.me/+ezE2-f-YtEo4NzU1"

@router.callback_query(F.data.startswith("vipdiscount:"))
async def vip_discount_list(c):
    package_code=c.data.split(":",1)[1]
    p=await get_pool()
    pkg=await p.fetchrow("SELECT code,price,tier FROM vip_packages WHERE code=$1 AND active",package_code)
    if not pkg: return await c.answer("Paket tidak ditemukan.",show_alert=True)
    if int(pkg["price"])<7000: return await c.answer("Code discount hanya berlaku untuk harga Rp7.000 ke atas.",show_alert=True)
    rows=await p.fetch("""SELECT dc.* FROM discount_codes dc JOIN user_discount_codes ud ON ud.discount_id=dc.id
      WHERE ud.user_id=$1 AND dc.active AND dc.starts_at<=NOW() AND dc.expires_at>NOW() AND dc.used_count<dc.max_uses
      AND dc.min_price<=$2 AND (dc.tier='all' OR dc.tier=$3)
      AND (cardinality(dc.package_codes)=0 OR $4=ANY(dc.package_codes)) ORDER BY dc.expires_at""",
      c.from_user.id,int(pkg["price"]),str(pkg["tier"] or "vip"),package_code)
    if not rows:
        kb=InlineKeyboardMarkup(inline_keyboard=[
          [InlineKeyboardButton(text="🎟 Ambil Code Discount",url=DISCOUNT_GROUP_URL)],
          [InlineKeyboardButton(text="🔙 Kembali",callback_data=f"vip:{package_code}")]])
        return await c.message.answer("Kamu belum memiliki code discount untuk paket ini. Ambil code di grup, lalu masukkan melalui My Code Discount.",reply_markup=kb)
    buttons=[]
    for d in rows:
        off=int(pkg["price"])*int(d["discount_value"])//100 if d["discount_type"]=="percent" else int(d["discount_value"])
        final=max(1000,int(pkg["price"])-off)
        buttons.append([InlineKeyboardButton(text=f"🎟 {d['code']} • Rp{final:,}".replace(",","."),callback_data=f"vipdiscapply:{package_code}:{d['id']}")])
    buttons.append([InlineKeyboardButton(text="🔙 Kembali",callback_data=f"vip:{package_code}")])
    await c.message.answer("Pilih code discount yang ingin digunakan:",reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await c.answer()

@router.callback_query(F.data.startswith("vipdiscapply:"))
async def vip_discount_apply(c):
    _,package_code,discount_id=c.data.split(":")
    pkg=await (await get_pool()).fetchrow("SELECT * FROM vip_packages WHERE code=$1 AND active",package_code)
    d=await (await get_pool()).fetchrow("SELECT dc.* FROM discount_codes dc JOIN user_discount_codes ud ON ud.discount_id=dc.id WHERE dc.id=$1 AND ud.user_id=$2 AND dc.active AND dc.expires_at>NOW() AND dc.used_count<dc.max_uses",int(discount_id),c.from_user.id)
    if not pkg or not d: return await c.answer("Code discount tidak tersedia.",show_alert=True)
    buttons=[]
    for provider,label in [("bayargg","⚡ BayarGG"),("cashi","💳 Cashi")]:
        if await enabled(provider): buttons.append([InlineKeyboardButton(text=label,callback_data=f"vip_provider:{package_code}:{provider}:{discount_id}")])
    if await enabled("manual"):
        buttons.append([InlineKeyboardButton(text="🧾 QR Manual",callback_data=f"vip_manual_discount:{package_code}:{discount_id}")])
    buttons.append([InlineKeyboardButton(text="🔙 Kembali",callback_data=f"vip:{package_code}")])
    await c.message.answer(f"🎟 Code: {d['code']}\nPilih metode pembayaran. Total diskon akan diterapkan ke invoice.",reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await c.answer()

from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
class DiscountClaimState(StatesGroup):
    code=State()

@router.message(F.text.regexp(r"(?i)^my code discount$"))
@router.message(F.text.regexp(r"(?i)^🎟 my code discount$"))
async def my_discount_codes(m):
    p = await get_pool()
    rows = await p.fetch("""SELECT dc.code,dc.discount_type,dc.discount_value,dc.expires_at,dc.used_count,dc.max_uses,
      CASE WHEN dc.expires_at<=NOW() THEN 'expired' WHEN dc.used_count>=dc.max_uses THEN 'full' ELSE 'active' END AS code_status
      FROM user_discount_codes ud JOIN discount_codes dc ON dc.id=ud.discount_id
      WHERE ud.user_id=$1 ORDER BY ud.claimed_at DESC LIMIT 50""", m.from_user.id)
    lines = ["🎟 <b>MY CODE DISCOUNT</b>", ""]
    if rows:
        for r in rows:
            status = {"expired": "⌛ Kadaluarsa", "full": "⛔ Kuota penggunaan penuh", "active": "✅ Aktif"}[r["code_status"]]
            value = f"{r['discount_value']}%" if r["discount_type"] == "percent" else f"Rp{int(r['discount_value']):,}".replace(",", ".")
            lines.append(f"• <code>{html.escape(r['code'])}</code> — {value} — {status} — pemakaian {r['used_count']}/{r['max_uses']}")
    else:
        lines.append("Kamu belum memiliki Code Discount yang berhasil di-redeem.")
    lines += ["", "📘 <b>Bantuan Code Discount</b>",
      "1. Tekan <b>Redeem Code</b> lalu kirim kode yang kamu dapatkan dari grup.",
      "2. Jika berhasil, kode akan masuk ke daftar My Code Discount.",
      "3. Saat membeli Code Media atau paket VIP/VVIP yang sesuai, pilih tombol Code Discount sebelum membayar.",
      "4. Diskon hanya berlaku untuk transaksi minimal Rp7.000 dan harus sesuai paket, masa berlaku, serta kuota.",
      "", "📣 Cara mendapatkan: buka grup Code Discount di bawah dan gunakan kode yang dibagikan admin."]
    kb = InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text="🎟 Redeem Code", callback_data="discount:claim")],
      [InlineKeyboardButton(text="📣 Dapatkan Code Discount", url=DISCOUNT_GROUP_URL)],
      [InlineKeyboardButton(text="🔄 Refresh", callback_data="discount:refresh")]])
    await m.answer("\n".join(lines), parse_mode="HTML", reply_markup=kb)

@router.callback_query(F.data == "discount:refresh")
async def discount_refresh(c):
    await c.message.delete()
    # Reuse the same display path without requiring the user to type the menu again.
    class _MessageProxy:
        from_user = c.from_user
        answer = c.message.answer
    proxy = _MessageProxy()
    await my_discount_codes(proxy)
    await c.answer("Daftar Code Discount diperbarui.")

@router.callback_query(F.data == "discount:claim")
async def discount_claim_start(c, state: FSMContext):
    await state.set_state(DiscountClaimState.code)
    await c.message.answer("🎟 <b>Redeem Code Discount</b>\nKirim kode yang kamu dapatkan dari grup.\n\nKetik /cancel untuk membatalkan.", parse_mode="HTML")
    await c.answer()

@router.message(DiscountClaimState.code)
async def discount_claim_save(m, state: FSMContext):
    raw = (m.text or "").strip()
    if raw.lower() == "/cancel":
        await state.clear()
        return await m.answer("Redeem dibatalkan. Buka My Code Discount untuk mencoba lagi.")
    code = raw.upper()
    p = await get_pool()
    async with p.acquire() as conn:
        async with conn.transaction():
            d = await conn.fetchrow("SELECT * FROM discount_codes WHERE code=$1 FOR UPDATE", code)
            if not d:
                archived = await conn.fetchrow("SELECT status FROM discount_code_archive WHERE code=$1", code)
                if archived and archived["status"] == "expired":
                    reason = "⌛ Kode ini sudah kedaluwarsa dan tidak bisa di-redeem lagi."
                elif archived and archived["status"] in ("full", "used"):
                    reason = "⛔ Kode ini sudah penuh atau seluruh kuotanya terpakai. Silakan ambil kode lain di grup."
                else:
                    reason = "❌ Kode tidak ditemukan. Periksa kembali penulisan kode atau minta kode yang benar di grup."
                await state.clear()
                return await m.answer(reason, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📣 Cari Kode Lain", url=DISCOUNT_GROUP_URL)], [InlineKeyboardButton(text="🎟 My Code Discount", callback_data="discount:refresh")]]))
            if not d["active"] or d["starts_at"] > __import__("datetime").datetime.now(d["starts_at"].tzinfo):
                await state.clear()
                return await m.answer("⛔ Kode belum aktif atau sudah dinonaktifkan admin.")
            if d["expires_at"] <= __import__("datetime").datetime.now(d["expires_at"].tzinfo):
                await conn.execute("INSERT INTO discount_code_archive(code,status) VALUES($1,'expired') ON CONFLICT(code) DO UPDATE SET status='expired',archived_at=NOW()", code)
                await state.clear()
                return await m.answer("⌛ Kode ini sudah kedaluwarsa. Silakan ambil kode yang masih aktif di grup.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📣 Ambil Kode Lain", url=DISCOUNT_GROUP_URL)]]))
            if int(d["used_count"]) >= int(d["max_uses"]):
                await conn.execute("INSERT INTO discount_code_archive(code,status) VALUES($1,'full') ON CONFLICT(code) DO UPDATE SET status='full',archived_at=NOW()", code)
                await state.clear()
                return await m.answer("⛔ Maaf, kuota penggunaan kode ini sudah penuh. Silakan ambil kode lain di grup.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📣 Ambil Kode Lain", url=DISCOUNT_GROUP_URL)]]))
            already = await conn.fetchval("SELECT 1 FROM user_discount_codes WHERE user_id=$1 AND discount_id=$2", m.from_user.id, d["id"])
            if already:
                await state.clear()
                return await m.answer("ℹ️ Kode ini sudah ada di My Code Discount kamu. Kamu tidak perlu redeem ulang.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎟 My Code Discount", callback_data="discount:refresh")]]))
            claimed = await conn.fetchval("SELECT COUNT(*) FROM user_discount_codes WHERE discount_id=$1", d["id"])
            if int(claimed or 0) >= int(d["max_uses"]):
                await state.clear()
                return await m.answer("⛔ Kode ini sudah full: semua slot redeem sudah diambil pengguna lain. Silakan ambil kode lain di grup.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📣 Ambil Kode Lain", url=DISCOUNT_GROUP_URL)]]))
            await conn.execute("INSERT INTO user_discount_codes(user_id,discount_id) VALUES($1,$2)", m.from_user.id, d["id"])
    await state.clear()
    await m.answer(f"✅ <b>Redeem berhasil!</b>\nCode Discount <code>{html.escape(code)}</code> sekarang tersimpan di My Code Discount kamu.\n\nGunakan saat checkout transaksi yang sesuai sebelum masa berlaku atau kuotanya habis.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎟 Buka My Code Discount", callback_data="discount:refresh")]]))


@router.callback_query(F.data.startswith("vip_manual_discount:"))
async def vip_manual_discount(c,state:FSMContext):
    from handlers.payments import ManualProofState
    _,code,discount_id=c.data.split(":")
    p=await get_pool()
    r=await p.fetchrow("SELECT * FROM vip_packages WHERE code=$1 AND active",code)
    d=await p.fetchrow("""SELECT dc.* FROM discount_codes dc JOIN user_discount_codes ud ON ud.discount_id=dc.id
      WHERE dc.id=$1 AND ud.user_id=$2 AND dc.active AND dc.starts_at<=NOW() AND dc.expires_at>NOW() AND dc.used_count<dc.max_uses""",int(discount_id),c.from_user.id)
    qr=await p.fetchval("SELECT value FROM settings WHERE key='manual_qr_file_id'")
    if not r or not d or not qr: return await c.answer("Paket, code discount, atau QR manual tidak tersedia.",show_alert=True)
    original=int(r["price"])
    if original<7000: return await c.answer("Diskon hanya berlaku untuk harga Rp7.000 ke atas.",show_alert=True)
    off=original*int(d["discount_value"])//100 if d["discount_type"]=="percent" else int(d["discount_value"])
    amount=max(1000,original-off)
    manual=await p.fetchrow("""INSERT INTO manual_payments(user_id,amount,target_code,target_type,quantity,status,note)
      VALUES($1,$2,$3,'vip',$4,'pending',$5) RETURNING id""",c.from_user.id,amount,code,int(r["duration_days"]),f"Discount {d['code']} (harga awal {original})")
    did=int(manual["id"])
    await p.execute("UPDATE discount_codes SET used_count=used_count+1 WHERE id=$1 AND used_count<max_uses",int(discount_id))
    await p.execute("DELETE FROM user_discount_codes WHERE user_id=$1 AND discount_id=$2", c.from_user.id, int(discount_id))
    await state.set_state(ManualProofState.proof)
    await state.update_data(kind="vip",quantity=int(r["duration_days"]),amount=amount,target_code=code,manual_id=did)
    cap=f"🧾 <b>QR MANUAL VIP</b>\n{html.escape(str(r['name']))}\nHarga awal: Rp{original:,}\nCode: <code>{html.escape(str(d['code']))}</code>\nDiskon: Rp{original-amount:,}\n<b>Total: Rp{amount:,}</b>\n\nKirim screenshot bukti pembayaran.".replace(",",".")
    msg=await c.message.answer_photo(qr,caption=cap+f"\nID: <code>{did}</code>",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Batal",callback_data=f"mancancel:{did}")]]))
    await p.execute("UPDATE manual_payments SET qr_message_id=$1 WHERE id=$2",msg.message_id,did)
    await c.answer()
