"""Web search with several providers tried in turn, so one blocked search engine does not end the search."""
import base64
import json
import os
import re
import time
import urllib.parse
from typing import Callable

Fetch = Callable[..., tuple[bytes, str]]
_BLOCKED = re.compile(r"anomaly|captcha|challenge|unusual traffic|are you a (human|robot)", re.I)


class SearchError(Exception):
    pass


def _clean(html_to_text, s: str) -> str:
    return html_to_text(s).strip()


def parse_ddg_html(html: str, limit: int, html_to_text) -> list[dict]:
    out = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<a[^>]+class="result__a"|$)', html, re.S):
        href = m.group(1)
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        url = q["uddg"][0] if "uddg" in q else href
        snip = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', m.group(3), re.S)
        out.append({"title": _clean(html_to_text, m.group(2)), "url": url, "snippet": _clean(html_to_text, snip.group(1)) if snip else ""})
        if len(out) >= limit:
            break
    return out


def parse_ddg_lite(html: str, limit: int, html_to_text) -> list[dict]:
    out = []
    for m in re.finditer(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*class=[\"']result-link[\"'][^>]*>(.*?)</a>(.*?)(?=<a[^>]+class=[\"']result-link|$)", html, re.S):
        href = m.group(1)
        if href.startswith("//"):
            href = "https:" + href
        q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
        url = q["uddg"][0] if "uddg" in q else href
        snip = re.search(r"class=[\"']result-snippet[\"'][^>]*>(.*?)</td>", m.group(3), re.S)
        out.append({"title": _clean(html_to_text, m.group(2)), "url": url, "snippet": _clean(html_to_text, snip.group(1)) if snip else ""})
        if len(out) >= limit:
            break
    return out


def _bing_target(href: str) -> str:
    """Bing wraps result addresses in /ck/a?...&u=a1<base64>; unwrap them."""
    q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query)
    u = (q.get("u") or [""])[0]
    if u.startswith("a1"):
        raw = u[2:]
        try:
            return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            pass
    return href


def parse_bing(html: str, limit: int, html_to_text) -> list[dict]:
    out = []
    for blk in re.findall(r'<li[^>]+class="[^"]*b_algo[^"]*"[^>]*>(.*?)</li>', html, re.S):
        m = re.search(r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', blk, re.S)
        if not m:
            continue
        snip = re.search(r"<p[^>]*>(.*?)</p>", blk, re.S)
        out.append({"title": _clean(html_to_text, m.group(2)), "url": _bing_target(m.group(1).replace("&amp;", "&")),
                    "snippet": _clean(html_to_text, snip.group(1)) if snip else ""})
        if len(out) >= limit:
            break
    return out


def _searx(q: str, limit: int, fetch: Fetch, html_to_text) -> list[dict]:
    base = os.environ.get("HERAMA_SEARX_URL", "").rstrip("/")
    if not base:
        raise SearchError("no SearXNG address configured")
    raw, _ = fetch(f"{base}/search?{urllib.parse.urlencode({'q': q, 'format': 'json'})}")
    return [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
            for r in json.loads(raw).get("results", [])[:limit]]


def _brave(q: str, limit: int, fetch: Fetch, html_to_text) -> list[dict]:
    key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not key:
        raise SearchError("no Brave API key configured")
    raw, _ = fetch(f"https://api.search.brave.com/res/v1/web/search?{urllib.parse.urlencode({'q': q, 'count': limit})}",
                   headers={"X-Subscription-Token": key, "Accept": "application/json"})
    return [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("description", "")}
            for r in json.loads(raw).get("web", {}).get("results", [])[:limit]]


def _page(url: str, parser, q: str, limit: int, fetch: Fetch, html_to_text) -> list[dict]:
    raw, _ = fetch(url)
    html = raw.decode("utf-8", "replace")
    hits = parser(html, limit, html_to_text)
    if not hits and _BLOCKED.search(html):
        raise SearchError("the search engine asked for a human check (blocked this request)")
    return hits


def _ddg_html(q, limit, fetch, h2t):
    return _page(f"https://html.duckduckgo.com/html/?{urllib.parse.urlencode({'q': q})}", parse_ddg_html, q, limit, fetch, h2t)


def _ddg_lite(q, limit, fetch, h2t):
    return _page(f"https://lite.duckduckgo.com/lite/?{urllib.parse.urlencode({'q': q})}", parse_ddg_lite, q, limit, fetch, h2t)


def _bing(q, limit, fetch, h2t):
    return _page(f"https://www.bing.com/search?{urllib.parse.urlencode({'q': q, 'setlang': 'en'})}", parse_bing, q, limit, fetch, h2t)


PROVIDERS = [("searxng", _searx), ("brave", _brave), ("duckduckgo", _ddg_html), ("duckduckgo-lite", _ddg_lite), ("bing", _bing)]


def search(query: str, limit: int, fetch: Fetch, html_to_text, budget: float = 30.0) -> tuple[list[dict], str, list[str]]:
    """(hits, provider name, notes about providers that failed). Providers without configuration are skipped silently."""
    notes = []
    end = time.monotonic() + budget   # never keep the app waiting longer than this in total
    for name, fn in PROVIDERS:
        if time.monotonic() > end:
            notes.append(f"{name}: skipped, time budget used up")
            continue
        try:
            hits = fn(query, limit, fetch, html_to_text)
        except SearchError as e:
            if "configured" not in str(e):
                notes.append(f"{name}: {e}")
            continue
        except Exception as e:  # network error, HTTP error from the tool layer, bad JSON
            notes.append(f"{name}: {e}")
            continue
        if hits:
            return hits, name, notes
        notes.append(f"{name}: no results")
    return [], "", notes
