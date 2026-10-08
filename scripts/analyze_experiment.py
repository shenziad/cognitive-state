"""Export a descriptive JSON/Markdown report from a frozen experiment run."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.analysis import analyze_run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--diagnostic", type=Path)
    args = parser.parse_args()
    report = analyze_run(args.run, args.output, args.diagnostic)
    print(f"Saved {report['status']} analysis to {args.output.resolve()}")


if __name__ == "__main__":
    main()
