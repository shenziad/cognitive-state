"""Verify and restore archived experiment records without replacing existing data."""

import argparse
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = ROOT / "results/archives/experiments_20261008.zip"


def digest(path):
    result = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def target_path(destination, name):
    relative = PurePosixPath(name)
    if (relative.is_absolute() or relative.as_posix() != name or
            "\\" in name or ":" in name or ".." in relative.parts or
            relative.parts[:2] != ("results", "raw") or
            "__pycache__" in relative.parts or relative.suffix not in {".json", ".txt", ".py", ".md"}):
        raise ValueError("Archive member has an invalid record path")
    target = destination.joinpath(*relative.parts)
    if not target.resolve().is_relative_to(destination / "results/raw"):
        raise ValueError("Archive member escapes the intended raw directory")
    return target


def restore(archive, destination, verify_only=False):
    archive, destination = archive.resolve(), destination.resolve()
    manifest = json.loads(archive.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    if manifest["format"] != "cognitive-state-record-archive-v1" or digest(archive) != manifest["archive_sha256"]:
        raise ValueError("Archive identity or SHA256 mismatch")
    expected = {entry["path"]: entry for entry in manifest["files"]}
    if len(expected) != len(manifest["files"]):
        raise ValueError("Manifest repeats a record path")
    pending = []
    with ZipFile(archive) as bundle:
        entries = bundle.infolist()
        if len(entries) != len(expected) or {i.filename for i in entries} != set(expected):
            raise ValueError("Archive and manifest member sets differ")
        total = 0
        # Validate every member and all destination conflicts before writing.
        for info in entries:
            target = target_path(destination, info.filename)
            reference = expected[info.filename]
            if info.is_dir() or (info.external_attr >> 16) & 0o170000 not in (0, 0o100000):
                raise ValueError("Archive contains a nonregular record")
            if info.file_size != reference["bytes"]:
                raise ValueError("Record length differs from manifest")
            result = sha256()
            with bundle.open(info) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    result.update(chunk)
            if result.hexdigest() != reference["sha256"]:
                raise ValueError("Record SHA256 mismatch")
            total += info.file_size
            if not verify_only:
                if target.exists():
                    if not target.is_file() or digest(target) != reference["sha256"]:
                        raise ValueError("Existing record differs; refusing to replace: " + info.filename)
                else:
                    pending.append((info, target))
        if total != manifest["total_record_bytes"]:
            raise ValueError("Total uncompressed length differs")
        for info, target in pending:
            target.parent.mkdir(parents=True, exist_ok=True)
            target_path(destination, info.filename)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=target.parent, prefix=".record-restore-", delete=False) as stream:
                    temporary = Path(stream.name)
                    with bundle.open(info) as source:
                        shutil.copyfileobj(source, stream)
                if target.exists():
                    raise ValueError("Record appeared during restoration; refusing to replace")
                temporary.rename(target)
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()
    return {"archive_verified": True, "record_files": len(expected),
            "record_bytes": total, "restored_files": len(pending),
            "verify_only": verify_only}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=DEFAULT_ARCHIVE)
    parser.add_argument("--destination", type=Path, default=ROOT)
    parser.add_argument("--verify-only", action="store_true")
    options = parser.parse_args()
    print(json.dumps(restore(options.archive, options.destination, options.verify_only)))
