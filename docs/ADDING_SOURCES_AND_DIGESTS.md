# Добавление источников и тематических дайджестов

## Новый RSS-источник

Создайте `config/sources/<id>.yaml`:

```yaml
id: example-football
title: Example Football
type: rss
enabled: true
url: https://example.com/feed.xml
language: en
tags: [football, liverpool]
trust_tier: major
perspective: international
ownership: independent
editorial_note: Кратко опишите происхождение источника и правила атрибуции спорных заявлений.
timeout_seconds: 15
options:
  limit: 20
```

Запустите:

```bash
.venv/bin/pytest -q
```

Для RSS Python-код менять не нужно. Новый `type` источника требует collector, реализации `Collector.collect()` и регистрации factory в `collectors/registry.py`.

## Новый дайджест

Скопируйте один файл из `config/digests/`, поменяйте `id`, правила темы, категории и веса. Затем добавьте минимум два положительных и два отрицательных материала в fixture и ожидаемое распределение в `expected_digest_membership`.

`sources.include_tags` — это allowlist источников для выпуска. Статья сначала должна прийти из источника с подходящим тегом, а затем пройти тематические `include_any`/`exclude_any` правила. Короткие термины сопоставляются как отдельные токены: `AI` не совпадает со словом `training`.

Для конфликтных тем задайте `min_perspectives`. Этот порог определяет маркировку уровня подтверждения, но не скрывает важное одностороннее сообщение. Государственные и официальные сообщения всегда должны иметь `ownership` и `editorial_note`; их утверждения атрибутируются конкретной стороне.

Frontend строит список выпусков из каталогов `data/digests/*`; новую Astro-страницу или пункт навигации вручную добавлять не требуется.

## Команды разработки

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/python -m trends.cli build-fixture --root .
.venv/bin/pytest -q
.venv/bin/ruff check src tests
cd frontend
pnpm install
pnpm run check
pnpm run build
```

## AI-контракт

- В AI передаются `article_id`, название и ID источника, title, excerpt, timestamp, `source_perspective`, `source_ownership`, `source_trust_tier` и `source_disclosure`.
- Structured Output проверяет форму через Pydantic.
- `validate_synthesis()` запрещает неизвестные article IDs и проверяет число независимых источников.
- После ошибки допускается один repair-запрос; повторная ошибка должна вести в quarantine, а не в публикацию.
- Prompt и schema версионируются. Изменение редакционных правил требует fixture и contract test.
- Уровень подтверждения вычисляется локально из источников после AI-аудита; модель не может самостоятельно повысить одностороннее сообщение до перекрёстно подтверждённого.
