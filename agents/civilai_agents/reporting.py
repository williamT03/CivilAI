from __future__ import annotations

import json
from pathlib import Path


def extract_report_failures(report_dir: Path) -> dict[str, list[dict]]:
    """Load agent JSON reports and return failed or warning checks grouped by report."""

    findings: dict[str, list[dict]] = {}
    for report_path in sorted(report_dir.glob("*.json")):
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        results = payload.get("results", [])
        actionable = [result for result in results if result.get("status") in {"fail", "warn"}]
        if actionable:
            findings[report_path.name] = actionable
    return findings
