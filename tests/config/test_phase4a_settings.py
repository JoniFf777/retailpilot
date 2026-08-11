import pytest
from pydantic import SecretStr, ValidationError

from app.core.settings import Settings


def test_checkout_secret_is_optional_in_development_and_hidden_in_repr() -> None:
    settings = Settings()
    assert settings.shopmind_checkout_signing_secret is None
    configured = Settings(shopmind_checkout_signing_secret=SecretStr("x" * 32))
    assert "x" * 32 not in repr(configured)


def test_checkout_secret_and_ttl_validation() -> None:
    with pytest.raises(ValidationError):
        Settings(shopmind_checkout_signing_secret=SecretStr("too-short"))
    with pytest.raises(ValidationError):
        Settings(shopmind_checkout_token_ttl_seconds=3_601)
    assert Settings(shopmind_checkout_token_ttl_seconds=1).shopmind_checkout_token_ttl_seconds == 1
