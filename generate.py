import html
import json
import os
import re
import time
from datetime import datetime, timedelta, timezone
from time import mktime

import feedparser
import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

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
MODEL = "gemini-3.5-flash"   # to samo, co w test_gemini.py
BROWSER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)


def clean_text(text):
    """Usuwa znaczniki HTML i nadmiar spacji z opisu."""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


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
                    "summary": clean_text(entry.get("summary", ""))[:500],
                    "published": published.isoformat(),
                })
                found += 1

        print(
            f"  {url} -> status: {status}, "
            f"wpisów w kanale: {len(entries)}, z ostatnich {HOURS}h: {found}"
        )

    items.sort(key=lambda item: item["published"], reverse=True)
    return items[:MAX_ITEMS]


def summarize(category, items, client):
    """Dodaje do każdego newsa polski tytuł i streszczenie."""
    if not items:
        return items

    numbered = []
    for number, item in enumerate(items):
        numbered.append(
            f"{number}. TYTUŁ: {item['title']}\n   OPIS: {item['summary']}"
        )

    prompt = (
        "Jesteś redaktorem codziennego serwisu o technologii. "
        "Dla każdej z poniższych wiadomości napisz po polsku krótki tytuł "
        "(maksymalnie 12 słów) oraz streszczenie w 1-2 zdaniach, "
        "prostym językiem, zrozumiałym dla zwykłego użytkownika. "
        "Opieraj się wyłącznie na podanych informacjach i niczego od siebie "
        "nie dodawaj. Zwróć wynik jako JSON: listę obiektów w formacie "
        '{"id": numer, "tytul": "...", "streszczenie": "..."}.\n\n'
        + "\n".join(numbered)
    )

    results = None
    max_attempts = 4

    for attempt in range(1, max_attempts + 1):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                ),
            )
            results = json.loads(response.text)
            break
        except Exception as error:
            print(
                f"  Próba {attempt}/{max_attempts} nie powiodła się "
                f"({category}): {str(error)[:120]}"
            )
            if attempt < max_attempts:
                time.sleep(10 * attempt)

    if results is None:
        print(f"  Kategoria {category} bez streszczeń.")
        return items

    for result in results:
        index = result.get("id")
        if isinstance(index, int) and 0 <= index < len(items):
            items[index]["title_pl"] = result.get("tytul", "")
            items[index]["summary_pl"] = result.get("streszczenie", "")

    return items


def main():
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    data = {"updated": datetime.now(timezone.utc).isoformat()}

    for category in SOURCES:
        print(f"Kategoria: {category}")
        items = fetch_category(category)
        data[category] = summarize(category, items, client)

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("Zapisano plik data.json")


if __name__ == "__main__":
    main()