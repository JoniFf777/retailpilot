import json
from pathlib import Path

from app.main import app


VERSIONED_COMMERCE_PATHS = (
    "/api/cart",
    "/api/checkout/preview",
    "/api/health/outbox",
    "/api/orders",
    "/api/orders/{order_id}/payments",
    "/api/pending-actions/add-to-cart",
)


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


def test_versioned_openapi_artifacts_match_runtime_schema() -> None:
    runtime_schema = app.openapi()
    exported_schema = json.loads(
        Path("frontend/openapi.json").read_text(encoding="utf-8")
    )
    generated_types = Path("frontend/src/api/openapi.generated.ts").read_text(
        encoding="utf-8"
    )

    assert exported_schema == runtime_schema
    for path in VERSIONED_COMMERCE_PATHS:
        assert path in exported_schema["paths"]
        assert f'"{path}":' in generated_types


def test_openapi_structured_action_errors_and_confirm_headers() -> None:
    schema = app.openapi()
    paths = schema["paths"]
    schemas = schema["components"]["schemas"]
    error = schemas["ActionErrorResponse"]
    assert set(error["properties"]) >= {"code", "message", "details", "idempotent_replay"}
    assert "action_resolution_conflict" in error["properties"]["code"]["enum"]
    assert "PendingActionErrorDetails" in str(error["properties"]["details"])
    assert schemas["PendingActionTransitionRequest"]["properties"]["expected_version"]
    confirm = paths["/api/pending-actions/{pending_action_id}/confirm"]["post"]
    assert not any(parameter.get("name") == "Idempotency-Key" for parameter in confirm.get("parameters", []))
    assert "410" in confirm["responses"]


def test_openapi_legacy_preference_fields_are_discriminated_and_typed() -> None:
    schemas = app.openapi()["components"]["schemas"]
    assert schemas["PendingActionView"]["properties"]["editable_fields"]["items"]["discriminator"]["propertyName"] == "field_type"
    assert schemas["IntegerEditableField"]["properties"]["field_type"]["const"] == "integer"
    assert schemas["EnumEditableField"]["properties"]["field_type"]["const"] == "enum"
    assert schemas["TextEditableField"]["properties"]["field_type"]["const"] == "text"
    assert "payload" not in schemas["PendingActionView"]["properties"]
