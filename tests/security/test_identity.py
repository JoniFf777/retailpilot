import pytest

from app.core.settings import Settings
from app.runtime import LocalRuntimeCoordinationBackend
from app.security import (
    AuthenticationRequiredError,
    AuthorizationDeniedError,
    IdentityAuthenticationFailure,
    IdentityProviderName,
    build_identity_boundary,
    signed_identity_signature,
)


SIGNED_SECRET = "signed-identity-test-secret-32-bytes-minimum"
SIGNED_NOW = 1_800_000_000


def _signed_settings() -> Settings:
    return Settings(
        shopmind_identity_provider="signed_header",
        shopmind_identity_signing_secret=SIGNED_SECRET,
        shopmind_identity_signature_max_age_seconds=60,
        shopmind_identity_signature_clock_skew_seconds=5,
    )


def _signed_headers(
    *,
    subject: str = "signed-user",
    issued_at: int = SIGNED_NOW,
    nonce: str = "nonce-0123456789abcdef",
) -> dict[str, str]:
    return {
        "trusted_subject": subject,
        "signed_issued_at": str(issued_at),
        "signed_nonce": nonce,
        "signed_signature": signed_identity_signature(
            secret=SIGNED_SECRET,
            subject_id=subject,
            issued_at=issued_at,
            nonce=nonce,
        ),
    }


def test_development_identity_preserves_optional_v3_user_contract() -> None:
    boundary = build_identity_boundary(Settings())

    anonymous = boundary.bind_user(None, require_user=False)
    identified = boundary.bind_user("  user-001  ", require_user=False)

    assert boundary.provider_name == IdentityProviderName.DEVELOPMENT_PAYLOAD
    assert anonymous.principal is None
    assert anonymous.effective_user_id is None
    assert identified.effective_user_id == "user-001"
    assert identified.principal.provider == "development_payload"
    assert len(identified.principal.subject_fingerprint) == 64
    assert "user-001" not in repr(identified)


def test_development_identity_requires_user_only_for_owner_required_operation() -> None:
    boundary = build_identity_boundary(Settings())

    with pytest.raises(AuthenticationRequiredError, match="required"):
        boundary.bind_user(None, require_user=True)


def test_trusted_header_identity_binds_or_rejects_owner_scope() -> None:
    boundary = build_identity_boundary(
        Settings(shopmind_identity_provider="trusted_header"),
        trusted_subject="proxy-user",
    )

    omitted = boundary.bind_user(None, require_user=False)
    matching = boundary.bind_user("proxy-user", require_user=True)

    assert boundary.provider_name == IdentityProviderName.TRUSTED_HEADER
    assert boundary.authenticated_principal is not None
    assert boundary.authenticated_principal.subject_id == "proxy-user"
    assert omitted.effective_user_id == "proxy-user"
    assert matching.effective_user_id == "proxy-user"
    assert matching.principal.provider == "trusted_header"
    with pytest.raises(AuthorizationDeniedError, match="cannot act"):
        boundary.bind_user("different-user", require_user=False)


def test_trusted_header_identity_fails_closed_when_subject_is_missing() -> None:
    boundary = build_identity_boundary(
        Settings(shopmind_identity_provider="trusted_header")
    )

    assert boundary.authenticated_principal is None
    with pytest.raises(AuthenticationRequiredError, match="required"):
        boundary.bind_user("payload-user", require_user=False)


def test_trusted_header_identity_fails_closed_for_invalid_subject() -> None:
    boundary = build_identity_boundary(
        Settings(shopmind_identity_provider="trusted_header"),
        trusted_subject="x" * 129,
    )

    assert boundary.authentication_failure == (
        IdentityAuthenticationFailure.INVALID
    )
    with pytest.raises(AuthenticationRequiredError) as raised:
        boundary.bind_user(None, require_user=False)
    assert raised.value.failure == IdentityAuthenticationFailure.INVALID


def test_signed_header_identity_authenticates_once_and_binds_owner() -> None:
    backend = LocalRuntimeCoordinationBackend()
    headers = _signed_headers()
    boundary = build_identity_boundary(
        _signed_settings(),
        replay_backend=backend,
        clock=lambda: SIGNED_NOW,
        **headers,
    )

    binding = boundary.bind_user("signed-user", require_user=True)

    assert boundary.provider_name == IdentityProviderName.SIGNED_HEADER
    assert boundary.authentication_scheme == "ShopMindSignedHeader"
    assert binding.effective_user_id == "signed-user"
    assert binding.principal.provider == "signed_header"
    assert SIGNED_SECRET not in repr(binding)
    assert headers["signed_signature"] not in repr(binding)
    with pytest.raises(AuthorizationDeniedError, match="cannot act"):
        boundary.bind_user("different-user", require_user=True)

    replayed = build_identity_boundary(
        _signed_settings(),
        replay_backend=backend,
        clock=lambda: SIGNED_NOW,
        **headers,
    )
    assert replayed.authentication_failure == (
        IdentityAuthenticationFailure.REPLAYED
    )
    with pytest.raises(AuthenticationRequiredError) as raised:
        replayed.bind_user("signed-user", require_user=True)
    assert raised.value.failure == IdentityAuthenticationFailure.REPLAYED


@pytest.mark.parametrize(
    ("header_overrides", "now", "failure"),
    (
        (
            {"signed_signature": "0" * 64},
            SIGNED_NOW,
            IdentityAuthenticationFailure.INVALID,
        ),
        (
            {"signed_issued_at": str(SIGNED_NOW - 61)},
            SIGNED_NOW,
            IdentityAuthenticationFailure.EXPIRED,
        ),
        (
            {"signed_signature": None},
            SIGNED_NOW,
            IdentityAuthenticationFailure.INVALID,
        ),
    ),
)
def test_signed_header_identity_rejects_invalid_or_partial_credentials(
    header_overrides,
    now,
    failure,
) -> None:
    headers = _signed_headers()
    headers.update(header_overrides)
    boundary = build_identity_boundary(
        _signed_settings(),
        replay_backend=LocalRuntimeCoordinationBackend(),
        clock=lambda: now,
        **headers,
    )

    assert boundary.authenticated_principal is None
    assert boundary.authentication_failure == failure
    with pytest.raises(AuthenticationRequiredError):
        boundary.bind_user(None, require_user=False)


def test_signed_header_identity_classifies_expired_and_backend_failure() -> None:
    expired_headers = _signed_headers(issued_at=SIGNED_NOW - 61)
    expired = build_identity_boundary(
        _signed_settings(),
        replay_backend=LocalRuntimeCoordinationBackend(),
        clock=lambda: SIGNED_NOW,
        **expired_headers,
    )

    class UnavailableBackend:
        def claim_duplicate(self, request):
            raise RuntimeError("private redis URL")

    unavailable = build_identity_boundary(
        _signed_settings(),
        replay_backend=UnavailableBackend(),
        clock=lambda: SIGNED_NOW,
        **_signed_headers(nonce="nonce-backend-0123456789"),
    )

    assert expired.authentication_failure == IdentityAuthenticationFailure.EXPIRED
    assert unavailable.authentication_failure == (
        IdentityAuthenticationFailure.BACKEND_UNAVAILABLE
    )
