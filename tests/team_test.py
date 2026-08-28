# -*- coding: utf-8 -*-
"""대결 팀전 검증."""
import sys, json, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
TOK = 'sandboxsecret123456'

def req(path, data=None, method=None):
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(B + path, data=body, method=method or ('POST' if body else 'GET'),
                               headers={'Content-Type': 'application/json',
                                        'Authorization': 'Bearer ' + TOK})
    try:
        with urllib.request.urlopen(r, timeout=10) as f:
            return f.status, json.loads(f.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]

def state():
    return req('/api/data')[1]

ok = fail = 0
def chk(label, cond, extra=''):
    global ok, fail
    if cond: ok += 1; print(f'  ✅ {label}')
    else: fail += 1; print(f'  ❌ {label} {extra}')

# ── 준비: 점수판 + 대결 팀 2개 ──
s = state()
s['bjs'] = [{"name": "철수", "score": 0, "contribution": 0},
            {"name": "영희 ", "score": 0, "contribution": 0},   # 뒤에 공백 (예전 버그)
            {"name": "민수", "score": 0, "contribution": 0},
            {"name": "지연", "score": 0, "contribution": 0}]
s['extra_game_active'] = False
s['match_data'] = {"active": True, "players": [
        {"name": "A팀", "score": 0, "members": ["철수", "영희"]},
        {"name": "B팀", "score": 0, "members": ["민수"]}],
    "time_left_ms": 180000, "is_running": False, "team_mode": True}
st, _ = req('/api/data', s)
print('1) 준비 저장:', st)
s = state()
print('   저장된 팀:', json.dumps(s['match_data'], ensure_ascii=False))
chk('team_mode 저장됨', s['match_data'].get('team_mode') is True)
chk('members 저장됨', s['match_data']['players'][0].get('members') == ["철수", "영희"])
chk('점수판 이름 공백 제거', [b['name'] for b in s['bjs']] == ["철수", "영희", "민수", "지연"])

# ── 팀원에게 점수 → 팀 점수도 오른다 ──
print('\n2) 팀원 점수 지급')
st, r = req('/api/score/add', {"scope": "rank", "name": "철수", "delta": 5000})
print('   ', st, r if st != 200 else '')
s = state()
chk('철수 점수 5000', next(b for b in s['bjs'] if b['name'] == '철수')['score'] == 5000)
chk('A팀 점수 5000', s['match_data']['players'][0]['score'] == 5000,
    s['match_data']['players'][0]['score'])

st, r = req('/api/score/add', {"scope": "rank", "name": "영희", "delta": 3000})
print('   영희:', st)
s = state()
chk('A팀 누적 8000', s['match_data']['players'][0]['score'] == 8000,
    s['match_data']['players'][0]['score'])
chk('B팀 그대로 0', s['match_data']['players'][1]['score'] == 0)

st, r = req('/api/score/add', {"scope": "rank", "name": "민수", "delta": 2000})
s = state()
chk('B팀 2000', s['match_data']['players'][1]['score'] == 2000)

# ── 소속 없는 사람 ──
st, r = req('/api/score/add', {"scope": "rank", "name": "지연", "delta": 1000})
s = state()
chk('무소속 지연은 어느 팀에도 안 들어감',
    (s['match_data']['players'][0]['score'], s['match_data']['players'][1]['score']) == (8000, 2000))

# ── 팀 이동 ──
print('\n3) 철수를 B팀으로 이동')
s = state()
s['match_data']['players'][0]['members'] = ["영희"]
s['match_data']['players'][1]['members'] = ["민수", "철수"]
req('/api/data', s)
req('/api/score/add', {"scope": "rank", "name": "철수", "delta": 1000})
s = state()
chk('A팀 안 오름 8000', s['match_data']['players'][0]['score'] == 8000, s['match_data']['players'][0]['score'])
chk('B팀 3000', s['match_data']['players'][1]['score'] == 3000, s['match_data']['players'][1]['score'])

# ── 팀전 끄면 합산 없음 ──
print('\n4) 팀전 끄기')
s = state(); s['match_data']['team_mode'] = False; req('/api/data', s)
req('/api/score/add', {"scope": "rank", "name": "영희", "delta": 7000})
s = state()
chk('팀전 꺼짐 → A팀 그대로 8000', s['match_data']['players'][0]['score'] == 8000, s['match_data']['players'][0]['score'])
chk('영희 개인 점수는 올라감 10000', next(b for b in s['bjs'] if b['name'] == '영희')['score'] == 10000)

# ── 대결 꺼짐 ──
print('\n5) 대결 자체를 끔')
s = state(); s['match_data']['team_mode'] = True; s['match_data']['active'] = False; req('/api/data', s)
req('/api/score/add', {"scope": "rank", "name": "영희", "delta": 1000})
s = state()
chk('대결 꺼짐 → A팀 그대로 8000', s['match_data']['players'][0]['score'] == 8000, s['match_data']['players'][0]['score'])

# ── match 스코프는 팀 자체에 직접 ──
print('\n6) 대결 카드에 직접 넣기 (scope=match)')
s = state(); s['match_data']['active'] = True; req('/api/data', s)
st, r = req('/api/score/add', {"scope": "match", "name": "A팀", "delta": 500})
s = state()
chk('A팀 직접 8500', s['match_data']['players'][0]['score'] == 8500, (st, s['match_data']['players'][0]['score']))

# ── 후원 경로로도 되는지 (실제 방송 경로) ──
print('\n7) 후원이 들어왔을 때')
before = state()['match_data']['players'][1]['score']
st, r = req('/api/donation', {"name": "테스터", "amount": 4000, "message": "민수", "tx_id": "team_t1"})
print('   후원:', st)
s = state()
print('   B팀:', s['match_data']['players'][1]['score'], '(후원은 대기함으로 가므로 변화 없을 수 있음)')

print(f'\n═══ 통과 {ok} / 실패 {fail} ═══')
