# LED Ticker

A scrolling LED matrix sign driven by an ESP32-S3 running
MicroPython: 16 MAX7219 modules (128×8 pixels) showing, in rotation,

- **Clock** — digital ("3:28 PM") and written-out ("Twenty-eight
  minutes past Three...") forms
- **METAR weather** — up to 12 airports, translated to plain English
  or raw
- **Stocks** — up to 12 symbols (Yahoo chart API)
- **Bible verse** — 16 New Testament (KJV) verses bundled on-board,
  no network needed
- **Dad joke** — one per cycle from icanhazdadjoke.com, with
  bundled fallbacks when offline
- **Inspirational quote** — from zenquotes.io (dummyjson.com
  behind it), last-good cached, bundled public-domain fallbacks
- **Weather alerts** — NWS watches/warnings for a ZIP code, with
  the affected areas; appears only while alerts are active
- **News headlines** — top stories from a wire RSS feed (NPR by
  default, BBC, or a custom URL)

Each content segment is introduced by a title card with the current
time ("3:28 PM - Joke:") when a clock subject is enabled, and a
quick "wow" sweep follows each segment (both configurable).

**Night mode** mirrors the LiveSectional maps: during a configured
window (default 22:00–06:00) the sign scales to a percentage of its
normal brightness (default 25%). At 0% the sign goes dark while the
app, admin page, and fetches keep running.

Everything is set from the board's own web admin page — subjects,
airports, symbols, ZIP, brightness, scroll speed — no reflashing to
change settings.

## Hardware

- ESP32-S3-DevKitC-1 (N8R8 used here; firmware
  `GENERIC_S3-SPIRAM-OCT`, MicroPython v1.29.0)
- 16× MAX7219 8×8 modules in 4 quads, through a 74ACT125-class
  level buffer, one 1000 µF capacitor per quad on the 5 V rail
- Wiring (board → buffer → first module):

  | Signal | ESP32-S3 GPIO |
  | ------ | ------------- |
  | DIN    | **GPIO 12**   |
  | CLK    | GPIO 18       |
  | CS     | GPIO 13       |

  **GPIO 12 for DIN is deliberate: the ESP32-S3 has no GPIO 23**
  (its pins run 0–21 and 26–48), which the classic ESP32 build used.
- Power: a 5 V supply sized for the panels; wall-powered.

## Install

1. Flash MicroPython with **Thonny 4.1 or newer** (5.x used here):
   Tools → Options → Interpreter → Install MicroPython, family
   **ESP32-S3**, image `GENERIC_S3-SPIRAM-OCT`. (Thonny 3.x writes
   S3 firmware at the wrong address and the board boot-loops.)
2. Upload these files to the board with Thonny's Files pane, under
   exactly these names: `main.py`, `max7219.py`, `textclock.py`,
   `metar.py`, `stocks.py`, `verse.py`, `joke.py`, `nws.py`,
   `news.py`, `zipgeo.py`, `ticker_config.json`.
3. Power up. With the shipped template config (blank Wi-Fi), the
   sign boots into **setup mode** — see Rehoming below. On a board
   already configured, it joins its network, shows its IP address
   once, and starts the rotation. The admin page is at
   `http://<that-ip>/`.

## Rehoming (Wi-Fi provisioning)

The sign can move to a new network or a new owner with no keyboard,
monitor, or reflash. It enters setup mode when the saved network
can't be joined, when no credentials are saved, or when the **BOOT
button is held starting just after power-up** for ~3 seconds (that
also wipes the saved credentials — note the timing: holding BOOT
*during* plug-in puts the S3 in download mode and nothing runs).

In setup mode the sign scrolls its instructions and raises an open
access point, **LED-Ticker-Setup**. Join it with a phone; the setup
page pops up by itself (a DNS catch-all makes it behave like a
hotel sign-in page; if it doesn't pop, browse to `192.168.4.1`).
Pick the network (or type a hidden one), enter the password, Save —
only the two Wi-Fi fields are written, and the board reboots onto
the new network.

## Self-update

The app checks this repository hourly (and once after boot),
comparing each code file against the git blob SHA GitHub publishes
for it. When files differ, the admin page shows **Update
available** with an **Update now** button: the new files are
downloaded, each verified against its SHA, swapped in with the old
copies kept as `.bak`, and the board reboots. A failed verification
changes nothing and the reason shows on the admin page.
`ticker_config.json` is never touched by updates — settings and the
Wi-Fi password belong to the board.

## Files

| File | What it is |
| ---- | ---------- |
| `main.py` | The app: display loop, web admin, provisioning, self-update |
| `max7219.py` | MAX7219 chain driver (SPI: DIN 12, CLK 18, CS 13) |
| `textclock.py` | Digital and written-out time |
| `metar.py` | METAR fetch (NOAA tgftp) and translation |
| `stocks.py` | Yahoo chart API quotes |
| `verse.py` | Bundled KJV New Testament verses |
| `joke.py` | icanhazdadjoke.com client with fallbacks |
| `quotes.py` | zenquotes.io / dummyjson.com quotes with fallbacks |
| `nws.py` | NWS alerts via NOAA's ArcGIS live feed (the api.weather.gov DNS chain defeats the ESP32 resolver; this host resolves normally) |
| `news.py` | RSS headline parser/fetcher |
| `zipgeo.py` | ZIP → coordinates via api.zippopotam.us |
| `ticker_config.json` | Settings template (blank Wi-Fi) |
| `test_desktop.py` | CPython desktop test suite (stubbed hardware/network) |

## Notes

- A 60-second hardware watchdog is fed by the display loop; a
  wedged download resets the board instead of freezing the sign.
- Settings changes in the admin page apply on the next cycle; the
  app merges new defaults under a saved config, so updates never
  clobber the board's settings or Wi-Fi password.
- Alerts refresh every 10 minutes and show only while active;
  with none active there is no alerts segment at all.
