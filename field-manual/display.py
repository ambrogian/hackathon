#!/usr/bin/env python3
"""Judge-facing display for the Dead-Zone Field Manual. Standard library only, fully offline."""
import argparse, json, mimetypes
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


class Handler(BaseHTTPRequestHandler):
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
<header><h1>Dead-Zone Field Manual</h1><span class="badge" id="npu">on-device &middot; NPU</span>
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
