#!/usr/bin/env python3
"""Reset tracked project files from GitHub while preserving runtime data.

This is the safer server reset path for CivilAI:
- tracked files are reset to the selected GitHub branch,
- untracked non-ignored files are removed,
- ignored runtime files such as `.env` and `backend/Data` are preserved.

The script intentionally does not run `git clean -x` and does not remove Docker
volumes. That keeps parsed PDFs, Chroma data, SQLite files, uploads, and local
environment files intact.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


PRESERVED_PATHS = (
    ".env",
    "backend/Data",
    "Data",
    "chroma_db",
    "backend/agents/reports",
)


def run(command: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess:
    print(f"\n$ {' '.join(command)}")
    return subprocess.run(command, cwd=cwd, check=check)


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise SystemExit(f"{name} was not found on PATH.")


def confirm_or_exit(args: argparse.Namespace, repo_root: Path) -> None:
    if args.yes:
        return

    print("This will reset tracked project files to GitHub.")
    print(f"Repository: {repo_root}")
    print(f"Target: {args.remote}/{args.branch}")
    print("Preserved ignored runtime paths:")
    for path in PRESERVED_PATHS:
        print(f"  - {path}")
    print("\nLocal tracked changes will be discarded.")

    answer = input("Type RESET_FILES to continue: ").strip()
    if answer != "RESET_FILES":
        print("Aborted.")
        raise SystemExit(1)


def docker_compose_base(repo_root: Path) -> list[str] | None:
    if shutil.which("docker") is None:
        return None

    compose_files = [
        repo_root / "docker-compose.yml",
        repo_root / "docker-compose.server.yml",
    ]
    existing = [path for path in compose_files if path.exists()]
    if not existing:
        return None

    command = ["docker", "compose"]
    for compose_file in existing:
        command.extend(["-f", str(compose_file)])
    return command


def snapshot_preserved_paths(repo_root: Path) -> None:
    print("\nPreserved path check:")
    for relative_path in PRESERVED_PATHS:
        path = repo_root / relative_path
        status = "exists" if path.exists() else "not found"
        print(f"  {relative_path}: {status}")


def create_env_backup(repo_root: Path) -> None:
    env_path = repo_root / ".env"
    if not env_path.exists():
        return

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = repo_root / "backend" / "Data" / "server_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f".env.backup.{timestamp}"
    shutil.copy2(env_path, backup_path)
    print(f"\nBacked up .env to {backup_path.relative_to(repo_root)}")


def stop_services(repo_root: Path, args: argparse.Namespace) -> None:
    if args.no_docker_stop:
        return

    compose = docker_compose_base(repo_root)
    if compose is None:
        print("\nDocker Compose files or docker were not found; skipping service stop.")
        return

    run([*compose, "down", "--remove-orphans"], repo_root)


def reset_files(repo_root: Path, args: argparse.Namespace) -> None:
    require_tool("git")
    run(["git", "fetch", args.remote, args.branch, "--prune"], repo_root)
    run(["git", "reset", "--hard", f"{args.remote}/{args.branch}"], repo_root)

    # `git clean -fd` removes untracked non-ignored files only. It preserves
    # ignored runtime files such as `.env`, `backend/Data`, and reports.
    run(["git", "clean", "-fd"], repo_root)


def start_services(repo_root: Path, args: argparse.Namespace) -> None:
    if not args.start and not args.rebuild:
        return

    compose = docker_compose_base(repo_root)
    if compose is None:
        print("\nDocker Compose files or docker were not found; skipping service start.")
        return

    if args.rebuild:
        run([*compose, "build", "--pull"], repo_root)
    if args.start:
        run([*compose, "up", "-d"], repo_root)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset CivilAI source files from GitHub without deleting .env or parsed data."
    )
    parser.add_argument("--remote", default="origin", help="Git remote to fetch from.")
    parser.add_argument("--branch", default="main", help="Git branch to reset to.")
    parser.add_argument("--repo", type=Path, default=repo_root_from_script(), help="Repo root.")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
    parser.add_argument(
        "--no-docker-stop",
        action="store_true",
        help="Do not stop Docker Compose services before resetting files.",
    )
    parser.add_argument("--rebuild", action="store_true", help="Rebuild Docker images after reset.")
    parser.add_argument("--start", action="store_true", help="Start Docker Compose after reset.")
    parser.add_argument(
        "--skip-env-backup",
        action="store_true",
        help="Do not create a timestamped .env backup before resetting.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo.resolve()

    if not (repo_root / ".git").exists():
        raise SystemExit(f"{repo_root} does not look like a git repository.")

    confirm_or_exit(args, repo_root)
    snapshot_preserved_paths(repo_root)
    if not args.skip_env_backup:
        create_env_backup(repo_root)
    stop_services(repo_root, args)
    reset_files(repo_root, args)
    snapshot_preserved_paths(repo_root)
    start_services(repo_root, args)

    print("\nDone. Tracked files now match GitHub; ignored runtime data was preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
