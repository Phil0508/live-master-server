# -*- coding: utf-8 -*-
"""📐 옛 위젯 자리 옮기기 · 🏺 모금함 깃발 왼쪽/오른쪽 — 옛 좌표를 v2 자리 체계(layers.js 기준점)로 바꾼다.

옛 자리(배치 파일 layout.json · 옛 편집기 세이브 슬롯의 layout · 옛 상태에 담긴 layout):
  {위젯: {x_px, y_px, scale}, '__v': 2, '__free': bool}
  옛 방송판(overlay.html applyLayout) 규칙 그대로 읽는다:
    - 모든 칸이 **왼쪽 위** 기준이다(left = x_px · top = y_px · transform-origin top left · scale).
    - '__v' 가 2 미만인 옛 파일은 통째로 무시했다(게이지 y=1598 같은 못된 값) → 여기서도 안 옮긴다.
    - '__free' 가 아니면 위아래 안전지대(115 ~ 954) · 가로(0 ~ 1080) 안으로 붙잡았다(fit) → 붙잡은 뒤 바꾼다.
    - 전광판(notice)은 코드가 자리를 정했다 → 안 옮긴다.
    - 룰렛은 배율을 안 읽었다(ROULETTE_FIT 0.87 고정) → 자리만.
    - 주사위 점수 띠가 기본 자리(6, 191 · 1배)로 적혀 있으면 '안 잡은 것'(판을 따라간다)으로 봤다 → 안 옮긴다.
v2 자리 = layout 조각 widgets[칸] = {x, y, scale} — x · y 는 그 칸의 **기준점(anchor)** 자리(v2/web/overlay/layers.js · groups/*.js).
  tl(왼쪽 위) : x = 옛 x                       — 그대로
  tr(오른쪽 위): x = 옛 x + 폭 × 배율           — 점수판 · 계좌 · 퇴근빵 · 지옥탈출(오른쪽 끝이 기준이라 판이 왼쪽으로 자란다)
  tc(위 가운데): x = 옛 x + 폭 × 배율 ÷ 2       — 점수 팝업 · 1등 탈환 · 주사위판
  y 는 모두 '위' 기준이라 그대로. 배율은 기준점을 붙박고 커진다(v2 place()) — 왼쪽 위 모서리가 옛 자리와 같아진다.
  폭(배율 1): REF_W(헤드리스 크롬으로 v2 방송판을 재서 적은 값) · 주사위판은 칸 수로 계산(v2 dice.js build 와 같은 식) ·
              계좌처럼 글자 길이에 따라 폭이 바뀌는 칸은 편집기가 잰 값(sizes)이 오면 그걸 쓴다.
  예) 운영 배치 점수판 (10, 263, 0.88) → v2 ranking (10 + 878 × 0.88 = 782.64, 263, 0.88) — 왼쪽 끝이 10 그대로.

명령
  layout.import_old {layout, sizes?}  옛 배치 → layout 조각. 옛 칸이 가리키는 v2 칸은 전부 옛 것대로(파일에 없던 칸은 기본 자리로),
                                      v2 에만 있는 칸(퀴즈 · 룰렛 당첨 글씨 …)은 안 건드린다.
  fundjar.side {side:'left'|'right'}  옛 /api/fundjar/side — 깃발을 점수판 왼쪽/오른쪽에 한 줄로 붙인다. 왼쪽이면 점수판이 깃발 폭만큼 비킨다.
"""
from ..bus import CommandError, command

CANVAS_W, SAFE_TOP, SAFE_BOT = 1080, 115, 954

# 옛 방송판이 읽던 칸(overlay.html applyLayout 의 LAY_IDS) → v2 칸(layers.js id)
OLD_TO_V2 = {
    'ranking': ('ranking',), 'gauge': ('gauge',),
    # 🏦 옛 계좌는 편집기에서 잡으면 판 아래 · 머리 줄 어디로도 안 갔다(__accLaid) → v2 의 두 칸을 같은 자리에
    'account': ('account', 'accountHead'),
    'match': ('match',), 'roulette': ('roulette',), 'slot': ('slot',), 'dicegame': ('dicegame',), 'dgscore': ('dgscore',),
    'donor-rank': ('donorRank',), 'sig-tally': ('sigTally',), 'siggame': ('siggame',),
    # 🏃 옛 퇴근빵 칸(home-race)은 지옥탈출도 같이 썼다
    'home-race': ('homeRace', 'hell'),
    'popup': ('scorePopup',), 'takeover': ('takeover',), 'karaoke': ('karaoke',), 'acct_video': ('acctVideo',),
    'fundjar': ('fundjar',), 'pinball': ('pinball',), 'best': ('best',),
}
CODE_OWNED = ('notice',)          # 옛 LAY_CODE_OWNED — 코드가 자리를 정했다
NO_SCALE = ('roulette',)          # 옛 showRouletteWidget 이 배율을 0.87 로 못 박았다
V2_IDS = tuple(sorted({v for vs in OLD_TO_V2.values() for v in vs}))

# v2 칸의 기준점 — ⚠️ layers.js · groups/*.js 와 같아야 한다(검사 test_oldlayout 이 그 파일을 읽어 맞대 본다). 없으면 tl.
ANCHOR = {'ranking': 'tr', 'account': 'tr', 'homeRace': 'tr', 'hell': 'tr',
          'scorePopup': 'tc', 'takeover': 'tc', 'dicegame': 'tc'}
# 배율 1 일 때 폭(px) — 10-17 헤드리스 크롬으로 v2 방송판을 잰 값(점수판 878 은 옛 features/layout.py _RANK_W 와 같다).
#   점수 팝업 · 1등 탈환은 글자만큼 폭이 바뀐다 → v2 기본 자리를 만들 때 쓴 폭(옛 342 → 540, 328 → 540)으로 —
#   그래야 옛 기본 자리가 v2 기본 자리로 그대로 온다.
#   계좌도 글자만큼(은행 · 예금주 · 번호) — 편집기가 잰 값이 오면 그걸 쓴다. 여기 값은 '기업은행 · 엔젤컴퍼니 · 123-456789-01-012' 를 잰 것.
REF_W = {'ranking': 878, 'account': 636, 'homeRace': 946, 'hell': 950, 'scorePopup': 396, 'takeover': 424}
MEASURED_OK = ('account', 'homeRace', 'hell')      # 편집기가 잰 폭을 믿는 칸(글자 · 내용으로 폭이 바뀌는데 지금 그려져 있는 것)

# 주사위판 폭 — v2 widgets/games/dice.js build() 와 같은 식(DG_TOP 307 · DG_BOTTOM 1030 · GAP 6 · MAXW 1010 · MAXH 810 · 칸 40~160 · 안쪽 여백 10×2)
DG_GAP, DG_MAXW, DG_MAXH, DG_CAP, DG_ROOM, DG_PAD = 6, 1010, 810, 160, 1030 - 307, 20


def dice_width(cols, rows):
    cols = max(1, int(cols or 7))
    rows = max(1, int(rows or 5))
    room_h = min(DG_MAXH, max(300, DG_ROOM))
    cell = max(40, min(DG_CAP, (DG_MAXW - DG_GAP * (cols - 1)) // cols, (room_h - DG_GAP * (rows - 1)) // rows))
    return cols * cell + DG_GAP * (cols - 1) + DG_PAD


def _num(v, dflt=0.0):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return dflt
    return dflt if f != f or f in (float('inf'), float('-inf')) else f


def is_old_layout(d):
    """옛 배치 모양인가 — {칸: {x_px …}} 가 하나라도 있으면."""
    return isinstance(d, dict) and any(isinstance(v, dict) and 'x_px' in v for k, v in d.items() if not str(k).startswith('__'))


def convert(old, sizes=None, dice=None, need_v=True):
    """옛 배치 → ({v2칸: {x, y, scale?}}, 알림 {'skipped': [(옛 칸, 까닭)], 'approx': [v2칸]}).
       sizes: {v2칸: {w}} 편집기가 잰 폭(MEASURED_OK 칸만 쓴다) · dice: (cols, rows) 주사위판 칸 수.
       옛 방송판도 안 읽던 파일(__v 2 미만)이면 ValueError — 세이브 슬롯은 need_v=False(옛 _cue_apply 가 불러올 때 __v=2 로 적었다)."""
    if not isinstance(old, dict):
        raise ValueError('배치 파일(JSON 사전)이 아니에요')
    if not is_old_layout(old):
        raise ValueError('옮길 위젯 자리가 없어요 — 옛 배치 파일(layout.json)이 맞나요?')
    if need_v and _num(old.get('__v'), 0) < 2:
        raise ValueError('옛 판(__v 2 미만) 배치 파일이에요 — 옛 방송판도 이 파일은 안 읽었어요. 옛 편집기에서 한 번 저장한 파일을 주세요')
    free = bool(old.get('__free'))
    sizes = sizes if isinstance(sizes, dict) else {}
    out, skipped, approx = {}, [], []
    for oid in sorted(k for k in old if not str(k).startswith('__')):
        c = old[oid]
        if oid in CODE_OWNED:
            skipped.append((oid, '코드가 자리를 정하는 칸(옛 것도 배치 파일을 안 읽었다)'))
            continue
        if oid not in OLD_TO_V2:
            skipped.append((oid, '옛 방송판이 안 읽던 칸'))
            continue
        if not isinstance(c, dict) or 'x_px' not in c:
            skipped.append((oid, '자리 값이 없음'))
            continue
        x, y = _num(c.get('x_px')), _num(c.get('y_px'))
        s = _num(c.get('scale'), 1.0) or 1.0
        if s <= 0:
            s = 1.0
        if oid == 'dgscore' and (x, y, s) == (6, 191, 1):
            skipped.append((oid, '기본 자리(판을 따라간다)'))
            continue
        if not free:                                  # 옛 fit — 붙잡은 뒤에 바꾼다
            x = min(max(x, 0), CANVAS_W)
            y = min(max(y, SAFE_TOP), SAFE_BOT)
        for vid in OLD_TO_V2[oid]:
            a = ANCHOR.get(vid, 'tl')
            if a == 'tl':
                nx = x
            else:
                m = sizes.get(vid) if vid in MEASURED_OK else None
                mw = _num((m or {}).get('w'), 0) if isinstance(m, dict) else 0
                if vid == 'dicegame':
                    w = dice_width(*(dice or (7, 5)))
                elif mw > 4:
                    w = mw
                else:
                    w = REF_W[vid]
                    if vid in MEASURED_OK:
                        approx.append(vid)
                nx = x + w * s if a == 'tr' else x + w * s / 2
            row = {'x': round(nx, 2), 'y': round(y, 2)}
            if vid not in NO_SCALE:
                row['scale'] = round(s, 3)
            out[vid] = _fence(row)
    return out, {'skipped': skipped, 'approx': approx}


def _fence(row):
    """layout.set 과 같은 울타리(show.py) — 화면 밖으로 크게 못 나가게."""
    lim = {'x': (-540, 1620), 'y': (-960, 2880), 'scale': (0.2, 4.0)}
    return {k: round(max(lim[k][0], min(lim[k][1], v)), 3) for k, v in row.items()}


def apply(ctx, widgets):
    """옛 칸이 가리키는 v2 칸은 전부 옛 것대로 — 바뀐 칸은 적고, 옛 파일에 없던 칸은 기본 자리로(옛 방송판도 그랬다)."""
    lay = ctx.edit('layout')['widgets']
    for vid in V2_IDS:
        if vid in widgets:
            lay[vid] = dict(widgets[vid])
        else:
            lay.pop(vid, None)


def _dice_now(ctx):
    g = ctx.read('dicegame') or {}
    return (g.get('cols') or 7, g.get('rows') or 5)


@command('layout.import_old')
def import_old(ctx, data):
    try:
        widgets, info = convert(data.get('layout'), data.get('sizes'), _dice_now(ctx))
    except ValueError as e:
        raise CommandError(str(e))
    if not widgets:
        raise CommandError('옮길 위젯 자리가 없어요 — %s' % (', '.join('%s(%s)' % t for t in info['skipped']) or '빈 파일'))
    apply(ctx, widgets)
    ctx.notes['moved'] = sorted(widgets)
    ctx.notes['skipped'] = ['%s — %s' % t for t in info['skipped']]
    ctx.notes['approx'] = sorted(set(info['approx']))


def import_from_state(ctx, old):
    """admin.import_old(옛 [💾 백업] 파일)에서 — 상태에 배치(layout)가 담겨 있으면 옮긴다. 옮긴 칸 수(없으면 0)."""
    ly = old.get('layout') if isinstance(old, dict) else None
    if not is_old_layout(ly):
        return 0
    try:
        widgets, _ = convert(ly, None, _dice_now(ctx))
    except ValueError:
        return 0
    if widgets:
        apply(ctx, widgets)
    return len(widgets)


def preset_layout(ctx, ly):
    """옛 세이브 슬롯의 layout → v2 슬롯 layout(슬롯에 있던 위젯만 — 불러올 때 그 위젯만 덮는다, 옛 _cue_apply).
       못 바꾸면 None(자리는 안 건드리는 슬롯으로)."""
    if not is_old_layout(ly):
        return None
    try:
        widgets, _ = convert(ly, None, _dice_now(ctx), need_v=False)
    except ValueError:
        return None
    return widgets or None


# ── 🏺 모금함 깃발 왼쪽 / 오른쪽 (옛 features/layout.py /api/fundjar/side, 대표님 10-03) ──
#    깃발(108×262)은 점수판(878×262 — 늘 두 칸이라 폭이 안 바뀐다)과 키가 같게 그렸다. 둘을 한 줄로 나란히 세우고 순서만 바꾼다.
#    깃발 배율 = 점수판 배율(키가 같게) · 사이 10 × 배율 · 같은 높이.
#    ⚠️ 왼쪽을 고르면 **점수판이 깃발 폭만큼 오른쪽으로 비킨다**(운영 배치는 점수판이 왼쪽 끝 10 에 붙어 있다).
#       오른쪽으로 돌아오면 점수판도 제자리로 온다 — 왕복해도 안 밀린다.
#    v2: 점수판 칸은 오른쪽 위 기준(x = 오른쪽 끝), 깃발 칸은 왼쪽 위 기준 → 셈은 옛 것처럼 '왼쪽 끝'으로 하고 적을 때만 바꾼다.
RANK_W, FLAG_W, EDGE = 878, 108, 6
RANK_DEFAULT = (1038.0, 167.0, 1.0)     # layers.js ranking — 오른쪽 끝 1038 · 위 167(옛 기본 '오른쪽 42 · 위 167')
SIDES = ('left', 'right')


def _rank_left(lay):
    """점수판 (왼쪽 끝, 위, 배율). 편집기에서 안 잡았으면 표의 기본 자리."""
    r = lay.get('ranking') if isinstance(lay.get('ranking'), dict) else {}
    rx, ry, rs = RANK_DEFAULT
    x = _num(r.get('x'), rx) if 'x' in r else rx
    y = _num(r.get('y'), ry) if 'y' in r else ry
    s = _num(r.get('scale'), rs) if 'scale' in r else rs
    s = s if s > 0 else 1.0
    return x - RANK_W * s, y, s


def side_now(lay):
    """지금 깃발이 점수판 어느 쪽에 붙어 있나 — 'left' · 'right' · 'free'(따로 놓임 · 기본 자리). 옛 _fj_side_now 그대로."""
    lay = lay if isinstance(lay, dict) else {}
    rx, ry, rs = _rank_left(lay)
    f = lay.get('fundjar') if isinstance(lay.get('fundjar'), dict) else None
    if not f or 'x' not in f:
        return 'free'
    fx, fy, fs = _num(f.get('x')), _num(f.get('y')), (_num(f.get('scale'), 1.0) or 1.0)
    if abs(fy - ry) > 40:
        return 'free'
    if 0 <= rx - (fx + FLAG_W * fs) <= 60:
        return 'left'
    if 0 <= fx - (rx + RANK_W * rs) <= 60:
        return 'right'
    return 'free'


def side_layout(lay, side):
    """깃발을 side 쪽에 붙인 점수판 · 깃발 자리(v2 기준점으로) — (ranking{x,y,scale}, fundjar{x,y,scale})."""
    lay = lay if isinstance(lay, dict) else {}
    rx, ry, rs = _rank_left(lay)
    rank_w, flag_w, gap = RANK_W * rs, FLAG_W * rs, round(10 * rs)
    # 둘이 차지하는 줄의 왼쪽 끝 — 깃발이 이미 왼쪽에 붙어 있으면 깃발 자리, 아니면 점수판 자리
    origin = _num(lay['fundjar'].get('x')) if side_now(lay) == 'left' else rx
    origin = max(0.0, min(origin, CANVAS_W - EDGE - (rank_w + gap + flag_w)))   # 화면 밖으로 안 나가게
    if side == 'right':
        rank_x, flag_x = origin, origin + rank_w + gap
    else:
        flag_x, rank_x = origin, origin + flag_w + gap
    rank = {'x': round(round(rank_x) + rank_w, 3), 'y': float(round(ry)), 'scale': rs}
    flag = {'x': float(round(flag_x)), 'y': float(round(ry)), 'scale': rs}
    return rank, flag


@command('fundjar.side')
def fundjar_side(ctx, data):
    side = data.get('side')
    if side not in SIDES:
        raise CommandError("side 는 'left' 나 'right' 여야 합니다")
    lay = ctx.edit('layout')['widgets']
    rank, flag = side_layout(lay, side)
    lay['ranking'] = dict(lay.get('ranking') or {}, **rank)
    lay['fundjar'] = flag
    ctx.notes.update({'side': side, 'ranking': rank, 'fundjar': flag})
