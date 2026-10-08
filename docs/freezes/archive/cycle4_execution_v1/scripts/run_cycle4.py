"""Run a released cycle4 stage. Real API calls incur usage; no implicit retries."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.cycle4 import run
from utils.io import load_json

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage", choices=["preflight", "regression", "longitudinal"], required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--gate", type=Path)
    p.add_argument("--progress", action="store_true")
    a = p.parse_args()
    run(ROOT / f"configs/cycle4_{a.stage}_v1.json", a.output, gate_path=a.gate,
        progress=(lambda row: print(row, flush=True)) if a.progress else None)
    raise SystemExit(0 if load_json(a.output / "summary.json")["complete"] else 1)
