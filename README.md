# LinkedIn Trends

Daily digest of tech trends and world news, auto-published to GitHub Pages.

Two pipelines run every day at 09:00 Moscow time:
- **Tech** — top posts from Reddit, Hacker News, Dev.to clustered by topic
- **News** — world news from RSS feeds (BBC, Al Jazeera, RBC) analyzed by significance

## Local usage

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your keys
python main.py         # runs both pipelines, writes to Obsidian vault
python main.py --mode tech   # tech only
python main.py --mode news   # news only
```

### Required env vars (`.env`)

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | yes | Google AI Studio key (free) — aistudio.google.com/apikey |
| `OBSIDIAN_VAULT_PATH` | locally | Absolute path to your Obsidian inbox folder |
| `GUARDIAN_API_KEY` | optional | The Guardian API key (uses public `test` key if absent) |

## GitHub Setup

1. **Push** this repo to GitHub

2. **Settings → Secrets → Actions** — add secrets:
   - `GOOGLE_API_KEY`
   - `GUARDIAN_API_KEY` (optional)

3. **Settings → Pages**
   - Source: **Deploy from a branch**
   - Branch: `main` / folder: `/docs`
   - Save

4. **Actions → Daily Trends → Run workflow** — first manual run

5. Site will be at: `https://<username>.github.io/<repo-name>/`

## How it works

```
main.py --mode all
  ├── Tech pipeline
  │   ├── collect: Reddit + HN + Dev.to
  │   ├── analyze: Gemini 2.5 Flash Lite (clusters by topic)
  │   └── save: docs/tech/YYYY-MM-DD.{md,html}
  │
  ├── News pipeline
  │   ├── collect: RSS feeds + The Guardian
  │   ├── fetch: USD/RUB + EUR/RUB from Yahoo Finance
  │   ├── analyze: Gemini 2.5 Flash Lite (clusters by significance)
  │   └── save: docs/news/YYYY-MM-DD.{md,html}
  │
  └── generate: docs/index.html
```

`OUTPUT_MODE=github` (set by Actions) routes output to `/docs`.  
`OUTPUT_MODE=local` (default) routes output to `OBSIDIAN_VAULT_PATH`.
