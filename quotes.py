# Inspirational quotes for the ticker (MicroPython).
#
# Sources, tried in order - both free, no key, one small JSON reply:
#   zenquotes.io/api/random      [{"q": ..., "a": ...}, ...]
#   dummyjson.com/quotes/random  {"quote": ..., "author": ...}
# The last good quote is cached, so a failed fetch just replays it;
# with nothing ever fetched, a bundled list of public-domain quotes
# rotates instead, so the subject still works offline. (Mark's one
# design note, Nov 6 2026: quotes come from an API - he does not
# want to have to think of them.)
#
# The network import is lazy (inside fetch) so the parsing can be
# unit-tested on a desktop with canned replies.

_SOURCES = ("https://zenquotes.io/api/random",
            "https://dummyjson.com/quotes/random")

_FALLBACK = [
    ("The best way to predict the future is to invent it.",
     "Alan Kay"),
    ("Whether you think you can or you think you can't, "
     "you're right.", "Henry Ford"),
    ("It always seems impossible until it's done.",
     "Nelson Mandela"),
    ("What lies in our power to do, lies in our power not to do.",
     "Aristotle"),
    ("Well done is better than well said.", "Benjamin Franklin"),
    ("The journey of a thousand miles begins with a single step.",
     "Lao Tzu"),
    ("That which does not kill us makes us stronger.",
     "Friedrich Nietzsche"),
    ("In the middle of difficulty lies opportunity.",
     "Albert Einstein"),
]

_MAX_CHARS = 220

_cache = None           # (text, author) fetched live, or None
_last_fetch_ok = False
_fallback_idx = 0


def _clean(text):
    if not text:
        return ""
    for a, b in (("\u2018", "'"), ("\u2019", "'"),
                 ("\u201c", '"'), ("\u201d", '"'),
                 ("\u2013", "-"), ("\u2014", "-"),
                 ("\u2026", "..."), ("\u00a0", " ")):
        text = text.replace(a, b)
    out = []
    for ch in text:
        o = ord(ch)
        out.append(ch if 32 <= o < 127 else " ")
    return " ".join("".join(out).split())


def _parse(data):
    """Normalize either source's shape to (text, author), or None."""
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return None
    text = _clean(data.get("q") or data.get("quote"))
    if not text:
        return None
    return text, _clean(data.get("a") or data.get("author"))


def fetch():
    """Fetch one fresh quote. Returns True on success; on failure
    the cached quote (if any) is kept and False is returned."""
    global _cache, _last_fetch_ok
    try:
        try:
            import requests
        except ImportError:
            import urequests as requests
    except ImportError:
        print("Quote: no requests module")
        return False
    for url in _SOURCES:
        try:
            import gc
            gc.collect()
            resp = requests.get(url, headers={"User-Agent": "LED-Ticker"})
            try:
                data = resp.json()
            finally:
                resp.close()
            got = _parse(data)
            if got:
                _cache = got
                _last_fetch_ok = True
                return True
        except Exception as e:
            print("Quote fetch failed (%s):" % url, e)
    _last_fetch_ok = False
    return False


def segment():
    """Quote text for the sign: the last live quote if there is
    one, else the next bundled fallback. Never None."""
    global _fallback_idx
    if _cache:
        text, author = _cache
    else:
        text, author = _FALLBACK[_fallback_idx % len(_FALLBACK)]
        _fallback_idx += 1
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS - 3].rstrip() + "..."
    if author:
        return "%s - %s" % (text, author)
    return text


def last_fetch_ok():
    return _last_fetch_ok
