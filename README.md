# LinkedIn Trends

Daily digest of tech trends and world news, auto-published to GitHub Pages via Quartz v4.

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
   - Branch: `gh-pages` / folder: `/ (root)`
   - Save

4. **Actions → Daily Trends → Run workflow** — first manual run

5. Site will be at: `https://<username>.github.io/<repo-name>/`

### Site features (Quartz v4)
- Interactive graph view of all reports
- Full-text search
- Backlinks between reports
- Dark theme (Obsidian-style)
- Table of contents on each page

## How it works

```
main.py --mode all
  ├── Tech pipeline
  │   ├── collect: Reddit + HN + Dev.to
  │   ├── analyze: Gemini 2.5 Flash Lite (clusters by topic)
  │   └── save: quartz/content/tech/YYYY-MM-DD.md
  │
  ├── News pipeline
  │   ├── collect: RSS feeds + The Guardian
  │   ├── fetch: USD/RUB + EUR/RUB from Yahoo Finance
  │   ├── analyze: Gemini 2.5 Flash Lite (clusters by significance)
  │   └── save: quartz/content/news/YYYY-MM-DD.md
  │
  └── generate: quartz/content/index.md

npx quartz build → quartz/public/
peaceiris/actions-gh-pages → gh-pages branch
```

`OUTPUT_MODE=github` (set by Actions) routes output to `quartz/content/`.  
`OUTPUT_MODE=local` (default) routes output to `OBSIDIAN_VAULT_PATH`.
