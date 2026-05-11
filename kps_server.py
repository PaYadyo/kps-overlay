"""
KPS Server — pynput + optional tosu sync → HTML overlay
- Built-in HTTP server serves the overlay page (no tosu needed for o2jam/custom)
- WebSocket broadcasts KPS data to the overlay
- Works standalone (no osu/tosu) just fine
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
from http.server import BaseHTTPRequestHandler, HTTPServer
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

DEFAULT_CONFIG = """\
[server]
# WebSocket port (overlay connects here for live data)
port = 24051
# HTTP port (open this in OBS Browser Source)
http_port = 24052
# Tosu address (optional - only needed for osu!mania auto key-switch)
tosu_host = localhost:24050

[keys]
# mode = mania | o2jam | custom
# mania: auto-switches key layout based on beatmap CS from tosu
# o2jam: always uses the o2jam row below (no tosu needed)
# custom: always uses the default row below (no tosu needed)
mode = mania

# mania key layouts (auto-switched by CS)
4k = q, w, p, [
7k = q, w, e, space, p, [, ]

# o2jam 7-key layout
o2jam = s, d, f, space, j, k, l

# custom layout (used when mode=custom)
default = q, w, p, [

[timing]
window_ms = 1000
broadcast_ms = 40
# only_in_play: set true to only count KPS while in osu gameplay
# for o2jam/custom set false so it always counts
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
    'server':  {'port': '24051', 'http_port': '24052', 'tosu_host': 'localhost:24050'},
    'keys':    {'mode': 'mania', '4k': 'q,w,p,[', '7k': 'q,w,e,space,p,[,]',
                'o2jam': 's,d,f,space,j,k,l', 'default': 'q,w,p,['},
    'timing':  {'window_ms': '1000', 'broadcast_ms': '40', 'only_in_play': 'false'},
    'opacity': {'min_opacity': '0.08', 'max_opacity': '1.0'},
})
cfg.read(CONFIG_PATH)

PORT         = int(cfg['server']['port'])
HTTP_PORT    = int(cfg['server']['http_port'])
TOSU_HOST    = cfg['server']['tosu_host']
WINDOW_MS    = int(cfg['timing']['window_ms'])
BROADCAST_MS = int(cfg['timing']['broadcast_ms'])
ONLY_IN_PLAY = cfg['timing']['only_in_play'].strip().lower() == 'true'
MIN_OPACITY  = float(cfg['opacity']['min_opacity'])
MAX_OPACITY  = float(cfg['opacity']['max_opacity'])
KEY_MODE     = cfg['keys']['mode'].strip().lower()

def parse_keys(s):
    return [k.strip().lower() for k in s.split(',') if k.strip()]

MANIA_KEYS = {}
for _k, _v in cfg['keys'].items():
    if _k.endswith('k') and _k[:-1].isdigit():
        MANIA_KEYS[int(_k[:-1])] = parse_keys(_v)

O2JAM_KEYS   = parse_keys(cfg['keys']['o2jam'])
DEFAULT_KEYS = parse_keys(cfg['keys']['default'])

print(f"[CONFIG] mode={KEY_MODE}  ws=:{PORT}  http=:{HTTP_PORT}")
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

# ── Active keys ───────────────────────────────────────────
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
    if KEY_MODE != 'mania':
        return
    cs        = round(float(cs_value))
    available = list(MANIA_KEYS.keys())
    if not available:
        return
    key_count = min(available, key=lambda k: abs(k - cs))
    with state_lock:
        old = state['key_count']
    if key_count != old:
        with state_lock:
            state['key_count'] = key_count
        set_active_keys(MANIA_KEYS[key_count])
        print(f"[KEYS] Switched to {key_count}K -> {MANIA_KEYS[key_count]}")

# ── pynput ────────────────────────────────────────────────
SPECIAL_MAP = {
    kb.Key.space:     'space',
    kb.Key.shift:     'shift',   kb.Key.shift_r: 'shift',
    kb.Key.ctrl_l:    'ctrl',    kb.Key.ctrl_r:  'ctrl',
    kb.Key.alt_l:     'alt',     kb.Key.alt_r:   'alt',
    kb.Key.enter:     'enter',
    kb.Key.backspace: 'bksp',
    kb.Key.tab:       'tab',
    kb.Key.up:        'up',      kb.Key.down:    'down',
    kb.Key.left:      'left',    kb.Key.right:   'right',
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

# ── tosu client (optional) ────────────────────────────────
_last_tosu_sig = None

def _parse_tosu(data):
    global _last_tosu_sig
    with state_lock:
        raw_state           = data.get('state', {}).get('name', 'menu')
        state['game_state'] = raw_state
        state['in_play']    = raw_state.lower() == 'play'
        mode_raw = (
            data.get('play',     {}).get('mode', {}).get('name') or
            data.get('beatmap',  {}).get('mode', {}).get('name') or
            data.get('settings', {}).get('mode', {}).get('name') or 'Osu'
        )
        mode_name    = mode_raw.strip().capitalize()
        state['mode']= mode_name
        beatmap      = data.get('beatmap', {})
        cs_raw       = (beatmap.get('stats', {}).get('cs', {}).get('original') or
                        beatmap.get('stats', {}).get('cs', {}).get('converted') or 4)
        bpm          = (beatmap.get('stats', {}).get('bpm', {}).get('common') or
                        beatmap.get('stats', {}).get('bpm', {}).get('realtime') or 0)
        state['bpm'] = round(float(bpm), 1)
        artist       = beatmap.get('artist') or ''
        title        = beatmap.get('title')  or ''
        state['beatmap'] = f"{artist} - {title}".strip(' -')

    update_active_keys_for_cs(cs_raw)

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
                print("[TOSU] Disconnected — standalone mode, retrying quietly...")
            was_connected = False
            await asyncio.sleep(2)

# ── KPS + payload ─────────────────────────────────────────
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

    kc         = len(keys_list) if KEY_MODE != 'mania' else s['key_count']
    mode_label = 'O2Jam' if KEY_MODE == 'o2jam' else ('Custom' if KEY_MODE == 'custom' else s['mode'])

    key_data = []
    for i, kid in enumerate(keys_list):
        lbl = kid.upper() if len(kid) == 1 else kid[:3].upper()
        key_data.append({
            'id': kid, 'label': lbl, 'col': i + 1,
            'isPressed': kid in pressing, 'count': counts.get(kid, 0),
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

# ── Embedded HTML overlay ─────────────────────────────────
HTML = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>KPS Overlay</title>
  <link href="https://fonts.googleapis.com/css2?family=Rajdhani:wght@700&family=Inter:wght@400;500&display=swap" rel="stylesheet">
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    html, body {{
      background: transparent;
      width: 160px; min-height: 200px;
      overflow: hidden;
      display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      gap: 8px;
    }}
    .badge {{
      font-family: 'Inter', sans-serif;
      font-size: 9px; font-weight: 500;
      letter-spacing: 2px;
      color: rgba(255,255,255,0.25);
      text-transform: uppercase;
      white-space: nowrap;
      transition: color 0.3s;
      height: 12px;
    }}
    .circle {{ position: relative; width: 120px; height: 120px; flex-shrink: 0; }}
    .c-bg   {{ position:absolute; inset:0; border-radius:50%; background:rgba(10,10,10,0.4); transition:background 0.3s; }}
    .c-ring {{ position:absolute; inset:-5px; border-radius:50%; border:1.5px solid rgba(255,255,255,0.07); transition:border-color 0.3s, box-shadow 0.3s; }}
    .c-inner {{ position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; }}
    #kpsNum {{ font-family:'Rajdhani',sans-serif; font-size:50px; font-weight:700; line-height:1; color:#fff; transition:color 0.2s; }}
    #kpsLbl {{ font-family:'Inter',sans-serif; font-size:10px; letter-spacing:3px; color:rgba(255,255,255,0.35); margin-top:1px; transition:color 0.2s; }}
    #colsRow {{ display:flex; gap:4px; align-items:center; }}
    .col {{
      height:24px; border-radius:5px;
      border:1.5px solid rgba(255,255,255,0.14);
      background:rgba(255,255,255,0.04);
      display:flex; align-items:center; justify-content:center;
      font-family:'Inter',sans-serif; font-size:9px; font-weight:500;
      color:rgba(255,255,255,0.28);
      transition:background .07s, border-color .07s, color .07s, transform .07s;
    }}
    .col.pressed {{ transform:scale(0.87); }}
    #status {{
      position:fixed; bottom:5px; right:6px;
      width:6px; height:6px; border-radius:50%;
      background:#ff4040; transition:background 0.4s;
    }}
    #status.on {{ background:#40ff90; }}
  </style>
</head>
<body>
  <div class="badge" id="badge">— loading —</div>
  <div class="circle">
    <div class="c-bg"   id="cBg"></div>
    <div class="c-ring" id="cRing"></div>
    <div class="c-inner">
      <div id="kpsNum">0</div>
      <div id="kpsLbl">KPS</div>
    </div>
  </div>
  <div id="colsRow"></div>
  <div id="status"></div>
<script>
  const WS_PORT = {PORT};
  function lerp(a,b,t){{return a+(b-a)*t;}}
  function getColor(k){{
    if(k<=0)  return [160,160,255];
    if(k<=8)  {{const t=k/8;     return [~~lerp(160,80,t), ~~lerp(160,200,t),255];}}
    if(k<=16) {{const t=(k-8)/8; return [~~lerp(80,0,t),   ~~lerp(200,255,t),255];}}
    if(k<=24) {{const t=(k-16)/8;return [~~lerp(0,80,t),   255, ~~lerp(255,60,t)];}}
    if(k<=32) {{const t=(k-24)/8;return [~~lerp(80,255,t), 255, ~~lerp(60,0,t)];}}
    if(k<=40) {{const t=(k-32)/8;return [255, ~~lerp(255,40,t), 0];}}
    if(k<=48) {{const t=(k-40)/8;return [~~lerp(255,160,t),~~lerp(40,0,t),~~lerp(0,230,t)];}}
    if(k<=56) {{const t=(k-48)/8;return [~~lerp(160,50,t), 0, ~~lerp(230,120,t)];}}
    return [20,0,50];
  }}
  function rgb(r,g,b){{return `rgb(${{r}},${{g}},${{b}})`;}}
  function hexx(r,g,b){{return '#'+[r,g,b].map(v=>v.toString(16).padStart(2,'0')).join('');}}
  function dim(r,g,b,f){{return [~~(r*f),~~(g*f),~~(b*f)];}}

  const cBg=document.getElementById('cBg'), cRing=document.getElementById('cRing');
  const kpsNum=document.getElementById('kpsNum'), kpsLbl=document.getElementById('kpsLbl');
  const badge=document.getElementById('badge'), colsRow=document.getElementById('colsRow');
  const status=document.getElementById('status');

  let colEls={{}}, lastKeySig='';

  function buildCols(keys){{
    const sig=keys.map(k=>k.id).join(',');
    if(sig===lastKeySig) return;
    lastKeySig=sig; colsRow.innerHTML=''; colEls={{}};
    const w=Math.max(18, Math.floor(140/keys.length)-4);
    keys.forEach(k=>{{
      const el=document.createElement('div');
      el.className='col'; el.style.width=w+'px'; el.textContent=k.col;
      colsRow.appendChild(el); colEls[k.id]=el;
    }});
  }}

  function render(d){{
    const kps=d.kps||0, opacity=d.opacity??0.08;
    const [r,g,b]=getColor(kps);
    document.body.style.opacity=opacity;
    cBg.style.background    = kps>5 ? hexx(...dim(r,g,b,0.12)) : '#111';
    cRing.style.borderColor = kps>5 ? `rgba(${{r}},${{g}},${{b}},0.5)` : 'rgba(255,255,255,0.07)';
    cRing.style.boxShadow   = kps>5 ? `0 0 ${{Math.min(kps*.7,28)}}px rgba(${{r}},${{g}},${{b}},0.45)` : 'none';
    kpsNum.style.color=rgb(r,g,b); kpsNum.textContent=kps;
    kpsLbl.style.color=`rgba(${{r}},${{g}},${{b}},0.6)`;
    badge.textContent=`— ${{d.keyCount||'?'}}K ${{(d.mode||'').toLowerCase()}} —`;
    badge.style.color=kps>3 ? `rgba(${{r}},${{g}},${{b}},0.5)` : 'rgba(255,255,255,0.2)';
    const keys=d.keys||[];
    buildCols(keys);
    keys.forEach(k=>{{
      const el=colEls[k.id]; if(!el) return;
      if(k.isPressed){{
        el.classList.add('pressed');
        el.style.background=`rgba(${{r}},${{g}},${{b}},0.28)`;
        el.style.borderColor=rgb(r,g,b); el.style.color=rgb(r,g,b);
      }} else {{
        el.classList.remove('pressed');
        el.style.background='rgba(255,255,255,0.04)';
        el.style.borderColor='rgba(255,255,255,0.14)';
        el.style.color='rgba(255,255,255,0.28)';
      }}
    }});
  }}

  function connect(){{
    const ws=new WebSocket(`ws://localhost:${{WS_PORT}}`);
    ws.onopen    = ()=> status.classList.add('on');
    ws.onclose   = ()=>{{ status.classList.remove('on'); setTimeout(connect,1500); }};
    ws.onerror   = ()=> ws.close();
    ws.onmessage = e=>{{ try{{render(JSON.parse(e.data));}}catch(err){{console.error(err);}} }};
  }}
  connect();
</script>
</body>
</html>"""

# ── HTTP server (serves embedded HTML) ───────────────────
class OverlayHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = HTML.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type',   'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control',  'no-cache')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass   # silence HTTP access log

def start_http_server():
    srv = HTTPServer(('127.0.0.1', HTTP_PORT), OverlayHTTPHandler)
    print(f"[HTTP] Overlay serving at http://localhost:{HTTP_PORT}/")
    srv.serve_forever()

# ── WebSocket server ──────────────────────────────────────
clients      = set()
clients_lock = asyncio.Lock()

async def handler(websocket):
    async with clients_lock:
        clients.add(websocket)
    print("[SERVER] HTML client connected")
    try:
        await websocket.wait_closed()
    finally:
        async with clients_lock:
            clients.discard(websocket)
        print("[SERVER] HTML client disconnected")

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
            shell=True, stderr=subprocess.DEVNULL, text=True)
        pids = set(re.findall(r'(\d+)\s*$', out, re.MULTILINE))
        pids.discard('0')
        for pid in pids:
            subprocess.call(f'taskkill /F /PID {pid}', shell=True,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"[SERVER] Freed port {port} (killed PID {pid})")
    except Exception as e:
        print(f"[SERVER] Could not free port {port}: {e}")

# ── Main ─────────────────────────────────────────────────
async def main():
    print(f"[SERVER] WebSocket  -> ws://localhost:{PORT}")
    print(f"[SERVER] OBS Source -> http://localhost:{HTTP_PORT}/  (160x200px)")
    print(f"[SERVER] Ctrl+C to stop.")

    # Start HTTP server in background thread
    t = threading.Thread(target=start_http_server, daemon=True)
    t.start()

    # Start WebSocket server
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
