"""Explicit next-stage CLI; real model calls require a frozen cycle5 release."""
from pathlib import Path
import argparse
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.exp004_mechanism.runtime_v2 import diagnostic,prepare_run,execute_run,source_packet,audit_run
from utils.io import save_json

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--phase',choices=['diagnostic','prepare','review_packet','execute','audit'],required=True)
    p.add_argument('--config',type=Path)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--review',type=Path)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    if a.phase=='diagnostic': diagnostic(a.config,a.run.resolve())
    elif a.phase=='prepare': prepare_run(a.config,a.run.resolve())
    elif a.phase=='execute': execute_run(a.run.resolve(),a.review)
    else:
        assert a.output and not a.output.exists()
        save_json(a.output,source_packet(a.run.resolve()) if a.phase=='review_packet' else audit_run(a.run.resolve()))
