"""
RabbitMQ worker for processing Arxiv article tasks.

============================================================
RabbitMQ BASICS (для понимания кода ниже):
============================================================

RabbitMQ - это брокер сообщений, работает по принципу "очередей".

Основные концепции:
1. PRODUCER (отправитель) - отправляет сообщения в очередь
2. QUEUE (очередь) - хранит сообщения, пока их не обработают
3. CONSUMER (получатель/worker) - читает и обрабатывает сообщения

Как это работает:
    [Producer] --> [Queue] --> [Consumer]

    Например:
    [main.py публикует задачу] --> [classify_article] --> [worker.py обрабатывает]

Преимущества:
- Задачи не теряются (хранятся в очереди)
- Можно запустить несколько workers для параллельной обработки
- Producer не ждёт завершения задачи (асинхронность)

============================================================
PIKA - это Python клиент для RabbitMQ
============================================================

Основные методы:
- connection = pika.BlockingConnection(params) - подключение к RabbitMQ
- channel = connection.channel() - создание канала для работы
- channel.queue_declare(queue='name') - создание очереди
- channel.basic_publish(...) - отправка сообщения в очередь
- channel.basic_consume(...) - подписка на очередь для получения сообщений
- channel.start_consuming() - начало бесконечного цикла обработки

============================================================
"""

import json
import time
from datetime import datetime
from typing import Any

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

from app.config import settings
from app.database import insert_article, mark_as_shown
from app.llm import check_relevance, score_article
from app.logging_config import get_logger
from app.telegram import send_article_notification, send_error_notification

logger = get_logger("worker")


# ============================================================
# Названия очередей
# ============================================================

# Очередь для классификации новых статей (проверка релевантности + скоринг)
CLASSIFY_QUEUE = "classify_article"

# Очередь для отправки уведомлений в Telegram
NOTIFY_QUEUE = "notify_article"


# Minimum score to save article
MIN_SCORE = 7


# ============================================================
# Подключение к RabbitMQ
# ============================================================


def get_connection() -> pika.BlockingConnection:
    """
    Создаёт подключение к RabbitMQ.

    BlockingConnection - синхронное подключение, проще в использовании.
    Для production можно использовать SelectConnection (асинхронное).
    """
    # Параметры подключения берём из настроек
    credentials = pika.PlainCredentials(
        settings.rabbitmq_user,
        settings.rabbitmq_password,
    )
    parameters = pika.ConnectionParameters(
        host=settings.rabbitmq_host,
        port=settings.rabbitmq_port,
        credentials=credentials,
        # Heartbeat - проверка что соединение живо (в секундах)
        heartbeat=600,
        # Таймаут на блокирующие операции
        blocked_connection_timeout=300,
    )
    return pika.BlockingConnection(parameters)


def wait_for_rabbitmq(max_retries: int = 30, delay: int = 2) -> None:
    """
    Ждёт пока RabbitMQ станет доступен.
    Полезно при запуске в Docker - RabbitMQ может стартовать дольше.
    """
    logger.info(f"Waiting for RabbitMQ at {settings.rabbitmq_host}:{settings.rabbitmq_port}")
    for attempt in range(max_retries):
        try:
            connection = get_connection()
            connection.close()
            logger.info("RabbitMQ is ready!")
            return
        except pika.exceptions.AMQPConnectionError:
            logger.warning(f"Waiting for RabbitMQ... attempt {attempt + 1}/{max_retries}")
            time.sleep(delay)
    logger.error("Could not connect to RabbitMQ after all retries")
    raise RuntimeError("Could not connect to RabbitMQ")


# ============================================================
# Публикация задач (Producer)
# ============================================================


def publish_task(queue_name: str, data: dict[str, Any]) -> None:
    """
    Публикует задачу в указанную очередь.

    Args:
        queue_name: Имя очереди (например, 'classify_article')
        data: Данные задачи в виде словаря (будут сериализованы в JSON)
    """
    connection = get_connection()
    channel = connection.channel()

    # queue_declare - создаёт очередь если её нет, или просто проверяет что есть
    # durable=True - очередь сохранится при перезапуске RabbitMQ
    channel.queue_declare(queue=queue_name, durable=True)

    # Сериализуем данные в JSON
    message = json.dumps(data, ensure_ascii=False, default=str)

    # Публикуем сообщение
    # exchange='' - используем default exchange (прямая отправка в очередь)
    # routing_key - имя очереди куда отправляем
    channel.basic_publish(
        exchange="",
        routing_key=queue_name,
        body=message.encode("utf-8"),
        # delivery_mode=2 - сообщение сохранится на диск (persistent)
        properties=pika.BasicProperties(delivery_mode=2),
    )

    logger.info(f"Published task to {queue_name}: {data.get('title', 'unknown')[:50]}...")
    connection.close()


def publish_classify_task(article_data: dict[str, Any]) -> None:
    """Публикует задачу на классификацию статьи."""
    publish_task(CLASSIFY_QUEUE, article_data)


def publish_notify_task(article_data: dict[str, Any]) -> None:
    """Публикует задачу на отправку уведомления."""
    publish_task(NOTIFY_QUEUE, article_data)


# ============================================================
# Обработка задач (Consumer)
# ============================================================


def process_classify_task(data: dict[str, Any]) -> None:
    """
    Обрабатывает задачу классификации статьи.

    1. Вызывает LLM для проверки релевантности
    2. Фильтрует по релевантности
    3. Оценивает статью (скоринг)
    4. Сохраняет в БД если score >= MIN_SCORE
    5. Создаёт задачу на уведомление
    """
    title = data.get("title", "unknown")
    logger.info(f"Processing classification for: {title[:50]}...")

    try:
        # Step 1: Check relevance via LLM
        logger.debug(f"Calling LLM for relevance check: {title[:50]}")
        relevance = check_relevance(
            title=data.get("title", ""),
            author=data.get("author", ""),
            pub_date=data.get("pub_date", ""),
            summary=data.get("summary", ""),
        )

        if not relevance.is_relevant:
            logger.info(f"Not relevant, skipping: {title[:50]}")
            return

        logger.info(f"Relevant! Summary: {relevance.summary_ru[:50]}...")

        # Step 2: Score the article
        logger.debug(f"Calling LLM for scoring: {title[:50]}")
        score = score_article(
            title=data.get("title", ""),
            author=data.get("author", ""),
            pub_date=data.get("pub_date", ""),
            summary=data.get("summary", ""),
        )

        logger.info(f"Score: {score} for: {title[:50]}")

        if score < MIN_SCORE:
            logger.info(f"Score too low ({score} < {MIN_SCORE}), skipping: {title[:50]}")
            return

        # Step 3: Parse pub_date
        pub_date = None
        try:
            pub_date = datetime.fromisoformat(data.get("pub_date", ""))
        except (ValueError, TypeError):
            pub_date = datetime.now()

        # Step 4: Save to DB
        logger.debug(f"Saving article to DB: {title[:50]}")
        insert_article(
            title=data.get("title", ""),
            link=data.get("link", ""),
            author=data.get("author", ""),
            pub_date=pub_date,
            summary=relevance.summary_ru,
        )

        logger.info(f"Saved article to DB: {title[:50]}")

        # Step 5: Publish notify task
        publish_notify_task({
            "title": data.get("title", ""),
            "link": data.get("link", ""),
            "pub_date": str(pub_date),
            "summary": relevance.summary_ru,
        })

    except Exception as e:
        logger.error(f"Error processing classification for {title[:50]}: {e}")
        send_error_notification(f"Classification error: {e}")


def process_notify_task(data: dict[str, Any]) -> None:
    """
    Обрабатывает задачу отправки уведомления.

    1. Отправляет в Telegram
    2. Помечает статью как показанную
    """
    title = data.get("title", "unknown")
    logger.info(f"Processing notification for: {title[:50]}...")
    logger.debug(f"Notification data: {data}")

    try:
        # Send to Telegram
        logger.info(f"Sending Telegram notification for: {title[:50]}")
        send_article_notification(
            title=data["title"],
            link=data["link"],
            pub_date=str(data.get("pub_date", "")),
            summary=data.get("summary", ""),
        )
        logger.info(f"Telegram notification sent for: {title[:50]}")

        # Mark as shown
        logger.debug(f"Marking as shown: {title[:50]}")
        mark_as_shown(data["title"])

        logger.info(f"Notification completed for: {title[:50]}")

    except Exception as e:
        logger.error(f"Error processing notification for {title[:50]}: {type(e).__name__}: {e}")
        send_error_notification(f"Notification error: {e}")


# ============================================================
# Worker (Consumer) - бесконечный цикл обработки задач
# ============================================================


def make_callback(process_func):
    """
    Создаёт callback-функцию для обработки сообщений из очереди.

    Callback вызывается каждый раз когда приходит новое сообщение.

    Параметры callback (передаются RabbitMQ автоматически):
    - channel: канал через который пришло сообщение
    - method: метаданные доставки (включая delivery_tag для подтверждения)
    - properties: свойства сообщения
    - body: тело сообщения (bytes)
    """
    def callback(
        channel: BlockingChannel,
        method: Basic.Deliver,
        properties: BasicProperties,
        body: bytes,
    ) -> None:
        # Десериализуем JSON
        data = json.loads(body.decode("utf-8"))

        try:
            # Обрабатываем задачу
            process_func(data)

            # basic_ack - подтверждаем что сообщение обработано
            # После этого RabbitMQ удалит его из очереди
            # delivery_tag - уникальный ID этого сообщения
            channel.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logger.error(f"Error in callback: {type(e).__name__}: {e}")
            # basic_nack - сообщаем что не смогли обработать
            # requeue=True - вернуть сообщение в очередь для повторной попытки
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    return callback


def run_worker(queue_name: str, process_func) -> None:
    """
    Запускает worker для обработки задач из очереди.

    Worker работает бесконечно, обрабатывая задачи по мере поступления.
    """
    logger.info(f"Starting worker for queue: {queue_name}")

    # Ждём пока RabbitMQ станет доступен
    wait_for_rabbitmq()

    connection = get_connection()
    channel = connection.channel()

    # Создаём очередь (если её ещё нет)
    channel.queue_declare(queue=queue_name, durable=True)

    # prefetch_count=1 - обрабатываем по одному сообщению за раз
    # Это важно для равномерного распределения нагрузки между workers
    channel.basic_qos(prefetch_count=1)

    # Подписываемся на очередь
    # on_message_callback - функция которая будет вызвана при получении сообщения
    channel.basic_consume(
        queue=queue_name,
        on_message_callback=make_callback(process_func),
    )

    logger.info(f"Worker ready. Waiting for tasks in {queue_name}...")

    # Запускаем бесконечный цикл обработки
    # Это блокирующий вызов - программа будет работать пока не остановят
    channel.start_consuming()


def run_classify_worker() -> None:
    """Запускает worker для классификации статей."""
    run_worker(CLASSIFY_QUEUE, process_classify_task)


def run_notify_worker() -> None:
    """Запускает worker для отправки уведомлений."""
    run_worker(NOTIFY_QUEUE, process_notify_task)
