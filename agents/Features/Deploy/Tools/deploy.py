"""Agent deploy file references."""

AGENT_ENV_EXAMPLE = "agents/deploy/agents.env.example"
INSTALL_TIMER = "agents/install_server_timer.sh"
RUN_SERVER = "agents/run_agents_server.sh"
SERVICE_TEMPLATE = "agents/deploy/civilai-agents.service"
TIMER_TEMPLATE = "agents/deploy/civilai-agents.timer"
UNINSTALL_TIMER = "agents/uninstall_server_timer.sh"

__all__ = [
    "AGENT_ENV_EXAMPLE",
    "INSTALL_TIMER",
    "RUN_SERVER",
    "SERVICE_TEMPLATE",
    "TIMER_TEMPLATE",
    "UNINSTALL_TIMER",
]
