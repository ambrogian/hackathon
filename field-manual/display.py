#!/usr/bin/env python3
"""Judge-facing display for the Dead-Zone Field Manual. Standard library only, fully offline."""
import argparse, json, mimetypes, os, signal, subprocess, sys, threading, time, datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = Path.home() / 'ondev/field-manual'


def load_manuals():
    out = {}
    for name in ('manual.json', 'manual-setup.json'):
        for base in (ROOT, HERE):
            p = base / name
            if p.is_file():
                try:
                    out[name] = {c['id']: c for c in json.loads(p.read_text())}
                except (ValueError, KeyError, TypeError, OSError):
                    out[name] = {}
                break
    return out


def card_info(rec, manuals):
    cid = rec.get('card')
    if cid is None:
        return None
    want = str(rec.get('manual') or '')
    order = [n for n in manuals if want and want in n] + [n for n in manuals if not (want and want in n)]
    for n in order:  # prefer the manual whose source matches the logged source
        c = manuals[n].get(cid)
        if c and (not rec.get('source') or c.get('source') == rec['source']):
            return {'id': cid, 'title': c.get('title', ''), 'manual': n}
    for n in order:
        c = manuals[n].get(cid)
        if c:
            return {'id': cid, 'title': c.get('title', ''), 'manual': n}
    return {'id': cid, 'title': '', 'manual': ''}


def media_name(path):
    """Map a logged path to a name relative to runs/, or None."""
    if not path:
        return None
    parts = Path(str(path)).parts
    if 'runs' in parts:
        i = len(parts) - 1 - parts[::-1].index('runs')
        return '/'.join(parts[i + 1:]) or None
    return '/'.join(parts[-2:])


def read_turns(n=10):
    log = ROOT / 'logs/field-manual.jsonl'
    try:
        lines = log.read_text(errors='replace').splitlines()
    except OSError:
        return []
    turns = []
    for line in lines[-60:]:
        try:
            r = json.loads(line)
            if isinstance(r, dict):
                turns.append(r)
        except ValueError:
            continue  # partially written or corrupt line
    return turns[-n:]


def shape(rec, manuals):
    g = rec.get('gate')
    t = rec.get('timings') if isinstance(rec.get('timings'), dict) else {}
    return {'time': rec.get('time'), 'transcript': rec.get('transcript') or '',
            'step': rec.get('step') or '', 'seen': rec.get('seen') or '',
            'card': card_info(rec, manuals), 'timings': t,
            'gate': (g.get('result') if isinstance(g, dict) else g) or '',
            'npu': bool(rec.get('npu')), 'model': rec.get('model') or '',
            'error': rec.get('error') or '', 'frame': media_name(rec.get('frame')),
            'input_mode': rec.get('input_mode') or ''}


def latest():
    manuals = load_manuals()
    turns = [shape(r, manuals) for r in read_turns()]
    return {'latest': turns[-1] if turns else None, 'recent': turns[::-1], 'count': len(turns)}


def safe_frame(name):
    runs = (ROOT / 'runs').resolve()
    try:
        p = (runs / name).resolve()
        p.relative_to(runs)
    except (ValueError, OSError):
        return None
    return p if p.is_file() else None


PROCS = {}
LOCK = threading.Lock()
ORIGINS = ('http://localhost:8765', 'http://127.0.0.1:8765')


def running():
    return [k for k, p in PROCS.items() if p.poll() is None]


def spawn(name, argv):
    PROCS[name] = subprocess.Popen(argv, cwd=ROOT, start_new_session=True, stdin=subprocess.DEVNULL,
                                   stdout=open(ROOT / 'live' / ('field-manual-%s.log' % name), 'w'), stderr=subprocess.STDOUT)


def write_stage(d):
    d['time'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    d.setdefault('timings', {})
    (ROOT / 'live').mkdir(exist_ok=True)
    tmp = ROOT / 'live/.stage.json.tmp'
    tmp.write_text(json.dumps(d))
    os.replace(tmp, ROOT / 'live/stage.json')


def stop_all():
    subprocess.run(['bash', str(ROOT / 'mock_feed.sh'), 'stop'], cwd=ROOT, timeout=10)
    for k, p in list(PROCS.items()):
        if p.poll() is None:
            try:
                os.killpg(p.pid, signal.SIGTERM)  # only groups this server started
            except OSError:
                pass


def demo_images():
    base = (ROOT / 'demo-images').resolve()
    return sorted(str(q.relative_to(base)) for q in base.rglob('*') if q.is_file() and q.suffix.lower() in ('.jpg', '.jpeg', '.png') and not q.name.startswith('_'))

def demo_image(name):
    base = (ROOT / 'demo-images').resolve()
    try:
        q = (base / name).resolve(); q.relative_to(base)
    except (ValueError, OSError, TypeError):
        return None
    return q if q.is_file() and q.suffix.lower() in ('.jpg', '.jpeg', '.png') else None

def control(path, body):
    with LOCK:
        if path == '/api/monitor':
            act = body.get('action')
            if act == 'stop':
                stop_all()
                return 200, {'ok': True, 'running': []}
            if act != 'start':
                return 400, {'error': 'action must be start or stop'}
            if running():
                return 409, {'error': 'already running', 'running': running()}
            subprocess.run(['bash', str(ROOT / 'camd.sh'), 'stop'], cwd=ROOT, timeout=10)
            try:
                os.remove(ROOT / 'live/stage.json')
            except OSError:
                pass
            spawn('feed', ['bash', str(ROOT / 'mock_feed.sh'), '12'])
            time.sleep(1.5)  # let the first frame land
            spawn('loop', [sys.executable, str(ROOT / 'inspect_mode.py'), 'check', '--loop', '--no-speak'])
            return 200, {'ok': True, 'running': running()}
        if path == '/api/analyze':
            if running():
                return 409, {'error': 'already running', 'running': running()}
            img = demo_image(body.get('image')) if body.get('image') else None
            if body.get('image') and not img:
                return 400, {'error': 'unknown image'}
            if img is None:
                img = ROOT / 'runs/_monitor/input.jpg'
            if not img.is_file():
                img = ROOT / 'live/latest.jpg'
            if not img.is_file():
                return 400, {'error': 'no input image'}
            try:
                os.remove(ROOT / 'live/stage.json')
            except OSError:
                pass
            spawn('analyze', [sys.executable, str(ROOT / 'inspect_mode.py'), 'check', '--no-speak', '--image', str(img)])
            return 200, {'ok': True, 'running': running()}
        if path == '/api/reset':
            if running():
                return 409, {'error': 'stop first', 'running': running()}
            fr = 'runs/_monitor/input.jpg' if (ROOT / 'runs/_monitor/input.jpg').is_file() else None
            write_stage({'stage': 'input', 'verdict': None, 'p': None, 'frame': fr, 'run': None})
            return 200, {'ok': True}
    return 404, {'error': 'not found'}


def stage_api():
    try:
        d = json.loads((ROOT / 'live/stage.json').read_text())
    except (OSError, ValueError):
        d = {'stage': 'input', 'frame': None}
    for k in ('frame', 'annotated', 'audio'):
        if d.get(k):
            d[k] = media_name(d[k])
    d['running'] = running()
    return d


class Handler(BaseHTTPRequestHandler):
    def host_ok(self):
        host = (self.headers.get('Host') or '').rsplit(':', 1)[0]
        return host in ('127.0.0.1', 'localhost')

    def do_POST(self):
        if not self.host_ok():
            return self.send_error(421)
        origin = self.headers.get('Origin')
        if origin is not None and origin not in ORIGINS:
            return self.send(403, b'{"error":"bad origin"}', 'application/json')
        path = unquote(urlsplit(self.path).path)
        try:
            n = min(int(self.headers.get('Content-Length') or 0), 4096)
            body = json.loads(self.rfile.read(n) or b'{}')
            if not isinstance(body, dict):
                body = {}
        except ValueError:
            body = {}
        code, out = control(path, body)
        self.send(code, json.dumps(out).encode(), 'application/json')

    def send(self, code, body, ctype, extra=()):
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        # Refuse other Host names (DNS rebinding): only the loopback names this server is reached by.
        host = (self.headers.get('Host') or '').rsplit(':', 1)[0]
        if host not in ('127.0.0.1', 'localhost'):
            self.send_error(421)
            return
        path = unquote(urlsplit(self.path).path)
        if path in ('/', '/index.html'):
            self.send(200, PAGE.encode(), 'text/html; charset=utf-8')
        elif path == '/monitor':
            self.send(200, MONITOR.encode(), 'text/html; charset=utf-8')
        elif path == '/api/stage':
            self.send(200, json.dumps(stage_api()).encode(), 'application/json')
        elif path == '/architecture':
            svg = (ROOT / 'architecture.svg')
            body = svg.read_text() if svg.is_file() else '<p>architecture.svg missing</p>'
            page = ('<!doctype html><meta charset="utf-8"><title>Architecture</title>'
                    '<body style="margin:0;background:#0d1117;color:#e6edf3;font-family:system-ui,sans-serif">'
                    '<header style="display:flex;gap:24px;align-items:center;padding:14px 22px;background:#161b22">'
                    '<h1 style="margin:0;font-size:26px">Field Manual &middot; Architecture</h1>' + '<nav style="display:flex;gap:14px;font-size:20px"><a href="/monitor" style="color:#9cf">Monitor</a><a href="/architecture" style="color:#9cf">Architecture</a></nav>' + '</header>'
                    '<main style="padding:18px;background:#fff;margin:18px;border-radius:10px">' + body + '</main></body>')
            self.send(200, page.encode(), 'text/html; charset=utf-8')
        elif path == '/api/images':
            self.send(200, json.dumps(demo_images()).encode(), 'application/json')
        elif path.startswith('/demo/'):
            q = demo_image(path[6:])
            if not q:
                return self.send(404, b'not found', 'text/plain')
            self.send(200, q.read_bytes(), mimetypes.guess_type(q.name)[0])
        elif path.startswith('/ref/'):
            refs = (ROOT / 'refs').resolve()
            try:
                p = (refs / path[5:]).resolve(); p.relative_to(refs)
            except (ValueError, OSError):
                p = None
            if not p or not p.is_file() or p.suffix.lower() not in ('.jpg', '.jpeg', '.png'):
                return self.send(404, b'not found', 'text/plain')
            self.send(200, p.read_bytes(), mimetypes.guess_type(p.name)[0])
        elif path.startswith('/audio/'):
            p = safe_frame(path[7:])
            if not p or p.suffix.lower() != '.wav':
                return self.send(404, b'not found', 'text/plain')
            self.send(200, p.read_bytes(), 'audio/wav')
        elif path == '/api/latest':
            self.send(200, json.dumps(latest()).encode(), 'application/json')
        elif path.startswith('/frame/'):
            p = safe_frame(path[7:])
            ctype = mimetypes.guess_type(p.name)[0] if p else None
            if not p or not ctype or not ctype.startswith('image/'):
                return self.send(404, b'not found', 'text/plain')
            self.send(200, p.read_bytes(), ctype)
        else:
            self.send(404, b'not found', 'text/plain')

    def log_message(self, *a):
        pass


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Dead-Zone Field Manual</title><style>
*{box-sizing:border-box}body{margin:0;background:#0b0f14;color:#eef3f8;font:20px/1.35 system-ui,sans-serif}
header{display:flex;flex-wrap:wrap;gap:14px;align-items:center;padding:12px 22px;background:#121a24;border-bottom:2px solid #223}
h1{font-size:28px;margin:0;flex:1}
.badge{background:#0a7d3c;color:#fff;font-weight:700;padding:8px 16px;border-radius:30px;font-size:24px}
.badge.off{background:#7a2a2a}
#clock{font-size:32px;font-variant-numeric:tabular-nums;font-weight:700}
button{font:inherit;padding:6px 14px;border-radius:8px;border:1px solid #567;background:#1d2b3a;color:#eef;cursor:pointer}
main{display:grid;grid-template-columns:minmax(300px,2fr) 3fr;gap:20px;padding:20px 22px}
@media(max-width:900px){main{grid-template-columns:1fr}}
#frame{width:100%;border-radius:10px;background:#000;min-height:160px;object-fit:contain;max-height:60vh}
.lbl{color:#8fa3b8;font-size:16px;text-transform:uppercase;letter-spacing:.08em;margin-top:14px}
#step{font-size:46px;line-height:1.2;font-weight:700;color:#fff}
#transcript{font-size:30px;font-style:italic}#seen{font-size:24px}
#card{font-size:28px;color:#7cc4ff;font-weight:600}
.pill{display:inline-block;margin:4px 8px 0 0;padding:5px 12px;background:#1a2634;border-radius:8px;font-size:22px;font-variant-numeric:tabular-nums}
.gate{display:inline-block;padding:4px 14px;border-radius:8px;font-weight:700;background:#33414f}
.gate.rejected{background:#8a2b2b}.gate.accepted,.gate.passed,.gate.ok{background:#1c6b3a}
#err{color:#ff8a80}
ol{list-style:none;margin:6px 0 0;padding:0}
li{padding:8px 12px;border-bottom:1px solid #223;font-size:20px;display:grid;grid-template-columns:90px 1fr 2fr;gap:12px}
li:first-child{background:#162130}.t{color:#8fa3b8}
footer{padding:0 22px 22px}.sec{max-height:300px;overflow:auto}
</style></head><body>
<header><h1>Dead-Zone Field Manual</h1><nav style="display:flex;gap:14px;font-size:20px"><a href="/monitor" style="color:#9cf">Monitor</a><a href="/architecture" style="color:#9cf">Architecture</a></nav><span class="badge" id="npu">on-device &middot; NPU</span>
<span>Wi-Fi off since: <b id="wifi">not set</b></span>
<button id="wbtn">Wi-Fi is off now</button><button id="wedit">edit</button><span id="clock"></span></header>
<main><section><img id="frame" alt="latest captured frame" hidden><div id="noframe" class="lbl">Waiting for first turn&hellip; press Enter on the board.</div>
<div class="lbl">Gate</div><span class="gate" id="gate">&ndash;</span> <span id="when" class="t"></span>
<div class="lbl">Timings</div><div id="timings"></div></section>
<section><div class="lbl">Question</div><div id="transcript">&ndash;</div>
<div class="lbl">Manual step</div><div id="step">&ndash;</div>
<div class="lbl">Manual card</div><div id="card">&ndash;</div>
<div class="lbl">Model saw</div><div id="seen">&ndash;</div><div id="err"></div></section></main>
<footer><div class="lbl">Last 10 turns</div><div class="sec"><ol id="list"></ol></div></footer>
<script>
const $=id=>document.getElementById(id);
function tick(){$('clock').textContent=new Date().toLocaleTimeString([], {hour12:false})}
setInterval(tick,500);tick();
function setWifi(v){$('wifi').textContent=v}
$('wbtn').onclick=()=>setWifi(new Date().toLocaleTimeString([], {hour12:false}));
$('wedit').onclick=()=>{const v=prompt('Wi-Fi off since:',$('wifi').textContent);if(v!==null)setWifi(v)};
const LAB=[['capture_s','capture'],['record_s','record'],['gate_s','gate'],['asr_s','ASR'],['first_token_s','answer 1st token'],['omni_s','answer total'],['answer_s','answer total'],['tts_s','speech synth'],['playback_s','playback'],['total_s','total']];
const f=v=>(typeof v==='number')?v.toFixed(2)+' s':'n/a';
function clock(t){const d=new Date(t);return isNaN(d)?'':d.toLocaleTimeString([], {hour12:false})}
let lastFrame=null;
function render(d){
 const t=d.latest;
 if(!t){$('transcript').textContent='No turns logged yet';return}
 $('npu').textContent=t.npu?'on-device · NPU':'NPU not confirmed';$('npu').className='badge'+(t.npu?'':' off');
 $('transcript').textContent=t.transcript?'“'+t.transcript+'”':'(no speech)';
 $('step').textContent=t.step||'–';
 $('card').textContent=t.card?('Card '+t.card.id+(t.card.title?' — '+t.card.title:'')):'No matching card';
 $('seen').textContent=t.seen||'(not established)';
 $('err').textContent=t.error?'Error: '+t.error:'';
 $('gate').textContent=t.gate||'n/a';$('gate').className='gate '+(t.gate||'');
 $('when').textContent=clock(t.time);
 const tm=$('timings');tm.textContent='';
 for(const [k,n] of LAB){if(typeof t.timings[k]==='number'){const s=document.createElement('span');s.className='pill';s.textContent=n+' '+f(t.timings[k]);tm.appendChild(s)}}
 const key=t.frame+'|'+t.time;
 if(t.frame&&key!==lastFrame){lastFrame=key;$('frame').src='/frame/'+t.frame.split('/').map(encodeURIComponent).join('/')+'?'+encodeURIComponent(t.time||'');$('frame').hidden=false;$('noframe').hidden=true}
 const ol=$('list');ol.textContent='';
 for(const r of d.recent){const li=document.createElement('li');
  for(const x of [clock(r.time),r.card?('Card '+r.card.id):'no card',(r.transcript||'(no speech)')+' → '+r.step]){const s=document.createElement('span');s.textContent=x;li.appendChild(s)}
  li.firstChild.className='t';ol.appendChild(li)}
}
async function poll(){try{const r=await fetch('/api/latest',{cache:'no-store'});render(await r.json())}catch(e){}}
poll();setInterval(poll,1000);
</script></body></html>"""


MONITOR = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Monitor</title><style>
*{box-sizing:border-box}body{margin:0;background:#0b0f14;color:#eef3f8;font:24px/1.3 system-ui,sans-serif}
header{display:flex;gap:14px;align-items:center;padding:12px 22px;background:#121a24}
h1{font-size:30px;margin:0;flex:1}.badge{background:#0a7d3c;padding:8px 18px;border-radius:30px;font-weight:700}
button{font:inherit;font-weight:700;padding:14px 30px;border-radius:12px;border:0;color:#fff;cursor:pointer}
#bm{background:#1f6feb}#bm.on{background:#b3342d}#ba{background:#8957e5}#br{background:#33414f;font-size:18px;padding:8px 16px}
button:disabled{opacity:.4}
main{display:grid;grid-template-columns:1fr 1fr;gap:22px;padding:22px}
@media(max-width:900px){main{grid-template-columns:1fr}}
.pair{display:grid;grid-template-columns:1fr 3fr;gap:12px;align-items:start}figure{margin:0}figcaption{font-size:22px;font-weight:700;margin-bottom:6px}
#ref,#img{width:100%;aspect-ratio:4/3;max-height:50vh;object-fit:contain;background:#000;border-radius:12px;border:6px solid #223}
#status{font-size:44px;font-weight:800;line-height:1.15}
.good{color:#3ddc84}.bad{color:#ff5a4f}.warn{color:#ffc247}
#text{font-size:44px;font-weight:700;margin-top:18px;min-height:2.5em}
.pill{display:inline-block;margin:6px 8px 0 0;padding:6px 14px;background:#1a2634;border-radius:8px;font-size:26px}
.box{margin-top:20px;padding:14px;border:2px dashed #456;border-radius:12px;color:#8fa3b8}
#err{color:#ff8a80;font-size:18px}
</style></head><body>
<header><h1>Field Manual &middot; Monitor</h1><nav style="display:flex;gap:14px;font-size:20px"><a href="/monitor" style="color:#9cf">Monitor</a><a href="/architecture" style="color:#9cf">Architecture</a></nav><button id="bm">Monitor</button><select id="pick" style="font-size:18px;max-width:340px;margin-left:8px"><option value="">live input</option></select><button id="ba">Analyze</button><button id="br">Reset</button></header>
<main><section><div class="pair"><figure><figcaption class="good">Control: GOOD reference</figcaption><img id="ref" src="/ref/good.jpg" alt="control"></figure>
<figure><figcaption id="cap">Live input</figcaption><img id="img" alt="input" hidden></figure></div><div id="err"></div></section>
<section><div id="status">Waiting&hellip;</div><div id="text"></div><div id="tm"></div>
<div class="badge" style="display:inline-block;margin-top:18px">on-device &middot; NPU &middot; Wi-Fi independent</div>
<div class="box">Audio &nbsp;<button id="play" disabled style="padding:6px 18px">&#9654; play</button> <span id="anote">(coming later)</span></div></section></main>
<script>
const $=id=>document.getElementById(id);let S={},shown='',typed=0,tkey='',au=null;
async function post(p,b){try{const r=await fetch(p,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b||{})});const j=await r.json();$('err').textContent=r.ok?'':(j.error||r.status);poll()}catch(e){$('err').textContent=String(e)}}
$('bm').onclick=()=>post('/api/monitor',{action:(S.running||[]).length?'stop':'start'});
fetch('/api/images').then(r=>r.json()).then(l=>{for(const n of l){const o=document.createElement('option');o.value=n;o.textContent=n;$('pick').appendChild(o)}});
$('pick').onchange=()=>{const v=$('pick').value;picked=!!v;if(v){$('img').src='/demo/'+v.split('/').map(encodeURIComponent).join('/');$('img').hidden=false;$('cap').textContent='Selected: '+v}};
$('ba').onclick=()=>post('/api/analyze',{image:$('pick').value||null});$('br').onclick=()=>post('/api/reset');
$('play').onclick=()=>{if(S.audio){new Audio('/audio/'+S.audio.split('/').map(encodeURIComponent).join('/')).play()}};
const url=n=>'/frame/'+n.split('/').map(encodeURIComponent).join('/')+'?'+encodeURIComponent(S.time||'');
function render(){
 const st=S.stage,run=(S.running||[]).length>0,p=typeof S.p==='number'?S.p.toFixed(2):'';
 $('bm').textContent=run?'Stop':'Monitor';$('bm').className=run?'on':'';$('bm').disabled=false;$('ba').disabled=run;$('br').disabled=run;
 const T=S.timings||{};let h='',c='';
 if(st==='input'){h='Input image';c=''}
 else if(st==='monitoring'){h='Monitoring line… GOOD '+p+' (d1, NPU'+(T.d1_s?', '+T.d1_s.toFixed(2)+' s':'')+')';c='good'}
 else if(st==='inference'){h='Anomaly: running inference…  '+(S.verdict||'')+' '+p;c='warn'}
 else if(st==='error'){h='Error: '+(S.error||'');c='bad'}
 else{h=(S.verdict||'')+' '+p;c=S.verdict==='GOOD'?'good':'bad'}
 $('status').textContent=h;$('status').className=c;
 if(st!=='input')picked=false;
 if(picked&&st==='input'){$('status').textContent=run?'Analyzing… (d1 loading on the NPU)':'Selected image: press Analyze';$('status').className='';return}
 const isbad=(st==='inference'||st==='box'||st==='text'||st==='done')&&S.verdict&&S.verdict!=='GOOD';
 $('cap').textContent=isbad?((st!=='inference'&&S.annotated?'Anomaly (box): ':'Live input: ')+S.verdict):(S.verdict==='GOOD'?'Live input: GOOD (d1 '+(S.p!=null?Number(S.p).toFixed(2):'')+')':'Input: not analyzed yet');
 $('cap').className=isbad?'bad':(S.verdict==='GOOD'?'good':'');
 if(st==='error'){$('cap').textContent='Error: '+(S.error||'');$('cap').className='bad'}
 const f=(st==='box'||st==='text'||st==='done')&&S.annotated?S.annotated:S.frame;
 if(f){const u=url(f);if(u!==shown){shown=u;$('img').src=u}$('img').hidden=false}
 const txt=(st==='text'||st==='done')?(S.text||''):'';
 if(txt){const k=S.run+txt;if(k!==tkey){tkey=k;typed=0}}else{tkey='';typed=0}
 $('text').textContent=txt.slice(0,typed);
 const tm=$('tm');tm.textContent='';
 if(st==='done'||st==='text'){for(const [k,n,u] of [['d1_s','d1',1000],['omni_s','Omni',1],['draw_s','draw',1000]]){if(typeof T[k]==='number'){const s=document.createElement('span');s.className='pill';s.textContent=n+' '+(u===1000?Math.round(T[k]*1000)+' ms':T[k].toFixed(1)+' s');tm.appendChild(s)}}}
 $('play').disabled=!S.audio;$('anote').textContent=S.audio?'':'(coming later)';
}
setInterval(()=>{const t=(S.stage==='text'||S.stage==='done')?(S.text||''):'';if(typed<t.length){typed+=2;$('text').textContent=t.slice(0,typed)}},40);
let picked=false;
async function poll(){try{S=await (await fetch('/api/stage',{cache:'no-store'})).json();render()}catch(e){}}
poll();setInterval(poll,500);
</script></body></html>"""


def main():
    global ROOT
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', default=str(ROOT))
    ap.add_argument('--port', type=int, default=8765)
    a = ap.parse_args()
    ROOT = Path(a.root).expanduser().resolve()
    srv = ThreadingHTTPServer(('127.0.0.1', a.port), Handler)
    print(f'Field Manual display: http://127.0.0.1:{a.port}  (root {ROOT})', flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
