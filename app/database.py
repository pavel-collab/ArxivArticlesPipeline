"""Database connection and CRUD operations for Arxiv articles."""

from datetime import datetime

from sqlalchemy import create_engine, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.models import ArticleStatus, ArxivArticle, Base

engine = create_engine(settings.database_url, echo=False)
SessionLocal = sessionmaker(bind=engine)


def init_db() -> None:
    """Create all tables in database."""
    Base.metadata.create_all(engine)


def get_session() -> Session:
    """Get new database session."""
    return SessionLocal()


def count_pending_articles() -> int:
    """Count articles with status 'new' or 'queued'."""
    with get_session() as session:
        result = session.execute(
            select(ArxivArticle).where(
                or_(
                    ArxivArticle.status == ArticleStatus.NEW,
                    ArxivArticle.status == ArticleStatus.QUEUED,
                )
            )
        )
        return len(result.scalars().all())


def article_exists(title: str) -> bool:
    """Check if article already exists in DB."""
    with get_session() as session:
        article = session.get(ArxivArticle, title)
        return article is not None


def insert_article(
    title: str,
    link: str,
    author: str,
    pub_date: datetime,
    summary: str,
) -> ArxivArticle:
    """Insert new article."""
    with get_session() as session:
        article = ArxivArticle(
            title=title,
            link=link,
            author=author,
            pub_date=pub_date,
            summary=summary,
            status=ArticleStatus.NEW,
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        return article


def get_pending_articles(limit: int = 3) -> list[ArxivArticle]:
    """Get articles with status 'new' or 'queued'."""
    with get_session() as session:
        result = session.execute(
            select(ArxivArticle)
            .where(
                or_(
                    ArxivArticle.status == ArticleStatus.NEW,
                    ArxivArticle.status == ArticleStatus.QUEUED,
                )
            )
            .limit(limit)
        )
        return list(result.scalars().all())


def mark_as_shown(title: str) -> None:
    """Mark article as shown."""
    with get_session() as session:
        article = session.get(ArxivArticle, title)
        if article:
            article.status = ArticleStatus.SHOWN
            session.commit()
