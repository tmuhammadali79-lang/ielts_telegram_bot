"""
PostgreSQL ulanish pool boshqaruvchisi.

AsyncPG yordamida asinxron ulanishlarni boshqaradi.
Bot ishga tushganda `init_db()` chaqiriladi,
to'xtashda `close_db()` chaqiriladi.
"""
import logging
import asyncpg
from config import config

logger = logging.getLogger(__name__)


class Database:
    """AsyncPG connection pool wrapper."""

    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    async def init(self):
        """Ulanish pool'ini yaratish."""
        self.pool = await asyncpg.create_pool(
            dsn=config.DATABASE_URL,
            min_size=2,
            max_size=10,
        )
        print("[OK] PostgreSQL ulanish pool yaratildi")

    async def close(self):
        """Pool'ni yopish."""
        if self.pool:
            await self.pool.close()
            print("[CLOSED] PostgreSQL ulanish pool yopildi")

    # --- Foydalanuvchi metodlari ---

    def _ensure_pool(self):
        """Pool mavjudligini tekshirish."""
        if self.pool is None:
            raise RuntimeError(
                "Database pool ishga tushmagan. Avval db.init() chaqiring."
            )

    async def get_or_create_user(
        self, telegram_id: int, username: str = None, full_name: str = None
    ) -> dict:
        """Foydalanuvchini topish yoki yangi yaratish."""
        self._ensure_pool()
        async with self.pool.acquire() as conn:
            # Avval qidirish
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE telegram_id = $1", telegram_id
            )
            if user:
                return dict(user)

            # Yangi yaratish
            user = await conn.fetchrow(
                """
                INSERT INTO users (telegram_id, username, full_name)
                VALUES ($1, $2, $3)
                RETURNING *
                """,
                telegram_id,
                username,
                full_name,
            )
            return dict(user)

    async def update_user_stats(
        self, telegram_id: int, band_score: float, xp: int
    ):
        """Speaking sessiyadan keyin foydalanuvchi statistikasini yangilash."""
        self._ensure_pool()
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users SET
                    total_xp = total_xp + $2,
                    weekly_xp = weekly_xp + $2,
                    total_sessions = total_sessions + 1,
                    best_band_score = GREATEST(best_band_score, $3),
                    avg_band_score = COALESCE(
                        (COALESCE(avg_band_score, 0) * total_sessions + $3)
                        / NULLIF(total_sessions + 1, 0),
                        $3
                    ),
                    updated_at = NOW()
                WHERE telegram_id = $1
                """,
                telegram_id,
                xp,
                band_score,
            )

    async def update_user_league(self, telegram_id: int, league: str):
        """Foydalanuvchining ligasini yangilash."""
        self._ensure_pool()
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET current_league = $2, updated_at = NOW() WHERE telegram_id = $1",
                telegram_id,
                league,
            )

    # --- Speaking sessiya metodlari ---

    async def save_session(self, user_id: int, data: dict) -> int:
        """Speaking sessiyani saqlash va session ID qaytarish."""
        self._ensure_pool()
        async with self.pool.acquire() as conn:
            session_id = await conn.fetchval(
                """
                INSERT INTO speaking_sessions
                    (user_id, part, question_text, transcript, band_score,
                     fluency_score, lexical_score, grammar_score,
                     pronunciation_score, feedback_text, model_answer,
                     xp_earned, audio_file_id, duration_seconds)
                VALUES
                    ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                RETURNING id
                """,
                user_id,
                data.get("part", 1),
                data.get("question_text"),
                data["transcript"],
                data.get("band_score"),
                data.get("fluency_score"),
                data.get("lexical_score"),
                data.get("grammar_score"),
                data.get("pronunciation_score"),
                data.get("feedback_text"),
                data.get("model_answer"),
                data.get("xp_earned", 0),
                data.get("audio_file_id"),
                data.get("duration_seconds"),
            )
            return session_id

    async def save_vocabulary_suggestions(
        self, session_id: int, user_id: int, suggestions: list[dict]
    ):
        """Vocabulary tavsiyalarni bazaga saqlash (batch insert)."""
        self._ensure_pool()

        VALID_CATEGORIES = {'vocabulary', 'idiom', 'collocation', 'phrasal_verb'}

        async with self.pool.acquire() as conn:
            # Batch insert — loopdan tezroq
            await conn.executemany(
                """
                INSERT INTO vocabulary_suggestions
                    (session_id, user_id, original_word, suggested_word,
                     context_sentence, score_impact, category)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                """,
                [
                    (
                        session_id,
                        user_id,
                        s.get("original_word", ""),
                        s.get("suggested_word", ""),
                        s.get("context_sentence"),
                        str(s["score_impact"]) if s.get("score_impact") is not None else None,
                        s.get("category", "vocabulary") if s.get("category") in VALID_CATEGORIES else "vocabulary",
                    )
                    for s in suggestions
                ],
            )

    async def save_score(
        self, user_id: int, session_id: int, band_score: float, xp: int, league: str
    ):
        """Ball yozuvini saqlash."""
        self._ensure_pool()
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO scores (user_id, session_id, band_score, xp_earned, league_at_time)
                VALUES ($1, $2, $3, $4, $5)
                """,
                user_id,
                session_id,
                band_score,
                xp,
                league,
            )

    # --- Leaderboard metodlari ---

    async def get_weekly_top10(self) -> list[dict]:
        """Joriy haftaning Top-10 foydalanuvchilarini olish."""
        self._ensure_pool()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    telegram_id,
                    username,
                    full_name,
                    weekly_xp,
                    best_band_score,
                    current_league,
                    total_sessions
                FROM users
                WHERE weekly_xp > 0
                ORDER BY weekly_xp DESC
                LIMIT 10
                """
            )
            return [dict(r) for r in rows]

    async def get_user_rank(self, telegram_id: int) -> int | None:
        """Foydalanuvchining joriy haftalik o'rnini olish."""
        self._ensure_pool()
        async with self.pool.acquire() as conn:
            rank = await conn.fetchval(
                """
                SELECT rank FROM (
                    SELECT telegram_id,
                           RANK() OVER (ORDER BY weekly_xp DESC) as rank
                    FROM users
                    WHERE weekly_xp > 0
                ) ranked
                WHERE telegram_id = $1
                """,
                telegram_id,
            )
            return rank

    # --- Subscription metodlari ---

    async def check_user_access(self, telegram_id: int) -> dict:
        """
        Foydalanuvchining botdan foydalanish huquqini tekshirish.

        Returns:
            dict: {"allowed": bool, "reason": str, "free_left": int}
        """
        self._ensure_pool()
        async with self.pool.acquire() as conn:
            user = await conn.fetchrow(
                """
                SELECT free_uses_left, is_subscribed, subscription_expires
                FROM users WHERE telegram_id = $1
                """,
                telegram_id,
            )
            if not user:
                return {"allowed": True, "reason": "new_user", "free_left": 3}

            # Obuna faol
            if user["is_subscribed"] and user["subscription_expires"]:
                from datetime import datetime, timezone
                if user["subscription_expires"] > datetime.now(timezone.utc):
                    return {"allowed": True, "reason": "subscribed", "free_left": 0}
                else:
                    # Obuna muddati tugagan — o'chirish
                    await conn.execute(
                        "UPDATE users SET is_subscribed = FALSE WHERE telegram_id = $1",
                        telegram_id,
                    )

            # Bepul urinishlar
            if user["free_uses_left"] and user["free_uses_left"] > 0:
                return {
                    "allowed": True,
                    "reason": "free",
                    "free_left": user["free_uses_left"],
                }

            return {"allowed": False, "reason": "limit_reached", "free_left": 0}

    async def use_free_attempt(self, telegram_id: int):
        """Bepul urinishni 1 taga kamaytirish."""
        self._ensure_pool()
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE users SET free_uses_left = GREATEST(free_uses_left - 1, 0)
                WHERE telegram_id = $1
                """,
                telegram_id,
            )

    async def create_payment_request(
        self, user_id: int, screenshot_file_id: str
    ) -> int:
        """To'lov so'rovini yaratish. Returns: subscription id."""
        self._ensure_pool()
        async with self.pool.acquire() as conn:
            sub_id = await conn.fetchval(
                """
                INSERT INTO subscriptions (user_id, status, payment_screenshot)
                VALUES ($1, 'pending', $2)
                RETURNING id
                """,
                user_id,
                screenshot_file_id,
            )
            return sub_id

    async def approve_subscription(self, sub_id: int, admin_telegram_id: int):
        """Admin to'lovni tasdiqlash — 30 kunlik obuna berish."""
        self._ensure_pool()
        async with self.pool.acquire() as conn:
            # Subscription'ni yangilash
            sub = await conn.fetchrow(
                """
                UPDATE subscriptions SET
                    status = 'active',
                    approved_by = $2,
                    starts_at = NOW(),
                    expires_at = NOW() + INTERVAL '30 days'
                WHERE id = $1
                RETURNING user_id, expires_at
                """,
                sub_id,
                admin_telegram_id,
            )
            if sub:
                # User'ni ham yangilash
                await conn.execute(
                    """
                    UPDATE users SET
                        is_subscribed = TRUE,
                        subscription_expires = $2
                    WHERE id = $1
                    """,
                    sub["user_id"],
                    sub["expires_at"],
                )
            return sub

    async def reject_subscription(self, sub_id: int):
        """Admin to'lovni rad etish."""
        self._ensure_pool()
        async with self.pool.acquire() as conn:
            sub = await conn.fetchrow(
                """
                UPDATE subscriptions SET status = 'rejected'
                WHERE id = $1
                RETURNING user_id
                """,
                sub_id,
            )
            return sub

    async def get_user_id_by_internal(self, internal_id: int) -> int | None:
        """Internal user ID dan telegram_id olish."""
        self._ensure_pool()
        async with self.pool.acquire() as conn:
            return await conn.fetchval(
                "SELECT telegram_id FROM users WHERE id = $1", internal_id
            )

    async def has_pending_payment(self, user_id: int) -> bool:
        """Foydalanuvchining kutilayotgan to'lovi bormi?"""
        self._ensure_pool()
        async with self.pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM subscriptions WHERE user_id = $1 AND status = 'pending'",
                user_id,
            )
            return count > 0


# Global instance
db = Database()
