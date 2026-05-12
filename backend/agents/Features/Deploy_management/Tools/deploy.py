"""Agent deploy file references."""

AGENT_ENV_EXAMPLE = "backend/agents/Features/Deploy_management/Templates/agents.env.example"
INSTALL_TIMER = "backend/agents/install_server_timer.sh"
RUN_SERVER = "backend/agents/run_agents_server.sh"
SERVICE_TEMPLATE = "backend/agents/Features/Deploy_management/Templates/civilai-agents.service"
TIMER_TEMPLATE = "backend/agents/Features/Deploy_management/Templates/civilai-agents.timer"
UNINSTALL_TIMER = "backend/agents/uninstall_server_timer.sh"

__all__ = [
    "AGENT_ENV_EXAMPLE",
    "INSTALL_TIMER",
    "RUN_SERVER",
    "SERVICE_TEMPLATE",
    "TIMER_TEMPLATE",
    "UNINSTALL_TIMER",
]
