"""Telegram bot integration for sending article notifications."""

import asyncio

from telegram import Bot

from app.config import settings
from app.logging_config import get_logger

logger = get_logger("telegram")


async def send_message_async(text: str) -> None:
    """Send message to configured Telegram chat (async version)."""
    logger.info(f"Sending message to chat_id={settings.telegram_chat_id}")
    logger.debug(f"Message text (first 100 chars): {text[:100]}...")

    try:
        bot = Bot(token=settings.telegram_bot_token)
        result = await bot.send_message(
            chat_id=settings.telegram_chat_id,
            text=text,
            parse_mode="HTML",
        )
        logger.info(f"Message sent successfully, message_id={result.message_id}")
    except Exception as e:
        logger.error(f"Failed to send message: {type(e).__name__}: {e}")
        raise


def send_message(text: str) -> None:
    """Send message to configured Telegram chat (sync wrapper)."""
    logger.debug("Calling send_message_async via asyncio.run")
    asyncio.run(send_message_async(text))


def send_article_notification(
    title: str,
    link: str,
    pub_date: str,
    summary: str,
) -> None:
    """Send formatted article notification."""
    logger.info(f"Sending article notification: {title[:50]}...")

    message = f"""<b>Подборка статей с портала arxiv:</b>

<b>Статья:</b> {title}
<b>Тема:</b> {summary}

================================

<b>Ссылка:</b> {link}
<b>Дата публикации:</b> {pub_date}"""

    send_message(message)
    logger.info(f"Article notification sent: {title[:50]}...")


def send_error_notification(error_message: str) -> None:
    """Send error notification."""
    logger.warning(f"Sending error notification: {error_message}")
    send_message(f"Error: {error_message}")
