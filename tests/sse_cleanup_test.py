# -*- coding: utf-8 -*-
"""🧹 죽은 실시간 연결(SSE)을 서버가 스스로 치우는가.

2026-09-30 방송 중 실제 사고: 조종실이 잠깐 안 되어 새로고침을 연타했더니
끊긴 연결이 161개 쌓이고 실 가닥이 235개가 됐다. 서버가 새 요청을 못 받아
점수가 안 들어갔고, 결국 컴퓨터를 껐다 켜야 했다.

여기서 지키는 것
  ① 살아 있는 화면은 절대 안 끊는다 (이게 제일 중요하다 — 방송 중이니까)
  ② 조용히 사라진 화면(탭 닫기 · 랜선 뽑힘 · 멈춘 OBS)은 스스로 치운다
  ③ 그래도 쌓이면 상한에서 가장 오래된 것부터 내보낸다 — 새 화면이 늘 붙을 수 있게
  ④ 치운 수를 상태 페이지에서 볼 수 있다
"""
import io
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
ROOT = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
PORT = int(os.environ.get('LM_PT_PORT', '5199'))
B = 'http://127.0.0.1:%d' % PORT
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:160]) if detail else ''))


def head(s):
    print()
    print('=' * 74)
    print(s)
    print('=' * 74)


def health():
    with urllib.request.urlopen(urllib.request.Request(B + '/api/health', headers=H), timeout=20) as r:
        return json.loads(r.read().decode())


SV = io.open(os.path.join(ROOT, 'server.py'), encoding='utf-8').read()

head('① 코드에 세 가지 장치가 있다')
chk('청소부가 돈다', "threading.Thread(target=_sse_janitor" in SV and 'def _sse_janitor()' in SV)
chk('죽은 연결을 빼는 곳이 한 군데다', 'def _sse_drop(' in SV and SV.count('_sse_drop(') >= 4)
chk('상한이 있다', 'SSE_MAX_CLIENTS' in SV and 'while len(sse_clients) > SSE_MAX_CLIENTS' in SV)
chk('소켓 시간제한을 건다', 'WSGIRequestHandler.timeout = SSE_SOCKET_TIMEOUT' in SV)
chk("받아 간 때를 적는다(살아 있음의 증거)", SV.count('q._drained = time.time()') == 2
    and "getattr(x, '_drained', now)" in SV)   # 붙을 때 + 받아 갈 때마다, 청소부가 그걸 본다
chk("'이제 그만' 표시를 보면 끝낸다", 'if msg is None or q._evict:' in SV)
chk('치운 수를 상태 페이지에 싣는다', "out['sse_evicted'] = _sse_evicted" in SV)
chk('값은 환경변수로 바꿀 수 있다(방송 중 급할 때)',
    "os.environ.get('SSE_MAX_CLIENTS'" in SV and "os.environ.get('SSE_STALE_SEC'" in SV)


def open_stream(read_first=True):
    """SSE 를 날것 소켓으로 연다. read_first=False 면 '받아 가지 않는' 죽은 화면 흉내."""
    s = socket.create_connection(('127.0.0.1', PORT), timeout=10)
    s.sendall(b'GET /api/stream HTTP/1.1\r\nHost: 127.0.0.1\r\nAccept: text/event-stream\r\n\r\n')
    if read_first:
        s.settimeout(10)
        s.recv(65536)      # 머리글 + 첫 상태
    return s


head('② 살아 있는 화면은 안 끊는다 (제일 중요)')
base = health()['sse_clients']
alive = open_stream()
time.sleep(1.0)
chk('붙으면 숫자가 는다', health()['sse_clients'] == base + 1, (base, health()['sse_clients']))
# 20초 동안 계속 받아 간다(15초 ping 을 한 번 이상 받는다)
got = 0
alive.settimeout(20)
t0 = time.time()
while time.time() - t0 < 20:
    try:
        b = alive.recv(65536)
        if b:
            got += len(b)
    except socket.timeout:
        break
chk('20초 동안 신호를 계속 받는다(연결 유지)', got > 0, '%d bytes' % got)
chk('그동안 안 끊겼다', health()['sse_clients'] == base + 1, health()['sse_clients'])

head('③ 조용히 사라진 화면은 치운다')
n0 = health()
dead = []
for _ in range(3):
    dead.append(open_stream())          # 붙기만 하고
for d in dead:
    d.close()                            # 곧바로 사라진다(탭 닫기)
time.sleep(1)
after_close = health()['sse_clients']
# 다음 broadcast 때 쓰기가 실패하면서 정리되거나, 늦어도 청소부가 치운다.
for _ in range(3):
    urllib.request.urlopen(urllib.request.Request(
        B + '/api/settings/patch', json.dumps({'notice_speed': 130}).encode(), H), timeout=20).read()
    time.sleep(0.5)
time.sleep(2)
now = health()
chk('탭을 닫으면 곧 정리된다', now['sse_clients'] <= base + 1,
    '닫은 직후 %d → 지금 %d (살아 있는 것 %d)' % (after_close, now['sse_clients'], base + 1))

head('④ 오늘 사고 그대로 — 앞단 웹서버가 "반만 끊는" 경우')
# ⚠️ 이게 2026-09-30 방송 중 CLOSE-WAIT 161개가 쌓인 바로 그 상황이다.
#    상대가 보내는 쪽만 끊으면(half-close) 글을 써 넣는 건 계속 성공한다 —
#    그래서 '쓰기가 실패하면 치운다' 만으로는 영영 못 알아챈다. 소켓을 직접 봐야 한다.
half = []
for _ in range(6):
    h = open_stream()
    h.shutdown(socket.SHUT_WR)      # 보내는 쪽만 끊는다(소켓은 살아 있다)
    half.append(h)
time.sleep(1.5)
chk('반만 끊긴 연결이 일단 붙어는 있다', health()['sse_clients'] >= base + 6, health()['sse_clients'])
t0 = time.time()
cleaned = False
while time.time() - t0 < 75:          # 청소부는 30초마다 돈다
    if health()['sse_clients'] <= base + 1:
        cleaned = True
        break
    time.sleep(5)
chk('서버가 스스로 알아채고 치운다(옛 코드는 영영 못 치웠다)', cleaned,
    '%d초 뒤 %d개' % (round(time.time() - t0), health()['sse_clients']))
for h in half:
    try:
        h.close()
    except Exception:
        pass
chk('소켓을 직접 들여다보는 장치가 있다', 'def _peer_gone(' in SV and "socket.MSG_PEEK" in SV and 'select.select' in SV)
chk('치울 때 소켓도 닫는다(CLOSE-WAIT 가 안 남게)', 'sk.shutdown(socket.SHUT_RDWR)' in SV)

head('⑤ 상한을 넘으면 오래된 것부터 (새 화면이 늘 붙게)')
cap = int(os.environ.get('SSE_MAX_CLIENTS', '60'))
chk('상한 기본값이 넉넉하다(방송 화면 · 조종실 · 폰을 다 합쳐도 남는다)', cap >= 30, cap)
chk('상한 처리는 붙는 순간에도 돈다(청소부를 기다리지 않는다)',
    SV.index('while len(sse_clients) > SSE_MAX_CLIENTS') < SV.index('def event_generator'))

alive.close()
# ⚠️ 닫아도 서버는 '다음에 쓸 때' 알아챈다(늦어도 15초 뒤 ping). broadcast 를 한 번 일으켜 앞당긴다.
for _ in range(3):
    urllib.request.urlopen(urllib.request.Request(
        B + '/api/settings/patch', json.dumps({'notice_speed': 130}).encode(), H), timeout=20).read()
    time.sleep(0.6)
time.sleep(2)
head('⑥ 마무리 — 다 정리되어 처음으로 돌아왔다')
fin = health()
chk('붙은 화면 수가 처음으로 돌아온다', fin['sse_clients'] <= base, (base, fin['sse_clients']))
chk('치운 수가 상태 페이지에 보인다', isinstance(fin.get('sse_evicted'), int), fin.get('sse_evicted'))
chk('서버는 여전히 정상', fin.get('status') == 'ok', fin.get('status'))

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
sys.exit(1 if BAD else 0)
