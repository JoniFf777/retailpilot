from app.main import app


def test_openapi_chat_schemas_include_v3_handoff_examples() -> None:
    schema = app.openapi()
    schemas = schema["components"]["schemas"]

    chat_request = schemas["ChatRequest"]
    chat_response = schemas["ChatResponse"]
    confirm_request = schemas["ConfirmChatRequest"]

    assert any(
        example["message"] == "add to cart TECH-KEY-010 quantity 2"
        for example in chat_request["examples"]
    )
    assert any(example["message"] == "1" for example in chat_request["examples"])
    assert chat_response["properties"]["status"]["examples"] == [
        "completed",
        "confirmation_required",
        "cancelled",
        "failed",
    ]
    assert "confirmation_required" in chat_response["properties"]["status"][
        "description"
    ]
    assert chat_response["examples"][0]["pending_action_id"] == "pending-action-id"
    assert "run_id" in chat_response["properties"]
    assert "trace_id" in chat_response["properties"]
    assert confirm_request["examples"][0]["confirmed"] is True
    assert confirm_request["examples"][0]["updated_arguments"] == {"quantity": 2}
    assert "updated_arguments" in confirm_request["properties"]
    assert confirm_request["examples"][1]["confirmed"] is False


def test_openapi_paths_reference_chat_contract_schemas() -> None:
    schema = app.openapi()
    paths = schema["paths"]

    chat_body_ref = paths["/api/chat"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    confirm_body_ref = paths["/api/chat/confirm"]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]["$ref"]

    assert chat_body_ref.endswith("/ChatRequest")
    assert confirm_body_ref.endswith("/ConfirmChatRequest")
    assert any(
        parameter["name"] == "Idempotency-Key"
        for parameter in paths["/api/chat"]["post"]["parameters"]
    )
    assert "/api/health/governance-audit" in paths
    assert "/api/health/preflight" in paths
    assert "/api/health/readiness" in paths
    assert "/api/health/service-metrics" in paths
    assert "/api/owner-data/runs/inspect" in paths
