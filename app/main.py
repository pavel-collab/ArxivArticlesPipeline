"""
Main entry point for Arxiv Pipeline.

Usage:
    python -m app.main run       - Run full pipeline once
    python -m app.main scheduler - Run pipeline on schedule (every 24h)
    python -m app.main init-db   - Initialize database tables
"""

import sys
import time
from datetime import datetime

from app.database import (
    article_exists,
    count_pending_articles,
    get_pending_articles,
    init_db,
    insert_article,
    mark_as_shown,
)
from app.llm import check_relevance, score_article
from app.rss import fetch_arxiv_articles
from app.telegram import send_article_notification

# Threshold: if we have >= this many pending articles, skip fetching new ones
PENDING_THRESHOLD = 5

# How many articles to notify at a time
NOTIFY_BATCH_SIZE = 3

# Minimum score to save article
MIN_SCORE = 7

# Scheduler interval (seconds) - every 24 hours
SCHEDULER_INTERVAL = 24 * 60 * 60


def process_new_articles() -> None:
    """
    Fetch and process new articles from Arxiv.

    1. Fetch articles from RSS
    2. Check relevance via LLM
    3. Score relevant articles via LLM
    4. Save articles with score >= 7 to DB
    """
    print("Fetching new articles...")
    articles = fetch_arxiv_articles(days_back=3, max_results=50)

    for article in articles:
        # Skip if already in DB
        if article_exists(article.title):
            print(f"Skipping (exists): {article.title[:50]}...")
            continue

        print(f"Processing: {article.title[:50]}...")

        try:
            # Step 1: Check relevance
            relevance = check_relevance(
                title=article.title,
                author=article.author,
                pub_date=str(article.pub_date),
                summary=article.summary,
            )

            if not relevance.is_relevant:
                print(f"  -> Not relevant, skipping")
                continue

            print(f"  -> Relevant! Summary: {relevance.summary_ru[:50]}...")

            # Step 2: Score the article
            score = score_article(
                title=article.title,
                author=article.author,
                pub_date=str(article.pub_date),
                summary=article.summary,
            )

            print(f"  -> Score: {score}")

            if score < MIN_SCORE:
                print(f"  -> Score too low, skipping")
                continue

            # Step 3: Save to DB
            insert_article(
                title=article.title,
                link=article.link,
                author=article.author,
                pub_date=article.pub_date,
                summary=relevance.summary_ru,
            )

            print(f"  -> Saved to DB!")

        except Exception as e:
            print(f"  -> Error processing: {e}")


def send_notifications() -> None:
    """
    Send notifications for pending articles.

    1. Get up to NOTIFY_BATCH_SIZE pending articles
    2. Send to Telegram
    3. Mark as shown
    """
    articles = get_pending_articles(limit=NOTIFY_BATCH_SIZE)

    if not articles:
        print("No pending articles to notify")
        return

    print(f"Sending {len(articles)} notifications...")

    for article in articles:
        try:
            send_article_notification(
                title=article.title,
                link=article.link,
                pub_date=str(article.pub_date),
                summary=article.summary,
            )
            mark_as_shown(article.title)
            print(f"  -> Sent: {article.title[:50]}...")
        except Exception as e:
            print(f"  -> Error sending: {e}")


def run_pipeline() -> None:
    """
    Run the full pipeline once.

    Logic (same as n8n workflow):
    1. Check how many pending articles we have in DB
    2. If >= 5 pending: just send notifications
    3. If < 5 pending: fetch new from Arxiv
    4. Send notifications
    """
    print(f"\n[{datetime.now()}] Running pipeline...")

    pending_count = count_pending_articles()
    print(f"Pending articles in DB: {pending_count}")

    if pending_count >= PENDING_THRESHOLD:
        print("Enough pending articles, skipping fetch...")
    else:
        process_new_articles()

    send_notifications()

    print("Pipeline complete!")


def run_scheduler() -> None:
    """Run pipeline on schedule."""
    print("Starting scheduler...")
    init_db()

    while True:
        try:
            run_pipeline()
        except Exception as e:
            print(f"Pipeline error: {e}")

        print(f"Sleeping for {SCHEDULER_INTERVAL} seconds...")
        time.sleep(SCHEDULER_INTERVAL)


def main() -> None:
    """Entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "run":
        init_db()
        run_pipeline()
    elif command == "scheduler":
        run_scheduler()
    elif command == "init-db":
        init_db()
        print("Database initialized!")
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
