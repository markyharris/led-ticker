# LED Ticker — HOWTO

Build the sign, wire it, load it, and run it: hardware, wiring,
firmware, first boot, what it shows, the admin page, night mode,
rehoming, updates, and troubleshooting. For the short version, see
[README.md](README.md).

## 1. What you need

| Item | Notes |
|---|---|
| **ESP32-S3-DevKitC-1** (N8R8 used here) | The controller. This build is ESP32-S3 only — its predecessor ran on a classic ESP32, and that board's small heap lost a daily lottery against TLS handshakes; the S3's PSRAM simply doesn't have the problem. Don't mix the two builds' files. |
| **16× MAX7219 8×8 LED modules** | Wired as one chain of 128×8 pixels, arranged as **4 quads of 4 modules**. Keep the quads in their proven order (label them 1–4 as you build). |
| **74ACT125-class level buffer** | Between the ESP32-S3's 3.3 V outputs and the first module's 5 V inputs (a quad buffer; one gate per signal — DIN, CLK, CS). |
| **1000 µF capacitors, one per quad** | Across the 5 V rail at each quad. Install-day insurance against rail sag when a whole quad lights up. |
| **5 V power supply, generously sized** | 128×8 red LEDs at full intensity draw real current; the reference install uses a 5 V / 10 A supply. The ESP32-S3 is powered from the same rail (its own run to the supply, not daisy-chained through a quad). Wall-powered — there is no battery story for this sign. |
| **USB-C cable — data-capable** | For flashing and file upload. A charge-only cable lights the board but never enumerates. |
| **A computer with Thonny 4.1+** | For the one-time firmware flash and the file upload. |

## 2. Firmware — stock MicroPython, no custom build

Unlike some ESP32-S3 display boards, these modules are plain SPI
peripherals, so **stock MicroPython works** — there is no custom
firmware for this project. Use:

- MicroPython **v1.29.0**, image **`GENERIC_S3-SPIRAM_OCT`**
  (the octal-PSRAM S3 build), flashed at **0x0**.

### Burning it with Thonny

1. Connect the board's USB-C to the computer.
2. **Tools → Options → Interpreter** → MicroPython (ESP32), the
   board's serial port.
3. Open the install/update MicroPython dialog and set the
   **family to ESP32-S3** — this decides the write address. In
   Thonny 3.x there is no family selector and S3 firmware lands at
   the classic-ESP32 address instead; the burn "succeeds" and the
   board boot-loops. **Thonny 4.1 or newer is a hard floor.**
4. Pick the `GENERIC_S3-SPIRAM_OCT` image (downloaded from
   MicroPython, or via the dialog's local-image option) and
   install.
5. Stop/Restart and confirm the v1.29.0 REPL banner.

## 3. Wiring

Board → buffer → first module; modules chain out-to-in from there,
quad after quad.

| Signal | ESP32-S3 GPIO |
| ------ | ------------- |
| DIN | **GPIO 12** |
| CLK | GPIO 18 |
| CS | GPIO 13 |

**GPIO 12 for DIN is deliberate:** the ESP32-S3 has no GPIO 23
(its pins run 0–21 and 26–48), which is what the classic-ESP32
build used. If you port wiring notes from a classic-ESP32 MAX7219
project, that is the one pin that must change. The driver talks to
the chain over hardware SPI(1).

Power notes:

- Feed each quad its 5 V with its 1000 µF capacitor across the
  rail at the quad.
- Give the ESP32-S3 its own home run from the 5 V supply to its
  VIN/5V pin rather than tapping a quad's rail — a sagging quad
  rail resetting the controller is the classic failure.
- The chain re-sends its configuration about once a second, so a
  module that glitches from a power transient heals itself.

## 4. Loading the software

1. Download this repository (Code → Download ZIP, or clone it).
2. In Thonny, open **View → Files** and upload these twelve files
   to the board's root, under exactly these names:

   `main.py`, `max7219.py`, `textclock.py`, `metar.py`,
   `stocks.py`, `verse.py`, `joke.py`, `quotes.py`, `nws.py`,
   `news.py`, `zipgeo.py`, `ticker_config.json`

   The eleven `.py` files are the same list as the repo's
   `update_files.txt` — the self-updater's manifest (§10).
   `ticker_config.json` is the settings template: it ships with
   **blank Wi-Fi**, so a fresh board boots straight into setup
   mode (§5).
3. **Upload with the Files pane** (right-click a file →
   "Upload to /"). Do not rely on Thonny's Run button to install
   code: Run executes the *editor's* text for the main script
   while helper modules still load from the board's storage, so a
   module you "ran" may not be on the board at all. After an
   upload, the Files pane's sizes are the truth — check them if a
   change seems not to have taken.
4. Never re-upload `ticker_config.json` over a configured board:
   it holds the board's settings and Wi-Fi password. (Updates
   can't touch it either — §10.)

## 5. First boot and Wi-Fi setup

With the template config (blank Wi-Fi), the board boots into
**setup mode**:

1. The sign scrolls its instructions:
   `WIFI SETUP - JOIN LED-TICKER-SETUP - THEN OPEN 192.168.4.1`
2. Join the open **`LED-Ticker-Setup`** network with a phone. The
   setup page pops up by itself (a DNS catch-all makes it behave
   like a hotel sign-in page); if it doesn't, browse to
   **192.168.4.1**.
3. Pick your network from the scanned list (or type a hidden one),
   enter the password (there's a *Show password* peek), and Save.
   Only the two Wi-Fi fields are written; the board reboots.
4. On the new network the sign joins, syncs its clock by NTP, and
   starts the rotation. Its **admin address** is announced at the
   head of the first rotation — see §6.

If the board was already configured (a rebuild), it simply joins
its saved network at boot; no setup mode.

## 6. What it shows

The sign rotates through the enabled subjects in a fixed order:

**Clock (normal) → Clock (text) → Weather (METAR) → Stocks →
Verse → Joke → Quote → Weather alerts → News**, then loops.

- **Title cards.** When a clock subject is enabled, each content
  segment is introduced by a still card — `3:28 PM - Weather:` —
  held for about two seconds.
- **The wow wipe.** A quick full-sign sweep follows each segment
  (a checkbox in the admin page; the configured wipe style —
  random, left, right, curtain, dissolve or cut — is used
  instead when it's off).
- **Admin scroll.** Once per boot, at the head of the first
  rotation, the sign scrolls `ADMIN <ip>` **twice** — that address
  is the admin page (§7). It is shown at night-mode brightness
  inside the night window, and not at all if night brightness is
  0%. It never appears again until the next boot.
- **ONE MOMENT.** Before each round of network fetches the sign
  latches a still `ONE MOMENT` frame — a slow fetch reads as
  "working on it," not a frozen sign.
- **Alerts are conditional.** The weather-alerts segment exists
  only while NWS has active watches/warnings for the ZIP; with
  none active there is no segment, silently.

Where the content comes from, and how often it refreshes (a failed
fetch retries about a minute later; last-good data is shown in the
meantime):

| Segment | Source | Refresh |
|---|---|---|
| Clock | NTP over Wi-Fi; local time from the configured UTC offset (default −7, America/Phoenix) | continuous |
| Weather | NOAA tgftp per-station METAR text files, decoded on-board (translated) or shown raw | 10 min |
| Stocks | Yahoo Finance chart API (quotes delayed ~15 min) | 10 min |
| Verse | 16 KJV New Testament verses bundled on-board — no network | each cycle |
| Joke | icanhazdadjoke.com, last-good cached, bundled fallbacks offline | 30 min |
| Quote | zenquotes.io, dummyjson.com behind it, last-good cached, bundled public-domain fallbacks | 30 min |
| Alerts | NOAA's ArcGIS live feed of NWS watches/warnings for the ZIP's location (ZIP → coordinates via api.zippopotam.us) | 10 min |
| News | RSS top stories — NPR (default), BBC, or a custom URL; top 3 headlines | 30 min |

Two source choices are scars, documented so nobody "fixes" them:
the alerts come from NOAA's ArcGIS republication because
api.weather.gov's DNS answer (a two-hop CNAME chain) defeats the
ESP32's resolver, and the METARs come from tgftp's plain
per-station files because the aviationweather.gov API's
certificate chain defeated the board's TLS in-app.

## 7. The admin page

Open `http://<the sign's IP>/` (port 80) — the address from the
boot-time `ADMIN <ip>` scroll (§6), or your router's client list.
There is no login; home network only.

The page is one form in eight colour-tinted sections, with the
matrix-'T' icon in the browser tab and beside the title. Pressing
**Save** anywhere saves the whole form and lands you back on the
page with your new values in it — that redisplay *is* the
confirmation. Settings changes apply on the next rotation cycle;
no reboot is needed (or wanted — see the watchdog note in §11).

- **Status** — uptime, Wi-Fi, the time source, memory, and a line
  per feed saying whether its last fetch succeeded; the update
  state (§10) shows here too.
- **Subjects** — a checkbox per segment (§6): clock in both forms,
  weather, stocks, verse, joke, quote, alerts, news. Turn them all
  off and the sign has nothing to rotate — leave at least one on.
- **Weather** — up to **12 airport IDs** for the METAR segment and
  the mode: **translated** (plain English, abbreviated — "Vis 4
  SM, Temp 9, Dewpt 8, Alt 29.93") or **raw** (the report itself,
  remarks cut).
- **Stocks & news** — up to **12 stock symbols**; the **ZIP
  code** the weather alerts are for; the news feed choice (NPR,
  BBC, or custom) and the custom feed URL.
- **Display** — **Brightness** as a slider (MAX7219 intensity
  0–15, default 6), **Scroll speed** as a slider (1–120 ms per
  one-column step, default 40; lower is faster — the real step
  time also includes a few ms of redraw work, so the bottom of
  the range is about 3× the old fastest in practice), the **wipe
  style**, and the **wow wipe** checkbox.
- **Night mode** — §8: the on/off switch, the window, and the
  **night brightness** slider (0–100%).
- **System** — the Wi-Fi SSID/password fields (changing them
  moves the sign at the next boot — §9 is usually the better
  tool), the **UTC offset** in hours (a number box, deliberately
  not a slider), and restart.
- **Update** — the update status and **Update now** (§10).

The same state is available as JSON at `/api/status` — handy for
checking the sign from a script.

## 8. Night mode

During the configured window (default **22:00–06:00**, and it may
wrap midnight) the sign scales to the **night brightness**
percentage of its normal intensity (default 25%). Set night
brightness to **0%** and the sign goes properly dark — the modules
are blanked, not just set to intensity 0, which is still faintly
lit on MAX7219s. The app, the admin page and the fetches keep
running all night; the rotation resumes at full brightness when
the window ends.

## 9. Rehoming — new Wi-Fi or new owner

No keyboard, monitor or reflash. The sign enters setup mode on
its own whenever there is nothing to join:

- **Automatically:** at boot, if no credentials are saved, or the
  saved network can't be joined (it tries, retries once fresh,
  and gives up into setup mode). Moving house needs no preparation
  at all — unplug, move, plug in, and follow §5 from step 2.
- **Forced:** hold the **BOOT** button starting **just after**
  power-up for about 3 seconds. This also **wipes the saved
  credentials**. Timing matters: hold it *after* power-up begins —
  holding BOOT *during* plug-in puts the S3 in firmware-download
  mode and nothing runs (just power-cycle and try again).

In setup mode the sign scrolls its instructions and raises
**LED-Ticker-Setup**; the portal flow is §5, steps 2–3. Saving
writes **only** the two Wi-Fi fields in `ticker_config.json` —
every other setting survives a move untouched.

## 10. Updates

The sign updates its own code from this repository:

- **Checking** is automatic and flag-only: after boot and then
  hourly, the app reads `update_files.txt` **fresh from the repo**
  (the manifest is the authoritative list — an updater with a
  frozen built-in list goes stale the day a release adds a module,
  a lesson learned in production), and compares each listed
  file's git blob SHA with GitHub's.
- **Installing** is always your press: **Update now** downloads
  each changed file, verifies its blob SHA, swaps it in (the old
  copy is kept as a `.bak`), and reboots. It answers with an
  auto-refreshing page that lands back on the admin page once the
  sign is up. A failed verification changes nothing, and the
  reason shows in the admin page.
- **Never touched:** `ticker_config.json` — it is not in the
  manifest, and the manifest reader accepts only plain `.py`
  names, so settings and the Wi-Fi password cannot be pulled into
  an update. New settings defaults in an update merge *under* the
  board's saved config.
- The 60-second watchdog (§11) is fed throughout a download, so
  a slow update doesn't reset the board mid-apply.

## 11. Troubleshooting

| Symptom | Likely cause and cure |
|---|---|
| Board boot-loops right after flashing | Firmware written at the classic-ESP32 address — Thonny older than 4.1, or the family not set to ESP32-S3. Reflash per §2. |
| No serial port with the board plugged in | Charge-only USB-C cable, or the wrong port. §1. |
| Sign dark but admin page alive at night | Night mode at 0% — working as configured (§8). Raise night brightness if you want it dim instead of dark. |
| Sign frozen on one frame, then reboots by itself about a minute later | The 60-second hardware watchdog doing its job: a network call wedged (usually a stalled TLS handshake on a bad network path). The board resets into a fresh heap and retries; the latched `ONE MOMENT` frame is what a wedged fetch leaves on the sign. If it repeats constantly, the network path is the problem, not the sign — check the gateway and the board's signal. |
| Board reboots ~60 s after you press Stop in Thonny | Same watchdog: it can't be disarmed once armed, and a stopped app stops feeding it. Harmless. |
| A code change "doesn't take" after using Thonny's Run | The Run-button trap (§4): Run executes the editor text while modules load from the board. Upload via the Files pane and verify by file size. |
| One feed stale while others update | Check the per-feed lines in the admin Status section. A single failing feed retries about a minute later and shows last-good data meanwhile; persistent failure for one source is usually that source (or its certificate chain) — see the source notes at the end of §6 before changing code. |
| Whole chain garbled or a quad dark | Power first: per-quad capacitor fitted, quad order/labels right, the ESP32 on its own supply run (§3). The chain reconfigures itself about once a second, so a transient glitch heals — a permanent one is wiring or rail. |
| Admin page slow to answer now and then | A fetch round is in progress; the app is one program and downloads briefly monopolise it. Wait and reload. |
| `ADMIN <ip>` scroll missed at boot | It shows twice, once per boot (§6). The address is also in your router's client list, and `/api/status` answers at the same address. |
