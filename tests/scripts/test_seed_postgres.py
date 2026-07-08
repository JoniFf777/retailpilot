from pathlib import Path

import pytest

from scripts.seed_postgres import get_seed_counts, load_seed_data, run_seed


FIXTURE_DATA_DIR = Path(__file__).parent / "fixtures" / "seed_postgres"


def test_load_seed_data_reads_json_counts() -> None:
    seed_data = load_seed_data(FIXTURE_DATA_DIR)

    assert get_seed_counts(seed_data) == {
        "customers": 1,
        "products": 2,
        "orders": 1,
        "order_items": 1,
    }


def test_dry_run_prints_counts_without_connecting(
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_if_called():
        raise AssertionError("dry-run should not create a database session")

    run_seed(data_dir=FIXTURE_DATA_DIR, dry_run=True, session_factory=fail_if_called)

    output = capsys.readouterr().out
    assert "读取 customers.json：1 条" in output
    assert "读取 products.json：2 条" in output
    assert "读取 orders.json：1 条" in output
    assert "读取 order_items.json：1 条" in output
    assert "dry-run：未写入 PostgreSQL" in output
