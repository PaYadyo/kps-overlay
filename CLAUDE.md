# CLAUDE.md — Project Context

## What this is
KPS (Keys Per Second) overlay for osu!mania and O2Jam.
Two components: Python server + HTML overlay.

## File structure
```
D:\Coding\My project\kps\
  kps_server.py     — main Python server (pynput + tosu + WebSocket + HTTP)
  kps_overlay.py    — standalone Windows overlay (tkinter, no server needed)
  config.ini        — server settings (kps_server reads this)
  kps_overlay.ini   — overlay settings (kps_overlay reads this, separate from server)
  build.bat         — compiles kps_server.exe via PyInstaller
  run.bat           — compiles kps_overlay.exe via PyInstaller
  dist\
    kps_server.exe  — compiled server binary
    kps_overlay.exe — compiled overlay binary
    config.ini      — server config next to exe
    kps_overlay.ini — overlay config next to exe
```

## Architecture
```
pynput (keyboard) ──┐
                    ├──► kps_server.py ──► WS :24051 ──► HTML overlay
tosu WS :24050  ────┘         │
                              └──► HTTP :24052 (OBS browser source)
```

- WS port 24051 — broadcasts KPS JSON payload every 40ms to overlay clients
- HTTP port 24052 — serves embedded overlay HTML (for OBS, no tosu needed)
- tosu WS is optional — used only for mania auto key-switch and game state

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
- `mode = o2jam`  — always uses [keys] o2jam row, no tosu needed
- `mode = custom` — always uses [keys] default row, no tosu needed

## Key name format
Regular: `a-z`, `0-9`, `[`, `]`, `;`, `'`, `,`, `.`, `/`, `` ` ``, `-`, `=`
Special: `space`, `shift`, `ctrl`, `alt`, `enter`, `bksp`, `tab`, `up`, `down`, `left`, `right`

## Known bugs fixed
- `UnboundLocalError: clients` — fixed with `global clients` in broadcaster()
- `UnboundLocalError: _last_tosu_sig` — fixed with `global _last_tosu_sig` in _parse_tosu()
- Hold key spamming KPS — fixed: only count first press (held_since guard)
- Stuck keys after alt-tab — fixed: 10s stale timeout auto-releases held_since
- Mode not saved — fixed: `_save_mode_to_disk()` writes mode back to config.ini after pick_mode() using regex replace, preserving comments
- Config conflict between kps_server and kps_overlay — fixed: kps_overlay now reads `kps_overlay.ini` instead of `config.ini`
- Missing o2jam row in config.ini — fixed: added `o2jam = s, d, f, space, j, k, l` and updated comments

## Build command
```
pyinstaller --onefile --noconsole --name "kps_server" kps_server.py
```
Dependencies: `pynput`, `websockets`, `pyinstaller`

## OBS setup
Browser Source → `http://localhost:24052/` → 160×200px, transparent background

## tosu ingame overlay
URL: `http://localhost:24050/kps-overlay/`
Connects to kps_server via `ws://localhost:24051`

## GitHub
https://github.com/PaYadyo/kps-overlay
