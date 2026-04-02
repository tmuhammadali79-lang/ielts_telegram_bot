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
                        s.get("category", "vocabulary"),
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


# Global instance
db = Database()
