from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(2000), nullable=False)
    document_number: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    issued_by: Mapped[str] = mapped_column(String(500), nullable=False)
    owner_department: Mapped[str] = mapped_column(String(200), nullable=False)
    access_level: Mapped[str] = mapped_column(String(30), nullable=False, default="internal")
    allowed_departments: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    versions: Mapped[list[DocumentVersion]] = relationship(back_populates="document", cascade="all, delete-orphan")


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "version_number", name="uq_document_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    issued_date: Mapped[date | None] = mapped_column(Date)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    legal_status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    processing_status: Mapped[str] = mapped_column(String(30), nullable=False, default="received")
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    source_path: Mapped[str] = mapped_column(String(2000), nullable=False)
    replaces_version_id: Mapped[str | None] = mapped_column(ForeignKey("document_versions.id"), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    approved_by: Mapped[str | None] = mapped_column(String(200))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    document: Mapped[Document] = relationship(back_populates="versions")
    sections: Mapped[list[Section]] = relationship(back_populates="version", cascade="all, delete-orphan")
    chunks: Mapped[list[Chunk]] = relationship(back_populates="version", cascade="all, delete-orphan")


class Section(Base):
    """Cấu trúc pháp lý đa cấp: Chương, Mục, Điều, Khoản, Điểm.

    Hỗ trợ cấu trúc cây qua parent_id self-reference (nullable). Với văn bản phẳng
    (đa số quy định chỉ có Điều/Khoản), heading_path JSON lưu đường dẫn phân cấp
    tương đương 'Chương II > Điều 5 > Khoản 2'.
    """

    __tablename__ = "sections"
    __table_args__ = (
        Index("ix_sections_version_id", "version_id"),
        Index("ix_sections_parent_id", "parent_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("sections.id", ondelete="SET NULL"), nullable=True
    )
    section_type: Mapped[str | None] = mapped_column(String(30))  # chapter | article | clause | point
    section_number: Mapped[str | None] = mapped_column(String(50))  # "II", "5", "2", "a"
    heading: Mapped[str | None] = mapped_column(String(1000))  # "Điều 5. Cán bộ được nghỉ phép"
    heading_path: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    content: Mapped[str] = mapped_column(Text, nullable=False)  # nội dung gốc, không qua chunking
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    version: Mapped[DocumentVersion] = relationship(back_populates="sections")
    parent: Mapped[Section | None] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list[Section]] = relationship(back_populates="parent", cascade="all, delete-orphan")
    chunks: Mapped[list[Chunk]] = relationship(back_populates="section")


class Chunk(Base):
    __tablename__ = "chunks"
    __table_args__ = (
        Index("ix_chunks_version_id", "version_id"),
        Index("ix_chunks_section_id", "section_id"),
    )

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[str | None] = mapped_column(ForeignKey("sections.id", ondelete="SET NULL"), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_text: Mapped[str] = mapped_column(Text, nullable=False)
    # ``content_hash_for_text`` stores the algorithm-qualified form
    # ``sha256:<64 hex chars>`` so PostgreSQL needs all 71 characters.
    content_hash: Mapped[str | None] = mapped_column(String(71), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime)

    version: Mapped[DocumentVersion] = relationship(back_populates="chunks")
    section: Mapped[Section | None] = relationship(back_populates="chunks")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str] = mapped_column(String(200), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    query: Mapped[str | None] = mapped_column(Text)
    resource_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class UserFeedback(Base):
    __tablename__ = "user_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(200), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class IngestionJob(Base):
    """Lịch sử xử lý ingestion, tách riêng để audit và retry độc lập."""

    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        Index("ix_ingestion_jobs_version_id", "version_id"),
        Index("ix_ingestion_jobs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="received"
    )  # received | quarantined | parsing | parsing_failed | chunking | indexing | failed
    parser_name: Mapped[str | None] = mapped_column(String(50))  # pypdf | docling | python-docx
    parser_warnings: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    chunking_warnings: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    error_message: Mapped[str | None] = mapped_column(Text)
    section_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class ApprovalRecord(Base):
    """Lịch sử duyệt đầy đủ: reviewer, note, warnings snapshot, timestamp."""

    __tablename__ = "approval_records"
    __table_args__ = (
        Index("ix_approval_records_version_id", "version_id"),
        Index("ix_approval_records_decision", "decision"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # approved | rejected | escalated
    reviewer_id: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    warnings_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class AccessPolicy(Base):
    """Policy quyền truy cập: access_level, allowed_roles, allowed_units, phạm vi áp dụng."""

    __tablename__ = "access_policies"
    __table_args__ = (
        Index("ix_access_policies_access_level", "access_level"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    access_level: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # public | internal | confidential | restricted
    allowed_roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    allowed_units: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    applies_to: Mapped[str] = mapped_column(
        String(20), nullable=False, default="document"
    )  # document | version | section | chunk
    applies_to_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class DocumentRelation(Base):
    """Quan hệ liên văn bản: amends, supersedes, references, annex, related."""

    __tablename__ = "document_relations"
    __table_args__ = (
        UniqueConstraint(
            "source_document_id", "target_document_id", "relation_type",
            name="uq_document_relation",
        ),
        Index("ix_document_relations_source", "source_document_id"),
        Index("ix_document_relations_target", "target_document_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    target_document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # amends | supersedes | references | annex | related
    direction: Mapped[str] = mapped_column(String(20), nullable=False, default="unidirectional")
    effective_from: Mapped[date | None] = mapped_column(Date)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
