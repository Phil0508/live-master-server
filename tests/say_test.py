# -*- coding: utf-8 -*-
"""💬 화면에 한마디 (2026-10-07).

 ① 로그인해야만 띄운다 — 주소만 아는 사람이 방송에 아무 글이나 띄우면 안 된다
 ② 쓴 글이 방송판(로그인 없는 쪽)에 'say' 신호로 그대로 간다 — 줄바꿈 · 겹친 띄어쓰기는 한 칸, 60자까지
 ③ 빈 글은 거절
 ④ 화면 파일 — 방송판은 궁서 · 흰 글씨 · 검은 테두리(글자 뒤) · 배경 없음, 조종실은 한글 조합 중 Enter 를 건너뛴다
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
ROOT = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:110]) if detail else ''))


def post(path, obj=None, authed=True):
    hdr = H if authed else {'Content-Type': 'application/json'}
    req = urllib.request.Request(B + path, json.dumps(obj or {}).encode(), hdr)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def listen(got, ready, stop):
    """방송판처럼(로그인 없이) 실시간 연결을 열고 'say' 신호만 모은다."""
    try:
        r = urllib.request.urlopen(B + '/api/stream?kind=overlay', timeout=15)
    except Exception as e:
        got.append({'error': str(e)})
        ready.set()
        return
    ready.set()
    ev = None
    try:
        while not stop.is_set():
            line = r.readline().decode('utf-8', 'replace').rstrip('\n')
            if line.startswith('event:'):
                ev = line.split(':', 1)[1].strip()
            elif line.startswith('data:') and ev == 'say':
                got.append(json.loads(line.split(':', 1)[1]))
            elif not line:
                ev = None
    except Exception:
        pass
    finally:
        try:
            r.close()
        except Exception:
            pass


print('=' * 74)
print('① 로그인해야만 띄운다')
print('=' * 74)
c, _ = post('/api/say', {'text': '몰래'}, authed=False)
chk('로그인 없이 보내면 막힌다', c in (401, 403, 302), c)

print('=' * 74)
print('② 방송판에 그대로 간다')
print('=' * 74)
got, ready, stop = [], threading.Event(), threading.Event()
t = threading.Thread(target=listen, args=(got, ready, stop), daemon=True)
t.start()
ready.wait(10)
time.sleep(1.0)                      # 첫 상태(init)가 먼저 지나가게
c, j = post('/api/say', {'text': '  오늘도\n와줘서   고마워요  '})
chk('보내기 200', c == 200, (c, j))
chk('줄바꿈 · 겹친 띄어쓰기는 한 칸', j.get('text') == '오늘도 와줘서 고마워요', j)
c2, j2 = post('/api/say', {'text': '가' * 80})
chk('60자까지 자른다', c2 == 200 and len(j2.get('text') or '') == 60, len(j2.get('text') or ''))
deadline = time.time() + 10
while time.time() < deadline and len(got) < 2:
    time.sleep(0.1)
stop.set()
texts = [g.get('text') for g in got]
chk('방송판(로그인 없음)이 say 신호를 받는다', '오늘도 와줘서 고마워요' in texts, got[:2])
chk('긴 글도 잘린 채로 간다', ('가' * 60) in texts, [len(x or '') for x in texts])

print('=' * 74)
print('③ 빈 글은 거절')
print('=' * 74)
c, j = post('/api/say', {'text': '   \n  '})
chk('빈 글 400', c == 400, (c, j))

print('=' * 74)
print('④ 화면 파일')
print('=' * 74)
ov = open(os.path.join(ROOT, 'overlay.html'), encoding='utf-8').read()
ct = open(os.path.join(ROOT, 'controller.html'), encoding='utf-8').read()
chk('방송판: say 신호를 듣는다', "addEventListener('say'" in ov and 'function sayShow' in ov)
chk('방송판: 자리가 있다', 'id="say-layer"' in ov)
chk('방송판: 궁서 · 흰 글씨 · 글자 뒤 검은 테두리', "'Gungsuh', '궁서'" in ov and 'paint-order: stroke fill' in ov
    and '-webkit-text-stroke: 0.14em #000' in ov)
chk('방송판: 1.8초(나타남 0.35 + 1초 + 사라짐 0.45) 뒤 걷는다', 'say-in-out 1.8s' in ov and 'setTimeout(done, 2300)' in ov)
chk('방송판: 글은 글자로만(태그로 안 읽는다)', 'el.textContent = text' in ov)
chk('조종실: 오른쪽 칸 맨 위 입력칸', 'id="rail-say"' in ct and 'id="say-input"' in ct)
chk('조종실: 한글 조합 중 Enter 는 건너뛴다', 'e.isComposing || e.keyCode === 229' in ct)

print('\n' + '=' * 74)
print('결과: 통과 %d · 실패 %d' % (len(OK), len(BAD)))
for b in BAD:
    print('  ✗', b)
sys.exit(1 if BAD else 0)
