# -*- coding: utf-8 -*-
"""🎨 조종실 새 옷(유리 스튜디오) — 겉모습만 바꾸고, 끄면 예전 그대로인가.

대표님(2026-09-30): 릴스 대시보드를 보고 "우리 대시보드도 이렇게 못 만드나" →
시안 A·B·C 중 A 를 보고 "와 A 너무 좋은데? 난 저런 디자인을 바랬어"

여기서 지키는 것
  ① 새 옷 규칙은 전부 body.skin-glass + 넓은 화면(1280px 이상) 안에만 있다 — 끄면(옛 모습) · 폰 · 반쪽 화면은 예전 그대로
  ② 흐림(backdrop-filter)을 안 쓴다 — 바탕 그림을 미리 흐리게 구웠다(방송 PC 가 OBS 와 같이 돌린다)
  ③ 켜고 끄기: 그리기 전에 입히고, 끈 것은 이 컴퓨터에 기억한다(기본은 새 옷)
  ④ 탭은 자리만 옮긴다 — 모든 탭 단추에 짧은 이름표가 있고, 누르는 동작(onclick)은 그대로
  ⑤ 첫 화면 숫자 칸은 이미 있는 셈을 쓴다(목표 = 방송판 막대 셈) · 못 잰 값은 '—'
  ⑥ 서버: /api/ai/board?today=1 이 '이번 방송 후원' 합계 · 건수를 준다(장부에서 센다)
"""
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid

sys.stdout.reconfigure(encoding='utf-8')
ROOT = (os.environ.get('LM_PROJECT_ROOT')
        or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')))
B = 'http://127.0.0.1:%s' % os.environ.get('LM_PT_PORT', '5199')
H = {'Content-Type': 'application/json', 'Authorization': 'Bearer sandboxsecret123456'}
OK, BAD = [], []


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:160]) if detail else ''))


def head(s):
    print()
    print('=' * 74)
    print(s)
    print('=' * 74)


CT = io.open(os.path.join(ROOT, 'controller.html'), encoding='utf-8').read()
AI = io.open(os.path.join(ROOT, 'features', 'ai.py'), encoding='utf-8').read()

head('① 새 옷 규칙은 body.skin-glass + 넓은 화면 안에만')
m = re.search(r'<style id="skin-glass-css">(.*?)</style>', CT, re.S)
chk('새 옷 규칙 덩어리가 있다', bool(m))
css = re.sub(r'/\*.*?\*/', '', m.group(1) if m else '', flags=re.S)
# 맨 바깥(미디어 밖)에는 '안 보이게' 두 줄만 있어야 한다
outside, media, depth, buf, cur = [], [], 0, '', None
i = 0
while i < len(css):
    c = css[i]
    if depth == 0 and css.startswith('@media', i):
        j = css.index('{', i)
        cur = css[i:j].strip(); buf = ''; depth = 1; i = j + 1
        continue
    if cur is not None:
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                media.append((cur, buf)); cur = None; i += 1
                continue
        buf += c
    else:
        outside.append(c)
    i += 1
out_rules = [r.strip() for r in re.findall(r'([^{}]+)\{[^}]*\}', ''.join(outside))]
chk('미디어 밖에는 숨김 두 줄뿐 (.skin-flip · #sk-head)', sorted(out_rules) == ['#sk-head', '.skin-flip'], out_rules)
chk('미디어는 전부 1280px 이상', media and all('min-width: 1280px' in q for q, _ in media), [q for q, _ in media])
leak = []
for q, body in media:
    for sel in re.findall(r'([^{}]+)\{[^}]*\}', body):
        for one in sel.split(','):
            one = one.strip()
            # .skin-flip(옷 바꾸기 단추 자신)만 옛 모습에서도 모양을 가진다
            if one and not (one.startswith('body.skin-glass') or one.startswith('.sk-') or one.startswith('#sk-')
                            or one.startswith('.skin-flip') or one.startswith('body:not(.skin-glass) .skin-flip')):
                leak.append(one)
chk('미디어 안 규칙도 새 옷 표시(body.skin-glass) 밑에만 걸린다', not leak, leak[:5])
chk('.sk-* 칸은 #sk-head 안에만 있다(새 옷 아니면 #sk-head 가 통째로 숨는다)',
    all(k in CT[CT.index('<section id="sk-head"'):CT.index('</section>', CT.index('<section id="sk-head"'))]
        for k in ('class="sk-stats"', 'class="sk-stat"', 'class="sk-meta"')))

head('② 흐림 효과 없이 — 바탕 그림을 미리 흐리게')
chk('새 옷 규칙에 backdrop-filter 가 없다', 'backdrop-filter' not in css)
bg = os.path.join(ROOT, 'vendor', 'stage', 'ctl_bg.jpg')
chk('바탕 그림(vendor/stage/ctl_bg.jpg)이 있고 가볍다(200KB 아래)', os.path.exists(bg) and os.path.getsize(bg) < 200 * 1024,
    os.path.getsize(bg) if os.path.exists(bg) else '없음')
chk('새 옷 바탕이 그 그림을 쓴다', "url('/vendor/stage/ctl_bg.jpg')" in css)

head('③ 켜고 끄기')
b = CT.index('<body>')
early = CT[b:b + 600]
chk('<body> 바로 뒤에서 그리기 전에 입힌다', early.lstrip('<body>').lstrip().startswith('<script>')
    and "localStorage.getItem('ctl_skin') !== 'classic'" in early and "classList.add('skin-glass')" in early)
chk('localStorage 가 막혀도 새 옷으로(오류 없이)', "catch (e) { document.body.classList.add('skin-glass'); }" in early)
fl = CT[CT.index('function skinFlip()'):CT.index('function skinFlipLabel()')]
chk('[옛 모습]/[새 옷] 단추가 이 컴퓨터에 기억한다', "localStorage.setItem('ctl_skin', on ? 'glass' : 'classic')" in fl)
chk('단추는 아랫줄(.tab-row2) 안에 있다 — 옛 모습에서 한 줄을 따로 안 먹는다',
    CT.index('id="skin-flip"') < CT.index('</div>', CT.index('class="tab-btn tab-minor tab-dots"')))

head('④ 탭은 자리만 옮긴다')
tabs = CT[CT.index('<div class="tabs tabs-2row">'):CT.index('id="skin-flip"')]
btns = re.findall(r'<button[^>]*class="tab-btn[^"]*"[^>]*>', tabs)
chk('탭 단추가 17개(⋯ 포함)', len(btns) == 17, len(btns))
chk('탭 단추마다 짧은 이름표(data-s)', all('data-s="' in x for x in btns), [x[:60] for x in btns if 'data-s="' not in x])
chk('누르는 동작은 예전 그대로(openTab 14 · ⋯ 1)',
    sum("onclick=\"openTab(event, '" in x for x in btns) == 14 and sum('tabs-open' in x for x in btns) == 1)
chk('이름표는 칸에 들어가는 길이(5글자 이하)', all(len(s) <= 5 for s in re.findall(r'data-s="([^"]+)"', tabs)),
    re.findall(r'data-s="([^"]+)"', tabs))

head('④-2 오른쪽 칸 순서 — 후원 콘솔이 미확인 후원 위')
aside = CT[CT.index('<aside class="shell-rail" id="shell-rail">'):CT.index('</aside>')]
chk('오른쪽 칸 첫 판이 후원 콘솔(시그니처 송출)', aside.index('id="rail-send"') < aside.index('id="rail-queue"')
    and not re.search(r'<div[^>]*id="(?!rail-send)[^"]*"', aside[:aside.index('id="rail-send"')]))
rp = CT[CT.index('function railPlace()'):CT.index("RAIL_MQ.addEventListener('change', railPlace)")]
chk('대기함 · 🆕 · 되돌리기는 재생 대기열 앞(= 후원 콘솔 밑)으로 옮겨 온다',
    "const first = document.getElementById('rail-queue');" in rp and 'rail.insertBefore(el, first)' in rp)

head('⑤ 첫 화면 숫자 칸 — 있는 셈을 쓴다')
sp = CT[CT.index('function skinStatsPaint()'):CT.index("document.addEventListener('DOMContentLoaded', () => { try { skinFlipLabel()")]
chk('목표 = 방송판 막대 셈(점수 + 운영비 + 보정)',
    "((gd.bottom_fixed || {}).score || 0) + (gd.bjs || []).reduce((s, b) => s + (b.score || 0), 0) + (parseInt(gd.goal_offset) || 0)" in sp)
chk('대기 = 대기함과 같은 목록(방금 누른 것 · 기여도 알림 · 퇴근 카드 빼고)',
    "!removedPendingIds.has(d.id) && d.type !== 'off_work' && d.kind !== 'contrib'" in sp)
chk('이번 방송 후원은 서버 값을 받기 전 "—"(지어내지 않는다)', "else put('sk-today', '—', '불러오는 중')" in sp)
chk('1등 이름은 글자로만 넣는다(escapeHTML)', "put('sk-top', escapeHTML(a.name || '')" in sp)
r = CT.index('try { renderPending(); } catch(e) {}')
chk('숫자 칸은 대기함과 같이 그린다(입력 중 조기 return 보다 앞)',
    CT.index('try { skinStatsPaint(); } catch(e) {}', r) < CT.index('if(document.activeElement.tagName === "INPUT"', r))
chk('장부 값은 첫 화면이 보일 때만 10초마다 묻는다',
    "setInterval(skinTodayLoad, 10000)" in CT and "t.classList.contains('active')" in CT[CT.index('async function skinTodayLoad'):CT.index('function skinTodayRun')])

head('⑦ 누르는 도중에 단추가 안 바뀌고 안 밀린다 (진짜 마우스로 눌러 보며 찾은 것)')
# 누름과 뗌 사이에 단추가 새것으로 바뀌면 클릭이 사라진다 — 바뀔 때만 다시 그린다
chk('점수표 머리([일괄등록]·[+])는 바뀔 때만 다시 그린다',
    "if (lastTHtml !== tHeadHtml) { document.getElementById('ranking-thead').innerHTML = tHeadHtml; lastTHtml = tHeadHtml; }" in CT
    and "document.getElementById('ranking-thead').innerHTML = tHeadHtml;\n" not in CT)
cx = CT[CT.index('function renderContextStrip()'):CT.index('// 대결 시간은 초마다 흐른다')]
chk('맨 윗줄 타이머 단추는 시간 글자가 바뀌어도 새로 안 그린다(시작/정지가 바뀔 때만)',
    "const hsig = hh ? ('run:' + !!md.is_running) : '';" in cx and 'if (_hdr.dataset.sig !== hsig)' in cx and 'if (_hdr.dataset.sig !== hh)' not in cx)
chk('탭 밑 대결 칩도 시간 글자를 빼고 비교한다', "const csig = html.replace(" in cx and 'if (csig !== _cxLast)' in cx)
ud = CT[CT.index('function renderUndoStrip()'):CT.index('function showUndoToast(')]
chk('되돌리기 줄([취소])은 바뀔 때만 다시 그린다', 'if (el._sig !== html) { el._sig = html; el.innerHTML = html; }' in ud)
chk('AI 제안은 대기함 안 맨 위(떠서 단추를 덮지 않는다)',
    'pb.insertBefore(w, pl)' in CT and '#ai-assign-toasts.in-box { position:static;' in CT and 'toastPlace();' in CT)
chk("'순서 고정' 글씨는 자리를 차지하지 않는다(제목이 두 줄이 되어 카드가 밀리지 않게)",
    '#pending-box.order-frozen .group-title::after { position: absolute;' in CT)
chk('새 옷 오른쪽 칸 높이 = 화면 − 맨 윗줄(맨 아래 단추가 화면 밖으로 안 잘리게)',
    'max-height: calc(100vh - var(--sk-hdr, 84px) - 56px)' in css and "setProperty('--sk-hdr'" in CT)

chk('창 크기가 바뀌면 오른쪽 칸을 다시 짠다(넓은 ↔ 좁은)', "RAIL_MQ.addEventListener('change', railPlace)" in CT)

head('⑥ 서버 — /api/ai/board?today=1')
chk('today 는 물을 때만(장부 조회를 4초마다 하지 않게)', "if request.args.get('today'):" in AI and "out['today'] = _today_donations()" in AI)


def get(path):
    req = urllib.request.Request(B + path, None, H, method='GET')
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            return res.status, json.loads(res.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {'err': str(e)}


def post(path, obj):
    req = urllib.request.Request(B + path, json.dumps(obj).encode(), H)
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            return res.status, json.loads(res.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        return e.code, {}


c0, d0 = get('/api/ai/board?today=1')
chk('?today=1 → today(건수 · 합계금액)', c0 == 200 and isinstance(d0.get('today'), dict)
    and {'건수', '합계금액'} <= set(d0['today']), (c0, d0.get('today')))
c1, d1 = get('/api/ai/board')
chk('그냥 부르면 today 가 없다(예전 그대로)', c1 == 200 and 'today' not in d1, list(d1))
if isinstance(d0.get('today'), dict):
    n0, s0 = d0['today']['건수'], d0['today']['합계금액']
    post('/api/donation', {'name': '새옷검사', 'amount': 30000, 'message': '', 'tx_id': 'toon_' + uuid.uuid4().hex[:12]})
    time.sleep(0.4)
    c2, d2 = get('/api/ai/board?today=1')
    t2 = d2.get('today') or {}
    chk('후원 한 건 → 건수 +1 · 합계 +30,000', t2.get('건수') == n0 + 1 and t2.get('합계금액') == s0 + 30000, (n0, s0, t2))

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
sys.exit(1 if BAD else 0)
