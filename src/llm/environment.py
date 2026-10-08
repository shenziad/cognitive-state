"""Load project-local credentials without exposing or overriding the environment."""

from pathlib import Path


def load_project_env(root: Path) -> bool:
    path = root / ".env"
    if not path.is_file():
        return False
    try:
        from dotenv import load_dotenv
    except ImportError:
        raise ValueError("Install the api optional dependencies to load .env") from None
    load_dotenv(path, override=False, encoding="utf-8-sig")
    return True
