"""Shared plumbing for the Hugging Face detectors (Grounding DINO and OWLv2).

Covers cache-first model loading, per-process model caching, and frame
preparation (RGB conversion plus optional downscaling for inference).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock

from aoi360_pipeline.cache_roots import (
    configure_huggingface_cache_environment,
    iter_huggingface_cache_roots,
    resolve_huggingface_snapshot_path,
)
from aoi360_pipeline.callbacks import LogCallback, emit_log
from aoi360_pipeline.detection_contract import get_frame_index


@dataclass(frozen=True)
class PreparedFrame:
    """Carry one frame through the batched inference pipeline."""

    frame_path: Path
    frame_index: int
    image: object
    target_size: tuple[int, int]  # (height, width) of the original frame


def _resampling_filter(image_module):
    try:
        return image_module.Resampling.BICUBIC
    except AttributeError:  # pragma: no cover - Pillow compatibility shim
        return image_module.BICUBIC


def resize_for_inference(image, image_module, max_width: int | None, max_height: int | None):
    """Downscale (never upscale) so the image fits within the given bounds."""
    width, height = image.size
    scale = 1.0
    if max_width is not None and max_width > 0 and width > max_width:
        scale = min(scale, max_width / width)
    if max_height is not None and max_height > 0 and height > max_height:
        scale = min(scale, max_height / height)
    if scale >= 1.0:
        return image

    resized_width = max(1, int(round(width * scale)))
    resized_height = max(1, int(round(height * scale)))
    return image.resize((resized_width, resized_height), _resampling_filter(image_module))


def prepare_frame(
    frame_path: Path,
    image_module,
    inference_max_width: int | None,
    inference_max_height: int | None,
) -> PreparedFrame:
    with image_module.open(frame_path) as image_handle:
        image = image_handle.convert("RGB")
        target_size = (image.height, image.width)
        inference_image = resize_for_inference(image, image_module, inference_max_width, inference_max_height)

    return PreparedFrame(
        frame_path=frame_path,
        frame_index=get_frame_index(frame_path),
        image=inference_image,
        target_size=target_size,
    )


def is_cuda_oom(exception: Exception, torch_module) -> bool:
    if hasattr(torch_module, "OutOfMemoryError") and isinstance(exception, torch_module.OutOfMemoryError):
        return True
    message = str(exception).lower()
    return "out of memory" in message and "cuda" in message


@dataclass
class PretrainedAssetCache:
    """Process-wide cache of processors and models for one detector backend."""

    display_name: str
    log_prefix: str
    _processors: dict[tuple[str], object] = field(default_factory=dict)
    _models: dict[tuple[str, str, str], object] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)

    def load_pretrained(self, factory, model_id: str, *, log_callback: LogCallback | None = None, **kwargs):
        """Prefer the local Hugging Face cache, then fall back to remote resolution.

        This keeps repeated preprocessing and benchmarking runs reproducible when
        the machine is offline, while still allowing first-time downloads.
        """
        primary_cache_root = configure_huggingface_cache_environment()
        local_failures: list[str] = []
        for cache_root in iter_huggingface_cache_roots():
            snapshot_path = resolve_huggingface_snapshot_path(model_id, cache_root)
            if snapshot_path is not None:
                try:
                    asset = factory.from_pretrained(str(snapshot_path), **{**kwargs, "local_files_only": True})
                    emit_log(log_callback, f"{self.log_prefix} Loaded assets from cached snapshot: {snapshot_path}")
                    return asset
                except Exception as local_exception:
                    local_failures.append(f"{snapshot_path} -> {local_exception}")

            try:
                asset = factory.from_pretrained(
                    model_id, **{**kwargs, "cache_dir": str(cache_root), "local_files_only": True}
                )
                emit_log(log_callback, f"{self.log_prefix} Loaded assets from local cache root: {cache_root}")
                return asset
            except Exception as local_exception:
                local_failures.append(f"{cache_root} -> {local_exception}")

        emit_log(
            log_callback,
            f"{self.log_prefix} Local cache lookup failed; falling back to remote resolution. "
            f"Tried: {' | '.join(local_failures)}",
        )
        try:
            return factory.from_pretrained(model_id, cache_dir=str(primary_cache_root), **kwargs)
        except Exception as remote_exception:
            raise RuntimeError(
                f"{self.display_name} could not be loaded from the local cache or from the remote Hugging Face "
                "repository. If the model was already downloaded before, check that the cache is still available."
            ) from remote_exception

    def get_processor(self, *, processor_factory, model_id: str, log_callback: LogCallback | None):
        key = (model_id,)
        with self._lock:
            cached = self._processors.get(key)
        if cached is not None:
            emit_log(log_callback, f"{self.log_prefix} Reusing cached processor for: {model_id}")
            return cached

        built = self.load_pretrained(processor_factory, model_id, log_callback=log_callback)
        with self._lock:
            return self._processors.setdefault(key, built)

    def get_model(
        self,
        *,
        model_factory,
        model_id: str,
        device: str,
        precision: str,
        model_kwargs: dict[str, object],
        log_callback: LogCallback | None,
    ):
        key = (model_id, device, precision)
        with self._lock:
            cached = self._models.get(key)
        if cached is not None:
            cached.eval()
            emit_log(log_callback, f"{self.log_prefix} Reusing cached model for: {model_id} [{device}, {precision}]")
            return cached

        built = self.load_pretrained(model_factory, model_id, log_callback=log_callback, **model_kwargs).to(device)
        with self._lock:
            model = self._models.setdefault(key, built)
        model.eval()
        return model
