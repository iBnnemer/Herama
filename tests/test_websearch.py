import base64

from app import tools, websearch

BING = ('<ol><li class="b_algo"><h2><a href="https://www.bing.com/ck/a?!&amp;&amp;p=x&amp;u=a1{u}&amp;ntb=1">Qwen <b>release</b></a></h2>'
        '<div class="b_caption"><p>The newest model.</p></div></li></ol>')
LITE = ("<table><tr><td><a rel='nofollow' href='//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&rut=1' class='result-link'>Example A</a></td></tr>"
        "<tr><td class='result-snippet'>About A</td></tr></table>")


def b64(url):
    return base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")


def test_parsers():
    b = websearch.parse_bing(BING.format(u=b64("https://example.org/q")), 5, tools.html_to_text)
    assert b[0]["url"] == "https://example.org/q" and b[0]["title"] == "Qwen release" and "newest" in b[0]["snippet"]
    d = websearch.parse_ddg_lite(LITE, 5, tools.html_to_text)
    assert d[0]["url"] == "https://example.com/a" and d[0]["snippet"] == "About A"


def test_falls_back_to_next_provider(monkeypatch):
    for k in ("HERAMA_SEARX_URL", "BRAVE_API_KEY"):
        monkeypatch.delenv(k, raising=False)

    def fetch(url, **kw):
        if "html.duckduckgo" in url:
            return b"<html>Unfortunately, bots use DuckDuckGo too. anomaly-modal captcha</html>", "text/html"
        if "lite.duckduckgo" in url:
            raise tools.ToolError("the site answered 429")
        return BING.format(u=b64("https://example.org/q")).encode(), "text/html"
    hits, provider, notes = websearch.search("x", 5, fetch, tools.html_to_text)
    assert provider == "bing" and hits[0]["url"] == "https://example.org/q"
    assert any("blocked" in n for n in notes) and any("429" in n for n in notes)


def test_failure_message_names_the_causes(monkeypatch):
    for k in ("HERAMA_SEARX_URL", "BRAVE_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(tools, "_fetch", lambda *a, **k: (_ for _ in ()).throw(tools.ToolError("could not reach the site")))
    r = tools.run("web_search", {"query": "x"})
    assert not r["ok"] and "could not reach" in r["result"] and "HERAMA_SEARX_URL" in r["result"]


def test_searx_provider(monkeypatch):
    monkeypatch.setenv("HERAMA_SEARX_URL", "https://searx.example")
    fetch = lambda url, **kw: (b'{"results":[{"title":"T","url":"https://u","content":"C"}]}', "application/json")  # noqa: E731
    hits, provider, _ = websearch.search("x", 5, fetch, tools.html_to_text)
    assert provider == "searxng" and hits[0]["snippet"] == "C"


def test_fetch_retries_transient_errors(monkeypatch):
    import io
    import urllib.error
    monkeypatch.setattr(tools, "_check_public", lambda u: None)
    monkeypatch.setattr(tools.time, "sleep", lambda s: None)
    calls = {"n": 0}

    class Resp(io.BytesIO):
        headers = {"Content-Type": "text/html"}
        def __enter__(self): return self
        def __exit__(self, *a): return False

    class Opener:
        def open(self, req, timeout=0):
            calls["n"] += 1
            if calls["n"] < 3:
                raise urllib.error.HTTPError("u", 429, "slow down", {}, None)
            return Resp(b"ok")
    monkeypatch.setattr(tools.urllib.request, "build_opener", lambda *a: Opener())
    assert tools._fetch("https://example.com")[0] == b"ok" and calls["n"] == 3
    calls["n"] = 0
    monkeypatch.setattr(Opener, "open", lambda self, req, timeout=0: (_ for _ in ()).throw(urllib.error.HTTPError("u", 404, "no", {}, None)))
    try:
        tools._fetch("https://example.com")
        assert False
    except tools.ToolError as e:
        assert "404" in str(e)
