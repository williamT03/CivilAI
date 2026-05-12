from .api_contract import ApiContractAgent
from .feature_flow import FeatureFlowAgent
from .frontend_features import FrontendFeaturesAgent
from .server_connections import ServerConnectionsAgent
from .server_runtime import ServerRuntimeAgent
from .security import SecurityAgent

AGENT_REGISTRY = {
    SecurityAgent.name: SecurityAgent,
    ApiContractAgent.name: ApiContractAgent,
    FeatureFlowAgent.name: FeatureFlowAgent,
    FrontendFeaturesAgent.name: FrontendFeaturesAgent,
    ServerConnectionsAgent.name: ServerConnectionsAgent,
    ServerRuntimeAgent.name: ServerRuntimeAgent,
}
