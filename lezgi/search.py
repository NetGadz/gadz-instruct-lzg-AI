import html
import json
import re
import urllib.parse
import urllib.request
from html.parser import HTMLParser

from .config import logger


class DuckDuckGoHtmlParser(HTMLParser):
    """Парсер поисковой выдачи DuckDuckGo (HTML версия)."""

    def __init__(self):
        super().__init__()
        self._in_result = False
        self._in_title = False
        self._in_snippet = False
        self._depth = 0
        self._title = ""
        self._snippet = ""
        self._url = ""
        self.results = []

    def handle_starttag(self, tag, attrs):
        attr_dict = dict(attrs)
        classes = (attr_dict.get("class") or "").split()

        if tag == "div" and "result" in classes:
            self._in_result = True
            self._depth = 0

        if self._in_result and tag == "div":
            self._depth += 1

        if self._in_result and tag == "a" and "result__a" in classes:
            self._in_title = True
            href = attr_dict.get("href", "")
            if "uddg=" in href:
                parsed = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
                href = urllib.parse.unquote(parsed.get("uddg", [href])[0])
            self._url = href

        if self._in_result and "result__snippet" in classes:
            self._in_snippet = True

    def handle_endtag(self, tag):
        if self._in_title and tag == "a":
            self._in_title = False
        if self._in_snippet and tag in ("a", "div", "span"):
            self._in_snippet = False
        if self._in_result and tag == "div":
            self._depth -= 1
            if self._depth <= 0 and self._title.strip():
                self.results.append((
                    self._title.strip(),
                    self._url.strip(),
                    self._snippet.strip(),
                ))
                self._in_result = False
                self._title = ""
                self._snippet = ""
                self._url = ""

    def handle_data(self, data):
        if self._in_title:
            self._title += data
        elif self._in_snippet:
            self._snippet += data


def _search_bing(query: str, limit: int = 4) -> list[tuple[str, str, str]]:
    """Резервный поиск через Bing."""
    try:
        url = f"https://www.bing.com/search?q={urllib.parse.quote_plus(query)}&setlang=ru"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "ru-RU,ru;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=6) as response:
            page = response.read().decode("utf-8", errors="ignore")

        items = []
        for block in re.findall(r'<li class="b_algo".*?</li>', page, flags=re.DOTALL):
            link = re.search(r'<h2>\s*<a href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.DOTALL)
            snip = re.search(r'<p>(.*?)</p>', block, flags=re.DOTALL)
            if not link:
                continue

            clean = lambda val: re.sub(r"<[^>]+>", "", html.unescape(val)).strip()
            title = clean(link.group(2))
            href = link.group(1)
            snippet = clean(snip.group(1)) if snip else ""

            if title:
                items.append((title, href, snippet))
            if len(items) >= limit:
                break
        return items
    except Exception as err:
        logger.debug("Ошибка поиска Bing: %s", err)
        return []


def _search_wikipedia(query: str, limit: int = 3) -> list[tuple[str, str, str]]:
    """Поиск по русскоязычной Википедии через официальный API."""
    try:
        url = (
            f"https://ru.wikipedia.org/w/api.php?action=opensearch&search="
            f"{urllib.parse.quote_plus(query)}&limit={limit}&namespace=0&format=json"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "LezgiAI/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
            titles, descriptions, urls = data[1], data[2], data[3]
            return list(zip(titles, urls, descriptions))
    except Exception as err:
        logger.debug("Ошибка поиска Wikipedia: %s", err)
        return []


def search_web(query: str, limit: int = 5) -> tuple[str, list[dict]]:
    """Выполняет поиск в сети (DuckDuckGo с фолбеком на Bing и Wikipedia).

    Возвращает строку с контекстом для LLM и список источников со ссылками.
    """
    results = []

    # 1. Пробуем DuckDuckGo
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(query)}"
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept-Language": "ru-RU,ru;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=7) as resp:
            parser = DuckDuckGoHtmlParser()
            parser.feed(resp.read().decode("utf-8", errors="ignore"))
            results = parser.results[:limit]
    except Exception as err:
        logger.debug("Ошибка поиска DuckDuckGo: %s", err)

    # 2. Фолбек на Bing при необходимости
    if len(results) < 2:
        results.extend(_search_bing(query, limit=limit))

    # 3. Если всё ещё мало результатов, пробуем Википедию
    if not results:
        results.extend(_search_wikipedia(query, limit=limit))

    if not results:
        return "", []

    # Фильтрация дубликатов по URL
    seen_urls = set()
    unique = []
    for title, href, snippet in results:
        if href not in seen_urls:
            seen_urls.add(href)
            unique.append((title, href, snippet))
        if len(unique) >= limit:
            break

    context_lines = [
        f"[{i}] {t}\nURL: {u}\n{s}" for i, (t, u, s) in enumerate(unique, 1)
    ]
    context_str = "\n".join(context_lines)
    sources = [{"title": t, "url": u, "snippet": s} for t, u, s in unique]

    return context_str, sources
