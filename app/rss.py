"""RSS feed reader for Arxiv articles."""

from dataclasses import dataclass
from datetime import datetime, timedelta

import feedparser


@dataclass
class RawArticle:
    """Raw article data from RSS feed."""
    title: str
    link: str
    author: str
    pub_date: datetime
    summary: str


def fetch_arxiv_articles(days_back: int = 3, max_results: int = 50) -> list[RawArticle]:
    """
    Fetch articles from Arxiv RSS API.

    Args:
        days_back: How many days back to search
        max_results: Maximum number of results

    Returns:
        List of RawArticle objects
    """
    # Build date range
    now = datetime.now()
    date_from = (now - timedelta(days=days_back)).strftime("%Y%m%d")
    date_to = now.strftime("%Y%m%d")

    # Arxiv API URL
    url = (
        f"http://export.arxiv.org/api/query?"
        f"search_query=submittedDate:[{date_from}+TO+{date_to}]"
        f"&max_results={max_results}"
    )

    print(f"Fetching articles from: {url}")

    # Parse RSS feed
    feed = feedparser.parse(url)

    articles = []
    for entry in feed.entries:
        # Parse publication date
        pub_date = datetime.now()
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            pub_date = datetime(*entry.published_parsed[:6])

        # Get authors
        author = ""
        if hasattr(entry, "author"):
            author = entry.author
        elif hasattr(entry, "authors"):
            author = ", ".join(a.get("name", "") for a in entry.authors)

        articles.append(RawArticle(
            title=entry.get("title", "").replace("\n", " ").strip(),
            link=entry.get("link", ""),
            author=author,
            pub_date=pub_date,
            summary=entry.get("summary", "").strip(),
        ))

    print(f"Fetched {len(articles)} articles")
    return articles
