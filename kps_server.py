"""
KPS Server — tracks keys with pynput, reads game state from tosu (optional),
broadcasts to HTML overlay via WebSocket.
Works without osu/tosu running — just tracks keys standalone.
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
from collections import deque
from pynput import keyboard as kb

try:
    import websockets
except ImportError:
    print("[ERROR] websockets not installed. Run: pip install websockets")
    input("Press Enter to exit...")
    sys.exit(1)

# ── Locate config next to the .exe or script ─────────────
def base_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE        = base_dir()
CONFIG_PATH = os.path.join(BASE, 'config.ini')

# ── Default config ────────────────────────────────────────
DEFAULT_CONFIG = """\
[server]
port = 24051
tosu_host = localhost:24050

[keys]
# mode = mania | o2jam | custom
# For mania: key count switches automatically based on beatmap CS from tosu
# For o2jam or custom: uses the 'default' row always (no auto-switch)
mode = mania

# mania key layouts (auto-switched by CS value from tosu)
4k = q, w, p, [
7k = q, w, e, space, p, [, ]

# o2jam layout (7 keys: s d f space j k l)
o2jam = s, d, f, space, j, k, l

# custom: set mode=custom and put your keys here
default = q, w, p, [

[timing]
window_ms = 1000
broadcast_ms = 40
only_in_play = false

[opacity]
min_opacity = 0.08
max_opacity = 1.0
"""

cfg = configparser.ConfigParser()
if not os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, 'w') as f:
        f.write(DEFAULT_CONFIG)
    print(f"[INFO] Created config.ini at {CONFIG_PATH}")

cfg.read_dict({
    'server':  {'port': '24051', 'tosu_host': 'localhost:24050'},
    'keys':    {'mode': 'mania', '4k': 'q,w,p,[', '7k': 'q,w,e,space,p,[,]',
                'o2jam': 's,d,f,space,j,k,l', 'default': 'q,w,p,['},
    'timing':  {'window_ms': '1000', 'broadcast_ms': '40', 'only_in_play': 'false'},
    'opacity': {'min_opacity': '0.08', 'max_opacity': '1.0'},
})
cfg.read(CONFIG_PATH)

PORT         = int(cfg['server']['port'])
TOSU_HOST    = cfg['server']['tosu_host']
WINDOW_MS    = int(cfg['timing']['window_ms'])
BROADCAST_MS = int(cfg['timing']['broadcast_ms'])
ONLY_IN_PLAY = cfg['timing']['only_in_play'].strip().lower() == 'true'
MIN_OPACITY  = float(cfg['opacity']['min_opacity'])
MAX_OPACITY  = float(cfg['opacity']['max_opacity'])
KEY_MODE     = cfg['keys']['mode'].strip().lower()   # 'mania' | 'o2jam' | 'custom'

def parse_keys(s):
    return [k.strip().lower() for k in s.split(',') if k.strip()]

# Build mania key map (4k, 7k, etc.)
MANIA_KEYS = {}
for _k, _v in cfg['keys'].items():
    if _k.endswith('k') and _k[:-1].isdigit():
        MANIA_KEYS[int(_k[:-1])] = parse_keys(_v)

# Fixed key layouts for non-mania modes
O2JAM_KEYS  = parse_keys(cfg['keys']['o2jam'])
DEFAULT_KEYS = parse_keys(cfg['keys']['default'])

print(f"[CONFIG] mode={KEY_MODE}")
if KEY_MODE == 'mania':
    for kc, keys in sorted(MANIA_KEYS.items()):
        print(f"[CONFIG]   {kc}K = {keys}")
elif KEY_MODE == 'o2jam':
    print(f"[CONFIG]   o2jam = {O2JAM_KEYS}")
else:
    print(f"[CONFIG]   default = {DEFAULT_KEYS}")

# ── Shared game state ─────────────────────────────────────
state = {
    'game_state': 'menu',
    'in_play':    False,
    'mode':       'Mania',
    'key_count':  4,
    'beatmap':    '',
    'bpm':        0.0,
}
state_lock = threading.Lock()

# ── Active keys (what we listen for) ─────────────────────
if KEY_MODE == 'o2jam':
    _start_keys = O2JAM_KEYS
elif KEY_MODE == 'mania':
    _start_keys = MANIA_KEYS.get(4, DEFAULT_KEYS)
else:
    _start_keys = DEFAULT_KEYS

active_keys     = list(_start_keys)
active_keys_set = set(_start_keys)
keys_lock       = threading.Lock()

def set_active_keys(keys):
    global active_keys, active_keys_set
    with keys_lock:
        active_keys     = list(keys)
        active_keys_set = set(keys)

def update_active_keys_for_cs(cs_value):
    """Only used in mania mode — pick closest key count to cs_value."""
    if KEY_MODE != 'mania':
        return
    cs = round(float(cs_value))
    available = list(MANIA_KEYS.keys())
    if not available:
        return
    key_count = min(available, key=lambda k: abs(k - cs))
    with state_lock:
        old = state['key_count']
    if key_count != old:
        with state_lock:
            state['key_count'] = key_count
        keys = MANIA_KEYS[key_count]
        set_active_keys(keys)
        print(f"[KEYS] Switched to {key_count}K -> {keys}")

# ── pynput key → string id ────────────────────────────────
SPECIAL_MAP = {
    kb.Key.space:     'space',
    kb.Key.shift:     'shift',   kb.Key.shift_r:   'shift',
    kb.Key.ctrl_l:    'ctrl',    kb.Key.ctrl_r:    'ctrl',
    kb.Key.alt_l:     'alt',     kb.Key.alt_r:     'alt',
    kb.Key.enter:     'enter',
    kb.Key.backspace: 'bksp',
    kb.Key.tab:       'tab',
    kb.Key.up:        'up',      kb.Key.down:      'down',
    kb.Key.left:      'left',    kb.Key.right:     'right',
}
CHAR_MAP = {
    ';': ';', "'": "'", ',': ',', '.': '.', '/': '/',
    '[': '[', ']': ']', '`': '`', '-': '-', '=': '=',
}

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

listener = kb.Listener(on_press=on_press, on_release=on_release)
listener.daemon = True
listener.start()
print("[PYNPUT] Keyboard listener started")

# ── tosu client (optional — works without it) ─────────────
_last_tosu_sig = None

def _parse_tosu(data):
    global _last_tosu_sig, active_keys, active_keys_set
    with state_lock:
        raw_state = data.get('state', {}).get('name', 'menu')
        state['game_state'] = raw_state
        state['in_play']    = raw_state.lower() == 'play'

        mode_raw = (
            data.get('play',     {}).get('mode', {}).get('name') or
            data.get('beatmap',  {}).get('mode', {}).get('name') or
            data.get('settings', {}).get('mode', {}).get('name') or
            'Osu'
        )
        mode_name = mode_raw.strip().capitalize()
        state['mode'] = mode_name

        beatmap = data.get('beatmap', {})
        cs_raw  = (
            beatmap.get('stats', {}).get('cs', {}).get('original') or
            beatmap.get('stats', {}).get('cs', {}).get('converted') or
            4
        )

        bpm = (
            beatmap.get('stats', {}).get('bpm', {}).get('common') or
            beatmap.get('stats', {}).get('bpm', {}).get('realtime') or
            0
        )
        state['bpm'] = round(float(bpm), 1)

        artist = beatmap.get('artist') or beatmap.get('metadata', {}).get('artist', '')
        title  = beatmap.get('title')  or beatmap.get('metadata', {}).get('title', '')
        state['beatmap'] = f"{artist} - {title}".strip(' -')

    # Key switching (only in mania mode)
    update_active_keys_for_cs(cs_raw)

    # Only log on meaningful changes
    with state_lock:
        kc = state['key_count']
    sig = (raw_state, mode_name, kc)
    if sig != _last_tosu_sig:
        _last_tosu_sig = sig
        print(f"[TOSU] state={raw_state}  mode={mode_name}  {kc}K")

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
            await asyncio.sleep(2)

# ── KPS + payload ─────────────────────────────────────────
def calc_kps():
    now = time.time()
    with track_lock:
        # Remove truly ghost keys (no release event for 10s) from held_since only
        # pressed_now is only cleared by on_release to avoid the hold-cancel bug
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

    # In o2jam/custom mode, report key_count from active keys length
    kc = len(keys_list) if KEY_MODE != 'mania' else s['key_count']
    mode_label = 'O2Jam' if KEY_MODE == 'o2jam' else s['mode']

    key_data = []
    for i, kid in enumerate(keys_list):
        lbl = kid.upper() if len(kid) == 1 else kid[:3].upper()
        key_data.append({
            'id':        kid,
            'label':     lbl,
            'col':       i + 1,
            'isPressed': kid in pressing,
            'count':     counts.get(kid, 0),
        })

    return {
        'kps':       kps,
        'opacity':   round(get_opacity(kps), 3),
        'inPlay':    s['in_play'],
        'gameState': s['game_state'],
        'mode':      mode_label,
        'keyCount':  kc,
        'beatmap':   s['beatmap'],
        'bpm':       s['bpm'],
        'keys':      key_data,
    }

# ── WebSocket server ──────────────────────────────────────
clients      = set()
clients_lock = asyncio.Lock()

async def handler(websocket):
    async with clients_lock:
        clients.add(websocket)
    print(f"[SERVER] HTML client connected")
    try:
        await websocket.wait_closed()
    finally:
        async with clients_lock:
            clients.discard(websocket)
        print(f"[SERVER] HTML client disconnected")

async def broadcaster():
    global clients
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
            clients -= dead

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
        print(f"[SERVER] Could not free port {port}: {e}")
        return False

# ── Main ─────────────────────────────────────────────────
async def main():
    print(f"[SERVER] ws://127.0.0.1:{PORT}  |  overlay: http://localhost:24050/kps-overlay/")
    print(f"[SERVER] Press Ctrl+C to stop.")

    try:
        server = await websockets.serve(handler, '127.0.0.1', PORT)
    except OSError as e:
        if e.errno == 10048 or '10048' in str(e):
            print(f"[SERVER] Port {PORT} busy — freeing...")
            free_port(PORT)
            await asyncio.sleep(0.5)
            try:
                server = await websockets.serve(handler, '127.0.0.1', PORT)
            except OSError:
                print(f"[ERROR] Port {PORT} still busy. Close old process and retry.")
                input("Press Enter to exit...")
                return
        else:
            raise

    tosu_task = asyncio.create_task(tosu_client())
    bcast     = asyncio.create_task(broadcaster())
    try:
        await asyncio.gather(server.serve_forever(), tosu_task, bcast)
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        server.close()
        tosu_task.cancel()
        bcast.cancel()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
