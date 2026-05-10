# 🎯 KPS Overlay for osu!

A lightweight, always-on-top keypress-per-second overlay for osu! — inspired by dressurf.  
Tracks your keys in real time with smooth color transitions and opacity effects.

![preview](https://img.shields.io/badge/platform-Windows-blue?style=flat-square)
![python](https://img.shields.io/badge/python-3.10%2B-yellow?style=flat-square)
![license](https://img.shields.io/badge/license-MIT-green?style=flat-square)

---

## ✨ Features

- **Live KPS counter** — rolling 1-second window, updates every 40ms
- **Color ramp** — smoothly shifts color as your KPS climbs

  | KPS | Color |
  |-----|-------|
  | 0 | Ghost white-blue |
  | 0 → 8 | White-blue → Sky blue |
  | 8 → 16 | Sky blue → Cyan |
  | 16 → 24 | Cyan → Green |
  | 24 → 32 | Green → Yellow |
  | 32 → 40 | Yellow → Orange → Red |
  | 40 → 48 | Red → Purple |
  | 48 → 56 | Purple → Dark Indigo |
  | 56+ | Near-black deep indigo |

- **Opacity fade** — nearly invisible at idle, fully visible when you're hitting notes
- **Key indicators** — shows which keys are pressed right now
- **Hover stats** — hover for 2 seconds to see total press count per key
- **True always-on-top** — uses Win32 `SetWindowPos` to stay above osu! fullscreen
- **Hold-key fix** — OS key repeat events are ignored, stuck keys auto-release after 2s
- **Draggable** — left-click and drag to reposition anywhere
- **config.ini** — all settings editable without recompiling

---

## 🚀 Quick Start

### Run from source

```bash
pip install pynput
python kps_overlay.py
```

### Build .exe

```bash
pip install pynput pyinstaller
pyinstaller --onefile --noconsole --name "kps_overlay" kps_overlay.py
```

Or just double-click **`build.bat`**.

Your `.exe` will be in the `dist\` folder alongside `config.ini`.

---

## ⚙️ Configuration

Edit `config.ini` (auto-created on first launch) — no recompile needed.

```ini
[keys]
# Regular keys : z, x, c, v, q, w, e, p, [, ]
# Special keys : space, shift, ctrl, alt, enter, bksp, tab
watched = z, x, c, v

[window]
size = 130          # circle size in pixels
position = auto     # auto = bottom-right, or: position = manual
x = 0               # used when position = manual
y = 0

[timing]
window_ms  = 1000   # KPS rolling window (ms)
update_ms  = 40     # UI refresh rate (ms)
topmost_ms = 500    # how often to re-assert always-on-top (ms)
stale_sec  = 2.0    # auto-release stuck keys after N seconds

[opacity]
min_opacity = 0.08  # opacity at 0 KPS
max_opacity = 1.0   # opacity at high KPS
```

---

## 🖱️ Controls

| Action | Result |
|--------|--------|
| Left-click + drag | Move the overlay |
| Hover 2 seconds | Show per-key press counts |
| Left-click on stats | Back to KPS view |
| Right-click | Close the overlay |

---

## 🛠️ Built With

- [Python](https://python.org) — core runtime
- [pynput](https://pypi.org/project/pynput/) — global keyboard listener
- [tkinter](https://docs.python.org/3/library/tkinter.html) — UI rendering
- [PyInstaller](https://pyinstaller.org) — packaging to `.exe`
- Win32 API (`ctypes`) — true always-on-top above fullscreen games

---

## 📁 Project Structure

```
kps/
├── kps_overlay.py   # main source
├── config.ini       # settings (auto-created)
├── build.bat        # one-click build script
└── dist/
    ├── kps_overlay.exe
    └── config.ini
```

---

> made with 💜 for the osu! community
