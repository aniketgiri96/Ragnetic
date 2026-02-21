"""Document and KnowledgeBase models."""
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class DocumentStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    INDEXED = "indexed"
    FAILED = "failed"


class KnowledgeBaseRole:
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    documents: Mapped[list] = relationship("Document", back_populates="knowledge_base")
    memberships: Mapped[list] = relationship("KnowledgeBaseMembership", back_populates="knowledge_base", cascade="all, delete-orphan")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)  # MinIO/S3 key
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # SHA-256 for dedup
    status: Mapped[str] = mapped_column(String(32), default=DocumentStatus.PENDING)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    knowledge_base: Mapped["KnowledgeBase"] = relationship("KnowledgeBase", back_populates="documents")


class KnowledgeBaseMembership(Base):
    __tablename__ = "knowledge_base_memberships"
    __table_args__ = (UniqueConstraint("knowledge_base_id", "user_id", name="uq_kb_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default=KnowledgeBaseRole.VIEWER)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    knowledge_base: Mapped["KnowledgeBase"] = relationship("KnowledgeBase", back_populates="memberships")
    user: Mapped["User"] = relationship("User", back_populates="kb_memberships")
