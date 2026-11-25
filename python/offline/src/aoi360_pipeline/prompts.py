"""Prompt and label text handling shared by detectors and AOI builders."""

from __future__ import annotations

import json
import re
from pathlib import Path

# Detector prompts are class lists separated by commas, new lines, or a full
# stop followed by whitespace (Grounding DINO's "person. car." convention).
_CLASS_PROMPT_SEPARATORS = re.compile(r"[,\n]+|\.(?:\s|$)")
# Prompt vocabulary used to canonicalise detector labels.
_VOCABULARY_SEPARATORS = re.compile(r"[.;\n\r]+")
_WHITESPACE = re.compile(r"\s+")


def normalize_text_fragment(value: str) -> str:
    return _WHITESPACE.sub(" ", str(value).replace("_", " ").strip().lower())


def split_class_prompt(text_prompt: str, detector_name: str) -> list[str]:
    """Split a detector prompt into unique class names, keeping their first spelling."""
    classes: list[str] = []
    seen: set[str] = set()
    for token in _CLASS_PROMPT_SEPARATORS.split(text_prompt):
        token = token.strip()
        if not token or token.lower() in seen:
            continue
        seen.add(token.lower())
        classes.append(token)

    if not classes:
        raise ValueError(
            f"text_prompt must contain at least one non-empty class prompt for {detector_name}."
        )
    return classes


def parse_prompt_vocabulary(prompt: str) -> list[str]:
    segments = (normalize_text_fragment(segment) for segment in _VOCABULARY_SEPARATORS.split(str(prompt)))
    return [segment for segment in segments if segment]


def parse_label_filters(values: list[str] | None) -> set[str]:
    if not values:
        return set()
    return {value.strip().lower() for value in values if value and value.strip()}


def tokenize_label(value: str) -> set[str]:
    return {token for token in normalize_text_fragment(value).split(" ") if token}


def canonicalize_label_to_prompt(label: str, prompt: str) -> str:
    """Map a free-text detector label onto the closest phrase of its prompt.

    Candidates are ranked by: containment, token-overlap ratio, overlap count,
    candidate length, and earlier position in the prompt.
    """
    normalized_label = normalize_text_fragment(label)
    vocabulary = parse_prompt_vocabulary(prompt)
    if not normalized_label or not vocabulary or normalized_label in vocabulary:
        return normalized_label

    label_tokens = tokenize_label(normalized_label)
    if not label_tokens:
        return normalized_label

    best_candidate = normalized_label
    best_score: tuple[int, float, int, int, int] | None = None
    for prompt_index, candidate in enumerate(vocabulary):
        candidate_tokens = tokenize_label(candidate)
        overlap = len(label_tokens & candidate_tokens)
        if overlap <= 0:
            continue

        score = (
            1 if candidate in normalized_label or normalized_label in candidate else 0,
            overlap / max(len(label_tokens), len(candidate_tokens)),
            overlap,
            len(candidate_tokens),
            -prompt_index,
        )
        if best_score is None or score > best_score:
            best_candidate = candidate
            best_score = score

    return best_candidate


def _add_prompt_override(overrides: dict[str, str], video_id: str, prompt: str, source: str) -> None:
    video_id = video_id.strip()
    prompt = prompt.strip()
    if not video_id:
        raise ValueError(f"Video id cannot be empty in {source}.")
    if not prompt:
        raise ValueError(f"Prompt override for '{video_id}' cannot be empty.")
    overrides[video_id] = prompt


def parse_video_prompt_overrides(
    *,
    prompt_overrides: list[str] | None = None,
    prompt_file: str | Path | None = None,
) -> dict[str, str]:
    """Resolve per-video prompts from a JSON file and/or ``video_id=prompt`` pairs.

    CLI pairs take precedence over the file.
    """
    overrides: dict[str, str] = {}

    if prompt_file is not None:
        prompt_file_path = Path(prompt_file).resolve()
        if not prompt_file_path.exists():
            raise FileNotFoundError(f"Video prompt mapping file not found: {prompt_file_path}")

        mapping = json.loads(prompt_file_path.read_text(encoding="utf-8"))
        if not isinstance(mapping, dict):
            raise ValueError("The video prompt mapping file must contain a JSON object of video_id -> prompt.")
        for video_id, prompt in mapping.items():
            if not isinstance(video_id, str) or not isinstance(prompt, str):
                raise ValueError("Every video prompt mapping entry must be a string key and a string value.")
            _add_prompt_override(overrides, video_id, prompt, "the video prompt mapping file")

    for override in prompt_overrides or []:
        if "=" not in override:
            raise ValueError("Each --video-prompt override must follow the format video_id=prompt.")
        video_id, prompt = override.split("=", 1)
        _add_prompt_override(overrides, video_id, prompt, "--video-prompt overrides")

    return overrides
