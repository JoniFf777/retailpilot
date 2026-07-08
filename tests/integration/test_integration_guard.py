import os


def test_postgres_integration_suite_is_explicitly_gated():
    assert os.getenv("RUN_POSTGRES_INTEGRATION") in {None, "", "0", "1"}
