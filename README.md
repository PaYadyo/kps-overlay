# 🎯 KPS Overlay for osu!mania & O2Jam

A lightweight, high-performance Keypress-Per-Second (KPS) telemetry suite for rhythm games — inspired by dressurf.

Supports both **OBS Browser Source streaming** and **Direct Desktop HUD Overlay** on Windows with smooth color ramps and opacity effects.

![platform](https://img.shields.io/badge/platform-Windows-blue?style=flat-square)
![python](https://img.shields.io/badge/python-3.10%2B-yellow?style=flat-square)
![license](https://img.shields.io/badge/license-MIT-green?style=flat-square)

---

## 📦 Two Modes to Choose From

| Component | Description | Best For |
|---|---|---|
| **`kps_server.py`** | Background server with WebSocket (`:24051`) and built-in HTTP server (`:24052`). Serves embedded overlay directly. | Streamers, OBS Studio, and tosu integration. |
| **`kps_overlay.py`** | Standalone transparent desktop HUD (Tkinter + Win32 topmost). Zero browser or web server needed. | In-game playing on single monitor setups. |

---

## ✨ Features

- **Live KPS counter** — rolling 1-second window, updates every 40ms.
- **Dynamic Color Ramp** — shifts smoothly across 8 tiers as your speed climbs:

  | KPS | Color | Hex Range |
  |---|---|---|
  | 0 | Ghost white-blue | `#a0a0ff` |
  | 0 → 8 | White-blue → Sky blue | `#a0a0ff` → `#50c8ff` |
  | 8 → 16 | Sky blue → Cyan | `#50c8ff` → `#00ffff` |
  | 16 → 24 | Cyan → Green | `#00ffff` → `#50ff3c` |
  | 24 → 32 | Green → Yellow | `#50ff3c` → `#ffff00` |
  | 32 → 40 | Yellow → Orange → Red | `#ffff00` → `#ff2800` |
  | 40 → 48 | Red → Purple | `#ff2800` → `#a000e6` |
  | 48 → 56 | Purple → Dark Indigo | `#a0a0ff` → `#320078` |
  | 56+ | Near-black deep indigo | `#140032` |

- **Adaptive Opacity** — fades nearly invisible when idle, becomes fully opaque when hitting streams.
- **Dynamic Game Modes**:
  - `mania`: Automatically switches key column layouts (4K, 7K, etc.) based on beatmap CS from tosu.
  - `o2jam`: Fixed 7-key layout (`s, d, f, space, j, k, l`), runs standalone without tosu.
  - `custom`: Your custom keybindings configured in `config.ini`.
- **Built-in HTTP Server** — no web server setup needed. Open `http://localhost:24052/` directly in OBS Browser Source!
- **True Always-On-Top** — Win32 `SetWindowPos` keeps the desktop overlay visible over fullscreen games.
- **Anti-Spam Key Guard** — OS key repeat events are filtered, stuck keys auto-release after timeout.

---

## 🚀 Quick Start

### 1. Run from Source

```bash
# Clone the repository
git clone https://github.com/PaYadyo/kps-overlay.git
cd kps-overlay

# Install dependencies
pip install -r requirements.txt

# Option A: Start OBS Server
python kps_server.py

# Option B: Start Desktop Overlay
python kps_overlay.py
```

### 2. OBS Studio Setup
1. Start `kps_server.exe` (or `python kps_server.py`).
2. In OBS: Add **Browser Source**.
3. Set URL to: `http://localhost:24052/`
4. Width: `160`, Height: `200`
5. Background is completely transparent by default.

---

## 🔨 Building Executables (.exe)

Run the included build suite:
```bat
build.bat
```
Or build individually:
- `build_server.bat` → outputs `dist\kps_server.exe`
- `build_overlay.bat` → outputs `dist\kps_overlay.exe`

---

## ⚙️ Configuration

- **`config.ini`**: Settings for `kps_server.py` (server ports, game mode, mania layouts, timing).
- **`kps_overlay.ini`**: Settings for `kps_overlay.py` (watched keys, circle size, window position, opacity).

---

## 👥 Contributors

- **[PaYadyo](https://github.com/PaYadyo)** — Original author & project creator.
- **[Antigravity](https://github.com/google-deepmind)** (Google DeepMind) — Code refactoring, built-in HTTP server, architecture modernization, and Antigravity skill integration.

---

## 📄 License

Distributed under the [MIT License](LICENSE).
