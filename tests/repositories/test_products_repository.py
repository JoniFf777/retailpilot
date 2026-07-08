from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import Product
from app.repositories.products import (
    get_product_detail,
    get_products_by_ids,
    search_products,
)


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def seed_products(session):
    session.add_all(
        [
            Product(
                product_id="TECH-LAP-001",
                name="MacBook Air M2",
                category="Laptops",
                price=1199.00,
                in_stock=True,
            ),
            Product(
                product_id="TECH-LAP-002",
                name="ThinkPad X1",
                category="Laptops",
                price=1499.00,
                in_stock=False,
            ),
            Product(
                product_id="TECH-ACC-001",
                name="USB-C Hub",
                category="Accessories",
                price=49.00,
                in_stock=True,
            ),
        ]
    )
    session.commit()


def test_search_products_supports_query_price_and_stock_filter():
    session = make_session()
    seed_products(session)

    products = search_products(session, query="laptop", max_price=1300)

    assert [product["product_id"] for product in products] == ["TECH-LAP-001"]


def test_get_product_detail_supports_id_and_fuzzy_name():
    session = make_session()
    seed_products(session)

    by_id = get_product_detail(session, "TECH-ACC-001")
    by_name = get_product_detail(session, "MacBook")
    missing = get_product_detail(session, "NO-SUCH-PRODUCT")

    assert by_id["name"] == "USB-C Hub"
    assert by_name["product_id"] == "TECH-LAP-001"
    assert missing is None


def test_get_products_by_ids_returns_existing_products_in_order():
    session = make_session()
    seed_products(session)

    products = get_products_by_ids(
        session, ["TECH-ACC-001", "NO-SUCH-PRODUCT", "TECH-LAP-001"]
    )

    assert [product["product_id"] for product in products] == [
        "TECH-ACC-001",
        "TECH-LAP-001",
    ]
