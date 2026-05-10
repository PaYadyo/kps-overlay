import tkinter as tk
import time
import ctypes
import configparser
import os
import sys
from pynput import keyboard as kb
from collections import deque

# ── Load config.ini ───────────────────────────────────────
def get_base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR    = get_base_dir()
CONFIG_PATH = os.path.join(BASE_DIR, 'config.ini')

DEFAULT_CONFIG = """\
[keys]
# Keys to track. Separate with commas.
# Regular keys : z, x, c, v, q, w, e, p, [, ]
# Special keys : space, shift, ctrl, alt, enter, bksp, tab
watched = z, x, c, v

[window]
# Circle size in pixels
size = 130
# Position: auto = bottom-right corner, or set to manual and fill x/y
position = auto
x = 0
y = 0

[timing]
# Rolling window for KPS calculation (milliseconds)
window_ms = 1000
# UI refresh rate (milliseconds) - lower = smoother but more CPU
update_ms = 40
# How often to re-assert always-on-top (milliseconds)
topmost_ms = 500
# Auto-release a stuck key after this many seconds
stale_sec = 2.0

[opacity]
# Opacity at 0 KPS (0.0 = invisible, 1.0 = fully visible)
min_opacity = 0.08
# Opacity at 10+ KPS
max_opacity = 1.0
"""

cfg = configparser.ConfigParser()

if not os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, 'w') as f:
        f.write(DEFAULT_CONFIG)

cfg.read_dict({
    'keys':    {'watched':     'z, x, c, v'},
    'window':  {'size':        '130',
                'position':    'auto',
                'x':           '0',
                'y':           '0'},
    'timing':  {'window_ms':   '1000',
                'update_ms':   '40',
                'topmost_ms':  '500',
                'stale_sec':   '2.0'},
    'opacity': {'min_opacity': '0.08',
                'max_opacity': '1.0'},
})
cfg.read(CONFIG_PATH)

WATCHED_KEYS = [k.strip().lower() for k in cfg['keys']['watched'].split(',') if k.strip()]
SIZE         = int(cfg['window']['size'])
POS_AUTO     = cfg['window']['position'].strip().lower() == 'auto'
POS_X        = int(cfg['window']['x'])
POS_Y        = int(cfg['window']['y'])
WINDOW_MS    = int(cfg['timing']['window_ms'])
UPDATE_MS    = int(cfg['timing']['update_ms'])
TOPMOST_MS   = int(cfg['timing']['topmost_ms'])
STALE_SEC    = float(cfg['timing']['stale_sec'])
MIN_OPACITY  = float(cfg['opacity']['min_opacity'])
MAX_OPACITY  = float(cfg['opacity']['max_opacity'])

# ── Key state ─────────────────────────────────────────────
press_log   = deque()
held_since  = {}
pressed_ui  = set()
press_count = {k: 0 for k in WATCHED_KEYS}

import threading
lock = threading.Lock()

SPECIAL_MAP = {
    kb.Key.space:     'space',
    kb.Key.shift:     'shift',
    kb.Key.shift_r:   'shift',
    kb.Key.ctrl_l:    'ctrl',
    kb.Key.ctrl_r:    'ctrl',
    kb.Key.alt_l:     'alt',
    kb.Key.alt_r:     'alt',
    kb.Key.enter:     'enter',
    kb.Key.backspace: 'bksp',
    kb.Key.tab:       'tab',
    kb.Key.up:        'up',
    kb.Key.down:      'down',
    kb.Key.left:      'left',
    kb.Key.right:     'right',
}

def key_to_id(key):
    if key in SPECIAL_MAP:
        return SPECIAL_MAP[key]
    try:
        if hasattr(key, 'char') and key.char:
            return key.char.lower()
    except Exception:
        pass
    return None

def on_press(key):
    k = key_to_id(key)
    if k in WATCHED_KEYS:
        with lock:
            if k not in held_since:
                press_log.append(time.time())
                held_since[k] = time.time()
                press_count[k] = press_count.get(k, 0) + 1
            pressed_ui.add(k)

def on_release(key):
    k = key_to_id(key)
    if k:
        with lock:
            held_since.pop(k, None)
            pressed_ui.discard(k)

listener = kb.Listener(on_press=on_press, on_release=on_release)
listener.daemon = True
listener.start()

# ── Win32 always-on-top ───────────────────────────────────
user32         = ctypes.windll.user32
HWND_TOPMOST   = -1
SWP_NOMOVE     = 0x0002
SWP_NOSIZE     = 0x0001
SWP_NOACTIVATE = 0x0010
FLAGS          = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE

def force_topmost(hwnd):
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, FLAGS)

# ── Colors ────────────────────────────────────────────────
def lerp(a, b, t):
    return a + (b - a) * t

def get_color(kps):
    if kps <= 0:
        return (160, 160, 255)          # ghost white-blue
    if kps <= 8:                        # white-blue → sky blue
        t = kps / 8
        return (int(lerp(160, 80, t)), int(lerp(160, 200, t)), 255)
    if kps <= 16:                       # sky blue → cyan
        t = (kps - 8) / 8
        return (int(lerp(80, 0, t)), int(lerp(200, 255, t)), 255)
    if kps <= 24:                       # cyan → green
        t = (kps - 16) / 8
        return (int(lerp(0, 80, t)), 255, int(lerp(255, 60, t)))
    if kps <= 32:                       # green → yellow
        t = (kps - 24) / 8
        return (int(lerp(80, 255, t)), 255, int(lerp(60, 0, t)))
    if kps <= 40:                       # yellow → orange → red
        t = (kps - 32) / 8
        return (255, int(lerp(255, 40, t)), 0)
    if kps <= 48:                       # red → purple
        t = (kps - 40) / 8
        return (int(lerp(255, 160, t)), int(lerp(40, 0, t)), int(lerp(0, 230, t)))
    if kps <= 56:                       # purple → dark indigo
        t = (kps - 48) / 8
        return (int(lerp(160, 50, t)), 0, int(lerp(230, 120, t)))
    return (20, 0, 50)                  # 56+ → near-black deep indigo

def get_opacity(kps):
    if kps <= 0:
        return MIN_OPACITY
    if kps <= 8:                        # nearly invisible → half visible
        t = kps / 8
        return MIN_OPACITY + t * (0.45 - MIN_OPACITY)
    if kps <= 20:                       # half → fully visible
        t = (kps - 8) / 12
        return 0.45 + t * (MAX_OPACITY - 0.45)
    return MAX_OPACITY

def hex3(r, g, b):
    return f'#{r:02x}{g:02x}{b:02x}'

def dim(r, g, b, f):
    return (int(r * f), int(g * f), int(b * f))

def key_label(k):
    return {'space':'SPC','shift':'SHF','ctrl':'CTL','alt':'ALT',
            'enter':'ENT','bksp':'BSP','tab':'TAB',
            'up':'UP','down':'DN','left':'LT','right':'RT'}.get(k, k.upper())

# ── Overlay ───────────────────────────────────────────────
HOVER_SHOW_SEC = 2.0   # seconds to hover before showing stats

class KPSOverlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('KPS Overlay')
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-transparentcolor', '#010101')
        self.root.configure(bg='#010101')

        pad     = 18
        keys    = WATCHED_KEYS
        key_w   = max(28, 10 + len(max(keys, key=len)) * 7)
        key_gap = 4
        row_w   = len(keys) * key_w + (len(keys) - 1) * key_gap
        W       = max(SIZE + pad * 2, row_w + pad * 2)
        H       = SIZE + 40 + pad * 2

        if POS_AUTO:
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            x  = sw - W - 20
            y  = sh - H - 60
        else:
            x, y = POS_X, POS_Y

        self.root.geometry(f'{W}x{H}+{x}+{y}')

        self.canvas = tk.Canvas(self.root, width=W, height=H,
                                bg='#010101', highlightthickness=0)
        self.canvas.pack()

        cx = W // 2
        cy = pad + SIZE // 2
        r  = SIZE // 2
        self.cx = cx
        self.cy = cy
        self.r  = r
        self.W  = W
        self.H  = H
        self.pad = pad

        # ── KPS view ──────────────────────────────────────
        self.bg   = self.canvas.create_oval(cx-r, cy-r, cx+r, cy+r,
                                             fill='#1a1a1a', outline='')
        self.ring = self.canvas.create_oval(cx-r-5, cy-r-5, cx+r+5, cy+r+5,
                                             fill='', outline='#333333', width=1.5)
        self.num  = self.canvas.create_text(cx, cy-5, text='0',
                                             font=('Segoe UI', 42, 'bold'), fill='#ffffff')
        self.lbl  = self.canvas.create_text(cx, cy+r-13, text='KPS',
                                             font=('Segoe UI', 9), fill='#666666')

        key_y = cy + r + pad + 8
        x0    = cx - row_w // 2
        self.key_rects  = {}
        self.key_labels = {}
        for i, k in enumerate(keys):
            kx = x0 + i * (key_w + key_gap)
            rect = self.canvas.create_rectangle(kx, key_y, kx+key_w, key_y+22,
                                                fill='#1e1e1e', outline='#444444', width=1)
            lbl  = self.canvas.create_text(kx+key_w//2, key_y+11,
                                            text=key_label(k),
                                            font=('Segoe UI', 8), fill='#666666')
            self.key_rects[k]  = rect
            self.key_labels[k] = lbl

        # ── Stats panel (hidden by default) ───────────────
        panel_x1 = pad // 2
        panel_y1 = pad // 2
        panel_x2 = W - pad // 2
        panel_y2 = H - pad // 2

        self.panel_bg = self.canvas.create_rectangle(
            panel_x1, panel_y1, panel_x2, panel_y2,
            fill='#111111', outline='#333333', width=1, state='hidden')

        self.panel_title = self.canvas.create_text(
            cx, pad + 10, text='key counts',
            font=('Segoe UI', 9), fill='#666666', state='hidden')

        self.stat_items = []   # list of (rect, key_lbl, count_lbl) per key
        row_h  = 26
        rows_y = pad + 28
        for i, k in enumerate(keys):
            ry = rows_y + i * row_h
            bg = self.canvas.create_rectangle(
                pad, ry, W - pad, ry + row_h - 4,
                fill='#1a1a1a', outline='', state='hidden')
            kl = self.canvas.create_text(
                pad + 10, ry + (row_h - 4) // 2,
                text=key_label(k), anchor='w',
                font=('Segoe UI', 10, 'bold'), fill='#aaaaaa', state='hidden')
            cl = self.canvas.create_text(
                W - pad - 10, ry + (row_h - 4) // 2,
                text='0', anchor='e',
                font=('Segoe UI', 10), fill='#ffffff', state='hidden')
            self.stat_items.append((bg, kl, cl, k))

        self.panel_hint = self.canvas.create_text(
            cx, H - pad - 6, text='right-click to close',
            font=('Segoe UI', 8), fill='#444444', state='hidden')

        # ── Hover tracking ────────────────────────────────
        self._hover_start  = None
        self._showing_stats = False
        self._hover_bar    = self.canvas.create_rectangle(
            cx - r, cy + r - 6, cx - r, cy + r,
            fill='#444444', outline='', state='hidden')

        self.canvas.bind('<Enter>',         self._on_enter)
        self.canvas.bind('<Leave>',         self._on_leave)
        self.canvas.bind('<ButtonPress-1>', self._drag_start)
        self.canvas.bind('<B1-Motion>',     self._drag_move)
        self.canvas.bind('<ButtonPress-3>', lambda e: self.root.destroy())

        self.hwnd         = None
        self.topmost_tick = 0
        self.update()
        self.root.mainloop()

    def _on_enter(self, e):
        if not self._showing_stats:
            self._hover_start = time.time()
            self.canvas.itemconfig(self._hover_bar, state='normal')

    def _on_leave(self, e):
        self._hover_start = None
        if not self._showing_stats:
            self.canvas.itemconfig(self._hover_bar, state='hidden')

    def _show_stats(self):
        self._showing_stats = True
        self.canvas.itemconfig(self._hover_bar, state='hidden')
        # hide KPS view
        for item in [self.bg, self.ring, self.num, self.lbl]:
            self.canvas.itemconfig(item, state='hidden')
        for rect in self.key_rects.values():
            self.canvas.itemconfig(rect, state='hidden')
        for lbl in self.key_labels.values():
            self.canvas.itemconfig(lbl, state='hidden')
        # show stats panel
        self.canvas.itemconfig(self.panel_bg,    state='normal')
        self.canvas.itemconfig(self.panel_title, state='normal')
        self.canvas.itemconfig(self.panel_hint,  state='normal')
        with lock:
            counts = dict(press_count)
        for bg, kl, cl, k in self.stat_items:
            self.canvas.itemconfig(bg, state='normal')
            self.canvas.itemconfig(kl, state='normal')
            self.canvas.itemconfig(cl, text=f'{counts.get(k, 0):,}', state='normal')
        self.root.attributes('-alpha', 0.92)

    def _hide_stats(self):
        self._showing_stats = False
        self._hover_start   = None
        # hide stats panel
        self.canvas.itemconfig(self.panel_bg,    state='hidden')
        self.canvas.itemconfig(self.panel_title, state='hidden')
        self.canvas.itemconfig(self.panel_hint,  state='hidden')
        for bg, kl, cl, k in self.stat_items:
            self.canvas.itemconfig(bg, state='hidden')
            self.canvas.itemconfig(kl, state='hidden')
            self.canvas.itemconfig(cl, state='hidden')
        # restore KPS view
        for item in [self.bg, self.ring, self.num, self.lbl]:
            self.canvas.itemconfig(item, state='normal')
        for rect in self.key_rects.values():
            self.canvas.itemconfig(rect, state='normal')
        for lbl in self.key_labels.values():
            self.canvas.itemconfig(lbl, state='normal')

    def _drag_start(self, e):
        if self._showing_stats:
            self._hide_stats()
            return
        self._dx = e.x_root - self.root.winfo_x()
        self._dy = e.y_root - self.root.winfo_y()

    def _drag_move(self, e):
        if not self._showing_stats:
            self.root.geometry(f'+{e.x_root - self._dx}+{e.y_root - self._dy}')

    def _get_hwnd(self):
        if not self.hwnd:
            try:
                self.hwnd = ctypes.windll.user32.FindWindowW(None, 'KPS Overlay')
            except Exception:
                pass
        return self.hwnd

    def update(self):
        now = time.time()

        with lock:
            stale = [k for k, t in held_since.items() if now - t > STALE_SEC]
            for k in stale:
                del held_since[k]
                pressed_ui.discard(k)
            while press_log and press_log[0] < now - WINDOW_MS / 1000:
                press_log.popleft()
            kps      = len(press_log)
            pressing = set(pressed_ui)

        # ── hover progress bar ─────────────────────────────
        if self._hover_start and not self._showing_stats:
            elapsed = now - self._hover_start
            if elapsed >= HOVER_SHOW_SEC:
                self._show_stats()
            else:
                t   = elapsed / HOVER_SHOW_SEC
                cx  = self.cx
                r   = self.r
                cy  = self.cy
                bar_x1 = cx - r
                bar_x2 = cx - r + int(2 * r * t)
                self.canvas.coords(self._hover_bar,
                                   bar_x1, cy + r - 6, bar_x2, cy + r)

        # ── update stats counts if panel is open ──────────
        if self._showing_stats:
            with lock:
                counts = dict(press_count)
            for bg, kl, cl, k in self.stat_items:
                self.canvas.itemconfig(cl, text=f'{counts.get(k, 0):,}')
            self.root.after(UPDATE_MS, self.update)
            return

        # ── normal KPS display ─────────────────────────────
        r2, g, b = get_color(kps)
        opacity  = get_opacity(kps)
        c_main   = hex3(r2, g, b)
        c_bg     = hex3(*dim(r2, g, b, 0.12)) if kps > 5 else '#1a1a1a'
        c_ring   = hex3(*dim(r2, g, b, 0.5))  if kps > 5 else '#333333'
        c_lbl    = hex3(*dim(r2, g, b, 0.6))

        self.canvas.itemconfig(self.bg,   fill=c_bg)
        self.canvas.itemconfig(self.ring, outline=c_ring)
        self.canvas.itemconfig(self.num,  text=str(kps), fill=c_main)
        self.canvas.itemconfig(self.lbl,  fill=c_lbl)
        self.root.attributes('-alpha', opacity)

        for k in WATCHED_KEYS:
            if k in pressing:
                self.canvas.itemconfig(self.key_rects[k],
                    fill=hex3(*dim(r2, g, b, 0.3)), outline=c_ring)
                self.canvas.itemconfig(self.key_labels[k], fill=c_main)
            else:
                self.canvas.itemconfig(self.key_rects[k],
                    fill='#1e1e1e', outline='#444444')
                self.canvas.itemconfig(self.key_labels[k], fill='#666666')

        self.topmost_tick += UPDATE_MS
        if self.topmost_tick >= TOPMOST_MS:
            self.topmost_tick = 0
            hwnd = self._get_hwnd()
            if hwnd:
                force_topmost(hwnd)

        self.root.after(UPDATE_MS, self.update)


if __name__ == '__main__':
    KPSOverlay()
