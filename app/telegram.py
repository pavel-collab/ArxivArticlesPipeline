"""Telegram bot integration for sending article notifications."""

import asyncio

from telegram import Bot

from app.config import settings


async def send_message_async(text: str) -> None:
    """Send message to configured Telegram chat (async version)."""
    bot = Bot(token=settings.telegram_bot_token)
    await bot.send_message(
        chat_id=settings.telegram_chat_id,
        text=text,
        parse_mode="HTML",
    )


def send_message(text: str) -> None:
    """Send message to configured Telegram chat (sync wrapper)."""
    asyncio.run(send_message_async(text))


def send_article_notification(
    title: str,
    link: str,
    pub_date: str,
    summary: str,
) -> None:
    """Send formatted article notification."""
    message = f"""<b>Подборка статей с портала arxiv:</b>

<b>Статья:</b> {title}
<b>Тема:</b> {summary}

================================

<b>Ссылка:</b> {link}
<b>Дата публикации:</b> {pub_date}"""

    send_message(message)
