"""Analytics persistence models."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class FeedbackRating:
    UP = "up"
    DOWN = "down"


class ChatFeedback(Base):
    __tablename__ = "chat_feedback"
    __table_args__ = (
        UniqueConstraint("user_id", "chat_message_id", name="uq_chat_feedback_user_message"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    knowledge_base_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id"), nullable=False, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    chat_message_id: Mapped[int] = mapped_column(ForeignKey("chat_messages.id"), nullable=False, index=True)
    rating: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
