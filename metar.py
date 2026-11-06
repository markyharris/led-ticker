# METAR fetch + plain-English translation for the ticker (MicroPython).
#
# Source: NOAA's tgftp per-station text files - one tiny file per
# station (a date line, then the raw METAR), e.g.
#   https://tgftp.nws.noaa.gov/data/observations/metar/stations/KFLG.TXT
# The raw report is parsed on the board into the same field shape the
# translator has always used, and the flight category is computed
# on-board from visibility and ceiling.
#
# Why not the aviationweather.gov JSON API (used in Phase 2)? On
# Nov 1 2026 its TLS handshake began failing inside the app with
# MBEDTLS_ERR_PK_INVALID_PUBKEY - the Azure-fronted certificate chain
# is more than this board's in-app TLS stack digests, and the aborted
# handshake then starved the next download too. NOAA's own host has a
# light chain (like Yahoo's, which works), and each reply is ~200
# bytes. Plain HTTP is not an option: tgftp 302-redirects to HTTPS.
#
# The network import is lazy (inside fetch) so the parsing and
# formatting functions can be unit-tested on a desktop with real
# station files.

_URL = "https://tgftp.nws.noaa.gov/data/observations/metar/stations/%s.TXT"
_STALE_S = 3 * 3600 + 900    # older than ~3h counts as no report

_cache = {}          # station id -> {"raw": str, "text": str} or {"missing": True}
_last_fetch_ok = False

_COVERS = {
    "FEW": "few clouds",
    "SCT": "scattered clouds",
    "BKN": "broken clouds",
    "OVC": "overcast",
    "VV": "vertical visibility",
    "CLR": "clear skies",
    "SKC": "clear skies",
    "NSC": "clear skies",
}

_WX = {
    "DZ": "drizzle", "RA": "rain", "SN": "snow", "SG": "snow grains",
    "PL": "ice pellets", "GR": "hail", "GS": "small hail",
    "BR": "mist", "FG": "fog", "FU": "smoke", "HZ": "haze",
    "SA": "sand", "DU": "dust", "SQ": "squalls", "FC": "funnel cloud",
    "TS": "thunderstorm", "SH": "showers", "FZ": "freezing",
    "BL": "blowing", "DR": "drifting", "MI": "shallow", "BC": "patches",
    "PO": "dust devils", "DS": "dust storm", "SS": "sandstorm",
    "UP": "unknown precipitation",
}


def _decode_wx(wx_string):
    """'-RA BR' -> 'light rain, mist'. Unknown codes pass through."""
    if not wx_string:
        return ""
    phrases = []
    for token in wx_string.split():
        t = token
        if t.startswith("VC"):
            t = t[2:]
        intensity = ""
        if t.startswith("-"):
            intensity = "light "
            t = t[1:]
        elif t.startswith("+"):
            intensity = "heavy "
            t = t[1:]
        words = []
        i = 0
        while i + 2 <= len(t):
            code = t[i:i + 2]
            words.append(_WX.get(code, code))
            i += 2
        if words:
            phrases.append(intensity + " ".join(words))
    return ", ".join(phrases)


def _comma(n):
    """Thousands separator without relying on format-spec support."""
    s = str(int(n))
    out = ""
    while len(s) > 3:
        out = "," + s[-3:] + out
        s = s[:-3]
    return s + out


def _fmt_vis(visib):
    if isinstance(visib, str):
        v = visib.strip()
        if v.endswith("+"):
            return v[:-1] + " SM or more"
        return v + " SM"
    if visib == int(visib):
        return "%d SM" % int(visib)
    return "%s SM" % visib


def translate(obs):
    """One parsed observation (AWC-shaped field dict) -> segment text."""
    parts = []
    label = obs.get("icaoId", "????")
    if obs.get("fltCat"):
        label += " (" + obs["fltCat"] + ")"

    wspd = obs.get("wspd")
    wdir = obs.get("wdir")
    if wspd is not None:
        if wspd == 0:
            parts.append("wind calm")
        elif wdir == "VRB" or wdir is None:
            parts.append("wind variable at %d kt" % wspd)
        else:
            w = "wind %03d at %d kt" % (int(wdir), wspd)
            if obs.get("wgst"):
                w += " gust %d" % obs["wgst"]
            parts.append(w)

    if obs.get("visib") is not None:
        parts.append("Vis " + _fmt_vis(obs["visib"]))

    wx = _decode_wx(obs.get("wxString"))
    if wx:
        parts.append(wx)

    clouds = obs.get("clouds") or []
    said_sky = False
    for layer in clouds:
        cover = layer.get("cover")
        base = layer.get("base")
        word = _COVERS.get(cover, cover)
        if cover in ("CLR", "SKC", "NSC"):
            parts.append(word)
        elif base:
            parts.append("%s at %s ft" % (word, _comma(base)))
        else:
            parts.append(word)
        said_sky = True
    if not said_sky and obs.get("cover") in ("CLR", "SKC", "NSC"):
        parts.append("clear skies")

    if obs.get("temp") is not None and obs.get("dewp") is not None:
        parts.append("Temp %d, Dewpt %d"
                     % (round(obs["temp"]), round(obs["dewp"])))
    if obs.get("altim"):
        parts.append("Alt %.2f" % (obs["altim"] * 0.02953))

    if not parts:
        return label + ": no data"
    text = label + ": " + ", ".join(parts)
    return text[0].upper() + text[1:]


# ---------------------------------------------------------------- parsing

def _is_digits(s):
    if not s:
        return False
    for ch in s:
        if ch < "0" or ch > "9":
            return False
    return True


def _vis_value(vstr):
    """'1 1/2' / '1/2' / '10' / '6+' -> float SM, or None."""
    try:
        v = vstr.rstrip("+").strip()
        total = 0.0
        for part in v.split():
            if "/" in part:
                num, den = part.split("/", 1)
                total += float(num) / float(den)
            else:
                total += float(part)
        return total
    except ValueError:
        return None


def _flt_cat(vis_sm, ceiling_ft):
    """Standard category from visibility (SM) and ceiling (ft AGL)."""
    if vis_sm is not None:
        if vis_sm < 1:
            return "LIFR"
        if vis_sm < 3:
            return "IFR"
    if ceiling_ft is not None:
        if ceiling_ft < 500:
            return "LIFR"
        if ceiling_ft < 1000:
            return "IFR"
    if vis_sm is not None and vis_sm <= 5:
        return "MVFR"
    if ceiling_ft is not None and ceiling_ft <= 3000:
        return "MVFR"
    if vis_sm is None and ceiling_ft is None:
        return None
    return "VFR"


def _looks_like_wx(tok):
    t = tok
    if t.startswith("VC"):
        t = t[2:]
    if t[:1] in ("-", "+"):
        t = t[1:]
    if len(t) < 2 or len(t) % 2:
        return False
    i = 0
    while i + 2 <= len(t):
        if t[i:i + 2] not in _WX:
            return False
        i += 2
    return True


def parse_metar(raw):
    """Raw METAR string (remarks already cut) -> field dict for
    translate(): icaoId, fltCat, wdir, wspd, wgst, visib (string),
    wxString, clouds, temp, dewp, altim (hPa, as the AWC API gives -
    translate() converts it to inHg for display)."""
    obs = {"clouds": []}
    tokens = raw.split()
    if not tokens:
        return obs
    obs["icaoId"] = tokens[0]
    wx = []
    ceiling = None
    vis_sm = None
    i = 1
    while i < len(tokens):
        tok = tokens[i]
        i += 1
        if tok.endswith("KT") and len(tok) >= 6:
            body = tok[:-2]
            gust = None
            if "G" in body:
                body, g = body.split("G", 1)
                if _is_digits(g):
                    gust = int(g)
            if body.startswith("VRB") and _is_digits(body[3:]):
                obs["wdir"] = "VRB"
                obs["wspd"] = int(body[3:])
            elif len(body) >= 5 and _is_digits(body):
                obs["wdir"] = int(body[:3])
                obs["wspd"] = int(body[3:])
            if gust is not None:
                obs["wgst"] = gust
            continue
        if tok.endswith("SM") and len(tok) >= 3:
            v = tok[:-2]
            if v.startswith("P"):
                v = v[1:] + "+"
            elif v.startswith("M"):
                v = v[1:]
            obs["visib"] = v
            vis_sm = _vis_value(v)
            continue
        if _is_digits(tok) and i < len(tokens) \
                and tokens[i].endswith("SM") and "/" in tokens[i]:
            v = tok + " " + tokens[i][:-2]
            obs["visib"] = v
            vis_sm = _vis_value(v)
            i += 1
            continue
        if len(tok) >= 5 and tok[:2] == "VV" and _is_digits(tok[2:5]):
            base = int(tok[2:5]) * 100
            obs["clouds"].append({"cover": "VV", "base": base})
            if ceiling is None or base < ceiling:
                ceiling = base
            continue
        if len(tok) >= 6 and tok[:3] in _COVERS and _is_digits(tok[3:6]):
            cover = tok[:3]
            base = int(tok[3:6]) * 100
            obs["clouds"].append({"cover": cover, "base": base})
            if cover in ("BKN", "OVC", "VV"):
                if ceiling is None or base < ceiling:
                    ceiling = base
            continue
        if tok in ("CLR", "SKC", "NSC"):
            obs["clouds"].append({"cover": tok})
            obs["cover"] = tok
            continue
        if "/" in tok:
            a, _, b = tok.partition("/")
            sa = a[1:] if a.startswith("M") else a
            sb = b[1:] if b.startswith("M") else b
            if len(a) <= 3 and len(b) <= 3 and _is_digits(sa) and _is_digits(sb):
                obs["temp"] = -int(sa) if a.startswith("M") else int(sa)
                obs["dewp"] = -int(sb) if b.startswith("M") else int(sb)
            continue
        if len(tok) == 5 and tok[0] == "A" and _is_digits(tok[1:]):
            obs["altim"] = (int(tok[1:]) / 100.0) / 0.02953
            continue
        if _looks_like_wx(tok):
            wx.append(tok)
            continue
        # Anything else (time group, AUTO, variable wind, ...) is skipped.
    if wx:
        obs["wxString"] = " ".join(wx)
    cat = _flt_cat(vis_sm, ceiling)
    if cat:
        obs["fltCat"] = cat
    return obs


def raw_core(text_line):
    """The raw report with remarks cut - the sign doesn't need RMK."""
    return text_line.split(" RMK")[0].strip()


def _file_epoch(dateline):
    """'2026/11/01 20:48' (UTC) -> epoch seconds, or None."""
    try:
        import time
        tup = (int(dateline[0:4]), int(dateline[5:7]), int(dateline[8:10]),
               int(dateline[11:13]), int(dateline[14:16]), 0, 0, 0)
        return time.mktime(tup)
    except Exception:
        return None


def _ingest(sid, text):
    """One station file's text -> cache entry, or None if unusable.
    The report is the first line starting with the station id, not
    assumed to be lines[1]: the file is normally dateline + report,
    but a blank line between them (seen in a Nov 5 desktop read of
    the live KFLG file) must not turn a good report into 'missing'."""
    lines = text.strip().split("\n")
    if len(lines) < 2:
        return None
    raw = None
    for line in lines[1:]:
        if line.strip().startswith(sid):
            raw = raw_core(line.strip())
            break
    if raw is None:
        return None
    import time
    epoch = _file_epoch(lines[0].strip())
    if epoch is not None and time.time() - epoch > _STALE_S:
        return {"missing": True}
    obs = parse_metar(raw)
    return {"raw": raw, "text": translate(obs)}


def fetch(ids):
    """Refresh the cache for the given station ids, one small file
    per station. Returns True if at least one station answered."""
    global _last_fetch_ok
    import gc
    if not ids:
        return False
    try:
        import requests
    except ImportError:
        import urequests as requests
    ok_any = False
    for sid in ids:
        gc.collect()
        try:
            resp = requests.get(_URL % sid,
                                headers={"User-Agent": "Mozilla/5.0"})
            try:
                text = resp.text
            finally:
                resp.close()
        except Exception as e:
            print("METAR fetch failed for", sid, ":", e)
            continue
        entry = _ingest(sid, text)
        if entry is not None:
            _cache[sid] = entry
            ok_any = True
        elif sid not in _cache:
            _cache[sid] = {"missing": True}
    _last_fetch_ok = ok_any
    return ok_any


def segment(ids, mode):
    """Joined segment text for the configured stations, or None if the
    cache has nothing yet (caller shows a 'waiting' message instead)."""
    if not _cache:
        return None
    parts = []
    for sid in ids:
        entry = _cache.get(sid)
        if entry is None:
            parts.append("%s: no data yet" % sid)
        elif entry.get("missing"):
            parts.append("%s: no recent report" % sid)
        elif mode == "raw":
            parts.append(entry["raw"])
        else:
            parts.append(entry["text"])
    return "   *   ".join(parts)


def last_fetch_ok():
    return _last_fetch_ok
