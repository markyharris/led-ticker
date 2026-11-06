# Ticker app - FULL S3 BUILD v2, Nov 6 2026: clock + METAR + stocks +
# verse + joke + NWS weather alerts + news headlines, with WiFi
# provisioning (rehoming). Built on the Nov 5 S3 build
# (ticker_app_s3.py), which was built on the pared interim build
# (Nov 1 2026: clock + METAR only, ticker_app_grey.py).
#
# v4 (Nov 6 2026): GitHub self-update added, ported from LS Lite
# Micro - the app checks markyharris/led-ticker hourly (and once
# after boot), compares each code file's git blob SHA, flags
# "Update available" on the admin page, and Update now downloads,
# verifies, swaps (.bak kept) and reboots. ticker_config.json is
# never touched by updates. (v3 was the same code as v2 plus the
# provisioning join-race fix, renamed for delivery.)
#
# v5 (Nov 6 2026): night mode, mirroring the LS Lite maps - during
# the configured window the sign scales to night_brightness percent
# of the normal intensity; at 0% the sign goes dark while the app,
# admin page and fetches keep running.
#
# v6 (Nov 6 2026): inspirational-quote segment (quotes.py) - one
# quote per refresh from zenquotes.io with dummyjson.com behind
# it, last-good cached, bundled public-domain fallbacks offline.
# Mark's one design note: quotes come from an API, not from him.
#
# What v2 adds (Mark's tweaks, Nov 6 2026):
# - Title cards: when a clock subject is enabled, every content
#   segment is preceded by a static card "3:28 PM - Joke:" naming
#   what is about to show.
# - Wow wipe: a quick full-sign sweep after each segment, replacing
#   the configured wipe while enabled; admin checkbox "wow_wipe".
# - Rehoming (WiFi provisioning, ported from LS Lite Micro): if the
#   saved network cannot be joined, the credentials are blank, or
#   BOOT is held just after power-up (which wipes the credentials),
#   the board raises an open setup AP "LED-Ticker-Setup" with a
#   captive-portal page, scrolls the instructions on the sign, and
#   saving writes ONLY the WiFi fields and reboots.
# - Weather alerts (nws.py): NWS watches/warnings for the point the
#   configured ZIP resolves to (zipgeo.py, api.zippopotam.us), via
#   NOAA's ArcGIS live feed - api.weather.gov's DNS chain defeats
#   the ESP32 resolver, the ArcGIS host resolves normally (Nov 1).
#   Segment appears only while alerts are active.
# - News headlines (news.py): top stories from a wire RSS feed
#   (NPR default, BBC, or a custom URL).
# v1 notes kept for the record:
# - Stocks restored from the Nov 3 stocks trial (ticker_app_stocks.py):
#   Yahoo chart API, up to 12 symbols, admin fields, 10-min refresh.
# - Verse added (verse.py): KJV New Testament verses bundled
#   on-board, no network, one picked per cycle.
# - Joke added (joke.py): icanhazdadjoke.com, one small JSON reply,
#   last-good cached, bundled fallback list when offline.
# - Startup IP splash restored (Nov 1 Phase 2 behaviour, minus the
#   "IP" label per Mark's Nov 1 note): once at boot, after WiFi
#   connects, the sign shows just the address for 5 s, never in
#   the rotation.
# - "ONE MOMENT" static message latched before a fetch round (Nov 3,
#   Mark confirmed it works well on the classic board).
# - 60 s hardware watchdog kept, fed by the display loop.
# Deliberate hygiene kept from the pared build: gc.collect() before
# every fetch, a 60-second retry after a failed fetch, last-good
# data held between fetches, and a "mem free" print each round.
# (v1 kept NWS alerts and breaking news out - they had starved the
# classic board's heap. The S3 has the headroom, and v2 restores
# both at Mark's direction, Nov 6 2026.)
#
# Runs on the ESP32-S3 with max7219.py (the S3 variant: DIN on
# GPIO12 - the S3 has no GPIO23), textclock.py, metar.py,
# stocks.py, verse.py, joke.py, nws.py, news.py and zipgeo.py saved
# alongside it, plus ticker_config.json (settings; created from
# defaults if missing).
# Do NOT overwrite the board's ticker_config.json on updates - the
# app merges new defaults under the saved config, preserving the
# WiFi password.
# Flash recipe (map-board recipe): Thonny 5.0.1 installer, ESP32-S3
# family, GENERIC_S3-SPIRAM-OCT; move the same three signal wires;
# upload via the Files pane and verify on the board.
# Bench use: run from Thonny like the demo; Stop button clears the sign.
#
# Design notes:
# - One cooperative loop: every display frame also services the web
#   server, the 1-second chain re-init (self-healing) and WiFi retries,
#   so the admin page stays responsive while text scrolls.
# - Segments are rebuilt from config at the top of every cycle, so an
#   admin Save takes effect on the next cycle - no reboot.

import time
import json
import gc
import socket
import framebuf
import hashlib
import binascii
import os
import ssl

import network
import ntptime

from max7219 import make_chain
import textclock
import metar as metar_mod
import stocks as stocks_mod
import verse as verse_mod
import joke as joke_mod
import quotes as quotes_mod
import nws as nws_mod
import news as news_mod
import zipgeo

from machine import WDT
import machine

try:
    import urandom
except ImportError:
    urandom = None

NUM_MODULES = 16           # the full sign: 4 quads x 4 modules
CONFIG_FILE = "ticker_config.json"

DEFAULTS = {
    "wifi_ssid": "",
    "wifi_pass": "",
    "tz_offset_hours": -7,          # America/Phoenix: UTC-7 all year
    "brightness": 6,                # MAX7219 intensity 0..15
    "scroll_ms": 40,                # ms per one-column scroll step
    "wipe": "random",               # random|left|right|curtain|dissolve|cut
    "wow_wipe": True,               # quick wow sweep after each segment
    "night_mode": True,             # dim (or darken) during the window
    "night_start": "22:00",         # HH:MM local
    "night_end": "06:00",           # HH:MM local; window may wrap midnight
    "night_brightness": 25,         # percent of normal intensity; 0 = dark
    "metar_ids": ["KFLG"],          # up to 12 ICAO station ids
    "metar_mode": "translated",     # translated | raw
    "stocks": ["AAPL", "GOOGL"],    # up to 12 ticker symbols
    "zip_code": "86001",            # for NWS weather alerts
    "news_feed": "npr",             # npr | bbc | custom
    "news_custom_url": "",          # used when news_feed == "custom"
    "subjects": {
        "clock_normal": True,
        "clock_text": True,
        "metar": True,
        "stocks": True,
        "verse": True,
        "joke": True,
        "quote": True,
        "alerts": True,
        "news": True,
    },
}

SUBJECT_LABELS = [
    ("clock_normal", "Clock - normal (12:15 PM)"),
    ("clock_text", "Clock - text (Quarter after Twelve...)"),
    ("metar", "METAR - up to 12 airports"),
    ("stocks", "Stocks - up to 12 symbols"),
    ("verse", "Bible verse - New Testament (KJV, on-board)"),
    ("joke", "Dad joke - icanhazdadjoke.com"),
    ("quote", "Inspirational quote - zenquotes.io"),
    ("alerts", "Weather alerts - NWS, for the ZIP below"),
    ("news", "News headlines - wire RSS feed"),
]

# Title-card names per segment kind (v2): shown as "3:28 PM - Joke:"
# before the segment when a clock subject is enabled.
SEGMENT_TITLES = {
    "metar": "Weather",
    "stocks": "Stocks",
    "verse": "Verse",
    "joke": "Joke",
    "quote": "Quote",
    "alerts": "Wx Alert",
    "news": "News",
}

# ---------------------------------------------------------------- config

def load_config():
    cfg = dict(DEFAULTS)
    cfg["subjects"] = dict(DEFAULTS["subjects"])
    try:
        with open(CONFIG_FILE) as f:
            saved = json.load(f)
        for k, v in saved.items():
            if k == "subjects" and isinstance(v, dict):
                cfg["subjects"].update(v)
            else:
                cfg[k] = v
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f)


cfg = load_config()
disp = make_chain(NUM_MODULES, intensity=cfg["brightness"])

# ---------------------------------------------------------------- network

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
_synced = False
_ip = None
_last_wifi_try = 0


def wifi_connect():
    global _last_wifi_try
    _last_wifi_try = time.ticks_ms()
    if not cfg["wifi_ssid"]:
        return
    try:
        wlan.connect(cfg["wifi_ssid"], cfg["wifi_pass"])
    except OSError:
        pass


def local_hms():
    """Local (hour, minute, second) from the RTC + configured offset."""
    t = time.localtime(time.time() + int(cfg["tz_offset_hours"]) * 3600)
    return t[3], t[4], t[5]


def network_service():
    """Keep WiFi up and NTP synced; called regularly from the loop."""
    global _synced, _ip
    if wlan.isconnected():
        _ip = wlan.ifconfig()[0]
        if not _synced:
            try:
                ntptime.settime()
                _synced = True
                print("NTP synced; IP", _ip)
            except OSError:
                pass
    else:
        _ip = None
        if time.ticks_diff(time.ticks_ms(), _last_wifi_try) > 30000:
            wifi_connect()


wifi_connect()

# ---------------------------------------------------------------- display

def _hhmm_mins(s):
    """'22:00' -> 1320, or None if the string isn't HH:MM."""
    try:
        hh, mm = str(s).split(":")
        hh, mm = int(hh), int(mm)
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh * 60 + mm
    except (ValueError, AttributeError):
        pass
    return None


def night_active():
    """True inside the configured night window (which may wrap
    past midnight). A malformed or zero-length window is never
    active."""
    if not cfg.get("night_mode"):
        return False
    start = _hhmm_mins(cfg.get("night_start"))
    end = _hhmm_mins(cfg.get("night_end"))
    if start is None or end is None or start == end:
        return False
    h, m, _s = local_hms()
    cur = h * 60 + m
    if start < end:
        return start <= cur < end
    return cur >= start or cur < end


def night_off():
    """Night window with night_brightness at 0: the sign goes dark
    (MAX7219 intensity 0 is still faintly lit, so dark means blank,
    not merely dim)."""
    return night_active() and int(cfg.get("night_brightness", 25)) <= 0


def effective_intensity():
    """The intensity to run right now: the configured brightness,
    scaled to night_brightness percent inside the night window."""
    base = int(cfg["brightness"])
    if night_active():
        pct = int(cfg.get("night_brightness", 25))
        return max(0, min(15, (base * pct + 50) // 100))
    return base


def blank_rest(hold_ms=5000):
    """Keep the sign dark while the loop keeps servicing - the
    night-off stand-in for a segment: watchdog fed, admin page and
    network alive, fetches still happening between segments."""
    disp.fb.fill(0)
    disp.show()
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < hold_ms:
        service()
        time.sleep_ms(50)


def scroll_text(text):
    """Scroll text right-to-left across the sign, demo-style."""
    msg_w = max(1, len(text)) * 8
    msg_buf = bytearray(msg_w)
    msg_fb = framebuf.FrameBuffer(msg_buf, msg_w, 8, framebuf.MONO_VLSB)
    msg_fb.text(text, 0, 0, 1)
    path = bytearray(disp.width + msg_w + disp.width)
    path[disp.width:disp.width + msg_w] = msg_buf
    frame_ms = int(cfg["scroll_ms"])
    step = 0
    last = len(path) - disp.width
    while step <= last:
        for x in range(disp.width):
            disp.buf[x] = path[step + x]
        disp.show()
        service()
        step += 1
        time.sleep_ms(frame_ms)


def static_text(text, hold_ms=4000):
    """Show short text centered, hold, servicing the loop meanwhile."""
    disp.fb.fill(0)
    x = (disp.width - len(text) * 8) // 2
    if x < 0:
        x = 0
    disp.fb.text(text, x, 0, 1)
    disp.show()
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < hold_ms:
        service()
        time.sleep_ms(50)


def show_frame(text):
    """Put short text on the sign and leave it there (no hold).
    The fetch notice: the frame stays latched while a download
    runs, so a slow fetch reads as 'working on it' instead of a
    frozen sign; the next segment redraws over it as soon as the
    fetch finishes. If a fetch wedges, the notice stays up until
    the watchdog resets the board."""
    disp.fb.fill(0)
    x = (disp.width - len(text) * 8) // 2
    if x < 0:
        x = 0
    disp.fb.text(text, x, 0, 1)
    disp.show()


def _wipe_steps(order_chunks):
    for chunk in order_chunks:
        for x in chunk:
            for y in range(8):
                disp.fb.pixel(x, y, 0)
        disp.show()
        service()
        time.sleep_ms(14)


def wipe_out():
    """Blank the current frame with the configured transition."""
    style = cfg["wipe"]
    if style == "random":
        choices = ["left", "right", "curtain", "dissolve"]
        if urandom:
            style = choices[urandom.getrandbits(8) % len(choices)]
        else:
            style = choices[time.ticks_ms() % len(choices)]
    w = disp.width
    if style == "cut":
        disp.fb.fill(0)
        disp.show()
    elif style == "left":
        _wipe_steps([list(range(i, min(i + 2, w))) for i in range(0, w, 2)])
    elif style == "right":
        _wipe_steps([list(range(j, max(j - 2, -1), -1))
                     for j in range(w - 1, -1, -2)])
    elif style == "curtain":
        chunks = []
        lo, hi = 0, w - 1
        while lo <= hi:
            chunk = [lo]
            if hi != lo:
                chunk.append(hi)
            chunks.append(chunk)
            lo += 1
            hi -= 1
        _wipe_steps(chunks)
    elif style == "dissolve":
        cols = list(range(w))
        if urandom:
            for i in range(w - 1, 0, -1):
                j = urandom.getrandbits(8) % (i + 1)
                cols[i], cols[j] = cols[j], cols[i]
        _wipe_steps([cols[i:i + 8] for i in range(0, w, 8)])
    else:
        disp.fb.fill(0)
        disp.show()


def wipe_wow():
    """The 'wow' wipe (v2): a quick full-sign sweep after a segment -
    a bright bar races left-to-right filling the sign, holds a beat,
    then clears right-to-left. Ends blank, like any wipe. About
    0.6 s total, and it replaces the configured wipe while the
    wow_wipe setting is on."""
    w = disp.width
    for x in range(0, w, 4):
        for xx in range(x, min(x + 4, w)):
            for y in range(8):
                disp.fb.pixel(xx, y, 1)
        disp.show()
        service()
        time.sleep_ms(8)
    time.sleep_ms(60)
    for x in range(w - 1, -1, -4):
        for xx in range(max(x - 3, 0), x + 1):
            for y in range(8):
                disp.fb.pixel(xx, y, 0)
        disp.show()
        service()
        time.sleep_ms(8)


# ------------------------------------------------- WiFi provisioning
# Rehoming (v2), ported from LS Lite Micro's captive-portal setup
# mode and rewritten synchronous to match this app's loop. When the
# sign cannot join its saved network - new home, gift, or a BOOT-hold
# wipe at power-up - it hosts an open setup AP and serves a page so
# the WiFi can be entered from a phone. A DNS catch-all answers every
# lookup with the board's own address, which makes the phone pop the
# page up by itself. Saving writes only the two WiFi fields of
# ticker_config.json and reboots.
PROV_AP_SSID = "LED-Ticker-Setup"
PROV_AP_IP = "192.168.4.1"
PROV_JOIN_WAIT_S = 15
PROV_BOOT_WINDOW_S = 3


def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _prov_clean_scan(raw):
    """wlan.scan() output -> (ssid, rssi) pairs, strongest first;
    hidden, duplicate and undecodable names dropped."""
    best = {}
    for entry in raw or ():
        try:
            ssid = entry[0].decode("utf-8").strip()
            rssi = int(entry[3])
        except Exception:
            continue
        if not ssid:
            continue
        if ssid not in best or rssi > best[ssid]:
            best[ssid] = rssi
    return sorted(best.items(), key=lambda kv: -kv[1])


def _prov_scan(sta):
    try:
        return _prov_clean_scan(sta.scan())
    except Exception as e:
        print("provisioning scan failed:", e)
        return []


def _dns_reply(query):
    """Answer one DNS query with PROV_AP_IP, whatever was asked.
    Returns the response packet, or None for a malformed query."""
    try:
        if len(query) < 12:
            return None
        if ((query[4] << 8) | query[5]) < 1:
            return None
        i = 12
        while True:
            if i >= len(query):
                return None
            n = query[i]
            i += 1
            if n == 0:
                break
            if n & 0xC0:
                return None
            i += n
        if i + 4 > len(query):
            return None
        question = query[12:i + 4]
        flags = 0x8000 | (query[2] & 0x79) | 0x0080
        resp = bytearray()
        resp += query[0:2]
        resp += bytes((flags >> 8, flags & 0xFF))
        resp += b"\x00\x01\x00\x01\x00\x00\x00\x00"
        resp += question
        resp += b"\xc0\x0c\x00\x01\x00\x01\x00\x00\x00\x3c\x00\x04"
        for part in PROV_AP_IP.split("."):
            resp.append(int(part))
        return bytes(resp)
    except Exception:
        return None


def _prov_validate(form):
    """Manual SSID wins over the scanned pick. Returns (ssid, pw);
    raises ValueError with a user-facing message."""
    ssid = ((form.get("ssid_manual") or "").strip()
            or (form.get("ssid") or "").strip())
    password = form.get("wifi_password") or ""
    if not ssid:
        raise ValueError("Pick a network from the list, or type its "
                         "name in the box below it.")
    if len(ssid) > 32:
        raise ValueError("That network name is too long - Wi-Fi "
                         "names are at most 32 characters.")
    if len(password) > 64:
        raise ValueError("That password is too long - Wi-Fi "
                         "passwords are at most 64 characters.")
    return ssid, password


def _prov_apply(ssid, password):
    """Write ONLY the WiFi fields of the config and save."""
    fresh = load_config()
    fresh["wifi_ssid"] = ssid
    fresh["wifi_pass"] = password
    save_config(fresh)
    cfg["wifi_ssid"] = ssid
    cfg["wifi_pass"] = password


_PROV_PAGE = """<!DOCTYPE html><html><head><title>LED Ticker - WiFi Setup</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body { font-family: sans-serif; max-width: 34em; margin: 1em auto; padding: 0 1em; }
input, select { font-size: 1em; padding: 0.3em; width: 100%; box-sizing: border-box; }
button { font-size: 1em; padding: 0.4em 1.2em; }
</style></head><body>
<h2>LED Ticker &mdash; WiFi Setup</h2>
%%ERR%%
<p>This sign is not on a Wi-Fi network yet. You are connected to its
own setup network, <strong>LED-Ticker-Setup</strong>. Tell it which
network to join and that network's password; it saves them, restarts,
and joins - this setup network then disappears, so reconnect your
phone to your normal Wi-Fi afterwards.</p>
<form method="post" action="/save">
<p><label for="ssid">Network</label><br>
<select name="ssid" id="ssid">%%OPTIONS%%</select></p>
<p><label for="ssid_manual">... or type the name instead (hidden networks)</label><br>
<input name="ssid_manual" id="ssid_manual" autocomplete="off"></p>
<p><label for="wifi_password">Wi-Fi password (blank for an open network)</label><br>
<input name="wifi_password" id="wifi_password" type="password"></p>
<p><label><input type="checkbox" id="show_pw" style="width:auto"
onchange="document.getElementById('wifi_password').type = this.checked ? 'text' : 'password'">
Show password</label></p>
<p><button type="submit">Save and restart</button></p>
</form>
<p><a href="/rescan">Rescan for networks</a></p>
</body></html>"""


def _prov_page(nets, error=""):
    options = "".join(
        '<option value="%s">%s (%d dBm)</option>'
        % (_esc(ssid), _esc(ssid), rssi) for ssid, rssi in nets)
    if not options:
        options = '<option value="">(no networks found)</option>'
    err = ('<p style="color:#b00"><strong>%s</strong></p>'
           % _esc(error)) if error else ""
    return (_PROV_PAGE.replace("%%ERR%%", err)
            .replace("%%OPTIONS%%", options))


def _prov_boot_held():
    """One sample of the BOOT button (GPIO0). Held = low."""
    try:
        from machine import Pin
        return Pin(0, Pin.IN, Pin.PULL_UP).value() == 0
    except Exception:
        return False


def _prov_boot_requested():
    """True when BOOT is held through the whole startup window -
    the deliberate 're-provision this sign' gesture. The hold must
    start just AFTER power-up: holding it during plug-in puts the
    S3 in download mode and nothing runs."""
    if not _prov_boot_held():
        return False
    deadline = time.ticks_add(time.ticks_ms(),
                              PROV_BOOT_WINDOW_S * 1000)
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        if not _prov_boot_held():
            return False
        time.sleep(0.05)
    return True


def _prov_try_join():
    """Wait for the boot-time join, then one fresh attempt.

    The module-level wifi_connect() at import starts a join that is
    still in flight when this runs, and connect() during an
    in-progress join raises 'Wifi Internal State Error' - seen on
    the board Nov 6 2026, where it sent a perfectly joinable sign
    into setup mode. So: first just wait for the in-flight join to
    land; only if it doesn't, disconnect (stops any retry loop) and
    make one fresh attempt; and if that attempt still cannot be
    placed, wait once more before giving up."""
    ssid = cfg.get("wifi_ssid", "") or ""
    if not ssid:
        return False
    for _ in range(PROV_JOIN_WAIT_S * 2):
        if wlan.isconnected():
            return True
        time.sleep(0.5)
    try:
        wlan.disconnect()
        time.sleep(0.5)
    except Exception:
        pass
    try:
        print("provisioning check: retrying join to '%s'" % ssid)
        wlan.connect(ssid, cfg.get("wifi_pass", ""))
    except Exception as e:
        print("provisioning join attempt failed:", e)
    for _ in range(PROV_JOIN_WAIT_S * 2):
        if wlan.isconnected():
            print("provisioning check: joined on the retry")
            return True
        time.sleep(0.5)
    try:
        wlan.disconnect()   # stop retrying a dead join, or it
    except Exception:       # starves the setup page's scans
        pass
    return False


def _prov_needed():
    """Setup mode when BOOT was held (also wipes the credentials),
    when there are no credentials, or when the saved network
    cannot be joined."""
    if _prov_boot_requested():
        print("BOOT held at startup - forgetting the saved Wi-Fi")
        cfg["wifi_ssid"] = ""
        cfg["wifi_pass"] = ""
        try:
            save_config(cfg)
        except Exception as e:
            print("could not save the wiped Wi-Fi config:", e)
        return True
    if not (cfg.get("wifi_ssid", "") or ""):
        print("no Wi-Fi credentials in config - setup mode")
        return True
    if wlan.isconnected() or _prov_try_join():
        return False
    print("saved Wi-Fi '%s' would not join - setup mode"
          % cfg.get("wifi_ssid", ""))
    return True


def _prov_handle_conn(conn, ctx):
    """One portal request: the page, its save POST (which reboots),
    or a 302 to the page for everything else - the captive-portal
    probes phones fire off all land on the form."""
    try:
        conn.settimeout(1.0)
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 8192:
            chunk = conn.recv(1024)
            if not chunk:
                break
            data += chunk
        if not data:
            return
        head, _, body = data.partition(b"\r\n\r\n")
        lines = head.decode().split("\r\n")
        parts = lines[0].split(" ")
        if len(parts) < 2:
            return
        method = parts[0]
        path = parts[1].split("?")[0]
        clen = 0
        for ln in lines[1:]:
            if ln.lower().startswith("content-length:"):
                clen = int(ln.split(":", 1)[1].strip())
        while len(body) < clen and len(body) < 8192:
            chunk = conn.recv(1024)
            if not chunk:
                break
            body += chunk
        if method == "GET" and path in ("/", "/rescan"):
            if path == "/rescan" or ctx["nets"] is None:
                ctx["nets"] = _prov_scan(wlan)
            page = _prov_page(ctx["nets"]).encode()
            conn.send(b"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n"
                      b"Content-Length: %d\r\n\r\n" % len(page) + page)
        elif method == "POST" and path == "/save":
            form = _parse_form(body.decode())
            try:
                ssid, password = _prov_validate(form)
            except ValueError as e:
                page = _prov_page(ctx["nets"] or [],
                                  str(e)).encode()
                conn.send(b"HTTP/1.0 200 OK\r\nContent-Type: text/html"
                          b"\r\nContent-Length: %d\r\n\r\n"
                          % len(page) + page)
                return
            _prov_apply(ssid, password)
            page = (b"<!DOCTYPE html><html><body style=\"font-family:"
                    b"sans-serif\"><h2>Saved</h2><p>The sign is "
                    b"restarting and will join <strong>"
                    + _esc(ssid).encode()
                    + b"</strong>. This setup network will disappear "
                    b"- reconnect your phone to your normal Wi-Fi.</p>"
                    b"</body></html>")
            conn.send(b"HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n"
                      b"Content-Length: %d\r\n\r\n" % len(page) + page)
            conn.close()
            time.sleep(1)
            machine.reset()
        else:
            conn.send(b"HTTP/1.0 302 Found\r\nLocation: http://"
                      + PROV_AP_IP.encode() + b"/\r\n\r\n")
    except OSError:
        pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def _prov_run():
    """Setup mode: open AP + DNS catch-all + portal, scrolling the
    instructions on the sign, until a save reboots the board. Runs
    before the watchdog/service machinery of the main loop; feeds
    the watchdog itself."""
    print("Provisioning: raising setup AP", PROV_AP_SSID)
    try:
        wlan.disconnect()
    except Exception:
        pass
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    try:
        ap.config(essid=PROV_AP_SSID, authmode=0)
    except Exception:
        ap.config(essid=PROV_AP_SSID)
    dns = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    dns.bind(("", 53))
    dns.settimeout(0.02)
    http = socket.socket()
    http.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    http.bind(("", 80))
    http.listen(2)
    http.settimeout(0)
    ctx = {"nets": None}
    # Non-blocking scroller for the setup instructions.
    msg = ("WIFI SETUP - JOIN %s - THEN OPEN %s"
           % (PROV_AP_SSID, PROV_AP_IP))
    msg_w = max(1, len(msg)) * 8
    msg_buf = bytearray(msg_w)
    msg_fb = framebuf.FrameBuffer(msg_buf, msg_w, 8,
                                  framebuf.MONO_VLSB)
    msg_fb.text(msg, 0, 0, 1)
    path = bytearray(disp.width + msg_w + disp.width)
    path[disp.width:disp.width + msg_w] = msg_buf
    step = 0
    last = len(path) - disp.width
    last_step = time.ticks_ms()
    while True:
        if _wdt is not None:
            _wdt.feed()
        try:
            query, addr = dns.recvfrom(512)
            reply = _dns_reply(query)
            if reply:
                dns.sendto(reply, addr)
        except OSError:
            pass
        try:
            conn, _addr = http.accept()
            _prov_handle_conn(conn, ctx)
        except OSError:
            pass
        now = time.ticks_ms()
        if time.ticks_diff(now, last_step) >= 60:
            for x in range(disp.width):
                disp.buf[x] = path[step + x]
            disp.show()
            step = step + 1 if step < last else 0
            last_step = now
        time.sleep_ms(5)




_server = None


def _unquote(s):
    s = s.replace("+", " ")
    out = ""
    i = 0
    while i < len(s):
        if s[i] == "%" and i + 2 < len(s):
            try:
                out += chr(int(s[i + 1:i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass
        out += s[i]
        i += 1
    return out


def _parse_form(body):
    params = {}
    for pair in body.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            params[_unquote(k)] = _unquote(v)
    return params


def _admin_page(msg=""):
    subs = cfg["subjects"]
    rows = ""
    for key, label in SUBJECT_LABELS:
        checked = " checked" if subs.get(key) else ""
        rows += ('<label style="display:block;margin:4px 0">'
                 '<input type="checkbox" name="sub_%s"%s> %s</label>'
                 % (key, checked, label))
    wipe_opts = ""
    for w in ("random", "left", "right", "curtain", "dissolve", "cut"):
        sel = " selected" if cfg["wipe"] == w else ""
        wipe_opts += '<option value="%s"%s>%s</option>' % (w, sel, w)
    metar_fields = ""
    for i in range(12):
        val = cfg["metar_ids"][i] if i < len(cfg["metar_ids"]) else ""
        metar_fields += ('<input type="text" name="metar_%d" value="%s" '
                         'size="6" maxlength="4" style="margin:2px">' % (i, val))
    mode_opts = ""
    for mode, label in (("translated", "Translated (plain English)"),
                        ("raw", "Raw METAR text")):
        sel = " selected" if cfg["metar_mode"] == mode else ""
        mode_opts += '<option value="%s"%s>%s</option>' % (mode, sel, label)
    stock_fields = ""
    for i in range(12):
        val = cfg["stocks"][i] if i < len(cfg["stocks"]) else ""
        stock_fields += ('<input type="text" name="stock_%d" value="%s" '
                         'size="6" maxlength="5" style="margin:2px">' % (i, val))
    feed_opts = ""
    for key, label in (("npr", "NPR top stories"), ("bbc", "BBC world"),
                       ("custom", "Custom URL")):
        sel = " selected" if cfg["news_feed"] == key else ""
        feed_opts += '<option value="%s"%s>%s</option>' % (key, sel, label)
    wow_checked = " checked" if cfg.get("wow_wipe") else ""
    night_checked = " checked" if cfg.get("night_mode") else ""
    if UPDATE_STATE["failed"]:
        update_html = ('<p style="color:#b00">%s</p>'
                       % _esc(UPDATE_STATE["failed"]))
    elif UPDATE_STATE["available"]:
        update_html = (
            '<p style="color:#b58900"><strong>Update available: '
            '%d file(s) changed on GitHub.</strong></p>'
            '<form method="post" action="/update">'
            '<p><button type="submit">Update now</button> '
            'Downloads the new code, verifies it, and reboots. '
            'Your settings are not touched.</p></form>'
            % UPDATE_STATE["files"])
    else:
        update_html = ""
    h, m, _s = local_hms()
    status = ("IP: %s &nbsp; Time: %s (%s) &nbsp; NTP: %s &nbsp; "
              "METAR: %s &nbsp; Stocks: %s &nbsp; Joke: %s &nbsp; "
              "Quote: %s &nbsp; Alerts: %s &nbsp; News: %s") % (
        _ip or "not connected",
        textclock.normal_time(h, m),
        textclock.text_time(h, m),
        "synced" if _synced else "waiting",
        "ok" if metar_mod.last_fetch_ok() else "waiting",
        "ok" if stocks_mod.last_fetch_ok() else "waiting",
        "ok" if joke_mod.last_fetch_ok() else "waiting",
        "ok" if quotes_mod.last_fetch_ok() else "waiting",
        "ok" if nws_mod.last_fetch_ok() else "waiting",
        "ok" if news_mod.last_fetch_ok() else "waiting")
    return """<!DOCTYPE html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>LED Ticker Admin</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg"></head>
<body style="font-family:sans-serif;max-width:560px;margin:16px auto;padding:0 12px">
<h2><img src="/favicon.svg" width="34" height="34" alt="" style="vertical-align:-9px;margin-right:8px">LED Ticker Admin</h2>
<p style="color:#444">%s</p>
<p style="color:green">%s</p>
%s
<form method="post" action="/save">
<h3>Subjects to display</h3>
%s
<h3>METAR</h3>
<p style="margin:4px 0">Airport IDs (ICAO, up to 12):<br>%s</p>
<label>Style <select name="metar_mode">%s</select></label>
<h3>Stocks</h3>
<p style="margin:4px 0">Symbols (up to 12):<br>%s</p>
<h3>Weather alerts</h3>
<label>ZIP code (alerts are for this area) <input type="text" name="zip_code" value="%s" size="10" maxlength="10"></label>
<h3>News</h3>
<label>Feed <select name="news_feed">%s</select></label><br><br>
<label>Custom feed URL <input type="text" name="news_custom_url" value="%s" size="40"></label>
<h3>Display</h3>
<label>Brightness (0-15) <input type="number" name="brightness" min="0" max="15" value="%d"></label><br><br>
<label>Scroll speed - ms per step (lower = faster) <input type="number" name="scroll_ms" min="1" max="120" value="%d"></label><br><br>
<label>Wipe between subjects <select name="wipe">%s</select></label><br><br>
<label style="display:block"><input type="checkbox" name="wow_wipe"%s> Wow wipe after each segment (replaces the wipe above while on)</label>
<h3>Night mode</h3>
<label style="display:block"><input type="checkbox" name="night_mode"%s> Night mode - dim during the window below</label><br>
<label>From <input type="text" name="night_start" value="%s" size="5" maxlength="5"></label>
<label> to <input type="text" name="night_end" value="%s" size="5" maxlength="5"></label>
<label> at <input type="number" name="night_brightness" min="0" max="100" value="%d"> %% of normal brightness (0 = sign dark)</label>
<h3>WiFi &amp; time</h3>
<label>SSID <input type="text" name="wifi_ssid" value="%s"></label><br><br>
<label>Password <input type="password" name="wifi_pass" value="%s"></label><br><br>
<label>UTC offset, hours <input type="number" name="tz_offset_hours" min="-12" max="14" value="%d"></label>
<p style="color:#666">Moving the sign to a new network? Power it on and hold the BOOT button (starting just after power-up) for about 3 seconds: it forgets this network and offers its own LED-Ticker-Setup page for the new one.</p>
<p><button type="submit" style="font-size:1.05em;padding:6px 18px">Save</button></p>
<p style="color:#666">Changes apply on the next display cycle.</p>
</form></body></html>""" % (
        status, msg, update_html, rows, metar_fields, mode_opts,
        stock_fields,
        cfg["zip_code"], feed_opts, cfg["news_custom_url"],
        int(cfg["brightness"]), int(cfg["scroll_ms"]), wipe_opts,
        wow_checked,
        night_checked, cfg["night_start"], cfg["night_end"],
        int(cfg["night_brightness"]),
        cfg["wifi_ssid"], cfg["wifi_pass"], int(cfg["tz_offset_hours"]))


# 8x8 LED matrix with a lit 'T' - served at /favicon.svg, used as the
# browser tab icon and next to the admin page title.
ICON_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 80"><rect width="80" height="80" rx="12" fill="#dcdcdc"/><g fill="#8f8380"><circle cx="5" cy="5" r="3.4"/><circle cx="75" cy="5" r="3.4"/><circle cx="5" cy="15" r="3.4"/><circle cx="15" cy="15" r="3.4"/><circle cx="25" cy="15" r="3.4"/><circle cx="55" cy="15" r="3.4"/><circle cx="65" cy="15" r="3.4"/><circle cx="75" cy="15" r="3.4"/><circle cx="5" cy="25" r="3.4"/><circle cx="15" cy="25" r="3.4"/><circle cx="25" cy="25" r="3.4"/><circle cx="55" cy="25" r="3.4"/><circle cx="65" cy="25" r="3.4"/><circle cx="75" cy="25" r="3.4"/><circle cx="5" cy="35" r="3.4"/><circle cx="15" cy="35" r="3.4"/><circle cx="25" cy="35" r="3.4"/><circle cx="55" cy="35" r="3.4"/><circle cx="65" cy="35" r="3.4"/><circle cx="75" cy="35" r="3.4"/><circle cx="5" cy="45" r="3.4"/><circle cx="15" cy="45" r="3.4"/><circle cx="25" cy="45" r="3.4"/><circle cx="55" cy="45" r="3.4"/><circle cx="65" cy="45" r="3.4"/><circle cx="75" cy="45" r="3.4"/><circle cx="5" cy="55" r="3.4"/><circle cx="15" cy="55" r="3.4"/><circle cx="25" cy="55" r="3.4"/><circle cx="55" cy="55" r="3.4"/><circle cx="65" cy="55" r="3.4"/><circle cx="75" cy="55" r="3.4"/><circle cx="5" cy="65" r="3.4"/><circle cx="15" cy="65" r="3.4"/><circle cx="25" cy="65" r="3.4"/><circle cx="55" cy="65" r="3.4"/><circle cx="65" cy="65" r="3.4"/><circle cx="75" cy="65" r="3.4"/><circle cx="5" cy="75" r="3.4"/><circle cx="15" cy="75" r="3.4"/><circle cx="25" cy="75" r="3.4"/><circle cx="35" cy="75" r="3.4"/><circle cx="45" cy="75" r="3.4"/><circle cx="55" cy="75" r="3.4"/><circle cx="65" cy="75" r="3.4"/><circle cx="75" cy="75" r="3.4"/></g><g fill="#ff2d16"><circle cx="15" cy="5" r="3.4"/><circle cx="25" cy="5" r="3.4"/><circle cx="35" cy="5" r="3.4"/><circle cx="45" cy="5" r="3.4"/><circle cx="55" cy="5" r="3.4"/><circle cx="65" cy="5" r="3.4"/><circle cx="35" cy="15" r="3.4"/><circle cx="45" cy="15" r="3.4"/><circle cx="35" cy="25" r="3.4"/><circle cx="45" cy="25" r="3.4"/><circle cx="35" cy="35" r="3.4"/><circle cx="45" cy="35" r="3.4"/><circle cx="35" cy="45" r="3.4"/><circle cx="45" cy="45" r="3.4"/><circle cx="35" cy="55" r="3.4"/><circle cx="45" cy="55" r="3.4"/><circle cx="35" cy="65" r="3.4"/><circle cx="45" cy="65" r="3.4"/></g></svg>'


def _handle_client(conn):
    try:
        conn.settimeout(1.0)
        data = b""
        while b"\r\n\r\n" not in data and len(data) < 8192:
            chunk = conn.recv(1024)
            if not chunk:
                break
            data += chunk
        if not data:
            return
        head, _, body = data.partition(b"\r\n\r\n")
        lines = head.decode().split("\r\n")
        parts = lines[0].split(" ")
        if len(parts) < 2:
            return
        method, path = parts[0], parts[1]
        clen = 0
        for ln in lines[1:]:
            if ln.lower().startswith("content-length:"):
                clen = int(ln.split(":", 1)[1].strip())
        while len(body) < clen and len(body) < 8192:
            chunk = conn.recv(1024)
            if not chunk:
                break
            body += chunk

        if method == "GET" and path == "/api/status":
            h, m, _s = local_hms()
            payload = json.dumps({
                "ip": _ip, "ntp": _synced,
                "time": textclock.normal_time(h, m),
                "subjects": cfg["subjects"],
                "metar_ids": cfg["metar_ids"],
                "metar_mode": cfg["metar_mode"],
                "metar_ok": metar_mod.last_fetch_ok(),
                "stocks": cfg["stocks"],
                "stocks_ok": stocks_mod.last_fetch_ok(),
                "joke_ok": joke_mod.last_fetch_ok(),
                "quote_ok": quotes_mod.last_fetch_ok(),
                "zip_code": cfg["zip_code"],
                "alerts_ok": nws_mod.last_fetch_ok(),
                "alerts_active": nws_mod.segment() is not None,
                "news_feed": cfg["news_feed"],
                "news_ok": news_mod.last_fetch_ok(),
                "wow_wipe": bool(cfg.get("wow_wipe")),
                "night_mode": bool(cfg.get("night_mode")),
                "night_active": night_active(),
                "update_available": UPDATE_STATE["available"],
                "update_files": UPDATE_STATE["files"],
                "update_failed": UPDATE_STATE["failed"]})
            conn.send("HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n" + payload)
        elif method == "GET" and path == "/favicon.svg":
            conn.send("HTTP/1.0 200 OK\r\nContent-Type: image/svg+xml\r\n\r\n" + ICON_SVG)
        elif method == "POST" and path == "/save":
            params = _parse_form(body.decode())
            for key, _label in SUBJECT_LABELS:
                cfg["subjects"][key] = ("sub_" + key) in params
            try:
                cfg["brightness"] = max(0, min(15, int(params.get("brightness", 6))))
                cfg["scroll_ms"] = max(1, min(120, int(params.get("scroll_ms", 40))))
                cfg["tz_offset_hours"] = int(params.get("tz_offset_hours", -7))
            except ValueError:
                pass
            if params.get("wipe") in ("random", "left", "right", "curtain", "dissolve", "cut"):
                cfg["wipe"] = params["wipe"]
            ids = []
            for i in range(12):
                v = params.get("metar_%d" % i, "").strip().upper()
                if v and v not in ids:
                    ids.append(v)
            cfg["metar_ids"] = ids[:12]
            if params.get("metar_mode") in ("translated", "raw"):
                cfg["metar_mode"] = params["metar_mode"]
            syms = []
            for i in range(12):
                v = params.get("stock_%d" % i, "").strip().upper()
                if v and v not in syms:
                    syms.append(v)
            cfg["stocks"] = syms[:12]
            zc = params.get("zip_code", "").strip()
            if zc:
                cfg["zip_code"] = zc[:10]
            if params.get("news_feed") in ("npr", "bbc", "custom"):
                cfg["news_feed"] = params["news_feed"]
            cfg["news_custom_url"] = params.get(
                "news_custom_url", cfg["news_custom_url"]).strip()
            cfg["wow_wipe"] = "wow_wipe" in params
            cfg["night_mode"] = "night_mode" in params
            for key in ("night_start", "night_end"):
                if _hhmm_mins(params.get(key, "")) is not None:
                    cfg[key] = params[key].strip()
            try:
                cfg["night_brightness"] = max(
                    0, min(100, int(params.get("night_brightness", 25))))
            except ValueError:
                pass
            cfg["wifi_ssid"] = params.get("wifi_ssid", cfg["wifi_ssid"])
            cfg["wifi_pass"] = params.get("wifi_pass", cfg["wifi_pass"])
            save_config(cfg)
            feeds_invalidate()
            disp.set_intensity(cfg["brightness"])
            conn.send("HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n"
                      + _admin_page("Saved. Changes apply on the next cycle."))
        elif method == "POST" and path == "/update":
            conn.send("HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n"
                      "<!DOCTYPE html><html><body style=\"font-family:"
                      "sans-serif\"><h2>Updating...</h2><p>Downloading "
                      "the new code from GitHub, verifying it, and "
                      "rebooting. The sign restarts on the new code in "
                      "a few seconds; reload the admin page shortly. "
                      "If the update fails, the reason shows on the "
                      "admin page and the current code keeps "
                      "running.</p></body></html>")
            _apply_update()
        elif method == "GET" and path in ("/", "/index.html"):
            conn.send("HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n"
                      + _admin_page())
        else:
            conn.send("HTTP/1.0 404 Not Found\r\n\r\nNot found")
    except OSError:
        pass
    finally:
        try:
            conn.close()
        except OSError:
            pass


def web_service():
    global _server
    if _ip is None:
        return
    if _server is None:
        try:
            _server = socket.socket()
            _server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            _server.bind(("", 80))
            _server.listen(2)
            _server.settimeout(0)
            print("Admin page at http://" + _ip)
        except OSError:
            _server = None
        return
    try:
        conn, _addr = _server.accept()
    except OSError:
        return
    _handle_client(conn)



# ------------------------------------------------- GitHub self-update
# Ported from LS Lite Micro (v4): the board has no git, so this is
# the file-based equivalent of pull-and-restart. The app checks the
# repo hourly (and once after boot), comparing each code file
# against the git blob SHA GitHub publishes for it. Update now
# downloads the changed files, verifies each SHA, swaps them in
# (old copies kept as .bak) and reboots. ticker_config.json is
# never in the list - it belongs to the board, not the repo.
GITHUB_REPO = "markyharris/led-ticker"
UPDATE_FILES = ("main.py", "max7219.py", "textclock.py", "metar.py",
                "stocks.py", "verse.py", "joke.py", "quotes.py",
                "nws.py", "news.py", "zipgeo.py")
UPDATE_CHECK_MS = 3600 * 1000
UPDATE_TIMEOUT_S = 20
MAX_API_BYTES = 32768
MAX_CODE_BYTES = 131072
UPDATE_AGENT = "led-ticker/1.0 (personal LED scrolling ticker)"
UPDATE_STATE = {"available": False, "files": 0, "failed": "",
                "applying": False}
_last_update_check = None


class _ChunkedStream:
    """readinto() wrapper that decodes HTTP chunked encoding."""

    def __init__(self, sock):
        self._s = sock
        self._buf = bytearray()
        self._left = -1
        self._eof = False

    def _readline(self):
        line = bytearray()
        while not line.endswith(b"\r\n"):
            ch = self._s.read(1)
            if not ch:
                break
            line += ch
        return bytes(line)

    def readinto(self, b):
        if self._eof:
            return 0
        while not self._buf:
            if self._left == -1:
                line = self._readline()
                try:
                    self._left = int(line.strip().split(b";")[0], 16)
                except (ValueError, IndexError):
                    self._eof = True
                    return 0
                if self._left == 0:
                    while True:
                        t = self._readline()
                        if t in (b"\r\n", b"\n", b""):
                            break
                    self._eof = True
                    return 0
            data = self._s.read(min(self._left, 4096))
            if not data:
                self._eof = True
                return 0
            self._left -= len(data)
            self._buf += data
            if self._left == 0:
                self._readline()
                self._left = -1
        n = min(len(b), len(self._buf))
        b[:n] = self._buf[:n]
        # Slice-rebind, not del buf[:n]: MicroPython bytearray has
        # no item deletion.
        self._buf = self._buf[n:]
        return n


def _blob_sha_bytes(data):
    """git blob SHA-1 of a byte string - the hash GitHub lists for
    every file in a repo."""
    h = hashlib.sha1()
    h.update(b"blob " + str(len(data)).encode() + b"\x00")
    h.update(data)
    return binascii.hexlify(h.digest()).decode()


def _file_blob_sha(path):
    """Blob SHA of a file on the board, or None if it doesn't exist."""
    try:
        size = os.stat(path)[6]
    except OSError:
        return None
    h = hashlib.sha1()
    h.update(b"blob " + str(size).encode() + b"\x00")
    try:
        with open(path, "rb") as f:
            while True:
                chunk = f.read(2048)
                if not chunk:
                    break
                h.update(chunk)
    except OSError:
        return None
    return binascii.hexlify(h.digest()).decode()


def _https_get_url(url, max_bytes, depth=0):
    """Small HTTPS GET for the update machinery: body bytes, or
    None on any failure. Follows up to 2 redirects."""
    if depth > 2 or not url.startswith("https://"):
        return None
    rest = url[len("https://"):]
    host, _, p = rest.partition("/")
    path = "/" + p
    try:
        addr = socket.getaddrinfo(host, 443, 0, socket.SOCK_STREAM)[0][-1]
        sock = socket.socket()
        sock.settimeout(UPDATE_TIMEOUT_S)
        sock.connect(addr)
        if hasattr(ssl, "wrap_socket"):
            sock = ssl.wrap_socket(sock, server_hostname=host)
        else:
            sock = ssl.create_default_context().wrap_socket(
                sock, server_hostname=host)
        try:
            req = ("GET %s HTTP/1.1\r\nHost: %s\r\nUser-Agent: %s\r\n"
                   "Accept-Encoding: identity\r\n"
                   "Connection: close\r\n\r\n"
                   % (path, host, UPDATE_AGENT))
            sock.write(req.encode())
            head = bytearray()
            while not head.endswith(b"\r\n\r\n"):
                ch = sock.read(1)
                if not ch:
                    return None
                head += ch
                if len(head) > 8192:
                    return None
            lines = bytes(head).decode().split("\r\n")
            status = int(lines[0].split(" ")[1])
            headers = {}
            for ln in lines[1:]:
                if ":" in ln:
                    k, v = ln.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
            if status in (301, 302, 303, 307, 308):
                return _https_get_url(headers.get("location", ""),
                                      max_bytes, depth + 1)
            if status != 200:
                print("update GET %s -> HTTP %d" % (path, status))
                return None
            if "chunked" in headers.get("transfer-encoding", ""):
                body = _ChunkedStream(sock)
            else:
                body = sock
            out = bytearray()
            buf = bytearray(2048)
            while len(out) <= max_bytes:
                if _wdt is not None:
                    _wdt.feed()
                n = body.readinto(buf)
                if not n:
                    break
                out += buf[:n]
            if len(out) > max_bytes:
                print("update GET %s: body too large" % path)
                return None
            return bytes(out)
        finally:
            try:
                sock.close()
            except OSError:
                pass
    except Exception as e:
        print("update GET failed:", e)
        return None


def _parse_listing(data):
    """GitHub contents-listing JSON -> {name: {sha, download_url}}
    for files only, or None if it doesn't parse."""
    if data is None:
        return None
    try:
        if isinstance(data, bytes):
            data = data.decode()
        items = json.loads(data)
    except (ValueError, TypeError):
        return None
    if not isinstance(items, list):
        return None
    out = {}
    for it in items:
        if isinstance(it, dict) and it.get("type") == "file":
            out[it.get("name", "")] = {
                "sha": it.get("sha", ""),
                "download_url": it.get("download_url") or ""}
    return out


def _fetch_repo_listing():
    # One retry: GitHub's edge occasionally drops the TLS connection
    # mid-handshake (seen on the map boards).
    for attempt in (1, 2):
        listing = _parse_listing(_https_get_url(
            "https://api.github.com/repos/%s/contents/" % GITHUB_REPO,
            MAX_API_BYTES))
        if listing is not None:
            return listing
        if attempt == 1:
            time.sleep(2)
    return None


def _changed_files(listing):
    """(name, info) pairs whose repo SHA differs from the board's."""
    plan = []
    for name in UPDATE_FILES:
        info = listing.get(name)
        if info and _file_blob_sha(name) != info["sha"]:
            plan.append((name, info))
    return plan


def _check_update():
    """Refresh UPDATE_STATE from GitHub. Quiet on network failure."""
    global _last_update_check
    _last_update_check = time.ticks_ms()
    listing = _fetch_repo_listing()
    if listing is None:
        return
    plan = _changed_files(listing)
    UPDATE_STATE["available"] = len(plan) > 0
    UPDATE_STATE["files"] = len(plan)
    if not plan:
        UPDATE_STATE["failed"] = ""
    print("update check: %s" % (
        ("%d file(s) changed on GitHub" % len(plan)) if plan
        else "code is current with GitHub"))


def _apply_update():
    """Download the changed code files, verify each blob SHA, swap
    them in (.bak kept) and reboot. Any failure before the swap
    leaves the running code untouched and records why."""
    if UPDATE_STATE["applying"]:
        return
    UPDATE_STATE["applying"] = True
    staged = []
    try:
        listing = _fetch_repo_listing()
        if listing is None:
            raise Exception("could not reach GitHub")
        plan = _changed_files(listing)
        if not plan:
            UPDATE_STATE["available"] = False
            UPDATE_STATE["files"] = 0
            UPDATE_STATE["failed"] = ""
            return
        for name, info in plan:
            if _wdt is not None:
                _wdt.feed()
            data = _https_get_url(info["download_url"], MAX_CODE_BYTES)
            if data is None:
                time.sleep(2)   # one retry, as in the check
                data = _https_get_url(info["download_url"],
                                      MAX_CODE_BYTES)
            if data is None:
                raise Exception("download of %s failed" % name)
            if _blob_sha_bytes(data) != info["sha"]:
                raise Exception("verification failed for %s" % name)
            with open(name + ".new", "wb") as f:
                f.write(data)
            staged.append(name)
        for name in staged:
            if _file_blob_sha(name) is not None:
                try:
                    os.remove(name + ".bak")
                except OSError:
                    pass
                os.rename(name, name + ".bak")
            try:
                os.rename(name + ".new", name)
            except OSError:
                try:
                    os.rename(name + ".bak", name)
                except OSError:
                    pass
                raise Exception("could not install %s" % name)
        UPDATE_STATE["available"] = False
        UPDATE_STATE["files"] = 0
        UPDATE_STATE["failed"] = ""
        print("update applied (%s); rebooting" % ", ".join(staged))
    except Exception as e:
        UPDATE_STATE["failed"] = ("The last update attempt failed: %s"
                                  % e)
        print("update failed:", e)
        for name in staged:
            try:
                os.remove(name + ".new")
            except OSError:
                pass
    finally:
        UPDATE_STATE["applying"] = False
    if staged and not UPDATE_STATE["failed"]:
        time.sleep(1)
        try:
            machine.reset()
        except Exception:
            pass


# ---------------------------------------------------------------- data feeds

METAR_REFRESH_MS = 10 * 60 * 1000
STOCKS_REFRESH_MS = 10 * 60 * 1000
JOKE_REFRESH_MS = 30 * 60 * 1000
QUOTE_REFRESH_MS = 30 * 60 * 1000
ALERTS_REFRESH_MS = 10 * 60 * 1000
NEWS_REFRESH_MS = 30 * 60 * 1000
_last_metar_fetch = None
_last_stocks_fetch = None
_last_joke_fetch = None
_last_quote_fetch = None
_last_alerts_fetch = None
_last_news_fetch = None


def feeds_invalidate():
    """Force the feeds to refetch at the next cycle (after a Save)."""
    global _last_metar_fetch, _last_stocks_fetch, _last_joke_fetch
    global _last_quote_fetch
    global _last_alerts_fetch, _last_news_fetch
    _last_metar_fetch = None
    _last_stocks_fetch = None
    _last_joke_fetch = None
    _last_quote_fetch = None
    _last_alerts_fetch = None
    _last_news_fetch = None


def _due(last, refresh, now):
    return last is None or time.ticks_diff(now, last) >= refresh


def _stamp(ok, refresh, now):
    """Success: next try one refresh period later. Failure: retry in
    about a minute instead of waiting out the whole period."""
    if ok:
        return now
    return now - refresh + 60000


def data_service():
    """Fetch whatever is due, at the top of a display cycle.
    gc.collect() runs before every fetch: a TLS handshake needs a
    large block of free memory, and leftovers from the previous
    download in the same cycle otherwise starve it - that is what
    the MBEDTLS_ERR_*_ALLOC_FAILED errors on the board were
    (Nov 1 2026). The "mem free" print each round is the budget
    gauge: Phase 2 fetched happily; the Phase 3 app showed 31,872
    and starved."""
    global _last_metar_fetch, _last_stocks_fetch, _last_joke_fetch
    global _last_quote_fetch
    global _last_alerts_fetch, _last_news_fetch
    if _ip is None:
        return
    print("mem free:", gc.mem_free())
    now = time.ticks_ms()
    subs = cfg["subjects"]
    metar_due = subs.get("metar") and cfg["metar_ids"] and _due(
        _last_metar_fetch, METAR_REFRESH_MS, now)
    stocks_due = subs.get("stocks") and cfg["stocks"] and _due(
        _last_stocks_fetch, STOCKS_REFRESH_MS, now)
    joke_due = subs.get("joke") and _due(
        _last_joke_fetch, JOKE_REFRESH_MS, now)
    quote_due = subs.get("quote") and _due(
        _last_quote_fetch, QUOTE_REFRESH_MS, now)
    alerts_due = subs.get("alerts") and cfg["zip_code"] and _due(
        _last_alerts_fetch, ALERTS_REFRESH_MS, now)
    news_due = subs.get("news") and _due(
        _last_news_fetch, NEWS_REFRESH_MS, now)
    if metar_due or stocks_due or joke_due or quote_due \
            or alerts_due or news_due:
        # "ONE MOMENT" latched before a download round (Nov 3, Mark
        # confirmed it works well on the classic board): a wedged
        # download never leaves the sign frozen mid-scroll with no
        # message - the notice stays up until the watchdog resets.
        show_frame("ONE MOMENT")
        now = time.ticks_ms()
    if metar_due:
        gc.collect()
        print("Fetch: METAR")
        ok = metar_mod.fetch(cfg["metar_ids"])
        print("Fetch: METAR done", ok)
        _last_metar_fetch = _stamp(ok, METAR_REFRESH_MS, now)
    if stocks_due:
        gc.collect()
        print("Fetch: stocks")
        ok = stocks_mod.fetch(cfg["stocks"])
        print("Fetch: stocks done", ok)
        _last_stocks_fetch = _stamp(ok, STOCKS_REFRESH_MS, now)
    if joke_due:
        gc.collect()
        print("Fetch: joke")
        ok = joke_mod.fetch()
        print("Fetch: joke done", ok)
        _last_joke_fetch = _stamp(ok, JOKE_REFRESH_MS, now)
    if quote_due:
        gc.collect()
        print("Fetch: quote")
        ok = quotes_mod.fetch()
        print("Fetch: quote done", ok)
        _last_quote_fetch = _stamp(ok, QUOTE_REFRESH_MS, now)
    if alerts_due:
        gc.collect()
        print("Fetch: alerts")
        ok = False
        coords = zipgeo.resolve(cfg["zip_code"])
        if coords:
            ok = nws_mod.fetch(coords[0], coords[1],
                               int(cfg["tz_offset_hours"]))
        else:
            print("Fetch: alerts - ZIP did not resolve")
        print("Fetch: alerts done", ok)
        _last_alerts_fetch = _stamp(ok, ALERTS_REFRESH_MS, now)
    if news_due:
        gc.collect()
        print("Fetch: news")
        ok = news_mod.fetch(news_mod.url_for(
            cfg["news_feed"], cfg["news_custom_url"]))
        print("Fetch: news done", ok)
        _last_news_fetch = _stamp(ok, NEWS_REFRESH_MS, now)
    if _last_update_check is None or time.ticks_diff(
            now, _last_update_check) >= UPDATE_CHECK_MS:
        gc.collect()
        _check_update()


# ---------------------------------------------------------------- loop

_last_reinit = time.ticks_ms()
_wdt = None


def service():
    """Housekeeping called every frame: watchdog, self-heal, network,
    web."""
    global _last_reinit
    if _wdt is not None:
        _wdt.feed()
    now = time.ticks_ms()
    if time.ticks_diff(now, _last_reinit) >= 1000:
        disp.init()
        _last_reinit = now
    network_service()
    web_service()


def build_segments():
    """Current cycle's segments as (kind, payload, title) triples,
    from config. Title is the SEGMENT_TITLES name for content
    segments (None for the clocks and the fallback): the main loop
    turns it into a "3:28 PM - Joke:" card when a clock is on."""
    segs = []
    subs = cfg["subjects"]
    h, m, _s = local_hms()
    if subs.get("clock_normal"):
        segs.append(("static", textclock.normal_time(h, m), None))
    if subs.get("clock_text"):
        if _synced:
            segs.append(("scroll", textclock.text_time(h, m), None))
        else:
            segs.append(("scroll", "Waiting for time sync...", None))
    if subs.get("metar") and cfg["metar_ids"]:
        text = metar_mod.segment(cfg["metar_ids"], cfg["metar_mode"])
        if text is None:
            text = "METAR: waiting for first fetch..."
        segs.append(("scroll", text, SEGMENT_TITLES["metar"]))
    if subs.get("stocks") and cfg["stocks"]:
        text = stocks_mod.segment(cfg["stocks"])
        if text is None:
            text = "Stocks: waiting for first fetch..."
        segs.append(("scroll", text, SEGMENT_TITLES["stocks"]))
    if subs.get("verse"):
        text = verse_mod.segment()
        if text is not None:
            segs.append(("scroll", text, SEGMENT_TITLES["verse"]))
    if subs.get("joke"):
        segs.append(("scroll", joke_mod.segment(),
                     SEGMENT_TITLES["joke"]))
    if subs.get("quote"):
        segs.append(("scroll", quotes_mod.segment(),
                     SEGMENT_TITLES["quote"]))
    if subs.get("alerts"):
        text = nws_mod.segment()
        if text is not None:
            segs.append(("scroll", text, SEGMENT_TITLES["alerts"]))
    if subs.get("news"):
        text = news_mod.segment()
        if text is not None:
            segs.append(("scroll", text, SEGMENT_TITLES["news"]))
    if not segs:
        if _ip:
            segs.append(("scroll", "Ticker admin: http://" + _ip, None))
        else:
            segs.append(("scroll", "Ticker starting - no WiFi yet", None))
    return segs


def show_ip_splash(timeout_ms=20000):
    """Startup IP splash (Phase 2 behaviour, restored): once at boot,
    wait for WiFi (up to timeout_ms), then show just the address -
    no "IP" label, per Mark's Nov 1 note - for 5 s. Never part of
    the rotation. Skips quietly if WiFi never connects."""
    t0 = time.ticks_ms()
    while not wlan.isconnected():
        service()
        if time.ticks_diff(time.ticks_ms(), t0) >= timeout_ms:
            return
        time.sleep_ms(200)
    if _ip:
        print("Splash: showing IP", _ip)
        static_text(_ip, 5000)


def main():
    global _wdt
    print("Ticker app starting (S3 build v6: clock + METAR + stocks + verse + joke + quote + alerts + news, provisioning, self-update, night mode)")
    _wdt = WDT(timeout=60000)
    print("Watchdog armed (60 s)")
    try:
        if _prov_needed():
            _prov_run()   # returns only if setup mode itself fails
    except Exception as e:
        print("Provisioning unavailable:", e)
    show_ip_splash()
    try:
        while True:
            data_service()
            segs = build_segments()
            print("Cycle:", len(segs), "segments")
            subs = cfg["subjects"]
            clock_on = subs.get("clock_normal") or subs.get("clock_text")
            for kind, payload, title in segs:
                if night_off():
                    blank_rest()
                    continue
                eff = effective_intensity()
                if eff != disp.intensity:
                    disp.set_intensity(eff)
                if title and clock_on:
                    h, m, _s = local_hms()
                    static_text("%s - %s:" % (
                        textclock.normal_time(h, m), title), 1800)
                if kind == "static":
                    static_text(payload)
                else:
                    scroll_text(payload)
                if cfg.get("wow_wipe"):
                    wipe_wow()
                else:
                    wipe_out()
    except KeyboardInterrupt:
        disp.clear()
        print("Stopped.")


main()
