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

# ── 📱 폰 앱 받기(로그인 없이) ──
apk = open(os.path.join('bank-phone', 'dist', 'angel-bankphone.apk'), 'rb').read()
r = c.get('/download/bankphone.apk')
say(r.status_code == 200 and r.data == apk, '폰 앱은 로그인 없이 그대로 받아진다', (r.status_code, len(r.data), len(apk)))
say(r.headers.get('Content-Type', '').startswith('application/vnd.android.package-archive')
    and 'angel-bankphone-' in r.headers.get('Content-Disposition', ''), '안드로이드 앱 종류 · 판 번호 붙은 파일 이름으로', dict(r.headers))
say(c.get('/api/bank/app').status_code == 401, '판 번호 조회는 로그인해야')
d = c.get('/api/bank/app', headers=H).get_json()
say(d.get('ready') and d.get('version') == open(os.path.join('bank-phone', 'dist', 'version.txt'), encoding='utf-8').read().strip()
    and d.get('size') == len(apk), '조종실이 판 번호 · 크기를 본다', d)

# ── 🪞 조종실 거울 · 명령 (10-16) ──
state = {'v': '0.4.0', 'enabled': True, 'interval': 30, 'clicks': 12, 'lastOkAt': 1760000000000, 'startedAt': 1759990000000,
         'dateOk': True, 'status': '자동 조회 중 · 30초마다 · 다음 12초 뒤', 'cls': 'ok', 'dead': False, 'rows': 8,
         'found': [{'at': 1760000000000, 'when': '2026-10-14 17:08:40', 'dep': 20000, 'memo': '스트밍밍플러' + '가' * 60}] * 12,
         'log': ['17:08:52 새 입금 20,000원 스트밍밍플러'] * 10, 'secret_extra': 'x' * 500}
r = dep(K, [], note='자동 조회 12번', state=state)
say(r.status_code == 200 and r.get_json().get('cmds') == [], '상자 내용을 실어 보내면 받고, 기다리는 명령이 없으면 빈 목록', r.get_json())
say(c.get('/api/bank/ext').status_code == 401, '거울은 로그인해야 본다')
e = c.get('/api/bank/ext', headers=H).get_json()
w = e['link']['web']
say(w['age_sec'] < 5 and w['state']['status'].startswith('자동 조회 중') and w['state']['cls'] == 'ok' and w['state']['clicks'] == 12
    and w['state']['enabled'] is True, '조종실이 확장 상자 내용(상태 · 조회 횟수 · 켜짐)을 그대로 본다', w['state'])
say(len(w['state']['found']) == 8 and len(w['state']['found'][0]['memo']) == 40 and len(w['state']['log']) == 6
    and 'secret_extra' not in w['state'], '상자 내용은 찾은 입금 8건 · 메모 40자 · 기록 6줄까지만, 모르는 칸은 버린다',
    (len(w['state']['found']), len(w['state']['found'][0]['memo']), len(w['state']['log'])))
say(e.get('new') == len(inbox()['items']) and (e.get('newest') or {}).get('id') == inbox()['items'][0]['id'],
    '미처리 수와 가장 새 카드를 같이 준다(조종실 초록 띠 재료)', (e.get('new'), e.get('newest')))
say(c.post('/api/bank/ext/cmd', json={'t': 'press'}).status_code == 401, '명령 넣기는 로그인해야')
say(c.post('/api/bank/ext/cmd', json={'t': 'reboot'}, headers=H).status_code == 400, '모르는 명령은 400')
say(c.post('/api/bank/ext/cmd', json={'t': 'enable'}, headers=H).status_code == 400, '켜기/끄기는 on 이 있어야')
say(c.post('/api/bank/ext/cmd', json={'t': 'interval', 'sec': 45}, headers=H).status_code == 400, '간격은 20 · 30 · 60 만')
r1 = c.post('/api/bank/ext/cmd', json={'t': 'enable', 'on': False}, headers=H).get_json()
r2 = c.post('/api/bank/ext/cmd', json={'t': 'enable', 'on': True}, headers=H).get_json()
r3 = c.post('/api/bank/ext/cmd', json={'t': 'interval', 'sec': 60}, headers=H).get_json()
pend = r3.get('pending') or []
say([x['t'] for x in pend] == ['enable', 'interval'] and pend[0]['on'] is True and pend[1]['sec'] == 60,
    '같은 종류 명령은 마지막 것만 남고(끄기→켜기 = 켜기), 다른 종류는 같이 기다린다', pend)
say((c.get('/api/bank/ext', headers=H).get_json().get('pending') or {}).get('web') == pend, '거울이 기다리는 명령을 보여준다')
r = dep(K, [], note='자동 조회 13번', state=state).get_json()
say([x['t'] for x in r.get('cmds') or []] == ['enable', 'interval'], '확장의 다음 신호 답에 명령이 실려 간다', r.get('cmds'))
say(dep(K, [], state=state).get_json().get('cmds') == [] and not (c.get('/api/bank/ext', headers=H).get_json().get('pending') or {}).get('web'),
    '한 번 넘긴 명령은 지워진다(두 번 실행 안 됨)')
# 폰 쪽 명령은 폰 신호에만 간다
c.post('/api/bank/ext/cmd', json={'t': 'press', 'source': 'phone'}, headers=H)
say(dep(K, [], state=state).get_json().get('cmds') == [], '폰에 넣은 명령은 웹 확장 신호엔 안 실린다')

# 새 입금 신호는 로그인한 화면에만 · 이름 · 금액 없이
import queue as _q
qa, qn = _q.Queue(), _q.Queue()
qa._authed = True
qn._authed = False
with server.sse_lock:
    server.sse_clients.extend([qa, qn])
dep(K, [{'ref': 'r_sse', 'amount': 77000, 'fields': [['거래내용', '김비밀 밍밍 화이팅']]}])
with server.sse_lock:
    server.sse_clients.remove(qa); server.sse_clients.remove(qn)
msg = qa.get_nowait() if not qa.empty() else ''
say(msg.startswith('event: bank_inbox') and '"n": 1' in msg and '김비밀' not in msg and '77000' not in msg,
    '새 입금이 오면 로그인한 화면에 건수만 알린다(이름 · 금액 없음)', msg[:120])
say(qn.empty(), '방송판(무인증)에는 안 간다')

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
chk('입금 받는 길 · 폰 앱 받기만 로그인 없이 연다(exempt_routes)', "'/api/bank/deposit'," in SRV and "'/download/bankphone.apk'," in SRV
    and "'/api/bank/inbox'" not in SRV and "'/api/bank/app'" not in SRV)
CT = open(os.path.join(ROOT, 'controller.html'), encoding='utf-8').read()
chk('조종실 시스템 탭에 폰 앱 받기 칸 · QR', 'id="bankapp-box"' in CT and "location.href='/download/bankphone.apk'" in CT
    and '<script src="/vendor/qrious.min.js">' in CT and 'new QRious(' in CT and os.path.exists(os.path.join(ROOT, 'vendor', 'qrious.min.js')))
chk('기능을 등록한다(features.ai 뒤)', SRV.find('import features.bank_inbox') > SRV.find('import features.ai '))
chk('거울 · 명령 길은 로그인해야(exempt 에 없음)', "'/api/bank/ext'" not in SRV)
chk('조종실: 머리줄 신호등 칩 · 빨간/초록 띠 · 거울 칸 · 새 입금 신호 듣기',
    'id="bank-chip"' in CT and 'id="bank-band"' in CT and 'id="bank-new"' in CT and 'id="bankext-box"' in CT
    and "addEventListener('bank_inbox'" in CT and "fetch('/api/bank/ext/cmd'" in CT and "bankExtCmd('enable')" in CT)
_bkx = CT[CT.find('/* 🪞 은행 확장 거울'):CT.find("setInterval(() => { try { bankExtLoad(); } catch (e) {} }, 10000);")]
chk('조종실 계좌 알림은 화면만 — 소리를 안 낸다(대표님 10-16)', len(_bkx) > 2000 and 'new Audio(' not in _bkx and '.play(' not in _bkx, len(_bkx))
BW = open(os.path.join(ROOT, 'bank-watch', 'content.js'), encoding='utf-8').read()
BG = open(os.path.join(ROOT, 'bank-watch', 'background.js'), encoding='utf-8').read()
chk('확장 0.4: 신호에 상자 내용(state)을 싣고, 답의 명령(cmds)을 실행한다',
    "note: what, state }" in BW and 'applyCmds(res.cmds)' in BW and 'state: msg.state' in BG and 'cmds: Array.isArray(j.cmds)' in BG)
chk('확장 0.4: 자동 조회가 꺼져 있어도 살아 있음 신호를 보낸다(조종실에서 켤 수 있게)', 'function beat() { if (ui && Date.now() - lastBeat > 25000) sendDeps([]); }' in BW)
chk('입금 기록 · 열쇠 파일은 저장소에 안 올라간다', 'bank_inbox.json' in GI and 'bank_key.json' in GI)
MS = open(os.path.join(ROOT, 'manual_send.html'), encoding='utf-8').read()
chk('후원 콘솔: 계좌 입금에서 채운 송출은 그 입금 번호(manual_bank_)를 쓴다 — 두 번 눌러도 장부엔 한 번',
    "pick ? 'manual_bank_'+pick.id" in MS and 'tx_id:base+' in MS)
chk('후원 콘솔: 송출하면 추천 칸에 씀 표시', 'if(pick) bankMarkUsed(pick.id, name, pick.prevLedger);' in MS and 'async function bankMarkUsed' in MS)
# 10-14 눌러 보다 찾음: [채우기] 가 켠 '장부 기록' 이 송출 뒤에도 켜진 채 남아, 다음 '재생만' 송출이 진짜 후원으로 들어갔다
chk('후원 콘솔: [채우기] 전 장부 체크를 기억했다가 송출 · 비우기 · 숨기기 · 다른 화면 처리 뒤 되돌린다',
    "_bankPick={id:it.id, amount:it.amount, prevLedger};" in MS
    and "$('in-ledger').checked=!!prevLedger;" in MS
    and MS.count("$('in-ledger').checked=!!_bankPick.prevLedger") == 3, MS.count("$('in-ledger').checked=!!_bankPick.prevLedger"))
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
    shutil.copytree(os.path.join(ROOT, 'bank-phone', 'dist'), os.path.join(tmp, 'bank-phone', 'dist'))
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
