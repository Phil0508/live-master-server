# -*- coding: utf-8 -*-
"""고친 세 가지가 실제로 고쳐졌는지, 그리고 원래 되던 것이 안 깨졌는지."""
import os, shutil, sys, time
import requests
sys.stdout.reconfigure(encoding='utf-8')

BASE = "http://127.0.0.1:5177"
TOK = "lt-sandbox-secret-0123456789"
H = {"Authorization": "Bearer " + TOK, "Content-Type": "application/json"}
OK, BAD = [], []


def chk(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print(("  [OK] " if cond else "  [!!] ") + name + (("  -- " + str(detail)[:120]) if detail else ""))


def P(p, j=None):
    return requests.post(BASE + p, headers=H, json=(j or {}), timeout=25)


def G(p):
    return requests.get(BASE + p, headers=H, timeout=25)


PLAYERS = ['제이양', '밍밍', '철수', '영희']


def reset():
    P('/api/restore', {'broadcast_active': True,
                       'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in PLAYERS],
                       'pending_donations': [], 'logs': []})
    time.sleep(0.3)


print("\n" + "=" * 76)
print("고침 ② — 이름이 낱말 속에 걸렸을 때")
print("=" * 76)
reset()
CASES = [
    ('철수 화이팅',            '철수', 'auto',    '정상 지목'),
    ('철수형 힘내요',           '철수', 'auto',    '호칭이 붙어도'),
    ('철수에게 보냅니다',         '철수', 'auto',    '조사가 붙어도'),
    ('철수님 감사합니다',         '철수', 'auto',    '님'),
    ('밍밍이 최고',            '밍밍', 'auto',    '이'),
    ('철수했다가 다시 왔어요',      '철수', 'suggest', '<- 예전엔 자동 배정됐다'),
    ('밍밍화이팅',             '밍밍', 'suggest', '붙여 써도 놓치지 않는다'),
    ('영희랑 철수 둘 다',        None,  'unknown', '두 명'),
    ('오늘 방송 재밌네요',        None,  'unknown', '아무도 안 부름'),
]
for msg, want, want_tier, note in CASES:
    r = P('/api/audit/suggest', {'name': '아무개', 'amount': 10000, 'message': msg,
                                 'players': PLAYERS}).json()
    got, tier = r.get('target'), r.get('tier')
    chk("%-18s -> %-4s %-8s  %s" % (repr(msg)[:18], got, tier, note),
        got == want and tier == want_tier, "기대 %s/%s" % (want, want_tier))

print("\n  1글자 이름이 섞였을 때")
r = P('/api/audit/suggest', {'name': '아무개', 'amount': 10000, 'message': '가즈아!!',
                             'players': ['가', '나', '다']}).json()
chk("'가즈아' 가 이름 '가' 로 자동 배정되지 않는다", r.get('tier') != 'auto',
    "%s %s %.2f" % (r.get('target'), r.get('tier'), r.get('confidence')))
r = P('/api/audit/suggest', {'name': '아무개', 'amount': 10000, 'message': '민트초코 맛있다',
                             'players': ['민', '수']}).json()
chk("'민트초코' 가 이름 '민' 으로 자동 배정되지 않는다", r.get('tier') != 'auto',
    "%s %s" % (r.get('target'), r.get('tier')))
r = P('/api/audit/suggest', {'name': '아무개', 'amount': 10000, 'message': '가 화이팅',
                             'players': ['가', '나', '다']}).json()
chk("'가 화이팅' 은 그대로 자동 배정된다", r.get('target') == '가' and r.get('tier') == 'auto',
    "%s %s" % (r.get('target'), r.get('tier')))

print("\n  이름이 겹치는 로스터 (수아 / 수)")
r = P('/api/audit/suggest', {'name': '아무개', 'amount': 10000, 'message': '수아 화이팅',
                             'players': ['수아', '수']}).json()
chk("'수아 화이팅' 은 긴 이름(수아)으로 간다", r.get('target') == '수아',
    "%s %s" % (r.get('target'), r.get('tier')))

print("\n" + "=" * 76)
print("고침 ③ — 기여도 수정이 실제로 되는가 (델타 방식으로 바뀐 뒤)")
print("=" * 76)
reset()
P('/api/score/add', {'scope': 'rank', 'name': '밍밍', 'delta': 5})
b = {x['name']: (x['score'], x.get('contribution')) for x in G('/api/data').json()['bjs']}
chk("배정으로 점수 5 · 기여도 5", b['밍밍'] == (5, 5), b['밍밍'])

# 기여도만 +3 (조종실 [+] 버튼이 하는 일)
P('/api/score/add', {'scope': 'rank', 'name': '밍밍', 'delta': 0, 'contribution': 3, 'log': False})
b = {x['name']: (x['score'], x.get('contribution')) for x in G('/api/data').json()['bjs']}
chk("기여도만 +3 (점수는 그대로)", b['밍밍'] == (5, 8), b['밍밍'])

# 기여도를 20 으로 맞추기 (차이 +12)
P('/api/score/add', {'scope': 'rank', 'name': '밍밍', 'delta': 0, 'contribution': 12, 'log': False})
b = {x['name']: (x['score'], x.get('contribution')) for x in G('/api/data').json()['bjs']}
chk("기여도를 20 으로 맞춤", b['밍밍'] == (5, 20), b['밍밍'])

# 기여도만 바꿔도 로그가 안 남는가
logs = G('/api/data').json().get('logs') or []
chk("기여도 조정은 지급 기록을 더럽히지 않는다", len(logs) == 1, "%d줄" % len(logs))

print("\n  명단 조작(이름변경·추가·삭제)이 그대로 되는가")
reset()
P('/api/score/add', {'scope': 'rank', 'name': '철수', 'delta': 7})
st = G('/api/data').json()
bjs = st['bjs']
# 이름 변경
for x in bjs:
    if x['name'] == '영희':
        x['name'] = '영희쨩'
P('/api/data', dict(st, bjs=bjs))
names = [x['name'] for x in G('/api/data').json()['bjs']]
chk("이름 변경이 반영된다", '영희쨩' in names and '영희' not in names, names)
sc = {x['name']: x['score'] for x in G('/api/data').json()['bjs']}
chk("이름을 바꿔도 남의 점수는 그대로", sc.get('철수') == 7, sc)

# 추가
st = G('/api/data').json()
st['bjs'] = st['bjs'] + [{'name': '새사람', 'score': 0, 'contribution': 0}]
P('/api/data', st)
names = [x['name'] for x in G('/api/data').json()['bjs']]
chk("플레이어 추가가 된다", '새사람' in names, names)

# 삭제
st = G('/api/data').json()
st['bjs'] = [x for x in st['bjs'] if x['name'] != '새사람']
P('/api/data', st)
names = [x['name'] for x in G('/api/data').json()['bjs']]
chk("플레이어 삭제가 된다", '새사람' not in names, names)
sc = {x['name']: x['score'] for x in G('/api/data').json()['bjs']}
chk("삭제해도 남의 점수는 그대로", sc.get('철수') == 7, sc)

print("\n  명단을 보내면서 점수를 되돌리려 해도 서버가 막는가")
st = G('/api/data').json()
for x in st['bjs']:
    x['score'] = 0
    x['contribution'] = 0
P('/api/data', st)
sc = {x['name']: x['score'] for x in G('/api/data').json()['bjs']}
chk("옛 점수를 실어 보내도 서버 값이 지켜진다", sc.get('철수') == 7, sc)

print("\n" + "=" * 76)
print("기존 동작 회귀 — 배정·되돌리기·반반")
print("=" * 76)
reset()
P('/api/score/add', {'scope': 'rank', 'name': '제이양', 'delta': 4,
                     'donor': '단골손님', 'donor_message': 'ㄱㅇㅈ'})
sc = {x['name']: x['score'] for x in G('/api/data').json()['bjs']}
chk("배정 +4", sc['제이양'] == 4, sc)
P('/api/score/add', {'scope': 'rank', 'items': [{'name': '밍밍', 'delta': 2},
                                                {'name': '철수', 'delta': 2}]})
sc = {x['name']: x['score'] for x in G('/api/data').json()['bjs']}
chk("반반 지급 2/2", sc['밍밍'] == 2 and sc['철수'] == 2, sc)
P('/api/score/add', {'scope': 'rank', 'name': '제이양', 'delta': -4})
sc = {x['name']: x['score'] for x in G('/api/data').json()['bjs']}
chk("되돌리기 -4", sc['제이양'] == 0, sc)

for _ in range(3):
    P('/api/score/add', {'scope': 'rank', 'name': '제이양', 'delta': 1,
                         'donor': '단골손님', 'donor_message': 'ㄱㅇㅈ 가즈아'})
r = P('/api/audit/suggest', {'name': '단골손님', 'amount': 10000, 'message': 'ㅎㅇ',
                             'players': PLAYERS}).json()
chk("후원자 기억이 여전히 동작한다", r.get('target') == '제이양',
    "%s %s %.2f" % (r.get('target'), r.get('tier'), r.get('confidence')))

print("\n" + "=" * 76)
print("통과 %d · 실패 %d" % (len(OK), len(BAD)))
for b in BAD:
    print("   - " + b)
print("=" * 76)
