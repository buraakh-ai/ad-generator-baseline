"""RSS headline fetcher — feeds the trending-event fallback used when no
India/US festival or holiday applies today or tomorrow. To add a new
source: append its RSS URL to the right category list. To add a category:
add a new key with a list of URLs."""
import feedparser

RSS_FEEDS_BY_CATEGORY = {
    "sports": [
        "https://feeds.bbci.co.uk/sport/rss.xml",
        "https://www.skysports.com/rss/12040",
        "https://sports.yahoo.com/rss/",
        "https://www.espn.com/espn/rss/news",
        "https://rss.nytimes.com/services/xml/rss/nyt/Sports.xml",
        "https://api.foxsports.com/v1/rss",
    ],
    "world_news": [
        "https://feeds.bbci.co.uk/news/rss.xml",
        "https://rss.cnn.com/rss/edition.rss",
        "https://feeds.skynews.com/feeds/rss/world.xml",
        "https://feeds.reuters.com/reuters/worldNews",
        "https://www.aljazeera.com/xml/rss/all.xml",
        "https://feeds.theguardian.com/theguardian/world/rss",
        "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
    ],
    "business_finance": [
        "https://feeds.reuters.com/reuters/businessNews",
        "https://feeds.reuters.com/reuters/companyNews",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
        "https://feeds.marketwatch.com/marketwatch/topstories",
        "https://feeds.bloomberg.com/markets/news.rss",
        "https://rss.nytimes.com/services/xml/rss/nyt/Business.xml",
    ],
    "technology": [
        "https://techcrunch.com/feed/",
        "https://www.theverge.com/rss/index.xml",
        "https://feeds.wired.com/wired/index",
        "https://arstechnica.com/feed/",
        "https://www.engadget.com/rss.xml",
        "https://feeds.bbci.co.uk/news/technology/rss.xml",
    ],
    "entertainment_culture": [
        "https://variety.com/feed/",
        "https://www.rollingstone.com/feed/",
        "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
        "https://feeds.skynews.com/feeds/rss/entertainment.xml",
        "https://deadline.com/feed/",
    ],
    "health_science": [
        "https://feeds.bbci.co.uk/news/health/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/Health.xml",
        "https://feeds.reuters.com/reuters/healthNews",
        "https://www.sciencedaily.com/rss/all.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/Science.xml",
    ],
    "lifestyle_trends": [
        "https://rss.nytimes.com/services/xml/rss/nyt/FashionandStyle.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/Travel.xml",
        "https://www.theguardian.com/lifeandstyle/rss",
        "https://feeds.reuters.com/reuters/lifestyle",
    ],
}

ALL_RSS_FEEDS = [url for urls in RSS_FEEDS_BY_CATEGORY.values() for url in urls]


def get_all_headlines(max_per_feed: int = 4, max_total: int = 60):
    """Returns a list of {title, category} dicts pulled from every feed in
    RSS_FEEDS_BY_CATEGORY, capped at max_total."""
    headlines = []
    for category, feed_urls in RSS_FEEDS_BY_CATEGORY.items():
        for feed_url in feed_urls:
            if len(headlines) >= max_total:
                break
            try:
                feed = feedparser.parse(feed_url)
                for entry in feed.entries[:max_per_feed]:
                    if hasattr(entry, "title") and entry.title.strip():
                        headlines.append({"title": entry.title.strip(), "category": category})
            except Exception as e:
                print(f"[rss] skipped feed {feed_url}: {e}")
                continue

    print(f"[rss] fetched {len(headlines)} headlines from {len(ALL_RSS_FEEDS)} feeds")
    return headlines[:max_total]
