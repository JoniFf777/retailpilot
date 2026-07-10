"""Read-only smoke checks for the ShopMind V2 PostgreSQL database."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import func, inspect, select, text
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.db.models import (
    Customer,
    Document,
    Order,
    OrderItem,
    Product,
)
from app.repositories import documents as document_repository
from app.repositories import products as product_repository


EXPECTED_ALEMBIC_VERSION = "0003_candidate_contexts"
STRUCTURED_TABLES = {
    "customers": Customer,
    "products": Product,
    "orders": Order,
    "order_items": OrderItem,
}
RUNTIME_TABLES = {
    "user_preferences",
    "cart_items",
    "pending_actions",
    "candidate_contexts",
}
DOCUMENT_TABLE = "documents"
REQUIRED_TABLES = set(STRUCTURED_TABLES) | RUNTIME_TABLES | {DOCUMENT_TABLE}


@dataclass(frozen=True)
class SmokeReport:
    database_url: str
    database_name: str
    database_user: str
    alembic_version: str
    table_counts: dict[str, int]
    document_counts: dict[str, int]
    product_search_count: int
    product_document_count: int
    policy_document_count: int


def _mask_database_url(database_url: str) -> str:
    if "://" not in database_url or "@" not in database_url:
        return database_url
    scheme, rest = database_url.split("://", 1)
    credentials, host = rest.split("@", 1)
    username = credentials.split(":", 1)[0]
    return f"{scheme}://{username}:***@{host}"


def _build_query_embedding(dimension: int) -> list[float]:
    return [0.001] * dimension


def get_database_identity(session: Session) -> tuple[str, str]:
    row = session.execute(
        text("select current_database(), current_user")
    ).one()
    return row[0], row[1]


def get_alembic_version(session: Session) -> str:
    return session.execute(text("select version_num from alembic_version")).scalar_one()


def assert_required_tables_exist(session: Session) -> None:
    existing_tables = set(inspect(session.get_bind()).get_table_names())
    missing_tables = sorted(REQUIRED_TABLES - existing_tables)
    if missing_tables:
        raise RuntimeError(f"缺少 PostgreSQL 表：{', '.join(missing_tables)}")


def get_structured_counts(session: Session) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table_name, model in STRUCTURED_TABLES.items():
        counts[table_name] = session.scalar(
            select(func.count()).select_from(model)
        ) or 0
    return counts


def get_document_counts(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(Document.doc_type, func.count())
        .group_by(Document.doc_type)
        .order_by(Document.doc_type)
    ).all()
    return {str(doc_type): int(count) for doc_type, count in rows}


def assert_seed_data_present(table_counts: dict[str, int]) -> None:
    missing = [
        table_name for table_name, count in table_counts.items()
        if count <= 0
    ]
    if missing:
        raise RuntimeError(f"结构化 seed 数据为空：{', '.join(missing)}")


def assert_documents_present(document_counts: dict[str, int]) -> None:
    missing = [
        doc_type for doc_type in ("product", "policy")
        if document_counts.get(doc_type, 0) <= 0
    ]
    if missing:
        raise RuntimeError(f"documents 缺少 doc_type 数据：{', '.join(missing)}")


def run_repository_checks(session: Session, vector_dimension: int) -> tuple[int, int, int]:
    products = product_repository.search_products(session, query="keyboard", limit=2)
    query_embedding = _build_query_embedding(vector_dimension)
    product_docs = document_repository.search_product_documents(
        session, query_embedding, k=1
    )
    policy_docs = document_repository.search_policy_documents(
        session, query_embedding, k=1
    )
    if not products:
        raise RuntimeError("Repository 商品搜索未返回结果")
    if not product_docs:
        raise RuntimeError("Repository product documents 搜索未返回结果")
    if not policy_docs:
        raise RuntimeError("Repository policy documents 搜索未返回结果")
    return len(products), len(product_docs), len(policy_docs)


def run_tool_checks() -> None:
    from tools.documents import search_policy_docs
    from tools.products import search_products

    product_result = search_products.invoke({"query": "keyboard", "limit": 1})
    if "TECH-" not in product_result:
        raise RuntimeError("search_products Tool 未返回商品结果")

    content, documents = search_policy_docs.func("return policy")
    if not documents or not content:
        raise RuntimeError("search_policy_docs Tool 未返回文档结果")

    print(f"Tool 商品搜索：通过")
    print(f"Tool policy docs 搜索：{len(documents)} 条")


def run_smoke(
    *,
    session_factory: Callable[[], Session] | None = None,
    include_tools: bool = False,
) -> SmokeReport:
    settings = get_settings()
    if session_factory is None:
        from app.db.session import SessionLocal

        session_factory = SessionLocal

    session = session_factory()
    try:
        database_name, database_user = get_database_identity(session)
        alembic_version = get_alembic_version(session)
        if alembic_version != EXPECTED_ALEMBIC_VERSION:
            raise RuntimeError(
                f"Alembic version 不匹配：当前 {alembic_version}，期望 {EXPECTED_ALEMBIC_VERSION}"
            )

        assert_required_tables_exist(session)
        table_counts = get_structured_counts(session)
        document_counts = get_document_counts(session)
        assert_seed_data_present(table_counts)
        assert_documents_present(document_counts)
        product_count, product_doc_count, policy_doc_count = run_repository_checks(
            session, settings.vector_dimension
        )
    finally:
        session.close()

    report = SmokeReport(
        database_url=_mask_database_url(settings.database_url),
        database_name=database_name,
        database_user=database_user,
        alembic_version=alembic_version,
        table_counts=table_counts,
        document_counts=document_counts,
        product_search_count=product_count,
        product_document_count=product_doc_count,
        policy_document_count=policy_doc_count,
    )
    print_report(report)

    if include_tools:
        run_tool_checks()

    return report


def print_report(report: SmokeReport) -> None:
    print(f"连接数据库：{report.database_url}")
    print(f"当前数据库：{report.database_name}")
    print(f"当前用户：{report.database_user}")
    print(f"Alembic version：{report.alembic_version}")
    for table_name, count in report.table_counts.items():
        print(f"{table_name}：{count} 条")
    for doc_type, count in report.document_counts.items():
        print(f"documents[{doc_type}]：{count} 条")
    print(f"Repository 商品搜索：{report.product_search_count} 条")
    print(f"Repository product docs 搜索：{report.product_document_count} 条")
    print(f"Repository policy docs 搜索：{report.policy_document_count} 条")
    print("PostgreSQL smoke check 完成")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run read-only smoke checks against the configured V2 PostgreSQL database."
    )
    parser.add_argument(
        "--include-tools",
        action="store_true",
        help="额外调用 LangChain Tools；会加载 embedding model，耗时更长。",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    run_smoke(include_tools=args.include_tools)


if __name__ == "__main__":
    main()
