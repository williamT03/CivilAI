from .api_contract import ApiContractAgent
from .audit_log import AuditLogAgent
from .data_leak import DataLeakAgent
from .deployment_gate import DeploymentGateAgent
from .feature_flow import FeatureFlowAgent
from .frontend_features import FrontendFeaturesAgent
from .llm_safety import LlmSafetyAgent
from .policy_gate import PolicyGateAgent
from .risk_register import RiskRegisterAgent
from .security import SecurityAgent
from .server_connections import ServerConnectionsAgent
from .server_runtime import ServerRuntimeAgent
from .tenant_isolation import TenantIsolationAgent
from .threat_model import ThreatModelAgent

AGENT_REGISTRY = {
    SecurityAgent.name: SecurityAgent,
    ApiContractAgent.name: ApiContractAgent,
    FeatureFlowAgent.name: FeatureFlowAgent,
    FrontendFeaturesAgent.name: FrontendFeaturesAgent,
    ServerConnectionsAgent.name: ServerConnectionsAgent,
    ServerRuntimeAgent.name: ServerRuntimeAgent,
    RiskRegisterAgent.name: RiskRegisterAgent,
    PolicyGateAgent.name: PolicyGateAgent,
    ThreatModelAgent.name: ThreatModelAgent,
    DataLeakAgent.name: DataLeakAgent,
    TenantIsolationAgent.name: TenantIsolationAgent,
    LlmSafetyAgent.name: LlmSafetyAgent,
    AuditLogAgent.name: AuditLogAgent,
    DeploymentGateAgent.name: DeploymentGateAgent,
}
