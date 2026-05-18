from __future__ import annotations

"""Prefetch detector assets into the repo-local cache."""

import argparse

from aoi360_pipeline.detectors import SUPPORTED_DETECTORS, normalize_detector_name, resolve_default_model_id


def prefetch_detector_assets(
    *,
    detector: str,
    model_id: str | None = None,
    text_prompt: str = "person. face. bottle. screen. product.",
    precision: str = "auto",
) -> dict[str, str]:
    detector_key = normalize_detector_name(detector)
    resolved_model_id = model_id or resolve_default_model_id(detector_key)

    if detector_key == "grounding_dino":
        from aoi360_pipeline.grounding_dino import prefetch_model_assets

        return prefetch_model_assets(model_id=resolved_model_id, precision=precision)

    if detector_key == "owlv2":
        from aoi360_pipeline.owlv2 import prefetch_model_assets

        return prefetch_model_assets(model_id=resolved_model_id, precision=precision)

    if detector_key == "yolo_world":
        from aoi360_pipeline.yolo_world import prefetch_model_assets

        return prefetch_model_assets(model_id=resolved_model_id, text_prompt=text_prompt)

    raise AssertionError(f"Unexpected detector key: {detector_key}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download detector assets into the repo-local cache and warm the in-process cache."
    )
    parser.add_argument(
        "--detector",
        default="grounding_dino",
        choices=sorted(SUPPORTED_DETECTORS),
        help="Detector backend whose assets should be prefetched.",
    )
    parser.add_argument(
        "--model-id",
        default=None,
        help="Optional override for the backend-specific pretrained model identifier.",
    )
    parser.add_argument(
        "--text-prompt",
        default="person. face. bottle. screen. product.",
        help="Prompt used when prefetching YOLO-World class embeddings.",
    )
    parser.add_argument(
        "--precision",
        default="auto",
        choices=["auto", "fp16", "fp32"],
        help="Precision used when warming transformer-based detectors in memory.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    summary = prefetch_detector_assets(
        detector=args.detector,
        model_id=args.model_id,
        text_prompt=args.text_prompt,
        precision=args.precision,
    )

    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
