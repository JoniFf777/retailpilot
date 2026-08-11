"""Explicit real-PostgreSQL migration checks in a disposable schema."""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
    pytest.skip("set RUN_POSTGRES_INTEGRATION=1 for Catalog PostgreSQL migration checks", allow_module_level=True)

from app.core.settings import get_settings


def _alembic(connection):
    config = Config("alembic.ini")
    config.attributes["connection"] = connection
    return config


def test_catalog_migrations_round_trip_and_root_category_unique() -> None:
    """Exercise the Catalog-scoped 0008/0009 migration round-trip only.

    Current-head migration acceptance belongs to the Phase 3/4/5/6 PostgreSQL
    suites; this test intentionally does not upgrade an artificial Catalog
    baseline through later non-Catalog revisions.
    """
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    schema = f"shopmind_catalog_test_{uuid4().hex}"
    try:
        with engine.connect() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.commit()
            print({"migration_schema": schema, "lifecycle": "create → migrate → drop cascade"})
            connection.execute(text(f'SET search_path TO "{schema}", public'))
            # Keep Alembic from falling through to shared public.alembic_version
            # while bootstrapping this private schema from revision None.
            connection.execute(
                text(
                    f'CREATE TABLE "{schema}".alembic_version '
                    '(version_num VARCHAR(32) NOT NULL PRIMARY KEY)'
                )
            )
            connection.commit()
            # Build a real 0007 baseline. Stamping an empty schema would hide
            # the fact that 0010 alters the legacy pending_actions table.
            command.upgrade(_alembic(connection), "0007_governance_audit")
            baseline_tables = set(inspect(connection).get_table_names(schema=schema))
            assert "pending_actions" in baseline_tables
            command.upgrade(_alembic(connection), "0008_shopmind_catalog_identity")
            assert {"shopmind_categories", "shopmind_attribute_definitions", "shopmind_products"}.issubset(inspect(connection).get_table_names(schema=schema))
            first_id = uuid4()
            second_id = uuid4()
            connection.execute(text(f"INSERT INTO shopmind_categories (id, code, name, status, managed_by_seed) VALUES ('{first_id}', 'laptop', 'Laptop', 'active', false)"))
            with pytest.raises(IntegrityError):
                connection.execute(text(f"INSERT INTO shopmind_categories (id, code, name, status, managed_by_seed) VALUES ('{second_id}', 'laptop', 'Duplicate', 'active', false)"))
            connection.rollback()
            connection.execute(text(f'SET search_path TO "{schema}", public'))
            connection.commit()
            command.downgrade(_alembic(connection), "0007_governance_audit")
            assert not set(inspect(connection).get_table_names(schema=schema)).intersection({"shopmind_categories", "shopmind_attribute_definitions", "shopmind_products"})
            command.upgrade(_alembic(connection), "0008_shopmind_catalog_identity")
            command.upgrade(_alembic(connection), "0009_shopmind_skus_inventory")
            assert {"shopmind_categories", "shopmind_attribute_definitions", "shopmind_products", "shopmind_product_skus", "shopmind_inventory"}.issubset(inspect(connection).get_table_names(schema=schema))
            command.downgrade(_alembic(connection), "0008_shopmind_catalog_identity")
            assert {"shopmind_product_skus", "shopmind_inventory"}.isdisjoint(inspect(connection).get_table_names(schema=schema))
            # This is the Catalog-scoped 0008/0009 test, not current-head
            # migration acceptance. Later revisions are covered by the real
            # Phase 3/4/5/6 PostgreSQL suites.
            command.upgrade(_alembic(connection), "0009_shopmind_skus_inventory")
            assert MigrationContext.configure(connection).get_current_revision() == "0009_shopmind_skus_inventory"
            command.current(_alembic(connection))
    finally:
        with engine.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.commit()
        engine.dispose()
