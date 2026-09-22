"""Import the trusted ShopMind shopping-evidence corpus through its pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import select

from app.ai_platform.ingestion import load_legacy_sources
from app.ai_platform.ingestion import ShoppingEvidencePipeline
from app.ai_platform.indexing import PostgreSQLEvidenceIndexer
from app.catalog.models import CatalogCategory, CatalogProduct
from app.core.settings import get_settings
from app.db.session import SessionLocal
from app.repositories.shopping_evidence import evidence_operational_snapshot


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ingest trusted ShopMind shopping evidence.")
    parser.add_argument("--documents-dir", type=Path, default=PROJECT_ROOT / "data" / "documents")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    sources = load_legacy_sources(args.documents_dir)
    if args.limit > 0:
        sources = sources[: args.limit]
    print({"sources": len(sources), "dry_run": args.dry_run})
    if args.dry_run:
        return 0
    settings = get_settings()
    from data.data_generation.build_vectorstore import get_embeddings

    session = SessionLocal()
    try:
        embeddings = get_embeddings(settings.embedding_provider)
        known_product_ids = set(
            session.scalars(
                select(CatalogProduct.legacy_product_id).where(
                    CatalogProduct.legacy_product_id.is_not(None)
                )
            ).all()
        )
        known_categories = set(
            session.scalars(
                select(CatalogCategory.code).where(CatalogCategory.status == "active")
            ).all()
        )
        indexer = PostgreSQLEvidenceIndexer(
            session,
            embeddings,
            embedding_provider=settings.embedding_provider,
            embedding_model="sentence-transformers/all-mpnet-base-v2",
        )
        pipeline = ShoppingEvidencePipeline(
            indexer,
            known_product_ids=known_product_ids,
            known_categories=known_categories,
        )
        for descriptor, content in sources:
            pipeline.run(session, descriptor, content)
            session.commit()
        print(evidence_operational_snapshot(session))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
