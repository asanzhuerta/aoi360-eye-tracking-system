from pathlib import Path
import sys

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from aoi360_pipeline.failure_taxonomy_diagnostics import main


if __name__ == "__main__":
    main()
