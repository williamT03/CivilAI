# Agents Feature Map

The agentic engineering harness is organized around management feature facades:

- `Features/Runner_management/runner_run.py`: command parsing, run-plan builder, and check execution.
- `Features/Checks_management/checks_run.py`: all concrete validation agents.
- `Features/Runtime_management/runtime_run.py`: HTTP runtime checks, shell commands, and auth test users.
- `Features/Static_management/static_run.py`: static file checks and source scanning helpers.
- `Features/Reports_management/reports_run.py`: JSON report writing and failure extraction.
- `Features/Deploy_management/deploy_run.py`: systemd timer/service templates and server scripts.

Existing scripts and imports still work. The feature folders make the harness easier to read and extend.
