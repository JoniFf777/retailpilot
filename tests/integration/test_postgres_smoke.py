import os

import pytest

if os.getenv("RUN_POSTGRES_INTEGRATION") != "1":
    pytest.skip(
        "set RUN_POSTGRES_INTEGRATION=1 to run PostgreSQL integration smoke tests",
        allow_module_level=True,
    )

from scripts.smoke_postgres import EXPECTED_ALEMBIC_VERSION, run_smoke


def test_postgres_smoke_against_configured_database():
    report = run_smoke()

    assert report.alembic_version == EXPECTED_ALEMBIC_VERSION
    assert report.table_counts["customers"] > 0
    assert report.table_counts["products"] > 0
    assert report.document_counts["product"] > 0
    assert report.document_counts["policy"] > 0
