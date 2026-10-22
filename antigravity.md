# antigravity.md — Project Context & Agent Guide

## What this is
KPS (Keys Per Second) telemetry overlay for osu!mania and O2Jam.
Two independent components:
1. **Python Server (`kps_server.py`)** — tracks keys via pynput, optional tosu sync, WebSocket broadcast (:24051), and built-in HTTP server (:24052) for OBS Browser Source.
2. **Standalone Desktop Overlay (`kps_overlay.py`)** — lightweight Windows transparent GUI (Tkinter + Win32 topmost), zero browser or server required.

## File structure
```
kps/
  kps_server.py     — server backend (pynput + tosu + WebSocket + HTTP)
  kps_overlay.py    — standalone desktop overlay (Tkinter, Win32 topmost)
  overlay.html      — responsive HTML/CSS/JS overlay for OBS browser source
  config.ini        — server settings (read by kps_server)
  kps_overlay.ini   — desktop overlay settings (read by kps_overlay)
  requirements.txt  — Python dependencies (pynput, websockets, pyinstaller)
  build.bat         — interactive build suite (Server, Overlay, or Both)
  build_server.bat  — compiles dist\kps_server.exe via PyInstaller
  build_overlay.bat — compiles dist\kps_overlay.exe via PyInstaller
  dist\
    kps_server.exe  — compiled server binary
    kps_overlay.exe — compiled desktop overlay binary
    overlay.html    — overlay file served by HTTP server
    config.ini      — server config next to exe
    kps_overlay.ini — overlay config next to exe
```

## Architecture
```
pynput (keyboard) ──┐
                    ├──► kps_server.py ──► WS :24051 ──► HTML overlay
tosu WS :24050  ────┘         │
                              └──► HTTP :24052 (OBS Browser Source)

pynput (keyboard) ──────► kps_overlay.py ──────────────► Transparent Win32 GUI
```

- **WS port 24051** — broadcasts KPS JSON payload every 40ms to overlay clients
- **HTTP port 24052** — serves `overlay.html` (for OBS Browser Source, no tosu needed)
- **tosu WS :24050** — optional; used only for mania auto key-switch (CS) and song metadata

## Payload shape (JSON broadcast)
```json
{
  "kps": 12,
  "opacity": 0.87,
  "inPlay": true,
  "gameState": "Play",
  "mode": "Mania",        // "Mania" | "O2Jam" | "Custom"
  "keyCount": 4,
  "beatmap": "Artist - Title",
  "bpm": 180.0,
  "keys": [
    { "id": "d", "label": "D", "col": 1, "isPressed": false, "count": 42 }
  ]
}
```

## config.ini modes
- `mode = mania`  — auto-switches key layout by beatmap CS from tosu
- `mode = o2jam`  — always uses `[keys] o2jam` row, no tosu needed
- `mode = custom` — always uses `[keys] default` row, no tosu needed

## Key name format
- Regular: `a-z`, `0-9`, `[`, `]`, `;`, `'`, `,`, `.`, `/`, `` ` ``, `-`, `=`
- Special: `space`, `shift`, `ctrl`, `alt`, `enter`, `bksp`, `tab`, `up`, `down`, `left`, `right`

## Color ramp table (KPS)
| KPS | Color | Hex Range |
|---|---|---|
| 0 | Ghost white-blue | `#a0a0ff` |
| 0 → 8 | White-blue → Sky blue | `#a0a0ff` → `#50c8ff` |
| 8 → 16 | Sky blue → Cyan | `#50c8ff` → `#00ffff` |
| 16 → 24 | Cyan → Green | `#00ffff` → `#50ff3c` |
| 24 → 32 | Green → Yellow | `#50ff3c` → `#ffff00` |
| 32 → 40 | Yellow → Orange → Red | `#ffff00` → `#ff2800` |
| 40 → 48 | Red → Purple | `#ff2800` → `#a000e6` |
| 48 → 56 | Purple → Dark Indigo | `#a000e6` → `#320078` |
| 56+ | Deep Indigo | `#140032` |

## Known bugs fixed & refactor notes
- `UnboundLocalError: clients` — fixed with thread-safe client management
- `UnboundLocalError: _last_tosu_sig` — fixed in `_parse_tosu()`
- Hold key spamming KPS — fixed: only count first press (`held_since` guard)
- Stuck keys after alt-tab — fixed: 10s stale timeout auto-releases `held_since`
- Mode not saved — fixed: `_save_mode_to_disk()` writes mode back to `config.ini` via regex
- Config conflict between server and overlay — fixed: separated into `config.ini` and `kps_overlay.ini`
- Missing HTTP server on port 24052 — fixed: implemented built-in `ThreadingHTTPServer` serving `overlay.html`
- Hardcoded build paths — fixed: replaced hardcoded paths with `%~dp0` in all `.bat` scripts
- Port conflict crash — fixed: automated `free_port()` kills orphaned listeners on startup

## Run & development
```bash
# Install dependencies
pip install -r requirements.txt

# Run server (for OBS / Web)
python kps_server.py

# Run standalone desktop overlay
python kps_overlay.py
```

## Build commands
```bash
# Build server binary
build_server.bat
# (Or manually: python -m PyInstaller --onefile --console --name "kps_server" kps_server.py)

# Build desktop overlay binary
build_overlay.bat
# (Or manually: python -m PyInstaller --onefile --noconsole --name "kps_overlay" kps_overlay.py)

# Interactive build suite
build.bat
```

## OBS setup
1. Run `kps_server.exe` (or `python kps_server.py`)
2. In OBS: Add **Browser Source**
3. URL: `http://localhost:24052/`
4. Width: `160`, Height: `200`
5. Check: `Shutdown source when not visible` (optional)
6. Background: Transparent by default

## tosu ingame overlay setup
1. Run `tosu.exe`
2. Ingame overlay URL: `http://localhost:24050/kps-overlay/`
3. Connects to `kps_server` via `ws://localhost:24051`

## Contributors
- **[PaYadyo](https://github.com/PaYadyo)** — Original author & project creator
- **[Antigravity](https://github.com/google-deepmind)** (Google DeepMind) — Refactoring, HTTP server & agent workflows

## GitHub
https://github.com/PaYadyo/kps-overlay
