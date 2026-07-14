# intel-monitor/backend/services/youtube_deep.py
"""
Deep analysis for YouTube videos.

Flow:
  1. yt-dlp downloads best audio stream → temp file
  2. faster-whisper transcribes audio → text
  3. LLM generates Chinese content summary
  4. Summary appended to SentimentPost.content
  5. Temp file deleted
  6. deep_analysis_status set to 'completed' or 'failed'
"""
import logging
import os
import tempfile
import asyncio

from sqlalchemy import select

from database import async_session
from models.sentiment_post import SentimentPost

logger = logging.getLogger(__name__)

# Lazy imports — only import on first use (avoid heavy deps on startup)
_yt_dlp = None
_faster_whisper = None
_whisper_model = None


def _get_yt_dlp():
    global _yt_dlp
    if _yt_dlp is None:
        import yt_dlp
        _yt_dlp = yt_dlp
    return _yt_dlp


def _do_transcribe(audio_path: str) -> str:
    """Run faster-whisper transcription in a synchronous context.
    Called via run_in_executor because faster-whisper uses CTranslate2 (CPU-bound).
    """
    global _faster_whisper, _whisper_model

    if _faster_whisper is None:
        from faster_whisper import WhisperModel
        _faster_whisper = WhisperModel

    if _whisper_model is None:
        logger.info("Loading faster-whisper small model...")
        _whisper_model = _faster_whisper("small", device="cpu", compute_type="int8")
        logger.info("faster-whisper model loaded")

    segments, _info = _whisper_model.transcribe(audio_path, beam_size=5, language="zh")
    text = " ".join(seg.text.strip() for seg in segments)
    logger.info(f"Transcription complete: {len(text)} chars")
    return text


async def run_deep_analysis(post_id: int, video_url: str):
    """Background task: download audio, transcribe, summarize, update DB."""
    temp_dir = None
    audio_path = None

    try:
        # 1. Download audio via yt-dlp
        yt_dlp = _get_yt_dlp()
        temp_dir = tempfile.mkdtemp(prefix="yt_deep_")
        output_template = os.path.join(temp_dir, "%(id)s.%(ext)s")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
            }],
            "quiet": True,
            "no_warnings": True,
        }

        logger.info(f"Downloading audio for {video_url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=True)
            video_id = info.get("id", "unknown")
            video_title = info.get("title", "")

        # Find the output file
        expected_mp3 = os.path.join(temp_dir, f"{video_id}.mp3")
        if os.path.exists(expected_mp3):
            audio_path = expected_mp3
        else:
            # Search for any audio file in temp dir
            for f in os.listdir(temp_dir):
                if f.endswith((".mp3", ".m4a", ".opus", ".webm")):
                    audio_path = os.path.join(temp_dir, f)
                    break

        if not audio_path or not os.path.exists(audio_path):
            raise RuntimeError(f"yt-dlp failed to produce audio file (temp_dir={temp_dir})")

        logger.info(f"Audio downloaded: {audio_path} ({os.path.getsize(audio_path)} bytes)")

        # 2. Transcribe via faster-whisper (CPU-bound, run in executor)
        loop = asyncio.get_event_loop()
        transcription = await loop.run_in_executor(None, _do_transcribe, audio_path)

        if not transcription or not transcription.strip():
            raise RuntimeError("Transcription produced empty text")

        # 3. Generate Chinese summary via LLM
        from services.summarizer import summarizer

        system_prompt = (
            "你是一个视频内容深度分析助手。请基于视频的完整转录文本，生成一份结构化的中文摘要。"
            "摘要应包含：\n"
            "1. 视频主题概述（一句话）\n"
            "2. 核心观点与关键信息点（3-5条）\n"
            "3. 情绪倾向（正面/负面/中立）\n"
            "4. 如果有明显的关键人物、组织、事件，请标注\n"
            "直接输出分析内容，不要输出思考过程。控制在500字以内。"
        )
        user_prompt = f"视频标题：{video_title}\n\n完整转录文本：\n{transcription[:8000]}"

        summary = await summarizer._call_ai(system_prompt, user_prompt, _allow_fallback=True)
        if not summary:
            raise RuntimeError("LLM 返回空摘要")
        summary = summary.strip()

        # 4. Update SentimentPost
        async with async_session() as db:
            post = await db.get(SentimentPost, post_id)
            if post:
                post.content = (post.content or "") + "\n\n【深度分析】\n" + summary
                post.deep_analysis_status = "completed"
                await db.commit()
                logger.info(f"Deep analysis completed for post {post_id}")

    except Exception as e:
        logger.exception(f"Deep analysis failed for post {post_id}")
        try:
            async with async_session() as db:
                post = await db.get(SentimentPost, post_id)
                if post:
                    post.deep_analysis_status = "failed"
                    post.content = (post.content or "") + f"\n\n【深度分析失败】{str(e)[:200]}"
                    await db.commit()
        except Exception:
            logger.exception("Failed to update deep_analysis_status to failed")

    finally:
        # 5. Clean up temp files
        if temp_dir and os.path.exists(temp_dir):
            import shutil
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned up temp dir: {temp_dir}")
            except Exception:
                logger.warning(f"Failed to clean up temp dir: {temp_dir}")
