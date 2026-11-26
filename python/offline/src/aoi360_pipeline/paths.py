"""Repository layout helpers shared by every entry point."""

from __future__ import annotations

from pathlib import Path


def find_repo_root(start: str | Path | None = None) -> Path:
    """Walk up from ``start`` (default: cwd) until a folder holding python/ and unity/ is found."""
    current = Path(start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "python").exists() and (candidate / "unity").exists():
            return candidate
    return current


def resolve_repo_path(repo_root: Path, candidate: str | Path) -> Path:
    """Resolve a repository-relative path; absolute paths are returned unchanged."""
    path = Path(candidate)
    if path.is_absolute():
        return path
    return (repo_root / path).resolve()


def default_runtime_pack_path(manifest_path: Path) -> Path:
    """``<video>_aoi_sequence_manifest.json`` -> ``<video>_aoi_sequence_rgb24.bin``."""
    return manifest_path.with_name(manifest_path.stem.replace("_manifest", "_rgb24") + ".bin")
