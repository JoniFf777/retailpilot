from app.main import app


def test_phase4a_openapi_paths_and_body_boundaries() -> None:
    schema = app.openapi()
    paths = schema["paths"]
    assert {
        "/api/checkout/preview",
        "/api/orders",
        "/api/orders/{order_id}",
        "/api/orders/{order_id}/cancel",
    }.issubset(paths)
    preview = paths["/api/checkout/preview"]["post"]
    preview_schema = preview["requestBody"]["content"]["application/json"]["schema"]
    assert preview_schema["$ref"].endswith("/CheckoutPreviewRequest")
    create = paths["/api/orders"]["post"]
    create_schema = create["requestBody"]["content"]["application/json"]["schema"]
    assert create_schema["$ref"].endswith("/CreateOrderRequest")
    assert any(parameter["name"] == "Idempotency-Key" for parameter in create["parameters"])
    cancel = paths["/api/orders/{order_id}/cancel"]["post"]
    assert not any(parameter["name"] == "Idempotency-Key" for parameter in cancel["parameters"])
    assert "Money" in str(schema["components"]["schemas"]["OrderView"])
    assert "410" in create["responses"]
    assert "503" in create["responses"]
    assert "409" in create["responses"]
    validation = create["responses"]["422"]["content"]["application/json"]["schema"]
    refs = {entry["$ref"] for entry in validation["oneOf"]}
    assert "#/components/schemas/HTTPValidationError" in refs
    assert "#/components/schemas/OrderErrorResponse" in refs


def test_phase4a_public_order_schema_hides_internal_facts() -> None:
    order = app.openapi()["components"]["schemas"]["OrderView"]["properties"]
    assert "request_hash" not in order
    assert "idempotency_key" not in order
    money = app.openapi()["components"]["schemas"]["Money"]["properties"]
    assert money["amount"]["type"] == "string"
