from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase


# Pin every table declared on this Base to the ``public`` schema so
# queries always resolve ``documents`` / ``document_versions`` etc.
# explicitly to ``public.*`` — independent of the connection's
# ``search_path``. Without this, SQLAlchemy emits the table name
# unqualified and PostgreSQL falls back to whichever schema in the
# connection's search_path owns the table (which can be
# ``rag_legacy.documents`` after a recycled pooled connection from
# the RAG runtime) and the query then fails with
# ``column documents.effective_date does not exist``.
metadata = MetaData(schema="public")


class Base(DeclarativeBase):
    metadata = metadata