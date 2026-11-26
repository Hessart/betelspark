import html
import json
import os
import re
import sys
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
# Modele próbowane po kolei. Nazwy skopiuj z Google AI Studio.
MODELS = [
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
]
ATTEMPTS_PER_MODEL = 2
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



def ask_gemini(prompt, client):
    """Próbuje kolejno modeli z listy MODELS. Zwraca wynik albo None."""
    for model in MODELS:
        for attempt in range(1, ATTEMPTS_PER_MODEL + 1):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    ),
                )
                return json.loads(response.text)
            except Exception as error:
                message = str(error)
                print(
                    f"  {model}, próba {attempt}/{ATTEMPTS_PER_MODEL}: "
                    f"{message[:100]}"
                )
                if "NOT_FOUND" in message or "404" in message or "429" in message:
                    break  # taki model nie istnieje, przechodzimy do następnego
                if attempt < ATTEMPTS_PER_MODEL:
                    time.sleep(10)
    return None


def summarize_all(all_items, client):
    """Jedno zapytanie dla wszystkich kategorii. Zwraca True, jeśli się udało."""
    numbered = []
    index = {}
    number = 0

    for category, items in all_items.items():
        for position, item in enumerate(items):
            numbered.append(
                f"{number}. TYTUŁ: {item['title']}\n   OPIS: {item['summary']}"
            )
            index[number] = (category, position)
            number += 1

    if not numbered:
        return True

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

    results = ask_gemini(prompt, client)
    if not isinstance(results, list):
        return False

    for result in results:
        if not isinstance(result, dict):
            continue
        key = result.get("id")
        if isinstance(key, int) and key in index:
            category, position = index[key]
            all_items[category][position]["title_pl"] = result.get("tytul", "")
            all_items[category][position]["summary_pl"] = result.get(
                "streszczenie", ""
            )

    return True


def main():
    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
        http_options=types.HttpOptions(timeout=60_000),
    )

    all_items = {}
    for category in SOURCES:
        print(f"Kategoria: {category}")
        all_items[category] = fetch_category(category)

    if not summarize_all(all_items, client):
        print("Nie udało się wygenerować streszczeń. Nie zapisuję pliku.")
        sys.exit(1)

    data = {"updated": datetime.now(timezone.utc).isoformat()}
    data.update(all_items)

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("Zapisano plik data.json")


if __name__ == "__main__":
    main()