from app.ai_platform.contracts import ModelCandidate, ModelOperation
from app.ai_platform.model_adapter import gateway_provider
from app.ai_platform.resilience import ModelGateway


def test_gateway_provider_preserves_structured_provider_result():
    gateway = ModelGateway(
        [
            ModelCandidate(
                candidate_id="planner",
                operation=ModelOperation.PLANNER,
                provider="test",
                model="test",
                priority=1,
            )
        ]
    )
    provider = gateway_provider(
        ModelOperation.PLANNER,
        lambda payload: {"routes": payload["routes"]},
        gateway,
    )
    assert provider({"routes": ["rag_agent"]}) == {"routes": ["rag_agent"]}
