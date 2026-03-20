# Arxiv Pipeline

Автоматический пайплайн для мониторинга статей с arxiv.org по тематике AI/ML.

## Что делает пайплайн

1. Загружает статьи с arxiv.org (последние 3 дня)
2. Фильтрует по релевантности AI-темам (AI, LLM, MCP, RAG, Computer Vision, AI-agents)
3. Оценивает интерес статьи по шкале 1-10
4. Сохраняет статьи с оценкой >= 7 в базу данных
5. Отправляет уведомления в Telegram (до 3 статей за раз)

## Быстрый старт

### 1. Настройка окружения

```bash
cd arxiv_pipeline
cp .env.example .env
```

Отредактируйте `.env`:

```env
# Telegram Bot (получить у @BotFather)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=448541908

# OpenRouter API (https://openrouter.ai)
OPENAI_API_KEY=sk-or-v1-xxxxxxxxxxxxx
OPENAI_API_BASE=https://openrouter.ai/api/v1
OPENAI_MODEL=openai/gpt-4o-mini
```

### 2. Запуск через Docker Compose

```bash
# Запуск всех сервисов
docker-compose up -d

# Просмотр логов
docker-compose logs -f pipeline

# Остановка
docker-compose down
```

### 3. Запуск вручную (для разработки)

```bash
# Установка зависимостей
pip install -r requirements.txt

# Инициализация БД
python -m app.main init-db

# Однократный запуск пайплайна
python -m app.main run

# Запуск по расписанию (каждые 24 часа)
python -m app.main scheduler
```

## Команды

| Команда | Описание |
|---------|----------|
| `python -m app.main run` | Однократный запуск пайплайна |
| `python -m app.main scheduler` | Запуск по расписанию (24ч) |
| `python -m app.main init-db` | Инициализация таблиц в БД |

## Структура проекта

```
arxiv_pipeline/
├── app/
│   ├── config.py       # Настройки из переменных окружения
│   ├── models.py       # SQLAlchemy модель ArxivArticle
│   ├── database.py     # CRUD операции с PostgreSQL
│   ├── rss.py          # Парсинг Arxiv RSS API
│   ├── llm.py          # LLM для фильтрации и скоринга
│   ├── telegram.py     # Отправка уведомлений
│   └── main.py         # Точка входа
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
└── .env.example
```

## Конфигурация

Все настройки задаются через переменные окружения:

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `POSTGRES_HOST` | `postgres` | Хост PostgreSQL |
| `POSTGRES_PORT` | `5432` | Порт PostgreSQL |
| `POSTGRES_USER` | `arxiv` | Пользователь БД |
| `POSTGRES_PASSWORD` | `arxiv` | Пароль БД |
| `POSTGRES_DB` | `arxiv` | Имя базы данных |
| `TELEGRAM_BOT_TOKEN` | — | Токен Telegram бота |
| `TELEGRAM_CHAT_ID` | — | ID чата для уведомлений |
| `OPENAI_API_KEY` | — | API ключ OpenRouter |
| `OPENAI_API_BASE` | `https://openrouter.ai/api/v1` | URL API |
| `OPENAI_MODEL` | `openai/gpt-4o-mini` | Модель LLM |

## Логика работы

```
┌─────────────────────────────────────────────────────────────┐
│                      Scheduler (24ч)                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │  Pending статей в БД >= 5?    │
              └───────────────────────────────┘
                     │                │
                    Да               Нет
                     │                │
                     ▼                ▼
         ┌───────────────┐   ┌─────────────────────┐
         │ Пропуск fetch │   │ Fetch с arxiv.org   │
         └───────────────┘   │ (3 дня, max 50)     │
                     │       └─────────────────────┘
                     │                │
                     │                ▼
                     │       ┌─────────────────────┐
                     │       │ LLM: Релевантность? │
                     │       │ (AI, LLM, RAG, CV)  │
                     │       └─────────────────────┘
                     │                │
                     │                ▼
                     │       ┌─────────────────────┐
                     │       │ LLM: Скоринг 1-10   │
                     │       └─────────────────────┘
                     │                │
                     │                ▼
                     │       ┌─────────────────────┐
                     │       │ Score >= 7?         │
                     │       │ Сохранить в БД      │
                     │       └─────────────────────┘
                     │                │
                     └────────┬───────┘
                              ▼
              ┌───────────────────────────────┐
              │  Отправить до 3 статей        │
              │  в Telegram                   │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │  Пометить как "shown"         │
              └───────────────────────────────┘
```

## Критерии скоринга статей

| Баллы | Тематика |
|-------|----------|
| 1-4 | AI в медицине, биологии, кибербезопасности. Оптимизация классических ML моделей |
| 5-7 | Безопасность нейросетей, MCP, RAG. AI-агенты в промышленности |
| 8-10 | Новые архитектуры, SOTA решения, оптимизация LLM, внедрение CV и AI-агентов |
| 10 | Смешные новости про ИИ |

## Работа с базой данных

Подключение к PostgreSQL:

```bash
docker-compose exec postgres psql -U arxiv -d arxiv
```

Полезные запросы:

```sql
-- Все статьи
SELECT title, status, pub_date FROM arxiv_records;

-- Pending статьи
SELECT * FROM arxiv_records WHERE status IN ('new', 'queued');

-- Сброс статуса для повторной отправки
UPDATE arxiv_records SET status = 'new' WHERE status = 'shown';
```

## Troubleshooting

### Пайплайн не находит статьи

Arxiv API может возвращать пустой результат если:
- Нет новых статей за последние 3 дня
- Проблемы с доступом к API

Проверьте URL вручную:
```
http://export.arxiv.org/api/query?search_query=submittedDate:[20240101+TO+20240103]&max_results=10
```

### Ошибки LLM

Проверьте:
- Корректность `OPENAI_API_KEY`
- Баланс на OpenRouter
- Доступность модели

### Telegram не отправляет

Проверьте:
- Токен бота корректный
- Бот добавлен в чат
- `TELEGRAM_CHAT_ID` корректный (можно узнать через @userinfobot)
