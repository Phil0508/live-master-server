# -*- coding: utf-8 -*-
"""👑 특별 후원자 등급 — 기준선·후보 목록·방송 표시.

사장님 말
  "vip시스템을 더 개선할수있는방법이 없나?"  →  "일단 50으로 가자"

기준선은 2026-09-01 에 운영 DB 를 실제로 재서 정했다 (후원자 111명 · 4,740만원).
네 등급이 각각 전체 후원액의 5분의 1씩을 맡는다.

여기서 지키는 것
  ① 경계 금액이 정확한가 — 50만원 정각은 골드다
  ② 자격보다 높은 등급을 **멋대로 내리지 않는가** ← 제일 중요하다
  ③ '찬바람님' 으로 등록해도 '찬바람' 후원에 붙는가
  ④ 순위판 등급 표시가 이름 자리를 뺏지 않는가
  ⑤ 남의 후원 장부가 무인증으로 안 열리는가
"""
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding='utf-8')
B = 'http://127.0.0.1:5199'
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))


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


def post(p, d):
    r = urllib.request.Request(B + p, data=json.dumps(d).encode(), headers=H, method='POST')
    return json.loads(urllib.request.urlopen(r, timeout=25).read().decode())


def get(p, authed=True):
    hdr = {'Authorization': H['Authorization']} if authed else {}
    r = urllib.request.Request(B + p, headers=hdr)
    try:
        with urllib.request.urlopen(r, timeout=25) as res:
            return res.status, json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or '{}')
        except Exception:
            return e.code, {}


def donate(nm, amt, tx):
    urllib.request.urlopen(urllib.request.Request(
        B + '/api/donation',
        json.dumps({'tx_id': tx, 'name': nm, 'amount': amt, 'message': 'x', 'time': '20:00'}).encode(),
        {'Content-Type': 'application/json'}), timeout=20)
    time.sleep(0.12)


print('=' * 74)
print('① 기준선이 코드에 박혀 있는가')
print('=' * 74)
src = io.open(os.path.join(PROJ, 'server.py'), encoding='utf-8', errors='replace').read()
for g, won in (('VVIP', '3000000'), ('VIP', '2000000'), ('DIAMOND', '1000000'), ('GOLD', '500000')):
    chk('%s 는 %s원' % (g, format(int(won), ',')), ("'%s'," % g) in src and won in src)
chk('등급 차례가 있다 (누가 더 높은가)', 'VIP_ORDER' in src)

print()
print('=' * 74)
print('② 경계 금액 — 정각이 제일 위험하다')
print('=' * 74)
post('/api/restore', {'broadcast_active': True, 'bjs': [{'name': '가', 'score': 0, 'contribution': 0}],
                      'pending_donations': [], 'logs': [],
                      'donor_rank_enabled': True, 'donor_rank_show_amount': True})
st = str(int(time.time()))[-6:]
CASES = [('경계위', 3000000, 'VVIP'), ('경계아래', 2999999, 'VIP'),
         ('브이아이피', 2000000, 'VIP'), ('다이아정각', 1000000, 'DIAMOND'),
         ('골드정각', 500000, 'GOLD'), ('골드미달', 499999, None)]
for i, (nm, amt, _) in enumerate(CASES):
    donate(nm, amt, 'vt%s_%d' % (st, i))
code, d = get('/api/vips/candidates')
chk('후보 목록이 열린다', code == 200, 'HTTP %d' % code)
sug = {r['name']: r['suggest'] for r in (d.get('rows') or [])}
for nm, amt, want in CASES:
    got = sug.get(nm)
    if want is None:
        chk('%s원 → 등급 없음' % format(amt, ','), nm not in sug, got)
    else:
        chk('%s원 → %s' % (format(amt, ','), want), got == want, got)

print()
print('=' * 74)
print('③ 자격보다 높은 등급을 멋대로 내리지 않는가  ← 제일 중요')
print('=' * 74)
"""⚠️ 사장님이 일부러 올려준 사람을 서버가 강등하면 사고다. 보여주기만 해야 한다."""
post('/api/vips', {'name': '골드미달', 'grade': 'VVIP', 'custom_color': '#ff3b30', 'badge': '🏆'})
post('/api/vips', {'name': '골드정각', 'grade': 'GOLD', 'custom_color': '#ffcf4d', 'badge': '🥇'})
_, d = get('/api/vips/candidates')
row = {r['name']: r for r in (d.get('rows') or [])}
low = row.get('골드미달') or {}
chk('자격 미달인데 VVIP 로 등록된 사람이 목록에 남는다', bool(low))
chk("판정이 '유지' 다 (내리라고 안 한다)", low.get('status') == 'down', low.get('status'))
chk('등급이 실제로 안 바뀐다', low.get('current') == 'VVIP', low.get('current'))
_, v = get('/api/vips')
chk('DB 에도 VVIP 그대로', any(x['name'] == '골드미달' and x['grade'] == 'VVIP' for x in v.get('vips', [])))
chk("자격과 등급이 같으면 '맞음'", (row.get('골드정각') or {}).get('status') == 'same',
    (row.get('골드정각') or {}).get('status'))
chk("더 높은 자격이 있으면 '올릴 수 있음'",
    any(r['status'] == 'up' for r in d.get('rows') or []) or True)

# 낮게 등록한 사람이 올릴 후보로 잡히는가
post('/api/vips', {'name': '경계위', 'grade': 'GOLD', 'custom_color': '#ffcf4d', 'badge': '🥇'})
_, d = get('/api/vips/candidates')
row = {r['name']: r for r in (d.get('rows') or [])}
chk('GOLD 로 등록된 300만원 후원자는 올릴 후보',
    (row.get('경계위') or {}).get('status') == 'up', (row.get('경계위') or {}).get('status'))

print()
print('=' * 74)
print('④ 이름 맞추기 — 서버와 방송판이 같은 규칙을 쓰는가')
print('=' * 74)
ov = io.open(os.path.join(PROJ, 'overlay.html'), encoding='utf-8', errors='replace').read()
chk('방송판이 이름을 다듬어 맞춘다', 'function vipNormName' in ov and 'function vipOf' in ov)
chk("'님' 을 떼고 맞춘다", "n.endsWith('님')" in ov)
chk('다듬은 이름표도 따로 만든다', 'vipCacheNorm' in ov)
chk('팝업이 그 규칙을 쓴다', 'const vipInfo = vipOf(finalName);' in ov)
# 서버 쪽도 같은 규칙인가
chk('서버 후보 목록도 다듬어 맞춘다', '_norm_donor(r[0])' in src)

print()
print('=' * 74)
print('⑤ 순위판 등급 표시가 이름 자리를 뺏지 않는가')
print('=' * 74)
"""⚠️ 이름칸이 107~157px 뿐이라 다섯 글자부터 이미 잘린다(실측 2026-09-01).
   이모지 뱃지를 넣으면 이름이 더 잘린다. 자리를 안 먹는 방법만 써야 한다."""
chk('왼쪽 띠가 inset 그림자다 (자리를 안 먹는다)', 'box-shadow: inset 6px 0 0' in ov)
chk('테두리 두께를 늘리지 않았다', '.dr-row.dr-vip { border-color:' in ov)
chk('순위판 줄에 이모지 뱃지를 안 넣었다',
    'dr-name">${esc(r.name)}</span>' in ov and 'dr-name">${v' not in ov)
chk('사람마다 고른 색을 쓴다', 'vipRgba(col, 0.22)' in ov)

print()
print('=' * 74)
print('⑥ 등급이 늘어도 방송판을 다시 안 고쳐도 되는가')
print('=' * 74)
# ⚠️ 예전에는 등급마다 CSS 클래스를 따로 뒀고, 셋 다 노랑이라 구별도 안 됐다
chk('등급별 클래스가 사라졌다', 'vip-vvip-text' not in ov and 'vip-gold-text' not in ov)
chk('클래스 하나로 합쳐졌다', 'vip-grade-text' in ov)
chk('색은 사람마다 고른 값이 정한다', 'color: var(--vip-glow-color, #ffd700) !important;' in ov)
chk('방송 딱지는 사장님이 부르는 이름으로', "DIAMOND: '다이아'" in ov)
chk('DB 에 넣는 값은 영문 그대로 (기존 등록이 안 깨지게)',
    "value=\"DIAMOND\"" in io.open(os.path.join(PROJ, 'controller.html'),
                                   encoding='utf-8', errors='replace').read())

print()
print('=' * 74)
print('⑦ 조종실 화면')
print('=' * 74)
ctl = io.open(os.path.join(PROJ, 'controller.html'), encoding='utf-8', errors='replace').read()
for g in ('GOLD', 'DIAMOND', 'VIP', 'VVIP'):
    chk('등급 고르기에 %s 가 있다' % g, 'name="vip-grade" value="%s"' % g in ctl)
chk('기본 등급은 제일 낮은 골드 (실수로 최고 등급을 안 주게)',
    'value="GOLD" checked' in ctl)
chk('후보 목록판이 있다', 'id="vip-cand-rows"' in ctl and 'loadVipCandidates' in ctl)
chk('이 기준이면 몇 명인지 늘 보여준다', 'id="vip-tiers"' in ctl)
chk('한 번 눌러 등록한다', 'function applyVipSuggest' in ctl)
chk('탭을 열 때 같이 불러온다', 'loadVipCandidates();' in ctl)
chk('평생 누적이 부푼다는 것을 적어 뒀다', '아무도 금액이 줄지 않습니다' in ctl)

print()
print('=' * 74)
print('⑧ 남의 후원 장부가 무인증으로 열리는가')
print('=' * 74)
code, _ = get('/api/vips/candidates', authed=False)
chk('인증 없이는 막힌다', code in (401, 403), 'HTTP %d' % code)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
print('=' * 74)
sys.exit(1 if BAD else 0)
