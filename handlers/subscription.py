"""
Subscription Handler — Obuna va to'lov boshqaruvi.

💳 Oylik obuna tizimi:
  - /subscribe — obuna ma'lumotlari
  - Screenshot yuborish — to'lov tasdiqlash
  - Admin ✅/❌ inline tugmalari
"""
import logging

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import config
from database.connection import db

logger = logging.getLogger(__name__)

router = Router(name="subscription")

# To'lov kutilayotgan foydalanuvchilar (state)
waiting_payment = set()


@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message):
    """
    /subscribe — Obuna ma'lumotlarini ko'rsatish.
    """
    user = await db.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    access = await db.check_user_access(message.from_user.id)

    if access["reason"] == "subscribed":
        await message.answer(
            "✅ <b>Sizda faol obuna mavjud!</b>\n\n"
            "🎤 Voice message yuboring — tahlil qilaman!",
            parse_mode=ParseMode.HTML,
        )
        return

    # Kutilayotgan to'lov bormi?
    has_pending = await db.has_pending_payment(user["id"])
    if has_pending:
        await message.answer(
            "⏳ <b>Sizning to'lovingiz tekshirilmoqda.</b>\n\n"
            "Admin tasdiqlaganidan keyin obuna faollashadi.\n"
            "Iltimos, biroz kuting...",
            parse_mode=ParseMode.HTML,
        )
        return

    waiting_payment.add(message.from_user.id)

    await message.answer(
        "💳 <b>Oylik Obuna — Premium</b>\n"
        f"{'━' * 28}\n\n"
        f"💰 <b>Narxi:</b> {config.SUBSCRIPTION_PRICE:,} so'm / oy\n\n"
        "📦 <b>Nimalar kiradi:</b>\n"
        "  ✅ Cheksiz voice message tahlili\n"
        "  ✅ GPT-4o bilan band score\n"
        "  ✅ Vocabulary upgrades\n"
        "  ✅ Model answer\n"
        "  ✅ Leaderboard ishtirok\n\n"
        f"{'━' * 28}\n\n"
        "💳 <b>To'lov uchun karta:</b>\n\n"
        f"  <code>{config.CARD_NUMBER}</code>\n"
        f"  👤 {config.CARD_HOLDER}\n\n"
        f"💵 Summa: <b>{config.SUBSCRIPTION_PRICE:,} so'm</b>\n\n"
        f"{'━' * 28}\n\n"
        "📸 To'lovdan keyin <b>screenshot</b>ni\n"
        "shu chatga rasm sifatida yuboring!\n\n"
        "⏳ Admin 5-30 daqiqa ichida tasdiqlaydi.",
        parse_mode=ParseMode.HTML,
    )


@router.message(F.photo)
async def handle_payment_screenshot(message: Message, bot: Bot):
    """
    Rasm (screenshot) handler — to'lov screenshotini qabul qilish.
    """
    user = await db.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    # Faqat to'lov kutilayotgan foydalanuvchilardan qabul qilish
    if message.from_user.id not in waiting_payment:
        # Tekshiramiz — bepul limiti tugaganmi?
        access = await db.check_user_access(message.from_user.id)
        if access["reason"] != "limit_reached":
            return  # Oddiy rasm — ignore qilish

    # Screenshot file_id
    photo = message.photo[-1]  # Eng katta o'lcham
    file_id = photo.file_id

    # Kutilayotgan to'lov allaqachon bormi?
    has_pending = await db.has_pending_payment(user["id"])
    if has_pending:
        await message.answer(
            "⏳ <b>Sizning to'lovingiz allaqachon tekshirilmoqda.</b>\n"
            "Iltimos, biroz kuting...",
            parse_mode=ParseMode.HTML,
        )
        return

    # DB ga saqlash
    sub_id = await db.create_payment_request(user["id"], file_id)

    # Waiting set dan olib tashlash
    waiting_payment.discard(message.from_user.id)

    await message.answer(
        "✅ <b>To'lov screenshot qabul qilindi!</b>\n\n"
        f"📋 So'rov raqami: <code>#{sub_id}</code>\n"
        "⏳ Admin tekshirmoqda...\n\n"
        "Tasdiqlangandan keyin obuna faollashadi! 🎉",
        parse_mode=ParseMode.HTML,
    )

    # Admin ga xabar yuborish
    if config.ADMIN_ID:
        # Inline tugmalar
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Tasdiqlash",
                        callback_data=f"approve_{sub_id}",
                    ),
                    InlineKeyboardButton(
                        text="❌ Rad etish",
                        callback_data=f"reject_{sub_id}",
                    ),
                ]
            ]
        )

        admin_text = (
            "💳 <b>Yangi to'lov so'rovi!</b>\n"
            f"{'━' * 28}\n\n"
            f"👤 <b>Foydalanuvchi:</b> {message.from_user.full_name}\n"
            f"🆔 ID: <code>{message.from_user.id}</code>\n"
            f"📛 Username: @{message.from_user.username or 'yo`q'}\n\n"
            f"📋 So'rov: <code>#{sub_id}</code>\n"
            f"💰 Summa: {config.SUBSCRIPTION_PRICE:,} so'm\n"
        )

        # Screenshot ni admin ga forward qilish
        await bot.send_photo(
            chat_id=config.ADMIN_ID,
            photo=file_id,
            caption=admin_text,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
        )

        logger.info(f"💳 To'lov so'rovi #{sub_id} admin ga yuborildi")


@router.callback_query(F.data.startswith("approve_"))
async def approve_payment(callback: CallbackQuery, bot: Bot):
    """Admin to'lovni tasdiqlash."""
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Faqat admin tasdiqlashi mumkin!", show_alert=True)
        return

    sub_id = int(callback.data.split("_")[1])

    sub = await db.approve_subscription(sub_id, callback.from_user.id)

    if sub:
        # Admin xabarini yangilash
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n✅ <b>TASDIQLANDI</b>",
            parse_mode=ParseMode.HTML,
        )

        # Foydalanuvchiga xabar
        user_telegram_id = await db.get_user_id_by_internal(sub["user_id"])
        if user_telegram_id:
            await bot.send_message(
                chat_id=user_telegram_id,
                text=(
                    "🎉 <b>Tabriklaymiz! Obuna faollashtirildi!</b>\n\n"
                    f"📅 Muddat: <b>{config.SUBSCRIPTION_DAYS} kun</b>\n"
                    "✅ Endi cheksiz voice message yuborishingiz mumkin!\n\n"
                    "🎤 Boshlang — voice message yuboring!"
                ),
                parse_mode=ParseMode.HTML,
            )

        await callback.answer("✅ Tasdiqlandi!")
        logger.info(f"✅ Obuna #{sub_id} tasdiqlandi admin tomonidan")
    else:
        await callback.answer("❌ So'rov topilmadi!", show_alert=True)


@router.callback_query(F.data.startswith("reject_"))
async def reject_payment(callback: CallbackQuery, bot: Bot):
    """Admin to'lovni rad etish."""
    if callback.from_user.id != config.ADMIN_ID:
        await callback.answer("⛔ Faqat admin rad etishi mumkin!", show_alert=True)
        return

    sub_id = int(callback.data.split("_")[1])

    sub = await db.reject_subscription(sub_id)

    if sub:
        # Admin xabarini yangilash
        await callback.message.edit_caption(
            caption=callback.message.caption + "\n\n❌ <b>RAD ETILDI</b>",
            parse_mode=ParseMode.HTML,
        )

        # Foydalanuvchiga xabar
        user_telegram_id = await db.get_user_id_by_internal(sub["user_id"])
        if user_telegram_id:
            await bot.send_message(
                chat_id=user_telegram_id,
                text=(
                    "❌ <b>To'lov rad etildi.</b>\n\n"
                    "To'lov tasdiqlanmadi. Mumkin sabablar:\n"
                    "  • Screenshot noaniq\n"
                    "  • Summa noto'g'ri\n\n"
                    "Qaytadan urinish uchun: /subscribe"
                ),
                parse_mode=ParseMode.HTML,
            )

        await callback.answer("❌ Rad etildi!")
        logger.info(f"❌ Obuna #{sub_id} rad etildi admin tomonidan")
    else:
        await callback.answer("❌ So'rov topilmadi!", show_alert=True)
