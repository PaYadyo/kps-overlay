"""
KPS Server — pynput + tosu → HTML overlay
Tracks keys with pynput, reads game state from tosu,
broadcasts everything via WebSocket to the HTML overlay.
"""
import asyncio
import json
import os
import sys
import time
import threading
import configparser
from collections import deque
from pynput import keyboard as kb

try:
    import websockets
except ImportError:
    print("[ERROR] websockets not installed. Run: pip install websockets")
    input("Press Enter to exit...")
    sys.exit(1)

# ── Locate files next to the .exe or script ──────────────
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

[mania_keys]
4k = d, f, j, k
5k = d, f, space, j, k
6k = s, d, f, j, k, l
7k = s, d, f, space, j, k, l
8k = a, s, d, f, j, k, l, ;
9k = a, s, d, f, space, j, k, l, ;

[timing]
window_ms = 1000
broadcast_ms = 40
only_in_play = true

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
    'server':     {'port': '24051', 'tosu_host': 'localhost:24050'},
    'mania_keys': {'4k':'d,f,j,k','5k':'d,f,space,j,k','6k':'s,d,f,j,k,l',
                   '7k':'s,d,f,space,j,k,l','8k':'a,s,d,f,j,k,l,;',
                   '9k':'a,s,d,f,space,j,k,l,;'},
    'timing':     {'window_ms':'1000','broadcast_ms':'40','only_in_play':'true'},
    'opacity':    {'min_opacity':'0.08','max_opacity':'1.0'},
})
cfg.read(CONFIG_PATH)

PORT         = int(cfg['server']['port'])
TOSU_HOST    = cfg['server']['tosu_host']
WINDOW_MS    = int(cfg['timing']['window_ms'])
BROADCAST_MS = int(cfg['timing']['broadcast_ms'])
ONLY_IN_PLAY = cfg['timing']['only_in_play'].strip().lower() == 'true'
MIN_OPACITY  = float(cfg['opacity']['min_opacity'])
MAX_OPACITY  = float(cfg['opacity']['max_opacity'])

def parse_keys(s):
    return [k.strip().lower() for k in s.split(',') if k.strip()]

MANIA_KEYS = {}
for k, v in cfg['mania_keys'].items():
    try:
        count = int(k.replace('k', ''))
        MANIA_KEYS[count] = parse_keys(v)
    except Exception:
        pass

# ── Shared game state ─────────────────────────────────────
state = {
    'game_state': 'Menu',
    'in_play':    False,
    'mode':       'Mania',
    'key_count':  4,
    'beatmap':    '',
    'bpm':        0.0,
}
state_lock = threading.Lock()

# ── Active key config ─────────────────────────────────────
active_keys     = parse_keys(cfg['mania_keys'].get('4k', 'd,f,j,k'))
active_keys_set = set(active_keys)
keys_lock       = threading.Lock()

def update_active_keys(key_count):
    global active_keys, active_keys_set
    keys = MANIA_KEYS.get(key_count) or MANIA_KEYS.get(4, ['d','f','j','k'])
    with keys_lock:
        active_keys     = keys
        active_keys_set = set(keys)
    print(f"[KEYS] {key_count}K -> {keys}")

# ── pynput key → string id ────────────────────────────────
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

# ── Key tracking state ────────────────────────────────────
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
print("[PYNPUT] Keyboard listener started")

# ── tosu WebSocket client ─────────────────────────────────
async def tosu_client():
    uri = f"ws://{TOSU_HOST}/websocket/v2"
    while True:
        try:
            async with websockets.connect(uri, ping_interval=None) as ws:
                print(f"[TOSU] Connected to {uri}")
                async for msg in ws:
                    try:
                        _parse_tosu(json.loads(msg))
                    except Exception:
                        pass
        except Exception as e:
            print(f"[TOSU] Disconnected ({e}), retrying in 2s...")
            await asyncio.sleep(2)

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
        stale = [k for k, t in held_since.items() if now - t > 2.0]
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

    return {
        'kps':       kps,
        'opacity':   round(get_opacity(kps), 3),
        'inPlay':    s['in_play'],
        'gameState': s['game_state'],
        'mode':      s['mode'],
        'keyCount':  s['key_count'],
        'beatmap':   s['beatmap'],
        'bpm':       s['bpm'],
        'keys':      key_data,
    }

# ── WebSocket server → HTML clients ──────────────────────
clients      = set()
clients_lock = asyncio.Lock()

async def handler(websocket):
    async with clients_lock:
        clients.add(websocket)
    print(f"[SERVER] Client connected: {websocket.remote_address}")
    try:
        await websocket.wait_closed()
    finally:
        async with clients_lock:
            clients.discard(websocket)
        print(f"[SERVER] Client disconnected")

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
            clients -= dead

# ── Main ──────────────────────────────────────────────────
async def main():
    print(f"[SERVER] KPS server starting on ws://localhost:{PORT}")
    print(f"[SERVER] Overlay URL: http://localhost:24050/kps-overlay/")
    print(f"[SERVER] Press Ctrl+C to stop.")

    server    = await websockets.serve(handler, 'localhost', PORT)
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
