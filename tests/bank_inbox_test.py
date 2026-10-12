# -*- coding: utf-8 -*-
"""🏦 계좌 입금 추천(features/bank_inbox.py) — 은행 확장이 보낸 입금이 후원 콘솔 '추천' 카드가 되는가.

서버 사본을 새 임시 폴더에 복사해 프로세스 안(test_client)에서 확인한다. 운영 · 샌드박스 서버는 건드리지 않는다.
AI(NVIDIA) 키는 빼고 돌린다 — 배정 예상은 규칙(메시지에 선수 이름)으로만 나온다.

  · 열쇠: 로그인해야 받는다 · 틀린 열쇠 · 열쇠 없음은 401 · 새 열쇠를 만들면 옛 열쇠는 막힌다
  · 같은 입금(ref)은 한 번만 · 빈 목록은 '살아 있음' 신호 · 이상한 금액 · 모양은 거른다 · 1분 60번 넘으면 429
  · 메모 나누기(예전 닉네임 · 첫 낱말) · 메모 없이 보낸 입금은 금액 · 입금자명만 · 실명 칸은 메모와 따로
  · 배정 예상('밍밍 ＋?')은 요청 밖에서 붙는다 · 송출 · 숨김 · 되살림
  · 실명은 상태(load_data) · 방송판(/api/data 무인증)에 안 나간다 · 기록 파일은 .gitignore
"""
import os
import shutil
import subprocess
import sys
import tempfile

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get('LM_PROJECT_ROOT') or os.path.abspath(os.path.join(HERE, '..'))
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:200]) if detail else ''))


INPROC = r'''
import os, sys, json, time
sys.stdout.reconfigure(encoding='utf-8')
os.environ.update(HEADLESS='1', ADMIN_PASSWORD='sandboxpw', SESSION_SECRET='sandboxsecret123456', SELF_PING='off')
os.environ.pop('NVIDIA_API_KEY', None)
sys.path.insert(0, os.getcwd())
import server
server.init_db()
import features.bank_inbox as fb
c = server.app.test_client()
H = {'Authorization': 'Bearer sandboxsecret123456'}
def say(ok, name, detail=''):
    print(('OK ' if ok else 'BAD ') + name + ((' -- ' + str(detail)[:200]) if detail else ''), flush=True)

with server.file_lock:
    st = server.load_data()
    st['bjs'] = [{'name': '밍밍', 'score': 0}, {'name': '예지랑', 'score': 0}, {'name': '순자', 'score': 0}]
    st['extra_game_active'] = False
    server.save_data(st)
server.remember_assignment('영원', '밍밍', 50000, '밍밍 화이팅')

def dep(key, deps, **kw):
    hdr = {'X-Bank-Key': key} if key is not None else {}
    return c.post('/api/bank/deposit', json=dict(source='web', deposits=deps, **kw), headers=hdr)

def inbox():
    return c.get('/api/bank/inbox', headers=H).get_json()

# ── 열쇠 ──
r = dep(None, [])
say(r.status_code == 401, '열쇠를 아직 안 만들었으면 401', r.status_code)
r = c.get('/api/bank/key')
say(r.status_code == 401, '열쇠는 로그인해야 받는다', r.status_code)
K = c.get('/api/bank/key', headers=H).get_json()['key']
say(len(K) == 32, '로그인하면 열쇠를 만들어 준다', K[:4])
say(c.get('/api/bank/key', headers=H).get_json()['key'] == K, '다시 물어도 같은 열쇠')
r = dep('x' * 32, [])
say(r.status_code == 401 and r.get_json().get('bad_key'), '틀린 열쇠는 401', r.status_code)
r = dep(K, [], note='조회 12번 · 표 찾음')
say(r.status_code == 200 and r.get_json()['added'] == 0, '빈 목록 = 살아 있음 신호', r.get_json())
r = c.get('/api/bank/inbox')
say(r.status_code == 401, '추천 목록은 로그인해야 본다', r.status_code)
b = inbox()
say(b['link'].get('web', {}).get('age_sec', 99) < 5 and b['link']['web']['note'] == '조회 12번 · 표 찾음',
    '후원 콘솔이 확장 연결 상태(몇 초 전 · 메모)를 본다', b['link'])

# ── 입금 ──
D1 = {'ref': 'r1', 'amount': 50000, 'when': '2026.10.14 19:01:02',
      'fields': [['거래내용', '영원밍밍화이팅'], ['상대계좌예금주명', '김진짜']]}
D2 = {'ref': 'r2', 'amount': 30000, 'when': '2026.10.14 19:02:00', 'fields': [['거래내용', '홍길동'], ['상대계좌예금주명', '홍길동']]}
D3 = {'ref': 'r3', 'amount': 10000, 'when': '2026.10.14 19:03:00', 'fields': {'입금자명': '새손님 순자 최고'}}
r = dep(K, [D1, D2, D3])
say(r.get_json().get('added') == 3, '입금 세 건이 추천 칸에 올라간다', r.get_json())
r = dep(K, [D1])
say(r.get_json().get('added') == 0, '같은 입금(ref)은 다시 안 올라간다', r.get_json())
bad = [{'ref': 'x1', 'amount': 0}, {'ref': 'x2', 'amount': '많이'}, {'ref': 'x3', 'amount': -5},
       {'ref': 'x4', 'amount': 10 ** 9}, {'amount': 1000}, '문자열', None]
r = dep(K, bad)
say(r.get_json().get('added') == 0, '이상한 금액 · ref 없는 줄은 거른다', r.get_json())
r = c.post('/api/bank/deposit', json={'deposits': {'a': 1}}, headers={'X-Bank-Key': K})
say(r.status_code == 400, '목록이 아니면 400', r.status_code)
r = c.post('/api/bank/deposit', json={'deposits': [{}] * 31}, headers={'X-Bank-Key': K})
say(r.status_code == 400, '한 번에 30건 넘으면 400', r.status_code)

items = {i['amount']: i for i in inbox()['items']}
a = items.get(50000, {})
say(a.get('name') == '영원' and a.get('message') == '밍밍화이팅' and a.get('how') == 'known' and a.get('sure'),
    '붙여 쓴 메모도 예전 닉네임으로 나눈다(영원 / 밍밍화이팅)', a)
say(a.get('memo') == '영원밍밍화이팅' and a.get('holder') == '김진짜', '메모 칸과 실명 칸을 따로 둔다', (a.get('memo'), a.get('holder')))
h = items.get(30000, {})
say(h.get('how') == 'no_memo' and h.get('name') == '홍길동' and h.get('message') == '',
    '메모 없이 보낸 입금은 금액 · 입금자명만', h)
n = items.get(10000, {})
say(n.get('name') == '새손님' and n.get('message') == '순자 최고' and n.get('how') == 'first' and not n.get('sure'),
    '처음 보는 닉네임은 첫 낱말 추천(확실하지 않음)', n)
order = [i['amount'] for i in inbox()['items']]
say(order == [10000, 30000, 50000], '최근 것이 위', order)

# 배정 예상은 요청 밖(스레드)에서 붙는다
for _ in range(60):
    items = {i['amount']: i for i in inbox()['items']}
    if all(i.get('ai') == 'done' for i in items.values()):
        break
    time.sleep(0.1)
say(all(i.get('ai') == 'done' for i in items.values()), '배정 예상이 끝났다', [i.get('ai') for i in items.values()])
say(items[50000].get('target') == '밍밍', '영원밍밍화이팅 → 밍밍 ＋ 예상', items[50000].get('target'))
say(items[10000].get('target') == '순자', '새손님 순자 최고 → 순자 ＋ 예상', items[10000].get('target'))
say(not items[30000].get('target'), '메시지 없는 입금은 예상 안 함', items[30000].get('target'))

# ── 실명은 바깥으로 안 나간다 ──
pub = c.get('/api/data').get_data(as_text=True)
say('김진짜' not in pub and '영원밍밍' not in pub, '방송판(무인증 /api/data)에 입금 · 실명이 없다')
with server.file_lock:
    st = server.load_data()
say('김진짜' not in json.dumps(st, ensure_ascii=False), '서버 상태(load_data)에도 넣지 않는다')
raw = open(fb.BANK_INBOX_FILE, encoding='utf-8').read()
say('김진짜' in raw and os.path.dirname(fb.BANK_INBOX_FILE) == server.BASE_DIR, '기록은 서버 폴더 bank_inbox.json 에만')

# ── 송출 · 숨김 · 되살림 ──
iid = items[50000]['id']
r = c.post('/api/bank/inbox/%s/used' % iid, json={'name': '영원'})
say(r.status_code == 401, '송출 표시는 로그인해야', r.status_code)
r = c.post('/api/bank/inbox/%s/used' % iid, json={'name': '영원'}, headers=H)
say(r.status_code == 200 and iid not in [i['id'] for i in inbox()['items']], '송출하면 추천 칸에서 빠진다')
iid2 = items[30000]['id']
c.post('/api/bank/inbox/%s/dismiss' % iid2, headers=H)
b = inbox()
say(iid2 not in [i['id'] for i in b['items']] and iid2 in [i['id'] for i in b['hidden']], '숨기면 숨긴 목록으로')
c.post('/api/bank/inbox/%s/restore' % iid2, headers=H)
say(iid2 in [i['id'] for i in inbox()['items']], '되살리면 다시 추천 칸으로')
r = c.post('/api/bank/inbox/%s/eat' % iid2, headers=H)
say(r.status_code == 400, '모르는 동작은 400', r.status_code)
r = c.post('/api/bank/inbox/nope/used', headers=H)
say(r.status_code == 404, '없는 입금은 404', r.status_code)

# 송출할 때 쓴 이름은 바로 기억 — 같은 방송에서 '새손님…' 이 다시 오면 확실한 닉네임
c.post('/api/bank/inbox/%s/used' % items[10000]['id'], json={'name': '새손님'}, headers=H)
dep(K, [{'ref': 'r9', 'amount': 20000, 'fields': [['거래내용', '새손님예지랑화이팅']]}])
n2 = next(i for i in inbox()['items'] if i['amount'] == 20000)
say(n2.get('name') == '새손님' and n2.get('how') == 'known', '방금 송출한 닉네임은 다음 입금에서 알아본다', n2)

# ── 새 열쇠 · 너무 잦은 신호 ──
K2 = c.post('/api/bank/key/reset', headers=H).get_json()['key']
say(K2 != K and dep(K, []).status_code == 401 and dep(K2, []).status_code == 200, '새 열쇠를 만들면 옛 열쇠는 막힌다')
fb._posts.clear()
codes = [dep(K2, []).status_code for _ in range(61)]
say(codes[:60].count(200) == 60 and codes[60] == 429, '1분에 60번 넘게 보내면 429', codes[-3:])
'''

print('=' * 74)
print('🏦 계좌 입금 추천 /api/bank/*')
print('=' * 74)
SRV = open(os.path.join(ROOT, 'server.py'), encoding='utf-8').read()
GI = open(os.path.join(ROOT, '.gitignore'), encoding='utf-8').read()
chk('입금 받는 길만 로그인 없이 연다(exempt_routes)', "'/api/bank/deposit'," in SRV and "'/api/bank/inbox'" not in SRV)
chk('기능을 등록한다(features.ai 뒤)', SRV.find('import features.bank_inbox') > SRV.find('import features.ai '))
chk('입금 기록 · 열쇠 파일은 저장소에 안 올라간다', 'bank_inbox.json' in GI and 'bank_key.json' in GI)
MS = open(os.path.join(ROOT, 'manual_send.html'), encoding='utf-8').read()
chk('후원 콘솔: 계좌 입금에서 채운 송출은 그 입금 번호(manual_bank_)를 쓴다 — 두 번 눌러도 장부엔 한 번',
    "pick ? 'manual_bank_'+pick.id" in MS and 'tx_id:base+' in MS)
chk('후원 콘솔: 송출하면 추천 칸에 씀 표시', 'if(pick) bankMarkUsed(pick.id, name);' in MS and 'async function bankMarkUsed' in MS)
chk('후원 콘솔: 목록은 내용이 바뀔 때만 다시 그린다(누르는 중에 단추가 안 바뀌게)',
    'JSON.stringify([BANK.items,BANK.hidden,_bankPick&&_bankPick.id])' in MS)
chk('후원 콘솔: 송출은 [채우기] 뒤 사람이 누른다 — 추천 칸이 스스로 /api/donation 을 부르지 않는다',
    MS.count("fetch('/api/donation'") == 0 and "endpoint = ledger ? '/api/donation'" in MS)

tmp = tempfile.mkdtemp(prefix='bankinbox_')
try:
    for f in ('server.py', 'show.py'):
        shutil.copy(os.path.join(ROOT, f), tmp)
    shutil.copytree(os.path.join(ROOT, 'features'), os.path.join(tmp, 'features'),
                    ignore=shutil.ignore_patterns('__pycache__'))
    with open(os.path.join(tmp, '_inproc.py'), 'w', encoding='utf-8') as fh:
        fh.write(INPROC)
    env = dict(os.environ, PYTHONIOENCODING='utf-8')
    for k in ('DATABASE_URL', 'NVIDIA_API_KEY'):
        env.pop(k, None)
    p = subprocess.run([sys.executable, '_inproc.py'], cwd=tmp, capture_output=True, timeout=300, env=env)
    out = p.stdout.decode('utf-8', 'replace')
    for ln in out.splitlines():
        if ln.startswith('OK '):
            chk(ln[3:].split(' -- ')[0], True)
        elif ln.startswith('BAD '):
            chk(ln[4:].split(' -- ')[0], False, ln.split(' -- ', 1)[1] if ' -- ' in ln else '')
    if p.returncode != 0 or not any(ln.startswith(('OK ', 'BAD ')) for ln in out.splitlines()):
        chk('프로세스 안 검사가 끝까지 돌았다', False, p.stderr.decode('utf-8', 'replace')[-1200:])
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
sys.exit(1 if BAD else 0)
