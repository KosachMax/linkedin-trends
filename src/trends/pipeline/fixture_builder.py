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


EDITORIAL_FIXTURES = {
    "reuters-energy-001": {
        "title": "Страны Европы создадут общий энергорезерв на зиму",
        "brief": "Двенадцать европейских правительств согласовали механизм совместных запасов газа и электроэнергии. Он должен снизить риск дефицита и резких ценовых скачков в периоды максимального зимнего спроса.",
        "context": "Совместный резерв дополняет национальные хранилища и должен помочь странам перераспределять ресурсы при локальном дефиците. Детальные квоты участников пока не опубликованы, поэтому практическая устойчивость механизма будет зависеть от будущих соглашений.",
        "why": "Решение усиливает координацию энергетической политики Европы и может повлиять на закупки, стоимость энергии для промышленности и устойчивость инфраструктуры в холодный сезон.",
    },
    "guardian-ai-003": {
        "title": "Государственные AI-системы будут проходить независимый аудит",
        "brief": "Государственные ведомства вводят внешнюю проверку автоматизированных систем с высоким уровнем риска. До запуска они должны публиковать оценку возможного вреда и подтверждать, что решения модели можно проверить.",
        "context": "Новые правила касаются систем, влияющих на доступ к государственным услугам и другим значимым решениям. Независимые эксперты должны оценивать качество данных, воспроизводимость результатов и механизмы обжалования.",
        "why": "Обязательный аудит повышает прозрачность государственного AI и формирует практику, которая позднее может стать стандартом для регулируемых отраслей и корпоративных систем.",
    },
    "hn-database-004": {
        "title": "Новая открытая база данных упрощает тестирование сбоев сети",
        "brief": "Небольшая команда выпустила распределенную базу данных с предсказуемой репликацией и встроенным симулятором сетевых разделений. Сложные сценарии отказа можно воспроизводить на обычном ноутбуке разработчика.",
        "context": "Проект делает упор на наблюдаемое поведение реплик и повторяемые тесты, а не только на максимальную производительность. Симулятор помогает заранее проверить потерю связи, задержки и восстановление узлов.",
        "why": "Доступное тестирование отказов снижает порог для разработки надежных распределенных приложений и позволяет небольшим командам находить ошибки до выхода системы в production.",
    },
    "devto-python-005": {
        "title": "Структурированная конкурентность упрощает управление задачами Python",
        "brief": "Практическое руководство показывает, как группы задач помогают согласованно запускать, отменять и очищать асинхронные операции Python. Подход сравнивается с ручным управлением отдельными задачами.",
        "context": "При ручном создании фоновых задач разработчик должен самостоятельно отслеживать исключения и корректно завершать дочерние операции. Структурированная конкурентность связывает их жизненный цикл с родительским блоком.",
        "why": "Предсказуемая отмена и обработка ошибок уменьшают количество зависших задач и упрощают поддержку асинхронных backend-сервисов.",
    },
    "aljazeera-diplomacy-006": {
        "title": "Региональные делегации начали переговоры о прекращении огня",
        "brief": "Представители сторон открыли трехдневные переговоры о контролируемой паузе в боевых действиях. В центре обсуждения находятся гуманитарный доступ, безопасность гражданского судоходства и механизм наблюдения.",
        "context": "Переговоры пока не означают заключения соглашения: сторонам предстоит согласовать сроки, географию действия режима и порядок фиксации нарушений. Посредники пытаются сначала закрепить ограниченные практические меры.",
        "why": "Даже временная пауза может улучшить доставку помощи и снизить риски для гражданской инфраструктуры, но устойчивость договоренностей будет зависеть от независимого контроля.",
    },
    "rbc-rates-007": {
        "title": "Центральный банк уточнил условия снижения ключевой ставки",
        "brief": "Регулятор отметил замедление инфляции, но связал дальнейшее смягчение политики с устойчивостью потребительских цен и динамикой кредитования. Одного краткосрочного улучшения показателей для решения недостаточно.",
        "context": "Центральный банк оценивает не только текущую инфляцию, но и ожидания бизнеса и населения, темпы выдачи кредитов и внутренний спрос. Поэтому снижение ставки будет зависеть от нескольких последовательных периодов устойчивой динамики.",
        "why": "Ключевая ставка влияет на стоимость кредитов, доходность сбережений, инвестиции компаний и курс валют, поэтому уточнение позиции регулятора важно для экономики в целом.",
    },
    "arxiv-climate-008": {
        "title": "Компактная модель прогнозирует локальные волны жары",
        "brief": "Исследователи представили компактную модель прогноза экстремальной жары для муниципалитетов с ограниченными вычислительными ресурсами и неполным покрытием датчиками.",
        "context": "Вместо крупной универсальной системы модель оптимизирована для локальных наблюдений и ограниченного набора входных данных. Авторы проверяют, насколько устойчиво она работает при пропусках измерений.",
        "why": "Доступный локальный прогноз помогает городам заранее планировать работу служб, предупреждать жителей и защищать уязвимые группы населения без дорогой инфраструктуры.",
    },
    "lfc-transfer-009": {
        "title": "Liverpool подписал долгосрочный контракт с Матео Силвой",
        "brief": "Liverpool подтвердил переход полузащитника Матео Силвы после завершения медицинского обследования. Игрок подписал долгосрочное соглашение и должен присоединиться к тренировкам основной команды.",
        "context": "Клуб официально завершил оформление трансфера и сообщил о долгосрочном контракте. Следующим этапом станет интеграция игрока в тренировочный процесс и подготовка к первым матчам.",
        "why": "Переход расширяет варианты команды в центре поля и может повлиять на распределение игрового времени, тактические сочетания и дальнейшие решения клуба на трансферном рынке.",
    },
}


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
            editorial = EDITORIAL_FIXTURES.get(primary.id, {})
            title = editorial.get("title", primary.title)
            brief = _long_text(editorial.get("brief", primary.excerpt or primary.title), "Событие продолжает развиваться; детали будут уточняться по мере появления подтверждений.")
            event_id = f"{profile.id}-{primary.id}"
            events.append(
                DigestEvent(
                    id=event_id,
                    slug=slugify(title),
                    title=title,
                    brief=brief,
                    context=_long_text(editorial.get("context", "Контекст события формируется из доступных публикаций."), ""),
                    why_it_matters=_long_text(editorial.get("why", "Это событие вошло в выпуск благодаря соответствию теме и редакционным критериям."), title),
                    importance=max(4, 10 - rank),
                    status=EventStatus.NEW,
                    category=primary.topic_hints[-1] if primary.topic_hints else "news",
                    article_ids=article_ids,
                    facts=[Fact(text=editorial.get("brief", primary.excerpt or title), article_ids=article_ids)],
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
