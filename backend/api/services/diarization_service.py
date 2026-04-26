"""
Speaker diarization service — identifies different speakers in audio.

Strategy (in order of preference):
1. pyannote-audio — best accuracy, requires HF_TOKEN + torch
2. LLM-based — uses Ollama/OpenAI to detect speakers from text patterns
3. Pause-based — simple fallback, alternates on silence gaps
"""
import os
import json
from loguru import logger
from typing import List, Dict, Optional


def diarize_with_segments(audio_path: str, segments: List[Dict], language: str = None, num_speakers: int = 0) -> List[Dict]:
    """
    Add speaker labels to transcript segments.
    num_speakers=0 means auto-detect.
    """
    if not segments:
        return segments

    # 1. Try pyannote-audio (best quality)
    try:
        return _diarize_pyannote(audio_path, segments, num_speakers=num_speakers)
    except ImportError:
        logger.info("pyannote-audio not installed")
    except Exception as e:
        logger.warning(f"pyannote failed: {e}")

    # 2. Try LLM-based diarization (good quality, uses existing Ollama/OpenAI)
    try:
        logger.info("Attempting LLM-based speaker diarization...")
        result = _diarize_with_llm(segments, num_speakers=num_speakers)
        if result:
            return result
        logger.info("LLM diarization returned None, falling back to pause-based")
    except Exception as e:
        logger.warning(f"LLM diarization failed: {e}")

    # 3. Fallback: pause-based
    return _diarize_by_pauses(segments, max_speakers=num_speakers or 2)


def _diarize_pyannote(audio_path: str, segments: List[Dict], num_speakers: int = 0) -> List[Dict]:
    """Use pyannote-audio for speaker diarization."""
    from pyannote.audio import Pipeline

    hf_token = os.getenv("HF_TOKEN", "")
    if not hf_token:
        raise ValueError("HF_TOKEN required for pyannote diarization")

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=hf_token,
    )

    params = {}
    if num_speakers > 0:
        params["num_speakers"] = num_speakers

    diarization = pipeline(audio_path, **params)

    speaker_timeline = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        speaker_timeline.append({"start": turn.start, "end": turn.end, "speaker": speaker})

    for seg in segments:
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", seg_start + 1)
        best_speaker = "Speaker"
        best_overlap = 0
        for st in speaker_timeline:
            overlap = max(0, min(seg_end, st["end"]) - max(seg_start, st["start"]))
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = st["speaker"]
        seg["speaker"] = best_speaker

    # Rename to friendly names
    speaker_map = {}
    counter = 1
    for seg in segments:
        raw = seg["speaker"]
        if raw not in speaker_map:
            speaker_map[raw] = f"Speaker {counter}"
            counter += 1
        seg["speaker"] = speaker_map[raw]

    logger.info(f"Pyannote diarization: {len(speaker_map)} speakers")
    return segments


def _diarize_with_llm(segments: List[Dict], num_speakers: int = 0) -> Optional[List[Dict]]:
    """
    Use LLM to detect speaker changes from transcript text.
    The LLM analyzes conversational patterns: questions/answers, tone shifts,
    topic changes, pronouns ("I" vs "you"), etc.
    """
    import httpx

    llm_mode = os.getenv("LLM_MODE", "cloud")
    if llm_mode != "local":
        # Only use for local mode (Ollama) to avoid API costs
        # For cloud, pause-based is fine since cloud users likely have pyannote
        return None

    ollama_url = os.getenv("OLLAMA_URL", "http://ollama:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

    # Build transcript text with segment indices
    lines = []
    for i, seg in enumerate(segments):
        time_str = f"{int(seg.get('start', 0) // 60)}:{int(seg.get('start', 0) % 60):02d}"
        lines.append(f"[{i}] {time_str} {seg.get('text', '')}")

    transcript = "\n".join(lines)

    # Limit to first 3000 chars to keep prompt small and fast
    if len(transcript) > 3000:
        transcript = transcript[:3000] + "\n..."

    speaker_hint = f"There are {num_speakers} speakers." if num_speakers > 0 else "Detect how many speakers there are."

    prompt = f"""Analyze this meeting transcript and identify which segments belong to which speaker.
{speaker_hint}

Look for clues:
- Questions followed by answers = different speakers
- "I think..." / "We should..." = one speaker's opinion
- Topic or tone changes
- Greeting/response patterns

Transcript:
{transcript}

Reply with ONLY a JSON array of speaker assignments, one per segment index.
Example: [{{"index": 0, "speaker": 1}}, {{"index": 1, "speaker": 2}}, ...]
Keep speaker numbers consistent (same person = same number).
JSON only, no explanation:"""

    try:
        response = httpx.post(
            f"{ollama_url}/api/generate",
            json={
                "model": ollama_model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 2048},
            },
            timeout=120.0,
        )
        response.raise_for_status()
        text = response.json().get("response", "").strip()

        # Parse JSON from response (handle markdown code blocks)
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()

        assignments = json.loads(text)

        if not isinstance(assignments, list):
            return None

        # Apply assignments
        assignment_map = {}
        for item in assignments:
            if isinstance(item, dict) and "index" in item and "speaker" in item:
                assignment_map[item["index"]] = int(item["speaker"])

        if len(assignment_map) < len(segments) * 0.5:
            # LLM didn't assign enough segments
            return None

        for i, seg in enumerate(segments):
            speaker_num = assignment_map.get(i, 1)
            seg["speaker"] = f"Speaker {speaker_num}"

        speakers = set(s["speaker"] for s in segments)
        logger.info(f"LLM diarization: {len(speakers)} speakers detected from text patterns")
        return segments

    except (json.JSONDecodeError, httpx.HTTPError) as e:
        logger.warning(f"LLM diarization parse error: {e}")
        return None


def _diarize_by_pauses(segments: List[Dict], pause_threshold: float = 2.0, max_speakers: int = 2) -> List[Dict]:
    """
    Simple speaker assignment based on pauses between segments.
    Fallback when LLM and pyannote are unavailable.
    """
    if not segments:
        return segments

    current_speaker = 1

    for i, seg in enumerate(segments):
        if i == 0:
            seg["speaker"] = f"Speaker {current_speaker}"
            continue

        prev_end = segments[i - 1].get("end", 0)
        curr_start = seg.get("start", 0)
        pause = curr_start - prev_end

        if pause > pause_threshold:
            current_speaker = (current_speaker % max_speakers) + 1

        seg["speaker"] = f"Speaker {current_speaker}"

    speakers = set(s["speaker"] for s in segments)
    logger.info(f"Pause-based diarization: {len(speakers)} speakers (threshold={pause_threshold}s)")
    return segments
