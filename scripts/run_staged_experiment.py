"""Run an explicitly configured staged experiment; never retry or overwrite."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.staged import run_staged_experiment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New directory only")
    parser.add_argument("--progress", action="store_true")
    args = parser.parse_args()
    try:
        callback = (lambda event: print(json.dumps(event, ensure_ascii=False), flush=True)) if args.progress else None
        summary = run_staged_experiment(ROOT, args.config.resolve(), args.output.resolve(), callback)
    except (ValueError, RuntimeError, OSError) as exc:
        print(f"Run failed: {exc}", file=sys.stderr)
        return 1
    print(f"Saved {summary['status']} to {args.output.resolve()}")
    return 0 if summary["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
