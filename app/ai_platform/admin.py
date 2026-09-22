"""Server-owned admin principal seam; no public header becomes admin by default."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AdminPrincipal:
    subject_fingerprint: str
    roles: frozenset[str]

    @property
    def is_admin(self) -> bool:
        return "admin" in self.roles


class AdminAuthorizer:
    """Read a principal installed by trusted ingress or the host application."""

    def __call__(self, request: Any) -> bool:
        principal = getattr(request.state, "admin_principal", None)
        return isinstance(principal, AdminPrincipal) and principal.is_admin


__all__ = ["AdminAuthorizer", "AdminPrincipal"]
