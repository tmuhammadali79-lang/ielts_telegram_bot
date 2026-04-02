-- ============================================
-- IELTS Speaking Bot — PostgreSQL Database Schema
-- Yaratilgan: 2026-04-02
-- ============================================

-- 1. Foydalanuvchilar jadvali
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    telegram_id     BIGINT UNIQUE NOT NULL,
    username        VARCHAR(64),
    full_name       VARCHAR(128),
    language_code   VARCHAR(10) DEFAULT 'uz',

    -- Gamification
    total_xp        INTEGER DEFAULT 0,
    current_league  VARCHAR(20) DEFAULT 'bronze'
        CHECK (current_league IN ('bronze', 'silver', 'gold', 'platinum', 'diamond')),
    weekly_xp       INTEGER DEFAULT 0,

    -- Statistika
    total_sessions      INTEGER DEFAULT 0,
    best_band_score     NUMERIC(2,1) DEFAULT 0.0,
    avg_band_score      NUMERIC(3,1) DEFAULT 0.0,

    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_users_weekly_xp ON users(weekly_xp DESC);
CREATE INDEX idx_users_current_league ON users(current_league);


-- 2. Speaking test sessiyalari
CREATE TABLE IF NOT EXISTS speaking_sessions (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    -- IELTS ma'lumotlari
    part            SMALLINT DEFAULT 1 CHECK (part IN (1, 2, 3)),
    question_text   TEXT,
    transcript      TEXT NOT NULL,

    -- Baholar (IELTS 0.0 - 9.0)
    band_score          NUMERIC(2,1),
    fluency_score       NUMERIC(2,1),
    lexical_score       NUMERIC(2,1),
    grammar_score       NUMERIC(2,1),
    pronunciation_score NUMERIC(2,1),

    -- GPT-4 javobi
    feedback_text       TEXT,
    model_answer        TEXT,

    -- XP
    xp_earned           INTEGER DEFAULT 0,

    -- Audio fayl
    audio_file_id       VARCHAR(256),
    duration_seconds    INTEGER,

    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sessions_user_id ON speaking_sessions(user_id);
CREATE INDEX idx_sessions_created_at ON speaking_sessions(created_at DESC);


-- 3. Vocabulary tavsiyalari tarixi
CREATE TABLE IF NOT EXISTS vocabulary_suggestions (
    id              SERIAL PRIMARY KEY,
    session_id      INTEGER NOT NULL REFERENCES speaking_sessions(id) ON DELETE CASCADE,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    original_word       VARCHAR(128) NOT NULL,
    suggested_word      VARCHAR(128) NOT NULL,
    context_sentence    TEXT,
    score_impact        VARCHAR(64),        -- masalan: "+0.5 band"
    category            VARCHAR(32) DEFAULT 'vocabulary'
        CHECK (category IN ('vocabulary', 'idiom', 'collocation', 'phrasal_verb')),

    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_vocab_user_id ON vocabulary_suggestions(user_id);
CREATE INDEX idx_vocab_session_id ON vocabulary_suggestions(session_id);


-- 4. Ballar tarixi (har bir sessiya uchun)
CREATE TABLE IF NOT EXISTS scores (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id      INTEGER NOT NULL REFERENCES speaking_sessions(id) ON DELETE CASCADE,

    band_score      NUMERIC(2,1) NOT NULL,
    xp_earned       INTEGER NOT NULL DEFAULT 0,
    league_at_time  VARCHAR(20),

    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_scores_user_id ON scores(user_id);
CREATE INDEX idx_scores_band ON scores(band_score DESC);


-- 5. Haftalik Leaderboard
CREATE TABLE IF NOT EXISTS leaderboard_weekly (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    week_start      DATE NOT NULL,
    week_end        DATE NOT NULL,
    total_xp        INTEGER DEFAULT 0,
    best_band       NUMERIC(2,1) DEFAULT 0.0,
    sessions_count  INTEGER DEFAULT 0,
    rank_position   INTEGER,
    league          VARCHAR(20),

    -- Sovg'alar
    prize_claimed   BOOLEAN DEFAULT FALSE,
    prize_details   TEXT,

    created_at      TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE (user_id, week_start)
);

CREATE INDEX idx_lb_week ON leaderboard_weekly(week_start, total_xp DESC);
CREATE INDEX idx_lb_user ON leaderboard_weekly(user_id);


-- 6. Haftalik XP reset qiluvchi funksiya
CREATE OR REPLACE FUNCTION reset_weekly_xp()
RETURNS void AS $$
BEGIN
    -- Avval joriy hafta natijalarini leaderboard_weekly ga saqlash
    INSERT INTO leaderboard_weekly (user_id, week_start, week_end, total_xp, best_band, sessions_count, league)
    SELECT
        u.id,
        date_trunc('week', NOW())::date,
        (date_trunc('week', NOW()) + INTERVAL '6 days')::date,
        u.weekly_xp,
        u.best_band_score,
        COALESCE(s.weekly_count, 0),
        u.current_league
    FROM users u
    LEFT JOIN (
        SELECT user_id, COUNT(*) AS weekly_count
        FROM speaking_sessions
        WHERE created_at >= date_trunc('week', NOW())
        GROUP BY user_id
    ) s ON s.user_id = u.id
    WHERE u.weekly_xp > 0
    ON CONFLICT (user_id, week_start)
    DO UPDATE SET
        total_xp = EXCLUDED.total_xp,
        best_band = EXCLUDED.best_band,
        sessions_count = EXCLUDED.sessions_count;

    -- Weekly XP ni nolga tushirish
    UPDATE users SET weekly_xp = 0;
END;
$$ LANGUAGE plpgsql;
