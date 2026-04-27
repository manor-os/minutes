"""
Local summarization using Ollama (no API key needed).

Uses Map-Reduce pattern for long transcripts:
1. MAP: Split transcript into chunks, summarize each chunk
2. REDUCE: Combine chunk summaries into final summary

This keeps memory usage constant regardless of transcript length.
"""
import os
import json
import logging
from typing import Dict, Any, List, Optional, Tuple

import httpx

from .meeting_templates import get_template

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

# Chunk size for map-reduce (chars). Keep under 2000 for 3B models.
CHUNK_SIZE = 2000


def _ollama_generate(prompt: str, system: str = "", temperature: float = 0.3, max_tokens: int = 1024) -> str:
    """Call Ollama generate API."""
    try:
        response = httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "system": system,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 2048},
            },
            timeout=7200.0,
        )
        response.raise_for_status()
        return response.json().get("response", "")
    except Exception as e:
        logger.error(f"Ollama error: {e}")
        raise


def _split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE) -> List[str]:
    """Split text into chunks at sentence boundaries."""
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    while text:
        if len(text) <= chunk_size:
            chunks.append(text)
            break

        # Find a sentence break near the chunk boundary
        cut = chunk_size
        for sep in ['. ', '。', '! ', '? ', '\n']:
            idx = text.rfind(sep, 0, chunk_size)
            if idx > chunk_size * 0.5:  # Don't cut too early
                cut = idx + len(sep)
                break

        chunks.append(text[:cut].strip())
        text = text[cut:].strip()

    return chunks


def _map_reduce_summarize(transcript: str, prompt_template: str, system: str = "", max_tokens: int = 512) -> str:
    """
    Map-Reduce summarization:
    1. MAP — summarize each chunk independently
    2. REDUCE — combine chunk summaries into final output
    """
    chunks = _split_into_chunks(transcript)

    if len(chunks) == 1:
        # Short transcript — single pass
        prompt = f"{prompt_template}\n\nTranscript:\n{chunks[0]}"
        return _ollama_generate(prompt, system=system, max_tokens=max_tokens)

    logger.info(f"Map-Reduce: {len(chunks)} chunks from {len(transcript)} chars")

    # MAP phase — summarize each chunk
    chunk_summaries = []
    for i, chunk in enumerate(chunks):
        logger.info(f"  MAP chunk {i + 1}/{len(chunks)} ({len(chunk)} chars)")
        prompt = f"Briefly summarize this meeting section in 2-3 sentences. Keep key facts only.\n\nSection {i + 1}:\n{chunk}\n\nBrief summary:"
        summary = _ollama_generate(prompt, system="Be very concise. 2-3 sentences max.", max_tokens=150)
        if summary.strip():
            chunk_summaries.append(summary.strip())

    if not chunk_summaries:
        return ""

    # REDUCE phase — combine into final summary
    combined = "\n\n".join(f"Part {i + 1}: {s}" for i, s in enumerate(chunk_summaries))
    logger.info(f"  REDUCE: combining {len(chunk_summaries)} summaries ({len(combined)} chars)")

    reduce_prompt = f"""{prompt_template}

Here are summaries of each section of the meeting:

{combined}

Now write a single cohesive summary combining all sections:"""

    return _ollama_generate(reduce_prompt, system=system, max_tokens=max_tokens)


def summarize_local(transcript: str, template_id: str = "general") -> Tuple[str, Dict[str, int]]:
    """Generate meeting summary using Map-Reduce pattern."""
    template = get_template(template_id)
    system = "You are a professional meeting assistant. Generate concise, well-structured meeting notes."

    result = _map_reduce_summarize(
        transcript,
        prompt_template=template['summary_prompt'],
        system=system,
        max_tokens=1024,
    )

    usage = {"prompt_tokens": len(transcript.split()), "completion_tokens": len(result.split()), "total_tokens": 0}
    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    return result, usage


def extract_key_points_local(transcript: str, template_id: str = "general") -> Tuple[List[str], Dict[str, int]]:
    """Extract key points using Map-Reduce."""
    template = get_template(template_id)
    chunks = _split_into_chunks(transcript)

    all_points = []

    if len(chunks) <= 2:
        # Short — single pass
        prompt = f"""{template['key_points_prompt']}

Transcript:
{transcript[:4000]}

Return ONLY a JSON array like: ["point 1", "point 2"]"""
        result = _ollama_generate(prompt, max_tokens=512)
        all_points = _parse_json_array(result)
    else:
        # MAP — extract points from each chunk
        for i, chunk in enumerate(chunks):
            prompt = f"Extract 2-3 key points from this meeting section. Return ONLY a JSON array of strings.\n\nSection:\n{chunk}\n\nJSON array:"
            result = _ollama_generate(prompt, max_tokens=256)
            points = _parse_json_array(result)
            all_points.extend(points)

        # REDUCE — deduplicate and pick top points
        if len(all_points) > 5:
            combined = "\n".join(f"- {p}" for p in all_points)
            prompt = f"These key points were extracted from a meeting. Remove duplicates and pick the 5-8 most important ones. Return ONLY a JSON array of strings.\n\nPoints:\n{combined}\n\nJSON array:"
            result = _ollama_generate(prompt, max_tokens=512)
            final_points = _parse_json_array(result)
            if final_points:
                all_points = final_points

    return all_points[:10], {"total_tokens": len(transcript.split()) + sum(len(p.split()) for p in all_points)}


def extract_action_items_local(transcript: str, template_id: str = "general") -> Tuple[List[Dict], Dict[str, int]]:
    """Extract action items using Map-Reduce."""
    template = get_template(template_id)
    chunks = _split_into_chunks(transcript)

    all_items = []

    if len(chunks) <= 2:
        # Short — single pass
        prompt = f"""{template['action_items_prompt']}

Transcript:
{transcript[:4000]}

Return ONLY a JSON array like: [{{"description": "...", "assignee": "...", "deadline": "..."}}]"""
        result = _ollama_generate(prompt, max_tokens=512)
        all_items = _parse_json_array(result, expect_objects=True)
    else:
        # MAP — extract items from each chunk
        for i, chunk in enumerate(chunks):
            prompt = f'Extract action items from this meeting section. Return ONLY a JSON array of objects with "description", "assignee", "deadline" keys.\n\nSection:\n{chunk}\n\nJSON array:'
            result = _ollama_generate(prompt, max_tokens=256)
            items = _parse_json_array(result, expect_objects=True)
            all_items.extend(items)

    return all_items, {"total_tokens": len(transcript.split()) + len(str(all_items).split())}


def _parse_json_array(text: str, expect_objects: bool = False) -> List:
    """Parse JSON array from LLM output, handling common formatting issues."""
    text = text.strip()

    # Handle markdown code blocks
    if "```" in text:
        parts = text.split("```")
        for part in parts[1:]:
            if part.startswith("json"):
                part = part[4:]
            part = part.strip()
            if part.startswith("["):
                text = part
                break

    # Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Find JSON array in text
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(text[start:end + 1])
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # Fallback: parse lines as strings
    if not expect_objects:
        points = [line.strip().lstrip("- *0123456789.)\u2022").strip() for line in text.split("\n") if line.strip() and len(line.strip()) > 5]
        return [p for p in points if p]

    return []


def is_ollama_available() -> bool:
    """Check if Ollama is running and model is available."""
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        return r.status_code == 200
    except Exception:
        return False
