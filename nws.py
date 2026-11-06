# NWS active alerts for the ticker (MicroPython).
#
# Source: NOAA's official ArcGIS live feed "NWS_Watches_Warnings_v1"
# (Esri Living Atlas) - the same NWS public alerts, republished
# every 5 minutes, queried by point. NOT api.weather.gov itself:
# that host's DNS answer is a two-hop Akamai CNAME chain, and the
# ESP32's resolver fails on it outright (OSError -202 from
# getaddrinfo, verified on the board Nov 1 2026, via router DNS and
# 8.8.8.8 alike), while hand-rolled raw-socket attempts to go
# around it wedged in connect() - which ignores socket timeouts
# on this port. services9.arcgis.com resolves and connects the
# ordinary way, through the same requests library as the METAR
# feed, which is the transport this board handles reliably.
#
# A point-intersect query with outFields=Event,End_,Affected keeps
# the reply small (a kilobyte or two). End_ is a Unix
# epoch-milliseconds timestamp; the local end time is computed by
# plain arithmetic
# with the configured UTC offset, so no clock/epoch conversion is
# involved. Data verified live Nov 1 2026: the query returned the
# day's Flood Warning and Flood Watch for the Flagstaff point,
# matching api.weather.gov exactly. Affected verified against the
# layer's field list Nov 6 2026, with a live Miami-area reply
# ("Coastal Palm Beach County; Coastal Broward County; ...").

_API = ("https://services9.arcgis.com/RHVPKKiFTONKtxq3/arcgis/rest/"
        "services/NWS_Watches_Warnings_v1/FeatureServer/6/query"
        "?geometry=%s,%s&geometryType=esriGeometryPoint&inSR=4326"
        "&spatialRel=esriSpatialRelIntersects"
        "&outFields=Event,End_,Affected&returnGeometry=false&f=json")

_alerts = []
_last_fetch_ok = False
_ever_ok = False


def _fmt_end(epoch_ms, tz_offset_hours):
    """Unix epoch ms -> local '8:30 PM' by arithmetic alone."""
    local = epoch_ms // 1000 + int(tz_offset_hours) * 3600
    secs = local % 86400
    hh = secs // 3600
    mm = (secs % 3600) // 60
    suffix = "AM" if hh < 12 else "PM"
    h = hh % 12
    if h == 0:
        h = 12
    return "%d:%02d %s" % (h, mm, suffix)


def _clean(text):
    """ArcGIS text -> sign-safe ASCII, single-spaced."""
    t = (text or "").replace(";", ",")
    out = ""
    for ch in t:
        if 32 <= ord(ch) < 127:
            out += ch
    return " ".join(out.split())


def parse_alerts(data, tz_offset_hours=-7, limit=3):
    """ArcGIS query JSON -> ['Event until 8:30 PM - Area, Area', ...].
    The same event can appear as several features (county-based and
    zone-based products); keep the latest end time per event, and
    the affected areas that came with that latest feature. Added in
    v2 (Nov 6 2026): the Affected areas ride along as the alert's
    details - requested live from the layer and verified against
    its field list (Event, End_, Affected all exist)."""
    best = {}
    order = []
    for feat in data.get("features", []):
        attrs = feat.get("attributes", {})
        event = (attrs.get("Event") or "").strip()
        end = attrs.get("End_")
        if not event or not end:
            continue
        affected = _clean(attrs.get("Affected"))
        areas = [a.strip() for a in affected.split(",") if a.strip()]
        detail = ", ".join(areas[:3])
        if event not in best:
            order.append(event)
            best[event] = (end, detail)
        elif end > best[event][0]:
            best[event] = (end, detail)
    out = []
    for event in order[:limit]:
        end, detail = best[event]
        line = event + " until " + _fmt_end(end, tz_offset_hours)
        if detail:
            line += " - " + detail
        out.append(line[:240])
    return out


def fetch(lat, lon, tz_offset_hours=-7):
    """Refresh active alerts for the point. Returns True on success
    (an empty alert list is a successful fetch - it means quiet)."""
    global _alerts, _last_fetch_ok, _ever_ok
    import gc
    gc.collect()
    try:
        try:
            import requests
        except ImportError:
            import urequests as requests
        resp = requests.get(_API % (lon, lat),
                            headers={"User-Agent": "Mozilla/5.0"})
        try:
            data = resp.json()
        finally:
            resp.close()
    except Exception as e:
        print("NWS fetch failed:", e)
        _last_fetch_ok = False
        return False
    if "error" in data:
        print("NWS fetch failed:", data["error"])
        _last_fetch_ok = False
        return False
    _alerts = parse_alerts(data, tz_offset_hours)
    _last_fetch_ok = True
    _ever_ok = True
    return True


def segment():
    if not _alerts:
        return None
    return "NWS ALERT: " + "  +++  ".join(_alerts)


def last_fetch_ok():
    return _last_fetch_ok


def ever_ok():
    return _ever_ok
