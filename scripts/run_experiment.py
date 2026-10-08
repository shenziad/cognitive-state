"""Run exp001 from any working directory, without an editable install."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluation.runner import run_experiment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "experiments/exp001_context_equivalence/config.json")
    parser.add_argument("--output", type=Path, default=None, help="A new directory; existing directories are never overwritten")
    parser.add_argument("--progress", action="store_true", help="Print sanitized per-cell progress")
    args = parser.parse_args()
    output = args.output or ROOT / "results/raw/exp001" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    try:
        callback = (lambda event: print(json.dumps(event), flush=True)) if args.progress else None
        summary = run_experiment(ROOT, args.config.resolve(), output.resolve(), progress=callback)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Run failed: {exc}", file=sys.stderr)
        return 1
    print(f"Saved {summary['evidence_type']} to {output.resolve()}")
    return 1 if any(s["errors"] for s in summary["conditions"].values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
