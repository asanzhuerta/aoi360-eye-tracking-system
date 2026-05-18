from __future__ import annotations

"""Shared cache locations for local detector assets.

The offline pipeline should keep heavyweight model downloads inside the
repository-local ``.cache`` directory so repeated experiments stay reproducible
and do not depend on user-profile caches that vary across machines.
"""

import os
from pathlib import Path


def get_repo_cache_root() -> Path:
    return Path(__file__).resolve().parents[4] / ".cache"


def get_huggingface_cache_root() -> Path:
    return get_repo_cache_root() / "huggingface"


def get_user_huggingface_cache_root() -> Path:
    return Path.home() / ".cache" / "huggingface"


def get_huggingface_hub_cache_root() -> Path:
    return get_huggingface_cache_root() / "hub"


def get_transformers_cache_root() -> Path:
    return get_huggingface_cache_root() / "transformers"


def configure_huggingface_cache_environment() -> Path:
    cache_root = get_huggingface_cache_root()
    hub_root = get_huggingface_hub_cache_root()
    transformers_root = get_transformers_cache_root()

    cache_root.mkdir(parents=True, exist_ok=True)
    hub_root.mkdir(parents=True, exist_ok=True)
    transformers_root.mkdir(parents=True, exist_ok=True)

    os.environ.setdefault("HF_HOME", str(cache_root))
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hub_root))
    os.environ.setdefault("TRANSFORMERS_CACHE", str(transformers_root))
    return cache_root


def iter_huggingface_cache_roots() -> tuple[Path, ...]:
    candidates: list[Path] = [get_huggingface_cache_root()]
    env_cache_root = os.environ.get("HF_HOME")
    if env_cache_root:
        candidates.append(Path(env_cache_root))
    candidates.append(get_user_huggingface_cache_root())

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        normalized_candidate = candidate.resolve()
        if normalized_candidate in seen:
            continue
        seen.add(normalized_candidate)
        unique_candidates.append(candidate)

    return tuple(unique_candidates)


def resolve_huggingface_snapshot_path(model_id: str, cache_root: Path) -> Path | None:
    model_cache_name = f"models--{model_id.replace('/', '--')}"
    candidate_hub_roots = [cache_root / "hub", cache_root]

    for hub_root in candidate_hub_roots:
        model_root = hub_root / model_cache_name
        snapshots_root = model_root / "snapshots"
        if not snapshots_root.exists():
            continue

        main_ref = model_root / "refs" / "main"
        if main_ref.exists():
            snapshot_name = main_ref.read_text(encoding="utf-8").strip()
            snapshot_path = snapshots_root / snapshot_name
            if snapshot_path.exists():
                return snapshot_path

        snapshot_directories = sorted([path for path in snapshots_root.iterdir() if path.is_dir()])
        if snapshot_directories:
            return snapshot_directories[-1]

    return None


def get_ultralytics_cache_root() -> Path:
    return get_repo_cache_root() / "ultralytics"
