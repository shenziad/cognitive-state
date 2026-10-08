"""Export source-only review packet or replay a cycle4 run and seal its gate."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from evaluation.cycle4_audit import audit, review_packet, make_gate
from utils.io import save_json

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--review-packet", action="store_true")
    p.add_argument("--review", type=Path)
    a = p.parse_args()
    if a.output.exists():
        raise ValueError("Refuse to overwrite existing review/audit")
    result = review_packet(a.run) if a.review_packet else make_gate(a.run, a.review) if a.review else audit(a.run)
    save_json(a.output, result)
