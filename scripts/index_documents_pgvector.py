"""Index TechHub markdown documents into the PostgreSQL pgvector table."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Literal

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.db.models import Document


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOCUMENTS_DIR = PROJECT_ROOT / "data" / "documents"
DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200

DocType = Literal["product", "policy"]
DocTypeFilter = Literal["all", "product", "policy"]


@dataclass(frozen=True)
class SourceDocument:
    content: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class DocumentChunk:
    content: str
    metadata: dict[str, Any]


def _extract_title(content: str) -> str | None:
    first_line = content.splitlines()[0] if content.splitlines() else ""
    if first_line.startswith("# "):
        return first_line[2:].strip()
    return None


def _load_product_documents(documents_dir: Path) -> list[SourceDocument]:
    product_docs: list[SourceDocument] = []
    products_dir = documents_dir / "products"
    for md_file in sorted(products_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        product_id = md_file.stem
        product_docs.append(
            SourceDocument(
                content=content,
                metadata={
                    "doc_type": "product",
                    "source_path": str(md_file),
                    "source_name": md_file.name,
                    "product_id": product_id,
                    "product_name": _extract_title(content),
                    "policy_name": None,
                },
            )
        )
    return product_docs


def _load_policy_documents(documents_dir: Path) -> list[SourceDocument]:
    policy_docs: list[SourceDocument] = []
    policies_dir = documents_dir / "policies"
    for md_file in sorted(policies_dir.glob("*.md")):
        content = md_file.read_text(encoding="utf-8")
        policy_docs.append(
            SourceDocument(
                content=content,
                metadata={
                    "doc_type": "policy",
                    "source_path": str(md_file),
                    "source_name": md_file.name,
                    "product_id": None,
                    "product_name": None,
                    "policy_name": md_file.stem,
                },
            )
        )
    return policy_docs


def load_source_documents(
    documents_dir: Path = DEFAULT_DOCUMENTS_DIR,
    doc_type: DocTypeFilter = "all",
) -> list[SourceDocument]:
    """Load markdown source documents without creating embeddings."""
    documents_dir = Path(documents_dir)
    documents: list[SourceDocument] = []
    if doc_type in {"all", "product"}:
        documents.extend(_load_product_documents(documents_dir))
    if doc_type in {"all", "policy"}:
        documents.extend(_load_policy_documents(documents_dir))
    return documents


def split_documents(
    source_documents: Iterable[SourceDocument],
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[DocumentChunk]:
    """Split source documents into chunks while preserving metadata."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        add_start_index=True,
    )
    chunks: list[DocumentChunk] = []
    for source_document in source_documents:
        split_texts = splitter.create_documents(
            [source_document.content], metadatas=[source_document.metadata]
        )
        for chunk_index, split_text in enumerate(split_texts):
            metadata = dict(split_text.metadata)
            metadata["chunk_index"] = chunk_index
            chunks.append(
                DocumentChunk(
                    content=split_text.page_content,
                    metadata=metadata,
                )
            )
    return chunks


def get_chunk_counts(chunks: Iterable[DocumentChunk]) -> dict[str, int]:
    counts = {"product": 0, "policy": 0, "total": 0}
    for chunk in chunks:
        doc_type = chunk.metadata["doc_type"]
        counts[doc_type] += 1
        counts["total"] += 1
    return counts


def get_embedding_model_name(provider: str) -> str:
    if provider == "openai":
        return "text-embedding-3-small"
    return "sentence-transformers/all-mpnet-base-v2"


def _format_pgvector(values: list[float]) -> str:
    return "[" + ",".join(str(value) for value in values) + "]"


def clear_documents(session: Session, doc_type: DocTypeFilter = "all") -> int:
    statement = delete(Document)
    if doc_type != "all":
        statement = statement.where(Document.doc_type == doc_type)
    result = session.execute(statement)
    session.flush()
    return result.rowcount or 0


def index_chunks(
    session: Session,
    chunks: list[DocumentChunk],
    embeddings: Any,
    *,
    embedding_provider: str,
    embedding_model: str,
) -> int:
    """Create embeddings and write document chunks into PostgreSQL."""
    vectors = embeddings.embed_documents([chunk.content for chunk in chunks])
    for chunk, vector in zip(chunks, vectors):
        metadata = chunk.metadata
        session.add(
            Document(
                doc_type=metadata["doc_type"],
                source_path=metadata["source_path"],
                source_name=metadata.get("source_name"),
                product_id=metadata.get("product_id"),
                product_name=metadata.get("product_name"),
                policy_name=metadata.get("policy_name"),
                chunk_index=metadata["chunk_index"],
                content=chunk.content,
                metadata_json=metadata,
                embedding=_format_pgvector(vector),
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
            )
        )
    session.flush()
    return len(chunks)


def print_index_summary(
    source_documents: list[SourceDocument],
    chunks: list[DocumentChunk],
) -> None:
    product_docs = [
        doc for doc in source_documents if doc.metadata["doc_type"] == "product"
    ]
    policy_docs = [
        doc for doc in source_documents if doc.metadata["doc_type"] == "policy"
    ]
    counts = get_chunk_counts(chunks)
    print(f"读取 product markdown：{len(product_docs)} 个")
    print(f"读取 policy markdown：{len(policy_docs)} 个")
    print(f"切分 product chunks：{counts['product']} 条")
    print(f"切分 policy chunks：{counts['policy']} 条")
    print(f"总 chunks：{counts['total']} 条")


def run_index(
    *,
    clear: bool = False,
    dry_run: bool = False,
    doc_type: DocTypeFilter = "all",
    documents_dir: Path = DEFAULT_DOCUMENTS_DIR,
    session_factory: Callable[[], Session] | None = None,
    embeddings_factory: Callable[[str], Any] | None = None,
) -> list[DocumentChunk]:
    source_documents = load_source_documents(documents_dir, doc_type)
    chunks = split_documents(source_documents)
    print_index_summary(source_documents, chunks)

    if dry_run:
        print("dry-run：未连接 PostgreSQL，未生成 embeddings，未写入 documents 表")
        return chunks

    settings = get_settings()
    embedding_provider = settings.embedding_provider
    embedding_model = get_embedding_model_name(embedding_provider)

    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal
    if embeddings_factory is None:
        from data.data_generation.build_vectorstore import get_embeddings

        embeddings_factory = get_embeddings

    session = session_factory()
    try:
        if clear:
            deleted_count = clear_documents(session, doc_type)
            print(f"已清空 documents：{deleted_count} 条")

        embeddings = embeddings_factory(embedding_provider)
        inserted_count = index_chunks(
            session,
            chunks,
            embeddings,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
        )
        session.commit()
        print(f"导入 documents：{inserted_count} 条")
        print("pgvector documents index 完成")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    return chunks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Index TechHub markdown documents into PostgreSQL pgvector."
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="先清空 documents 表中对应 doc-type 的记录再导入。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只读取和切分 markdown，不连接数据库、不生成 embeddings。",
    )
    parser.add_argument(
        "--doc-type",
        choices=["all", "product", "policy"],
        default="all",
        help="选择要索引的文档类型。",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_index(clear=args.clear, dry_run=args.dry_run, doc_type=args.doc_type)


if __name__ == "__main__":
    main()
