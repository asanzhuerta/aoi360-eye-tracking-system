"""Progress and log callbacks shared by every pipeline stage."""

from __future__ import annotations

from collections.abc import Callable

ProgressCallback = Callable[[int, int, str], None]
StageProgressCallback = Callable[[str, int, int, str], None]
LogCallback = Callable[[str], None]


def emit_log(log_callback: LogCallback | None, message: str) -> None:
    """Send a message to the callback, or print it when none is given."""
    if log_callback is not None:
        log_callback(message)
    else:
        print(message)


def emit_progress(
    progress_callback: ProgressCallback | None,
    current: int,
    total: int,
    message: str,
) -> None:
    if progress_callback is not None:
        progress_callback(current, total, message)
