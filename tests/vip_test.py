# -*- coding: utf-8 -*-
"""👑 특별 후원자 등급 = 이번 방송(한 회차) 후원 순위, 실시간.

사장님 말 (2026-09-09)
  "한달치가 아니라 수-목 방송 한 회차의 순위로 등록하고싶어"
  "수 17:00~목 03:00까지의 순위를 매기는거라 실시간으로 반영이 되어야해"
  등급: 1위 VVIP · 2~3위 VIP · 4~6위 DIAMOND · 7~10위 BRONZE · 계좌 후원 포함 · 옛 등급은 전부 비움

여기서 지키는 것
  ① 순위 구간이 코드에 박혀 있고, 옛 평생누적 등급은 한 번 비운다
  ② 순위 → 등급이 맞는가 (동점은 같은 순위 · 익명 제외 · 11위부터 없음)
  ③ 실시간인가 — 후원 한 건으로 1위가 바뀌면 그 자리에서 등급이 바뀐다 · 빼기도 즉시
  ④ 직접 준 등급은 순위에 못 든 사람에게만 붙는다 (방송판 규칙)
  ⑤ 이름 맞추기 — 서버와 방송판이 같은 규칙을 쓰는가
  ⑥ 순위판 등급 표시가 이름 자리를 뺏지 않는가
  ⑦ 등급이 늘어도 방송판을 다시 안 고쳐도 되는가
  ⑧ 조종실 화면
  ⑨ 남의 후원 장부가 무인증으로 안 열리는가
"""
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
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


def post(p, d, method='POST'):
    r = urllib.request.Request(B + p, data=json.dumps(d, ensure_ascii=False).encode('utf-8'),
                               headers=H, method=method)
    try:
        return json.loads(urllib.request.urlopen(r, timeout=25).read().decode())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode())
        except Exception:
            return {'status': 'error', 'code': e.code}


def get(p, authed=True):
    hdr = H if authed else {}
    r = urllib.request.Request(B + p, headers=hdr)
    try:
        with urllib.request.urlopen(r, timeout=25) as res:
            return res.status, json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


_tx = [0]


def donate(nm, amt):
    _tx[0] += 1
    urllib.request.urlopen(urllib.request.Request(
        B + '/api/donation',
        json.dumps({'tx_id': 'vipr-%d-%d' % (int(time.time()), _tx[0]), 'name': nm, 'amount': amt,
                    'message': 'x', 'time': '20:00'}, ensure_ascii=False).encode('utf-8'),
        headers=H, method='POST'), timeout=25).read()


def live():
    """무인증 /api/data 의 vip_live — 방송판이 보는 그대로."""
    c, d = get('/api/data', authed=False)
    return d.get('vip_live') or {}


src = io.open(os.path.join(PROJ, 'server.py'), encoding='utf-8', errors='replace').read()
ov = io.open(os.path.join(PROJ, 'overlay.html'), 'rb').read().replace(b'\x00', b'').decode('utf-8', 'replace')
ctl = io.open(os.path.join(PROJ, 'controller.html'), encoding='utf-8', errors='replace').read()

print('=' * 74)
print('① 순위 구간이 코드에 박혀 있는가 · 옛 등급은 한 번 비우는가')
print('=' * 74)
chk('순위 구간표', "('VVIP',    1,  1," in src and "('BRONZE',  7, 10," in src)
# 🎖️ 색이 귀금속 순서인지 — 빨강으로 되돌아가면 여기서 잡힌다
chk('1위는 금 · 7~10위는 동 (빨강·노랑 아님)',
    "'#f6c453', '🏆'" in src and "'#c97f3d', '🥉'" in src and "'#ff3b30'" not in src)
chk('순위 → 등급 함수', 'def vip_tier_for_rank(rank)' in src and 'def _vip_live(state)' in src)
chk('평생 누적 기준선이 사라졌다', 'def vip_tier_for(total)' not in src and 'VIP_RECENT_DAYS' not in src)
chk('옛 등급은 서버가 뜰 때 한 번 비운다 (표시는 kv_store 가 아니라 app_flags)',
    'def _vip_wipe_legacy_once' in src and "app_flags" in src and "'vip_rank_reset_v1'" in src)
chk('매 상태에 실어 보낸다 (SSE·GET 이 같이 지나는 깔때기)', "out['vip_live'] = _vip_live(out)" in src)
# ⚠️ 갓 뜬 서버는 첫 상태 읽기에서 표를 만든다 — 먼저 한 번 두드리고, 잠깐 기다린다
get('/api/data')
for _ in range(20):
    c, v = get('/api/vips')
    if c == 200 and v.get('status') == 'success':
        break
    time.sleep(0.5)
chk('갓 뜬 서버의 직접 준 등급 목록이 비어 있다', c == 200 and v.get('vips') == [], (c, v.get('vips')))

print()
print('=' * 74)
print('② 순위 → 등급 (동점 · 익명 · 11위)')
print('=' * 74)
post('/api/restore', {'broadcast_active': True, 'bjs': [{'name': '가', 'score': 0, 'contribution': 0}],
                      'pending_donations': [], 'logs': [], 'reaction_queue': [], 'donor_tally': {}})
plan = [('으뜸', 100000), ('버금', 90000), ('버금둘', 90000), ('넷째', 80000), ('다섯', 70000),
        ('여섯', 60000), ('일곱', 50000), ('여덟', 40000), ('아홉', 30000), ('열', 20000),
        ('열하나', 10000), ('익명', 200000)]
for nm, amt in plan:
    donate(nm, amt)
L = live()
g = lambda n: (L.get(n) or {}).get('grade')
r = lambda n: (L.get(n) or {}).get('rank')
chk('1위 VVIP', g('으뜸') == 'VVIP' and r('으뜸') == 1, (g('으뜸'), r('으뜸')))
chk('동점 둘은 같은 2위 · 둘 다 VIP', g('버금') == 'VIP' and g('버금둘') == 'VIP' and r('버금') == 2 and r('버금둘') == 2,
    [(n, g(n), r(n)) for n in ('버금', '버금둘')])
chk('동점 다음은 4위(3위 건너뜀) → DIAMOND', g('넷째') == 'DIAMOND' and r('넷째') == 4, (g('넷째'), r('넷째')))
chk('6위 DIAMOND · 7위 BRONZE', g('여섯') == 'DIAMOND' and g('일곱') == 'BRONZE', (g('여섯'), g('일곱')))
chk('10위 BRONZE', g('열') == 'BRONZE' and r('열') == 10, (g('열'), r('열')))
chk('11위는 등급 없음', '열하나' not in L)
chk('익명은 아무리 커도 순위에 없다', '익명' not in L)
chk('색·뱃지가 같이 온다 (방송판이 그대로 쓴다)', (L.get('으뜸') or {}).get('custom_color') == '#f6c453'
    and (L.get('으뜸') or {}).get('badge') == '🏆', L.get('으뜸'))
c, cand = get('/api/vips/candidates')
chk('조종실 순위표가 열린다', c == 200 and cand.get('status') == 'success', c)
rows = {x['name']: x for x in cand.get('rows', [])}
chk('조종실 표는 11위도 순위를 이어 붙인다', (rows.get('열하나') or {}).get('rank') == 11 and not (rows.get('열하나') or {}).get('grade'),
    rows.get('열하나'))

print()
print('=' * 74)
print('③ 실시간 — 후원 한 건으로 1위가 바뀐다 · 빼기도 즉시')
print('=' * 74)
donate('열하나', 100000)          # 110,000 → 1위
L = live()
chk('방금 후원한 사람이 바로 1위 VVIP', g('열하나') == 'VVIP' and r('열하나') == 1, (g('열하나'), r('열하나')))
chk('밀린 사람은 2위 VIP 로 내려간다 (저장된 등급이 아니라 순위다)', g('으뜸') == 'VIP' and r('으뜸') == 2, (g('으뜸'), r('으뜸')))
chk('10위였던 사람은 11위로 밀려 등급이 없다', '열' not in L)
post('/api/donors/excluded', {'name': '열하나', 'memo': '테스트'})
L = live()
chk('순위에서 빼면 그 자리에서 사라진다', '열하나' not in L)
chk('나머지가 올라온다 — 으뜸이 다시 1위', g('으뜸') == 'VVIP' and r('으뜸') == 1, (g('으뜸'), r('으뜸')))
post('/api/donors/excluded?name=' + urllib.parse.quote('열하나'), {}, method='DELETE')
post('/api/server/start_broadcast', {'names': ['가']})   # 새 회차 — 순위는 처음부터
c, d = get('/api/data', authed=False)
chk('방송을 새로 켜면 순위가 비어 등급도 없다', not (d.get('vip_live') or {}), d.get('vip_live'))
post('/api/restore', {'broadcast_active': True, 'bjs': [{'name': '가', 'score': 0, 'contribution': 0}],
                      'pending_donations': [], 'logs': [], 'reaction_queue': [], 'donor_tally': {}})

print()
print('=' * 74)
print('④ 직접 준 등급은 순위에 못 든 사람에게만 (방송판 규칙)')
print('=' * 74)
post('/api/vips', {'name': '골드미달', 'grade': 'VVIP', 'custom_color': '#f6c453', 'badge': '🏆'})
c, v = get('/api/vips')
chk('직접 준 등급은 그대로 남는다 (서버가 멋대로 안 지운다)', any(x['name'] == '골드미달' and x['grade'] == 'VVIP' for x in v.get('vips', [])))
chk('방송판은 순위 등급을 먼저 본다', 'const lv = window.vipLive || {};' in ov and 'if (lv[key]) return lv[key];' in ov)
chk('그 다음에야 직접 준 등급', 'return c[raw] || n[key] || null;' in ov)
chk('상태가 올 때마다 순위 등급을 받아 둔다 (팝업보다 먼저)', 'window.vipLive = d.vip_live;' in ov)
chk('팝업에 몇 위인지 붙인다 (딱지·메달·머리띠 어디로 가든)',
    "vipRank + '위'" in ov and '${vipRank}위' in ov)

print()
print('=' * 74)
print('⑤ 이름 맞추기 — 서버와 방송판이 같은 규칙을 쓰는가')
print('=' * 74)
chk('방송판이 이름을 다듬어 맞춘다', 'function vipNormName' in ov and 'function vipOf' in ov)
chk("'님' 을 떼고 맞춘다", "n.endsWith('님')" in ov)
chk('팝업이 그 규칙을 쓴다', 'const vipInfo = vipOf(finalName);' in ov)
chk('서버 순위표는 다듬은 이름(donor_tally 키)으로 매긴다 · 제외 명단을 본다', 'is_excluded(who)' in src)
donate('찬바람님', 999999)
L = live()
chk("'찬바람님' 후원이 '찬바람' 으로 1위", g('찬바람') == 'VVIP', [(k, x.get('rank')) for k, x in L.items()][:4])

print()
print('=' * 74)
print('⑥ 순위판 등급 표시가 이름 자리를 뺏지 않는가')
print('=' * 74)
chk('왼쪽 띠가 inset 그림자다 (자리를 안 먹는다)', 'box-shadow: inset 6px 0 0' in ov)
chk('테두리 두께를 늘리지 않았다', '.dr-row.dr-vip { border-color:' in ov)
chk('사람마다(등급마다) 온 색을 쓴다', 'vipRgba(col, 0.22)' in ov)

print()
print('=' * 74)
print('⑦ 등급이 늘어도 방송판을 다시 안 고쳐도 되는가')
print('=' * 74)
chk('등급별 클래스가 사라졌다', 'vip-vvip-text' not in ov and 'vip-gold-text' not in ov)
chk('클래스 하나로 합쳐졌다', 'vip-grade-text' in ov)
# 🎖️ 등급마다 모양이 다르다 — 색만 다르면 1위와 8위가 같은 급으로 보인다
chk('1위는 훈장 · 2~3위는 머리띠 · 4위 이하는 딱지',
    'vip-rank-top' in ov and 'vip-rank-mid' in ov and 'vipRank === 1' in ov
    and 'vipRank >= 2 && vipRank <= 3' in ov)
chk('장식 자리는 따로 둔다 (후원 내용 구조는 안 건드린다)', 'id="toon-vip-deco"' in ov)
chk('다음 후원에 흔적이 안 남는다', "decoEl.innerHTML = ''" in ov
    and "'vip-premium-card', 'vip-rank-top', 'vip-rank-mid'" in ov)
chk('색은 온 값이 정한다', ('color: var(--vip-glow-color, var(--gold)) !important;' in ov or 'color: var(--vip-glow-color, #ffd700) !important;' in ov))
chk('방송 딱지는 사장님이 부르는 이름으로', "DIAMOND: '다이아'" in ov)

print()
print('=' * 74)
print('⑧ 조종실 화면')
print('=' * 74)
chk('이번 방송 순위표가 있다', 'id="vip-cand-rows"' in ctl and 'function renderVipLive' in ctl)
chk('순위 구간을 보여준다', 'id="vip-tiers"' in ctl and "['BRONZE', 7, 10]" in ctl)
# 조종실과 방송판이 서로 다른 색을 쓰면 같은 사람이 화면마다 다른 등급으로 보인다
chk('조종실 색표가 서버와 같다', "VVIP: '#f6c453'" in ctl and "BRONZE: '#c97f3d'" in ctl)
chk('옛 GOLD 도 계속 알아듣는다 (직접 준 등급에 남아 있을 수 있다)',
    "GOLD: '#ffcf4d'" in ctl and "BRONZE: '브론즈'" in ov)
chk('상태가 올 때마다 다시 그린다 (실시간)', 'renderVipLive(false)' in ctl)
chk('예전 "누르면 반영" 버튼은 없다', 'applyVipSuggest' not in ctl and 'vip-only-todo' not in ctl)
chk('실시간이라고 적어 뒀다', '후원이 들어오면 그 자리에서 바뀝니다' in ctl)

print()
print('=' * 74)
print('⑨ 남의 후원 장부가 무인증으로 열리는가')
print('=' * 74)
code, _ = get('/api/vips/candidates', authed=False)
chk('조종실 순위표는 인증 없이는 막힌다', code in (401, 403), 'HTTP %d' % code)
c, d = get('/api/data', authed=False)
chk('방송판이 보는 순위 등급에는 이름·등급·순위만 있다 (메시지 없음)',
    all(set(x.keys()) <= {'name', 'rank', 'total', 'grade', 'custom_color', 'badge'} for x in (d.get('vip_live') or {}).values()))

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
print('=' * 74)
