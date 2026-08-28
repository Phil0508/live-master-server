# -*- coding: utf-8 -*-
"""점수가 틀어지는 길이 있는가 — 집중 점검.

방송에서 가장 중요한 값은 점수다. 여기서는 '어떻게 하면 점수가 틀어지는가'를
일부러 만들어 본다. 후원 한 건이 늘 같은 점수여야 하고, 되돌리면 정확히
제자리로 와야 하고, 여러 곳에서 동시에 눌러도 어긋나면 안 된다.
"""
import json, sys, threading, time, urllib.error, urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:110]) if detail else ''))


def post(path, obj, hdr=None):
    req = urllib.request.Request(B + path, json.dumps(obj).encode(), hdr or H)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode() or '{}')
        except Exception: return e.code, {}


def get():
    with urllib.request.urlopen(urllib.request.Request(B + '/api/data', headers=H), timeout=30) as r:
        return json.loads(r.read().decode())


def scores(d=None):
    d = d or get()
    src = 'extra_bjs' if d.get('extra_game_active') else 'bjs'
    return {b['name']: (b.get('score', 0), b.get('contribution', 0)) for b in (d.get(src) or [])}


def reset(names=('가', '나', '다')):
    post('/api/restore', {'broadcast_active': True, 'extra_game_active': False,
                          'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in names],
                          'extra_bjs': [], 'pending_donations': [], 'logs': [], 'match_logs': []})


def donate(name, amount, tx, msg=''):
    post('/api/donation', {'tx_id': tx, 'name': name, 'amount': amount, 'message': msg,
                           'time': '01:00'}, {'Content-Type': 'application/json'})
    time.sleep(0.35)
    pend = get()['pending_donations']
    return next((p['id'] for p in reversed(pend) if p.get('amount') == amount), None)


def js_round(x):
    """자바스크립트 Math.round — 5 는 항상 올린다.

       ⚠️ 파이썬 round() 는 5 를 짝수 쪽으로 보낸다(round(2.5)=2). 그대로 쓰면
          4만5천·5만원 같은 금액에서 화면과 다른 답이 나와, 검사가 거짓으로 통과한다.
    """
    import math
    return math.floor(x + 0.5)


def split_points(amount, n):
    """조종실·폰의 splitPoints() 와 같은 식(합계가 단독 배정과 같아야 한다)."""
    total = js_round(amount / 10000)
    base, rest = divmod(total, n)
    return [base + (1 if i < rest else 0) for i in range(n)]


print('=' * 74)
print('① 후원 한 건은 어떻게 나눠도 총점이 같아야 한다')
print('=' * 74)
for amount in (7000, 10000, 15000, 25000, 30000, 45000, 50000, 55000, 70000, 100000, 333000):
    single = js_round(amount / 10000)
    for n in (2, 3, 4):
        got = sum(split_points(amount, n))
        if got != single:
            chk('%d원을 %d명에게 나눠도 합계 %d점' % (amount, n, single), False, '%d점' % got)
            break
    else:
        chk('%d원 → 혼자 %d점 · 나눠도 합계 같음' % (amount, single), True)

# 예전 식들이 실제로 어긋났는지 (고친 이유를 숫자로 남긴다)
old_pc_half = lambda a: js_round(a / 2 / 10000) * 2
old_mo_half = lambda a: (js_round(a / 10000) // 2) * 2
diff = [(a, js_round(a / 10000), old_pc_half(a), old_mo_half(a)) for a in (10000, 30000, 50000, 70000, 333000)]
print('     참고 — 예전 식의 총점 (금액 / 혼자 / 옛 조종실반반 / 옛 폰반반):')
for row in diff:
    print('       %6d원  %2d점  %2d점  %2d점' % row)

print()
print('=' * 74)
print('② 배정하면 딱 그만큼만 오른다')
print('=' * 74)
reset()
did = donate('후원자A', 50000, 'toon_s1')
b0 = scores()
post('/api/score/add', {'scope': 'rank', 'name': '가', 'delta': 5, 'pending_id': did,
                        'donor': '후원자A'})
b1 = scores()
chk('점수 +5', b1['가'][0] - b0['가'][0] == 5, '%d → %d' % (b0['가'][0], b1['가'][0]))
chk('기여도도 +5', b1['가'][1] - b0['가'][1] == 5)
chk('다른 사람은 그대로', b1['나'] == b0['나'] and b1['다'] == b0['다'])
chk('대기함에서 빠졌다', not any(p['id'] == did for p in get()['pending_donations']))

print()
print('=' * 74)
print('③ 되돌리면 정확히 제자리')
print('=' * 74)
post('/api/score/add', {'scope': 'rank', 'name': '가', 'delta': -5, 'log': False})
b2 = scores()
chk('점수가 원래대로', b2['가'][0] == b0['가'][0], '%d' % b2['가'][0])
chk('기여도도 원래대로', b2['가'][1] == b0['가'][1])

print()
print('=' * 74)
print('④ 나눠주기 — 합계가 정확한가 (실제 API)')
print('=' * 74)
reset()
did = donate('후원자B', 50000, 'toon_s2')
pts = split_points(50000, 3)
before = scores()
post('/api/score/add', {'scope': 'rank', 'pending_id': did, 'donor': '후원자B',
                        'items': [{'name': n, 'delta': p} for n, p in zip(('가', '나', '다'), pts)]})
after = scores()
gained = sum(after[n][0] - before[n][0] for n in ('가', '나', '다'))
chk('세 명이 나눠 받은 합 = 혼자 받았을 때', gained == js_round(50000 / 10000), '%d점 (%s)' % (gained, pts))
# 되돌리기도 사람별로
post('/api/score/add', {'scope': 'rank', 'log': False,
                        'items': [{'name': n, 'delta': -p} for n, p in zip(('가', '나', '다'), pts)]})
back = scores()
chk('나눠준 것을 되돌리면 제자리',
    all(back[n] == before[n] for n in ('가', '나', '다')),
    {n: (before[n], back[n]) for n in ('가', '나', '다') if back[n] != before[n]})

print()
print('=' * 74)
print('⑤ 여러 곳에서 동시에 눌러도 어긋나지 않는가')
print('=' * 74)
reset()
N = 40
errs = []
def worker(i):
    try:
        c, _ = post('/api/score/add', {'scope': 'rank', 'name': ('가', '나', '다')[i % 3], 'delta': 1})
        if c != 200: errs.append(c)
    except Exception as e:
        errs.append(str(e))
ths = [threading.Thread(target=worker, args=(i,)) for i in range(N)]
t0 = time.time()
for t in ths: t.start()
for t in ths: t.join()
time.sleep(0.8)
s = scores()
total = sum(v[0] for v in s.values())
chk('%d번 동시에 눌러도 합계 %d점' % (N, N), total == N, '%d점 · %.1f초' % (total, time.time() - t0))
chk('실패한 요청 없음', not errs, errs[:3])

print()
print('=' * 74)
print('⑥ 상태 전체를 보내도 점수가 안 밀린다')
print('=' * 74)
reset()
post('/api/score/add', {'scope': 'rank', 'name': '가', 'delta': 7})
stale = get()                      # 조종실이 들고 있는 사본
post('/api/score/add', {'scope': 'rank', 'name': '가', 'delta': 3})   # 그 사이 폰에서 +3
for k in ('bjs', 'extra_bjs', 'bottom_fixed', 'logs', 'match_logs'):
    stale.pop(k, None)             # 조종실 pushAPI 가 빼고 보내는 것들
stale['marquee_text'] = '공지'
post('/api/data', stale)
time.sleep(0.4)
chk('낡은 사본을 보내도 나중 점수가 살아 있다', scores()['가'][0] == 10, scores()['가'])

# 명단을 실제로 고치는 경우(기여도 수정) — 이름이 같으면 서버 점수를 지킨다
stale2 = get()
stale2['bjs'] = [dict(b) for b in stale2['bjs']]
for b in stale2['bjs']:
    b['score'] = 999                # 브라우저의 낡은/엉뚱한 값
post('/api/score/add', {'scope': 'rank', 'name': '나', 'delta': 4})
post('/api/data', stale2)
time.sleep(0.4)
s = scores()
chk('명단을 보내도 점수는 서버 값', s['가'][0] == 10 and s['나'][0] == 4, s)

print()
print('=' * 74)
print('⑦ 이름을 바꿔도 점수가 따라간다')
print('=' * 74)
reset()
post('/api/score/add', {'scope': 'rank', 'name': '가', 'delta': 12})
cur = get()
rows = [dict(b) for b in cur['bjs']]
i = next(k for k, b in enumerate(rows) if b['name'] == '가')
rows[i]['name'] = '가나다'          # 개명
rows[i]['score'] = 0                # 브라우저가 들고 있던 낡은 값
rows[i]['contribution'] = 0
cur['bjs'] = rows
post('/api/data', cur)
time.sleep(0.4)
s = scores()
chk('개명해도 점수 12점 그대로', s.get('가나다', (None,))[0] == 12, s)

print()
print('=' * 74)
print('⑧ 이상한 값을 보내면')
print('=' * 74)
reset()
for body, want, why in [
    ({'scope': 'rank', 'name': '없는사람', 'delta': 5}, 404, '없는 사람'),
    ({'scope': 'rank', 'name': '', 'delta': 5}, 400, '이름이 빈칸'),
    ({'scope': 'rank', 'name': '가', 'delta': 'abc'}, 400, '점수가 글자'),
    ({'scope': 'ㅁㄴㅇ', 'name': '가', 'delta': 1}, 400, '모르는 scope'),
    ({'scope': 'rank', 'items': [{'name': '가', 'delta': 3}, {'name': '없음', 'delta': 3}]}, 404, '반반 중 한 명이 오타'),
]:
    c, _ = post('/api/score/add', body)
    chk('%s → %d' % (why, want), c == want, c)
s = scores()
chk('거부된 요청은 한 점도 안 넣었다', all(v == (0, 0) for v in s.values()), s)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
print('=' * 74)
