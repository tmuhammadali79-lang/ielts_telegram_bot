"""
Vocabulary Booster Service — GPT-4 bilan nutq tahlili.

Bu modul foydalanuvchining speech transcript'ini GPT-4 ga yuboradi
va vocabulary tavsiyalari, ball, va model answer oladi.
"""
import json
import logging
from openai import AsyncOpenAI

from config import config
from prompts.system_prompts import VOCABULARY_BOOSTER_PROMPT, VIDEO_FEEDBACK_PROMPT

logger = logging.getLogger(__name__)

# OpenAI asinxron klient
client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)


async def analyze_transcript(transcript: str, question: str = None) -> dict:
    """
    Foydalanuvchi nutq transcript'ini GPT-4 bilan tahlil qilish.

    Args:
        transcript: Whisper'dan olingan matn
        question: IELTS speaking savolи (ixtiyoriy)

    Returns:
        dict: Band score, vocabulary upgrades, model answer va boshqalar
    """
    user_message = f"IELTS Speaking Question: {question}\n\n" if question else ""
    user_message += f"Student's Transcript:\n\"{transcript}\""

    try:
        response = await client.chat.completions.create(
            model=config.GPT_MODEL,
            messages=[
                {"role": "system", "content": VOCABULARY_BOOSTER_PROMPT},
                {"role": "user", "content": user_message},
            ],
            temperature=0.7,
            max_tokens=2000,
        )

        result_text = response.choices[0].message.content.strip()

        # JSON ni ajratib olish (ba'zan GPT ```json ... ``` bilan o'rab yuboradi)
        if result_text.startswith("```"):
            # ```json ... ``` formatini tozalash
            lines = result_text.split("\n")
            result_text = "\n".join(lines[1:-1])

        result = json.loads(result_text)

        logger.info(
            f"📊 Tahlil natijasi: Band {result.get('band_score')}, "
            f"{len(result.get('vocabulary_upgrades', []))} ta tavsiya"
        )
        return result

    except json.JSONDecodeError as e:
        logger.error(f"❌ JSON parse xatosi: {e}")
        return {"error": "GPT-4 javobini parse qilib bo'lmadi"}
    except Exception as e:
        logger.error(f"❌ GPT-4 API xatosi: {e}")
        return {"error": str(e)}


async def transcribe_voice(audio_path: str) -> tuple[str, str]:
    """
    Whisper API yordamida audio faylni matnga aylantirish.

    Args:
        audio_path: Audio fayl yo'li (.ogg, .mp3, .wav)

    Returns:
        tuple: (transcript, error) — muvaffaqiyatli bo'lsa error bo'sh string
    """
    try:
        with open(audio_path, "rb") as audio_file:
            response = await client.audio.transcriptions.create(
                model=config.WHISPER_MODEL,
                file=audio_file,
                language="en",
                response_format="text",
            )
        logger.info(f"🎤 Transcription tayyor: {len(response)} belgi")
        return response, ""
    except Exception as e:
        logger.error(f"❌ Whisper API xatosi: {e}", exc_info=True)
        return "", str(e)


async def generate_feedback_script(analysis: dict) -> str:
    """
    Tahlil natijasidan video feedback uchun natural speech skript yaratish.

    Args:
        analysis: analyze_transcript() natijasi

    Returns:
        str: 60-90 soniyalik feedback skripti
    """
    summary = (
        f"Band Score: {analysis.get('band_score')}\n"
        f"Fluency: {analysis.get('fluency_score')}, "
        f"Lexical: {analysis.get('lexical_score')}, "
        f"Grammar: {analysis.get('grammar_score')}, "
        f"Pronunciation: {analysis.get('pronunciation_score')}\n"
        f"Feedback: {analysis.get('feedback_text', '')}\n"
        f"Key Improvements: {', '.join(analysis.get('key_improvements', []))}"
    )

    try:
        response = await client.chat.completions.create(
            model=config.GPT_MODEL,
            messages=[
                {"role": "system", "content": VIDEO_FEEDBACK_PROMPT},
                {"role": "user", "content": summary},
            ],
            temperature=0.8,
            max_tokens=500,
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"❌ Feedback script xatosi: {e}")
        return f"Your band score is {analysis.get('band_score')}. Keep practicing!"


def format_analysis_message(analysis: dict) -> str:
    """
    GPT-4 tahlil natijasini chiroyli Telegram xabar formatiga aylantirish.

    Args:
        analysis: analyze_transcript() natijasi

    Returns:
        str: Formatlangan xabar matni (HTML parse_mode)
    """
    if "error" in analysis:
        return f"❌ Xatolik yuz berdi: {analysis['error']}"

    band = analysis.get("band_score", "N/A")
    potential = analysis.get("potential_score_with_upgrades", "N/A")

    # Asosiy natijalar
    msg = (
        f"🎯 <b>IELTS Speaking Natijasi</b>\n"
        f"{'━' * 28}\n\n"
        f"📊 <b>Umumiy Ball:</b> <code>{band}</code> / 9.0\n\n"
        f"   🗣 Fluency & Coherence:  <code>{analysis.get('fluency_score', 'N/A')}</code>\n"
        f"   📚 Lexical Resource:     <code>{analysis.get('lexical_score', 'N/A')}</code>\n"
        f"   ✏️ Grammar:              <code>{analysis.get('grammar_score', 'N/A')}</code>\n"
        f"   🔊 Pronunciation:        <code>{analysis.get('pronunciation_score', 'N/A')}</code>\n\n"
    )

    # Vocabulary tavsiyalar
    upgrades = analysis.get("vocabulary_upgrades", [])
    if upgrades:
        msg += f"💡 <b>Vocabulary Upgrades ({len(upgrades)} ta):</b>\n\n"
        for i, u in enumerate(upgrades[:6], 1):  # Max 6 ta ko'rsatish
            msg += (
                f"   {i}. ❌ <s>{u['original_word']}</s>  →  "
                f"✅ <b>{u['suggested_word']}</b>\n"
                f"      📝 <i>{u.get('context_sentence', '')}</i>\n"
                f"      📈 <code>{u.get('score_impact', '')}</code>\n\n"
            )

    # Potensial ball
    msg += (
        f"🚀 <b>Potensial ball:</b> <code>{potential}</code> / 9.0\n"
        f"{'━' * 28}\n\n"
    )

    # Asosiy maslahatlar
    improvements = analysis.get("key_improvements", [])
    if improvements:
        msg += "🔑 <b>Asosiy Maslahatlar:</b>\n"
        for tip in improvements[:3]:
            msg += f"   • {tip}\n"
        msg += "\n"

    # Model answer
    model = analysis.get("model_answer", "")
    if model:
        msg += (
            f"🏆 <b>Model Answer (Band 8.0+):</b>\n\n"
            f"<i>{model[:800]}</i>\n"
        )

    return msg
