"""
Konfiguratsiya fayli — barcha muhit o'zgaruvchilari shu yerdan olinadi.

.env faylida quyidagilar bo'lishi kerak:
    BOT_TOKEN=your_telegram_bot_token
    OPENAI_API_KEY=sk-...
    DATABASE_URL=postgresql://user:password@localhost:5432/ielts_bot
    DID_API_KEY=your_d_id_api_key
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Bot konfiguratsiyasi."""

    # Telegram
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")

    # OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    GPT_MODEL: str = "gpt-4o"
    WHISPER_MODEL: str = "whisper-1"
    TTS_MODEL: str = "tts-1"
    TTS_VOICE: str = "alloy"

    # PostgreSQL
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ielts_bot"
    )

    # D-ID (Video Avatar)
    DID_API_KEY: str = os.getenv("DID_API_KEY", "")
    DID_API_URL: str = "https://api.d-id.com"
    DID_PRESENTER_URL: str = (
        "https://d-id-public-bucket.s3.us-west-2.amazonaws.com/"
        "alice.jpg"  # Default presenter avatar
    )

    # Subscription / Admin
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0")) if os.getenv("ADMIN_ID", "0").isdigit() else 0
    CARD_NUMBER: str = os.getenv("CARD_NUMBER", "8600 0000 0000 0000")
    CARD_HOLDER: str = os.getenv("CARD_HOLDER", "ISM FAMILIYA")
    FREE_LIMIT: int = 3
    SUBSCRIPTION_PRICE: int = 60000  # so'm
    SUBSCRIPTION_DAYS: int = 30

    # Gamification
    LEAGUE_THRESHOLDS: dict = None

    def __post_init__(self):
        if self.LEAGUE_THRESHOLDS is None:
            self.LEAGUE_THRESHOLDS = {
                "bronze": 0,
                "silver": 500,
                "gold": 1500,
                "platinum": 3500,
                "diamond": 7000,
            }


config = Config()
