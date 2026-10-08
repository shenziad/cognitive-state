"""Freeze a full second preflight on new labels after protocol debugging.

These use the same six templates; they are not an independently designed test set.
Previously inspected regression and chain inputs are copied without content changes.
"""
from pathlib import Path
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
if __name__ == "__main__":
    source = ROOT / "datasets/cycle3_v03"
    destination = ROOT / "datasets/cycle3_v03r2"
    destination.mkdir(exist_ok=False)
    data = (source / "preflight.json").read_text(encoding="utf-8")
    for old, new in (("pre03_", "pre03r2_"), ("amber", "silver"), ("violet", "gold"), ("birch", "willow"), ("preflight-v0.3", "preflight-v0.3r2")):
        data = data.replace(old, new)
    json.loads(data)
    (destination / "preflight.json").write_text(data, encoding="utf-8", newline="\n")
    for name in ("regression.json", "longitudinal.json"):
        shutil.copyfile(source / name, destination / name)
    (destination / "README.md").write_text("# Revision 2 inputs\n\nPreflight reuses six development templates with new labels after observing revision 1 failures. Not an independent held-out set. Regression and longitudinal data are byte-identical to revision 1, and were not called while fixing the protocol.\n", encoding="utf-8")
    print(destination)
