"""
shared/voice.py — Голосовой ввод через Whisper.

Поддерживает:
- OpenAI Whisper API (через OpenRouter)
- Локальный Whisper (whisper python package)
- Браузерный Web Speech API (фронтенд)

Зависимости: whisper (опционально), httpx

Использование:
    from shared.voice import transcribe_audio, transcribe_file
    text = transcribe_file("recording.wav")
"""

import os
import tempfile
from typing import Optional

from shared.config import settings


def transcribe_audio(audio_bytes: bytes, language: str = "ru",
                     api_key: str = "", model: str = "whisper-1") -> str:
    """
    Транскрибирует аудио через OpenAI Whisper API.

    Args:
        audio_bytes: байты аудиофайла (wav, mp3, ogg, webm)
        language: код языка ("ru", "en")
        api_key: OpenAI API ключ (или из env)
        model: модель whisper

    Returns:
        Распознанный текст
    """
    import httpx

    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY", "")

    if not api_key:
        # Fallback на локальный Whisper
        return _transcribe_local(audio_bytes, language)

    headers = {"Authorization": f"Bearer {api_key}"}

    # Определяем формат
    files = {
        "file": ("audio.wav", audio_bytes, "audio/wav"),
    }
    data = {
        "model": model,
        "language": language,
        "response_format": "text",
    }

    try:
        r = httpx.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers=headers,
            files=files,
            data=data,
            timeout=30.0,
        )
        if r.status_code == 200:
            return r.text.strip()
        else:
            print(f"[voice] Whisper API error: {r.status_code} {r.text[:200]}")
            return _transcribe_local(audio_bytes, language)
    except Exception as e:
        print(f"[voice] Whisper API failed: {e}, trying local")
        return _transcribe_local(audio_bytes, language)


def transcribe_file(file_path: str, language: str = "ru") -> str:
    """
    Транскрибирует аудиофайл.

    Args:
        file_path: путь к аудиофайлу
        language: код языка

    Returns:
        Распознанный текст
    """
    with open(file_path, "rb") as f:
        audio_bytes = f.read()
    return transcribe_audio(audio_bytes, language)


def _transcribe_local(audio_bytes: bytes, language: str = "ru") -> str:
    """Транскрибация через локальный Whisper."""
    try:
        import whisper
    except ImportError:
        raise ImportError(
            "whisper не установлен. Установите: pip install openai-whisper\n"
            "Или задайте OPENAI_API_KEY для использования API."
        )

    # Сохраняем во временный файл
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        model = whisper.load_model("base")
        result = model.transcribe(tmp_path, language=language)
        return result["text"].strip()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def detect_language_hint(text: str) -> str:
    """
    Определяет подсказку языка из текста промта.
    Используется для выбора языка Whisper.
    """
    russian_chars = sum(1 for c in text if '\u0400' <= c <= '\u04ff')
    if russian_chars > len(text) * 0.3:
        return "ru"
    return "en"
