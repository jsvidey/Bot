from aiogram import Router, F
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)

router = Router()


@router.callback_query(F.data == "channel")
async def channel_menu(call: CallbackQuery):

    await call.answer()

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Channel Update Code",
                    url="https://t.me/+8NajMZzycUE2NGE1"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Group Chat💬",
                    url="https://t.me/+WeFUnjG8ojQzOWQ5https://t.me/+WeFUnjG8ojQzOWQ5"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔔 Channel Notifikasi",
                    url="https://t.me/+iG0rS6GFY3Y2NTNk"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Menu Utama",
                    callback_data="home"
                )
            ]
        ]
    )

    text = (
        "📢 <b>LIST CHANNEL RESMI</b>\n\n"
        "Silakan bergabung ke channel resmi bot untuk mendapatkan update terbaru.\n\n"
        "📌 <b>Daftar Channel:</b>\n"
        "• Update Code\n"
        "• All Code\n"
        "• Transaksi\n"
        "• Notifikasi Pembaruan"
    )

    try:
        await call.message.edit_text(
            text,
            parse_mode="HTML",
            reply_markup=kb
        )
    except:
        await call.message.answer(
            text,
            parse_mode="HTML",
            reply_markup=kb
        )
