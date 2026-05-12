# Agents Feature Map

The agentic engineering harness is organized around feature facades:

- `Features/Runner/runner_run.py`: command parsing, run-plan builder, and check execution.
- `Features/Checks/checks_run.py`: all concrete validation agents.
- `Features/Runtime/runtime_run.py`: HTTP runtime checks, shell commands, and auth test users.
- `Features/Static/static_run.py`: static file checks and source scanning helpers.
- `Features/Reports/reports_run.py`: JSON report writing and failure extraction.
- `Features/Deploy/deploy_run.py`: systemd timer/service file locations and server scripts.

Existing scripts and imports still work. The feature folders make the harness easier to read and extend.
