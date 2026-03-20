"""SQLAlchemy models for Arxiv articles."""

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class ArticleStatus(str, PyEnum):
    """Status of article processing."""
    NEW = "new"
    QUEUED = "queued"
    SHOWN = "shown"


class ArxivArticle(Base):
    """Arxiv article model."""

    __tablename__ = "arxiv_records"

    title: Mapped[str] = mapped_column(String(1000), primary_key=True)
    link: Mapped[str] = mapped_column(String(500), nullable=True)
    author: Mapped[str] = mapped_column(String(500), nullable=True)
    pub_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(ArticleStatus),
        default=ArticleStatus.NEW,
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<ArxivArticle(title={self.title!r}, status={self.status})>"
