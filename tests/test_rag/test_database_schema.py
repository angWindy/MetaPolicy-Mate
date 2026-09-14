from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from src.db.models import Base, Chunk
from src.db.session import Database
from src.rag.config import RAGSettings
from src.services.embeddings import content_hash_for_text

ROOT = Path(__file__).resolve().parents[2]


def test_database_schema_has_no_duplicate_indexes():
    for table in Base.metadata.tables.values():
        names: set[str] = set()
        column_sets: set[tuple[str, ...]] = set()

        for index in table.indexes:
            columns = tuple(column.name for column in index.columns)
            assert index.name not in names, f"duplicate index name on {table.name}: {index.name}"
            assert columns not in column_sets, f"duplicate index columns on {table.name}: {columns}"
            names.add(index.name)
            column_sets.add(columns)


def test_database_create_all_is_idempotent_on_clean_sqlite(tmp_path):
    database = Database(
        RAGSettings(
            app_env="test",
            database_url="sqlite://",
            data_dir=tmp_path,
            vector_backend="memory",
            generator_provider="template",
            embedding_provider="hash",
        )
    )

    database.create_all()
    database.create_all()

    table_names = set(inspect(database.engine).get_table_names())
    assert {"documents", "document_versions", "sections", "chunks"} <= table_names
    assert {"ingestion_jobs", "approval_records", "access_policies", "document_relations"} <= table_names


def test_chunk_content_hash_column_fits_algorithm_qualified_sha256():
    qualified_hash = content_hash_for_text("regression")

    assert len(qualified_hash) == 71
    assert Chunk.__table__.c.content_hash.type.length >= len(qualified_hash)


def test_alembic_history_is_deterministic_and_revision_ids_fit_postgresql():
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    revisions = list(ScriptDirectory.from_config(config).walk_revisions())

    # NOTE: The migration list was updated when new schemas were added
    # (0050_add_documents_school_id.py, cc0902b4e6c6_add_unique_document_number_index.py).
    # If you add another migration, update this expected ordering too.
    # ``walk_revisions`` returns revisions in reverse chronological order
    # (newest first), so [0] is the most recent migration.
    actual_revisions = [revision.revision for revision in revisions]
    assert len(actual_revisions) >= 4, (
        f"Expected at least 4 migrations, got {actual_revisions}"
    )
    assert actual_revisions[0] == "0050_add_documents_school_id"
    assert actual_revisions[-1] == "0001_initial"
    assert all(len(revision.revision) <= 32 for revision in revisions)

    initial_source = (ROOT / "migrations" / "versions" / "0001_initial.py").read_text(
        encoding="utf-8"
    )
    assert "Base.metadata" not in initial_source
    assert "src.db.models" not in initial_source
