import os

OUTPUT_MODE = os.getenv("OUTPUT_MODE", "local")  # "local" or "github"
DOCS_PATH = "quartz/content"

TOPICS = [
    "python",
    "machine learning",
    "artificial intelligence",
    "software development",
    "backend",
    "llm",
    "openai",
]

SOURCES = {
    "reddit": {
        "enabled": True,
        "subreddits": [
            "Python",
            "MachineLearning",
            "programming",
            "ExperiencedDevs",
            "LocalLLaMA",
            "artificial",
            "learnpython",
            "softwarearchitecture",
        ],
        "post_limit": 20,          # постов на subreddit
        "min_score": 50,           # минимальный рейтинг
        "time_filter": "day",      # hour / day / week
    },
    "hackernews": {
        "enabled": True,
        "post_limit": 30,
        "min_score": 50,
    },
    "devto": {
        "enabled": True,
        "tags": ["python", "machinelearning", "ai", "backend", "programming"],
        "post_limit": 20,
        "min_reactions": 10,
    },
    "github": {
        "enabled": True,
        "post_limit": 20,
        "min_stars": 50,
        "since_days": 1,
    },
    "lobsters": {
        "enabled": True,
        "post_limit": 25,
        "min_score": 10,
    },
    "mastodon": {
        "enabled": True,
        "instance": "hachyderm.io",
        "post_limit": 40,
        "min_score": 5,
    },
    "stackoverflow": {
        "enabled": True,
        "tags": ["python", "machine-learning", "artificial-intelligence", "pytorch", "tensorflow"],
        "post_limit": 30,
        "min_score": 3,
    },
}

CLUSTER_COUNT = 10           # сколько тем выдать в итоге
MAX_POSTS_FOR_ANALYSIS = 150 # лимит постов отправляемых в LLM (экономия токенов)

RSS_FEEDS = {
    "Reuters World": "https://feeds.reuters.com/reuters/worldNews",
    "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "RBC": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
    "Le Figaro": "https://www.lefigaro.fr/rss/figaro_actualites.xml",
    "Bild": "https://www.bild.de/rssfeeds/rss3-20745882,feed=alles.bild.html",
    "Der Spiegel": "https://www.spiegel.de/schlagzeilen/index.rss",
    "Le Monde": "https://www.lemonde.fr/rss/une.xml",
    "Euronews": "https://feeds.feedburner.com/euronews/en/home/",
    "Politico Europe": "https://www.politico.eu/feed/",
}

RSS_FEED_LANGUAGE = {
    "Reuters World": "en",
    "BBC World": "en",
    "Al Jazeera": "en",
    "RBC": "ru",
    "Le Figaro": "fr",
    "Bild": "de",
    "Der Spiegel": "de",
    "Le Monde": "fr",
    "Euronews": "en",
    "Politico Europe": "en",
}

NEWS_CATEGORIES = ["politics", "war", "economics", "world"]
NEWS_TOP_COUNT = 30
NEWS_MAX_FOR_ANALYSIS = 60
NEWS_PER_SOURCE = 5  # top N posts from each individual source
