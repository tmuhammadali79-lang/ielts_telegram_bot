"""
Speaking Handler — Voice message qabul qilish va IELTS tahlil qilish.

🎙 Killer Feature #1: Vocabulary & Idiom Booster

Jarayon:
  1. Foydalanuvchi voice message yuboradi
  2. Bot audio faylni yuklab oladi
  3. Whisper API bilan matnga aylantiradi
  4. GPT-4 bilan tahlil qiladi (vocabulary_booster service)
  5. Natijani chiroyli format bilan yuboradi
  6. Ball va XP ni bazaga saqlaydi
"""
import os
import logging

from aiogram import Router, F
from aiogram.types import Message
from aiogram.enums import ParseMode

from database.connection import db
from services.vocabulary_booster import (
    transcribe_voice,
    analyze_transcript,
    format_analysis_message,
)
from services.scoring import calculate_xp, determine_league

logger = logging.getLogger(__name__)

router = Router(name="speaking")

# Vaqtinchalik audio fayllar papkasi
TEMP_AUDIO_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp_audio")
os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)


@router.message(F.voice)
async def handle_voice_message(message: Message):
    """
    Voice message handler — Foydalanuvchi ovozli xabar yuborganda ishga tushadi.

    Qadam 1: Foydalanuvchini bazada ro'yxatga olish
    Qadam 2: Audio faylni yuklab olish
    Qadam 3: Whisper bilan transcribe qilish
    Qadam 4: GPT-4 bilan tahlil qilish
    Qadam 5: Natijani yuborish + bazaga saqlash
    """
    # Foydalanuvchini ro'yxatga olish
    user = await db.get_or_create_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )

    # Kutish xabari
    processing_msg = await message.answer(
        "🎧 <b>Audio qabul qilindi!</b>\n\n"
        "⏳ Tahlil qilinmoqda...\n"
        "🔄 Whisper → Transcribe\n"
        "🔄 GPT-4 → Vocabulary Analysis\n\n"
        "<i>Bu 10-15 soniya olishi mumkin...</i>",
        parse_mode=ParseMode.HTML,
    )

    audio_path = None

    try:
        # 1. Audio faylni yuklab olish
        voice = message.voice
        file = await message.bot.get_file(voice.file_id)
        audio_path = os.path.join(TEMP_AUDIO_DIR, f"{message.from_user.id}_{message.message_id}.ogg")
        await message.bot.download_file(file.file_path, audio_path)

        logger.info(f"📥 Audio yuklab olindi: {audio_path} ({voice.duration}s)")

        # 2. Whisper bilan transcribe qilish
        transcript = await transcribe_voice(audio_path)

        if not transcript:
            await processing_msg.edit_text(
                "❌ <b>Audio'ni aniqlash mumkin emas.</b>\n\n"
                "Iltimos, ingliz tilida gapirib qaytadan yuboring. 🎤",
                parse_mode=ParseMode.HTML,
            )
            return

        # 3. GPT-4 bilan tahlil qilish
        analysis = await analyze_transcript(transcript)

        if "error" in analysis:
            await processing_msg.edit_text(
                f"❌ <b>Tahlil xatosi:</b> {analysis['error']}",
                parse_mode=ParseMode.HTML,
            )
            return

        # GPT javobidan band_score ni xavfsiz olish
        raw_band = analysis.get("band_score")
        if raw_band is None:
            await processing_msg.edit_text(
                "❌ <b>GPT-4 band score qaytarmadi.</b>\n"
                "Iltimos, qaytadan urinib ko'ring. 🎤",
                parse_mode=ParseMode.HTML,
            )
            return

        # 4. Natijani chiroyli format bilan yuborish
        result_message = format_analysis_message(analysis)
        await processing_msg.edit_text(
            result_message,
            parse_mode=ParseMode.HTML,
        )

        # 5. Ball hisoblash va bazaga saqlash
        try:
            band_score = float(raw_band)
            # IELTS 0.0 — 9.0 oralig'ida bo'lishi kerak
            band_score = max(0.0, min(9.0, band_score))
        except (TypeError, ValueError):
            logger.warning(f"⚠️ Noto'g'ri band_score: {raw_band}, default 0.0 ishlatiladi")
            band_score = 0.0

        xp_earned = calculate_xp(band_score)

        # Sub-score'larni xavfsiz float ga aylantirish
        def safe_float(val, default=None):
            if val is None:
                return default
            try:
                return float(val)
            except (TypeError, ValueError):
                return default

        # Sessiyani saqlash
        session_id = await db.save_session(
            user_id=user["id"],
            data={
                "transcript": transcript,
                "band_score": band_score,
                "fluency_score": safe_float(analysis.get("fluency_score")),
                "lexical_score": safe_float(analysis.get("lexical_score")),
                "grammar_score": safe_float(analysis.get("grammar_score")),
                "pronunciation_score": safe_float(analysis.get("pronunciation_score")),
                "feedback_text": analysis.get("feedback_text"),
                "model_answer": analysis.get("model_answer"),
                "xp_earned": xp_earned,
                "audio_file_id": voice.file_id,
                "duration_seconds": voice.duration,
            },
        )

        # Vocabulary tavsiyalarni saqlash
        upgrades = analysis.get("vocabulary_upgrades", [])
        if upgrades:
            vocab_data = [
                {
                    "original_word": u["original_word"],
                    "suggested_word": u["suggested_word"],
                    "context_sentence": u.get("context_sentence"),
                    "score_impact": u.get("score_impact"),
                    "category": u.get("category", "vocabulary"),
                }
                for u in upgrades
            ]
            await db.save_vocabulary_suggestions(session_id, user["id"], vocab_data)

        # Foydalanuvchi statistikasini yangilash
        await db.update_user_stats(
            telegram_id=message.from_user.id,
            band_score=band_score,
            xp=xp_earned,
        )

        # Liga tekshiruvi
        new_league = determine_league(user["total_xp"] + xp_earned)
        if new_league != user["current_league"]:
            await db.update_user_league(message.from_user.id, new_league)
            from services.scoring import LEAGUE_EMOJI, LEAGUE_NAMES

            await message.answer(
                f"🎉 <b>Tabriklaymiz!</b>\n\n"
                f"Siz {LEAGUE_EMOJI[new_league]} <b>{LEAGUE_NAMES[new_league]}</b> ga ko'tarildingiz!\n"
                f"⚡ Jami XP: {user['total_xp'] + xp_earned}",
                parse_mode=ParseMode.HTML,
            )

        # Ball haqida qo'shimcha xabar
        await db.save_score(user["id"], session_id, band_score, xp_earned, new_league)

        await message.answer(
            f"⚡ <b>+{xp_earned} XP qo'shildi!</b>\n"
            f"📈 Jami: {user['total_xp'] + xp_earned} XP\n\n"
            f"💡 Video feedback olish uchun: /video_feedback",
            parse_mode=ParseMode.HTML,
        )

    except Exception as e:
        logger.error(f"❌ Speaking handler xatosi: {e}", exc_info=True)
        await processing_msg.edit_text(
            "❌ <b>Kutilmagan xatolik yuz berdi.</b>\n"
            "Iltimos, qaytadan urinib ko'ring.",
            parse_mode=ParseMode.HTML,
        )
    finally:
        # Vaqtinchalik audio faylni o'chirish
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)
