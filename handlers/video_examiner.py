"""
Video Examiner Handler — AI avatar video note yuborish.

📹 Killer Feature #2: Video-Message (Round Video) Examiner

Jarayon:
  1. Foydalanuvchi /video_feedback komandasini yuboradi
  2. Oxirgi sessiya tahlili olinadi
  3. GPT-4 bilan feedback skript yaratiladi
  4. D-ID API bilan talking head video yaratiladi
  5. Video Telegram video_note (dumaloq video) sifatida yuboriladi

📌 D-ID API tanlangan sabablari (HeyGen va Synclabs bilan taqqoslash):
  ┌──────────────┬────────────┬──────────┬──────────────┐
  │              │   D-ID     │  HeyGen  │  Synclabs    │
  ├──────────────┼────────────┼──────────┼──────────────┤
  │ Narx         │ $5.90/oy   │ $29/oy   │ $49/oy       │
  │ Tezlik       │ 30-60s     │ 2-5 min  │ 1-3 min      │
  │ API oddiylik │ ⭐⭐⭐⭐⭐    │ ⭐⭐⭐     │ ⭐⭐⭐⭐       │
  │ Sifat        │ ⭐⭐⭐⭐     │ ⭐⭐⭐⭐⭐  │ ⭐⭐⭐⭐       │
  │ Real-time    │ ✅          │ ❌       │ ✅           │
  └──────────────┴────────────┴──────────┴──────────────┘
  Xulosa: D-ID — narx/sifat/tezlik bo'yicha eng yaxshi tanlov.
"""
import os
import logging

from aiogram import Router
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command
from aiogram.enums import ParseMode

from database.connection import db
from services.vocabulary_booster import generate_feedback_script, analyze_transcript
from services.video_generator import create_talking_video, cleanup_video

logger = logging.getLogger(__name__)

router = Router(name="video_examiner")


@router.message(Command("video_feedback"))
async def handle_video_feedback(message: Message):
    """
    /video_feedback komandasi — AI examiner video note yuborish.

    1. Foydalanuvchining oxirgi sessiyasini bazadan olish
    2. Feedback skript yaratish (GPT-4)
    3. D-ID API bilan avatar video yaratish
    4. send_video_note bilan dumaloq video yuborish
    """
    user = await db.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    # Kutish xabari
    wait_msg = await message.answer(
        "📹 <b>Video Feedback Tayyorlanmoqda...</b>\n\n"
        "⏳ Bu 30-60 soniya olishi mumkin.\n"
        "🤖 AI Examiner siz uchun video tayyorlamoqda...\n\n"
        "🔄 GPT-4 → Feedback skript\n"
        "🔄 D-ID → Avatar video\n"
        "🔄 Telegram → Video Note",
        parse_mode=ParseMode.HTML,
    )

    video_path = None

    try:
        # 1. Oxirgi sessiyani bazadan olish
        async with db.pool.acquire() as conn:
            session = await conn.fetchrow(
                """
                SELECT transcript, band_score, fluency_score, lexical_score,
                       grammar_score, pronunciation_score, feedback_text,
                       model_answer
                FROM speaking_sessions
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT 1
                """,
                user["id"],
            )

        if not session:
            await wait_msg.edit_text(
                "⚠️ <b>Avval voice message yuboring!</b>\n\n"
                "Video feedback olish uchun kamida bitta\n"
                "speaking sessiyasi kerak. 🎤\n\n"
                "Ovozli xabar yuboring va keyin /video_feedback buyrug'ini yuboring.",
                parse_mode=ParseMode.HTML,
            )
            return

        session = dict(session)

        # 2. Tahlil natijasidan feedback skript yaratish
        analysis = {
            "band_score": session["band_score"],
            "fluency_score": session["fluency_score"],
            "lexical_score": session["lexical_score"],
            "grammar_score": session["grammar_score"],
            "pronunciation_score": session["pronunciation_score"],
            "feedback_text": session["feedback_text"],
            "key_improvements": [],
        }

        await wait_msg.edit_text(
            "📹 <b>Video Feedback Tayyorlanmoqda...</b>\n\n"
            "✅ Sessiya topildi\n"
            "🔄 GPT-4 → Feedback skript yozilmoqda...\n"
            "🔄 D-ID → Kutilmoqda\n"
            "🔄 Telegram → Kutilmoqda",
            parse_mode=ParseMode.HTML,
        )

        script = await generate_feedback_script(analysis)
        logger.info(f"📝 Feedback skript tayyor: {len(script)} belgi")

        # 3. D-ID API bilan video yaratish
        await wait_msg.edit_text(
            "📹 <b>Video Feedback Tayyorlanmoqda...</b>\n\n"
            "✅ Sessiya topildi\n"
            "✅ Feedback skript tayyor\n"
            "🔄 D-ID → Avatar video yaratilmoqda...\n"
            "🔄 Telegram → Kutilmoqda",
            parse_mode=ParseMode.HTML,
        )

        video_path = await create_talking_video(script)

        if not video_path:
            # Agar D-ID API ishlamasa, matnli feedback yuborish
            await wait_msg.edit_text(
                "⚠️ <b>Video yaratish vaqtincha ishlamayapti.</b>\n\n"
                f"🎤 <b>AI Examiner Feedback:</b>\n\n"
                f"<i>{script}</i>\n\n"
                "💡 Keyinroq /video_feedback buyrug'ini qaytadan yuboring.",
                parse_mode=ParseMode.HTML,
            )
            return

        # 4. Video Note sifatida yuborish
        await wait_msg.edit_text(
            "📹 <b>Video Feedback Tayyorlanmoqda...</b>\n\n"
            "✅ Sessiya topildi\n"
            "✅ Feedback skript tayyor\n"
            "✅ Avatar video tayyor\n"
            "🔄 Telegram → Yuborilmoqda...",
            parse_mode=ParseMode.HTML,
        )

        # Telegram video_note — dumaloq video
        video_file = FSInputFile(video_path)
        await message.answer_video_note(
            video_note=video_file,
            length=240,  # 240x240 piksel (dumaloq)
            duration=60,  # maksimal davomiylik
        )

        await wait_msg.edit_text(
            "✅ <b>Video Feedback yuborildi!</b>\n\n"
            f"🎯 Band Score: <code>{session['band_score']}</code>\n"
            "🤖 AI Examiner sizga feedback berdi.\n\n"
            "📊 Reyting: /leaderboard\n"
            "🎤 Yangi sessiya: voice message yuboring",
            parse_mode=ParseMode.HTML,
        )

        logger.info(f"📹 Video Note yuborildi: {message.from_user.id}")

    except Exception as e:
        logger.error(f"❌ Video feedback xatosi: {e}", exc_info=True)
        await wait_msg.edit_text(
            "❌ <b>Video yaratishda xatolik.</b>\n"
            "Iltimos, keyinroq qaytadan urinib ko'ring.\n\n"
            f"<code>{str(e)[:100]}</code>",
            parse_mode=ParseMode.HTML,
        )
    finally:
        if video_path:
            await cleanup_video(video_path)
