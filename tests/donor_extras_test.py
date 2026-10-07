# -*- coding: utf-8 -*-
"""🏷️ 서버 — 칭호 · 레벨 · VIP · 번호표를 받아 싣고, 다시 보기 · 테스트는 화면에만(2026-10-08).

 ① 보통 후원: 대기함엔 칭호 · 레벨 · VIP · 번호표, 방송판(로그인 없음)엔 칭호 · 레벨만 — ⭐ 번호표는 밖으로 안 나간다
 ② 다시 보기 · 후원 테스트: 대기함 · 정산 장부에 안 들어간다(예전엔 80만 원 다시 보기가 장부에 또 적혔다)
 ③ 이상한 값(색 · 그림 주소 · 번호표)은 버린다 · 크리에이터 칭호(301~)는 버린다 · 리스너가 아닌 곳이 붙여 보낸 칭호는 안 믿는다
"""
import json
import os
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:%s' % os.environ.get('LM_PT_PORT', '5199')
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
HERE = os.path.dirname(os.path.abspath(__file__))
_PT = os.environ.get('LM_SANDBOX_PT') or os.path.join(HERE, 'pausetest')
DB = os.path.join(_PT, 'live_master.db')
KEY = 'abcdef0123456789'
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:120]) if detail else ''))


def post(path, obj, authed=False):
    req = urllib.request.Request(B + path, json.dumps(obj).encode(), H if authed else {'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return r.status, json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def data():
    with urllib.request.urlopen(urllib.request.Request(B + '/api/data', headers=H), timeout=25) as r:
        return json.loads(r.read().decode())


def public_state():
    """방송판처럼(로그인 없이) 실시간 연결의 첫 상태(init)를 읽는다."""
    r = urllib.request.urlopen(B + '/api/stream?kind=overlay', timeout=15)
    ev, out = None, None
    t_end = time.time() + 10
    while time.time() < t_end:
        line = r.readline().decode('utf-8', 'replace').rstrip('\n')
        if line.startswith('event:'):
            ev = line.split(':', 1)[1].strip()
        elif line.startswith('data:') and ev in ('init', 'update'):
            out = line.split(':', 1)[1]
            break
    r.close()
    return out or ''


def ledger_count():
    if not os.path.exists(DB):
        return None
    c = sqlite3.connect(DB)
    try:
        return c.execute('SELECT COUNT(*) FROM donation_history').fetchone()[0]
    finally:
        c.close()


def donor_key_rows(tx):
    if not os.path.exists(DB):
        return None
    c = sqlite3.connect(DB)
    try:
        return c.execute('SELECT donor_key, level, title, vip FROM donor_keys WHERE tx_id = ?', (tx,)).fetchall()
    finally:
        c.close()


def pending():
    return data().get('pending_donations') or []


def don(tx, amount=12000, **extra):
    body = {'name': '칭호검사', 'amount': amount, 'message': '서아 화이팅', 'tx_id': tx}
    body.update(extra)
    return post('/api/donation', body)


EXTRAS = {'title': {'name': '블랙 다이아', 'type': 120}, 'level': 44, 'vip': 'VIP', 'donor_key': KEY}

print('=' * 74)
print('① 보통 후원')
print('=' * 74)
n0, l0 = len(pending()), ledger_count()
tx1 = 'toon_dx%d' % int(time.time() * 1000)
c, j = don(tx1, **EXTRAS)
chk('접수 200', c == 200 and j.get('status') == 'success', (c, j))
it = next((x for x in pending() if x.get('id') == j.get('id')), {})
chk('대기함: 공식 칭호 + 이름으로 정한 색(블랙 다이아 = 검정)', it.get('title') == {'name': '블랙 다이아', 'color': '#3A3A44'}, it.get('title'))
chk('대기함: 레벨 · VIP · 번호표', it.get('level') == 44 and it.get('vip') == 'VIP' and it.get('donor_key') == KEY,
    {k: it.get(k) for k in ('level', 'vip', 'donor_key')})
ld = data().get('latest_donation') or {}
chk('최근 후원(방송판 팝업 · 띠): 칭호 · 레벨', ld.get('donor_title', {}).get('name') == '블랙 다이아' and ld.get('donor_level') == 44, ld)
chk('최근 후원엔 번호표 · VIP 없음', 'donor_key' not in ld and 'vip' not in ld)
pub = public_state()
chk('⭐ 방송판(로그인 없음) 상태 어디에도 번호표가 없다', pub and KEY not in pub, len(pub))
chk('방송판 상태엔 칭호가 실려 있다', '블랙 다이아' in pub)
if l0 is not None:
    chk('정산 장부에 한 줄', ledger_count() == l0 + 1, (l0, ledger_count()))
    rows = donor_key_rows(tx1)
    chk('번호표 표에 한 줄(tx_id 로 장부와 잇는다)', rows == [(KEY, 44, '블랙 다이아', 'VIP')], rows)
else:
    print('  (장부 파일을 못 찾아 장부 검사는 건너뜀)', DB)

print('=' * 74)
print('② 다시 보기 · 후원 테스트는 화면에만')
print('=' * 74)
n1, l1 = len(pending()), ledger_count()
c, j = don('toon_dr%d' % int(time.time() * 1000), amount=800000, replay=True, **EXTRAS)
chk('다시 보기 → show_only replay', c == 200 and j.get('show_only') == 'replay', (c, j))
c2, j2 = don('toon_dt%d' % int(time.time() * 1000), amount=100012, test=True, **EXTRAS)
chk('후원 테스트 → show_only test', c2 == 200 and j2.get('show_only') == 'test', (c2, j2))
chk('대기함에 안 들어간다', len(pending()) == n1, (n1, len(pending())))
if l1 is not None:
    chk('⭐ 정산 장부에 안 적힌다', ledger_count() == l1, (l1, ledger_count()))
ld = data().get('latest_donation') or {}
chk('화면엔 띄운다(최근 후원 · 칭호 실림)', ld.get('show_only') == 'test' and ld.get('donor_title', {}).get('name') == '블랙 다이아', ld)
c3, j3 = don('toon_ds%d' % int(time.time() * 1000), amount=3000, display_only=True, replay=True, **EXTRAS)
ld = data().get('latest_donation') or {}
chk('소액(화면에만 띠)도 칭호를 싣는다', c3 == 200 and ld.get('display_only') and ld.get('donor_title', {}).get('name') == '블랙 다이아', ld)

print('=' * 74)
print('③ 이상한 값 · 리스너가 아닌 곳')
print('=' * 74)
bad = {'title': {'name': '<b>다이아</b>' + 'x' * 40, 'type': 120, 'color': 'red;background:url(x)', 'icon': 'https://evil.example/x.png'},
       'level': 'abc', 'vip': '', 'donor_key': 'XYZ<script>'}
c, j = don('toon_db%d' % int(time.time() * 1000), **bad)
it = next((x for x in pending() if x.get('id') == j.get('id')), {})
t = it.get('title') or {}
chk('그림 주소는 버리고 이름은 24자까지 · 색은 이름으로(글자로만 — 화면이 escape 한다)', t.get('name', '').startswith('<b>') and len(t['name']) == 24
    and t.get('color') == '#9EE7FF' and 'icon' not in t, t)
chk('이상한 레벨 · 번호표는 버린다', 'level' not in it and 'donor_key' not in it, {k: it.get(k) for k in ('level', 'donor_key')})
c, j = post('/api/donation', dict({'name': '조종실', 'amount': 15000, 'message': '', 'tx_id': 'tm_dm%d' % int(time.time() * 1000)}, **EXTRAS),
            authed=True)
it = next((x for x in pending() if x.get('id') == j.get('id')), {})
c4, j4 = don('toon_dc%d' % int(time.time() * 1000), title={'name': '밍밍', 'type': 301, 'color': '#FF8282'})
it4 = next((x for x in pending() if x.get('id') == j4.get('id')), {})
chk('⭐ 크리에이터 칭호(type 301~)는 서버도 버린다', c4 == 200 and 'title' not in it4, it4.get('title'))
chk('리스너가 아닌 곳이 붙여 보낸 칭호 · 번호표는 안 믿는다', c == 200 and 'title' not in it and 'donor_key' not in it, it)

print('=' * 74)
print('④ 화면 파일')
print('=' * 74)
ROOT = os.path.abspath(os.path.join(HERE, '..'))
ov = open(os.path.join(ROOT, 'overlay.html'), encoding='utf-8').read()
ct = open(os.path.join(ROOT, 'controller.html'), encoding='utf-8').read()
chk('방송판: 시그니처 카드 — 이름 앞 칭호 알약 · 이름 옆 Lv(시안 A)', 'donorTag(data.donor_title)' in ov
    and 'donorLv(data.donor_level)' in ov and 'setReactionTitle' not in ov and 'reaction-title-ribbon' not in ov)
chk('방송판: 팝업 · 소액 띠에도 칭호 알약', ov.count('donorTag(') >= 4)
chk('방송판: 단계 13개 · 효과 7단계(앞 단계 효과를 모두 갖고 더한다)', "'블랙노블레스': ['#8D90A8', '#07070B', 6, true]" in ov
    and "'금수저': ['#FFD76A', '#C8961E', 0]" in ov and "['g', 'sh', 'gl', 'spk', 'cr', 'bd', 'orb', 'rb', 'ray']]" in ov)
chk('방송판: 칭호 글자는 textContent 로만', 'tx.textContent = String(t.name)' in ov and 'innerHTML' not in ov[ov.find('function donorTag'):ov.find('function donorLv')])
chk('방송판: 칭호 그림은 안 쓴다(투네이션 자산)', 't.icon' not in ov and 'DONOR_TITLE_ICON' not in ov and '__special_title_img__' not in ov)
chk('조종실: 대기함 카드 칭호 · Lv (escapeHTML)', 'function pdTitleHtml' in ct and 'escapeHTML(String(t.name))' in ct and 'class="pd-lv"' in ct)

print('\n' + '=' * 74)
print('결과: 통과 %d · 실패 %d' % (len(OK), len(BAD)))
for b in BAD:
    print('  ✗', b)
sys.exit(1 if BAD else 0)
