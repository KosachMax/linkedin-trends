# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A dual-pipeline daily digest generator. Two pipelines run on a cron schedule:
- **Tech** — collects posts from Reddit/HN/Dev.to, clusters by topic via Gemini LLM
- **News** — collects world news from RSS + The Guardian, clusters by significance via Gemini LLM

Output: Markdown files published to GitHub Pages via Quartz v4.

## Running the pipelines

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in GOOGLE_API_KEY at minimum

python main.py              # both pipelines
python main.py --mode tech  # tech only
python main.py --mode news  # news only
```

Required env: `GOOGLE_API_KEY` (Google AI Studio, free). Optional: `OBSIDIAN_VAULT_PATH`, `GUARDIAN_API_KEY`, `DEVTO_API_KEY`.

## Output modes

`OUTPUT_MODE` (env var) controls where files are written:
- `local` (default) — writes to `OBSIDIAN_VAULT_PATH/YYYY-MM-DD-*.md`
- `github` (set by Actions) — writes to `quartz/content/tech/` and `quartz/content/news/`

In `github` mode, `obsidian_writer.save()` and `news_writer.save()` also call `index_writer.generate_index()` which regenerates `quartz/content/index.md` and `archive.md`.

## Architecture

```
collectors/          → raw data (Post / NewsItem dataclasses)
  reddit.py          → Reddit API, filters by min_score
  hackernews.py      → Algolia Search API, 24h window
  devto.py           → Dev.to REST API
  rss_news.py        → feedparser, 5 items per feed
  guardian_news.py   → Guardian API
  currency.py        → CBR (Central Bank Russia) XML API for RUB rates

analyzer/
  llm_analyzer.py    → Gemini 2.5 Flash Lite → {clusters} for tech
  news_analyzer.py   → Gemini 2.5 Flash Lite → {clusters} with significance 1-10

output/
  obsidian_writer.py → renders tech markdown
  news_writer.py     → renders news markdown + currency line
  index_writer.py    → generates homepage + archive, caches top-3 to data/*.json
```

Both analyzers use the **OpenAI SDK pointed at Google's Gemini endpoint**:
```python
client = OpenAI(api_key=os.environ["GOOGLE_API_KEY"],
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
```

## Markdown format

Pages are written in Obsidian/Quartz callout syntax:
- `> [!danger]` / `> [!warning]` / `> [!note]` for cluster severity
- `> [!tip]` / `> [!success]` for structural blocks
- Currency rates render as a plain inline line: `💱 label: rate ↑ delta (pct%)`

The `quartz/content/` directory is the only custom part of the Quartz installation. Everything else under `quartz/` is boilerplate.

## Deployment

GitHub Actions (`.github/workflows/daily_trends.yml`):
- Schedule: 05:30 UTC (08:30 Moscow) daily + `workflow_dispatch`
- Secrets needed: `GOOGLE_API_KEY`, `GUARDIAN_API_KEY`
- Steps: `python main.py --mode all` → `npx quartz build` → deploy `quartz/public/` to `gh-pages` via `peaceiris/actions-gh-pages`

GitHub Pages setup: Settings → Pages → Source: **Deploy from a branch** → `gh-pages` / root.

## Data persistence

`data/` is not gitignored. It stores:
- `currency_history.json` — 30-day rolling window of exchange rates (written by `fetch_and_save_rates()`, read by `get_rates_with_delta()` for day-over-day comparison)
- `tech_latest.json`, `news_latest.json` — top-3 cluster cache for the index page

## Adding a new news source

1. Create `collectors/my_source.py` with a `collect() -> list[NewsItem]` function
2. Import and call it in `main.py → collect_news()`
3. Optionally add it to `config.py` if it needs per-source config

## config.py key knobs

- `CLUSTER_COUNT` — number of topic clusters LLM should produce
- `MAX_POSTS_FOR_ANALYSIS` / `NEWS_MAX_FOR_ANALYSIS` — token budget cap
- `RSS_FEEDS` — list of feed URLs; `RSS_FEED_LANGUAGE` maps URL → language code
- `NEWS_PER_SOURCE` — items fetched per RSS feed
- `SOURCES` — enable/disable reddit/hackernews/devto and their per-source settings
