from __future__ import annotations

"""Inspect the local PyTorch runtime and derive sensible preprocessing defaults."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TorchRuntimeSummary:
    """Compact snapshot of the currently available PyTorch execution backend."""

    torch_version: str
    cuda_available: bool
    cuda_version: str | None
    device_count: int
    device_name: str
    total_memory_gb: float | None
    default_device: str
    recommended_precision: str
    recommended_batch_size: int
    recommended_preload_workers: int

    @property
    def short_label(self) -> str:
        if self.cuda_available:
            memory_label = f"{self.total_memory_gb:.1f} GB" if self.total_memory_gb is not None else "unknown VRAM"
            return (
                f"CUDA | {self.device_name} | torch {self.torch_version} | "
                f"CUDA {self.cuda_version or 'unknown'} | {memory_label}"
            )

        return f"CPU | torch {self.torch_version}"


def inspect_torch_runtime(torch_module=None) -> TorchRuntimeSummary:
    """Return the available backend plus conservative defaults for preprocessing."""

    if torch_module is None:
        try:
            import torch as imported_torch
        except Exception:
            return TorchRuntimeSummary(
                torch_version="not-installed",
                cuda_available=False,
                cuda_version=None,
                device_count=0,
                device_name="CPU",
                total_memory_gb=None,
                default_device="cpu",
                recommended_precision="fp32",
                recommended_batch_size=2,
                recommended_preload_workers=2,
            )

        torch_module = imported_torch

    cuda_available = bool(torch_module.cuda.is_available())
    torch_version = str(getattr(torch_module, "__version__", "unknown"))
    cuda_version = str(getattr(torch_module.version, "cuda", "")) or None

    if not cuda_available:
        return TorchRuntimeSummary(
            torch_version=torch_version,
            cuda_available=False,
            cuda_version=cuda_version,
            device_count=0,
            device_name="CPU",
            total_memory_gb=None,
            default_device="cpu",
            recommended_precision="fp32",
            recommended_batch_size=2,
            recommended_preload_workers=2,
        )

    device_count = int(torch_module.cuda.device_count())
    device_name = str(torch_module.cuda.get_device_name(0))
    properties = torch_module.cuda.get_device_properties(0)
    total_memory_gb = float(properties.total_memory) / float(1024 ** 3)

    if total_memory_gb >= 10.0:
        recommended_batch_size = 8
        recommended_preload_workers = 4
    elif total_memory_gb >= 6.0:
        recommended_batch_size = 6
        recommended_preload_workers = 4
    elif total_memory_gb >= 4.5:
        # 4-5 GB laptop GPUs tend to OOM with Grounding DINO when using the
        # old automatic batch size of 4, especially on 1920x960 inference
        # inputs. Keep the default conservative so the GUI works out of the box.
        recommended_batch_size = 2
        recommended_preload_workers = 2
    else:
        recommended_batch_size = 1
        recommended_preload_workers = 1

    return TorchRuntimeSummary(
        torch_version=torch_version,
        cuda_available=True,
        cuda_version=cuda_version,
        device_count=device_count,
        device_name=device_name,
        total_memory_gb=total_memory_gb,
        default_device="cuda",
        recommended_precision="fp16",
        recommended_batch_size=recommended_batch_size,
        recommended_preload_workers=recommended_preload_workers,
    )
