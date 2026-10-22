"""
KPS Server — tracks keys with pynput, reads game state from tosu (optional),
broadcasts to HTML overlay via WebSocket, and serves embedded HTML overlay via HTTP.
"""
import asyncio
import json
import os
import re
import sys
import time
import threading
import subprocess
import configparser
import http.server
from collections import deque
from pynput import keyboard as kb

try:
    import websockets
except ImportError:
    print("[ERROR] websockets not installed. Run: pip install websockets")
    input("Press Enter to exit...")
    sys.exit(1)

# ── Locate base directory & config ────────────────────────
def base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE        = base_dir()
CONFIG_PATH = os.path.join(BASE, 'config.ini')

# ── Embedded HTML fallback for OBS Browser Source ────────
EMBEDDED_OVERLAY_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>KPS Overlay</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; user-select: none; }
    body {
      background: transparent;
      overflow: hidden;
      font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      color: #ffffff;
    }
    #container {
      display: flex;
      flex-direction: column;
      align-items: center;
      transition: opacity 0.12s ease-out;
      opacity: 0.1;
      padding: 10px;
    }
    .meter-box {
      position: relative;
      width: 120px;
      height: 120px;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 12px;
    }
    .circle-bg {
      position: absolute;
      inset: 0;
      border-radius: 50%;
      background: #1a1a1a;
      transition: background 0.15s ease-out, box-shadow 0.15s ease-out;
    }
    .circle-ring {
      position: absolute;
      inset: -3px;
      border-radius: 50%;
      border: 2px solid #333333;
      transition: border-color 0.15s ease-out, box-shadow 0.15s ease-out;
    }
    .meter-content {
      position: relative;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      z-index: 2;
    }
    .kps-num {
      font-size: 40px;
      font-weight: 700;
      line-height: 1;
      color: #ffffff;
      font-feature-settings: "tnum";
      font-variant-numeric: tabular-nums;
      transition: color 0.15s ease-out;
    }
    .kps-label {
      font-size: 9px;
      font-weight: 600;
      letter-spacing: 1px;
      color: #777777;
      margin-top: 4px;
      transition: color 0.15s ease-out;
    }
    .keys-row {
      display: flex;
      gap: 4px;
      justify-content: center;
      align-items: center;
      flex-wrap: nowrap;
    }
    .key-cap {
      min-width: 28px;
      height: 24px;
      padding: 0 6px;
      background: #1e1e1e;
      border: 1px solid #444444;
      border-radius: 4px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 9px;
      font-weight: 700;
      color: #777777;
      transition: all 0.06s cubic-bezier(0.2, 0.8, 0.2, 1);
    }
    .key-cap.pressed {
      transform: translateY(2px) scale(0.97);
    }
  </style>
</head>
<body>
  <div id="container">
    <div class="meter-box">
      <div id="circleBg" class="circle-bg"></div>
      <div id="circleRing" class="circle-ring"></div>
      <div class="meter-content">
        <div id="kpsNum" class="kps-num">0</div>
        <div id="kpsLabel" class="kps-label">KPS</div>
      </div>
    </div>
    <div id="keysRow" class="keys-row"></div>
  </div>
  <script>
    const params = new URLSearchParams(window.location.search);
    const wsPort = params.get('port') || '24051';
    const wsHost = window.location.hostname || 'localhost';
    const wsUrl = `ws://${wsHost}:${wsPort}`;
    const container = document.getElementById('container');
    const kpsNum = document.getElementById('kpsNum');
    const kpsLabel = document.getElementById('kpsLabel');
    const circleBg = document.getElementById('circleBg');
    const circleRing = document.getElementById('circleRing');
    const keysRow = document.getElementById('keysRow');

    function lerp(a, b, t) { return a + (b - a) * t; }

    function getColor(kps) {
      if (kps <= 0)  return [160, 160, 255];
      if (kps <= 8) {
        const t = kps / 8;
        return [Math.round(lerp(160, 80, t)), Math.round(lerp(160, 200, t)), 255];
      }
      if (kps <= 16) {
        const t = (kps - 8) / 8;
        return [Math.round(lerp(80, 0, t)), Math.round(lerp(200, 255, t)), 255];
      }
      if (kps <= 24) {
        const t = (kps - 16) / 8;
        return [Math.round(lerp(0, 80, t)), 255, Math.round(lerp(255, 60, t))];
      }
      if (kps <= 32) {
        const t = (kps - 24) / 8;
        return [Math.round(lerp(80, 255, t)), 255, Math.round(lerp(60, 0, t))];
      }
      if (kps <= 40) {
        const t = (kps - 32) / 8;
        return [255, Math.round(lerp(255, 40, t)), 0];
      }
      if (kps <= 48) {
        const t = (kps - 40) / 8;
        return [Math.round(lerp(255, 160, t)), Math.round(lerp(40, 0, t)), Math.round(lerp(0, 230, t))];
      }
      if (kps <= 56) {
        const t = (kps - 48) / 8;
        return [Math.round(lerp(160, 50, t)), 0, Math.round(lerp(230, 120, t))];
      }
      return [20, 0, 50];
    }

    let renderedKeyIds = '';
    function renderKeys(keys, mainColor, ringColor) {
      const keySignature = keys.map(k => k.id).join(',');
      if (keySignature !== renderedKeyIds) {
        keysRow.innerHTML = '';
        keys.forEach(k => {
          const cap = document.createElement('div');
          cap.id = `key-${k.id}`;
          cap.className = 'key-cap';
          cap.textContent = k.label;
          keysRow.appendChild(cap);
        });
        renderedKeyIds = keySignature;
      }
      keys.forEach(k => {
        const el = document.getElementById(`key-${k.id}`);
        if (!el) return;
        if (k.isPressed) {
          el.classList.add('pressed');
          el.style.backgroundColor = `rgba(${mainColor[0]}, ${mainColor[1]}, ${mainColor[2]}, 0.35)`;
          el.style.borderColor = ringColor;
          el.style.color = `rgb(${mainColor[0]}, ${mainColor[1]}, ${mainColor[2]})`;
          el.style.boxShadow = `0 0 10px rgba(${mainColor[0]}, ${mainColor[1]}, ${mainColor[2]}, 0.5)`;
        } else {
          el.classList.remove('pressed');
          el.style.backgroundColor = '#1e1e1e';
          el.style.borderColor = '#444444';
          el.style.color = '#777777';
          el.style.boxShadow = 'none';
        }
      });
    }

    function updateOverlay(data) {
      const kps = data.kps || 0;
      const opacity = data.opacity ?? 0.1;
      const color = getColor(kps);
      const cStr = `rgb(${color[0]}, ${color[1]}, ${color[2]})`;
      const ringStr = kps > 5 ? `rgba(${color[0]}, ${color[1]}, ${color[2]}, 0.6)` : '#333333';
      const bgStr = kps > 5 ? `rgba(${color[0]}, ${color[1]}, ${color[2]}, 0.12)` : '#1a1a1a';
      const glowStr = kps > 8 ? `0 0 18px rgba(${color[0]}, ${color[1]}, ${color[2]}, 0.4)` : 'none';

      container.style.opacity = opacity;
      kpsNum.textContent = kps;
      kpsNum.style.color = cStr;
      kpsNum.style.textShadow = kps > 0 ? `0 0 14px rgba(${color[0]}, ${color[1]}, ${color[2]}, 0.5)` : 'none';
      kpsLabel.style.color = `rgba(${color[0]}, ${color[1]}, ${color[2]}, 0.7)`;

      circleBg.style.background = bgStr;
      circleBg.style.boxShadow = glowStr;
      circleRing.style.borderColor = ringStr;

      if (Array.isArray(data.keys)) {
        renderKeys(data.keys, color, ringStr);
      }
    }

    function connect() {
      const ws = new WebSocket(wsUrl);
      ws.onmessage = (event) => {
        try { updateOverlay(JSON.parse(event.data)); } catch (e) {}
      };
      ws.onclose = () => {
        container.style.opacity = '0.08';
        setTimeout(connect, 1500);
      };
    }
    connect();
  </script>
</body>
</html>"""

# ── Default configuration ─────────────────────────────────
DEFAULT_CONFIG = """\
[server]
; WebSocket port - overlay connects here for live telemetry
port = 24051
; HTTP port - open this in OBS Browser Source (160x200px)
http_port = 24052
; Tosu address - only needed for osu!mania auto key-switch
tosu_host = localhost:24050

[keys]
; mode = mania | o2jam | custom
; mania  - auto-switches key layout based on beatmap CS from tosu
; o2jam  - always uses the o2jam row, no tosu needed
; custom - always uses the default row, no tosu needed
mode = mania

; osu!mania key layouts (auto-switched by CS value)
4k = q, w, p, [
7k = q, w, e, space, p, [, ]

; o2jam layout (7 keys: s d f space j k l)
o2jam = s, d, f, space, j, k, l

; custom layout (used when mode = custom)
default = q, w, p, [

[timing]
; KPS rolling window in milliseconds
window_ms = 1000
; How often to broadcast to HTML overlay in milliseconds
broadcast_ms = 40
; only count KPS while in osu gameplay - set false for o2jam/custom
only_in_play = false

[opacity]
min_opacity = 0.08
max_opacity = 1.0
"""

cfg = configparser.ConfigParser()
if not os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        f.write(DEFAULT_CONFIG)
    print(f"[INFO] Created config.ini at {CONFIG_PATH}")

cfg.read_dict({
    'server':  {'port': '24051', 'http_port': '24052', 'tosu_host': 'localhost:24050'},
    'keys':    {'mode': 'mania', '4k': 'q,w,p,[', '7k': 'q,w,e,space,p,[,]',
                'o2jam': 's,d,f,space,j,k,l', 'default': 'q,w,p,['},
    'timing':  {'window_ms': '1000', 'broadcast_ms': '40', 'only_in_play': 'false'},
    'opacity': {'min_opacity': '0.08', 'max_opacity': '1.0'},
})
cfg.read(CONFIG_PATH, encoding='utf-8')

# ── Console mode picker ───────────────────────────────────
def pick_mode():
    saved = cfg['keys'].get('mode', 'mania').strip().lower()

    if not sys.stdin.isatty():
        return saved

    try:
        os.system('cls' if os.name == 'nt' else 'clear')
    except Exception:
        pass

    print("=" * 45)
    print("  KPS Overlay Server -- Mode Select")
    print("=" * 45)
    print()
    print("  [1] mania   (auto key-switch via tosu)")
    print("  [2] o2jam   (fixed 7-key layout)")
    print("  [3] custom  (your own key layout)")
    print()
    print(f"  Last used: {saved}  (Press Enter to keep)")
    print()

    options = {'1': 'mania', '2': 'o2jam', '3': 'custom'}
    while True:
        try:
            choice = input("  Pick mode [1/2/3]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return saved

        if choice == '':
            print(f"  >> Using saved mode: {saved}")
            return saved
        if choice in options:
            selected = options[choice]
            print(f"  >> Mode set to: {selected}")
            return selected
        print("  Invalid choice, enter 1, 2, or 3.")

PICKED_MODE = pick_mode()
cfg['keys']['mode'] = PICKED_MODE

def _save_mode_to_disk(mode):
    """Write mode back to config.ini preserving comments."""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            content = f.read()
        content = re.sub(r'^(mode\s*=\s*)\S+', f'mode = {mode}', content, flags=re.MULTILINE)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print(f"[CONFIG] Could not save mode: {e}")

_save_mode_to_disk(PICKED_MODE)

PORT         = int(cfg['server']['port'])
HTTP_PORT    = int(cfg['server'].get('http_port', '24052'))
TOSU_HOST    = cfg['server']['tosu_host']
WINDOW_MS    = int(cfg['timing']['window_ms'])
BROADCAST_MS = int(cfg['timing']['broadcast_ms'])
ONLY_IN_PLAY = cfg['timing']['only_in_play'].strip().lower() == 'true'
MIN_OPACITY  = float(cfg['opacity']['min_opacity'])
MAX_OPACITY  = float(cfg['opacity']['max_opacity'])
KEY_MODE     = PICKED_MODE

def parse_keys(s):
    return [k.strip().lower() for k in s.split(',') if k.strip()]

MANIA_KEYS = {}
for _k, _v in cfg['keys'].items():
    if _k.endswith('k') and _k[:-1].isdigit():
        MANIA_KEYS[int(_k[:-1])] = parse_keys(_v)

O2JAM_KEYS  = parse_keys(cfg['keys'].get('o2jam',   's,d,f,space,j,k,l'))
CUSTOM_KEYS = parse_keys(cfg['keys'].get('default', 'q,w,p,['))

# ── Shared game state ─────────────────────────────────────
state = {
    'game_state': 'Menu',
    'in_play':    False,
    'mode':       KEY_MODE,
    'key_count':  4,
    'beatmap':    '',
    'bpm':        0.0,
}
state_lock = threading.Lock()

# ── Active keys (runtime, can switch for mania) ───────────
if KEY_MODE == 'mania':
    active_keys = MANIA_KEYS.get(4, CUSTOM_KEYS)
elif KEY_MODE == 'o2jam':
    active_keys = O2JAM_KEYS
else:
    active_keys = CUSTOM_KEYS

active_keys_set = set(active_keys)
keys_lock       = threading.Lock()

def update_active_keys(key_count):
    global active_keys, active_keys_set
    if KEY_MODE != 'mania':
        return
    keys = MANIA_KEYS.get(key_count) or MANIA_KEYS.get(4, CUSTOM_KEYS)
    with keys_lock:
        active_keys     = keys
        active_keys_set = set(keys)
    print(f"[KEYS] {key_count}K -> {keys}")

# ── pynput key -> string id ───────────────────────────────
SPECIAL_MAP = {
    kb.Key.space:     'space',
    kb.Key.shift:     'shift', kb.Key.shift_r: 'shift',
    kb.Key.ctrl_l:    'ctrl',  kb.Key.ctrl_r:  'ctrl',
    kb.Key.alt_l:     'alt',   kb.Key.alt_r:   'alt',
    kb.Key.enter:     'enter',
    kb.Key.backspace: 'bksp',
    kb.Key.tab:       'tab',
    kb.Key.up:        'up',    kb.Key.down:  'down',
    kb.Key.left:      'left',  kb.Key.right: 'right',
}
CHAR_MAP = {';':';',"'":"'",',':',','.':'.','/':'/','[':'[',']':']','`':'`','-':'-','=':'='}

def key_to_id(key):
    if key in SPECIAL_MAP:
        return SPECIAL_MAP[key]
    try:
        if hasattr(key, 'char') and key.char:
            c = key.char.lower()
            return CHAR_MAP.get(c, c)
    except Exception:
        pass
    return None

# ── Key tracking ──────────────────────────────────────────
press_log   = deque()
held_since  = {}
pressed_now = set()
press_count = {}
track_lock  = threading.Lock()

def on_press(key):
    k = key_to_id(key)
    with keys_lock:
        watched = active_keys_set
    if k in watched:
        with track_lock:
            if k not in held_since:
                with state_lock:
                    do_count = not ONLY_IN_PLAY or state['in_play']
                if do_count:
                    press_log.append(time.time())
                    press_count[k] = press_count.get(k, 0) + 1
                held_since[k] = time.time()
            pressed_now.add(k)

def on_release(key):
    k = key_to_id(key)
    if k:
        with track_lock:
            held_since.pop(k, None)
            pressed_now.discard(k)

pynput_listener = kb.Listener(on_press=on_press, on_release=on_release)
pynput_listener.daemon = True
pynput_listener.start()
print(f"[PYNPUT] Listener active | mode={KEY_MODE} | keys={active_keys}")

# ── tosu WebSocket client ─────────────────────────────────
async def tosu_client():
    uri = f"ws://{TOSU_HOST}/websocket/v2"
    was_connected = False
    while True:
        try:
            async with websockets.connect(uri, ping_interval=None) as ws:
                if not was_connected:
                    print(f"[TOSU] Connected -> {uri}")
                    was_connected = True
                async for msg in ws:
                    try:
                        _parse_tosu(json.loads(msg))
                    except Exception as e:
                        print(f"[TOSU] Parse error: {e}")
        except Exception:
            if was_connected:
                print("[TOSU] Disconnected — running standalone, retrying quietly...")
                was_connected = False
            await asyncio.sleep(2.5)

def _parse_tosu(data):
    with state_lock:
        state['game_state'] = data.get('state', {}).get('name', 'Menu')
        state['in_play']    = state['game_state'] == 'Play'

        mode_name = (data.get('play', {}).get('mode', {}).get('name')
                     or data.get('settings', {}).get('mode', {}).get('name', 'Osu'))
        state['mode'] = mode_name

        beatmap   = data.get('beatmap', {})
        cs_raw    = beatmap.get('stats', {}).get('cs', {}).get('original', 4)
        key_count = max(1, round(float(cs_raw))) if mode_name == 'Mania' else 4

        if key_count != state['key_count']:
            state['key_count'] = key_count
            update_active_keys(key_count)

        bpm = beatmap.get('stats', {}).get('bpm', {}).get('common', 0)
        state['bpm'] = round(float(bpm), 1)

        artist = beatmap.get('artist', '')
        title  = beatmap.get('title', '')
        state['beatmap'] = f"{artist} - {title}".strip(' -')

# ── KPS calculation ───────────────────────────────────────
def calc_kps():
    now = time.time()
    with track_lock:
        stale = [k for k, t in held_since.items() if now - t > 10.0]
        for k in stale:
            del held_since[k]
            pressed_now.discard(k)
        while press_log and press_log[0] < now - WINDOW_MS / 1000:
            press_log.popleft()
        return len(press_log)

def get_opacity(kps):
    if kps <= 0:  return MIN_OPACITY
    if kps <= 8:  return MIN_OPACITY + kps / 8 * (0.45 - MIN_OPACITY)
    if kps <= 20: return 0.45 + (kps - 8) / 12 * (MAX_OPACITY - 0.45)
    return MAX_OPACITY

def build_payload():
    kps = calc_kps()
    with state_lock:
        s = dict(state)
    with keys_lock:
        keys_list = list(active_keys)
    with track_lock:
        pressing = set(pressed_now)
        counts   = dict(press_count)

    key_data = []
    for i, kid in enumerate(keys_list):
        key_data.append({
            'id':        kid,
            'label':     kid.upper() if len(kid) == 1 else kid.upper()[:3],
            'col':       i + 1,
            'isPressed': kid in pressing,
            'count':     counts.get(kid, 0),
        })

    display_mode = KEY_MODE if KEY_MODE != 'mania' else s['mode']
    return {
        'kps':       kps,
        'opacity':   round(get_opacity(kps), 3),
        'inPlay':    s['in_play'],
        'gameState': s['game_state'],
        'mode':      display_mode,
        'keyCount':  len(keys_list),
        'beatmap':   s['beatmap'],
        'bpm':       s['bpm'],
        'keys':      key_data,
    }

# ── WebSocket server -> HTML clients ─────────────────────
clients      = set()
clients_lock = asyncio.Lock()

async def ws_handler(websocket):
    async with clients_lock:
        clients.add(websocket)
    addr = getattr(websocket, 'remote_address', 'client')
    print(f"[WS] Overlay connected from {addr}")
    try:
        await websocket.wait_closed()
    finally:
        async with clients_lock:
            clients.discard(websocket)
        print(f"[WS] Overlay disconnected")

async def broadcaster():
    interval = BROADCAST_MS / 1000
    while True:
        await asyncio.sleep(interval)
        if not clients:
            continue
        payload = json.dumps(build_payload())
        dead = set()
        async with clients_lock:
            for ws in list(clients):
                try:
                    await ws.send(payload)
                except Exception:
                    dead.add(ws)
            clients.difference_update(dead)

# ── HTTP Server (serves overlay.html for OBS) ─────────────
class OverlayHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        # Prefer external overlay.html if present, else use embedded HTML
        local_html = os.path.join(BASE, 'overlay.html')
        content = None
        if os.path.exists(local_html):
            try:
                with open(local_html, 'rb') as f:
                    content = f.read()
            except Exception:
                pass

        if not content:
            content = EMBEDDED_OVERLAY_HTML.encode('utf-8')

        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(content)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        # Suppress noisy HTTP request logging
        pass

def start_http_server(port):
    try:
        httpd = http.server.ThreadingHTTPServer(('0.0.0.0', port), OverlayHTTPRequestHandler)
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        print(f"[HTTP] OBS Browser Source ready: http://localhost:{port}/")
        return httpd
    except Exception as e:
        print(f"[HTTP] Could not start HTTP server on port {port}: {e}")
        return None

# ── Port helper ───────────────────────────────────────────
def free_port(port):
    try:
        out = subprocess.check_output(
            f'netstat -ano | findstr ":{port} "',
            shell=True, stderr=subprocess.DEVNULL, text=True
        )
        pids = set(re.findall(r'(\d+)\s*$', out, re.MULTILINE))
        pids.discard('0')
        for pid in pids:
            subprocess.call(f'taskkill /F /PID {pid}',
                            shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[SERVER] Freed port {port} (killed PID {pid})")
        return bool(pids)
    except Exception as e:
        return False

# ── Main ─────────────────────────────────────────────────
async def main():
    print()
    print("=" * 45)
    print("  KPS Server running!")
    print(f"  • WebSocket broadcast : ws://127.0.0.1:{PORT}")
    print(f"  • OBS Browser Source  : http://localhost:{HTTP_PORT}/")
    print(f"  • Mode                : {KEY_MODE}")
    print("=" * 45)
    print()

    # Free busy ports if leftover
    for p in (PORT, HTTP_PORT):
        try:
            free_port(p)
        except Exception:
            pass

    # Start built-in HTTP server
    start_http_server(HTTP_PORT)

    # Start WebSocket server
    try:
        ws_server = await websockets.serve(ws_handler, '0.0.0.0', PORT)
    except OSError as e:
        if e.errno == 10048 or '10048' in str(e):
            print(f"[SERVER] Port {PORT} busy -- freeing and retrying...")
            free_port(PORT)
            await asyncio.sleep(0.5)
            ws_server = await websockets.serve(ws_handler, '0.0.0.0', PORT)
        else:
            raise

    tosu_task = asyncio.create_task(tosu_client())
    bcast     = asyncio.create_task(broadcaster())

    try:
        await asyncio.gather(ws_server.serve_forever(), tosu_task, bcast)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        ws_server.close()
        tosu_task.cancel()
        bcast.cancel()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[SERVER] Stopped.")
