"""Persistence for server-owned shopping AI extensions."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai_platform.extensions import ExtensionDefinition, ExtensionRegistry, ExtensionSnapshot
from app.ai_platform.prompts import validate_prompt_candidate
from app.ai_platform.models import AIExtensionDefinition, AIExtensionPublication


def persist_extension(session: Session, definition: ExtensionDefinition) -> AIExtensionDefinition:
    if definition.extension_type == "prompt":
        validate_prompt_candidate(definition.extension_key, definition.content)
    row = AIExtensionDefinition(
        extension_type=definition.extension_type,
        extension_key=definition.extension_key,
        version=definition.version,
        capability=definition.capability,
        agent_names=list(definition.agent_names),
        content=definition.content,
        content_fingerprint=definition.content_fingerprint,
        tool_ids=list(definition.tool_ids),
        side_effect=definition.side_effect,
        status="draft",
        metadata_json=definition.metadata,
    )
    session.add(row)
    session.flush()
    return row


def publish_extension(session: Session, definition_id: int) -> AIExtensionDefinition:
    row = session.get(AIExtensionDefinition, definition_id)
    if row is None:
        raise ValueError("Extension definition was not found.")
    definition = ExtensionDefinition(
        extension_type=row.extension_type,
        extension_key=row.extension_key,
        version=row.version,
        capability=row.capability,
        agent_names=tuple(row.agent_names or []),
        content=row.content,
        tool_ids=tuple(row.tool_ids or []),
        side_effect=row.side_effect,
        metadata=row.metadata_json or {},
    )
    row.status = "active"
    row.activated_at = datetime.now(timezone.utc)
    current = session.scalar(
        select(AIExtensionPublication).where(
            AIExtensionPublication.extension_type == row.extension_type,
            AIExtensionPublication.extension_key == row.extension_key,
        )
    )
    if current is None:
        session.add(
            AIExtensionPublication(
                extension_type=row.extension_type,
                extension_key=row.extension_key,
                definition_id=row.id,
            )
        )
    else:
        old = session.get(AIExtensionDefinition, current.definition_id)
        if old is not None:
            old.status = "revoked"
        current.definition_id = row.id
        current.published_at = datetime.now(timezone.utc)
    session.flush()
    return row


def load_extension_snapshot(session: Session) -> ExtensionSnapshot:
    rows = session.scalars(
        select(AIExtensionDefinition)
        .join(
            AIExtensionPublication,
            AIExtensionPublication.definition_id == AIExtensionDefinition.id,
        )
        .where(AIExtensionDefinition.status == "active")
        .order_by(AIExtensionDefinition.extension_type, AIExtensionDefinition.extension_key)
    ).all()
    definitions = tuple(
        ExtensionDefinition(
            extension_type=row.extension_type,
            extension_key=row.extension_key,
            version=row.version,
            capability=row.capability,
            agent_names=tuple(row.agent_names or []),
            content=row.content,
            tool_ids=tuple(row.tool_ids or []),
            side_effect=row.side_effect,
            metadata=row.metadata_json or {},
        )
        for row in rows
    )
    return ExtensionSnapshot("shopmind-extensions.persisted.v1", definitions)


__all__ = ["load_extension_snapshot", "persist_extension", "publish_extension"]
