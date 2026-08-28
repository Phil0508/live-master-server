# -*- coding: utf-8 -*-
"""마지막 세 가지가 정말 고쳐졌는지 + 원래 되던 게 안 깨졌는지."""
import sys, time
import requests
sys.stdout.reconfigure(encoding='utf-8')

BASE = "http://127.0.0.1:5177"
TOK = "lt-sandbox-secret-0123456789"
H = {"Authorization": "Bearer " + TOK, "Content-Type": "application/json"}
OK, BAD = [], []


def chk(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print(("  [OK] " if cond else "  [!!] ") + name + (("  -- " + str(detail)[:130]) if detail else ""))


def P(p, j=None):
    return requests.post(BASE + p, headers=H, json=(j or {}), timeout=25)


def G(p):
    return requests.get(BASE + p, headers=H, timeout=25).json()


PL = ['제이양', '밍밍', '철수', '영희']


def reset():
    P('/api/restore', {'broadcast_active': True,
                       'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in PL],
                       'pending_donations': [], 'logs': []})
    time.sleep(0.3)


print("\n" + "=" * 70)
print("① git 이 없는 서버에서 버전 되돌리기 → 500 이 아니라 400")
print("=" * 70)
r = requests.post(BASE + '/api/version/latest', headers=H, timeout=25)
chk("500 이 아니다", r.status_code != 500, r.status_code)
chk("400 으로 곱게 거절", r.status_code == 400, "%s %s" % (r.status_code, r.text[:90]))

print("\n" + "=" * 70)
print("② 별명은 두 번 이상 같은 사람으로 이어졌을 때부터")
print("=" * 70)
reset()
# 한 번만 본 말
P('/api/score/add', {'scope': 'rank', 'name': '밍밍', 'delta': 1,
                     'donor': '갑', 'donor_message': '색다른말하나'})
r = P('/api/audit/suggest', {'name': '을', 'amount': 10000, 'message': '색다른말하나',
                             'players': PL}).json()
chk("한 번만 본 말은 쓰지 않는다", r.get('source') != '별명',
    "source=%s target=%s" % (r.get('source'), r.get('target')))
# 두 번째
P('/api/score/add', {'scope': 'rank', 'name': '밍밍', 'delta': 1,
                     'donor': '병', 'donor_message': '색다른말하나'})
r = P('/api/audit/suggest', {'name': '정', 'amount': 10000, 'message': '색다른말하나',
                             'players': PL}).json()
chk("두 번부터 별명으로 쓴다", r.get('source') == '별명' and r.get('target') == '밍밍',
    "source=%s target=%s conf=%s" % (r.get('source'), r.get('target'), r.get('confidence')))

print("\n" + "=" * 70)
print("③ 이름을 바꿔도 그 사람 점수가 그대로 남는가")
print("=" * 70)
reset()
P('/api/score/add', {'scope': 'rank', 'name': '밍밍', 'delta': 40})
P('/api/score/add', {'scope': 'rank', 'name': '철수', 'delta': 7})
st = G('/api/data')
before = {b['name']: b['score'] for b in st['bjs']}
# 브라우저가 '낡은 점수'를 들고 개명을 보내는 상황을 그대로 재현한다
stale = [dict(b) for b in st['bjs']]
for b in stale:
    b['score'] = 0
    b['contribution'] = 0          # 브라우저가 들고 있던 낡은 값(0점 시절)
    if b['name'] == '밍밍':
        b['name'] = '밍밍이'        # 이름만 바꿔서 보낸다
P('/api/data', dict(st, bjs=stale))
after = {b['name']: b['score'] for b in G('/api/data')['bjs']}
chk("이름이 바뀌었다", '밍밍이' in after and '밍밍' not in after, list(after))
chk("바뀐 사람 점수가 그대로", after.get('밍밍이') == before.get('밍밍'),
    "%s → %s (기대 %s)" % (before.get('밍밍'), after.get('밍밍이'), before.get('밍밍')))
chk("남의 점수도 그대로", after.get('철수') == before.get('철수'), after)

print("\n  덧: 추가·삭제는 예전대로 (개명 처리에 휩쓸리면 안 된다)")
st = G('/api/data')
add = [dict(b) for b in st['bjs']] + [{'name': '새사람', 'score': 0, 'contribution': 0}]
P('/api/data', dict(st, bjs=add))
names = [b['name'] for b in G('/api/data')['bjs']]
chk("추가가 된다", '새사람' in names, names)
st = G('/api/data')
rm = [dict(b) for b in st['bjs'] if b['name'] != '새사람']
P('/api/data', dict(st, bjs=rm))
after2 = {b['name']: b['score'] for b in G('/api/data')['bjs']}
chk("삭제가 된다", '새사람' not in after2, list(after2))
chk("삭제해도 점수 그대로", after2.get('밍밍이') == before.get('밍밍'), after2)

print("\n  덧: 한 번에 둘을 바꾸면 손대지 않는다(확신할 수 없으므로)")
st = G('/api/data')
two = [dict(b) for b in st['bjs']]
n = 0
for b in two:
    if b['name'] in ('철수', '영희'):
        b['name'] = b['name'] + 'X'
        n += 1
P('/api/data', dict(st, bjs=two))
names = [b['name'] for b in G('/api/data')['bjs']]
chk("둘 다 이름은 바뀐다", ('철수X' in names and '영희X' in names), names)

print("\n" + "=" * 70)
print("기존 동작 회귀")
print("=" * 70)
reset()
P('/api/score/add', {'scope': 'rank', 'name': '제이양', 'delta': 4})
chk("배정 +4", {b['name']: b['score'] for b in G('/api/data')['bjs']}['제이양'] == 4)
for _ in range(4):
    P('/api/score/add', {'scope': 'rank', 'name': '밍밍', 'delta': 1,
                         'donor': '단골', 'donor_message': 'ㅇㅇ'})
r = P('/api/audit/suggest', {'name': '단골', 'amount': 10000, 'message': 'ㅎㅇ',
                             'players': PL}).json()
chk("후원자 이력은 여전히 자동", r.get('tier') == 'auto' and r.get('target') == '밍밍',
    "%s %s" % (r.get('target'), r.get('tier')))
r = P('/api/audit/suggest', {'name': '아무개', 'amount': 10000, 'message': '철수 화이팅',
                             'players': PL}).json()
chk("이름 부르면 자동", r.get('target') == '철수' and r.get('tier') == 'auto', r.get('tier'))
r = P('/api/audit/suggest', {'name': '아무개', 'amount': 10000, 'message': '철수했다가',
                             'players': PL}).json()
chk("낱말이 안 떨어지면 추천까지만", r.get('tier') == 'suggest', r.get('tier'))

print("\n" + "=" * 70)
print("통과 %d · 실패 %d" % (len(OK), len(BAD)))
for b in BAD:
    print("   - " + b)
print("=" * 70)
