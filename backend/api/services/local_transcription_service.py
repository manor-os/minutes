"""
Local transcription using faster-whisper (no API key needed).
Supports real-time streaming with word-level timestamps.
"""
import os
import logging
import tempfile
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Lazy-load model to avoid startup delay
_model = None
_model_size = os.getenv("WHISPER_MODEL_SIZE", "base")  # tiny, base, small, medium, large-v3


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        device = os.getenv("WHISPER_DEVICE", "cpu")  # cpu or cuda
        compute_type = "int8" if device == "cpu" else "float16"
        logger.info(f"Loading faster-whisper model: {_model_size} on {device} ({compute_type})")
        _model = WhisperModel(_model_size, device=device, compute_type=compute_type)
        logger.info(f"Model loaded successfully")
    return _model


def _convert_to_wav(audio_filepath: str) -> str:
    """Convert audio to 16kHz mono WAV for faster-whisper.
    For long files (>10min), compress to low-bitrate MP3 first to save memory."""
    import subprocess

    # Check duration
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_filepath],
            capture_output=True, text=True, timeout=30,
        )
        duration = float(probe.stdout.strip()) if probe.stdout.strip() else 0
    except Exception:
        duration = 0

    # For long recordings, use compressed MP3 (saves memory)
    if duration > 600:  # > 10 minutes
        logger.info(f"Long audio ({duration:.0f}s), compressing to MP3 first")
        mp3_path = tempfile.mktemp(suffix=".mp3")
        try:
            subprocess.run(
                ["ffmpeg", "-i", audio_filepath, "-ar", "16000", "-ac", "1", "-b:a", "32k", "-y", mp3_path],
                check=True, capture_output=True, timeout=600,
            )
            logger.info(f"Compressed: {os.path.getsize(audio_filepath)} → {os.path.getsize(mp3_path)} bytes")
            return mp3_path
        except Exception as e:
            logger.warning(f"MP3 compression failed: {e}")
            if os.path.exists(mp3_path):
                os.unlink(mp3_path)

    # Standard: convert to WAV
    wav_path = tempfile.mktemp(suffix=".wav")
    try:
        subprocess.run(
            ["ffmpeg", "-i", audio_filepath, "-ar", "16000", "-ac", "1", "-y", wav_path],
            check=True, capture_output=True, timeout=300,
        )
        return wav_path
    except Exception as e:
        logger.warning(f"WAV conversion failed: {e}, using original file")
        if os.path.exists(wav_path):
            os.unlink(wav_path)
        return audio_filepath


def _split_audio(audio_filepath: str, chunk_minutes: int = 5) -> List[str]:
    """Split long audio into chunks for memory-safe transcription."""
    import subprocess

    # Get duration
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_filepath],
            capture_output=True, text=True, timeout=30,
        )
        duration = float(probe.stdout.strip())
    except Exception:
        return [audio_filepath]

    chunk_seconds = chunk_minutes * 60
    if duration <= chunk_seconds:
        return [audio_filepath]

    chunks = []
    num_chunks = int(duration / chunk_seconds) + 1
    logger.info(f"Splitting {duration:.0f}s audio into {num_chunks} chunks of {chunk_minutes}min")

    for i in range(num_chunks):
        start = i * chunk_seconds
        chunk_path = tempfile.mktemp(suffix=f"_chunk{i}.wav")
        try:
            subprocess.run(
                ["ffmpeg", "-i", audio_filepath, "-ss", str(start), "-t", str(chunk_seconds),
                 "-ar", "16000", "-ac", "1", "-y", chunk_path],
                check=True, capture_output=True, timeout=120,
            )
            if os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 1000:
                chunks.append(chunk_path)
        except Exception as e:
            logger.warning(f"Failed to create chunk {i}: {e}")
            if os.path.exists(chunk_path):
                os.unlink(chunk_path)

    return chunks if chunks else [audio_filepath]


def transcribe_local(audio_filepath: str, language: Optional[str] = None) -> Dict[str, Any]:
    """Transcribe audio file using local faster-whisper model.
    Splits long audio into 5-min chunks to prevent OOM."""
    model = _get_model()

    # Convert for reliable processing
    wav_path = _convert_to_wav(audio_filepath)
    converted = wav_path != audio_filepath

    orig_size = os.path.getsize(audio_filepath) if os.path.exists(audio_filepath) else 0
    wav_size = os.path.getsize(wav_path) if os.path.exists(wav_path) else 0
    logger.info(f"Transcribing: original={audio_filepath} ({orig_size}B), converted={wav_path} ({wav_size}B)")

    kwargs = {"beam_size": 5, "word_timestamps": True}
    if language:
        kwargs["language"] = language

    # Split long audio into chunks
    chunks = _split_audio(wav_path)
    is_chunked = len(chunks) > 1

    segments = []
    full_text_parts = []
    detected_language = None
    language_prob = 0.0
    total_duration = 0.0
    time_offset = 0.0
    temp_files = []

    for chunk_idx, chunk_path in enumerate(chunks):
        if is_chunked:
            logger.info(f"Transcribing chunk {chunk_idx + 1}/{len(chunks)}: {chunk_path}")
            if chunk_path != wav_path:
                temp_files.append(chunk_path)

        try:
            segments_iter, info = model.transcribe(chunk_path, **kwargs)
        except Exception as e:
            logger.warning(f"Chunk {chunk_idx} transcription failed: {e}")
            if is_chunked:
                time_offset += 5 * 60  # skip this chunk
                continue
            raise

        if not detected_language:
            detected_language = info.language
            language_prob = info.language_probability
        total_duration = max(total_duration, info.duration + time_offset)

        for segment in segments_iter:
            seg_data = {
                "start": round(segment.start + time_offset, 2),
                "end": round(segment.end + time_offset, 2),
                "text": segment.text.strip(),
            }
            if segment.words:
                seg_data["words"] = [
                    {"word": w.word, "start": round(w.start + time_offset, 2), "end": round(w.end + time_offset, 2), "probability": round(w.probability, 3)}
                    for w in segment.words
                ]
            segments.append(seg_data)
            full_text_parts.append(segment.text.strip())

        time_offset += info.duration

    # Clean up temp files
    if converted and os.path.exists(wav_path):
        try: os.unlink(wav_path)
        except Exception: pass
    for f in temp_files:
        try: os.unlink(f)
        except Exception: pass

    return {
        "text": " ".join(full_text_parts),
        "segments": segments,
        "language": info.language,
        "language_probability": round(info.language_probability, 3),
        "duration": round(info.duration, 2),
    }


def transcribe_chunk_streaming(audio_data: bytes, language: Optional[str] = None) -> List[Dict[str, Any]]:
    """Transcribe a short audio chunk for real-time streaming.
    Returns list of words with timestamps."""
    model = _get_model()

    # Write to temp file
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
        f.write(audio_data)
        temp_path = f.name

    try:
        kwargs = {"beam_size": 1, "word_timestamps": True, "vad_filter": True}
        if language:
            kwargs["language"] = language

        segments_iter, info = model.transcribe(temp_path, **kwargs)

        words = []
        for segment in segments_iter:
            if segment.words:
                for w in segment.words:
                    words.append({
                        "word": w.word,
                        "start": round(w.start, 2),
                        "end": round(w.end, 2),
                    })
            else:
                words.append({"word": segment.text.strip(), "start": round(segment.start, 2), "end": round(segment.end, 2)})

        return words
    finally:
        os.unlink(temp_path)
