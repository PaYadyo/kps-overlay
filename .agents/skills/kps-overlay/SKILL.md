---
name: kps-overlay
description: >-
  Development, debugging, testing, and building guide for KPS Overlay (osu!mania, O2Jam, and OBS streaming keypress telemetry). Use when working on kps_server, kps_overlay, overlay HTML/CSS, PyInstaller scripts, or network protocols.
---

# KPS Overlay — Developer & Agent Skill

## Overview
KPS (Keys Per Second) telemetry overlay for rhythm gaming (osu!mania and O2Jam).
Two components:
1. **`kps_server.py`**: Background server (pynput keyboard hook + tosu client + WebSocket :24051 + HTTP :24052 serving `overlay.html` for OBS).
2. **`kps_overlay.py`**: Standalone Windows transparent desktop GUI (Tkinter + Win32 topmost).

## Architecture
```
pynput (keyboard) ──┐
                    ├──► kps_server.py ──► WS :24051 ──► HTML overlay
tosu WS :24050  ────┘         │
                              └──► HTTP :24052 (OBS Browser Source)

pynput (keyboard) ──────► kps_overlay.py ──────────────► Transparent Win32 GUI
```

## Key Files
- `kps_server.py`: Main server broadcasting telemetry on port 24051, serving `overlay.html` on port 24052.
- `kps_overlay.py`: Standalone desktop overlay with dressurf-inspired color ramp.
- `overlay.html`: Responsive HTML/CSS/JS overlay with automatic WebSocket reconnect.
- `config.ini`: Server configuration (`port`, `http_port`, `tosu_host`, `mode`, key bindings).
- `kps_overlay.ini`: Desktop overlay configuration (`watched`, `size`, `position`, `timing`, `opacity`).
- `build.bat`: Unified build menu.
- `build_server.bat` / `build_overlay.bat`: PyInstaller compiler scripts using `%~dp0`.

## JSON Payload Structure (:24051)
```json
{
  "kps": 12,
  "opacity": 0.87,
  "inPlay": true,
  "gameState": "Play",
  "mode": "Mania",
  "keyCount": 4,
  "beatmap": "Artist - Title",
  "bpm": 180.0,
  "keys": [
    { "id": "d", "label": "D", "col": 1, "isPressed": false, "count": 42 }
  ]
}
```

## Common Tasks & Procedures

### 1. Running in Development
```powershell
pip install -r requirements.txt
python kps_server.py
python kps_overlay.py
```

### 2. Building Executables
Run `build.bat` or compile directly:
```powershell
pyinstaller --onefile --console --name "kps_server" kps_server.py
pyinstaller --onefile --noconsole --name "kps_overlay" kps_overlay.py
```
Always verify runtime configuration files (`config.ini`, `overlay.html`, or `kps_overlay.ini`) are placed next to the `.exe` in `dist\`.

### 3. Port Allocation & Troubleshooting
- Default ports: `24051` (WS Broadcast), `24052` (HTTP Server), `24050` (tosu).
- If ports are held by orphaned processes on Windows, `kps_server.py` invokes `free_port()` via `netstat -ano` and `taskkill /F /PID`.

### 4. Mode Logic
- `mania`: Key count adapts dynamically based on beatmap CS received from tosu (`4k`, `7k`, etc.).
- `o2jam`: Uses fixed 7-key layout (`s, d, f, space, j, k, l`), ignoring tosu.
- `custom`: Uses custom layout from `default` row in `config.ini`.
