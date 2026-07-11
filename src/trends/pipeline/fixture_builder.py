from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from trends.config import load_digests
from trends.domain.enums import EventStatus, SourceState
from trends.domain.ids import slugify
from trends.domain.models import (
    CurrencyRate,
    DailyDigest,
    DailyPicture,
    DigestEvent,
    Fact,
    RawArticle,
    SourceRun,
)
from trends.pipeline.dedupe import exact_dedupe
from trends.pipeline.normalize import normalize_articles
from trends.pipeline.select import select_for_digest
from trends.storage.daily_store import DailyStore


def _long_text(text: str, suffix: str) -> str:
    value = f"{text} {suffix}"
    while len(value) < 220:
        value += " Материалы собраны из тестовых источников и предназначены для проверки интерфейса."
    return value


def build_fixture_digests(root: Path) -> list[Path]:
    fixture = json.loads((root / "tests/fixtures/articles.json").read_text(encoding="utf-8"))
    collected_at = datetime.fromisoformat(fixture["generated_at"].replace("Z", "+00:00"))
    raw = [
        RawArticle(
            **item,
            collected_at=collected_at,
        )
        for item in fixture["articles"]
    ]
    articles = exact_dedupe(normalize_articles(raw))
    groups = {
        item["article_ids"][0]: item["article_ids"]
        for item in fixture["expected_event_groups"]
    }
    grouped_ids = {item for values in groups.values() for item in values}
    written: list[Path] = []
    store = DailyStore(root / "data/digests")

    for profile in load_digests(root / "config/digests"):
        selected = select_for_digest(articles, profile)
        by_id = {article.id: article for article in selected}
        event_article_groups: list[list[str]] = []
        for first, ids in groups.items():
            present = [article_id for article_id in ids if article_id in by_id]
            if present:
                event_article_groups.append(present)
        event_article_groups.extend(
            [article.id] for article in selected if article.id not in grouped_ids
        )

        events = []
        for rank, article_ids in enumerate(event_article_groups, 1):
            event_articles = [by_id[article_id] for article_id in article_ids]
            primary = event_articles[0]
            brief = _long_text(primary.excerpt or primary.title, "Событие продолжает развиваться; детали будут уточняться по мере появления подтверждений.")
            event_id = f"{profile.id}-{primary.id}"
            events.append(
                DigestEvent(
                    id=event_id,
                    slug=slugify(primary.title),
                    title=primary.title,
                    brief=brief,
                    context=_long_text("Контекст события формируется из доступных публикаций.", primary.excerpt or ""),
                    why_it_matters=_long_text("Это событие вошло в выпуск благодаря соответствию теме и редакционным критериям.", primary.title),
                    importance=max(4, 10 - rank),
                    status=EventStatus.NEW,
                    category=primary.topic_hints[-1] if primary.topic_hints else "news",
                    article_ids=article_ids,
                    facts=[Fact(text=primary.excerpt or primary.title, article_ids=article_ids)],
                    first_seen_at=primary.published_at or collected_at,
                    updated_at=collected_at,
                )
            )

        sources = []
        represented = {source: 0 for source in {article.source_id for article in selected}}
        for event in events:
            for source in {by_id[item].source_id for item in event.article_ids}:
                represented[source] += 1
        for article in selected:
            if any(source.source_id == article.source_id for source in sources):
                continue
            accepted = sum(1 for item in selected if item.source_id == article.source_id)
            sources.append(SourceRun(
                source_id=article.source_id,
                source_name=article.source_name,
                state=SourceState.AVAILABLE,
                fetched=accepted,
                accepted=accepted,
                represented_events=represented[article.source_id],
                history=[max(0, accepted - 2), max(0, accepted - 1), accepted, accepted, accepted, accepted, accepted],
            ))

        body = _long_text(
            f"В выпуске «{profile.title}» собрано {len(events)} ключевых событий из {len(sources)} источников.",
            "Основные темы сопоставлены между независимыми публикациями, а важность выражена единым редакционным рейтингом.",
        )
        digest = DailyDigest(
            digest_id=profile.id,
            date=collected_at.date(),
            generated_at=collected_at,
            daily_picture=DailyPicture(body=body),
            currencies=[
                CurrencyRate(pair="USD/RUB", value=88.12, change_pct=-0.21),
                CurrencyRate(pair="EUR/RUB", value=96.18, change_pct=-0.21),
                CurrencyRate(pair="CNY/RUB", value=12.16, change_pct=0.08),
            ] if profile.id == "world" else [],
            sources=sources,
            articles=selected,
            events=events[: profile.output.max_events],
        )
        written.append(store.write(digest))
    return written
