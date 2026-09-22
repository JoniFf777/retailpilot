from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ai_platform.extensions import ExtensionDefinition
from app.db.base import Base
from app.repositories.ai_extensions import (
    load_extension_snapshot,
    persist_extension,
    publish_extension,
)


def test_extension_repository_publishes_and_reloads_snapshot():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    definition = ExtensionDefinition(
        extension_type="prompt",
        extension_key="decision",
        version=1,
        capability="shopping",
        content="Use Catalog facts and cite evidence.",
    )
    row = persist_extension(session, definition)
    publish_extension(session, row.id)
    session.commit()
    snapshot = load_extension_snapshot(session)
    assert snapshot.definitions[0].extension_key == "decision"
