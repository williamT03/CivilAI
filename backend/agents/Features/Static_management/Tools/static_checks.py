from __future__ import annotations

from pathlib import Path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def read_existing(paths: list[Path]) -> str:
    """Read and combine every existing file from a static check target list."""

    return "\n".join(read_text(path) for path in paths if path.exists())


def auth_source_files(repo_root: Path) -> list[Path]:
    """Return auth implementation files from User management."""

    feature_dir = repo_root / "backend" / "Features" / "User_management"
    tool_dir = feature_dir / "Tools"
    return [
        feature_dir / "auth_run.py",
        tool_dir / "auth.py",
        tool_dir / "models.py",
        tool_dir / "schemas.py",
        tool_dir / "tables.py",
        tool_dir / "database.py",
        tool_dir / "routes.py",
    ]


def relative_existing_paths(repo_root: Path, paths: list[Path]) -> list[str]:
    return [path.relative_to(repo_root).as_posix() for path in paths if path.exists()]


def missing_strings(text: str, required: list[str]) -> list[str]:
    return [item for item in required if item not in text]
