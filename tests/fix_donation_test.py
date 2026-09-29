# -*- coding: utf-8 -*-
"""💰 후원 돈 구멍 고친 것 (2026-09-30) — 감사에서 재현된 네 가지가 다시 안 생기는가.

여기서 지키는 것
  ① 같은 tx_id 가 동시에 여러 번 와도 한 번만 세어진다 (대기함 · 순위 · 시그니처)
     — 예전엔 시그니처 조회가 느리면 리스너가 10초에 포기하고 같은 tx_id 로 다시 보내, 두 번 들어갔다
  ② 장부엔 있는데 대기함엔 없는 후원(장부 적고 상태 저장 전에 서버가 죽음)은 재전송 때 되살린다
     — 장부 줄은 다시 안 적는다. 판단이 애매하면(옛 장부 줄) 평소처럼 중복으로 버린다
  ③ 리스너 — 시간 초과 · 409(처리 중)면 곧바로 다시 안 보내고 대기줄에 넣는다. 기다리는 시간은 30초
  ④ 후원 콘솔 ×N 송출이 도중에 실패하면 몇 건 들어갔는지 알리고, 다시 누르면 같은 번호를 쓴다
  ⑤ 순위에서 뺀 이름은 '한 방 최고' · 전광판 소액 목록에서도 내려간다. 되돌리면 기록도 돌아온다
  ⑥ 제외 명단을 못 읽었을 때 빈 목록을 영원히 기억하지 않는다

⚠️ 연습 서버(기본 5199, LM_PT_PORT 로 바꿈)가 필요하다 — runall 이 띄운다.
⚠️ ② 는 서버 옆 SQLite 장부에 줄을 직접 넣는다(LM_SANDBOX_PT 또는 tests/pausetest). 못 찾으면 건너뛴다.
"""
import http.server
import importlib.util
import io
import json
import os
import socket
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:%s' % os.environ.get('LM_PT_PORT', '5199')
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(HERE, '..')))
OK, BAD = [], []
U = uuid.uuid4().hex[:6]


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:150]) if detail else ''))


def post(path, obj=None, method='POST'):
    req = urllib.request.Request(B + path, json.dumps(obj or {}).encode(), H, method=method)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def get():
    with urllib.request.urlopen(urllib.request.Request(B + '/api/data', headers=H), timeout=25) as r:
        return json.loads(r.read().decode())


def pend_of(d, name):
    return [p for p in (d.get('pending_donations') or []) if p.get('name') == name]


def donate(name, amount, tx=None, msg='돈구멍시험'):
    return post('/api/donation', {'name': name, 'amount': amount, 'message': msg,
                                  'tx_id': tx or ('toon_fx_%s_%s' % (U, uuid.uuid4().hex[:8]))})


def read(p):
    return io.open(os.path.join(PROJ, p), encoding='utf-8', errors='replace').read()


print('=' * 74)
print('① 같은 tx_id 가 동시에 와도 한 번만 세어진다')
print('=' * 74)
c, r = post('/api/server/start_broadcast', {'names': ['가', '나']})
chk('방송 시작이 된다', c == 200, (c, r))
nm1 = '동시%s' % U
tx1 = 'toon_same_%s' % U
q0 = len(get().get('reaction_queue') or [])
res = []


def _fire():
    res.append(donate(nm1, 30000, tx1))


ths = [threading.Thread(target=_fire) for _ in range(6)]
for t in ths:
    t.start()
for t in ths:
    t.join()
time.sleep(0.8)
d = get()
codes = sorted(c for c, _ in res)
chk('여섯 번 보내도 대기함엔 한 건', len(pend_of(d, nm1)) == 1, (len(pend_of(d, nm1)), codes))
row = (d.get('donor_tally') or {}).get(nm1) or {}
chk('후원 순위도 한 번만 (횟수 1 · 3만 원)', row.get('count') == 1 and row.get('total') == 30000, row)
chk('시그니처도 한 번만', len(d.get('reaction_queue') or []) - q0 <= 1,
    len(d.get('reaction_queue') or []) - q0)
chk('응답은 성공(처음 한 건 · 이미 끝남) 아니면 409(처리 중)뿐', all(c in (200, 409) for c in codes), codes)
chk('409 에는 처리 중 표시가 붙는다',
    all(b.get('in_progress') for c, b in res if c == 409), [b for c, b in res if c == 409][:1])
c, b = donate(nm1, 30000, tx1)
chk('끝난 뒤 다시 보내면 200 중복', c == 200 and 'Duplicate' in str(b.get('message')), (c, b))
chk('그래도 한 건', len(pend_of(get(), nm1)) == 1)
nm1b = '진짜두번%s' % U
donate(nm1b, 20000)
donate(nm1b, 20000)
time.sleep(0.5)
chk('tx_id 가 다르면(진짜 두 번 쏜 것) 두 건 다 남는다', len(pend_of(get(), nm1b)) == 2)
don_src = read('features/donation.py')
chk('처리 중 표는 느린 일(시그니처 조회) 전에 찍는다',
    don_src.index('_tx_claim(_t)') < don_src.index('server.supabase_match_signature(amount)'))
chk('실패하면 처리 중을 풀어 재전송이 통한다 (finally)',
    'finally:' in don_src and '_tx_release(_tx, _handled)' in don_src)

print()
print('=' * 74)
print('② 장부에만 있고 대기함엔 없는 후원을 되살린다')
print('=' * 74)
_PT = os.environ.get('LM_SANDBOX_PT') or os.path.join(HERE, 'pausetest')
DB = os.path.join(_PT, 'live_master.db')
if not os.path.exists(DB):
    print('  (장부 파일을 못 찾아 건너뜀: %s)' % DB)
else:
    lg = (get().get('latest_donation') or {}).get('tx_log') or {}
    chk('상태에 "들어간 tx" 목록이 있다', tx1 in [x[0] for x in lg.get('ids') or []], lg)
    time.sleep(1.2)       # 장부 시각은 초 단위 — 목록 시작 시각보다 확실히 뒤로
    nm2, tx2 = '되살림%s' % U, 'toon_lost_%s' % U

    def _ledger_put(name, tx, ts):
        c_ = sqlite3.connect(DB)
        c_.execute("INSERT INTO donation_history (timestamp, name, amount, current_total, message, source, tx_id)"
                   " VALUES (?, ?, ?, ?, ?, ?, ?)", (ts, name, 20000, 20000, '되살림', 'toonation', tx))
        c_.commit()
        c_.close()

    def _ledger_n(tx):
        c_ = sqlite3.connect(DB)
        n_ = c_.execute("SELECT COUNT(*) FROM donation_history WHERE tx_id = ?", (tx,)).fetchone()[0]
        c_.close()
        return n_

    # 서버가 장부 INSERT 까지 하고 상태 저장 전에 죽은 모양을 만든다
    _ledger_put(nm2, tx2, time.strftime('%Y-%m-%d %H:%M:%S'))
    c, b = donate(nm2, 20000, tx2, msg='되살림')
    d = get()
    chk('재전송이 오면 대기함에 들어간다', c == 200 and len(pend_of(d, nm2)) == 1, (c, b, len(pend_of(d, nm2))))
    chk('후원 순위에도 들어간다', ((d.get('donor_tally') or {}).get(nm2) or {}).get('count') == 1)
    chk('장부 줄은 다시 안 적는다 (정산 두 번 방지)', _ledger_n(tx2) == 1, _ledger_n(tx2))
    c, b = donate(nm2, 20000, tx2, msg='되살림')
    chk('한 번 더 와도 이제는 중복', c == 200 and len(pend_of(get(), nm2)) == 1, (c, b))
    # 옛 장부 줄(목록을 적기 전 것) — 들어갔는지 알 길이 없으니 평소처럼 중복으로 버린다
    nm3, tx3 = '옛줄%s' % U, 'toon_old_%s' % U
    _ledger_put(nm3, tx3, '2020-01-01 00:00:00')
    c, b = donate(nm3, 20000, tx3, msg='옛줄')
    chk('애매하면(옛 장부 줄) 되살리지 않는다', c == 200 and not pend_of(get(), nm3), (c, b))

print()
print('=' * 74)
print('③ 리스너 — 느린 서버 · 처리 중(409)이면 바로 다시 안 보낸다')
print('=' * 74)
_spec = importlib.util.spec_from_file_location('tl_fix', os.path.join(PROJ, 'toon_listener.py'))
TL = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(TL)
TL.log = lambda *a: None
chk('기다리는 시간이 30초 (서버 최악보다 길게)', TL.POST_TIMEOUT >= 30, TL.POST_TIMEOUT)
_hits = {'n': 0}


class _H(http.server.BaseHTTPRequestHandler):
    mode = 'ok'

    def do_POST(self):
        _hits['n'] += 1
        self.rfile.read(int(self.headers.get('Content-Length') or 0))
        if self.mode == 'slow':
            time.sleep(1.5)
        code = {'ok': 200, 'slow': 200, 'busy': 409}[self.mode]
        body = b'{"status":"success"}' if code == 200 else b'{"status":"error","in_progress":true}'
        try:
            self.send_response(code)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            pass

    def log_message(self, *a):
        pass


_srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _H)
threading.Thread(target=_srv.serve_forever, daemon=True).start()
TL.DONATION_URL = 'http://127.0.0.1:%d/api/donation' % _srv.server_address[1]
_tmp = tempfile.mkdtemp(prefix='fixdon_')
TL.SPOOL_FILE = os.path.join(_tmp, 'spool.jsonl')


def _spool_n():
    if not os.path.exists(TL.SPOOL_FILE):
        return 0
    return len([ln for ln in open(TL.SPOOL_FILE, encoding='utf-8') if ln.strip()])


for mode, label in (('slow', '느린 서버(시간 초과)'), ('busy', '409 처리 중')):
    _H.mode = mode
    _hits['n'] = 0
    if os.path.exists(TL.SPOOL_FILE):
        os.remove(TL.SPOOL_FILE)
    TL.POST_TIMEOUT = 0.5
    okd = TL.deliver({'name': 'x', 'amount': 10000, 'message': '', 'tx_id': 'toon_' + mode})
    time.sleep(1.6 if mode == 'slow' else 0.1)
    chk('%s — 한 번만 보낸다 (0.6초 뒤 재시도 없음)' % label, _hits['n'] == 1, _hits['n'])
    chk('%s — 대기줄에 넣는다 (나중에 같은 tx_id 로 다시)' % label, not okd and _spool_n() == 1, (okd, _spool_n()))
_H.mode = 'ok'
_hits['n'] = 0
TL.POST_TIMEOUT = 5
TL.spool_drain()
chk('서버가 받아 주면 대기줄이 비워진다', _spool_n() == 0 and _hits['n'] == 1, (_spool_n(), _hits['n']))
# 연결 자체가 안 되면(재시작 중) 예전처럼 한 번 더 본다
_s = socket.socket()
_s.bind(('127.0.0.1', 0))
_dead = _s.getsockname()[1]
_s.close()
TL.DONATION_URL = 'http://127.0.0.1:%d/api/donation' % _dead
_t0 = time.time()
okd = TL.deliver({'name': 'y', 'amount': 10000, 'message': '', 'tx_id': 'toon_dead'})
chk('연결이 안 되면 0.6초 뒤 한 번 더 보고 대기줄에 넣는다',
    not okd and time.time() - _t0 >= 0.6 and _spool_n() == 1, (round(time.time() - _t0, 2), _spool_n()))
_srv.shutdown()

print()
print('=' * 74)
print('④ 후원 콘솔 ×N — 몇 건 들어갔는지 알리고, 다시 누르면 같은 번호')
print('=' * 74)
ms = read('manual_send.html')
_s0 = ms.index('async function send(){')
snd = ms[_s0:ms.index('/* ── 후원 순위 ── */', _s0)]
chk('실패한 묶음의 번호를 기억한다', "_manualRetry={sig, stamp}" in snd and 'let _manualRetry=null;' in snd)
chk('같은 내용이면 그 번호를 다시 쓴다', "const stamp = reuse ? _manualRetry.stamp : Date.now();" in snd)
chk('통신이 끊겨도 몇 건 들어갔는지 알린다 (okN 을 try 밖에)',
    snd.index('let okN=0') < snd.index('try{') and "'건 들어감)'" in snd)
chk('다 들어가면 기억을 지운다', '_manualRetry=null;' in snd.split('if(okN===payloads.length){')[1][:80])
# 서버 쪽: 같은 번호로 다시 보내면 이미 들어간 것은 걸러진다 (manual_ 도 tx_id 중복 검사를 탄다)
nm4 = '콘솔%s' % U
st = 'manual_%s' % int(time.time() * 1000)
for i in (1, 2):
    post('/api/donation', {'name': nm4, 'amount': 10000, 'message': '', 'tx_id': '%s_%d' % (st, i)})
for i in (1, 2, 3):
    post('/api/donation', {'name': nm4, 'amount': 10000, 'message': '', 'tx_id': '%s_%d' % (st, i)})
chk('×3 중 2건 들어간 뒤 같은 번호로 다시 보내면 빠진 1건만 더해진다', len(pend_of(get(), nm4)) == 3,
    len(pend_of(get(), nm4)))

print()
print('=' * 74)
print('⑤ 순위에서 빼면 한 방 최고 · 전광판에서도 내려간다')
print('=' * 74)
post('/api/server/start_broadcast', {'names': ['가', '나']})
X, Y, Z = '뺄사람%s' % U, '진짜%s' % U, '다음%s' % U
donate(X, 90000)
donate(Y, 30000)
donate(X, 500, msg='소액')
d = get()
chk('준비: 뺄 사람이 한 방 최고', (d.get('best_single') or {}).get('name') == X, d.get('best_single'))
chk('준비: 전광판 소액 목록에 있다', any(e.get('name') == X for e in d.get('notice_donors') or []),
    d.get('notice_donors'))
c, _ = post('/api/donors/excluded', {'name': X + '님', 'memo': '돈구멍시험'})   # '님' 붙여도 같은 사람
d = get()
bs = d.get('best_single') or {}
chk('빼기가 된다', c == 200, c)
chk('한 방 최고가 다음 사람으로 내려온다', bs.get('name') == Y and bs.get('amount') == 30000, bs)
chk('내려온 기록은 갱신 연출을 안 한다 (at 0)', bs.get('at') == 0, bs.get('at'))
chk('대기함에 있으면 그 줄 번호를 붙인다 (배정 때 멤버가 붙게)',
    bs.get('id') and bs.get('id') == (pend_of(d, Y) or [{}])[0].get('id'), bs.get('id'))
chk('전광판 소액 목록에서도 빠진다', not any(e.get('name') == X for e in d.get('notice_donors') or []),
    d.get('notice_donors'))
chk('순위판에서도 빠진다 (원래 하던 것)', X not in (d.get('donor_tally') or {}))
donate(Z, 40000)
bs = get().get('best_single') or {}
chk('진짜 후원자의 더 작은 한 방(4만 < 뺀 9만)이 기록을 가져간다', bs.get('name') == Z and bs.get('amount') == 40000, bs)
chk('그건 진짜 갱신이라 at 이 적힌다', int(bs.get('at') or 0) > 0, bs.get('at'))
c, _ = post('/api/donors/excluded?name=' + urllib.parse.quote(X), method='DELETE')
d = get()
bs = d.get('best_single') or {}
chk('되돌리면 더 큰 한 방이 기록을 되찾는다', c == 200 and bs.get('name') == X and bs.get('amount') == 90000, (c, bs))
chk('되돌리면 순위판에도 돌아온다', ((d.get('donor_tally') or {}).get(X) or {}).get('total') == 90500,
    (d.get('donor_tally') or {}).get(X))
ex_src = read('features/excluded.py')
_add = ex_src.split('def api_excluded_add')[1].split('def api_excluded_remove')[0]
chk('빼기 코드는 장부를 직접 안 만진다 (읽기 도우미만 부른다)', 'donation_history' not in _add)

print()
print('=' * 74)
print('⑥ 제외 명단을 못 읽으면 잠깐만 빈 목록')
print('=' * 74)
_en = ex_src.split('def excluded_names():')[1].split('\ndef ')[0]
chk('실패하면 다시 읽을 시각을 적는다', "_excluded_cache['retry_at'] = (time.time() + _EXCLUDED_RETRY_SEC) if failed else 0.0" in _en)
chk('그 시각이 지나면 다시 읽는다', "time.time() < _excluded_cache['retry_at']" in _en)
chk('간격은 몇 초 (후원마다 DB 를 두드리지 않게)', '_EXCLUDED_RETRY_SEC = 5.0' in ex_src)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
sys.exit(1 if BAD else 0)
