# ZIP code -> coordinates for the ticker's weather alerts
# (MicroPython).
#
# Source: api.zippopotam.us - free, no key, and the reply is a few
# hundred bytes of JSON, which matters on a microcontroller:
# {"places": [{"latitude": "35.1859", "longitude": "-111.662", ...}]}
# (86001 = Flagstaff, verified live Nov 6 2026). Results are cached
# per ZIP for the life of the process - a sign does not move - and a
# failed lookup keeps no cache entry, so the next fetch round tries
# again. The network import is lazy so the parser can be tested on
# a desktop.

_API = "https://api.zippopotam.us/us/%s"

_cache = {}


def parse(data):
    """Zippopotam reply -> (lat, lon) floats, or None."""
    try:
        place = data["places"][0]
        return float(place["latitude"]), float(place["longitude"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def resolve(zip_code):
    """(lat, lon) for a US ZIP, or None if it cannot be resolved."""
    z = (zip_code or "").strip()
    if not z:
        return None
    if z in _cache:
        return _cache[z]
    try:
        try:
            import requests
        except ImportError:
            import urequests as requests
        resp = requests.get(_API % z,
                            headers={"User-Agent": "Mozilla/5.0"})
        try:
            data = resp.json()
        finally:
            resp.close()
    except Exception as e:
        print("ZIP lookup failed:", e)
        return None
    coords = parse(data)
    if coords:
        _cache[z] = coords
    return coords
