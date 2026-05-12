from .api_contract import ApiContractAgent
from .feature_flow import FeatureFlowAgent
from .security import SecurityAgent

AGENT_REGISTRY = {
    SecurityAgent.name: SecurityAgent,
    ApiContractAgent.name: ApiContractAgent,
    FeatureFlowAgent.name: FeatureFlowAgent,
}
