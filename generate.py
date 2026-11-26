import json
from datetime import datetime, timedelta, timezone
from time import mktime

import feedparser
import requests

# Skąd pobieramy newsy (kanały RSS) dla każdej kategorii
SOURCES = {
    "ai": [
        "https://techcrunch.com/category/artificial-intelligence/feed/",
        "https://www.technologyreview.com/feed/",
    ],
    "tech": [
        "https://www.theverge.com/rss/index.xml",
        "https://feeds.arstechnica.com/arstechnica/technology-lab",
    ],
    "kosmos": [
        "https://spacenews.com/feed/",
        "https://www.nasa.gov/feed/",
    ],
}

HOURS = 48       # z ilu ostatnich godzin bierzemy newsy
MAX_ITEMS = 7    # ile newsów na kategorię
BROWSER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def download_feed(url):
    """Pobiera kanał RSS. Zwraca (status, lista wpisów)."""
    try:
        response = requests.get(
            url, headers={"User-Agent": BROWSER_AGENT}, timeout=20
        )
    except requests.RequestException as error:
        print(f"     błąd: {error}")
        return None, []

    feed = feedparser.parse(response.content)
    return response.status_code, feed.entries


def fetch_category(category):
    since = datetime.now(timezone.utc) - timedelta(hours=HOURS)
    items = []

    for url in SOURCES[category]:
        status, entries = download_feed(url)
        found = 0

        for entry in entries:
            parsed = entry.get("published_parsed") or entry.get("updated_parsed")
            if not parsed:
                continue

            published = datetime.fromtimestamp(mktime(parsed), timezone.utc)
            if published >= since:
                items.append({
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                    "summary": entry.get("summary", "")[:300],
                    "published": published.isoformat(),
                })
                found += 1

        print(
            f"  {url} -> status: {status}, "
            f"wpisów w kanale: {len(entries)}, z ostatnich {HOURS}h: {found}"
        )

    items.sort(key=lambda item: item["published"], reverse=True)
    return items[:MAX_ITEMS]


def main():
    data = {"updated": datetime.now(timezone.utc).isoformat()}

    for category in SOURCES:
        print(f"Kategoria: {category}")
        data[category] = fetch_category(category)

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("Zapisano plik data.json")


if __name__ == "__main__":
    main()