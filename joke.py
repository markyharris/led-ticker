# Dad jokes for the ticker (MicroPython).
#
# Source: icanhazdadjoke.com - free, no key, one small JSON reply
# (~200 bytes) with an Accept: application/json header. The reply
# is cached as the last-good joke, so a failed fetch just replays
# the previous joke; with nothing ever fetched, a bundled fallback
# list rotates instead, so the subject still works offline.
#
# The network import is lazy (inside fetch) so the parsing can be
# unit-tested on a desktop with a canned reply.

_API = "https://icanhazdadjoke.com/"
_REFRESH_HINT = "one joke per fetch; the app refetches on its own cadence"

_FALLBACK = [
    "I only know 25 letters of the alphabet. I don't know y.",
    "I used to hate facial hair, but then it grew on me.",
    "Why did the scarecrow win an award? Because he was outstanding in his field.",
    "I told my wife she was drawing her eyebrows too high. She looked surprised.",
    "What do you call a fish without eyes? A fsh.",
    "Why don't scientists trust atoms? Because they make up everything.",
    "I would tell you a construction joke, but I'm still working on it.",
    "Did you hear about the restaurant on the moon? Great food, no atmosphere.",
]

_cache = None           # last joke fetched live, or None
_last_fetch_ok = False
_fallback_idx = 0


def _parse(data):
    return data["joke"]


def fetch():
    """Fetch one fresh joke. Returns True on success; on failure the
    cached joke (if any) is kept and False is returned."""
    global _cache, _last_fetch_ok
    try:
        try:
            import requests
        except ImportError:
            import urequests as requests
    except ImportError:
        print("Joke: no requests module")
        return False
    try:
        import gc
        gc.collect()
        resp = requests.get(_API, headers={"Accept": "application/json",
                                           "User-Agent": "LED-Ticker"})
        try:
            data = resp.json()
        finally:
            resp.close()
        _cache = _parse(data)
        _last_fetch_ok = True
        return True
    except Exception as e:
        print("Joke fetch failed:", e)
        _last_fetch_ok = False
        return False


def segment():
    """Joke text for the sign: the last live joke if there is one,
    else the next bundled fallback joke. Never None."""
    global _fallback_idx
    if _cache:
        return _cache
    joke = _FALLBACK[_fallback_idx % len(_FALLBACK)]
    _fallback_idx += 1
    return joke


def last_fetch_ok():
    return _last_fetch_ok
