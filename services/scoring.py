"""
Scoring & Gamification Service.

Band score → XP konvertatsiya va League tizimi.

🏆 Liga tizimi:
  🥉 Bronze   — 0 XP
  🥈 Silver   — 500 XP
  🥇 Gold     — 1,500 XP
  💎 Platinum — 3,500 XP
  👑 Diamond  — 7,000 XP

📊 XP hisoblash formulasi:
  XP = band_score * 20 + bonus
  Bonus: Band 7.0+ = +50, Band 8.0+ = +100
"""
import logging
from config import config

logger = logging.getLogger(__name__)

# Liga emoji mapping
LEAGUE_EMOJI = {
    "bronze": "🥉",
    "silver": "🥈",
    "gold": "🥇",
    "platinum": "💎",
    "diamond": "👑",
}

LEAGUE_NAMES = {
    "bronze": "Bronze Liga",
    "silver": "Silver Liga",
    "gold": "Gold Liga",
    "platinum": "Platinum Liga",
    "diamond": "Diamond Liga",
}

# Top-10 o'rin uchun medal emoji
RANK_EMOJI = {
    1: "🥇",
    2: "🥈",
    3: "🥉",
}


def calculate_xp(band_score: float) -> int:
    """
    IELTS Band score'dan XP hisoblash.

    Formula:
        base_xp = band_score * 20
        bonus = 50 (agar band >= 7.0) yoki 100 (agar band >= 8.0)

    Misollar:
        Band 5.0 → 100 XP
        Band 6.5 → 130 XP
        Band 7.0 → 190 XP (140 + 50 bonus)
        Band 8.5 → 270 XP (170 + 100 bonus)
    """
    base_xp = int(band_score * 20)

    # Yuqori ball uchun bonus
    bonus = 0
    if band_score >= 8.0:
        bonus = 100
    elif band_score >= 7.0:
        bonus = 50
    elif band_score >= 6.0:
        bonus = 20

    total_xp = base_xp + bonus
    logger.info(f"📊 XP hisoblandi: Band {band_score} → {total_xp} XP (bonus: {bonus})")
    return total_xp


def determine_league(total_xp: int) -> str:
    """
    Umumiy XP asosida foydalanuvchi ligasini aniqlash.

    Args:
        total_xp: Foydalanuvchining jami XP miqdori

    Returns:
        str: Liga nomi (bronze, silver, gold, platinum, diamond)
    """
    thresholds = config.LEAGUE_THRESHOLDS

    if total_xp >= thresholds["diamond"]:
        return "diamond"
    elif total_xp >= thresholds["platinum"]:
        return "platinum"
    elif total_xp >= thresholds["gold"]:
        return "gold"
    elif total_xp >= thresholds["silver"]:
        return "silver"
    else:
        return "bronze"


def get_league_progress(total_xp: int, current_league: str) -> dict:
    """
    Keyingi ligagacha qancha XP qolganini hisoblash.

    Returns:
        dict: {
            "current_league": "silver",
            "next_league": "gold",
            "current_xp": 800,
            "next_threshold": 1500,
            "remaining_xp": 700,
            "progress_percent": 53.3,
            "progress_bar": "████████░░░░░░░"
        }
    """
    thresholds = config.LEAGUE_THRESHOLDS
    leagues = ["bronze", "silver", "gold", "platinum", "diamond"]

    current_idx = leagues.index(current_league)

    if current_idx >= len(leagues) - 1:
        # Diamond — eng yuqori liga
        return {
            "current_league": "diamond",
            "next_league": None,
            "current_xp": total_xp,
            "next_threshold": None,
            "remaining_xp": 0,
            "progress_percent": 100.0,
            "progress_bar": "█" * 15,
        }

    next_league = leagues[current_idx + 1]
    current_threshold = thresholds[current_league]
    next_threshold = thresholds[next_league]

    progress_in_range = total_xp - current_threshold
    range_size = next_threshold - current_threshold
    progress_percent = min((progress_in_range / max(range_size, 1)) * 100, 100)

    # Progress bar yaratish (15 blok)
    filled = int(progress_percent / 100 * 15)
    bar = "█" * filled + "░" * (15 - filled)

    return {
        "current_league": current_league,
        "next_league": next_league,
        "current_xp": total_xp,
        "next_threshold": next_threshold,
        "remaining_xp": max(0, next_threshold - total_xp),
        "progress_percent": round(progress_percent, 1),
        "progress_bar": bar,
    }


def format_leaderboard(top_users: list[dict], user_rank: int = None) -> str:
    """
    Top-10 leaderboard'ni chiroyli Telegram xabar formatiga aylantirish.

    Args:
        top_users: DB'dan olingan top-10 foydalanuvchilar ro'yxati
        user_rank: Joriy foydalanuvchining o'rni (ixtiyoriy)

    Returns:
        str: HTML formatlangan xabar
    """
    if not top_users:
        return (
            "📊 <b>Haftalik Reyting</b>\n\n"
            "😴 Hali hech kim ball to'plamagan.\n"
            "Birinchi bo'ling — voice message yuboring! 🎤"
        )

    # Sarlavha
    msg = (
        "🏆 <b>HAFTALIK TOP-10 REYTING</b> 🏆\n"
        f"{'━' * 30}\n"
        "🇺🇿 <i>O'zbekistonning eng yaxshi IELTS spikerlar</i>\n\n"
    )

    # Top-10 ro'yxat
    for i, user in enumerate(top_users, 1):
        # O'rin emoji
        rank_icon = RANK_EMOJI.get(i, f"{i}.")

        # Ism
        name = user.get("full_name") or user.get("username") or "Anonymous"
        if len(name) > 16:
            name = name[:15] + "…"

        # Liga emoji
        league = user.get("current_league", "bronze")
        league_icon = LEAGUE_EMOJI.get(league, "🥉")

        # XP va Band (Decimal -> float konvertatsiya)
        xp = user.get("weekly_xp", 0)
        band = float(user.get("best_band_score", 0))

        # XP bar (10 blok, max XP = birinchi o'rindagi)
        max_xp = top_users[0].get("weekly_xp", 1)
        bar_filled = int((xp / max(max_xp, 1)) * 10)
        xp_bar = "▓" * bar_filled + "░" * (10 - bar_filled)

        msg += (
            f"  {rank_icon} {league_icon} <b>{name}</b>\n"
            f"      ⚡ {xp} XP  |  🎯 Band {band}\n"
            f"      [{xp_bar}]\n\n"
        )

    msg += f"{'━' * 30}\n"

    # Foydalanuvchining o'rni
    if user_rank:
        msg += f"📍 <b>Sizning o'rningiz:</b> #{user_rank}\n\n"

    # Sponsor chegirmalari
    msg += (
        "🎁 <b>Haftalik Sovg'alar:</b>\n"
        "  🥇 1-o'rin: IELTS kurs -50% chegirma\n"
        "  🥈 2-o'rin: Speaking club bepul 1 hafta\n"
        "  🥉 3-o'rin: Kitob sovg'asi 📚\n\n"
        "💪 <i>Har kuni mashq qiling va top-ga chiqing!</i>"
    )

    return msg
