# -*- coding: utf-8 -*-
"""🛠️ 점수·돈 버그 고친 것 (2026-09-30 감사) — 서버가 정말 그렇게 하는가.

1. 대결 점수 — 조종실(/api/data)·폰 타이머(/api/settings/patch)가 보낸 낡은 사본이 점수를 덮지 않는다
2. 원장 재정산 — 이번 방송분만 더하고, 명단에 없는 이름을 되살리지 않는다
3. 시각으로 되돌리기 — 막혀 있다(410). 명단이 후원자 이름으로 바뀌지 않는다
5. 방송 종료를 두 번 눌러도 후원이 두 번 보관되지 않는다
6. 방송이 바뀌면 리액션 대기줄이 비워진다
4·5·7 의 '실패 경로' 는 HTTP 로 못 일으키므로, LM_SANDBOX_DIR(서버 사본 폴더)를 주면
   그 사본을 새 임시 폴더에 복사해 프로세스 안에서(test_client) 확인한다.

⚠️ 방송 시작·종료를 부른다 — 반드시 샌드박스 서버에만 돌린다.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:%s' % os.environ.get('LM_PT_PORT', '5199')
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:150]) if detail else ''))


def post(path, obj=None):
    req = urllib.request.Request(B + path, json.dumps(obj or {}).encode(), H)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def get(path='/api/data'):
    with urllib.request.urlopen(urllib.request.Request(B + path, headers=H), timeout=40) as r:
        return json.loads(r.read().decode())


def mscore(s, name):
    p = next((p for p in (s.get('match_data') or {}).get('players') or [] if p.get('name') == name), None)
    return None if p is None else p.get('score')


def bscore(s, name):
    p = next((p for p in s.get('bjs') or [] if p.get('name') == name), None)
    return None if p is None else p.get('score')


# ─────────────────────────────────────────────────────────────
print('1) 대결 점수 — 낡은 사본이 덮지 않는다')
st, r = post('/api/server/start_broadcast', {'names': ['철수', '영희']})
chk('방송 시작', st == 200, r)
s = get()
s['match_data'] = {'active': True, 'players': [{'name': 'A팀', 'score': 0, 'members': []},
                                              {'name': 'B팀', 'score': 0, 'members': []}],
                   'time_left_ms': 180000, 'is_running': False, 'team_mode': False}
post('/api/data', s)
stale = get()                                   # 조종실이 들고 있는 사본(점수 주기 전)
st, r = post('/api/score/add', {'scope': 'match', 'name': 'A팀', 'delta': 500})
chk('대결 점수 주기', st == 200, r)
chk('A팀 500', mscore(get(), 'A팀') == 500, mscore(get(), 'A팀'))

stale['match_data']['time_left_ms'] = 120000   # 조종실에서 타이머만 고쳐 통째로 보낸다
post('/api/data', stale)
s = get()
chk('/api/data 낡은 사본 뒤에도 A팀 500', mscore(s, 'A팀') == 500, mscore(s, 'A팀'))
chk('/api/data 타이머 변경은 받아들인다', s['match_data'].get('time_left_ms') == 120000,
    s['match_data'].get('time_left_ms'))

md = json.loads(json.dumps(stale['match_data']))
md['is_running'] = True
md['end_time_ms'] = int(time.time() * 1000) + 60000
st, r = post('/api/settings/patch', {'match_data': md})   # 폰 타이머 버튼
s = get()
chk('폰 패치 뒤에도 A팀 500', mscore(s, 'A팀') == 500, (st, mscore(s, 'A팀')))
chk('폰 패치 타이머 시작은 받아들인다', s['match_data'].get('is_running') is True)
_mdx = json.loads(json.dumps(stale['match_data']))
_mdx['players'][0]['name'] = '폰에서바꾼이름'
post('/api/settings/patch', {'match_data': _mdx})
chk('폰 창구로는 대결자 이름 · 팀원이 안 바뀐다 (서버 명단 그대로)', mscore(get(), 'A팀') == 500 and mscore(get(), '폰에서바꾼이름') is None)

post('/api/score/add', {'scope': 'match', 'name': 'B팀', 'delta': 70})
# ⚠️ 2026-09-30 — 폰 창구(/api/settings/patch)는 이제 대결자 명단을 통째로 서버 값으로 지킨다
#    (옛 사본 타이머가 팀원 구성을 되돌려 점수가 옛 팀으로 가던 것). 이름은 조종실 창구로만 바꾼다.
_st = get()
_st['match_data'] = json.loads(json.dumps(stale['match_data']))
_st['match_data']['players'][0]['name'] = 'A팀장'   # 이름만 바꾼다(낡은 점수 0 이 실려 간다)
st, r = post('/api/data', _st)
s = get()
chk('이름 바꾼 대결자는 옛 점수를 물려받는다', mscore(s, 'A팀장') == 500, s['match_data'].get('players'))
chk('B팀 70 그대로', mscore(s, 'B팀') == 70, mscore(s, 'B팀'))

s = get()
s['match_data']['players'].append({'name': '새팀', 'score': 0, 'members': []})
post('/api/data', s)
s = get()
chk('새 대결자는 0 으로 들어온다', mscore(s, '새팀') == 0, mscore(s, '새팀'))
s['match_data']['players'] = [p for p in s['match_data']['players'] if p['name'] != 'B팀']
post('/api/data', s)
s = get()
chk('대결자 삭제는 받아들인다', mscore(s, 'B팀') is None and mscore(s, 'A팀장') == 500,
    s['match_data'].get('players'))
# ⚠️ [대결자 추가]를 두 번 누르면 둘 다 'Player' — 두 번째가 첫 번째 점수를 복사하면 안 된다(최종 검증에서 잡은 회귀)
s['match_data']['players'].append({'name': 'Player', 'score': 0, 'members': []})
post('/api/data', s)
post('/api/score/add', {'scope': 'match', 'name': 'Player', 'delta': 50})
s = get()
s['match_data']['players'].append({'name': 'Player', 'score': 0, 'members': []})
post('/api/data', s)
s = get()
_pl = [p.get('score') for p in s['match_data']['players'] if p.get('name') == 'Player']
chk('같은 이름 대결자 둘 — 두 번째는 0 (첫 번째 점수를 복사하지 않는다)', _pl == [50, 0], _pl)

# ─────────────────────────────────────────────────────────────
print('\n2) 원장 재정산 — 이번 방송분만 · 명단에 없는 이름은 안 되살린다')
post('/api/server/start_broadcast', {'names': ['철수', '영희', '옛사람']})
post('/api/score/add', {'scope': 'rank', 'name': '옛사람', 'delta': 7})
post('/api/score/add', {'scope': 'rank', 'name': '철수', 'delta': 3})
time.sleep(0.5)
post('/api/server/start_broadcast', {'names': ['철수', '영희']})   # 다음 방송
post('/api/score/add', {'scope': 'rank', 'name': '철수', 'delta': 2})
time.sleep(0.5)
st, r = post('/api/bank/recalculate')
s = get()
chk('재정산 성공', st == 200, r)
chk('철수 = 이번 방송분 2 (지난 방송 3 을 안 더한다)', bscore(s, '철수') == 2, bscore(s, '철수'))
chk('영희 0 그대로', bscore(s, '영희') == 0, bscore(s, '영희'))
chk('옛사람이 되살아나지 않는다', bscore(s, '옛사람') is None, [b['name'] for b in s['bjs']])

# ─────────────────────────────────────────────────────────────
print('\n3) 시각으로 되돌리기 — 막혀 있다')
st, r = post('/api/donation', {'name': '후원자갑', 'amount': 30000, 'message': 't', 'tx_id': 'fix3_%d' % time.time()})
before = [b['name'] for b in get()['bjs']]
st, r = post('/api/time_machine/restore_by_time', {'time': time.strftime('%H:%M', time.localtime(time.time() + 60))})
after = [b['name'] for b in get()['bjs']]
chk('410 으로 답한다', st == 410, (st, r))
chk('스냅샷 되돌리기를 안내한다', '스냅샷' in str(r.get('message')), r)
chk('명단이 후원자 이름으로 안 바뀐다', before == after and '후원자갑' not in after, after)

# ─────────────────────────────────────────────────────────────
print('\n5·6) 방송 종료 — 두 번 눌러도 보관 한 번 · 리액션 대기줄 비움')


def archived_total():
    return sum(x['count'] for x in get('/api/archive/sessions').get('sessions') or [])


stamp = int(time.time())
for i in range(2):
    post('/api/donation', {'name': '보관%d' % i, 'amount': 1000 + i, 'message': 'x', 'tx_id': 'fix5_%d_%d' % (stamp, i)})
winner = {'id': 10001, 'amount': 10100, 'title': '테스트시그1',
          'image_url': 'https://example.invalid/i.webp', 'sound_url': 'https://example.invalid/s.mp3', 'duration': 10}
st, r = post('/api/slot/spin', {'winner': winner, 'candidates': [winner]})
time.sleep(5)                                    # 슬롯 결과(4초) 뒤 대기줄에 들어간다
chk('슬롯 당첨이 리액션 대기줄에 들어갔다', len(get().get('reaction_queue') or []) >= 1,
    len(get().get('reaction_queue') or []))
n0 = archived_total()
st, r = post('/api/server/end_broadcast')
chk('방송 종료', st == 200, r)
n1 = archived_total()
chk('이번 방송 후원이 보관됐다(3건 이상)', n1 - n0 >= 3, (n0, n1))
st, r = post('/api/server/end_broadcast')
n2 = archived_total()
chk('두 번째 종료는 다시 보관하지 않는다', n2 == n1, (n1, n2))
s = get()
chk('리액션 대기줄이 비었다', not (s.get('reaction_queue') or []), len(s.get('reaction_queue') or []))
chk('리액션 모드 꺼짐', s.get('reaction_mode') is False)

# ─────────────────────────────────────────────────────────────
INPROC = r'''
import os, sys, json, copy
sys.stdout.reconfigure(encoding='utf-8')
os.environ.update(HEADLESS='1', ADMIN_PASSWORD='sandboxpw', SESSION_SECRET='sandboxsecret123456', SELF_PING='off')
sys.path.insert(0, os.getcwd())
import server
server.init_db()
c = server.app.test_client()
H = {'Authorization': 'Bearer sandboxsecret123456'}
def say(ok, name, detail=''):
    print(('OK ' if ok else 'BAD ') + name + ((' -- ' + str(detail)[:150]) if detail else ''), flush=True)
def cnt(t):
    with server.get_db_connection() as conn:
        cur = conn.cursor(); cur.execute('SELECT COUNT(*) FROM ' + t); return cur.fetchone()[0]
def kv(k):
    with server.get_db_connection() as conn:
        cur = conn.cursor(); cur.execute('SELECT value FROM kv_store WHERE key = ?', (k,)); r = cur.fetchone()
        return json.loads(r[0]) if r else None

c.post('/api/server/start_broadcast', json={'names': ['갑', '을']}, headers=H)
for i in range(3):
    c.post('/api/donation', json={'name': 'd%d' % i, 'amount': 1000, 'message': 'm', 'tx_id': 'ip_%d' % i}, headers=H)
c.post('/api/settings/patch', json={'slot_price': 33000}, headers=H)
server.drain_db_writes()

# 5) 지우기 도중 실패 → 보관도 되돌려진다(한 트랜잭션)
a0, h0 = cnt('donation_archive'), cnt('donation_history')
_orig_mark = server._ledger_mark_broadcast
def _boom(cur, label): raise RuntimeError('일부러 낸 실패')
server._ledger_mark_broadcast = _boom
r = c.post('/api/server/end_broadcast', headers=H)
server._ledger_mark_broadcast = _orig_mark
say(r.status_code == 500, '5) 초기화 중 실패하면 500', r.status_code)
say(cnt('donation_archive') == a0 and cnt('donation_history') == h0,
    '5) 실패하면 보관도 지우기도 안 됐다(재시도해도 두 번 보관 안 됨)', (a0, cnt('donation_archive'), h0, cnt('donation_history')))
r = c.post('/api/server/end_broadcast', headers=H)
say(r.status_code == 200 and cnt('donation_archive') == a0 + h0 and cnt('donation_history') == 0,
    '5) 다시 누르면 정확히 한 번 보관', (r.status_code, a0, h0, cnt('donation_archive')))

# 4) 전체 저장이 실패하면 성공이라고 답하지 않는다 + 다음 저장이 설정 칸을 다시 쓴다
_orig_sync = server.save_data_sync
def _fail_initial(new_data, is_initial=False, _retry=True):
    if is_initial:
        raise RuntimeError('일부러 낸 저장 실패')
    return _orig_sync(new_data, is_initial, _retry)
server.save_data_sync = _fail_initial
r = c.post('/api/server/start_broadcast', json={'names': ['병']}, headers=H)
server.save_data_sync = _orig_sync
say(r.status_code == 500, '4) 전체 저장 실패 → 500', (r.status_code, r.get_json()))
say(kv('slot_price') is None, '4) (재현) 저장 실패 직후 DB 에서 설정 칸이 비어 있다', kv('slot_price'))
c.post('/api/settings/patch', json={'ticker_speed': 71}, headers=H)   # 아무 평소 저장
server.drain_db_writes()
say(kv('slot_price') == 33000, '4) 다음 평소 저장이 지워진 설정 칸을 다시 쓴다', kv('slot_price'))

# 7) 옛 스냅샷(새 칸 없음)으로 되돌려도 기본값이 채워진다
with server.get_db_connection() as conn:
    cur = conn.cursor()
    cur.execute('INSERT INTO snapshots (timestamp, state_json, summary) VALUES (?, ?, ?)',
                ('2026-01-01 00:00:00', json.dumps({'bjs': [{'name': '옛', 'score': 5, 'contribution': 5}]}), '옛 스냅샷'))
    sid = cur.lastrowid
r = c.post('/api/snapshots/restore', json={'id': sid}, headers=H)
st = server.load_data()
missing = [k for k in server.DEFAULT_STATE if k not in st]
say(r.status_code == 200 and not missing and st['bjs'][0]['name'] == '옛', '7) 옛 스냅샷 복원 뒤 빠진 칸이 없다', (r.status_code, missing[:5]))
r2 = c.get('/api/data', headers=H)
say(r2.status_code == 200, '7) 복원 뒤 상태 읽기 정상', r2.status_code)
'''

src = os.environ.get('LM_SANDBOX_DIR')
if src and os.path.isdir(src):
    print('\n4·5·7) 실패 경로 (프로세스 안, 새 임시 DB)')
    tmp = tempfile.mkdtemp(prefix='fixsrv_')
    try:
        for f in ('server.py', 'show.py'):
            shutil.copy(os.path.join(src, f), tmp)
        shutil.copytree(os.path.join(src, 'features'), os.path.join(tmp, 'features'))
        with open(os.path.join(tmp, '_inproc.py'), 'w', encoding='utf-8') as fh:
            fh.write(INPROC)
        env = dict(os.environ, PYTHONIOENCODING='utf-8')
        env.pop('DATABASE_URL', None)
        p = subprocess.run([sys.executable, '_inproc.py'], cwd=tmp, capture_output=True, timeout=300, env=env)
        out = p.stdout.decode('utf-8', 'replace')
        for ln in out.splitlines():
            if ln.startswith('OK '):
                chk(ln[3:].split(' -- ')[0], True)
            elif ln.startswith('BAD '):
                chk(ln[4:].split(' -- ')[0], False, ln.split(' -- ', 1)[1] if ' -- ' in ln else '')
        if p.returncode != 0 or not any(ln.startswith(('OK ', 'BAD ')) for ln in out.splitlines()):
            chk('프로세스 안 검사가 끝까지 돌았다', False, p.stderr.decode('utf-8', 'replace')[-600:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
else:
    print('\n(LM_SANDBOX_DIR 가 없어 4·5·7 실패 경로 검사는 건너뜁니다)')

print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
sys.exit(1 if BAD else 0)
