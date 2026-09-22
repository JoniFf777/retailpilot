"""Stable server-owned prompt slots for ShopMind's shopping agents."""

from __future__ import annotations

from enum import StrEnum

from app.ai_platform.extensions import ExtensionRegistry


class PromptSlot(StrEnum):
    SUPERVISOR = "supervisor"
    PLANNER = "planner"
    PRODUCT = "product"
    RAG = "rag"
    PREFERENCE = "preference"
    DECISION = "decision"


BUILTIN_PROMPTS: dict[PromptSlot, str] = {
    PromptSlot.SUPERVISOR: "Route shopping requests to read-only specialists.",
    PromptSlot.PLANNER: "Preserve the server-compiled read plan.",
    PromptSlot.PRODUCT: "Use Catalog as the source of SKU, price, and inventory truth.",
    PromptSlot.RAG: "Return scoped shopping evidence and never invent policy facts.",
    PromptSlot.PREFERENCE: "Read owner preferences without writing them.",
    PromptSlot.DECISION: "Synthesize validated Catalog and evidence results.",
}


def validate_prompt_candidate(slot: PromptSlot | str, content: str) -> None:
    """Run a small deterministic contract gate before a Prompt is activated."""

    normalized = PromptSlot(slot)
    text = content.strip()
    if not text or len(text) > 100_000:
        raise ValueError("Prompt content is empty or exceeds its bound.")
    required = {
        PromptSlot.PRODUCT: ("Catalog",),
        PromptSlot.RAG: ("evidence",),
        PromptSlot.PREFERENCE: ("preference",),
        PromptSlot.DECISION: ("Catalog",),
        PromptSlot.SUPERVISOR: ("read",),
        PromptSlot.PLANNER: ("plan",),
    }[normalized]
    if not all(token.casefold() in text.casefold() for token in required):
        raise ValueError("Prompt candidate failed its deterministic contract gate.")
    if any(
        token in text.casefold()
        for token in ("ignore tool policy", "bypass hitl", "disable confirmation")
    ):
        raise ValueError("Prompt candidate attempts to weaken a safety boundary.")


def resolve_prompt(
    slot: PromptSlot | str, registry: ExtensionRegistry | None = None
) -> str:
    normalized = PromptSlot(slot)
    if registry is not None:
        for definition in registry.enabled_for("prompt"):
            if (
                definition.extension_key == normalized.value
                and definition.content.strip()
            ):
                return definition.content
    return BUILTIN_PROMPTS[normalized]


__all__ = [
    "BUILTIN_PROMPTS",
    "PromptSlot",
    "resolve_prompt",
    "validate_prompt_candidate",
]
