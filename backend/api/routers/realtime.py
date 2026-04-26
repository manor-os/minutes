"""
Real-time transcription via WebSocket.
Browser sends audio chunks -> server transcribes -> sends back text segments.
"""
import asyncio
import json
import os
import tempfile
import time
from typing import Optional

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger
from openai import OpenAI

router = APIRouter(tags=["realtime"])

# Minimum audio buffer before transcribing (seconds of audio)
MIN_CHUNK_DURATION = 3.0
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/meeting_notes")
STT_MODE = os.getenv("STT_MODE", "cloud")  # "cloud" or "local"


def _load_user_stt_key() -> Optional[str]:
    """Load user's STT API key from database."""
    try:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        with conn.cursor() as cur:
            cur.execute("SELECT stt_api_key FROM users WHERE stt_api_key IS NOT NULL AND stt_api_key != '' LIMIT 1")
            row = cur.fetchone()
        conn.close()
        return row["stt_api_key"] if row else None
    except Exception:
        return None


@router.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket):
    """
    Real-time transcription WebSocket.

    Client sends:
      - Binary frames: raw audio data (webm/opus or wav)
      - Text frames: JSON commands like {"type": "config", "language": "en"}

    Server sends:
      - JSON text frames: {"type": "transcript", "text": "...", "timestamp": 1.5, "is_final": true}
      - JSON text frames: {"type": "status", "message": "processing..."}
    """
    # Authenticate WebSocket connection
    token = websocket.query_params.get("token") or websocket.headers.get("authorization", "").replace("Bearer ", "")
    if token:
        try:
            import jwt
            payload = jwt.decode(token, os.getenv("JWT_SECRET", ""), algorithms=["HS256"])
        except Exception:
            await websocket.close(code=4001, reason="Invalid token")
            return
    # No token provided — allow unauthenticated connections (local auth mode)

    await websocket.accept()

    language = None
    audio_buffer = bytearray()
    chunk_count = 0
    session_start = time.time()
    total_audio_duration = 0.0

    use_local_stt = STT_MODE == "local"

    client = None
    if not use_local_stt:
        # Resolve API key: user's DB key > env var
        env_key = os.getenv("OPENAI_API_KEY", "").strip()
        user_key = _load_user_stt_key()
        effective_key = user_key or env_key

        if not effective_key:
            await websocket.send_json({"type": "error", "message": "No OpenAI API key configured. Set your key in Settings."})
            await websocket.close()
            return

        client = OpenAI(api_key=effective_key)

    try:
        await websocket.send_json({"type": "status", "message": "Connected. Listening..."})

        while True:
            data = await websocket.receive()

            if "text" in data:
                try:
                    msg = json.loads(data["text"])
                    if msg.get("type") == "config":
                        language = msg.get("language") or None
                        # Allow overriding key from client
                        client_key = msg.get("stt_api_key") or msg.get("api_key")
                        if client_key:
                            client = OpenAI(api_key=client_key)
                        await websocket.send_json({"type": "status", "message": f"Ready. Language: {language or 'auto-detect'}"})
                    elif msg.get("type") == "stop":
                        if len(audio_buffer) > 0:
                            text = await _transcribe_buffer(client, audio_buffer, language, use_local=use_local_stt)
                            if text:
                                await websocket.send_json({
                                    "type": "transcript",
                                    "text": text,
                                    "timestamp": total_audio_duration,
                                    "is_final": True,
                                })
                        await websocket.send_json({"type": "status", "message": "Session ended"})
                        break
                except json.JSONDecodeError:
                    pass

            elif "bytes" in data:
                # Each binary message is a complete 5-second webm audio file
                chunk_count += 1
                audio_data = bytearray(data["bytes"])

                if len(audio_data) < 1000:
                    continue  # Too small, skip

                total_audio_duration += 3.0  # Each chunk is ~3 seconds
                text = await _transcribe_buffer(client, audio_data, language, use_local=use_local_stt)

                if text and text.strip():
                    await websocket.send_json({
                        "type": "transcript",
                        "text": text.strip(),
                        "timestamp": total_audio_duration,
                        "is_final": True,
                        "chunk": chunk_count,
                    })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected after {time.time() - session_start:.1f}s, {chunk_count} chunks")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": "An internal error occurred. Please try again."})
        except Exception:
            pass


async def _transcribe_buffer(client, audio_buffer: bytearray, language: Optional[str] = None, use_local: bool = False) -> str:
    """Transcribe an audio buffer using Whisper API or local faster-whisper.
    The buffer contains raw WebM/opus data from MediaRecorder chunks.
    First chunk contains the WebM header; subsequent chunks are cluster data."""
    if not use_local and not client:
        return ""
    if len(audio_buffer) < 1000:
        return ""  # Too small to be valid audio
    try:
        if use_local:
            from api.services.local_transcription_service import transcribe_chunk_streaming
            loop = asyncio.get_event_loop()
            words = await loop.run_in_executor(None, lambda: transcribe_chunk_streaming(bytes(audio_buffer), language))
            return " ".join(w["word"] for w in words).strip()

        # Save as .webm — the accumulated buffer should contain valid WebM
        # since MediaRecorder sends complete WebM clusters
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
            f.write(bytes(audio_buffer))
            temp_path = f.name

        try:
            loop = asyncio.get_event_loop()
            transcript = await loop.run_in_executor(None, lambda: _whisper_transcribe(client, temp_path, language))
            return transcript
        finally:
            os.unlink(temp_path)
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        return ""


def _whisper_transcribe(client, filepath: str, language: Optional[str] = None) -> str:
    """Sync Whisper API call."""
    with open(filepath, "rb") as audio_file:
        kwargs = {"model": "whisper-1", "file": audio_file, "response_format": "text"}
        if language:
            kwargs["language"] = language
        return client.audio.transcriptions.create(**kwargs)
