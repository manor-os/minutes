"""
Robust parsing of LLM output that is expected to be a JSON array.

Handles the formatting issues LLMs commonly introduce: markdown code fences,
prose around the array, truncated output (max_tokens cutoffs), and plain
bullet-list answers when the model ignores the JSON instruction entirely.
"""
import json
import re
from typing import List

_FENCE_OR_BRACKET_LINE = re.compile(r"^(```\w*|```|\[|\]|\{|\})\s*,?\s*$")
_JSON_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')


def parse_json_array(text: str, expect_objects: bool = False) -> List:
    """Parse a JSON array from LLM output, handling common formatting issues."""
    text = (text or "").strip()
    if not text:
        return []

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

    # Salvage a truncated/malformed array of strings: pull out the individual
    # JSON string literals (e.g. output cut off by max_tokens before the "]")
    if not expect_objects and start != -1:
        salvaged = []
        for match in _JSON_STRING.finditer(text[start:]):
            try:
                salvaged.append(json.loads(f'"{match.group(1)}"'))
            except json.JSONDecodeError:
                continue
        salvaged = [s.strip() for s in salvaged if s and s.strip()]
        if salvaged:
            return salvaged

    # Fallback: parse lines as strings, skipping fence/bracket scaffolding
    if not expect_objects:
        points = []
        for line in text.split("\n"):
            line = line.strip()
            if not line or _FENCE_OR_BRACKET_LINE.match(line):
                continue
            line = re.sub(r"^(?:[-*•]\s*|\d+[.)]\s+)", "", line).rstrip(",").strip()
            if line.startswith('"') and line.endswith('"') and len(line) > 1:
                line = line[1:-1]
            if len(line) > 5:
                points.append(line)
        return points

    return []
