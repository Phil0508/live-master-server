# -*- coding: utf-8 -*-
"""💰 게이지 보정 — 막대의 현재 금액을 사장님이 ± 로 직접 고친다.

사장님 말
  "최종 목표치는 수정 가능한데 실시간 목표는 내가 수정하게 할 수 있나?"
  → 막대에 뜨는 💰 현재 금액을 조종실에서 고칠 수 있게 했다.

여기서 지키는 것
  ① 보정은 막대 숫자에만 얹힌다 — 선수 점수·운영비는 한 푼도 안 움직인다
  ② 음수도 된다 (잘못 잡힌 만큼 빼기)
  ③ 방송을 끝내면 0 으로 돌아간다 — 다음 주로 넘어가면 그게 사고다 (목표치는 남는다)
  ④ 달성 판정 세 곳(막대·조종실 알림·서버 AI)이 같은 셈을 쓴다 — 점수 + 운영비 + 보정
"""
import io, json, os, sys, time, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
HERE = os.path.dirname(os.path.abspath(__file__))
def _find_proj():
    d = HERE
    for _ in range(4):
        d = os.path.dirname(d)
        if os.path.exists(os.path.join(d, 'server.py')): return d
    return (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
PROJ = _find_proj(); OK, BAD = [], []
def chk(n, c, d=''):
    (OK if c else BAD).append(n); print(('  [OK] ' if c else '  [!!] ') + n + (('  -- ' + str(d)[:100]) if d else ''))
def post(p, d):
    r = urllib.request.Request(B + p, data=json.dumps(d).encode(), headers=H, method='POST')
    with urllib.request.urlopen(r, timeout=25) as x: return json.loads(x.read().decode() or '{}')
def get():
    return json.loads(urllib.request.urlopen(urllib.request.Request(B + '/api/data', headers={'Authorization': H['Authorization']}), timeout=25).read().decode())
def push(**kw):
    """조종실 pushAPI 와 같은 길 — 점수 필드는 빼고 상태를 보낸다."""
    d = get(); body = {k: v for k, v in d.items() if k not in ('bjs', 'extra_bjs', 'bottom_fixed', 'logs', 'match_logs')}
    body.update(kw); post('/api/data', body)

print('=' * 74); print('① 보정은 막대 숫자에만 얹힌다'); print('=' * 74)
post('/api/restore', {'broadcast_active': True, 'target_goal': 100000, 'goal_offset': 0,
    'bjs': [{'name': '가', 'score': 30000, 'contribution': 30000}], 'bottom_fixed': {'name': '운영비', 'score': 10000},
    'pending_donations': [], 'logs': []})
push(goal_offset=25000)
d = get()
chk('보정이 저장된다', d.get('goal_offset') == 25000, d.get('goal_offset'))
chk('선수 점수는 그대로', d['bjs'][0]['score'] == 30000, d['bjs'][0]['score'])
chk('운영비도 그대로', d['bottom_fixed']['score'] == 10000, d['bottom_fixed']['score'])
chk('기여도도 그대로', d['bjs'][0]['contribution'] == 30000)

print(); print('=' * 74); print('② 음수도 된다'); print('=' * 74)
push(goal_offset=-5000); chk('−5,000 저장', get().get('goal_offset') == -5000, get().get('goal_offset'))

print(); print('=' * 74); print('③ 방송을 끝내면 0 으로 (목표치는 남는다)'); print('=' * 74)
push(goal_offset=70000); post('/api/server/end_broadcast', {}); time.sleep(1)
d = get()
chk('보정 0', int(d.get('goal_offset') or 0) == 0, d.get('goal_offset'))
chk('목표치는 남는다', d.get('target_goal') == 100000, d.get('target_goal'))

print(); print('=' * 74); print("③-b 방송을 '시작'해도 0 으로 — 지난주 보정이 넘어오면 안 된다"); print('=' * 74)
# ⚠️ 예전에는 종료 쪽에서만 0 으로 돌렸다. 그런데 서버는 상태를 메모리에 들고 있어서,
#    종료를 안 거치고 다음 방송을 시작하면 지난주 보정이 그대로 남아
#    게이지가 처음부터 그만큼 올라간 채로 시작했다.
post('/api/restore', {'broadcast_active': False, 'target_goal': 100000, 'goal_offset': 0,
    'bjs': [], 'bottom_fixed': {'name': '운영비', 'score': 0}, 'pending_donations': [], 'logs': []})
push(goal_offset=88000)
chk('시작 전 보정이 남아 있다', get().get('goal_offset') == 88000, get().get('goal_offset'))
post('/api/server/start_broadcast', {'names': ['가', '나']}); time.sleep(1)
d = get()
chk('방송을 시작하면 보정 0', int(d.get('goal_offset') or 0) == 0, d.get('goal_offset'))
chk('목표치는 그대로 남는다', d.get('target_goal') == 100000, d.get('target_goal'))

print(); print('=' * 74); print('④ 달성 판정 세 곳이 같은 셈 — 점수 + 운영비 + 보정'); print('=' * 74)
ov = io.open(os.path.join(PROJ, 'overlay.html'), encoding='utf-8', errors='replace').read()
ct = io.open(os.path.join(PROJ, 'controller.html'), encoding='utf-8', errors='replace').read()
sv = io.open(os.path.join(PROJ, 'server.py'), encoding='utf-8', errors='replace').read()
chk('막대 — 보정을 더한다', 'tot += parseInt(d.goal_offset) || 0;' in ov)
chk('조종실 알림 — 점수 + 운영비 + 보정', "+ (parseInt(gd.goal_offset) || 0);" in ct and "acc + (b.score || 0), 0)" in ct)
chk('조종실 알림 — 기여도로 안 본다', "acc + (b.contribution || 0), 0);\n            const isGoalReached" not in ct.replace('\r\n', '\n'))
seg = sv.split('def _goal_waiting')[1].split('def ')[0]
chk('서버 AI 판정 — 같은 셈', "state.get('goal_offset')" in seg and "b.get('score')" in seg and 'contribution' not in seg)
chk('조종실에 입력칸이 있다', 'id="in-offset"' in ct and 'function updateOffset' in ct)
chk('방송 종료 때 0 으로 돌리는 줄이 있다', "state['goal_offset'] = 0" in sv)
# ⚠️ 시작·종료 양쪽에서 불리는 reset_session_keys 안에 있어야 한다. 종료 쪽에만 두면
#    종료를 안 거치고 시작한 방송에 지난주 보정이 넘어온다.
_NL = chr(10)
_rs = sv.split('def reset_session_keys')[1].split(_NL + 'def ')[0]
chk('보정 초기화가 reset_session_keys 안에 있다', "state['goal_offset'] = 0" in _rs)

print(); print('=' * 74); print('⑤ 슬롯은 기본으로 꺼져 있다 — 켜져 있으면 게이지 금액을 가린다'); print('=' * 74)
# ⚠️ 기본값이 True 였다. DB 를 새로 만들면 아무도 안 켰는데 슬롯판이 떠 있고,
#    오버레이가 body.game-on 을 붙여 게이지 옆 💰 금액이 사라진다.
_ds = sv.split('DEFAULT_STATE = {')[1].split(_NL + '}')[0]
chk('slot_enabled 기본값이 False', '"slot_enabled": False' in _ds, 
    [l.strip() for l in _ds.split(_NL) if 'slot_enabled' in l])
chk('게임판이 뜨면 금액을 숨기는 규칙은 그대로', 'body.game-on .goal-rail-tip' in ov)

print(); print('=' * 74); print('통과 %d · 실패 %d' % (len(OK), len(BAD))); print('=' * 74)
sys.exit(1 if BAD else 0)
