"""LLM processing for article relevance and scoring."""

from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.config import settings


class RelevanceResult(BaseModel):
    """Structured output for relevance check."""
    is_relevant: bool = Field(description="Is the article relevant to AI topics")
    summary_ru: str = Field(description="Summary in Russian (empty if not relevant)")


class ScoringResult(BaseModel):
    """Structured output for article scoring."""
    score: int = Field(description="Interest score from 1 to 10")

#TODO: need to use this function inplace
def get_llm() -> ChatOpenAI:
    """Create ChatOpenAI instance."""
    return ChatOpenAI(
        model=settings.openai_model,
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base,
        temperature=0,
    )

#TODO: move prompts to the separate folder
RELEVANCE_PROMPT = PromptTemplate.from_template(
    """Тебе дана следующая статья:

Заголовок статьи: {title}
Дата публикации: {pub_date}
Автор: {author}
Summary: {summary}

Определи, относится ли эта статья к теме искусственного интеллекта.
Ключевые темы, которые считаются релевантными: AI, LLM, MCP, RAG, Computer vision, AI-agents.

В случае, если статья релевантна заданным тематикам, выдай is_relevant=true и сделай краткий пересказ статьи НА РУССКОМ ЯЗЫКЕ, основываясь на Summary.
Иначе выдай is_relevant=false и пустой summary_ru."""
)


SCORING_PROMPT = PromptTemplate.from_template(
    """Тебе дана следующая статья:

Заголовок статьи: {title}
Дата публикации: {pub_date}
Автор: {author}
Summary: {summary}

Дай ей оценку, на сколько статья является интересной. Оценка представляет собой число от 1 до 10, где 1 -- совсем не интересная статья, 10 -- максимально интересная. Очки начисляются в соответствии с тематикой статьи следующим образом:

1-4 очка: применение искусственного интеллекта в областях медицины, биологии, кибербезопасности. Исследования тривиальных сфер машинного обучения, например оптимизации классических моделей.
5-7 очков: исследования в области безопасности нейронных сетей, MCP, RAG. Применение нейронных сетей и AI агентов в отраслях промышленности.
8-10 очков: разработка принципиально новых способов обучения нейросетей, новые архитектуры, state of the art решения, новые технологии в сфере llm, оптимизации llm, внедрение компьютерного зрения в рабочие процессы, внедрение ai-агентов в рабочие процессы.
10 очков: смешные новости про ИИ

Верни только score."""
)


def check_relevance(
    title: str,
    author: str,
    pub_date: str,
    summary: str,
) -> RelevanceResult:
    """Check if article is relevant to AI topics."""
    llm = get_llm()
    chain = RELEVANCE_PROMPT | llm.with_structured_output(RelevanceResult)

    result = chain.invoke({
        "title": title,
        "author": author,
        "pub_date": pub_date,
        "summary": summary,
    })

    return result


def score_article(
    title: str,
    author: str,
    pub_date: str,
    summary: str,
) -> int:
    """Score article interest level (1-10)."""
    llm: ChatOpenAI = get_llm()
    chain = SCORING_PROMPT | llm.with_structured_output(ScoringResult)

    result = chain.invoke({
        "title": title,
        "author": author,
        "pub_date": pub_date,
        "summary": summary,
    })

    return result.score
