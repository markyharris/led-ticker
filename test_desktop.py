# Desktop test for the LED ticker (repo main.py) (main.py +
# nws.py + news.py + zipgeo.py), run with CPython 3.12. MicroPython
# modules are stubbed; no real network is touched - the fake
# `requests` module answers with canned payloads: the live KFLG
# station file (Nov 5 2026), a Yahoo chart payload, the live
# zippopotam.us reply for 86001 (Nov 6 2026), an ArcGIS alerts reply
# in the shape of the live Miami-area answer (Nov 6 2026), and a
# small NPR-style RSS document. Run: python3 test_s3_v2_desktop.py
import sys
import os
import types

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# --- fake time: MicroPython ticks API on top of a manual clock -------
import time as _time

_clock = {"ms": 0}


def _ticks_ms():
    return _clock["ms"]


def _ticks_diff(a, b):
    return a - b


def _ticks_add(a, b):
    return a + b


def _sleep_ms(ms):
    _clock["ms"] += ms


def _sleep(s):
    _clock["ms"] += int(s * 1000)


_time.ticks_ms = _ticks_ms
_time.ticks_diff = _ticks_diff
_time.ticks_add = _ticks_add
_time.sleep_ms = _sleep_ms
_time.sleep = _sleep

# --- gc.mem_free (MicroPython only) ----------------------------------
import gc as _gc

_gc.mem_free = lambda: 8000000

# --- stubs for MicroPython modules -----------------------------------
machine = types.ModuleType("machine")


class _WDT:
    def __init__(self, timeout=60000):
        self.timeout = timeout
        self.fed = 0

    def feed(self):
        self.fed += 1


class _Pin:
    IN = 0
    PULL_UP = 1
    value_now = 1          # BOOT not held

    def __init__(self, *a, **k):
        pass

    def value(self):
        return _Pin.value_now


machine.WDT = _WDT
machine.Pin = _Pin
machine.reset = lambda: (_ for _ in ()).throw(RuntimeError("reset"))
sys.modules["machine"] = machine

network = types.ModuleType("network")
network.STA_IF = 0
network.AP_IF = 1


class _WLAN:
    connected = True

    def __init__(self, *a):
        pass

    def active(self, v):
        pass

    def connect(self, ssid, pw):
        pass

    def disconnect(self):
        pass

    def config(self, **kw):
        pass

    def scan(self):
        return [(b"HomeNet", b"\x01" * 6, 1, -40, 0, 0),
                (b"HomeNet", b"\x02" * 6, 6, -70, 0, 0),
                (b"Weak", b"\x03" * 6, 1, -85, 0, 0),
                (b"", b"\x04" * 6, 1, -50, 0, 1)]

    def isconnected(self):
        return _WLAN.connected

    def ifconfig(self):
        return ("192.168.1.42", "255.255.255.0", "192.168.1.1",
                "8.8.8.8")


network.WLAN = _WLAN
sys.modules["network"] = network

ntptime = types.ModuleType("ntptime")
ntptime.settime = lambda: None
sys.modules["ntptime"] = ntptime

framebuf = types.ModuleType("framebuf")
framebuf.MONO_VLSB = 0


class _FB:
    def __init__(self, buf, w, h, fmt):
        self.buf = buf
        self.width = w
        self.height = h
        self.text_calls = []

    def text(self, s, x, y, c):
        self.text_calls.append(s)

    def fill(self, v):
        pass

    def pixel(self, x, y, v):
        pass


framebuf.FrameBuffer = _FB
sys.modules["framebuf"] = framebuf

max7219 = types.ModuleType("max7219")


class _Disp:
    def __init__(self, n, intensity=6):
        self.width = n * 8
        self.buf = bytearray(self.width)
        self.fb = _FB(self.buf, self.width, 8, 0)
        self.intensity = intensity
        self.shows = 0

    def init(self):
        pass

    def set_intensity(self, v):
        self.intensity = v

    def clear(self):
        pass

    def show(self):
        self.shows += 1


max7219.make_chain = lambda n, intensity=6: _Disp(n, intensity)
sys.modules["max7219"] = max7219

# --- canned payloads ---------------------------------------------------
KFLG_FILE = ("2026/11/05 13:57\n\nKFLG 051357Z 00000KT 10SM CLR "
             "M04/M05 A3016 RMK AO2 SLP202 T10391050\n")
YAHOO = {"chart": {"result": [{"meta": {"symbol": "AAPL",
                                        "regularMarketPrice": 259.30,
                                        "chartPreviousClose": 254.10}}],
                  "error": None}}
JOKE = {"id": "abc123",
        "joke": "Why did the coffee file a police report? It got mugged.",
        "status": 200}
# Live zippopotam.us reply for 86001, read Nov 6 2026.
ZIPPOPOTAM = {"country": "United States", "post code": "86001",
              "places": [{"place name": "Flagstaff",
                          "longitude": "-111.662",
                          "latitude": "35.1859",
                          "state": "Arizona"}]}
# ArcGIS alerts reply in the shape of the live Miami answer, Nov 6
# 2026 (Coastal Flood Statement), plus a duplicated Flood Warning
# with two end times to exercise the dedupe.
ARCGIS = {"features": [
    {"attributes": {"Event": "Coastal Flood Statement",
                    "End_": 1794182400000,
                    "Affected": "Coastal Palm Beach County; Coastal "
                                "Broward County; Coastal Miami Dade "
                                "County; Far Inland"}},
    {"attributes": {"Event": "Flood Warning",
                    "End_": 1794100000000,
                    "Affected": "Old Zone"}},
    {"attributes": {"Event": "Flood Warning",
                    "End_": 1794200000000,
                    "Affected": "New Zone; Second County"}},
]}
RSS = ("<?xml version='1.0'?><rss><channel>"
       "<item><title>Markets rally on jobs report</title>"
       "<link>http://x</link></item>"
       "<item><title><![CDATA[Storm &amp; flood cleanup begins]]>"
       "</title></item>"
       "<item><title>Third headline here</title></item>"
       "<item><title>Fourth headline ignored</title></item>"
       "</channel></rss>")


class _Resp:
    def __init__(self, text=None, js=None):
        self.text = text
        self._js = js

    def json(self):
        return self._js

    def close(self):
        pass


def _fake_get(url, headers=None):
    if "tgftp" in url:
        return _Resp(text=KFLG_FILE)
    if "yahoo" in url:
        return _Resp(js=YAHOO)
    if "icanhazdadjoke" in url:
        return _Resp(js=JOKE)
    if "zippopotam" in url:
        return _Resp(js=ZIPPOPOTAM)
    if "arcgis" in url:
        return _Resp(js=ARCGIS)
    if "npr.org" in url:
        return _Resp(text=RSS)
    raise AssertionError("unexpected URL in test: %s" % url)


requests = types.ModuleType("requests")
requests.get = _fake_get
sys.modules["requests"] = requests
sys.modules["urequests"] = requests

# --- import the real modules -------------------------------------------
import nws
import news
import zipgeo

failures = []


def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name
          + ((" | " + str(detail)) if detail and not cond else ""))
    if not cond:
        failures.append(name)


# 1. nws parser: dedupe per event, latest end wins, details ride along
lines = nws.parse_alerts(ARCGIS, tz_offset_hours=-5)
check("nws: two events after dedupe", len(lines) == 2, lines)
check("nws: first event kept in order",
      lines[0].startswith("Coastal Flood Statement until "), lines)
check("nws: affected detail, max 3 areas, commas",
      "Coastal Palm Beach County, Coastal Broward County, "
      "Coastal Miami Dade County" in lines[0]
      and "Far Inland" not in lines[0], lines)
check("nws: latest end + its areas win",
      "New Zone, Second County" in lines[1]
      and "Old Zone" not in lines[1], lines)
check("nws: empty reply -> no lines",
      nws.parse_alerts({"features": []}) == [])
check("nws: segment None when quiet", nws.segment() is None)
check("nws: fetch via fake requests",
      nws.fetch(25.79, -80.19, -5) is True)
check("nws: segment has NWS ALERT prefix + details",
      nws.segment() is not None
      and nws.segment().startswith("NWS ALERT: Coastal Flood")
      and "New Zone" in nws.segment(), nws.segment())

# 2. zipgeo: parse the live 86001 reply, resolve + cache
check("zipgeo: parse live reply",
      zipgeo.parse(ZIPPOPOTAM) == (35.1859, -111.662),
      zipgeo.parse(ZIPPOPOTAM))
check("zipgeo: parse junk -> None",
      zipgeo.parse({"places": []}) is None)
check("zipgeo: resolve", zipgeo.resolve("86001") == (35.1859, -111.662))
check("zipgeo: cached", "86001" in zipgeo._cache)
check("zipgeo: blank -> None", zipgeo.resolve("") is None)

# 3. news parser: titles, CDATA/entities cleaned, limit applied
titles = news.parse_headlines(RSS)
check("news: three titles", len(titles) == 3, titles)
check("news: entity cleaned", titles[1] == "Storm & flood cleanup begins",
      titles)
check("news: url_for feeds",
      news.url_for("npr", "") == news.FEEDS["npr"]
      and news.url_for("custom", "http://x/rss") == "http://x/rss")
check("news: fetch + segment",
      news.fetch(news.FEEDS["npr"]) is True
      and news.segment().startswith("NEWS: Markets rally"),
      news.segment())

# 4. the v2 app itself (import with main() stripped), run from a
# scratch cwd holding a seeded config: saved values must survive,
# new v2 defaults must fill in underneath them.
import tempfile
import json as _json

tmp = tempfile.mkdtemp(prefix="ticker_v2_test_")
os.chdir(tmp)
with open("ticker_config.json", "w") as f:
    _json.dump({"wifi_ssid": "HomeNet", "wifi_pass": "secretpw",
                "brightness": 9, "subjects": {"joke": False}}, f)
src = open(os.path.join(HERE, "main.py")).read()
assert src.rstrip().endswith("main()")
src = src.rstrip()[: -len("main()")]
ns = {"__name__": "main"}
exec(compile(src, "main.py", "exec"), ns)
cfg = ns["cfg"]

check("app: saved wifi survives", cfg["wifi_ssid"] == "HomeNet"
      and cfg["wifi_pass"] == "secretpw")
check("app: saved brightness survives", cfg["brightness"] == 9)
check("app: v2 defaults filled in",
      cfg["zip_code"] == "86001" and cfg["wow_wipe"] is True
      and cfg["news_feed"] == "npr")
check("app: subjects merged (joke off, alerts/news default on)",
      cfg["subjects"]["joke"] is False
      and cfg["subjects"]["alerts"] is True
      and cfg["subjects"]["news"] is True, cfg["subjects"])

# 5. segments are triples; content segments carry titles
segs = ns["build_segments"]()
check("app: segments are triples", all(len(s) == 3 for s in segs), segs)
by_title = {s[2]: s[1] for s in segs if s[2]}
check("app: titles for metar/stocks/verse/alerts/news",
      set(by_title) == {"Weather", "Stocks", "Verse", "Wx Alert",
                        "News"}, list(by_title))
check("app: clocks have no title",
      all(s[2] is None for s in segs if s[0] == "static"))
check("app: alerts segment carries details",
      "New Zone" in by_title["Wx Alert"], by_title.get("Wx Alert"))
check("app: news segment present", "Markets rally" in by_title["News"])

# 6. data_service end-to-end through the fake network
ns["_ip"] = "192.168.1.42"
ns["data_service"]()
check("app: data_service fetched alerts",
      nws.last_fetch_ok() is True)
check("app: data_service fetched news", news.last_fetch_ok() is True)

# 7. main loop: title cards when a clock is on; wow wipe replaces
# the plain wipe while enabled, and only then
calls = {"static": [], "scroll": [], "wow": 0, "wipe": 0}
real_build = ns["build_segments"]
state = {"cycles": 0}


def build_then_stop():
    state["cycles"] += 1
    if state["cycles"] > 1:
        raise KeyboardInterrupt
    return real_build()


ns["build_segments"] = build_then_stop
ns["data_service"] = lambda: None
ns["static_text"] = lambda t, hold_ms=4000: calls["static"].append(t)
ns["scroll_text"] = lambda t: calls["scroll"].append(t)
ns["wipe_wow"] = lambda: calls.__setitem__("wow", calls["wow"] + 1)
ns["wipe_out"] = lambda: calls.__setitem__("wipe", calls["wipe"] + 1)
cfg["subjects"]["joke"] = True
ns["main"]()
nsegs = len(real_build())
cards = [t for t in calls["static"] if " - " in t and t.endswith(":")]
check("loop: title cards shown", len(cards) >= 4, cards)
check("loop: card format 'H:MM AM - Joke:'",
      any(t.split(" - ")[-1] == "Joke:" and (" AM" in t or " PM" in t)
          for t in cards), cards)
check("loop: wow wipe after every segment",
      calls["wow"] == nsegs and calls["wipe"] == 0, calls)

calls.update({"static": [], "scroll": [], "wow": 0, "wipe": 0})
state["cycles"] = 0
cfg["wow_wipe"] = False
cfg["subjects"]["clock_normal"] = False
cfg["subjects"]["clock_text"] = False
ns["main"]()
check("loop: wow off -> plain wipe",
      calls["wipe"] == len(real_build()) and calls["wow"] == 0, calls)
check("loop: no clock -> no title cards",
      not [t for t in calls["static"] if t.endswith(":")],
      calls["static"])
cfg["subjects"]["clock_normal"] = True
cfg["subjects"]["clock_text"] = True
cfg["wow_wipe"] = True

# 8. provisioning helpers
check("prov: scan cleaned + sorted",
      ns["_prov_clean_scan"](_WLAN().scan())
      == [("HomeNet", -40), ("Weak", -85)],
      ns["_prov_clean_scan"](_WLAN().scan()))
check("prov: validate manual wins",
      ns["_prov_validate"]({"ssid": "A", "ssid_manual": " B ",
                            "wifi_password": "x"}) == ("B", "x"))
try:
    ns["_prov_validate"]({"ssid": "", "ssid_manual": ""})
    check("prov: validate rejects empty", False)
except ValueError:
    check("prov: validate rejects empty", True)
ns["_prov_apply"]("NewNet", "newpw")
saved = _json.load(open("ticker_config.json"))
check("prov: apply writes only wifi fields",
      saved["wifi_ssid"] == "NewNet" and saved["wifi_pass"] == "newpw"
      and saved["brightness"] == 9, saved)

q = bytearray()
q += b"\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00"
q += b"\x07example\x03com\x00\x00\x01\x00\x01"
reply = ns["_dns_reply"](bytes(q))
check("prov: DNS catch-all answers 192.168.4.1",
      reply is not None and reply[-4:] == bytes((192, 168, 4, 1))
      and reply[6:8] == b"\x00\x01")
check("prov: DNS drops junk", ns["_dns_reply"](b"\x00\x01") is None)
check("prov: BOOT not held", ns["_prov_boot_held"]() is False)
check("prov: not needed while joined", ns["_prov_needed"]() is False)

# 9. admin page carries the v2 fields
page = ns["_admin_page"]()
check("admin: zip field", 'name="zip_code"' in page
      and 'value="86001"' in page)
check("admin: news feed + wow wipe controls",
      'name="news_feed"' in page and 'name="wow_wipe"' in page
      and 'name="news_custom_url"' in page)
check("admin: alerts + news subjects listed",
      "Weather alerts" in page and "News headlines" in page)
check("admin: rehome hint present", "LED-Ticker-Setup" in page)

# 10. regression (board, Nov 6 2026): the import-time join is still
# in flight when _prov_needed runs, and connect() during an
# in-progress join raises - the sign fell into setup mode on a
# joinable network. _prov_try_join must wait the in-flight join out.
class _RaceWLAN:
    """isconnected() turns True after ~2 s of polling; connect()
    raises while that first join is 'in progress'."""

    def __init__(self):
        self.polls = 0
        self.connect_calls = 0

    def isconnected(self):
        self.polls += 1
        return self.polls > 4

    def connect(self, ssid, pw):
        self.connect_calls += 1
        raise OSError("Wifi Internal State Error")

    def disconnect(self):
        pass


_race = _RaceWLAN()
_real_wlan = ns["wlan"]
ns["wlan"] = _race
check("prov: in-flight join waited out, no setup mode",
      ns["_prov_try_join"]() is True and _race.connect_calls == 0,
      "connect_calls=%d" % _race.connect_calls)
ns["wlan"] = _real_wlan

# 11. self-update machinery (v4): blob SHAs, listing parse, check
# and apply with the transport stubbed at _https_get_url
import hashlib as _hl


def _git_blob_sha(data):
    return _hl.sha1(b"blob %d\x00" % len(data) + data).hexdigest()


check("upd: blob sha matches git's",
      ns["_blob_sha_bytes"](b"hello ticker\n")
      == _git_blob_sha(b"hello ticker\n"))

OLD_MAIN = b"# old main\n"
NEW_MAIN = b"# new main - v4 code\n"
VERSE_NOW = open(os.path.join(HERE, "verse.py"), "rb").read()
LISTING = _json.dumps([
    {"name": "main.py", "type": "file",
     "sha": _git_blob_sha(NEW_MAIN),
     "download_url": "https://dl/main.py"},
    {"name": "verse.py", "type": "file",
     "sha": _git_blob_sha(VERSE_NOW),
     "download_url": "https://dl/verse.py"},
    {"name": "README.md", "type": "file", "sha": "x",
     "download_url": "https://dl/README.md"},
]).encode()

parsed = ns["_parse_listing"](LISTING)
check("upd: listing parsed, files only that we track",
      parsed["main.py"]["sha"] == _git_blob_sha(NEW_MAIN)
      and "README.md" in parsed)
check("upd: listing junk -> None", ns["_parse_listing"](b"no") is None)

with open("main.py", "wb") as f:
    f.write(OLD_MAIN)
with open("verse.py", "wb") as f:
    f.write(VERSE_NOW)
plan = ns["_changed_files"](parsed)
check("upd: only main.py changed",
      [n for n, _i in plan] == ["main.py"], plan)


def _fake_https(url, max_bytes, depth=0):
    if "api.github.com" in url:
        return LISTING
    if url == "https://dl/main.py":
        return NEW_MAIN
    return None


ns["_https_get_url"] = _fake_https
ns["_check_update"]()
check("upd: check flags 1 file",
      ns["UPDATE_STATE"]["available"] is True
      and ns["UPDATE_STATE"]["files"] == 1, ns["UPDATE_STATE"])
ns["_apply_update"]()
check("upd: apply swapped main.py",
      open("main.py", "rb").read() == NEW_MAIN)
check("upd: old main kept as .bak",
      open("main.py.bak", "rb").read() == OLD_MAIN)
check("upd: state clean after apply",
      ns["UPDATE_STATE"]["available"] is False
      and ns["UPDATE_STATE"]["failed"] == "")

# a download whose bytes fail SHA verification must change nothing
BAD_LISTING = _json.dumps([
    {"name": "main.py", "type": "file",
     "sha": _git_blob_sha(b"something else entirely"),
     "download_url": "https://dl/main.py"}]).encode()


def _fake_https_bad(url, max_bytes, depth=0):
    if "api.github.com" in url:
        return BAD_LISTING
    return NEW_MAIN


ns["_https_get_url"] = _fake_https_bad
ns["_apply_update"]()
check("upd: bad SHA -> no swap, failure recorded",
      open("main.py", "rb").read() == NEW_MAIN
      and "verification failed" in ns["UPDATE_STATE"]["failed"],
      ns["UPDATE_STATE"])

# 12. night mode (v5): window math (incl. wrap past midnight),
# intensity scaling, and the dark-at-0% state
check("night: HH:MM parse",
      ns["_hhmm_mins"]("22:00") == 1320
      and ns["_hhmm_mins"]("6:05") == 365
      and ns["_hhmm_mins"]("24:00") is None
      and ns["_hhmm_mins"]("abc") is None)
_real_hms = ns["local_hms"]
cfg["night_mode"] = True
cfg["night_start"] = "22:00"
cfg["night_end"] = "06:00"
cfg["night_brightness"] = 25
cfg["brightness"] = 6
for hh, mm, want in ((21, 59, False), (22, 0, True), (23, 30, True),
                     (0, 0, True), (5, 59, True), (6, 0, False),
                     (12, 0, False)):
    ns["local_hms"] = lambda h=hh, m=mm: (h, m, 0)
    check("night: wrap window at %02d:%02d" % (hh, mm),
          ns["night_active"]() is want)
ns["local_hms"] = lambda: (23, 0, 0)
check("night: 25% of 6 -> 2", ns["effective_intensity"]() == 2,
      ns["effective_intensity"]())
check("night: not off at 25%", ns["night_off"]() is False)
cfg["night_brightness"] = 0
check("night: 0% -> off in window", ns["night_off"]() is True)
ns["local_hms"] = lambda: (12, 0, 0)
check("night: midday not off", ns["night_off"]() is False)
check("night: midday full intensity",
      ns["effective_intensity"]() == 6)
cfg["night_mode"] = False
ns["local_hms"] = lambda: (23, 0, 0)
check("night: disabled never active", ns["night_active"]() is False)
cfg["night_mode"] = True
cfg["night_brightness"] = 25
ns["local_hms"] = _real_hms
page = ns["_admin_page"]()
check("admin: night fields",
      'name="night_mode"' in page and 'name="night_start"' in page
      and 'name="night_end"' in page
      and 'name="night_brightness"' in page)

print()
if failures:
    print("FAILURES:", failures)
    sys.exit(1)
print("ALL CHECKS PASSED")
