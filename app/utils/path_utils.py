from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
UPLOAD_ROOT = PROJECT_ROOT / "uploaded"
OUTPUT_ROOT = PROJECT_ROOT / "output"


def ensure_session_dir(thread_id: str) -> Path:
    """Return and create this task's output directory."""
    session_dir = OUTPUT_ROOT / thread_id
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def ensure_upload_dir(thread_id: str) -> Path:
    """Return and create this task's upload directory."""
    upload_dir = UPLOAD_ROOT / thread_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def safe_join(base: Path, *parts: str) -> Path:
    """Join paths while preventing traversal outside the base directory."""
    base_path = base.resolve()
    target = (base_path / Path(*parts)).resolve()

    try:
        target.relative_to(base_path)
    except ValueError as exc:
        raise ValueError(f"Path traversal is not allowed: {target}") from exc

    return target
