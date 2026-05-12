from __future__ import annotations

import subprocess
import shutil
from pathlib import Path


def run_command(command: list[str], cwd: Path, timeout_seconds: int = 120) -> subprocess.CompletedProcess[str]:
    resolved_command = list(command)
    executable = shutil.which(resolved_command[0])
    if executable:
        resolved_command[0] = executable

    return subprocess.run(
        resolved_command,
        cwd=str(cwd),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
