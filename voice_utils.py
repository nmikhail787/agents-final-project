"""Person D voice helpers: fragment-based ASR and TTS via OpenAI audio APIs."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import BinaryIO

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

ASR_MODEL = os.getenv("ASR_MODEL", "whisper-1")
TTS_MODEL = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")
TTS_VOICE = os.getenv("TTS_VOICE", "coral")


def _client() -> OpenAI:
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Copy .env.example to .env and add your key."
        )
    return OpenAI()


def transcribe_audio(audio_file: BinaryIO, filename: str = "recording.wav") -> str:
    """Transcribe a recorded/uploaded fragment into text."""
    client = _client()

    # Streamlit UploadedFile objects work like file objects, but OpenAI also
    # needs a filename to infer the media type reliably.
    audio_file.seek(0)
    payload = (filename, audio_file.read())

    result = client.audio.transcriptions.create(
        model=ASR_MODEL,
        file=payload,
        prompt=(
            "The speaker is shopping for Toys & Games. Product and brand names "
            "may be mentioned. Preserve prices and brand names accurately."
        ),
    )
    return (result.text or "").strip()


def synthesize_speech(text: str) -> bytes:
    """Convert the short spoken answer to MP3 bytes for Streamlit playback."""
    if not text.strip():
        return b""

    client = _client()
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "answer.mp3"
        with client.audio.speech.with_streaming_response.create(
            model=TTS_MODEL,
            voice=TTS_VOICE,
            input=text,
            instructions=(
                "Speak clearly and naturally like a concise shopping assistant. "
                "Keep a friendly, neutral tone and do not add words not in the text."
            ),
        ) as response:
            response.stream_to_file(output_path)
        return output_path.read_bytes()
