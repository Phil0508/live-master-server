# -*- coding: utf-8 -*-
"""이번에 막은 두 구멍이 정말 막혔는가.

① 같은 후원을 폰과 PC 에서 동시에 배정하면 점수가 두 번 들어가던 것
② 조종실이 스위치 하나를 누를 때 보내는 '상태 전체' 가
   그 사이 들어온 후원의 순위 집계를 덮어쓰던 것
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
    req = urllib.request.Request(B + '/api/data', headers=H)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def reset(players=('제이양', '밍밍')):
    post('/api/restore', {'broadcast_active': True,
                          'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in players],
                          'pending_donations': [], 'logs': []})


print('=' * 74)
print('① 같은 후원을 두 곳에서 동시에 배정하면')
print('=' * 74)
reset()
post('/api/donation', {'tx_id': 'toon_dbl1', 'name': '겹침이', 'amount': 50000,
                       'message': '제이양 화이팅', 'time': '01:00'}, {'Content-Type': 'application/json'})
time.sleep(0.8)
pend = get()['pending_donations']
chk('후원이 대기함에 들어왔다', len(pend) == 1, '%d건' % len(pend))
don_id = pend[0]['id']
add = 5      # 50000원 → 5점

res = {}
def worker(tag):
    res[tag] = post('/api/score/add', {'scope': 'rank', 'name': '제이양', 'delta': add,
                                       'pending_id': don_id, 'donor': '겹침이',
                                       'donor_message': '제이양 화이팅'})

ths = [threading.Thread(target=worker, args=(t,)) for t in ('폰', 'PC')]
for t in ths: t.start()
for t in ths: t.join()
time.sleep(0.6)

d = get()
score = next((b['score'] for b in d['bjs'] if b['name'] == '제이양'), None)
chk('점수가 한 번만 들어간다', score == add, '%s점 (기대 %d)' % (score, add))
chk('대기함에서 사라졌다', len(d['pending_donations']) == 0, '%d건' % len(d['pending_donations']))
skipped = [t for t, (c, b) in res.items() if b.get('already')]
chk('한쪽은 "이미 처리됨" 을 돌려받는다', len(skipped) == 1, '%s 쪽이 건너뜀' % (skipped or '아무도 아님'))

print()
print('=' * 74)
print('② 상태 전체를 보낼 때 집계가 덮이는가')
print('=' * 74)
reset()
for i, (nm, amt) in enumerate([('큰손', 100000), ('작은손', 20000)]):
    post('/api/donation', {'tx_id': 'toon_ov%d' % i, 'name': nm, 'amount': amt,
                           'message': '', 'time': '02:00'}, {'Content-Type': 'application/json'})
    time.sleep(0.3)
before = get()
chk('집계가 쌓였다', len(before.get('donor_tally') or {}) == 2,
    json.dumps(before.get('donor_tally'), ensure_ascii=False)[:80])

# 조종실이 들고 있던 '낡은 사본' — 집계가 비어 있던 시절의 것
stale = dict(before)
stale['donor_tally'] = {}
stale['sig_tally'] = {}
stale['marquee_text'] = '공지'
for k in ('bjs', 'extra_bjs', 'bottom_fixed', 'logs', 'match_logs'):
    stale.pop(k, None)          # 조종실 pushAPI 가 빼고 보내는 것들
code, _ = post('/api/data', stale)
time.sleep(0.5)
after = get()
chk('상태 전체를 보내도 후원 집계가 살아남는다',
    len(after.get('donor_tally') or {}) == 2,
    json.dumps(after.get('donor_tally'), ensure_ascii=False)[:80])
chk('설정은 정상적으로 바뀐다', after.get('marquee_text') == '공지', after.get('marquee_text'))

# 편집기의 '집계 지우기'(설정 패치)는 계속 동작해야 한다
code, _ = post('/api/settings/patch', {'sig_tally': {}})
chk('편집기의 집계 지우기는 그대로 된다(시그니처)', code == 200, code)
code, body = post('/api/settings/patch', {'donor_tally': {}})
chk('후원 집계는 밖에서 못 지운다', code == 400, '%s %s' % (code, body.get('message', '')[:40]))

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
print('=' * 74)
