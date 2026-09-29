# -*- coding: utf-8 -*-
"""🧮 점수 조작 고친 것 (2026-09-30 감사) — 폰 · 조종실 점수 길이 정말 그렇게 하는가.

번호는 감사 보고의 번호와 같다.
  1. 폰에서 기여도 카드(슬롯 당첨 · 주사위 시그)를 배정하면 기여도가 들어간다
     (예전: delta=manWon(0)=0 만 보내 기여도 0 · 카드는 사라짐) + 서버 안전장치
  2. 조종실에서 기여도 카드 배정을 되돌리면 기여도가 빠지고 장부 줄도 지워진다
  3. 되돌리기 — 서버 실패를 확인해 되살린다 · 연타해도 한 건만 · 원래 명단(list)에서 뺀다
  4. 이름 고치기 · 빼기 · 기여도 고치기는 '그린 순간의 이름' 으로만 사람을 찾는다
  5. 다른 탭이 방송을 끝낸 뒤 '서버 초기화 감지 → 복구?' 로 새 방송을 덮어쓰지 않는다
  6. 점수 칸 "1.5" 가 15 가 되지 않는다

⚠️ 조종실 함수는 베끼지 않는다 — controller.html 에서 **그 함수 본문을 그대로 잘라** node 로 돌리고,
   점수는 살아 있는 시험 서버로 보낸다(검사 도구는 실물과 같아야 한다).
돌리는 법: 시험 서버를 띄우고  LM_PT_PORT=5313 python tests/fix_client_test.py
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:%s' % os.environ.get('LM_PT_PORT', '5199')
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:160]) if detail else ''))


def post(path, obj=None):
    req = urllib.request.Request(B + path, json.dumps(obj or {}).encode(), H)
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def get():
    with urllib.request.urlopen(urllib.request.Request(B + '/api/data', headers=H), timeout=25) as r:
        return json.loads(r.read().decode())


def row(name, key='bjs'):
    return next((b for b in (get().get(key) or []) if b.get('name') == name), None)


def reset(names=('가', '나', '다'), **extra):
    body = {'broadcast_active': True, 'extra_game_active': False, 'extra_bjs': [],
            'pending_donations': [], 'logs': [], 'match_logs': [],
            'bjs': [{'name': n, 'score': 0, 'contribution': 0} for n in names]}
    body.update(extra)
    post('/api/restore', body)


def card(cid, contrib, name='🎰 슬롯 당첨'):
    return {'id': cid, 'name': name, 'orig_name': '주사위게임', 'amount': 0, 'message': '시험',
            'time': '01:00', 'kind': 'contrib', 'contrib': contrib}


def _proj():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(4):
        if os.path.exists(os.path.join(d, 'controller.html')):
            return d
        d = os.path.dirname(d)
    return os.environ.get('LM_ROOT') or os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


PROJ = _proj()
CTL = io.open(os.path.join(PROJ, 'controller.html'), encoding='utf-8', errors='replace').read()
MOB = io.open(os.path.join(PROJ, 'mobile.html'), encoding='utf-8', errors='replace').read()


def cut(src, start, end):
    """src 에서 start 가 처음 나오는 곳부터 end 직전까지 — 함수 본문을 그대로 잘라 온다."""
    i = src.index(start)
    j = src.index(end, i)
    return src[i:j]


def node(js):
    """node 로 돌려 마지막 줄(JSON)을 돌려준다."""
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(js)
        path = f.name
    try:
        p = subprocess.run(['node', path], capture_output=True, text=True, encoding='utf-8', timeout=60)
    finally:
        os.unlink(path)
    out = (p.stdout or '').strip().splitlines()
    if p.returncode != 0 or not out:
        return {'_err': (p.stderr or '')[-600:]}
    return json.loads(out[-1])


print('=' * 74)
print('1. 폰에서 기여도 카드를 배정하면 기여도가 들어간다')
print('=' * 74)
# 서버 안전장치 — 낡은 폰 화면이 예전 모양(delta 0 · contribution 없음)으로 보내도 잃지 않는다
reset(pending_donations=[card('dg_old1', 7)])
code, r = post('/api/score/add', {'scope': 'rank', 'name': '가', 'delta': 0, 'pending_id': 'dg_old1',
                                  'popup': True, 'takeover': True, 'donor': '🎰 슬롯 당첨'})
g = row('가')
chk('예전 폰 모양으로 보내도 카드의 기여도 7 이 들어간다', code == 200 and g and g['contribution'] == 7, (code, g))
chk('점수(일당)는 한 점도 안 오른다', g and g['score'] == 0, g)
chk('카드는 대기함에서 빠진다', not [d for d in get()['pending_donations'] if d.get('id') == 'dg_old1'])
chk('장부에는 기여도 줄로 남는다',
    any(l.get('name') == '가' and l.get('val') == 7 and l.get('kind') == 'contrib' for l in get().get('logs') or []),
    (get().get('logs') or [])[:2])
# 기여도를 직접 보냈으면 그 값을 쓴다(서버가 멋대로 바꾸지 않는다)
reset(pending_donations=[card('dg_new1', 7)])
post('/api/score/add', {'scope': 'rank', 'name': '나', 'delta': 0, 'contribution': 3, 'pending_id': 'dg_new1'})
chk('기여도를 보냈으면 그 값(3)을 쓴다', (row('나') or {}).get('contribution') == 3, row('나'))
# 일반 후원은 예전 그대로 — 점수와 기여도가 같이 오른다
reset(pending_donations=[{'id': 'p_norm', 'name': '후원자', 'amount': 50000, 'message': '', 'time': '01:00'}])
post('/api/score/add', {'scope': 'rank', 'name': '다', 'delta': 5, 'pending_id': 'p_norm'})
chk('일반 후원은 그대로 (점수 5 · 기여도 5)', (row('다') or {}).get('score') == 5 and row('다')['contribution'] == 5, row('다'))

# 폰 assign() 을 그대로 잘라 돌린다 — 무엇을 보내는가
_assign = cut(MOB, 'async function assign(donId, name) {', '// 후원 한 건을 n 명에게 나눌 때')
_manwon = cut(MOB, 'function manWon(amount) {', 'function splitPoints')
res = node(r"""
let busy = false, sent = [], banners = [];
const gd = { pending_donations: [ %s ], bjs: [{name:'가', score:0, contribution:0}] };
const players = () => gd.bjs;
const addScore = async p => { sent.push(p); return { status:'success', time:'01:02:03' }; };
const renderApp = () => {}, renderHome = () => {}, toast = () => {};
const undoBanner = (t, u) => banners.push([t, u]);
%s
%s
(async () => { await assign('dg_m1', '가'); console.log(JSON.stringify({ sent, banners })); })();
""" % (json.dumps(card('dg_m1', 4)), _manwon, _assign))
s0 = (res.get('sent') or [{}])[0]
chk('폰: 기여도 카드는 delta 0 · contribution 4 로 보낸다', s0.get('delta') == 0 and s0.get('contribution') == 4
    and s0.get('pending_id') == 'dg_m1', res)
chk('폰: 되돌리기 배너가 기여도를 안다', (res.get('banners') or [[None, {}]])[0][1].get('contrib') == 4, res.get('banners'))
chk('폰: 대기함 카드에 "0원" 대신 기여도가 보인다', "? '기여도 ' + won(d.contrib) : won(d.amount) + '원'" in MOB)
# 폰 되돌리기 배너가 보내는 것 — 기여도 카드는 기여도를 빼고 장부 줄(val=기여도)을 지운다
_ub = cut(MOB, 'function undoBanner(text, u) {', '/* ═══ 🏆 점수판 ═══ */')
res = node(r"""
let sent = [];
const addScore = async p => { sent.push(p); return {}; };
const toast = () => {};
const banner = (i, t, s, bg, onTap) => { banner.tap = onTap; };
%s
(async () => { undoBanner('x', { name:'가', pts:0, contrib:4, isC:true, time:'01:02:03', list:'main' });
               await banner.tap(); console.log(JSON.stringify(sent)); })();
""" % _ub)
u0 = (res if isinstance(res, list) else [{}])[0]
chk('폰 되돌리기: contribution -4 · undo_log val 4 · list main', u0.get('contribution') == -4 and u0.get('delta') == 0
    and (u0.get('undo_log') or {}).get('val') == 4 and u0.get('list') == 'main', res)

print()
print('=' * 74)
print('2 · 3. 조종실 되돌리기 — 실제 함수를 잘라 살아 있는 서버로')
print('=' * 74)
_undo = cut(CTL, '// ===== ↩ 점수 되돌리기(undo) =====', 'function clearLogs(type)')
_parse = cut(CTL, 'function parseIntStrict(v) {', 'async function addScoreEl(scope, el) {')
HARNESS = r"""
const B = %s, AUTH = 'Bearer sandboxsecret123456';
let gd = null, toasts = [], sentLog = [], FAIL = false;
const document = { getElementById: () => null };
const requestAnimationFrame = f => 0;
const escapeHTML = s => String(s), escapeHtml = s => String(s);
const renderUI = () => {};
const acctToast = (m, k) => toasts.push([m, k]);
async function addScoreAPI(payload) {
    sentLog.push(payload);
    if (FAIL) return null;
    const res = await fetch(B + '/api/score/add', { method:'POST',
        headers: { 'Content-Type':'application/json', 'Authorization': AUTH }, body: JSON.stringify(payload) });
    if (!res.ok) return null;
    return await res.json();
}
async function pull() { const r = await fetch(B + '/api/data', { headers: { 'Authorization': AUTH } }); gd = await r.json(); }
%s
%s
""" % (json.dumps(B), _undo, _parse)

# ② 기여도 카드 배정 → 되돌리기
reset(pending_donations=[card('dg_c2', 6)])
res = node(HARNESS + r"""
(async () => {
  await pull();
  // 조종실 assignPending 이 보내는 그대로
  const r = await addScoreAPI({ scope:'rank', name:'가', popup:true, takeover:true, delta:0, contribution:6, pending_id:'dg_c2' });
  await pull();
  // ⚠️ 복사해 둔다 — 되돌리기가 화면용 gd 를 제자리에서 고치므로, 참조로 들고 있으면 같이 바뀐다
  const after = JSON.parse(JSON.stringify(gd.bjs.find(b => b.name === '가')));
  recordScoreAction({ scope:'rank', name:'가', delta:0, contrib:6, isExtra:false, addedContrib:true, logTime:r.time });
  await undoScoreById(lastScoreActions[0].uid);
  await pull();
  console.log(JSON.stringify({ after, back: gd.bjs.find(b => b.name === '가'), logs: gd.logs, sent: sentLog[1], left: lastScoreActions.length }));
})();
""")
chk('배정: 기여도 6 · 점수 0', (res.get('after') or {}).get('contribution') == 6 and res['after'].get('score') == 0, res)
chk('되돌리기: 기여도 0 으로 돌아온다', (res.get('back') or {}).get('contribution') == 0, res.get('back'))
chk('되돌리기: 장부의 기여도 줄도 지워진다', not [l for l in res.get('logs') or [] if l.get('name') == '가'], res.get('logs'))
chk('되돌리기: contribution -6 · list main 을 보낸다', (res.get('sent') or {}).get('contribution') == -6
    and res['sent'].get('list') == 'main', res.get('sent'))

# ③-a 연타 — 같은 줄을 두 번 눌러도 한 건만 취소된다(옆 기록은 그대로)
reset()
res = node(HARNESS + r"""
(async () => {
  await pull();
  for (const [nm, d] of [['가', 3], ['나', 5]]) {
    const r = await addScoreAPI({ scope:'rank', name:nm, delta:d });
    recordScoreAction({ scope:'rank', name:nm, delta:d, contrib:d, isExtra:false, addedContrib:true, logTime:r.time });
  }
  await pull();
  const uid = lastScoreActions[0].uid;            // '가 +3' 줄
  await Promise.all([undoScoreById(uid), undoScoreById(uid)]);   // 연타
  await pull();
  console.log(JSON.stringify({ bjs: gd.bjs, left: lastScoreActions.map(a => a.name), n: sentLog.length }));
})();
""")
sc = {b['name']: b['score'] for b in res.get('bjs') or []}
chk('연타: 가 는 한 번만 빠진다 (0)', sc.get('가') == 0, sc)
chk('연타: 옆 기록(나 +5)은 그대로', sc.get('나') == 5 and res.get('left') == ['나'], res)
chk('연타: 서버로 되돌리기는 한 번만 갔다', res.get('n') == 3, res.get('n'))

# ③-b 서버 실패 — 기록이 되살아나고 경고가 뜬다
reset()
res = node(HARNESS + r"""
(async () => {
  await pull();
  const r = await addScoreAPI({ scope:'rank', name:'가', delta:4 });
  await pull();
  recordScoreAction({ scope:'rank', name:'가', delta:4, contrib:4, isExtra:false, addedContrib:true, logTime:r.time });
  FAIL = true;
  await undoScoreById(lastScoreActions[0].uid);
  const local = gd.bjs.find(b => b.name === '가');
  console.log(JSON.stringify({ left: lastScoreActions.length, toasts, local }));
})();
""")
chk('실패: 되돌리기 기록이 되살아난다(다시 누를 수 있다)', res.get('left') == 1, res)
chk('실패: 경고가 뜬다', any(k == 'warn' for _, k in res.get('toasts') or []), res.get('toasts'))
chk('실패: 화면 점수도 도로 4', (res.get('local') or {}).get('score') == 4, res.get('local'))
chk('실패: 서버 점수는 그대로 4', (row('가') or {}).get('score') == 4, row('가'))

# ③-c 원래 명단 — 번외 게임 중 준 점수를 번외가 끝난 뒤 되돌린다(본 명단에 같은 이름이 있다)
reset(names=('가', '나'))
post('/api/data', {'extra_game_active': True, 'extra_bjs': [{'name': '가', 'score': 0, 'contribution': 0}]})
res = node(HARNESS + r"""
(async () => {
  await pull();
  const r = await addScoreAPI({ scope:'rank', name:'가', delta:2 });
  recordScoreAction({ scope:'rank', name:'가', delta:2, contrib:2, isExtra:true, addedContrib:true, logTime:r.time });
  await fetch(B + '/api/data', { method:'POST', headers:{ 'Content-Type':'application/json', 'Authorization':AUTH },
                                 body: JSON.stringify({ extra_game_active:false }) });
  await pull();
  await undoScoreById(lastScoreActions[0].uid);
  await pull();
  console.log(JSON.stringify({ main: gd.bjs.find(b => b.name === '가'), extra: gd.extra_bjs.find(b => b.name === '가'), sent: sentLog[1] }));
})();
""")
chk('번외 명단 사람에게서 빠진다 (0)', (res.get('extra') or {}).get('score') == 0, res)
chk('본 명단 같은 이름은 안 건드린다 (0 그대로)', (res.get('main') or {}).get('score') == 0, res.get('main'))
code, r = post('/api/score/add', {'scope': 'rank', 'name': '가', 'delta': 1, 'list': 'bogus'})
chk('모르는 list 값은 400', code == 400, (code, r))
code, _ = post('/api/score/add', {'scope': 'rank', 'name': '가', 'delta': 1, 'list': 'main'})
chk('list 없이 / main 은 예전처럼 들어간다', code == 200 and (row('가') or {}).get('score') == 1, row('가'))

print()
print('=' * 74)
print('4. 줄 번호가 아니라 그린 순간의 이름으로')
print('=' * 74)
_rk = cut(CTL, 'var _rkRowNames', 'function renderUI() {')
res = node(r"""
let pushed = 0, toasts = [], asked = [];
let gd = { bjs: [{name:'가', score:0, contribution:0}, {name:'나', score:3, contribution:3}] };
const pushAPI = () => { pushed++; };
const acctToast = (m, k) => toasts.push(m);
const rkDiceGuard = async () => true;
let ANSWER = true;
const premiumConfirm = async (m) => { asked.push(m); return ANSWER; };
%s
(async () => {
  _rkRowNames = { key:'bjs', names:['가', '나'] };             // 그린 순간: 0번 가, 1번 나
  gd.bjs = [{name:'나', score:3, contribution:3}, {name:'가', score:0, contribution:0}];   // 그 사이 순서가 바뀜
  const el = { dataset:{ tname:'가' }, value:'가나다' };        // 0번 줄(가)의 이름칸을 고쳤다
  await rkRename('bjs', 0, el);
  const renamed = gd.bjs.map(b => b.name);
  ANSWER = false;
  await rkRemove('bjs', 1);                                     // 1번 줄 = 나 (점수 있음) → 묻는다 → 취소
  const afterNo = gd.bjs.map(b => b.name);
  ANSWER = true;
  await rkRemove('bjs', 1);
  console.log(JSON.stringify({ renamed, afterNo, after: gd.bjs.map(b => b.name), asked: asked.length }));
})();
""" % _rk)
chk('이름 고치기: 순서가 바뀌어도 가 의 이름만 바뀐다', res.get('renamed') == ['나', '가나다'], res)
chk('빼기: 점수·기여도가 있으면 먼저 묻고, 취소하면 그대로', res.get('afterNo') == ['나', '가나다'] and res.get('asked', 0) >= 1, res)
chk('빼기: 순서가 바뀌어도 그린 순간의 1번(나)이 빠진다', res.get('after') == ['가나다'], res)
chk('dice_fix_test 가 보는 손잡이 모양은 그대로',
    CTL.count("onchange=\"rkRename('${listKey}', ${i}, this)\"") == 2 and CTL.count("onclick=\"rkRemove('${listKey}', ${i})\"") == 2)
_cc = cut(CTL, 'function contribPopName() {', 'function cancelContribEdit() {')
res = node(r"""
let sent = [];
let gd = { bjs: [{name:'가', contribution:10}, {name:'나', contribution:5}] };
const POP = { dataset:{ tname:'나' } }, INP = { value:'8' };
const document = { getElementById: id => id === 'contrib-popover' ? POP : (id === 'edit-contrib-popover-input' ? INP : null) };
const renderUI = () => {}, cancelContribEdit = () => {}, acctToast = () => {};
const premiumConfirm = async () => true, premiumAlert = async () => {};
const addScoreAPI = async p => { sent.push(p); return { status:'success' }; };
%s
%s
(async () => {
  gd.bjs = [{name:'나', contribution:5}, {name:'가', contribution:10}];   // 팝오버를 연 뒤 순서가 바뀜(idx 1 = 가)
  await confirmContribChange(1);
  INP.value = '1.5';
  await confirmContribChange(1);
  console.log(JSON.stringify({ sent, bjs: gd.bjs }));
})();
""" % (_parse, _cc))
chk('기여도 고치기: 팝오버를 연 사람(나)에게 +3 이 간다', (res.get('sent') or [{}])[0].get('name') == '나'
    and res['sent'][0].get('contribution') == 3, res)
chk('기여도 고치기: "1.5" 는 보내지 않는다', len(res.get('sent') or []) == 1, res.get('sent'))

print()
print('=' * 74)
print('5. 다른 탭이 방송을 끝낸 뒤 옛 백업으로 새 방송을 덮어쓰지 않는다')
print('=' * 74)
_rv = cut(CTL, 'function restoreVerdict(serverState, startedAt) {', 'function startAutoBackupInterval() {')
post('/api/server/start_broadcast', {'names': ['가', '나']})
s1 = get()
t1 = int(s1.get('broadcast_started_at') or 0)
chk('방송 시작 시각이 상태에 실린다', s1.get('broadcast_active') and t1 > 0, t1)
post('/api/server/end_broadcast', {})
s2 = get()
chk('방송 종료 뒤에도 시작 시각이 남는다(판단의 근거)', not s2.get('broadcast_active')
    and int(s2.get('broadcast_started_at') or 0) == t1, s2.get('broadcast_started_at'))
res = node(_rv + r"""
console.log(JSON.stringify({
  ended: restoreVerdict(%s, %d),
  live:  restoreVerdict({ broadcast_active:true, broadcast_started_at:%d }, %d),
  other: restoreVerdict({ broadcast_active:false, broadcast_started_at:%d }, %d),
  reset: restoreVerdict({ broadcast_active:false, broadcast_started_at:0 }, %d),
  old:   restoreVerdict(%s, 0) }));
""" % (json.dumps(s2), t1, t1 + 5000, t1, t1 + 5000, t1, t1, json.dumps(s2)))
chk('같은 방송이 서버에서 끝났으면 복구 안 함(ended)', res.get('ended') == 'ended', res)
chk('서버가 방송 중이면 복구 안 함(live)', res.get('live') == 'live', res)
chk('다른 방송이 있었으면 복구 안 함(other)', res.get('other') == 'other', res)
chk('서버 기록이 0(진짜 초기화)일 때만 복구를 묻는다(ok)', res.get('reset') == 'ok', res)
chk('시작 시각 없는 옛 백업도 끝난 방송이면 안 묻는다', res.get('old') == 'ended', res)
_hs = cut(CTL, "premiumConfirm(msg, \"서버 재기동/초기화 감지\"", "let res = await fetch('/api/restore'")
chk('[확인] 순간 서버 상태를 다시 받아 판단한다', "fetch('/api/data'" in _hs and 'restoreVerdict(cur' in _hs)
chk('백업에 시작 시각을 같이 적는다', "localStorage.setItem('active_broadcast_backup_started'" in CTL)

print()
print('=' * 74)
print('6. 점수 칸 — 정수만')
print('=' * 74)
res = node(_parse + r"""
console.log(JSON.stringify(['1.5', '1-2', '-3', '+7', '1,000', '', ' 12 ', 'abc'].map(v => {
  const n = parseIntStrict(v); return isNaN(n) ? null : n; })));
""")
chk('"1.5"·"1-2"·"abc"·"" 는 거절, "-3"·"+7"·"1,000"·" 12 " 는 정수', res == [None, None, -3, 7, 1000, None, 12, None], res)
chk('점수 칸이 새 읽기를 쓴다', 'let val = parseIntStrict(rawTxt);' in CTL
    and "parseInt(String(el.value).replace(/[^\\d-]/g, ''))" not in CTL)
chk('폰 대결 patch 주석이 "한 사람만 만지는 값" 이라고 우기지 않는다', '한 사람(운영자)만 만지는 값이라' not in MOB)

reset()
print()
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for b in BAD:
    print('   실패:', b)
sys.exit(1 if BAD else 0)
