"""
Video Examiner Handler — AI avatar video note yuborish.

📹 Killer Feature #2: Video-Message (Round Video) Examiner
🚧 Hozircha Coming Soon — keyinroq D-ID API bilan ishga tushiriladi.
"""
import logging

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode

logger = logging.getLogger(__name__)

router = Router(name="video_examiner")


@router.message(Command("video_feedback"))
async def handle_video_feedback(message: Message):
    """
    /video_feedback komandasi — hozircha Coming Soon.
    """
    await message.answer(
        "🚧 <b>Coming Soon!</b>\n\n"
        "📹 <b>AI Video Examiner</b> hozirda ishlab chiqilmoqda.\n\n"
        "Bu funksiya tayyor bo'lganda:\n"
        "  🤖 AI Examiner sizga video feedback yuboradi\n"
        "  🎯 Band score va tavsiyalar video formatda\n"
        "  🗣 Real examiner kabi muloqot\n\n"
        "⏳ <i>Tez orada ishga tushadi!</i>\n\n"
        "🎤 Hozircha voice message yuboring — nutqingizni tahlil qilaman!",
        parse_mode=ParseMode.HTML,
    )
