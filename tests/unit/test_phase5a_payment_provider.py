from app.payments.providers import MockPaymentProvider, ProviderChargeRequest


def _request(key: str, method: str = "method") -> ProviderChargeRequest:
    return ProviderChargeRequest(
        provider_idempotency_key=key,
        amount="10.00",
        currency="CNY",
        payment_method_ref=method,
    )


def test_mock_provider_reuses_one_operation_and_payment_id() -> None:
    provider = MockPaymentProvider()
    first = provider.charge(_request("same-provider-key"))
    replay = provider.charge(_request("same-provider-key"))

    assert first.status == "succeeded"
    assert replay == first
    assert provider.charge_calls == 2
    assert first.provider_payment_id == "mock-pay-same-provider-key"


def test_mock_provider_unknown_reconcile_resolves_without_second_charge() -> None:
    provider = MockPaymentProvider(
        scenarios_by_method={"unknown": ("timeout", "success")}
    )
    first = provider.charge(_request("unknown-provider-key", "unknown"))
    resolved = provider.get_result("unknown-provider-key")

    assert first.status == "unknown"
    assert resolved.status == "succeeded"
    assert resolved.provider_payment_id == first.provider_payment_id
    assert provider.charge_calls == 1
    assert provider.get_result_calls == 1


def test_mock_provider_unknown_result_is_stable_until_provider_changes_it() -> None:
    provider = MockPaymentProvider(
        scenarios_by_method={"stuck": ("unknown",)}
    )
    first = provider.charge(_request("stuck-provider-key", "stuck"))
    second = provider.get_result("stuck-provider-key")

    assert first.status == "unknown"
    assert second.status == "unknown"
    assert second.provider_payment_id == first.provider_payment_id
