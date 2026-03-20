"""
Main entry point for Arxiv Pipeline.

Usage:
    python -m app.main scheduler   - Run scheduler (fetches articles periodically)
    python -m app.main classify    - Run classification worker
    python -m app.main notify      - Run notification worker
    python -m app.main init-db     - Initialize database tables
"""

import sys
import time
from datetime import datetime

from app.database import (
    article_exists,
    count_pending_articles,
    get_pending_articles,
    init_db,
)
from app.logging_config import get_logger
from app.rss import fetch_arxiv_articles
from app.telegram import send_error_notification
from app.worker import (
    publish_classify_task,
    publish_notify_task,
    run_classify_worker,
    run_notify_worker,
    wait_for_rabbitmq,
)

logger = get_logger("main")


# Threshold: if we have >= this many pending articles, skip fetching new ones
PENDING_THRESHOLD = 5

# How many articles to notify at a time
NOTIFY_BATCH_SIZE = 3

# Scheduler interval (seconds) - every 24 hours
SCHEDULER_INTERVAL = 24 * 60 * 60


def run_scheduler() -> None:
    """
    Main scheduler loop.

    Logic (same as n8n workflow):
    1. Check how many pending articles we have in DB
    2. If >= 5 pending: just send notifications from existing
    3. If < 5 pending: fetch new from Arxiv RSS
    """
    logger.info("Starting scheduler...")
    init_db()
    wait_for_rabbitmq()

    while True:
        logger.info(f"Running scheduler iteration at {datetime.now()}")

        try:
            pending_count = count_pending_articles()
            logger.info(f"Pending articles in DB: {pending_count}")

            if pending_count >= PENDING_THRESHOLD:
                # We have enough pending - just send notifications
                logger.info("Enough pending articles, sending notifications...")
                articles = get_pending_articles(limit=NOTIFY_BATCH_SIZE)

                for article in articles:
                    logger.info(f"Publishing notify task for: {article.title[:50]}...")
                    publish_notify_task({
                        "title": article.title,
                        "link": article.link,
                        "pub_date": str(article.pub_date),
                        "summary": article.summary or "",
                    })

            else:
                # Need to fetch new articles
                logger.info("Fetching new articles from Arxiv RSS...")

                articles = fetch_arxiv_articles(days_back=3, max_results=50)
                logger.info(f"Fetched {len(articles)} articles")

                if not articles:
                    logger.info("No articles fetched, skipping...")
                else:
                    for article in articles:
                        # Skip if already in DB
                        if article_exists(article.title):
                            logger.debug(f"Skipping (exists): {article.title[:50]}...")
                            continue

                        # Publish classify task
                        logger.info(f"Publishing classify task for: {article.title[:50]}...")
                        publish_classify_task({
                            "title": article.title,
                            "link": article.link,
                            "author": article.author,
                            "pub_date": str(article.pub_date),
                            "summary": article.summary,
                        })

        except Exception as e:
            logger.error(f"Scheduler error: {type(e).__name__}: {e}")
            send_error_notification(f"Scheduler error: {e}")

        logger.info(f"Sleeping for {SCHEDULER_INTERVAL} seconds...")
        time.sleep(SCHEDULER_INTERVAL)


def main() -> None:
    """Entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    logger.info(f"Starting Arxiv Pipeline with command: {command}")

    if command == "scheduler":
        run_scheduler()
    elif command == "classify":
        init_db()
        run_classify_worker()
    elif command == "notify":
        init_db()
        run_notify_worker()
    elif command == "init-db":
        init_db()
        logger.info("Database initialized!")
    else:
        logger.error(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
