#!/usr/bin/env python3
"""Reset CivilAI Docker state and update the repo from GitHub.

Default behavior:
1. Stop Docker Compose services.
2. Remove Compose containers, networks, and volumes for this project.
3. Pull the latest code from the configured Git remote.

More destructive actions require explicit flags:
- `--hard-reset` discards local git changes after fetching.
- `--prune-docker` runs a global Docker system prune, including volumes.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def run(command: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess:
    print(f"\n$ {' '.join(command)}")
    return subprocess.run(command, cwd=cwd, check=check)


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[1]


def confirm_or_exit(args: argparse.Namespace) -> None:
    if args.yes:
        return

    print("This will stop Docker Compose services and remove project Docker volumes.")
    if args.hard_reset:
        print("It will also discard local git changes.")
    if args.prune_docker:
        print("It will also prune unused Docker images, containers, networks, and volumes globally.")

    answer = input("Type RESET to continue: ").strip()
    if answer != "RESET":
        print("Aborted.")
        raise SystemExit(1)


def docker_compose_base(repo_root: Path) -> list[str]:
    if shutil.which("docker") is None:
        raise SystemExit("Docker was not found on PATH.")

    compose_files = [
        repo_root / "docker-compose.yml",
        repo_root / "docker-compose.server.yml",
    ]
    existing = [path for path in compose_files if path.exists()]
    if not existing:
        raise SystemExit("No docker-compose.yml files were found.")

    command = ["docker", "compose"]
    for compose_file in existing:
        command.extend(["-f", str(compose_file)])
    return command


def reset_docker(repo_root: Path, args: argparse.Namespace) -> None:
    compose = docker_compose_base(repo_root)

    run([*compose, "down", "--volumes", "--remove-orphans", "--rmi", "local"], repo_root)

    if args.prune_docker:
        run(["docker", "system", "prune", "--all", "--force", "--volumes"], repo_root)


def update_from_github(repo_root: Path, args: argparse.Namespace) -> None:
    if shutil.which("git") is None:
        raise SystemExit("Git was not found on PATH.")

    run(["git", "fetch", args.remote, args.branch, "--prune"], repo_root)

    if args.hard_reset:
        run(["git", "reset", "--hard", f"{args.remote}/{args.branch}"], repo_root)
        run(["git", "clean", "-fd"], repo_root)
        return

    run(["git", "pull", "--ff-only", args.remote, args.branch], repo_root)


def rebuild_or_start(repo_root: Path, args: argparse.Namespace) -> None:
    if not args.rebuild and not args.start:
        return

    compose = docker_compose_base(repo_root)
    if args.rebuild:
        run([*compose, "build", "--pull"], repo_root)
    if args.start:
        run([*compose, "up", "-d"], repo_root)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset CivilAI Docker Compose state and pull latest GitHub code."
    )
    parser.add_argument("--remote", default="origin", help="Git remote to fetch/pull.")
    parser.add_argument("--branch", default="main", help="Git branch to fetch/pull.")
    parser.add_argument("--repo", type=Path, default=repo_root_from_script(), help="Repo root.")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt.")
    parser.add_argument(
        "--hard-reset",
        action="store_true",
        help="Discard local git changes and reset to remote branch.",
    )
    parser.add_argument(
        "--prune-docker",
        action="store_true",
        help="Also run global docker system prune --all --volumes.",
    )
    parser.add_argument("--rebuild", action="store_true", help="Rebuild Docker images after pull.")
    parser.add_argument("--start", action="store_true", help="Start Docker Compose after reset.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = args.repo.resolve()

    if not (repo_root / ".git").exists():
        raise SystemExit(f"{repo_root} does not look like a git repository.")

    confirm_or_exit(args)
    reset_docker(repo_root, args)
    update_from_github(repo_root, args)
    rebuild_or_start(repo_root, args)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
