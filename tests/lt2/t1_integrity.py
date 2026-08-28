# -*- coding: utf-8 -*-
"""1단계 — 무결성 검증. 인증 구멍 / 정보 유출 / 데이터 손실을 본다."""
import io, json, os, re, sys, threading, time, uuid
import requests
sys.stdout.reconfigure(encoding='utf-8')

BASE = "http://127.0.0.1:5177"
TOK = "lt-sandbox-secret-0123456789"
H = {"Authorization": "Bearer " + TOK, "Content-Type": "application/json"}
SRC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'server.py')
S = requests.Session()
OK, BAD = [], []


def chk(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print(("  [OK] " if cond else "  [!!] ") + name + (("  -- " + str(detail)[:120]) if detail else ""))


def P(p, j=None):
    return S.post(BASE + p, headers=H, json=(j if j is not None else {}), timeout=20)


def G(p):
    return S.get(BASE + p, headers=H, timeout=20)


print("\n" + "=" * 68)
print("(1) 인증 - 상태를 바꾸는 요청이 토큰 없이 통과하는가")
print("=" * 68)

SRC = io.open(SRC_PATH, encoding='utf-8').read()
routes = re.findall(r"@app\.route\('([^']+)'(?:,\s*methods=\[([^\]]+)\])?\)", SRC)
EXEMPT = {'/login', '/logout', '/', '/overlay', '/overlay.html', '/alertbox', '/alertbox.html',
          '/slot', '/slot.html', '/signature-display', '/signature-display.html',
          '/signature_display.html', '/api/stream', '/api/ping', '/health', '/api/health',
          '/api/donation', '/api/roulette/winner', '/api/match/timeup', '/api/signatures',
          '/api/reaction/next', '/toonation_tampermonkey.user.js'}
leaky = []
tested = 0
for u, m in routes:
    if not m or 'POST' not in m or u in EXEMPT or '<' in u:
        continue
    tested += 1
    try:
        r = S.post(BASE + u, json={}, timeout=15, allow_redirects=False)
        if r.status_code not in (401, 403, 302):
            leaky.append((u, r.status_code))
    except Exception as e:
        leaky.append((u, 'ERR ' + str(e)[:40]))
chk("토큰 없는 POST %d개가 모두 막힌다" % tested, not leaky, leaky[:6])

for u in ('/api/pending/remove/zzz', '/api/reaction/queue/remove/zzz',
          '/api/signatures/delete/1', '/api/signatures/update/1'):
    r = S.post(BASE + u, json={}, timeout=15, allow_redirects=False)
    chk("무인증 %s 차단" % u, r.status_code in (401, 403, 302), r.status_code)

print("\n" + "=" * 68)
print("(2) 정보 유출 - 무인증으로 볼 수 있는 것에 민감한 게 섞였는가")
print("=" * 68)
SECRET_PAT = re.compile(r"lt-sandbox-secret|lt-sandbox-pw|session_secret|totp_secret|admin_password", re.I)

r = S.get(BASE + "/api/data", timeout=15)
d = r.json() if r.ok else {}
chk("무인증 /api/data 에 대기 후원이 없다", not d.get('pending_donations'),
    "%d건 노출" % len(d.get('pending_donations') or []))
chk("무인증 /api/data 에 비밀값이 없다", not SECRET_PAT.search(json.dumps(d, ensure_ascii=False)))

for path in ('/api/health', '/health'):
    r = S.get(BASE + path, timeout=15)
    chk("무인증 %s 에 비밀값이 없다" % path, not SECRET_PAT.search(r.text), r.status_code)

sse_lines = []


def _sse(url, out):
    try:
        rr = requests.get(url, stream=True, timeout=(5, 8))
        n = 0
        for ln in rr.iter_lines(decode_unicode=True):
            out.append(ln or '')
            n += 1
            if n > 80:
                break
        rr.close()
    except Exception:
        pass


t = threading.Thread(target=_sse, args=(BASE + "/api/stream", sse_lines))
t.start()
t.join(14)
blob = "\n".join(sse_lines)
has_pend = re.search(r'"pending_donations"\s*:\s*\[\s*\{', blob)
chk("무인증 SSE 에 대기 후원이 없다", not has_pend, "받은 줄 %d" % len(sse_lines))
chk("무인증 SSE 에 비밀값이 없다", not SECRET_PAT.search(blob), "%d바이트" % len(blob))

print("\n" + "=" * 68)
print("(3) 경로 탈출 - 서버 파일을 내주는가")
print("=" * 68)
for probe in ('/videos/../server.py', '/videos/..%2fserver.py', '/videos/....//server.py',
              '/server.py', '/auth_config.json', '/live_master.db',
              '/videos/%2e%2e/%2e%2e/auth_config.json', '/sfx/../server.py'):
    try:
        r = S.get(BASE + probe, timeout=15, allow_redirects=False)
        body = r.content[:600]
        bad = (r.status_code == 200 and (b'Flask' in body or b'session_secret' in body
                                         or b'SQLite' in body or b'totp' in body
                                         or b'import os' in body))
        chk("%s 막힘" % probe, not bad, r.status_code)
    except Exception as e:
        chk("%s 막힘" % probe, True, str(e)[:40])

print("\n" + "=" * 68)
print("(4) 데이터 손실 - 후원 중복 / 되돌리기 / 복구")
print("=" * 68)
P('/api/server/start_broadcast', {})
BASE_STATE = {'broadcast_active': True,
              'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in ['가', '나', '다', '라']],
              'pending_donations': [], 'logs': []}
P('/api/restore', dict(BASE_STATE))

did = "dup_" + uuid.uuid4().hex[:8]
for _ in range(3):
    S.post(BASE + "/api/donation", json={'id': did, 'name': '중복군', 'amount': 10000,
                                         'message': 'ㅎㅇ', 'time': '20:00'}, timeout=15)
st = G('/api/data').json()
# 서버는 보낸 id 를 쓰지 않고 자기 id 를 새로 만든다. 중복 판정은 이름+금액+메시지로 한다.
cnt = sum(1 for x in (st.get('pending_donations') or []) if x.get('name') == '중복군')
chk("같은 후원 3번 보내도 대기함에 1건", cnt == 1, "%d건" % cnt)

before = {b['name']: b.get('score', 0) for b in G('/api/data').json()['bjs']}
P('/api/score/add', {'scope': 'rank', 'name': '가', 'delta': 7})
after = {b['name']: b.get('score', 0) for b in G('/api/data').json()['bjs']}
chk("점수 +7 이 정확히 반영", after['가'] - before['가'] == 7, (before['가'], after['가']))
P('/api/score/add', {'scope': 'rank', 'name': '가', 'delta': -7})
after2 = {b['name']: b.get('score', 0) for b in G('/api/data').json()['bjs']}
chk("되돌리기 -7 이 정확히 반영", after2['가'] == before['가'], after2['가'])

# ⚠️ 서버는 대기함 번호를 스스로 만든다. 보낸 id 는 쓰이지 않으므로 받아서 써야 한다.
#    (예전에는 아무 번호나 보내도 점수가 들어갔다. 지금은 대기함에 없는 번호면
#     '이미 처리된 것' 으로 보고 점수를 더하지 않는다 — 이중 지급 방지)
S.post(BASE + "/api/donation", json={'name': '배정군', 'amount': 30000,
                                     'message': '나 화이팅', 'time': '20:01'}, timeout=15)
time.sleep(0.4)
_pend = G('/api/data').json()['pending_donations']
did2 = next((x['id'] for x in reversed(_pend) if x.get('name') == '배정군'), None)
chk("배정할 후원이 대기함에 있다", did2 is not None, did2)
b0 = {b['name']: b.get('score', 0) for b in G('/api/data').json()['bjs']}
P('/api/score/add', {'scope': 'rank', 'name': '나', 'delta': 3, 'pending_id': did2,
                     'donor': '배정군', 'donor_message': '나 화이팅'})
b1 = {b['name']: b.get('score', 0) for b in G('/api/data').json()['bjs']}
st = G('/api/data').json()
chk("배정하면 대기함에서 빠진다", not any(x['id'] == did2 for x in st['pending_donations']))
chk("배정 점수 +3", b1['나'] - b0['나'] == 3, (b0['나'], b1['나']))
P('/api/pending/remove/' + did2, {})
b2 = {b['name']: b.get('score', 0) for b in G('/api/data').json()['bjs']}
chk("이미 뺀 후원을 또 빼도 점수가 안 늘어난다", b2['나'] == b1['나'], (b1['나'], b2['나']))

S.post(BASE + "/api/donation", json={'id': 'rst_1', 'name': '복구군', 'amount': 5000,
                                     'message': 'ㅇㅇ', 'time': '20:02'}, timeout=15)
full = G('/api/data').json()
n_pend = len(full['pending_donations'])
P('/api/restore', dict(BASE_STATE))
mid = G('/api/data').json()
chk("복구 전에 실제로 비워졌다", len(mid['pending_donations']) == 0, len(mid['pending_donations']))
P('/api/restore', full)
back = G('/api/data').json()
chk("복구가 대기 후원을 되살린다", len(back['pending_donations']) == n_pend,
    "%d -> %d" % (n_pend, len(back['pending_donations'])))
chk("복구가 점수도 되살린다",
    {b['name']: b['score'] for b in back['bjs']} == {b['name']: b['score'] for b in full['bjs']})

print("\n" + "=" * 68)
print("(5) 오토파일럿 기억 - 배운 것이 정확한가")
print("=" * 68)
PLAYERS = ['가', '나', '다', '라']
for i in range(3):
    P('/api/score/add', {'scope': 'rank', 'name': '다', 'delta': 1,
                         'donor': '별빛', 'donor_message': 'ㄷㄷ 가즈아'})
r = P('/api/audit/suggest', {'name': '별빛', 'amount': 10000, 'message': 'ㄱㅇㅈ',
                             'players': PLAYERS}).json()
chk("이력으로 알 수 없는 메시지를 푼다", r.get('target') == '다', r)
# 3번이면 0.87 = 추천이 설계다(4번부터 자동). 사람 확인 없이 돈이 가지 않게.
chk("3번 이력은 '추천' 까지만", r.get('tier') == 'suggest', (r.get('tier'), r.get('confidence')))

r = P('/api/audit/suggest', {'name': '처음', 'amount': 10000, 'message': 'ㄷㄷ 화이팅',
                             'players': PLAYERS}).json()
chk("별명으로 다른 후원자도 푼다", r.get('target') == '다', r)

r = P('/api/audit/suggest', {'name': '처음', 'amount': 10000, 'message': '가 화이팅',
                             'players': PLAYERS}).json()
chk("메시지의 이름이 이력보다 우선", r.get('target') == '가', r)

r = P('/api/audit/suggest', {'name': '처음', 'amount': 10000, 'message': '가 나 둘 다 화이팅',
                             'players': PLAYERS}).json()
chk("두 사람을 부르면 사람에게 넘긴다", r.get('target') is None, r)

P('/api/score/add', {'scope': 'rank', 'name': '라', 'delta': -5,
                     'donor': '되돌림군', 'donor_message': 'ㄹㄹ전용말'})
r = P('/api/audit/suggest', {'name': '되돌림군', 'amount': 1000, 'message': 'ㅎㅇ',
                             'players': PLAYERS}).json()
chk("되돌린 배정은 기억하지 않는다", r.get('target') is None, r)

for _ in range(3):
    P('/api/score/add', {'scope': 'rank', 'name': '라', 'delta': 1,
                         'donor': '익명', 'donor_message': 'ㅋㅋ'})
r = P('/api/audit/suggest', {'name': '익명', 'amount': 1000, 'message': 'ㅎㅇ',
                             'players': PLAYERS}).json()
chk("익명은 기억하지 않는다", r.get('target') is None, r)

r = P('/api/audit/suggest', {'name': '별빛', 'amount': 10000, 'message': 'ㄱㅇㅈ',
                             'players': ['전혀', '다른', '사람들']}).json()
chk("지금 없는 사람을 추천하지 않는다", r.get('target') in (None, '전혀', '다른', '사람들'), r)
chk("없는 사람이면 모름으로 떨어진다", r.get('target') is None, r)

print("\n" + "=" * 68)
print("(6) 리액션 큐 상한")
print("=" * 68)
qmax = int(re.search(r"REACTION_QUEUE_MAX\s*=\s*(\d+)", SRC).group(1))
st = G('/api/data').json()
print("  상한 %d건 / 현재 큐 %d건" % (qmax, len(st.get('reaction_queue') or [])))

print("\n" + "=" * 68)
print("통과 %d · 실패 %d" % (len(OK), len(BAD)))
if BAD:
    print("실패 목록:")
    for b in BAD:
        print("   - " + b)
print("=" * 68)
