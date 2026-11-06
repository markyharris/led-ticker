# Breaking-news headlines for the ticker (MicroPython).
#
# Source: an RSS top-stories feed. Built-in choices are feeds verified
# reachable without a key (AP's public RSS is gone - it answers 403 -
# so NPR is the default). The admin page can also point at a custom
# feed URL. Only the first few <item> titles are used.
#
# RSS is parsed with plain string searches - MicroPython has no XML
# parser - and headlines are cleaned down to the plain ASCII the LED
# font can draw (smart quotes and dashes are mapped, the rest dropped).
# The network import is lazy so the parser can be tested on a desktop.

FEEDS = {
    "npr": "https://feeds.npr.org/1001/rss.xml",
    "bbc": "https://feeds.bbci.co.uk/news/world/rss.xml",
}

_headlines = []
_last_fetch_ok = False
_ever_ok = False


def url_for(feed_key, custom_url):
    if feed_key == "custom" and custom_url:
        return custom_url
    return FEEDS.get(feed_key, FEEDS["npr"])


def clean(text):
    """RSS title -> sign-safe ASCII."""
    t = text.replace("<![CDATA[", "").replace("]]>", "")
    t = t.replace("&amp;", "&").replace("&quot;", '"')
    t = t.replace("&apos;", "'").replace("&#39;", "'")
    t = t.replace("&lt;", "<").replace("&gt;", ">")
    t = t.replace("‘", "'").replace("’", "'")
    t = t.replace("“", '"').replace("”", '"')
    t = t.replace("—", "-").replace("–", "-")
    t = t.replace("…", "...")
    out = ""
    for ch in t:
        o = ord(ch)
        if 32 <= o < 127:
            out += ch
    return " ".join(out.split())


def parse_headlines(body, limit=3):
    """First `limit` item titles from an RSS document."""
    titles = []
    pos = 0
    while len(titles) < limit:
        i = body.find("<item", pos)
        if i < 0:
            break
        j = body.find("</item>", i)
        block = body[i:j if j > i else len(body)]
        t0 = block.find("<title>")
        t1 = block.find("</title>", t0)
        if t0 >= 0 and t1 > t0:
            title = clean(block[t0 + 7:t1])
            if title:
                titles.append(title)
        if j < 0:
            break
        pos = j + 7
    return titles


def fetch(url):
    """Refresh headlines from the given RSS URL. Keeps the previous
    headlines on failure. Returns True on success."""
    global _headlines, _last_fetch_ok, _ever_ok
    import gc
    gc.collect()
    try:
        try:
            import requests
        except ImportError:
            import urequests as requests
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            body = resp.text
        finally:
            resp.close()
    except Exception as e:
        print("News fetch failed:", e)
        _last_fetch_ok = False
        return False
    titles = parse_headlines(body)
    if titles:
        _headlines = titles
        _last_fetch_ok = True
        _ever_ok = True
        return True
    _last_fetch_ok = False
    return False


def segment():
    if not _headlines:
        return None
    return "NEWS: " + "  +++  ".join(_headlines)


def last_fetch_ok():
    return _last_fetch_ok


def ever_ok():
    return _ever_ok
