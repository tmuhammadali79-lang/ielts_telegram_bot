"""
D-ID API Video Generator Service.

Bu modul D-ID API yordamida AI avatar video yaratadi.
Feedback matni → Talking Head Video → Telegram Video Note

📹 D-ID tanlangan sabablari:
  - Real-time API — 30 soniya ichida video tayyor
  - Arzon narx — $5.90/oy (10 ta video)
  - Yuqori sifat — lip-sync va natural ko'rinish
  - Oddiy REST API — faqat 2 ta endpoint kerak
"""
import os
import asyncio
import logging
import aiohttp
import aiofiles

from config import config

logger = logging.getLogger(__name__)

# Video fayllar uchun vaqtinchalik papka
TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp_videos")
os.makedirs(TEMP_DIR, exist_ok=True)


async def create_talking_video(
    script_text: str,
    presenter_url: str = None,
    voice_id: str = "en-US-JennyNeural",
) -> str | None:
    """
    D-ID API yordamida talking head video yaratish.

    Args:
        script_text: Avatar gapirishi kerak bo'lgan matn
        presenter_url: Avatar rasm URL (default: config'dan)
        voice_id: Microsoft Azure TTS voice ID

    Returns:
        str: Tayyor video fayl yo'li yoki None (xatolikda)

    Jarayon:
        1. D-ID API ga POST so'rov yuboriladi (video yaratish)
        2. Video tayyor bo'lguncha kutiladi (polling)
        3. Tayyor video yuklab olinadi
    """
    if not config.DID_API_KEY:
        logger.warning("⚠️ D-ID API kaliti yo'q. Video yaratib bo'lmaydi.")
        return None

    presenter = presenter_url or config.DID_PRESENTER_URL

    headers = {
        "Authorization": f"Basic {config.DID_API_KEY}",
        "Content-Type": "application/json",
    }

    # 1-qadam: Video yaratish so'rovi
    payload = {
        "source_url": presenter,
        "script": {
            "type": "text",
            "input": script_text,
            "provider": {
                "type": "microsoft",
                "voice_id": voice_id,
            },
        },
        "config": {
            "result_format": "mp4",
            "stitch": True,
        },
    }

    try:
        async with aiohttp.ClientSession() as session:
            # Video yaratishni boshlash
            async with session.post(
                f"{config.DID_API_URL}/talks",
                json=payload,
                headers=headers,
            ) as resp:
                if resp.status != 201:
                    error = await resp.text()
                    logger.error(f"❌ D-ID yaratish xatosi: {resp.status} — {error}")
                    return None

                data = await resp.json()
                talk_id = data["id"]
                logger.info(f"🎬 Video yaratish boshlandi: {talk_id}")

            # 2-qadam: Video tayyor bo'lishini kutish (polling)
            video_url = await _poll_video_status(session, headers, talk_id)

            if not video_url:
                return None

            # 3-qadam: Videoni yuklab olish
            video_path = await _download_video(session, video_url, talk_id)
            return video_path

    except Exception as e:
        logger.error(f"❌ D-ID API umumiy xato: {e}")
        return None


async def _poll_video_status(
    session: aiohttp.ClientSession,
    headers: dict,
    talk_id: str,
    max_attempts: int = 30,
    interval: float = 2.0,
) -> str | None:
    """
    Video tayyor bo'lishini kutish (polling).

    D-ID video yaratish 10-60 soniya olishi mumkin.
    Har 2 soniyada status tekshiriladi.
    """
    for attempt in range(max_attempts):
        await asyncio.sleep(interval)

        async with session.get(
            f"{config.DID_API_URL}/talks/{talk_id}",
            headers=headers,
        ) as resp:
            if resp.status != 200:
                continue

            data = await resp.json()
            status = data.get("status")

            if status == "done":
                video_url = data.get("result_url")
                logger.info(f"✅ Video tayyor: {video_url}")
                return video_url
            elif status == "error":
                logger.error(f"❌ D-ID video xatosi: {data}")
                return None
            else:
                logger.debug(
                    f"⏳ Video status: {status} (urinish {attempt + 1}/{max_attempts})"
                )

    logger.error("❌ D-ID video timeout — 60 soniya ichida tayyor bo'lmadi")
    return None


async def _download_video(
    session: aiohttp.ClientSession,
    video_url: str,
    talk_id: str,
) -> str:
    """Tayyor videoni mahalliy faylga yuklab olish."""
    file_path = os.path.join(TEMP_DIR, f"{talk_id}.mp4")

    async with session.get(video_url) as resp:
        if resp.status == 200:
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(await resp.read())
            logger.info(f"📥 Video yuklab olindi: {file_path}")
            return file_path
        else:
            logger.error(f"❌ Video yuklab olish xatosi: {resp.status}")
            return None


async def cleanup_video(file_path: str):
    """Vaqtinchalik video faylni o'chirish."""
    try:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            logger.debug(f"🗑 Video fayl o'chirildi: {file_path}")
    except OSError as e:
        logger.warning(f"⚠️ Video fayl o'chirilmadi: {e}")
