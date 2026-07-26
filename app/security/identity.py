"""Server-owned request identity and owner-binding contracts."""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from collections.abc import Callable
from enum import StrEnum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.core.settings import Settings
from app.runtime.coordination import (
    DeduplicationRequest,
    LocalRuntimeCoordinationBackend,
    RuntimeCoordinationBackend,
    coordination_key_fingerprint,
)


SIGNED_IDENTITY_SCHEMA_VERSION = "shopmind.identity-signature.v1"
_SIGNED_NONCE_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_SIGNED_SIGNATURE_RE = re.compile(r"^[0-9a-f]{64}$")
_SIGNED_TIMESTAMP_RE = re.compile(r"^(0|[1-9][0-9]{0,11})$")
_DEFAULT_SIGNED_IDENTITY_REPLAY_BACKEND = LocalRuntimeCoordinationBackend()


class IdentityProviderName(StrEnum):
    DEVELOPMENT_PAYLOAD = "development_payload"
    TRUSTED_HEADER = "trusted_header"
    SIGNED_HEADER = "signed_header"


class IdentityAuthenticationFailure(StrEnum):
    MISSING = "missing"
    INVALID = "invalid"
    EXPIRED = "expired"
    REPLAYED = "replayed"
    BACKEND_UNAVAILABLE = "backend_unavailable"


class AuthenticationRequiredError(RuntimeError):
    """Raised when the selected identity provider cannot authenticate a request."""

    def __init__(
        self,
        failure: IdentityAuthenticationFailure = (
            IdentityAuthenticationFailure.MISSING
        ),
    ) -> None:
        super().__init__("Authentication required.")
        self.failure = failure


class AuthorizationDeniedError(RuntimeError):
    """Raised when an authenticated principal attempts to cross owner scope."""


class AuthenticatedPrincipal(BaseModel):
    """Authenticated subject with a PII-safe identity for audit/event use."""

    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True)

    subject_id: str = Field(min_length=1, max_length=128, repr=False)
    subject_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: IdentityProviderName

    @field_validator("subject_id")
    @classmethod
    def validate_subject_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(ord(character) < 32 for character in normalized):
            raise ValueError("Authenticated subject is invalid.")
        return normalized


class IdentityBinding(BaseModel):
    """One authorized owner binding for an API operation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    principal: AuthenticatedPrincipal | None = None
    effective_user_id: str | None = Field(default=None, repr=False)


class SignedIdentityVerification(BaseModel):
    """Closed signed-ingress result that never represents raw credentials."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        use_enum_values=True,
    )

    authenticated: bool
    subject_id: str | None = Field(default=None, repr=False)
    failure: IdentityAuthenticationFailure | None = None

    @model_validator(mode="after")
    def validate_result(self) -> "SignedIdentityVerification":
        if self.authenticated != (self.subject_id is not None):
            raise ValueError(
                "Authenticated identity verification requires one subject."
            )
        if self.authenticated == (self.failure is not None):
            raise ValueError(
                "Identity verification failure classification is invalid."
            )
        return self


def signed_identity_signature(
    *,
    secret: str,
    subject_id: str,
    issued_at: int,
    nonce: str,
) -> str:
    """Create the versioned ingress signature without retaining its inputs."""

    if not secret:
        raise ValueError("Identity signing secret is required.")
    canonical = (
        f"{SIGNED_IDENTITY_SCHEMA_VERSION}\0{subject_id}\0{issued_at}\0{nonce}"
    ).encode("utf-8")
    return hmac.new(
        secret.encode("utf-8"),
        canonical,
        hashlib.sha256,
    ).hexdigest()


class SignedHeaderIdentityVerifier:
    """Verify one short-lived, one-time HMAC ingress assertion."""

    def __init__(
        self,
        *,
        signing_secret: str,
        replay_backend: RuntimeCoordinationBackend,
        max_age_seconds: int,
        clock_skew_seconds: int,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if len(signing_secret) < 32:
            raise ValueError("Identity signing secret is too short.")
        if not 1 <= max_age_seconds <= 300:
            raise ValueError("Identity signature max age is invalid.")
        if not 0 <= clock_skew_seconds < max_age_seconds:
            raise ValueError("Identity signature clock skew is invalid.")
        self._signing_secret = signing_secret
        self._replay_backend = replay_backend
        self._max_age_seconds = max_age_seconds
        self._clock_skew_seconds = clock_skew_seconds
        self._clock = clock or time.time

    def verify(
        self,
        *,
        subject_id: str | None,
        issued_at: str | None,
        nonce: str | None,
        signature: str | None,
    ) -> SignedIdentityVerification:
        values = (subject_id, issued_at, nonce, signature)
        if all(value is None for value in values):
            return self._failure(IdentityAuthenticationFailure.MISSING)
        if any(value is None for value in values):
            return self._failure(IdentityAuthenticationFailure.INVALID)

        normalized_subject = str(subject_id).strip()
        if (
            not normalized_subject
            or len(normalized_subject) > 128
            or any(ord(character) < 32 for character in normalized_subject)
            or not _SIGNED_TIMESTAMP_RE.fullmatch(str(issued_at))
            or not _SIGNED_NONCE_RE.fullmatch(str(nonce))
            or not _SIGNED_SIGNATURE_RE.fullmatch(str(signature))
        ):
            return self._failure(IdentityAuthenticationFailure.INVALID)

        issued_at_seconds = int(str(issued_at))
        now = self._clock()
        age_seconds = now - issued_at_seconds
        if (
            age_seconds > self._max_age_seconds
            or age_seconds < -self._clock_skew_seconds
        ):
            return self._failure(IdentityAuthenticationFailure.EXPIRED)

        expected = signed_identity_signature(
            secret=self._signing_secret,
            subject_id=normalized_subject,
            issued_at=issued_at_seconds,
            nonce=str(nonce),
        )
        if not hmac.compare_digest(expected, str(signature)):
            return self._failure(IdentityAuthenticationFailure.INVALID)

        replay_fingerprint = coordination_key_fingerprint(
            "identity-signed-request",
            (
                f"{normalized_subject}\0{issued_at_seconds}\0"
                f"{nonce}\0{signature}"
            ),
        )
        try:
            decision = self._replay_backend.claim_duplicate(
                DeduplicationRequest(
                    namespace="identity.signed-header",
                    key_fingerprint=replay_fingerprint,
                    ttl_ms=(
                        self._max_age_seconds + self._clock_skew_seconds
                    )
                    * 1_000,
                )
            )
        except Exception:
            return self._failure(
                IdentityAuthenticationFailure.BACKEND_UNAVAILABLE
            )
        if not decision.acquired:
            return self._failure(
                IdentityAuthenticationFailure.REPLAYED
                if decision.reason == "duplicate"
                else IdentityAuthenticationFailure.BACKEND_UNAVAILABLE
            )
        return SignedIdentityVerification(
            authenticated=True,
            subject_id=normalized_subject,
        )

    @staticmethod
    def _failure(
        failure: IdentityAuthenticationFailure,
    ) -> SignedIdentityVerification:
        return SignedIdentityVerification(
            authenticated=False,
            failure=failure,
        )


class IdentityBoundary:
    """Bind an API owner field to identity selected only by server settings."""

    def __init__(
        self,
        provider: IdentityProviderName,
        *,
        trusted_subject: str | None = None,
        authentication_failure: IdentityAuthenticationFailure = (
            IdentityAuthenticationFailure.MISSING
        ),
    ) -> None:
        self._provider = provider
        normalized_subject = self._normalize_optional(trusted_subject)
        invalid_subject = (
            trusted_subject is not None
            and (
                normalized_subject is None
                or len(normalized_subject) > 128
                or any(ord(character) < 32 for character in normalized_subject)
            )
        )
        self._trusted_subject = (
            None if invalid_subject else normalized_subject
        )
        self._authentication_failure = (
            IdentityAuthenticationFailure.INVALID
            if (
                invalid_subject
                and authentication_failure
                == IdentityAuthenticationFailure.MISSING
            )
            else authentication_failure
        )

    @property
    def provider_name(self) -> IdentityProviderName:
        return self._provider

    @property
    def authenticated_principal(self) -> AuthenticatedPrincipal | None:
        """Expose only a server-selected trusted principal for denial auditing."""

        if (
            self._provider
            in {
                IdentityProviderName.TRUSTED_HEADER,
                IdentityProviderName.SIGNED_HEADER,
            }
            and self._trusted_subject is not None
        ):
            return self._principal(self._trusted_subject)
        return None

    @property
    def authentication_failure(self) -> IdentityAuthenticationFailure:
        return self._authentication_failure

    @property
    def authentication_scheme(self) -> str:
        if self._provider == IdentityProviderName.SIGNED_HEADER:
            return "ShopMindSignedHeader"
        return "ShopMindTrustedHeader"

    def bind_user(
        self,
        requested_user_id: str | None,
        *,
        require_user: bool,
    ) -> IdentityBinding:
        requested = self._normalize_optional(requested_user_id)
        if self._provider == IdentityProviderName.DEVELOPMENT_PAYLOAD:
            if requested is None:
                if require_user:
                    raise AuthenticationRequiredError()
                return IdentityBinding()
            principal = self._principal(requested)
            return IdentityBinding(
                principal=principal,
                effective_user_id=principal.subject_id,
            )

        if self._trusted_subject is None:
            raise AuthenticationRequiredError(self._authentication_failure)
        principal = self._principal(self._trusted_subject)
        if requested is not None and requested != principal.subject_id:
            raise AuthorizationDeniedError(
                "Authenticated principal cannot act for requested user."
            )
        return IdentityBinding(
            principal=principal,
            effective_user_id=principal.subject_id,
        )

    def _principal(self, subject_id: str) -> AuthenticatedPrincipal:
        return AuthenticatedPrincipal(
            subject_id=subject_id,
            subject_fingerprint=hashlib.sha256(
                f"shopmind.identity.subject\0{subject_id}".encode("utf-8")
            ).hexdigest(),
            provider=self._provider,
        )

    @staticmethod
    def _normalize_optional(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


def build_identity_boundary(
    settings: Settings,
    *,
    trusted_subject: str | None = None,
    signed_issued_at: str | None = None,
    signed_nonce: str | None = None,
    signed_signature: str | None = None,
    replay_backend: RuntimeCoordinationBackend | None = None,
    clock: Callable[[], float] | None = None,
) -> IdentityBoundary:
    """Construct only the identity provider selected by server configuration."""

    provider = IdentityProviderName(settings.shopmind_identity_provider)
    if provider == IdentityProviderName.SIGNED_HEADER:
        signing_secret = settings.shopmind_identity_signing_secret
        if signing_secret is None:
            return IdentityBoundary(
                provider,
                authentication_failure=(
                    IdentityAuthenticationFailure.BACKEND_UNAVAILABLE
                ),
            )
        verification = SignedHeaderIdentityVerifier(
            signing_secret=signing_secret.get_secret_value(),
            replay_backend=(
                replay_backend or _DEFAULT_SIGNED_IDENTITY_REPLAY_BACKEND
            ),
            max_age_seconds=(
                settings.shopmind_identity_signature_max_age_seconds
            ),
            clock_skew_seconds=(
                settings.shopmind_identity_signature_clock_skew_seconds
            ),
            clock=clock,
        ).verify(
            subject_id=trusted_subject,
            issued_at=signed_issued_at,
            nonce=signed_nonce,
            signature=signed_signature,
        )
        return IdentityBoundary(
            provider,
            trusted_subject=verification.subject_id,
            authentication_failure=(
                IdentityAuthenticationFailure(
                    verification.failure
                    or IdentityAuthenticationFailure.MISSING
                )
            ),
        )
    return IdentityBoundary(
        provider,
        trusted_subject=trusted_subject,
    )


__all__ = [
    "AuthenticatedPrincipal",
    "AuthenticationRequiredError",
    "AuthorizationDeniedError",
    "IdentityAuthenticationFailure",
    "IdentityBinding",
    "IdentityBoundary",
    "IdentityProviderName",
    "SIGNED_IDENTITY_SCHEMA_VERSION",
    "SignedHeaderIdentityVerifier",
    "SignedIdentityVerification",
    "build_identity_boundary",
    "signed_identity_signature",
]
