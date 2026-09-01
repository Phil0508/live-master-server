# -*- coding: utf-8 -*-
"""🚫 순위에서 뺄 이름 — 익명·테스트를 명단에서 뺀다.

사장님 말
  "내가 고액후원자 명단을 수정할수있게 해줘. 익명이나 테스트로 썼던 사람들은
   없애고싶어."

여기서 지키는 것
  ① 후원 기록은 **안 지운다** ← 제일 중요하다. 지우면 되돌릴 수 없다
  ② 돈(게이지·총액)은 안 줄어든다 — 명단에서만 빠진다
  ③ 익명은 따로 안 빼도 언제나 명단 밖이다
  ④ 세 곳에 다 적용된다 — 등급 후보 · 월별 순위 · 방송 순위판
  ⑤ 언제든 되돌릴 수 있다
  ⑥ 아무나 남의 후원 장부를 못 만진다
"""
import io
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = r'C:\Users\Administrator\Desktop\새로다시시작'


def _find_proj():
    d = HERE
    for _ in range(4):
        d = os.path.dirname(d)
        if os.path.exists(os.path.join(d, 'server.py')):
            return d
    return REPO


PROJ = _find_proj()
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:120]) if detail else ''))


def post(p, d=None, authed=True):
    hdr = H if authed else {'Content-Type': 'application/json'}
    r = urllib.request.Request(B + p, data=json.dumps(d or {}).encode(), headers=hdr, method='POST')
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            return x.status, json.loads(x.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        return e.code, {}


def dele(p, authed=True):
    hdr = H if authed else {}
    r = urllib.request.Request(B + p, headers=hdr, method='DELETE')
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            return x.status, json.loads(x.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        return e.code, {}


def get(p, authed=True):
    hdr = {'Authorization': H['Authorization']} if authed else {}
    r = urllib.request.Request(B + p, headers=hdr)
    try:
        with urllib.request.urlopen(r, timeout=25) as x:
            return x.status, json.loads(x.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, {}


def donate(nm, amt, tx):
    urllib.request.urlopen(urllib.request.Request(
        B + '/api/donation',
        json.dumps({'tx_id': tx, 'name': nm, 'amount': amt, 'message': 'x', 'time': '20:00'}).encode(),
        {'Content-Type': 'application/json'}), timeout=20)
    time.sleep(0.15)


def names(path):
    _, d = get(path)
    return [r['name'] for r in (d.get('rows') or [])]


def tally():
    _, d = get('/api/data')
    return sorted((d.get('donor_tally') or {}).keys())


post('/api/restore', {'broadcast_active': True, 'bjs': [{'name': '가', 'score': 0, 'contribution': 0}],
                      'pending_donations': [], 'logs': [], 'donor_rank_enabled': True})
st = str(int(time.time()))[-6:]
SEED = [('진짜후원자', 900000), ('테스트', 700000), ('ㅇㅇ', 600000), ('익명', 5000000), ('별빛', 550000)]
for i, (n, a) in enumerate(SEED):
    donate(n, a, 'ex%s_%d' % (st, i))

# 월별 순위는 수요일 방송 시간만 세므로, 지난 수요일 기록을 장부에 직접 넣는다.
# ⚠️ 서버 사본 옆의 SQLite 를 쓴다. 운영은 Postgres 지만 셈하는 코드는 같다.
DB = os.path.join(HERE, 'pausetest', 'live_master.db')
if not os.path.exists(DB):
    DB = os.path.join(HERE, 'live_master.db')
seeded_month = os.path.exists(DB)
if seeded_month:
    try:
        c = sqlite3.connect(DB)
        for nm, amt, ts in [('진짜후원자', 900000, '2026-08-26 20:00:00'),
                            ('테스트', 700000, '2026-08-26 21:00:00'),
                            ('ㅇㅇ', 600000, '2026-08-26 22:00:00'),
                            ('익명', 5000000, '2026-08-26 23:00:00'),
                            ('별빛', 550000, '2026-08-27 01:30:00')]:   # 목 새벽 = 같은 방송
            c.execute("INSERT INTO donation_archive (archived_at, session_label, timestamp,"
                      " name, amount) VALUES (?,?,?,?,?)",
                      ('2026-08-27 03:00:00', '8월26일', ts, nm, amt))
        c.commit()
        c.close()
    except Exception as e:
        seeded_month = False
        print('  (월별 확인용 기록을 못 넣었습니다: %s)' % e)

print('=' * 74)
print('① 익명은 따로 안 빼도 언제나 명단 밖이다')
print('=' * 74)
"""⚠️ 익명은 사람이 아니다. 여러 건이 한 덩어리로 묶여 순위 위쪽에 앉으면
   '익명 500만원 1등' 같은 화면이 나온다. 월별 순위만 이걸 안 빼고 있었다."""
chk('등급 후보에 익명이 없다', '익명' not in names('/api/vips/candidates'))
if seeded_month:
    chk('월별 순위에 익명이 없다', '익명' not in names('/api/ranking/monthly'),
        names('/api/ranking/monthly'))
    _, m = get('/api/ranking/monthly?month=2026-08')
    chk('익명 500만원이 합계에서 빠졌다', (m.get('total') or 0) < 5000000, m.get('total'))
chk('익명은 빼기 목록에 넣을 수도 없다 (이미 늘 빠져 있다)',
    post('/api/donors/excluded', {'name': '익명'})[0] == 400)

print()
print('=' * 74)
print('② 뺀 이름이 세 곳에서 다 사라지는가')
print('=' * 74)
before_cand = names('/api/vips/candidates')
chk('빼기 전에는 후보에 있다', '테스트' in before_cand and 'ㅇㅇ' in before_cand, before_cand)
chk('빼기 전에는 방송 순위판에도 있다', '테스트' in tally(), tally())
chk('빼기가 된다', post('/api/donors/excluded', {'name': '테스트', 'memo': '테스트용'})[0] == 200)
post('/api/donors/excluded', {'name': 'ㅇㅇ'})
after = names('/api/vips/candidates')
chk('① 등급 후보에서 사라진다', '테스트' not in after and 'ㅇㅇ' not in after, after)
if seeded_month:
    mon = names('/api/ranking/monthly')
    chk('② 월별 순위에서 사라진다', '테스트' not in mon and 'ㅇㅇ' not in mon, mon)
chk('③ 방송 순위판에서 지금 바로 내려간다', '테스트' not in tally() and 'ㅇㅇ' not in tally(), tally())
chk('안 뺀 사람은 그대로 있다', '진짜후원자' in after and '별빛' in after)

print()
print('=' * 74)
print('③ 후원 기록을 지우지 않는가  ← 제일 중요')
print('=' * 74)
"""⚠️ donation_archive 는 '절대 삭제하지 않는' 영구 장부다. 지우면 총액·게이지·
   지난 방송 내역이 전부 어긋나고 되돌릴 수도 없다. 쪽지만 따로 둬야 한다."""
src = io.open(os.path.join(PROJ, 'server.py'), encoding='utf-8', errors='replace').read()
# ⚠️ donation_history 를 비우는 곳은 따로 있다 — 방송을 끝낼 때 장부(archive)로
#    옮긴 뒤 이번 방송분을 비우는 정상 동작이다. 그건 건드리면 안 되고, 여기서
#    볼 것은 '빼기 기능이 후원을 지우느냐' 뿐이다. 그래서 그 함수 안만 본다.
# 빼기·되돌리기 두 함수만 잘라 본다. 되돌리기가 donor_excluded 를 지우는 것은
# 정상이다 — 봐야 할 것은 '후원 표' 를 건드리느냐다.
_ex_code = src.split('def api_excluded_add')[1].split('# ====')[0]
chk('영구 장부(donation_archive)는 어디서도 안 지운다',
    'DELETE FROM donation_archive' not in src)
chk('빼기 기능이 후원 표를 건드리지 않는다',
    'donation_history' not in _ex_code and 'donation_archive' not in _ex_code,
    [l.strip() for l in _ex_code.splitlines() if 'donation_' in l][:2])
chk('빼기 기능이 지우는 것은 쪽지뿐이다',
    [l for l in _ex_code.splitlines() if 'DELETE FROM' in l.upper()]
    == ['            cur.execute(db_query("DELETE FROM donor_excluded WHERE name = ?"), (who,))'],
    [l.strip() for l in _ex_code.splitlines() if 'DELETE FROM' in l.upper()])
chk('쪽지를 따로 두는 표가 있다', 'CREATE TABLE IF NOT EXISTS donor_excluded' in src)
if seeded_month:
    try:
        c = sqlite3.connect(DB)
        n = c.execute("SELECT COUNT(*) FROM donation_archive WHERE name IN ('테스트','ㅇㅇ','익명')").fetchone()[0]
        c.close()
        chk('뺀 사람의 후원 기록이 장부에 그대로 있다', n == 3, '%d건' % n)
    except Exception as e:
        chk('장부 확인', False, e)

print()
print('=' * 74)
print('④ 돈은 안 줄어드는가')
print('=' * 74)
"""⚠️ 명단에서 빼는 것과 돈을 빼는 것은 다르다. 게이지는 점수판(bjs)에서 계산하므로
   donor_tally 와 길이 다르다 — 그래서 빼기가 게이지를 못 건드린다."""
ov = io.open(os.path.join(PROJ, 'overlay.html'), encoding='utf-8', errors='replace').read()
chk('게이지는 점수판에서 계산한다 (순위 명단과 다른 길)',
    'let tgt = d.target_goal || 1;' in ov and 'let bjs = d.bjs || [];' in ov)
chk('빼기는 donor_tally 만 건드린다', "state.get('donor_tally') or {}).pop(who, None)" in src)
chk('빼기 코드가 금액 합계를 건드리지 않는다',
    'target_goal' not in src.split('def api_excluded_add')[1].split('def api_excluded_remove')[0])

print()
print('=' * 74)
print('⑤ 되돌릴 수 있는가')
print('=' * 74)
chk('뺀 이름 목록이 보인다', sorted(names('/api/donors/excluded')) == sorted(['ㅇㅇ', '테스트']),
    names('/api/donors/excluded'))
chk('되돌리기가 된다',
    dele('/api/donors/excluded?name=' + urllib.parse.quote('테스트'))[0] == 200)
back = names('/api/vips/candidates')
chk('되돌리면 명단에 다시 나온다', '테스트' in back, back)
chk('다른 사람은 그대로 빠져 있다', 'ㅇㅇ' not in back)

print()
print('=' * 74)
print('⑥ 이름 다듬기가 서버와 같은가')
print('=' * 74)
# ⚠️ '홍길동님' 으로 빼고 '홍길동' 후원이 들어오면 안 빠진다 — 같은 규칙을 써야 한다
post('/api/donors/excluded', {'name': '별빛님'})
chk("'별빛님' 으로 빼면 '별빛' 도 빠진다", '별빛' not in names('/api/vips/candidates'),
    names('/api/vips/candidates'))
chk('저장은 다듬은 이름으로 된다', '별빛' in names('/api/donors/excluded'),
    names('/api/donors/excluded'))
dele('/api/donors/excluded?name=' + urllib.parse.quote('별빛'))

print()
print('=' * 74)
print('⑦ 아무나 남의 후원 장부를 못 만지는가')
print('=' * 74)
chk('무인증 조회 막힘', get('/api/donors/excluded', authed=False)[0] in (401, 403))
chk('무인증 빼기 막힘', post('/api/donors/excluded', {'name': 'x'}, authed=False)[0] in (401, 403))
chk('무인증 되돌리기 막힘', dele('/api/donors/excluded?name=x', authed=False)[0] in (401, 403))
chk('빈 이름은 안 받는다', post('/api/donors/excluded', {'name': '   '})[0] == 400)

print()
print('=' * 74)
print('⑧ 조종실 화면')
print('=' * 74)
ctl = io.open(os.path.join(PROJ, 'controller.html'), encoding='utf-8', errors='replace').read()
chk('후보 줄에서 바로 뺄 수 있다', 'excludeAdd(decodeURIComponent(' in ctl)
chk('뺀 이름 목록이 있다', 'id="ex-rows"' in ctl and 'loadExcluded' in ctl)
chk('직접 적어서도 뺄 수 있다', 'id="ex-name"' in ctl)
chk('되돌리기 버튼이 있다', 'function excludeRemove' in ctl)
chk('⚠️ 후원 기록은 안 지운다고 화면에 적혀 있다',
    '후원 기록은 지우지 않습니다' in ctl)
chk('익명은 자동으로 빠진다고 적혀 있다', '항상 명단에서 제외' in ctl)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
print('=' * 74)
sys.exit(1 if BAD else 0)
