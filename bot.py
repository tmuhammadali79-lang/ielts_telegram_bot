"""
IELTS Speaking Bot — Asosiy fayl (Entry Point).

🤖 Bu bot 3 ta Killer Feature bilan ishlaydi:
  1. 🎙 Vocabulary & Idiom Booster — nutqni tahlil + ilg'or so'zlar
  2. 📹 Video-Message Examiner — AI avatar video feedback
  3. 🏆 Gamification & Leaderboard — liga tizimi va reyting

Ishga tushirish:
  1. .env fayl yarating (BOT_TOKEN, OPENAI_API_KEY, DATABASE_URL, DID_API_KEY)
  2. pip install -r requirements.txt
  3. PostgreSQL'da bazani yarating va schema.sql ni ishga tushiring
  4. python bot.py
"""
import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message

from config import config
from database.connection import db

# Handler'larni import qilish
from handlers.speaking import router as speaking_router
from handlers.video_examiner import router as video_router
from handlers.leaderboard import router as leaderboard_router
from handlers.subscription import router as subscription_router

# Logging sozlash (Windows cp1251 encoding muammosini hal qilish)
handler = logging.StreamHandler(
    open(sys.stdout.fileno(), mode="w", encoding="utf-8", errors="replace", closefd=False)
)
handler.setFormatter(
    logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)-20s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)
logging.basicConfig(level=logging.INFO, handlers=[handler])
logger = logging.getLogger(__name__)

# Bot va Dispatcher
bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


# ==========================
# Start va Help komandalar
# ==========================


@dp.message(Command("start"))
async def cmd_start(message: Message):
    """
    /start — Botni ishga tushirish va foydalanuvchini ro'yxatga olish.
    """
    user = await db.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    await message.answer(
        f"👋 <b>Assalomu alaykum, {message.from_user.first_name}!</b>\n\n"
        "🎓 <b>IELTS Speaking AI Bot</b> ga xush kelibsiz!\n"
        f"{'━' * 30}\n\n"
        "🤖 Men sizning shaxsiy IELTS Speaking\n"
        "imtihon tayyorgarlik yordamchingizman.\n\n"
        "✨ <b>Mening imkoniyatlarim:</b>\n\n"
        "  🎙 <b>Vocabulary Booster</b>\n"
        "     Voice message yuboring — nutqingizni\n"
        "     tahlil qilib, ilg'or so'zlar tavsiya etaman\n\n"
        "  📹 <b>Video Examiner</b>\n"
        "     AI examiner video-feedback yuboradi\n"
        "     /video_feedback — buyrug'ini yuboring\n\n"
        "  🏆 <b>Liga & Reyting</b>\n"
        "     Ball to'plang, ligangizni oshiring!\n"
        "     /leaderboard — top-10 reyting\n\n"
        f"{'━' * 30}\n\n"
        "🎤 <b>Boshlash uchun:</b>\n"
        "Ingliz tilida voice message yuboring!\n\n"
        "📋 Barcha buyruqlar: /help",
    )


@dp.message(Command("help"))
async def cmd_help(message: Message):
    """
    /help — Barcha mavjud buyruqlar ro'yxati.
    """
    await message.answer(
        "📋 <b>Buyruqlar Ro'yxati</b>\n"
        f"{'━' * 28}\n\n"
        "🎤 <b>Speaking Test:</b>\n"
        "  Voice message yuboring — avtomatik tahlil\n\n"
        "📹 <b>Video Feedback:</b>\n"
        "  /video_feedback — AI examiner video\n\n"
        "📊 <b>Statistika:</b>\n"
        "  /mystats — Shaxsiy statistikangiz\n"
        "  /leaderboard — Haftalik Top-10\n"
        "  /leagues — Liga tizimi haqida\n\n"
        "ℹ️ <b>Boshqa:</b>\n"
        "  /start — Botni qayta ishga tushirish\n"
        "  /help — Shu yordam xabari\n\n"
        f"{'━' * 28}\n"
        "💡 <i>Har kuni mashq qiling — natija aniq!</i>",
    )


# ==========================
# Startup & Shutdown
# ==========================


async def on_startup():
    """Bot ishga tushganda chaqiriladi."""
    logger.info("[START] Bot ishga tushmoqda...")

    # PostgreSQL ulanish
    await db.init()
    logger.info("[OK] PostgreSQL ulandi")

    # Bot ma'lumotlari
    bot_info = await bot.get_me()
    logger.info(f"[BOT] @{bot_info.username} ({bot_info.full_name})")


async def on_shutdown():
    """Bot to'xtashda chaqiriladi."""
    logger.info("[STOP] Bot to'xtamoqda...")
    await db.close()
    await bot.session.close()
    logger.info("[DONE] Bot to'xtadi")


async def main():
    """Asosiy funksiya — botni ishga tushirish."""
    # Router'larni ro'yxatga olish
    dp.include_router(subscription_router)  # Subscription — birinchi (photo handler)
    dp.include_router(speaking_router)
    dp.include_router(video_router)
    dp.include_router(leaderboard_router)

    # Startup/Shutdown hooks
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Botni polling rejimida ishga tushirish
    logger.info("[POLL] Polling boshlandi...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
