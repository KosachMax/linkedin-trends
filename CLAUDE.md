# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A dual-pipeline daily digest generator that publishes to a static site (Quartz v4 → GitHub Pages).

- **Tech pipeline** — collects posts from 10 developer sources, clusters by topic via Gemini LLM → `quartz/content/tech/YYYY-MM-DD.md`
- **News pipeline** — collects world news from RSS feeds + The Guardian, clusters by significance via Gemini LLM → `quartz/content/news/YYYY-MM-DD.md`

Live site: **https://kosachmax.github.io/linkedin-trends**

## Running

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in GOOGLE_API_KEY at minimum

python main.py              # both pipelines
python main.py --mode tech  # tech only
python main.py --mode news  # news only
```

Required env: `GOOGLE_API_KEY` (Google AI Studio, free tier sufficient).  
Optional: `OBSIDIAN_VAULT_PATH`, `GUARDIAN_API_KEY`, `DEVTO_API_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`.

## Architecture

```
main.py                   → orchestrates both pipelines; _safe_collect() wraps each
                            collector so one broken source never crashes the pipeline
collectors/               → each returns list[Post] or list[NewsItem]
  reddit.py               → PRAW OAuth if REDDIT_CLIENT_ID set, else public JSON API
  hackernews.py           → Algolia /search_by_date; local filtering by score+age
  devto.py                → Dev.to REST API (optional DEVTO_API_KEY)
  github_trending.py      → GitHub Search API (repos created today, sorted by stars)
  lobsters.py             → Lobste.rs JSON API
  mastodon.py             → Mastodon trending (hachyderm.io)
  stackoverflow.py        → Stack Exchange API hot questions
  medium.py               → RSS feeds per tag (feedparser)
  arxiv.py                → Atom API (cs.AI, cs.LG, cs.CL)
  indiehackers.py         → RSS (currently returns 0 — feed is broken)
  rss_news.py             → feedparser, NEWS_PER_SOURCE items per feed
  guardian_news.py        → Guardian API (requires GUARDIAN_API_KEY)
  currency.py             → CBR (Central Bank Russia) XML API; 30-day rolling
                            history in data/currency_history.json

analyzer/
  llm_analyzer.py         → Gemini → CLUSTER_COUNT tech topic clusters
  news_analyzer.py        → Gemini → NEWS_TOP_COUNT news clusters with significance 1-10

output/
  obsidian_writer.py      → renders tech .md in Obsidian/Quartz callout syntax
  news_writer.py          → renders news .md with currency block
  index_writer.py         → regenerates index.md + archive.md; caches top-3 clusters
                            to data/tech_latest.json and data/news_latest.json
```

## LLM

Both analyzers use the **OpenAI SDK pointed at Google's Gemini endpoint**:
```python
client = OpenAI(api_key=os.environ["GOOGLE_API_KEY"],
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
# model = "gemini-2.5-flash-lite", max_tokens = 16384
```

The LLM returns raw JSON. Both analyzers:
1. Extract the outermost `{…}` by `find`/`rfind` to discard any preamble/postamble text the model adds
2. Strip ` ```json ` fences, `// comments`, and trailing commas before `json.loads()`
3. Retry the API call up to 3× with exponential backoff on API exceptions

`obsidian_writer.render()` accesses all LLM-provided cluster fields via `.get()` with defaults and casts numeric fields to `int()` to guard against the model returning `null`.

## Output modes

`OUTPUT_MODE` env var:
- `local` (default) — writes to `OBSIDIAN_VAULT_PATH/YYYY-MM-DD-*.md`
- `github` (set by Actions) — writes to `quartz/content/tech/` and `quartz/content/news/`; calls `generate_index()` after each pipeline

In `github` mode, if the tech pipeline fails entirely, `_write_stub_tech()` writes a placeholder `.md` so the CI file-existence check doesn't exit 1.

## config.py key knobs

| Variable | Default | Effect |
|---|---|---|
| `CLUSTER_COUNT` | 10 | tech clusters per run |
| `MAX_POSTS_FOR_ANALYSIS` | 150 | posts sent to LLM (token budget) |
| `NEWS_TOP_COUNT` | 10 | news clusters per run; keep ≤15 |
| `NEWS_MAX_FOR_ANALYSIS` | 60 | news items sent to LLM |
| `NEWS_PER_SOURCE` | 5 | items fetched per RSS feed |
| `SOURCES` | dict | enable/disable each collector + per-source thresholds |
| `RSS_FEEDS` / `RSS_FEED_LANGUAGE` | dicts | news RSS sources and their language codes |

## Deployment

GitHub Actions (`.github/workflows/daily_trends.yml`):
- **Triggers:** cron `05:30 UTC` daily + `workflow_dispatch` + every push to `main`
- **Secrets needed:** `GOOGLE_API_KEY` (required), `GUARDIAN_API_KEY` (optional)
- **Steps:** `python main.py --mode all` → verify both `.md` files exist → `npx quartz build` → deploy `quartz/public/` to `gh-pages` via `peaceiris/actions-gh-pages`

`quartz/content/` is the only custom part of the Quartz installation; everything else under `quartz/` is boilerplate.

## Known source limitations in CI

| Source | Issue |
|---|---|
| Reddit | GitHub Actions IPs blocked (403). Needs `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` secrets for PRAW OAuth. Without them returns 0 posts. |
| Guardian | Returns 401 if `GUARDIAN_API_KEY` secret is not set. |
| GitHub Trending | Unauthenticated rate limit is 60 req/hr; `GITHUB_TOKEN` is passed via env automatically. |
| Indie Hackers | RSS feed always returns 0 posts (broken endpoint). |

## data/ directory

Not gitignored. Stores persistent state across runs:
- `currency_history.json` — 30-day rolling window of exchange rates
- `tech_latest.json`, `news_latest.json` — top-3 cluster cache for the index page

## Adding a new collector

1. Create `collectors/my_source.py` returning `list[Post]` (tech) or `list[NewsItem]` (news), with all exceptions caught internally (print + return `[]`)
2. For tech: call via `_safe_collect("name", my_source.collect)` in `collect_tech()` in `main.py`
3. For news: import and call directly in `collect_news()` in `main.py`
4. Add config entry to `SOURCES` in `config.py` if it needs per-source thresholds
