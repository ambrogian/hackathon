#!/usr/bin/env python3
"""Inspection mode: compare the camera frame to a good reference. GOOD / BAD / UNSURE + bbox. stdlib only.
  python3 inspect.py ref good|bad [--image f]    save reference
  python3 inspect.py check [--loop] [--image f] [--no-speak]"""
import argparse, base64, datetime, json, os, re, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:18080'
FFMPEG = os.path.expanduser('~/ondev/tools/ffmpeg')
if not os.path.exists(FFMPEG):
    FFMPEG = '/home/ubuntu/ondev/tools/ffmpeg'
IXH = Path(os.path.expanduser('~/ixh'))
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
LIVE = ROOT / 'live/latest.jpg'
GOOD_T, BAD_T = 0.8, 0.2
Q_SAME = 'Is the second picture the same correct state as the first picture, with nothing missing, covered, moved or damaged?'
Q_OK = 'Is everything in this picture correct, complete and undamaged?'


def grab(args, dest):
    src = args.image or str(LIVE)
    if not os.path.exists(src):
        sys.exit('no image source: ' + src)
    shutil.copyfile(src, dest)


def cmd_ref(args):
    (ROOT / 'refs').mkdir(exist_ok=True)
    dest = ROOT / 'refs' / (args.which + '.jpg')
    if args.image and not args.image.lower().endswith(('.jpg', '.jpeg')):
        subprocess.run([FFMPEG, '-nostdin', '-loglevel', 'error', '-y', '-i', args.image, '-frames:v', '1', '-q:v', '2', str(dest)], check=True)
    else:
        grab(args, dest)
    print('saved', dest)
    if not (ROOT / 'refs/notes.txt').exists():
        (ROOT / 'refs/notes.txt').write_text('')  # optional: describe what "good" means


def png512(src, dest):
    subprocess.run([FFMPEG, '-nostdin', '-loglevel', 'error', '-y', '-i', str(src), '-vf',
        'scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2,format=rgb24',
        '-frames:v', '1', str(dest)], check=True)


def data_url(path, mime):
    return 'data:%s;base64,%s' % (mime, base64.b64encode(Path(path).read_bytes()).decode())


class D1:
    def __init__(self):
        env = {**os.environ, 'HOME': str(IXH), 'XDG_CACHE_HOME': str(IXH / '.cache'), 'TMPDIR': str(IXH / 'tmp'), 'PYTHONDONTWRITEBYTECODE': '1'}
        self.p = subprocess.Popen([str(IXH / 'ixian-hexagon-0.2.2-linux-arm64-qcom-iq9/bin/zetic_d1_cli'), 'serve', '--model',
            str(IXH / 'models/d1-2b'), '--target', 'v73'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1, cwd=IXH, env=env)
        r = json.loads(self.p.stdout.readline())
        if r.get('event') != 'ready':
            raise RuntimeError('d1 not ready: %r' % r)

    def ask(self, images, state, questions):
        req = {'id': str(time.time()), 'state': state, 'images': images,
               'questions': {k: {'type': 'noul', 'instructions': v} for k, v in questions.items()}}
        self.p.stdin.write(json.dumps(req) + '\n'); self.p.stdin.flush()
        rep = json.loads(self.p.stdout.readline())
        if 'answers' not in rep:
            raise RuntimeError('d1 error: %r' % rep)
        return {k: round(v['noul'], 4) for k, v in rep['answers'].items()}


def omni(text, images, max_tokens=200):
    parts = [{'type': 'image_url', 'image_url': {'url': u}} for u in images] + [{'type': 'text', 'text': text}]
    body = {'messages': [{'role': 'user', 'content': parts}], 'max_tokens': max_tokens, 'temperature': 0,
            'chat_template_kwargs': {'enable_thinking': False}}
    req = urllib.request.Request(BASE + '/v1/chat/completions', data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
    with OPENER.open(req, timeout=120) as r:
        return json.loads(r.read())['choices'][0]['message']['content'].strip()


def explain(refs, cur, notes):
    prompt = ('Image 1 is the GOOD reference' + (' and image 2 is a known BAD example' if len(refs) > 1 else '') +
              '. The last image is the current frame to inspect. ' + (('Good means: ' + notes + ' ') if notes else '') +
              'Reply with ONLY JSON: {"difference":"one short sentence on what is wrong or different in the current frame",'
              '"bbox_2d":[xmin,ymin,xmax,ymax],"label":"..."} where bbox_2d is a box around the problem in the CURRENT frame, '
              'normalized 0-1000.')
    raw = omni(prompt, refs + [cur])
    sent, box = raw, None
    m = re.search(r'\{.*\}', raw, re.S)
    if m:
        try:
            j = json.loads(m.group(0))
            sent = str(j.get('difference') or j.get('label') or '').strip()
            b = j.get('bbox_2d') or (j.get('bbox') if isinstance(j.get('bbox'), list) else None)
            if b and len(b) == 4:
                box = [max(0, min(1000, float(v))) for v in b]
        except ValueError:
            pass
    if box is None:
        mm = re.findall(r'\d+', (re.search(r'bbox_2d"?\s*:\s*\[([^\]]*)\]', raw) or [None, ''])[1] if re.search(r'bbox_2d', raw) else '')
        if len(mm) == 4:
            box = [float(v) for v in mm]
    if box is None and sent:
        try:
            r2 = omni('Image 1 is the good reference, image 2 is the current frame (same viewpoint). Problem: ' + sent +
                      ' Output only the bounding box of the problem region as [{"bbox_2d":[xmin,ymin,xmax,ymax],"label":"..."}], normalized 0-1000, in image 2.', refs[:1] + [cur], 80)
            raw += ' || ' + r2
            n = re.findall(r'-?\d+(?:\.\d+)?', (re.search(r'bbox_2d"?\s*:\s*\[([^\]]*)\]', r2) or [None, ''])[1])
            if len(n) == 4:
                box = [max(0, min(1000, float(v))) for v in n]
        except Exception:
            pass
    if box and (box[2] <= box[0] or box[3] <= box[1]):
        box = None
    return sent[:240], box, raw


def draw(frame, box, out):
    probe = subprocess.run([FFMPEG, '-nostdin', '-i', str(frame)], capture_output=True, text=True).stderr
    m = re.search(r'Video:.*?(\d{2,5})x(\d{2,5})', probe)
    W, H = (int(m.group(1)), int(m.group(2))) if m else (1280, 720)
    x0, y0, x1, y1 = box[0] * W / 1000, box[1] * H / 1000, box[2] * W / 1000, box[3] * H / 1000
    vf = 'drawbox=x=%d:y=%d:w=%d:h=%d:color=red:t=6' % (x0, y0, max(4, x1 - x0), max(4, y1 - y0))
    subprocess.run([FFMPEG, '-nostdin', '-loglevel', 'error', '-y', '-i', str(frame), '-vf', vf, '-frames:v', '1', '-q:v', '3', str(out)], check=True)


def speak(text):
    try:
        req = urllib.request.Request(BASE + '/v1/audio/speech', data=json.dumps({'model': 'tts', 'input': text, 'stream_format': 'audio', 'response_format': 'wav'}).encode(), headers={'Content-Type': 'application/json'})
        wav = ROOT / 'runs/_speech.wav'
        with OPENER.open(req, timeout=150) as r:
            wav.write_bytes(r.read())
        subprocess.run(['pw-play', '--target', '55', str(wav)], timeout=45)
    except Exception as e:
        print('speak failed:', e)


_d1 = None


def check_once(args, ref_png_cache={}):
    global _d1
    t0 = time.monotonic(); T = {}
    rid = datetime.datetime.now().strftime('insp-%Y%m%d-%H%M%S')
    run = ROOT / 'runs' / rid; run.mkdir(parents=True, exist_ok=True)
    good = ROOT / 'refs/good.jpg'
    if not good.exists():
        sys.exit('no reference: run  inspect.py ref good  first')
    bad = ROOT / 'refs/bad.jpg'
    notes = ''
    if (ROOT / 'refs/notes.txt').exists():
        notes = (ROOT / 'refs/notes.txt').read_text().strip()
    frame = run / 'frame.jpg'
    grab(args, frame)
    T['capture_s'] = round(time.monotonic() - t0, 3); t = time.monotonic()
    if _d1 is None:
        _d1 = D1(); T['d1_load_s'] = round(time.monotonic() - t, 3); t = time.monotonic()
    key = str(good.stat().st_mtime)
    if ref_png_cache.get('k') != key:
        png512(good, run / 'ref.png'); ref_png_cache.update(k=key, p=(run / 'ref.png').read_bytes())
    (run / 'ref.png').write_bytes(ref_png_cache['p'])
    png512(frame, run / 'cur.png')
    T['prep_s'] = round(time.monotonic() - t, 3); t = time.monotonic()
    imgs = [data_url(run / 'ref.png', 'image/png'), data_url(run / 'cur.png', 'image/png')]
    st = ('The correct state: ' + notes) if notes else None
    probs = _d1.ask(imgs, st, {'same_as_ref': Q_SAME})
    T['d1_s'] = round(time.monotonic() - t, 3)
    score = probs['same_as_ref']
    verdict = 'GOOD' if score > GOOD_T else 'BAD' if score < BAD_T else 'UNSURE'
    sent, box, raw, shown = '', None, '', frame
    if verdict != 'GOOD':
        t = time.monotonic()
        refs = [data_url(good, 'image/jpeg')] + ([data_url(bad, 'image/jpeg')] if bad.exists() else [])
        try:
            sent, box, raw = explain(refs, data_url(frame, 'image/jpeg'), notes)
        except Exception as e:
            sent, raw = 'explanation failed: %s' % e, ''
        T['omni_s'] = round(time.monotonic() - t, 3); t = time.monotonic()
        if box:
            shown = run / 'annotated.jpg'
            try:
                draw(frame, box, shown)
            except Exception as e:
                print('drawbox failed', e); shown = frame
            T['draw_s'] = round(time.monotonic() - t, 3)
    if not (run / 'annotated.jpg').exists():
        shutil.copyfile(frame, run / 'annotated.jpg')
    shown = run / 'annotated.jpg'
    step = verdict + (': ' + sent if sent else ': matches the reference')
    spoken = step
    if not args.no_speak:
        t = time.monotonic(); speak(spoken); T['speak_s'] = round(time.monotonic() - t, 3)
    T['total_s'] = round(time.monotonic() - t0, 3)
    rec = {'time': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'transcript': '[inspection check]',
           'step': step, 'seen': (sent + ' (box approximate)') if box else sent, 'card': None, 'timings': T, 'model': 'd1-2b + LFM3-Omni-2B',
           'npu': True, 'gate': {'result': verdict.lower(), **probs, 'good_t': GOOD_T, 'bad_t': BAD_T},
           'frame': str(shown), 'run': str(run), 'input_mode': 'inspection', 'verdict': verdict, 'bbox': box, 'omni_raw': raw[:400]}
    with (ROOT / 'logs').joinpath('field-manual.jsonl').open('a') as f:
        f.write(json.dumps(rec) + '\n')
    print('VERDICT', verdict, json.dumps(probs), 'box(0-1000, approx)=', box)
    print('Sentence:', sent); print('Annotated:', shown); print('Timings:', json.dumps(T), flush=True)
    return verdict


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest='c', required=True)
    r = sub.add_parser('ref'); r.add_argument('which', choices=['good', 'bad']); r.add_argument('--image')
    c = sub.add_parser('check'); c.add_argument('--loop', action='store_true'); c.add_argument('--image'); c.add_argument('--no-speak', action='store_true')
    a = ap.parse_args()
    (ROOT / 'logs').mkdir(exist_ok=True); (ROOT / 'runs').mkdir(exist_ok=True)
    if a.c == 'ref':
        return cmd_ref(a)
    try:
        while True:
            check_once(a)
            if not a.loop:
                break
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        if _d1:
            _d1.p.stdin.close()


main()
