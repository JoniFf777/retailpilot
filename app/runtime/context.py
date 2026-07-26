"""Bounded, owner-scoped memory loading for one runtime invocation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.repositories.runtime_conversations import (
    get_conversation_thread,
    list_conversation_messages,
    list_conversation_summaries,
)
from app.repositories.runtime_memory import list_memory_records

from .contracts import (
    ContextSlice,
    MemoryItem,
    MemoryKind,
    MemoryReference,
    MemoryScope,
    RunContext,
)


DEFAULT_CONTEXT_TOKEN_BUDGET = 2048


def estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


class RuntimeContextManager:
    """Build a deterministic context slice without automatic memory promotion."""

    def __init__(
        self,
        session_factory: Callable[[], Session] | None = None,
        *,
        default_token_budget: int = DEFAULT_CONTEXT_TOKEN_BUDGET,
        max_messages: int = 30,
        max_summaries: int = 10,
        max_memory_records: int = 50,
    ) -> None:
        self._session_factory = session_factory
        self._default_token_budget = default_token_budget
        self._max_messages = max_messages
        self._max_summaries = max_summaries
        self._max_memory_records = max_memory_records

    def build(self, context: RunContext) -> ContextSlice:
        candidates = self._current_turn_item(context)
        if self._session_factory is not None:
            with self._session_factory() as session:
                candidates.extend(self._load_persisted_items(session, context))

        deduplicated = self._deduplicate(candidates)
        budget = context.budget.max_prompt_tokens or self._default_token_budget
        selected: list[MemoryItem] = []
        estimated_tokens = 0
        for item in sorted(
            deduplicated,
            key=lambda value: (value.priority, value.created_at),
            reverse=True,
        ):
            if selected and estimated_tokens + item.token_estimate > budget:
                continue
            selected.append(item)
            estimated_tokens += item.token_estimate

        selected.sort(key=lambda value: value.created_at)
        rendered_text = "\n".join(
            f"[{self._enum_value(item.kind)}/{self._enum_value(item.scope)}] {item.content}"
            for item in selected
        )
        context.memory_references = [
            MemoryReference(
                ref_id=item.memory_id,
                ref_type=self._enum_value(item.kind),
                scope=self._enum_value(item.scope),
                thread_id=item.thread_id,
                metadata={"priority": item.priority},
            )
            for item in selected
        ]
        return ContextSlice(
            items=selected,
            rendered_text=rendered_text,
            token_budget=budget,
            estimated_tokens=estimated_tokens,
            omitted_count=max(0, len(deduplicated) - len(selected)),
            metadata={"candidate_count": len(candidates), "deduplicated_count": len(deduplicated)},
        )

    def _current_turn_item(self, context: RunContext) -> list[MemoryItem]:
        if not context.request.input_text:
            return []
        return [
            MemoryItem(
                memory_id=f"request:{context.request.request_id}",
                kind=MemoryKind.WORKING,
                scope=MemoryScope.THREAD,
                user_id=context.user_id,
                thread_id=context.runtime_thread_id,
                content=context.request.input_text,
                priority=1000,
                token_estimate=estimate_tokens(context.request.input_text),
                provenance={"source": "current_request"},
            )
        ]

    def _load_persisted_items(
        self,
        session: Session,
        context: RunContext,
    ) -> list[MemoryItem]:
        thread = get_conversation_thread(
            session,
            runtime_thread_id=context.runtime_thread_id,
            user_id=context.user_id,
        )
        if thread is None:
            return []
        thread_id = thread["thread_id"]
        items: list[MemoryItem] = []
        for message in list_conversation_messages(
            session,
            thread_id=thread_id,
            user_id=context.user_id,
            limit=self._max_messages,
        ):
            if not message["content_text"]:
                continue
            items.append(
                MemoryItem(
                    memory_id=message["message_id"],
                    kind=MemoryKind.WORKING,
                    scope=MemoryScope.THREAD,
                    user_id=message["user_id"],
                    thread_id=thread_id,
                    content=message["content_text"],
                    priority=80 if message["role"] == "user" else 60,
                    token_estimate=estimate_tokens(message["content_text"]),
                    provenance={"source": "conversation_message", "sequence": message["sequence"]},
                    created_at=self._as_utc(message["created_at"]),
                    expires_at=message["expires_at"],
                )
            )
        for summary in list_conversation_summaries(
            session,
            thread_id=thread_id,
            user_id=context.user_id,
            status="active",
        )[: self._max_summaries]:
            items.append(
                MemoryItem(
                    memory_id=summary["summary_id"],
                    kind=MemoryKind.EPISODIC,
                    scope=MemoryScope.THREAD,
                    user_id=summary["user_id"],
                    thread_id=thread_id,
                    content=summary["summary_text"],
                    priority=70,
                    token_estimate=estimate_tokens(summary["summary_text"]),
                    provenance={"source": "conversation_summary"},
                    created_at=self._as_utc(summary["created_at"]),
                    expires_at=summary["expires_at"],
                )
            )
        include_operational = bool(
            context.policy.metadata.get("include_operational_memory", False)
        )
        for record in list_memory_records(
            session,
            user_id=context.user_id,
            thread_id=thread_id,
            include_operational=include_operational,
            limit=self._max_memory_records,
        ):
            try:
                kind = MemoryKind(record["kind"])
                scope = MemoryScope(record["scope"])
            except ValueError:
                continue
            items.append(
                MemoryItem(
                    memory_id=record["memory_id"],
                    kind=kind,
                    scope=scope,
                    user_id=record["user_id"],
                    thread_id=record["thread_id"],
                    content=record["content"],
                    priority=record["priority"],
                    token_estimate=record["token_count"] or estimate_tokens(record["content"]),
                    provenance=record["provenance"],
                    confidence=record["confidence"],
                    created_at=self._as_utc(record["created_at"]),
                    expires_at=record["expires_at"],
                    metadata=record["content_json"],
                )
            )
        return items

    @staticmethod
    def _deduplicate(items: list[MemoryItem]) -> list[MemoryItem]:
        by_content: dict[str, MemoryItem] = {}
        for item in items:
            key = " ".join(item.content.lower().split())
            previous = by_content.get(key)
            if previous is None or item.priority > previous.priority:
                by_content[key] = item
        return list(by_content.values())

    @staticmethod
    def _enum_value(value: object) -> str:
        return str(getattr(value, "value", value))

    @staticmethod
    def _as_utc(value: datetime | None) -> datetime:
        if value is None:
            return datetime.now(timezone.utc)
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
