import os

OUTPUT_MODE = os.getenv("OUTPUT_MODE", "local")  # "local" or "github"
DOCS_PATH = "docs"

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
}

CLUSTER_COUNT = 10          # сколько тем выдать в итоге
MAX_POSTS_FOR_ANALYSIS = 80 # лимит постов отправляемых в LLM (экономия токенов)

RSS_FEEDS = {
    "Reuters World": "https://feeds.reuters.com/reuters/worldNews",
    "BBC World": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "RBC": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
}
NEWS_CATEGORIES = ["politics", "war", "economics", "world"]
NEWS_TOP_COUNT = 30
NEWS_MAX_FOR_ANALYSIS = 50  # лимит новостей отправляемых в LLM
