from __future__ import annotations

from pathlib import Path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def read_existing(paths: list[Path]) -> str:
    """Read and combine every existing file from a static check target list."""

    return "\n".join(read_text(path) for path in paths if path.exists())


def auth_source_files(repo_root: Path) -> list[Path]:
    """Return auth implementation files for both legacy and package layouts."""

    legacy_file = repo_root / "backend" / "app" / "auth.py"
    package_dir = repo_root / "backend" / "app" / "auth"
    package_files = [
        package_dir / "__init__.py",
        package_dir / "models.py",
        package_dir / "schemas.py",
        package_dir / "tables.py",
        package_dir / "database.py",
        package_dir / "routes.py",
    ]
    return [legacy_file, *package_files]


def relative_existing_paths(repo_root: Path, paths: list[Path]) -> list[str]:
    return [path.relative_to(repo_root).as_posix() for path in paths if path.exists()]


def missing_strings(text: str, required: list[str]) -> list[str]:
    return [item for item in required if item not in text]
