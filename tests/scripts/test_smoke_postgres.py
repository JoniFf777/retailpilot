from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Customer, Document, Order, OrderItem, Product
from scripts import smoke_postgres


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.execute(text("create table alembic_version (version_num varchar(32))"))
    session.execute(
        text("insert into alembic_version values (:version)"),
        {"version": smoke_postgres.EXPECTED_ALEMBIC_VERSION},
    )
    return session


def seed_smoke_data(session):
    session.add(
        Customer(
            customer_id="CUST-001",
            email="customer@example.com",
            name="Test Customer",
            phone=None,
            city="Seattle",
            state="WA",
            segment="Consumer",
        )
    )
    session.add(
        Product(
            product_id="TECH-KEY-001",
            name="Mechanical Keyboard",
            category="Keyboards",
            price=99.00,
            in_stock=True,
        )
    )
    session.add(
        Order(
            order_id="ORD-2026-0001",
            customer_id="CUST-001",
            order_date=date(2026, 1, 1),
            status="Processing",
            shipped_date=None,
            tracking_number=None,
            total_amount=99.00,
        )
    )
    session.add(
        OrderItem(
            order_id="ORD-2026-0001",
            product_id="TECH-KEY-001",
            quantity=1,
            price_per_unit=99.00,
        )
    )
    session.add_all(
        [
            Document(
                doc_type="product",
                source_path="data/documents/products/TECH-KEY-001.md",
                source_name="TECH-KEY-001.md",
                product_id="TECH-KEY-001",
                product_name="Mechanical Keyboard",
                policy_name=None,
                chunk_index=0,
                content="Keyboard documentation.",
                metadata_json={"doc_type": "product"},
                embedding="[0.1,0.2,0.3]",
                embedding_provider="huggingface",
                embedding_model="sentence-transformers/all-mpnet-base-v2",
            ),
            Document(
                doc_type="policy",
                source_path="data/documents/policies/return_policy.md",
                source_name="return_policy.md",
                product_id=None,
                product_name=None,
                policy_name="return_policy",
                chunk_index=0,
                content="Return policy documentation.",
                metadata_json={"doc_type": "policy"},
                embedding="[0.1,0.2,0.3]",
                embedding_provider="huggingface",
                embedding_model="sentence-transformers/all-mpnet-base-v2",
            ),
        ]
    )
    session.commit()


def test_mask_database_url_hides_password():
    masked = smoke_postgres._mask_database_url(
        "postgresql+psycopg://postgres:secret@127.0.0.1:5432/app"
    )

    assert masked == "postgresql+psycopg://postgres:***@127.0.0.1:5432/app"


def test_smoke_helpers_collect_counts_and_repository_results():
    session = make_session()
    seed_smoke_data(session)

    assert smoke_postgres.get_alembic_version(session) == (
        smoke_postgres.EXPECTED_ALEMBIC_VERSION
    )
    assert smoke_postgres.get_structured_counts(session) == {
        "customers": 1,
        "products": 1,
        "orders": 1,
        "order_items": 1,
    }
    assert smoke_postgres.get_document_counts(session) == {
        "policy": 1,
        "product": 1,
    }
    assert smoke_postgres.run_repository_checks(session, vector_dimension=3) == (
        1,
        1,
        1,
    )


def test_run_smoke_is_read_only_and_returns_report(monkeypatch, capsys):
    session = make_session()
    seed_smoke_data(session)

    monkeypatch.setattr(
        smoke_postgres,
        "get_database_identity",
        lambda session: ("sqlite-smoke", "test-user"),
    )

    report = smoke_postgres.run_smoke(session_factory=lambda: session)

    output = capsys.readouterr().out
    assert report.database_name == "sqlite-smoke"
    assert report.alembic_version == smoke_postgres.EXPECTED_ALEMBIC_VERSION
    assert report.table_counts["products"] == 1
    assert "PostgreSQL smoke check 完成" in output


def test_assert_seed_data_present_raises_for_empty_table():
    with pytest.raises(RuntimeError, match="结构化 seed 数据为空"):
        smoke_postgres.assert_seed_data_present(
            {
                "customers": 1,
                "products": 0,
                "orders": 1,
                "order_items": 1,
            }
        )
