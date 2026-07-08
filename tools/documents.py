"""
Documents tools for searching TechHub product documentation and policies.

These tools provide semantic search over PostgreSQL + pgvector documents:
- Product documentation (specs, features, setup guides)
- Store policies (returns, warranties, shipping)
- Metadata filtering through the repository layer

Tools use response_format="content_and_artifact" to return both:
- Formatted content string for the LLM
- Raw Document objects as artifacts for downstream processing and LangSmith tracing
"""

from contextlib import contextmanager
from typing import Any, Sequence

from langchain_core.documents import Document
from langchain_core.tools import tool

from app.core.settings import get_settings
from app.repositories import documents as document_repository

# Module-level embedding model (lazy loaded)
_embeddings = None


@contextmanager
def _get_document_session():
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_embeddings():
    """Lazy load the configured embedding model."""
    global _embeddings
    if _embeddings is None:
        from data.data_generation.build_vectorstore import get_embeddings as build_embeddings

        settings = get_settings()
        _embeddings = build_embeddings(settings.embedding_provider)
    return _embeddings


def _embed_query(query: str) -> Sequence[float]:
    return get_embeddings().embed_query(query)


def _document_dict_to_langchain_document(document: dict[str, Any]) -> Document:
    metadata = dict(document.get("metadata") or {})
    for key in (
        "doc_type",
        "source_path",
        "source_name",
        "product_id",
        "product_name",
        "policy_name",
        "chunk_index",
        "embedding_provider",
        "embedding_model",
    ):
        value = document.get(key)
        if value is not None:
            metadata.setdefault(key, value)
    if "score" in document:
        metadata["score"] = document["score"]
    return Document(page_content=document["content"], metadata=metadata)


def _fetch_product_documents(query: str) -> list[Document]:
    query_embedding = _embed_query(query)
    with _get_document_session() as session:
        results = document_repository.search_product_documents(
            session, query_embedding, k=3
        )
    return [_document_dict_to_langchain_document(result) for result in results]


def _fetch_policy_documents(query: str) -> list[Document]:
    query_embedding = _embed_query(query)
    with _get_document_session() as session:
        results = document_repository.search_policy_documents(
            session, query_embedding, k=2
        )
    return [_document_dict_to_langchain_document(result) for result in results]


@tool(response_format="content_and_artifact")
def search_product_docs(query: str) -> tuple[str, list[Document]]:
    """Search product documentation for specifications, features, and details.

    Use this tool when users ask about:
    - Product specifications (CPU, RAM, storage, ports, etc.)
    - Features and capabilities
    - Setup and usage instructions
    - Technical details
    - Product comparisons

    Args:
        query: What to search for (e.g., "USB-C ports on MacBook", "Sony headphone battery life")

    Returns:
        Tuple of (formatted_content, documents) where:
        - formatted_content: Clean string for the LLM with product info
        - documents: List of raw Document objects for downstream use and tracing
    """
    results = _fetch_product_documents(query)

    if not results:
        return "No relevant product documentation found.", []

    # Format results with sources for the LLM
    formatted_results = []
    for doc in results:
        product_name = doc.metadata.get("product_name", "Unknown Product")
        product_id = doc.metadata.get("product_id", "")
        formatted_results.append(f"[{product_name} ({product_id})]\n{doc.page_content}")

    # Return tuple: (content for LLM, raw docs as artifact)
    return "\n\n---\n\n".join(formatted_results), results


@tool(response_format="content_and_artifact")
def search_policy_docs(query: str) -> tuple[str, list[Document]]:
    """Search store policies including returns, warranties, and shipping information.

    Use this tool when users ask about:
    - Return and refund policies
    - Warranty coverage and terms
    - Shipping information and timelines
    - Customer support policies
    - General store policies

    Args:
        query: What policy information to find (e.g., "return policy", "warranty coverage", "shipping times")

    Returns:
        Tuple of (formatted_content, documents) where:
        - formatted_content: Clean string for the LLM with policy info
        - documents: List of raw Document objects for downstream use and tracing
    """
    results = _fetch_policy_documents(query)

    if not results:
        return "No relevant policy information found.", []

    # Format results with sources for the LLM
    formatted_results = []
    for doc in results:
        policy_name = doc.metadata.get("policy_name", "Unknown Policy")
        formatted_results.append(f"[{policy_name}]\n{doc.page_content}")

    # Return tuple: (content for LLM, raw docs as artifact)
    return "\n\n---\n\n".join(formatted_results), results
