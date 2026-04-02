"""
Leaderboard Handler — Haftalik reyting va liga tizimi.

🏆 Killer Feature #3: Gamification & League Leaderboard

Komandalar:
  /leaderboard — Haftalik Top-10 reyting ko'rsatish
  /mystats    — Foydalanuvchining shaxsiy statistikasini ko'rsatish
  /leagues    — Liga tizimi haqida ma'lumot
"""
import logging

from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.enums import ParseMode

from database.connection import db
from services.scoring import (
    format_leaderboard,
    get_league_progress,
    LEAGUE_EMOJI,
    LEAGUE_NAMES,
)

logger = logging.getLogger(__name__)

router = Router(name="leaderboard")


@router.message(Command("leaderboard"))
async def handle_leaderboard(message: Message):
    """
    /leaderboard — Haftalik Top-10 reyting.

    O'zbekistonning eng yaxshi IELTS spikerlarini ko'rsatadi.
    Har bir foydalanuvchining XP, Band score va ligasini ko'rsatadi.
    Pastki qismida sponsor chegirmalari ko'rinadi.
    """
    try:
        # Top-10 foydalanuvchilarni olish
        top_users = await db.get_weekly_top10()

        # Joriy foydalanuvchining o'rnini olish
        user_rank = await db.get_user_rank(message.from_user.id)

        # Chiroyli formatlanigan xabar
        leaderboard_text = format_leaderboard(top_users, user_rank)

        await message.answer(
            leaderboard_text,
            parse_mode=ParseMode.HTML,
        )

        logger.info(
            f"📊 Leaderboard ko'rsatildi: {message.from_user.id}, "
            f"o'rni: {user_rank}, {len(top_users)} ta top user"
        )

    except Exception as e:
        logger.error(f"❌ Leaderboard xatosi: {e}", exc_info=True)
        await message.answer(
            "❌ <b>Reytingni yuklashda xatolik.</b>\n"
            "Iltimos, keyinroq qaytadan urinib ko'ring.",
            parse_mode=ParseMode.HTML,
        )


@router.message(Command("mystats"))
async def handle_my_stats(message: Message):
    """
    /mystats — Shaxsiy statistika va liga progress.

    Foydalanuvchining:
    - Jami XP va liga holati
    - Keyingi ligagacha progress bar
    - Eng yaxshi va o'rtacha band score
    - Jami sessiyalar soni
    """
    try:
        user = await db.get_or_create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            full_name=message.from_user.full_name,
        )

        # Liga progress ma'lumotlari
        progress = get_league_progress(user["total_xp"], user["current_league"])

        # Foydalanuvchining haftalik o'rni
        rank = await db.get_user_rank(message.from_user.id)
        rank_text = f"#{rank}" if rank else "Reyting yo'q"

        league = user["current_league"]
        league_icon = LEAGUE_EMOJI.get(league, "🥉")
        league_name = LEAGUE_NAMES.get(league, "Bronze")

        msg = (
            f"📊 <b>Sizning Statistikangiz</b>\n"
            f"{'━' * 28}\n\n"
            f"👤 <b>{user.get('full_name', 'Anonymous')}</b>\n\n"
            # Liga
            f"🏆 <b>Liga:</b> {league_icon} {league_name}\n"
            f"⚡ <b>Jami XP:</b> {user['total_xp']}\n"
            f"📅 <b>Haftalik XP:</b> {user['weekly_xp']}\n"
            f"📍 <b>Reyting:</b> {rank_text}\n\n"
        )

        # Progress bar
        if progress["next_league"]:
            next_icon = LEAGUE_EMOJI.get(progress["next_league"], "")
            msg += (
                f"📈 <b>Keyingi liga:</b> {next_icon} {LEAGUE_NAMES[progress['next_league']]}\n"
                f"   [{progress['progress_bar']}] {progress['progress_percent']}%\n"
                f"   Qoldi: {progress['remaining_xp']} XP\n\n"
            )
        else:
            msg += f"   [{progress['progress_bar']}] 🏆 Eng yuqori liga!\n\n"

        # Statistika
        msg += (
            f"🎯 <b>Eng yaxshi Ball:</b> {user['best_band_score']}\n"
            f"📊 <b>O'rtacha Ball:</b> {user['avg_band_score']}\n"
            f"🎤 <b>Jami Sessiyalar:</b> {user['total_sessions']}\n\n"
            f"{'━' * 28}\n"
            f"📊 Reyting: /leaderboard\n"
            f"🎤 Yangi test: voice yuboring"
        )

        await message.answer(msg, parse_mode=ParseMode.HTML)

    except Exception as e:
        logger.error(f"❌ My stats xatosi: {e}", exc_info=True)
        await message.answer(
            "❌ <b>Statistikani yuklashda xatolik.</b>",
            parse_mode=ParseMode.HTML,
        )


@router.message(Command("leagues"))
async def handle_leagues_info(message: Message):
    """
    /leagues — Liga tizimi haqida batafsil ma'lumot.
    """
    msg = (
        "🏆 <b>LIGA TIZIMI</b>\n"
        f"{'━' * 28}\n\n"
        "Har bir speaking sessiyada XP qo'lga kiriting\n"
        "va yuqori ligaga ko'tariling!\n\n"
        "  🥉 <b>Bronze Liga</b>  — 0 XP\n"
        "     Yangi boshlovchilar\n\n"
        "  🥈 <b>Silver Liga</b>  — 500 XP\n"
        "     Band 5.0+ darajali spikerlar\n\n"
        "  🥇 <b>Gold Liga</b>    — 1,500 XP\n"
        "     Band 6.0+ darajali spikerlar\n\n"
        "  💎 <b>Platinum Liga</b> — 3,500 XP\n"
        "     Band 7.0+ professional spikerlar\n\n"
        "  👑 <b>Diamond Liga</b>  — 7,000 XP\n"
        "     IELTS ustolari — eng zo'rlar!\n\n"
        f"{'━' * 28}\n\n"
        "📊 <b>XP qanday hisoblanadi?</b>\n"
        "  Base: Band × 20\n"
        "  Bonus: Band 6.0+ = +20\n"
        "  Bonus: Band 7.0+ = +50\n"
        "  Bonus: Band 8.0+ = +100\n\n"
        "🎁 <b>Haftalik sovg'alar:</b>\n"
        "  🥇 1-o'rin — IELTS kurs -50%\n"
        "  🥈 2-o'rin — Speaking club 1 hafta\n"
        "  🥉 3-o'rin — Kitob sovg'asi 📚\n\n"
        "💪 Mashq qiling va ligangizni oshiring!"
    )

    await message.answer(msg, parse_mode=ParseMode.HTML)
