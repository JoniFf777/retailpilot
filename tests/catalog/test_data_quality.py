from pathlib import Path

from scripts.validate_shopmind_catalog import DEFAULT_SEEDS, validate_catalog_files


def test_managed_electronics_seed_quality_is_valid() -> None:
    report = validate_catalog_files(DEFAULT_SEEDS)

    assert report["valid"] is True
    assert report["counts"]["categories"] == 10
    assert report["counts"]["products"] == 88
    assert report["counts"]["skus"] == 88
    assert report["categories"]["laptop"]["docs"] == 9
    assert report["categories"]["monitor"]["docs"] == 7
    for category in ("phone", "tablet", "keyboard", "mouse", "headphones", "speaker", "camera", "router"):
        assert report["categories"][category]["products"] == 9
        assert report["categories"][category]["docs"] == 9
    assert report["issues"] == []


def test_validator_reports_duplicate_identifier_deterministically(tmp_path: Path) -> None:
    laptop_seed = Path(__file__).resolve().parents[2] / "data" / "catalog" / "laptop_catalog.json"
    source = laptop_seed.read_text(encoding="utf-8")
    duplicate = source.replace("LAP-MBA-M2-13", "LAP-HP-PAV-15", 1)
    seed_path = tmp_path / "duplicate.json"
    seed_path.write_text(duplicate, encoding="utf-8")

    report = validate_catalog_files((seed_path,), docs_dir=Path("data/documents/products"))

    assert report["valid"] is False
    assert any(issue["code"] == "duplicate_product_code" for issue in report["issues"])
    assert report["issues"] == sorted(
        report["issues"], key=lambda issue: (issue["code"], issue["path"], issue["detail"])
    )
