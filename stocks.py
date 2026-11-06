# Stock quotes for the ticker (MicroPython).
#
# Source: Yahoo Finance chart API - the same endpoint the Schwab
# trailing-stop monitor uses on the desktop; it answers without an
# account or API key. One request per symbol. Quotes are ~15 minutes
# delayed, which is fine for a wall sign.
#
# Change is computed against chartPreviousClose so the line always
# shows price, day change and percent change consistently.
# The network import is lazy (inside fetch) so the line formatting
# can be unit-tested on a desktop with real payloads.

_API = "https://query1.finance.yahoo.com/v8/finance/chart/%s?range=1d&interval=1d"

_cache = {}          # symbol -> {"price": float, "chg": float, "pct": float}
_last_fetch_ok = False


def format_line(sym, price, prev_close):
    chg = price - prev_close
    pct = (chg / prev_close * 100.0) if prev_close else 0.0
    return "%s %.2f %+.2f (%+.2f%%)" % (sym, price, chg, pct)


def _parse(sym, data):
    result = data["chart"]["result"][0]
    meta = result["meta"]
    price = meta["regularMarketPrice"]
    prev = meta["chartPreviousClose"]
    return {"price": price, "chg": price - prev,
            "pct": (price - prev) / prev * 100.0 if prev else 0.0}


def fetch(symbols):
    """Refresh quotes for the given symbols. Symbols that fail keep
    their previous quote if they have one. Returns True if at least
    one symbol updated."""
    global _last_fetch_ok
    import gc
    if not symbols:
        return False
    try:
        try:
            import requests
        except ImportError:
            import urequests as requests
    except ImportError:
        print("Stocks: no requests module")
        return False
    ok_any = False
    for sym in symbols:
        try:
            gc.collect()
            resp = requests.get(_API % sym,
                                headers={"User-Agent": "Mozilla/5.0"})
            try:
                data = resp.json()
            finally:
                resp.close()
            _cache[sym] = _parse(sym, data)
            ok_any = True
        except Exception as e:
            print("Stock fetch failed for", sym, ":", e)
    _last_fetch_ok = ok_any
    return ok_any


def segment(symbols):
    """Joined segment text, or None if nothing has ever been fetched."""
    parts = []
    for sym in symbols:
        q = _cache.get(sym)
        if q:
            parts.append("%s %.2f %+.2f (%+.2f%%)"
                         % (sym, q["price"], q["chg"], q["pct"]))
    if not parts:
        return None
    return "  |  ".join(parts)


def last_fetch_ok():
    return _last_fetch_ok
