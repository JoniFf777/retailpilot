from pathlib import Path


def test_v3_release_version_is_consistent() -> None:
    pyproject = Path("pyproject.toml").read_text()
    readme = Path("README.md").read_text()
    release_notes = Path("docs/v3_release_notes.md").read_text()
    summary = Path("docs/v3_multi_agent_handoff_summary.md").read_text()

    assert 'version = "3.0.0"' in pyproject
    assert "ShopMind V3.0.0" in readme
    assert "Tag: `v3.0.0`" in release_notes
    assert "# V3.0.0 Multi-Agent Handoff Release Summary" in summary


def test_v3_release_notes_capture_validation_and_boundaries() -> None:
    release_notes = Path("docs/v3_release_notes.md").read_text()

    for expected in (
        "227 passed, 4 skipped",
        "10/10",
        "3/3",
        "shopmind-v3-handoff-ef66ba2f",
        "6/6",
        "## Known Boundaries",
        "## Next Release Line",
    ):
        assert expected in release_notes
