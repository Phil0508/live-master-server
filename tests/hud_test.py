# -*- coding: utf-8 -*-
"""🖥️ 안전지대 한 몸 HUD.

유튜브 세로 라이브에서 안 가려지는 자리는 y 115~960, 845px 뿐이다.
여기에 상시 위젯과 게임판이 다 들어가야 한다. 서로 맞물려 있어서 하나만
움직여도 나머지가 깨지므로 자리를 HTML 에 못 박고, 이 검사가 그 자리를 지킨다.

    머리 줄   6~1042 / 115~163   계좌 한 줄 + 흐르는 안내 자막
    엑셀판    336~1038 / 167~299  (오른쪽 기준이라 사람이 늘면 왼쪽으로 자란다)
    게임판    6~1036 / 307~956
    세로 게이지 1046~1076 / 115~954
    전광판 쌍  0~1080 / 115~187 · 882~954  (리액션 때만 뜬다)

무엇을 지키나
  · 총후원 게이지가 세로 막대인가 (가로 박스로 되돌아가면 세로 186px 을 뺏긴다)
  · 넷이 서로 안 겹치고 다 안전지대 안인가 (막대가 판 뒤로 숨은 적이 있다)
  · 못 박은 것들이 applyLayout 대상에서 빠졌는가
    (배치 파일에 남은 옛 자리 — 게이지 y 1598 · 안내 y 1680 — 이 다시 덮어쓰면 사라진다)
  · 게임 중에는 금액 딱지를 숨기는가 (판 위에 겹쳐 앉는다)
  · 전광판 쌍이 하나로 합쳐지지 않았는가 (갈라지는 연출이 죽는다)
  · 편집기가 같은 자리를 그리고, 못 박은 것은 못 끌게 하는가
  · 옛 흔적(가로 게이지·두 단 계좌)이 안 남았는가
"""
import io
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
ROOT = r'C:\Users\Administrator\Desktop\새로다시시작'
OK, BAD = [], []

# 유튜브 세로 라이브 실측 (1080×1920)
SAFE_TOP, SAFE_BOT, W = 115, 960, 1080
RANK_W, RANK_H = 702, 132       # 화면에서 직접 잰 엑셀판 크기 (소스에 숫자로 없다)
TICKER_H = 74                   # .ticker-bar 70px + 위아래 테두리 2px 씩


def chk(name, cond, detail=''):
    (OK if cond else BAD).append(name)
    print(('  [OK] ' if cond else '  [!!] ') + name + (('  -- ' + str(detail)[:110]) if detail else ''))


ov = io.open(os.path.join(ROOT, 'overlay.html'), encoding='utf-8', errors='replace').read()
ad = io.open(os.path.join(ROOT, 'admin.html'), encoding='utf-8', errors='replace').read()


def pos(pat, src=None):
    mm = re.search(pat, src if src is not None else ov)
    return (int(mm.group(1)), int(mm.group(2))) if mm else None


print('=' * 74)
print('① 총후원 게이지가 세로 막대인가')
print('=' * 74)
m = re.search(r'\.goal-rail \{[^}]*width:\s*(\d+)px;\s*height:\s*(\d+)px', ov)
chk('세로 막대 규칙이 있다', m is not None, m.group(0)[:70] if m else '못 찾음')
rail_w, rail_h = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
chk('막대가 얇다 (가로 40px 이하)', 0 < rail_w <= 40, '%dpx' % rail_w)
chk('막대가 안전지대 높이(845)를 안 넘는다', 0 < rail_h <= 845, '%dpx' % rail_h)
chk('바닥부터 찬다 (bottom 기준)', re.search(r'\.goal-rail-fill \{[^}]*bottom:', ov) is not None)
chk('찬 높이에 금액 딱지가 붙는다', '.goal-rail-tip' in ov and 'goal-tip' in ov)
chk('막대 높이를 style.height 로 채운다 (옛 가로 박스는 width 였다)', 'goalFill.style.height' in ov)
chk('딱지를 막대 안에 가둔다 (끝에서 안전지대를 안 넘게)', 'goalTipF' in ov)

print()
print('=' * 74)
print('② 머리 줄 — 계좌 한 줄 + 흐르는 안내 자막')
print('=' * 74)
mh = re.search(r'id="headrow"[^>]*left:\s*(\d+)px;\s*top:\s*(\d+)px;\s*'
               r'width:\s*(\d+)px;\s*height:\s*(\d+)px', ov)
chk('머리 줄이 있다', mh is not None, mh.group(0)[:80] if mh else '못 찾음')
hx, hy, hw, hh = (int(x) for x in mh.groups()) if mh else (0, 0, 0, 0)
chk('머리 줄이 낮다 (60px 이하)', 0 < hh <= 60,
    '%dpx (예전 계좌 181 + 안내 78 = 259)' % hh)
chk('계좌와 안내 자막이 같은 줄에 있다',
    'id="account-container"' in ov[ov.find('id="headrow"'):ov.find('id="headrow"') + 2200]
    and 'id="notice-container"' in ov[ov.find('id="headrow"'):ov.find('id="headrow"') + 2200])
chk('계좌는 제 폭만큼만 쓴다 (flex:none)', 'id="account-container"' in ov
    and 'flex: none' in ov[ov.find('id="account-container"'):ov.find('id="account-container"') + 160])
chk('자막이 남는 자리를 다 쓴다 (flex:1)', 'id="notice-container"' in ov
    and 'flex: 1' in ov[ov.find('id="notice-container"'):ov.find('id="notice-container"') + 160])
ma = re.search(r'\.acc-box-v2 \{[^}]*height:\s*(\d+)px', ov)
chk('계좌가 한 줄이다', ma and int(ma.group(1)) <= 60,
    (ma.group(1) + 'px') if ma else '못 찾음')
mn = re.search(r'\.notice-board \{[^}]*height:\s*(\d+)px', ov)
chk('안내 띠도 같은 높이다', mn and ma and mn.group(1) == ma.group(1),
    (mn.group(1) + 'px') if mn else '못 찾음')
chk('테두리를 높이에 안 더한다 (box-sizing)',
    'box-sizing: border-box; height: 48px' in ov and ov.count('box-sizing: border-box') >= 2)
chk('리액션 중에는 머리 줄도 숨는다 (계좌가 ui-layer 밖으로 나왔다)',
    'body.reaction-mode #headrow' in ov)

print()
print('=' * 74)
print('③ 넷이 안 겹치고 안전지대 안에 있는가')
print('=' * 74)
g = pos(r'id="gauge-container"[^>]*left:\s*(\d+)px;\s*top:\s*(\d+)px')
rmm = re.search(r'id="ranking-container"[^>]*right:\s*(\d+)px;\s*top:\s*(\d+)px', ov)
d = pos(r'id="dicegame-container"[^>]*left:\s*(\d+)px;\s*top:\s*(\d+)px')
chk('게이지 자리를 찾았다', g is not None, g)
chk('엑셀판이 오른쪽 기준으로 붙어 있다 (사람이 늘어도 막대를 안 덮게)',
    rmm is not None, rmm.group(0)[:60] if rmm else '못 찾음')
chk('주사위판 자리를 찾았다', d is not None, d)
mm = re.search(r'const GAP = (\d+), MAXW = (\d+), MAXH = (\d+), CELL_CAP = (\d+)', ov)
chk('주사위 칸 크기 한계를 찾았다', mm is not None)

if g and rmm and d and mm and mh:
    gap, maxw, maxh, cap = (int(x) for x in mm.groups())
    cell = max(40, min(cap, (maxw - gap * 7) // 8, (maxh - gap * 4) // 5))
    dw, dh = 8 * cell + gap * 7 + 20, 5 * cell + gap * 4 + 20
    rank_right = W - int(rmm.group(1))
    box = {
        '머리줄': (hx, hy, hx + hw, hy + hh),
        '게이지': (g[0], g[1], g[0] + rail_w + 2, g[1] + rail_h + 2),   # 테두리 1px 씩
        '엑셀판': (rank_right - RANK_W, int(rmm.group(2)),
                rank_right, int(rmm.group(2)) + RANK_H),
        '주사위판': (d[0], d[1], d[0] + dw, d[1] + dh),
    }
    for k, (l, t, r, b) in box.items():
        chk('%s 이 안전지대 안이다' % k,
            l >= 0 and r <= W and t >= SAFE_TOP and b <= SAFE_BOT,
            '가로 %d~%d · 세로 %d~%d' % (l, r, t, b))
    names = list(box)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            (l1, t1, r1, b1), (l2, t2, r2, b2) = box[names[i]], box[names[j]]
            hit = not (r1 <= l2 or l1 >= r2 or b1 <= t2 or t1 >= b2)
            chk('%s 과 %s 이 안 겹친다' % (names[i], names[j]), not hit,
                '세로 %d~%d / %d~%d' % (t1, b1, t2, b2) if hit else '')
    # 말은 칸 위로 16px 튀어나온다 (판 여백 10px 이 그 중 10 을 먹는다)
    chk('주사위 말이 엑셀판 아래로 내려온다',
        d[1] + 10 - 16 >= box['엑셀판'][3],
        '말 꼭대기 %d / 엑셀판 아래끝 %d' % (d[1] + 10 - 16, box['엑셀판'][3]))

print()
print('=' * 74)
print('④ 전광판 쌍 — 합치지 않고 자리만 바로잡았는가')
print('=' * 74)
t1 = pos(r'id="ticker_top-container"[^>]*left:\s*(\d+)px;\s*top:\s*(\d+)px')
t2 = pos(r'id="ticker_bottom-container"[^>]*left:\s*(\d+)px;\s*top:\s*(\d+)px')
chk('상단 전광판 자리를 찾았다', t1 is not None, t1)
chk('하단 전광판 자리를 찾았다', t2 is not None, t2)
chk('둘 다 남아 있다 (합치면 갈라지는 연출이 죽는다)',
    'revealTickerSplit' in ov and "'ticker_top', 'ticker_bottom'" in ov)
if t1 and t2:
    for nm, p in (('상단', t1), ('하단', t2)):
        chk('%s 전광판이 안전지대 안이다' % nm,
            p[0] >= 0 and p[0] + W <= W + 1 and p[1] >= SAFE_TOP and p[1] + TICKER_H <= SAFE_BOT,
            '가로 %d~%d · 세로 %d~%d' % (p[0], p[0] + W, p[1], p[1] + TICKER_H))
    chk('둘 사이에 큰 배너 자리가 남는다 (400px 이상)',
        t2[1] - (t1[1] + TICKER_H) >= 400, '%dpx' % (t2[1] - (t1[1] + TICKER_H)))

print()
print('=' * 74)
print('⑤ 못 박은 자리를 배치 파일이 덮어쓰지 않는가')
print('=' * 74)
# ⚠️ applyLayout 안의 목록만 본다. 방송 시작/종료 때 위젯을 보였다 숨겼다 하는
#    다른 목록(['ranking','gauge','account',...])도 같은 모양이라 그걸 잡으면 안 된다.
_al = ov[ov.find('function applyLayout'):]
_al = _al[:_al.find('function ', 30)]
mm = re.search(r"\[('[^\]]*)\]\.forEach\(id => \{", _al)
lst = mm.group(1) if mm else ''
chk('applyLayout 목록을 찾았다', bool(lst), lst[:70])
for w in ('gauge', 'ranking', 'account', 'ticker_top', 'ticker_bottom', 'notice'):
    chk("'%s' 가 목록에서 빠졌다" % w, ("'" + w + "'") not in lst)
chk('번외 모드에서 엑셀판이 비켜준다 (오른쪽 기준이라 left 로는 안 밀린다)',
    "rankEl.style.right = 'auto'" in ov and "rankEl.style.left = '-800px'" in ov)
# ⚠️ 번외 점수판(702×68)과 퇴근빵(586×64)은 엑셀판 자리를 대신 쓴다. 예전에는 그
#    자리를 배치 파일의 ly['ranking'] 에서 읽었는데, 엑셀판 자리를 못 박은 뒤로
#    그 값은 옛 자리(362,178)라 서로 어긋난다.
chk('엑셀판 자리를 상수 하나로 쓴다', "const RANK_RIGHT = '42px', RANK_TOP = '167px'" in ov)
for nm, var in (('번외 점수판', 'extraEl'), ('퇴근빵', 'raceEl')):
    chk('%s 도 같은 자리 상수를 쓴다' % nm,
        (var + ".style.top = RANK_TOP") in ov and (var + ".style.right = RANK_RIGHT") in ov)
# 주석에 남은 설명까지 잡으면 안 된다 — 실제로 값을 꺼내 쓰는 모양만 본다.
chk('배치 파일의 옛 엑셀판 자리를 더는 안 읽는다',
    re.search(r"ly\['ranking'\]\s*[.|)]", ov) is None)

print()
print('=' * 74)
print('⑥ 게임 중에는 금액 딱지를 숨기는가')
print('=' * 74)
chk('숨김 규칙이 있다', 'body.game-on .goal-rail-tip' in ov)
chk('게임 넷을 다 본다 (주사위·룰렛·슬롯·시그뒤집기)', 'syncGameOn' in ov
    and all(("'" + k + "'") in ov for k in ('dicegame', 'roulette', 'slot', 'siggame')))
chk('컨테이너 변화를 지켜본다 (게임마다 켜는 자리가 다르다)', 'MutationObserver' in ov)
chk('인라인 값으로 판단한다 (계산값은 0.4초 전환 동안 옛 값이다)',
    "el.style.visibility === 'visible'" in ov)

print()
print('=' * 74)
print('⑦ 목표 달성 연출이 막대에 맞는가')
print('=' * 74)
chk('막대가 번쩍이는 규칙이 있다 (예전엔 JS 만 있고 CSS 가 없었다)',
    '@keyframes goalRailFlash' in ov and '.goal-rail.goal-flash' in ov)
mb = re.search(r'\.goal-banner \{[^}]*top:\s*(\d+)px', ov)
chk('알림 자리가 안전지대 안이다', mb and SAFE_TOP < int(mb.group(1)) < SAFE_BOT,
    (mb.group(1) + 'px') if mb else '못 찾음')
# ⚠️ scale(1.6) 은 무관한 타이머 폭발 연출에도 쓰인다 — 연출 함수 안만 본다.
fx = ov[ov.find('function triggerGoalCelebrationEffect'):]
_end = fx.find('\n        function ')
fx = fx[:_end] if _end > 0 else fx[:2000]
chk('연출 함수를 찾았다', 'goal-banner' in fx)
chk('게이지를 화면 한가운데로 옮기지 않는다 (막대는 1.6배면 화면을 넘는다)',
    'translate3d' not in fx and 'transformOrigin' not in fx and 'gauge-container' not in fx)
chk('되돌리기 타이머가 필요 없어졌다', 'goalCelebrationReturnTimer' not in ov)

print()
print('=' * 74)
print('⑧ 편집기가 같은 자리를 그리는가')
print('=' * 74)
me = re.search(r'id="gauge" data-id="gauge"[^>]*style="left:(\d+)px; top:(\d+)px', ad)
chk('편집기 게이지 자리가 방송판과 같다',
    me and g and (int(me.group(1)), int(me.group(2))) == g, (me.groups() if me else None, g))
me = re.search(r'id="account" data-id="account"[^>]*style="left:(\d+)px; top:(\d+)px', ad)
chk('편집기 계좌가 머리 줄 자리에 있다',
    me and (int(me.group(1)), int(me.group(2))) == (hx, hy), (me.groups() if me else None, (hx, hy)))
me = re.search(r'id="ranking" data-id="ranking"[^>]*style="left:(\d+)px; top:(\d+)px', ad)
if me and rmm:
    chk('편집기 엑셀판 자리가 방송판과 같다',
        (int(me.group(1)), int(me.group(2))) == (rank_right - RANK_W, int(rmm.group(2))),
        (me.groups(), (rank_right - RANK_W, rmm.group(2))))
for wid in ('gauge', 'account', 'ranking', 'ticker_top', 'ticker_bottom', 'notice'):
    chk('편집기 %s 이 고정 표시다' % wid,
        re.search(r'id="%s" data-id="%s" data-pinned' % (wid, wid), ad) is not None)
chk('고정된 것은 못 끈다', 'if (widgetEl.dataset.pinned) return;' in ad)
chk('고정된 것은 배치 파일에 저장하지 않는다', 'if (el.dataset.pinned) return;' in ad)
chk('고정된 것은 기본값 되돌리기에도 안 움직인다', ad.count('el.dataset.pinned') >= 3)
chk('편집기 게이지도 세로 막대다', '.goal-rail-mini' in ad)
chk('편집기 계좌도 한 줄이다', '.acc-ico' in ad and '.acc-who' in ad)

print()
print('=' * 74)
print('⑨ 게임·연출이 모두 게임 자리 안인가')
print('=' * 74)
"""게임 자리 = x 6~1036 · y 307~956.
   저장된 배치로는 룰렛이 168~999(채팅 39px 침범), 슬롯이 680~1040(80px 침범),
   후원 순위가 850~1112(가로 32px 넘침) 이었다. 전부 여기 안으로 못 박았다."""
GX, GY, GR, GB = 6, 307, 1036, 956
# 화면에서 직접 잰 크기 (배율 1 기준)
SIZE = {'roulette': (660, 740), 'slot': (660, 360), 'match': (466, 147),
        'siggame': (700, 74), 'donor-rank': (262, 62), 'sig-tally': (228, 62)}
mrf = re.search(r'const ROULETTE_FIT = ([\d.]+);', ov)
chk('룰렛 배율을 상수로 못 박았다 (배치 파일의 1.123 이면 채팅에 잠긴다)',
    mrf is not None, mrf.group(1) if mrf else '못 찾음')
rfit = float(mrf.group(1)) if mrf else 1.0
chk('룰렛 켤 때 배율에 1.1 을 또 곱하지 않는다 (그래서 56px 넘쳤었다)',
    'ROULETTE_FIT * 1.1' not in ov)
for wid, (w, h) in SIZE.items():
    mm = re.search(r'id="%s-container"[^>]*left:\s*(-?\d+)px;\s*top:\s*(-?\d+)px' % wid, ov)
    if not mm:
        chk('%s 자리를 찾았다' % wid, False, '못 찾음')
        continue
    x, y = int(mm.group(1)), int(mm.group(2))
    sc = rfit if wid == 'roulette' else 1.0
    r, bm = x + round(w * sc), y + round(h * sc)
    chk('%s 이 게임 자리 안이다' % wid, x >= GX and r <= GR and y >= GY and bm <= GB,
        '%d~%d / %d~%d' % (x, r, y, bm))
mm = re.search(r"\[('popup'[^\]]*)\]\.forEach\(id => \{", ov)
chk('편집기로 옮길 수 있는 건 잠깐 뜨는 것들만 남았다', mm is not None,
    mm.group(1) if mm else '못 찾음')

print()
print('=' * 74)
print('⑩ 편집기에 안전지대 안내선이 있는가')
print('=' * 74)
"""게이지가 y 1598, 안내 전광판이 y 1680 — 폰에서 안 보이는 자리로 내려간
   근본 원인은 편집기에 안전지대 표시가 하나도 없었다는 것이다."""
for nm, pat in (('채널줄', r'zone-dead[^>]*top:0; height:115px'),
                ('안전지대', r'zone-safe[^>]*top:115px; height:845px'),
                ('채팅', r'zone-chat[^>]*top:960px; height:422px'),
                ('고정 UI', r'zone-dead[^>]*top:1382px')):
    chk('편집기에 %s 구역이 그려진다' % nm, re.search(pat, ad) is not None)
chk('안전지대 경계선을 긋는다', ad.count('zone-line') >= 3)
mg = re.search(r'\.zone-game \{[^}]*left:\s*(\d+)px; top:\s*(\d+)px; '
               r'width:\s*(\d+)px; height:\s*(\d+)px', ad)
chk('편집기에 게임 자리가 그려진다', mg is not None, mg.group(0)[-60:] if mg else '못 찾음')
if mg:
    gx, gy, gw, gh = (int(x) for x in mg.groups())
    chk('편집기 게임 자리가 방송판과 같다', (gx, gy, gx + gw, gy + gh) == (GX, GY, GR, GB),
        (gx, gy, gx + gw, gy + gh))

print()
print('=' * 74)
print('⑪ 옛 흔적이 안 남았는가')
print('=' * 74)
for gone in ('excel-gauge-box', 'gauge-header', 'gauge-total', 'goal-bar-bg', 'goal-bar-fill',
             'acc-header'):
    chk('overlay 에 %s 가 없다' % gone, gone not in ov)
    chk('admin 에 %s 가 없다' % gone, gone not in ad)
chk('overlay 에 쓰이지 않는 잠금 플래그가 없다', 'isGoalCelebrating' not in ov)

print()
print('=' * 74)
print('통과 %d · 실패 %d' % (len(OK), len(BAD)))
for n in BAD:
    print('   [실패] ' + n)
print('=' * 74)
