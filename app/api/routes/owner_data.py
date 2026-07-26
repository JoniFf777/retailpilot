"""Authenticated owner-data inspection, correction, and deletion routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.settings import get_settings
from app.db.session import SessionLocal
from app.dependencies import security as security_dependency
from app.dependencies.security import bind_request_user, get_identity_boundary
from app.governance import (
    OwnerDataDeletion,
    OwnerDataService,
    OwnerDataSnapshot,
    OwnerDataStorageError,
    OwnerMemoryCorrection,
    OwnerMemoryDeletion,
    OwnerRunInspection,
)
from app.schemas.owner_data import (
    OwnerDataDeletionRequest,
    OwnerDataInspectRequest,
    OwnerMemoryCorrectionRequest,
    OwnerMemoryDeletionRequest,
    OwnerRunInspectRequest,
)
from app.security import (
    AuditRequestOperation,
    AuthenticatedPrincipal,
    IdentityBoundary,
)


router = APIRouter()


def get_owner_data_service() -> OwnerDataService:
    return OwnerDataService(
        SessionLocal,
        audit_emitter=security_dependency.governance_audit_emitter,
    )


def _audit_enabled() -> bool:
    return bool(
        getattr(
            get_settings(),
            "shopmind_governance_audit_enabled",
            False,
        )
    )


def _bind_owner(
    boundary: IdentityBoundary,
    owner_id: str,
    operation: AuditRequestOperation,
) -> tuple[str, AuthenticatedPrincipal]:
    binding = bind_request_user(
        boundary,
        owner_id,
        require_user=True,
        request_operation=operation,
    )
    if binding.effective_user_id is None or binding.principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    return binding.effective_user_id, binding.principal


def _storage_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Owner data storage unavailable.",
    )


@router.post(
    "/owner-data/inspect",
    response_model=OwnerDataSnapshot,
)
def inspect_owner_data(
    request: OwnerDataInspectRequest,
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    service: OwnerDataService = Depends(get_owner_data_service),
) -> OwnerDataSnapshot:
    owner_id, principal = _bind_owner(
        identity_boundary,
        request.user_id,
        AuditRequestOperation.OWNER_DATA_INSPECT,
    )
    try:
        return service.inspect(
            owner_id=owner_id,
            principal=principal,
            memory_limit=request.memory_limit,
            audit_enabled=_audit_enabled(),
        )
    except OwnerDataStorageError as exc:
        raise _storage_unavailable() from exc


@router.post(
    "/owner-data/runs/inspect",
    response_model=OwnerRunInspection,
)
def inspect_owner_run(
    request: OwnerRunInspectRequest,
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    service: OwnerDataService = Depends(get_owner_data_service),
) -> OwnerRunInspection:
    owner_id, _principal = _bind_owner(
        identity_boundary,
        request.user_id,
        AuditRequestOperation.OWNER_DATA_INSPECT,
    )
    try:
        result = service.inspect_run(
            owner_id=owner_id,
            run_id=request.run_id,
            trace_id=request.trace_id,
            event_limit=request.event_limit,
        )
    except OwnerDataStorageError as exc:
        raise _storage_unavailable() from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Owner run not found.",
        )
    return result


@router.post(
    "/owner-data/memory/correct",
    response_model=OwnerMemoryCorrection,
)
def correct_owner_memory(
    request: OwnerMemoryCorrectionRequest,
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    service: OwnerDataService = Depends(get_owner_data_service),
) -> OwnerMemoryCorrection:
    owner_id, principal = _bind_owner(
        identity_boundary,
        request.user_id,
        AuditRequestOperation.OWNER_MEMORY_CORRECT,
    )
    try:
        result = service.correct_memory(
            owner_id=owner_id,
            principal=principal,
            memory_id=request.memory_id,
            content=request.content,
            audit_enabled=_audit_enabled(),
        )
    except OwnerDataStorageError as exc:
        raise _storage_unavailable() from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Owner memory record not found.",
        )
    return result


@router.post(
    "/owner-data/memory/delete",
    response_model=OwnerMemoryDeletion,
)
def delete_owner_memory(
    request: OwnerMemoryDeletionRequest,
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    service: OwnerDataService = Depends(get_owner_data_service),
) -> OwnerMemoryDeletion:
    owner_id, principal = _bind_owner(
        identity_boundary,
        request.user_id,
        AuditRequestOperation.OWNER_MEMORY_DELETE,
    )
    try:
        result = service.delete_memory(
            owner_id=owner_id,
            principal=principal,
            memory_id=request.memory_id,
            audit_enabled=_audit_enabled(),
        )
    except OwnerDataStorageError as exc:
        raise _storage_unavailable() from exc
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Owner memory record not found.",
        )
    return result


@router.post(
    "/owner-data/delete",
    response_model=OwnerDataDeletion,
)
def delete_owner_data(
    request: OwnerDataDeletionRequest,
    identity_boundary: IdentityBoundary = Depends(get_identity_boundary),
    service: OwnerDataService = Depends(get_owner_data_service),
) -> OwnerDataDeletion:
    owner_id, principal = _bind_owner(
        identity_boundary,
        request.user_id,
        AuditRequestOperation.OWNER_DATA_DELETE,
    )
    try:
        return service.delete_all(
            owner_id=owner_id,
            principal=principal,
            deletion_request_id=request.deletion_request_id,
            audit_enabled=_audit_enabled(),
        )
    except OwnerDataStorageError as exc:
        raise _storage_unavailable() from exc


__all__ = ["get_owner_data_service", "router"]
