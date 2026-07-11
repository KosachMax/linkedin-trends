# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A config-driven news digest pipeline with two stacks coexisting during migration:

- **New stack (primary):** `src/trends/` Python package + `frontend/` Astro site — produces `data/digests/<id>/current.json`
- **Legacy stack (still running):** `main.py` + `output/` — produces `quartz/content/tech/` and `quartz/content/news/` markdown

Live site (Quartz, will move to Astro): **https://kosachmax.github.io/linkedin-trends**

## Running — new stack

```bash
pip install -e '.[dev]'         # installs trends CLI + dev tools

trends run                       # collect + synthesize → writes data/digests/
trends collect                   # collect only → writes data/pipeline/<timestamp>.json
trends build-fixture             # regenerate tests/fixtures/articles.json
trends retention                 # prune old data per retention policy

pytest -q                        # run tests
ruff check src tests             # lint
```

```bash
cd frontend
pnpm install
pnpm run dev                     # local Astro dev server
pnpm run build                   # static build → frontend/dist/
pnpm run check                   # TypeScript type-check
```

## Running — legacy stack

```bash
pip install -r requirements.txt
cp .env.example .env             # needs GOOGLE_API_KEY at minimum

python main.py                   # both pipelines
python main.py --mode tech
python main.py --mode news
```

## Architecture — new stack

```
config/
  sources/<id>.yaml              → SourceConfig (type, url, tags, trust_tier, language)
  digests/<id>.yaml              → DigestProfile (topic filter, ranking weights, output limits)

src/trends/
  cli.py                         → entrypoint: run | collect | build-fixture | retention
  config.py                      → load_sources() + load_digests() from YAML via Pydantic
  domain/models.py               → all Pydantic models: RawArticle, Article, DigestEvent,
                                   DailyDigest, SourceConfig, DigestProfile, …
  domain/enums.py                → EventStatus, SourceState
  domain/ids.py                  → slugify()
  collectors/
    base.py                      → Collector protocol: async collect(context, config) → CollectorResult
    registry.py                  → maps type string → Collector impl
    rss.py                       → async httpx + feedparser RSS collector
    runner.py                    → collect_sources(): runs all enabled sources concurrently
  pipeline/
    normalize.py                 → deduplicate URLs, clean titles
    dedupe.py                    → exact_dedupe() on normalized URL
    cluster.py                   → group articles into topic clusters
    rank.py                      → cluster_score() using DigestProfile ranking weights
    select.py                    → select_for_digest() by tag + language + topic filter
    merge.py                     → merge_events() to carry forward existing events
    fixture_builder.py           → builds tests/fixtures/articles.json for CI
    production.py                → run_production(): full orchestration per DigestProfile
  ai/
    base.py                      → AIProvider protocol
    gemini.py                    → GeminiProvider (google-genai SDK, NOT OpenAI SDK)
    schemas.py                   → Pydantic schemas for LLM structured output
    service.py                   → EventSynthesisService.synthesize(cluster) → synthesis
    validate.py                  → validation helpers
  storage/
    daily_store.py               → DailyStore: writes data/digests/<id>/current.json
                                   and data/digests/<id>/days/YYYY/MM/YYYY-MM-DD.json
    retention.py                 → prune data/pipeline/ and old day files

data/
  digests/<id>/
    current.json                 → latest DailyDigest (schema_version=1)
    days/YYYY/MM/YYYY-MM-DD.json → archive
    archive-index.json           → {dates: [...]}
    source-history.json          → per-source accepted counts (7-day rolling)
  runs/YYYY/MM/DD/HHMMSS.json   → pipeline run report (not committed)
  pipeline/                      → raw collect outputs (gitignored)
  currency_history.json          → 30-day CBR exchange rates (shared with legacy)

frontend/                        → Astro 5 + Tailwind 4 static site
  src/lib/data.ts                → reads data/digests/ at build time (node:fs)
  src/lib/types.ts               → TypeScript mirror of DailyDigest shape
  src/pages/
    index.astro                  → redirects to /digest/world/
    digest/[digest]/index.astro  → current digest for a named feed
    digest/[digest]/[date].astro → archived day
    events/[digest]/[date]/[slug].astro → single event detail
```

## Key design decisions

**Cluster → event gating:** a cluster must have `min_independent_sources` (default 2) distinct source_ids to pass. Single-source clusters go to quarantine unless `allow_single_source_for` matches the category (e.g. `official_statement`).

**AI is optional:** if `GOOGLE_API_KEY` is unset, `run_production` uses a rule-based fallback that copies the primary article's title/excerpt. The pipeline still produces valid JSON.

**Idempotent writes:** `run_production` will not replace a healthy existing digest with an empty transient run (checked via `if digest.events or existing is None`).

**Astro data layer:** `frontend/src/lib/data.ts` reads `data/digests/` directly via `node:fs` at build time — no API server. `SITE_URL` and `BASE_PATH` env vars configure the Astro output base.

## Deployment (GitHub Actions)

Two jobs in `.github/workflows/daily_trends.yml`:

**`test-next-stack`** (runs first):
- `pytest -q` + `ruff check src tests`
- `trends build-fixture`
- `pnpm install && pnpm run check && pnpm run build` in `frontend/`
- Uploads `frontend/dist` as artifact `astro-preview`

**`generate`** (needs `test-next-stack`):
- Legacy: `python main.py --mode all` (writes Quartz markdown)
- New: `trends run` → `trends retention` → git-commits `data/digests/` + `data/runs/` with `[skip ci]`
- Builds and deploys Quartz to `gh-pages`

Triggers: cron 05:30, 11:00, 17:00 UTC + `workflow_dispatch` + every push to `main`.  
Secrets needed: `GOOGLE_API_KEY` (required), `GUARDIAN_API_KEY` (optional for legacy).

## Adding a new digest feed

1. Create `config/digests/<id>.yaml` with `DigestProfile` fields
2. Tag relevant source configs with a tag that matches `sources.include_tags`
3. `data/digests/<id>/` directory is created automatically on first run

## Adding a new collector type

1. Implement `async collect(context, config) → CollectorResult` in `src/trends/collectors/`
2. Register the type string in `collectors/registry.py`
3. Set `type: <your-type>` in source YAML configs
