"""Run the explicitly bounded four-handoff pilot; existing output is never replaced."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.longitudinal import run_longitudinal  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/exp003_longitudinal_pilot.json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--progress", action="store_true")
    args = parser.parse_args()
    output = args.output or ROOT / "results/raw/exp003" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    callback = (lambda event: print(json.dumps(event), flush=True)) if args.progress else None
    try:
        summary = run_longitudinal(ROOT, args.config.resolve(), output.resolve(), progress=callback)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Run failed: {exc}", file=sys.stderr)
        return 1
    print(f"Saved {summary['evidence_type']} to {output.resolve()}")
    return int(not summary["performance_evaluation_available"])


if __name__ == "__main__":
    raise SystemExit(main())
