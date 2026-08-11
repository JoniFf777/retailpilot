from app.main import app


def test_phase5a_payment_openapi_contract() -> None:
    schema = app.openapi()
    paths = schema["paths"]
    assert "/api/orders/{order_id}/payments" in paths
    post = paths["/api/orders/{order_id}/payments"]["post"]
    get = paths["/api/orders/{order_id}/payments"]["get"]
    assert any(parameter["name"] == "Idempotency-Key" for parameter in post["parameters"])
    assert "202" in post["responses"]
    assert "402" in post["responses"]
    assert "409" in post["responses"]
    assert "503" in post["responses"]
    assert "422" in post["responses"]
    assert "404" in get["responses"]
    assert "422" in get["responses"]

    request_schema = schema["components"]["schemas"]["PaymentAttemptRequest"]["properties"]
    assert set(request_schema) == {"provider", "payment_method_ref"}
    assert "amount" not in request_schema
    assert "currency" not in request_schema
    assert "user_id" not in request_schema
    assert "scenario" not in request_schema

    public_attempt = schema["components"]["schemas"]["PaymentAttemptView"]["properties"]
    assert "request_hash" not in public_attempt
    assert "idempotency_key" not in public_attempt
    assert "provider_idempotency_key" not in public_attempt
    assert "provider_payment_id" not in public_attempt
    assert "paid" in str(schema["components"]["schemas"]["OrderView"])
