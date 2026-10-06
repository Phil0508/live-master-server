# -*- coding: utf-8 -*-
"""💡 조명(시그니처가 나오는 동안 화면 테두리 네온 · 아우디 LED) · ✨ 테마 연출 스위치.

옛 프로그램: 조종실 '조명' 탭(controller.html triggerNeon · updateNeonSpeed · 색 슬롯 9칸) → 상태 effect_trigger {time, color}
           + neon_speed + saved_colors · 방송판(overlay.html)이 globalNeon · globalAudi 를 **화면마다 따로** 들고 있었다.
           그래서 방송판을 새로 고치면 아우디가 꺼진 채로 돌아오거나(토글이라 되살리지 못했다), 창마다 달랐다.
v2: 서버가 '지금 조명' 을 들고 있다(lights 조각, 공개) — 어느 창을 새로 열어도 같은 조명이 켜진다.

lights 조각(공개)
  color   지금 네온 — '#rrggbb'(단색) · 'RAINBOW'(무지개) · 'OFF'(끔)
  audi    아우디 LED 켜짐?
  speed   조명 속도(초, 0.3~5.0 · 기본 1.5) — 방송판: 네온 한 바퀴 = speed×2초, 아우디 한 번 = speed×0.56초(옛 계산 그대로)
  colors  색 슬롯 9칸(조종실 [켜기] 단추) — 옛 saved_colors 기본값 그대로
  at      마지막으로 바꾼 시각(ms)
look.fx   ✨ 테마 연출(테마를 입었을 때 후원 알림 · 최고 기록 · 핀볼 우승에 테마 모양 입자) — 없으면 켜진 것(옛 theme_fx_enabled !== false)

⚠️ 조명은 **시그니처가 나오는 동안만** 보인다(옛 reaction_mode 와 같다 — 방송판이 정한다). 꺼 두는 것은 서버가 아니라 방송판의 몫.
⚠️ 방송을 시작 · 끝내도 그대로 둔다 — 옛 BROADCAST_KEEP_KEYS 가 neon_speed · saved_colors · theme_fx_enabled 를 남겼다.
   (색 · 아우디도 남긴다: 옛 방송판은 켜 둔 창이면 방송을 넘어서도 조명을 기억했다 — 새로 고칠 때만 잃었다.)

명령
  lights.color {color}           옛 조명 단추 하나와 같다: '#hex' · 'RAINBOW' → 그 네온 / 'AUDI' → 아우디 뒤집기 / 'OFF' → 네온 · 아우디 둘 다 끔
  lights.set {color?, audi?, speed?}   하나씩 맞추기(color 는 '#hex' · 'RAINBOW' · 'OFF' — 여기서 OFF 는 네온만 끈다)
  lights.slot {index, color}     색 슬롯 한 칸 바꾸기(0~8, '#hex' 만)
  look.fx {on}                   ✨ 테마 연출 켜기 · 끄기
"""
import re

from ..bus import CommandError, command
from ..state import slice_

# 옛 server.py DEFAULT_STATE['saved_colors'] 그대로(9칸)
DEFAULT_COLORS = ['#ff0055', '#00e5ff', '#ff9100', '#d500f9', '#00ff00', '#ffff00', '#ff0000', '#0000ff', '#ffffff']
SPEED_MIN, SPEED_MAX, SPEED_DEFAULT = 0.3, 5.0, 1.5      # 옛 조종실 슬라이더 min 0.3 · max 5.0 · 기본 1.5
MODES = ('RAINBOW', 'OFF')

slice_('lights', True, lambda: {'color': 'OFF', 'audi': False, 'speed': SPEED_DEFAULT, 'colors': list(DEFAULT_COLORS), 'at': 0})

_HEX = re.compile(r'^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$')


def norm_hex(v):
    """'#FF0055' · 'ff0055' · '#f05' → '#ff0055'. 색 글자가 아니면 None(이름 색 'red' 같은 것은 안 받는다)."""
    m = _HEX.match(str(v if v is not None else '').strip())
    if not m:
        return None
    h = m.group(1).lower()
    if len(h) == 3:
        h = ''.join(c * 2 for c in h)
    return '#' + h


def _neon(v, allow_audi):
    """조명 값 하나 → '#rrggbb' · 'RAINBOW' · 'OFF' (· 'AUDI'). 못 알아보면 CommandError."""
    s = str(v if v is not None else '').strip()
    up = s.upper()
    if up in MODES or (allow_audi and up == 'AUDI'):
        return up
    h = norm_hex(s)
    if h is None:
        raise CommandError('조명 색을 못 알아봤어요: %s — #ff0055 같은 색 글자나 RAINBOW · AUDI · OFF 만 됩니다' % (s[:20] or '(빈칸)'))
    return h


def norm_speed(v):
    """속도(초) — 숫자가 아니면 거절, 범위 밖이면 끝으로 붙인다. 0.1초 단위(옛 슬라이더 step 0.1)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise CommandError('조명 속도는 숫자(초)여야 합니다')
    if f != f:                                           # NaN
        raise CommandError('조명 속도가 숫자가 아닙니다')
    return round(max(SPEED_MIN, min(SPEED_MAX, f)), 1)


def _touch(ctx, L):
    L['at'] = int(ctx.now * 1000)


@command('lights.color')
def lights_color(ctx, data):
    """옛 effect_trigger 와 같은 뜻 — 단추 하나 = 이것 하나. 스트림덱 /api/streamdeck/neon 도 이 명령을 부른다."""
    c = _neon(data.get('color'), allow_audi=True)
    L = ctx.edit('lights')
    if c == 'OFF':                       # 옛 'OFF' — 네온 · 아우디 둘 다
        L['color'], L['audi'] = 'OFF', False
    elif c == 'AUDI':                    # 옛 'AUDI' — 누를 때마다 뒤집기(네온 색은 그대로)
        L['audi'] = not L.get('audi')
    else:
        L['color'] = c
    _touch(ctx, L)
    ctx.notes['lights'] = {'color': L['color'], 'audi': L['audi']}


@command('lights.set')
def lights_set(ctx, data):
    L = ctx.edit('lights')
    if not any(k in data for k in ('color', 'audi', 'speed')):
        raise CommandError('바꿀 것(color · audi · speed)을 적어 주세요')
    if 'color' in data:
        L['color'] = _neon(data.get('color'), allow_audi=False)
    if 'audi' in data:
        L['audi'] = bool(data.get('audi'))
    if 'speed' in data:
        L['speed'] = norm_speed(data.get('speed'))
    _touch(ctx, L)


@command('lights.slot')
def lights_slot(ctx, data):
    try:
        i = int(data.get('index'))
    except (TypeError, ValueError):
        raise CommandError('몇 번째 칸인지(index 0~8) 적어 주세요')
    if not 0 <= i < len(DEFAULT_COLORS):
        raise CommandError('색 칸은 0~8 번까지입니다', 404)
    h = norm_hex(data.get('color'))
    if h is None:
        raise CommandError('색은 #ff0055 같은 글자로 적어 주세요')
    L = ctx.edit('lights')
    cols = fix_colors(L.get('colors'))
    cols[i] = h
    L['colors'] = cols
    # ⚠️ 켜 둔 네온 색은 안 바꾼다(옛 것과 같다) — 새 색은 그 칸의 [켜기] 를 눌러야 방송판에 나간다
    _touch(ctx, L)


@command('look.fx')
def look_fx(ctx, data):
    if 'on' not in data:
        raise CommandError('켤지(on: true) 끌지(on: false) 적어 주세요')
    ctx.edit('look')['fx'] = bool(data.get('on'))


def fix_colors(v):
    """색 슬롯을 9칸 '#rrggbb' 로 — 모자라면 기본값으로 채운다(옛 6칸 → 9칸 옮기기와 같다), 이상한 칸은 기본값."""
    src = v if isinstance(v, list) else []
    out = []
    for i, d in enumerate(DEFAULT_COLORS):
        out.append((norm_hex(src[i]) if i < len(src) else None) or d)
    return out


def import_old(ctx, old):
    """admin.import_old 가 부른다 — 옛 상태에서 조명 속도 · 색 슬롯 · 테마 연출을 옮긴다. 옮긴 것 이름 목록을 돌려준다.
       (켜 둔 색 effect_trigger 는 옮기지 않는다 — 옛 것도 방송을 넘기면 지웠다)"""
    done = []
    if 'neon_speed' in old or 'saved_colors' in old:
        L = ctx.edit('lights')
        if 'neon_speed' in old:
            try:
                L['speed'] = norm_speed(old.get('neon_speed') or SPEED_DEFAULT)      # 옛 방송판: d.neon_speed || 1.5
            except CommandError:
                pass
        if isinstance(old.get('saved_colors'), list):
            L['colors'] = fix_colors(old['saved_colors'])
        done.append('조명 속도 · 색')
    if 'theme_fx_enabled' in old:
        ctx.edit('look')['fx'] = old.get('theme_fx_enabled') is not False
        done.append('테마 연출')
    return done
