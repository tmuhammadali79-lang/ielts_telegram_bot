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


@router.message(Command("users"))
async def cmd_users(message: Message):
    """
    /users — Admin uchun barcha foydalanuvchilar ro'yxati.
    """
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Bu buyruq faqat admin uchun!")
        return

    users = await db.get_all_users()

    if not users:
        await message.answer("📭 Hali foydalanuvchilar yo'q.")
        return

    # Liga emoji
    league_emoji = {
        "bronze": "🥉",
        "silver": "🥈",
        "gold": "🥇",
        "platinum": "💎",
        "diamond": "👑",
    }

    msg = (
        f"👥 <b>Foydalanuvchilar ({len(users)} ta)</b>\n"
        f"{'━' * 30}\n\n"
    )

    for i, u in enumerate(users, 1):
        username = f"@{u['username']}" if u["username"] else "—"
        name = u["full_name"] or "Nomsiz"
        league = league_emoji.get(u["current_league"], "🥉")
        sub = "✅" if u["is_subscribed"] else f"🆓{u['free_uses_left']}"

        msg += (
            f"{i}. {league} <b>{name}</b>\n"
            f"   {username} | ID: <code>{u['telegram_id']}</code>\n"
            f"   XP: {u['total_xp']} | "
            f"Sessions: {u['total_sessions']} | {sub}\n"
        )

        # Telegram xabar limiti — 4096 belgi
        if len(msg) > 3800:
            msg += f"\n... va yana {len(users) - i} ta foydalanuvchi"
            break

    await message.answer(msg, parse_mode=ParseMode.HTML)


@router.message(Command("grant"))
async def cmd_grant(message: Message, bot: Bot):
    """
    /grant <telegram_id> — Foydalanuvchiga cheksiz dostup berish.
    """
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Bu buyruq faqat admin uchun!")
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer(
            "📋 <b>Foydalanish:</b>\n"
            "<code>/grant 123456789</code>\n\n"
            "Telegram ID ni /users buyrug'idan olishingiz mumkin.",
            parse_mode=ParseMode.HTML,
        )
        return

    target_id = int(args[1])
    await db.grant_unlimited(target_id)

    # Foydalanuvchiga xabar yuborish
    try:
        await bot.send_message(
            chat_id=target_id,
            text=(
                "🎉 <b>Tabriklaymiz!</b>\n\n"
                "👑 Sizga <b>cheksiz Premium dostup</b> berildi!\n"
                "✅ Endi cheksiz voice message yuborishingiz mumkin!\n\n"
                "🎤 Boshlang — voice message yuboring!"
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        pass  # User bot ni block qilgan bo'lishi mumkin

    await message.answer(
        f"✅ <b>Cheksiz dostup berildi!</b>\n\n"
        f"🆔 Telegram ID: <code>{target_id}</code>",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("revoke"))
async def cmd_revoke(message: Message, bot: Bot):
    """
    /revoke <telegram_id> — Foydalanuvchidan cheksiz dostupni olish.
    """
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("⛔ Bu buyruq faqat admin uchun!")
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer(
            "📋 <b>Foydalanish:</b>\n"
            "<code>/revoke 123456789</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    target_id = int(args[1])
    await db.revoke_unlimited(target_id)

    await message.answer(
        f"❌ <b>Dostup olib tashlandi!</b>\n\n"
        f"🆔 Telegram ID: <code>{target_id}</code>",
        parse_mode=ParseMode.HTML,
    )
