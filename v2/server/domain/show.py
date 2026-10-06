# -*- coding: utf-8 -*-
"""📺 무대 · 고정 자리 · 알림 · 공지 · 계좌 · 테마 — 방송판에 '무엇을 띄울지'.

show 조각(공개)
  stage   지금 무대에 오른 판 하나(None = 비어 있음). 옛 show.py 와 같은 이름들.
  ret     잠깐 올라온 판(룰렛 · 슬롯)이 끝나면 돌아갈 무대
  hud     고정 자리 켜고 끄기(점수판 · 게이지 · 계좌 · 공지 · 후원 순위 · 시그 순위 · 최고 후원 · 모금함)
  alerts  알림 켜고 끄기(후원 팝업 · 1등 탈환 · 시그 제목 · 1천~9천 띠)
notice 조각(공개)  msgs[여러 줄] · period(초) · speed(px/s) · now{ts, idx}(진행자가 지금 띄운 것)
account 조각(공개) bank · acc_num · name
look 조각(공개)    theme(방송판 테마 이름)

⚠️ 옛 서버는 *_enabled 스위치 수십 개 + show 를 같이 들고 다녔다. v2 는 show 하나뿐이다.
"""
from ..bus import CommandError, command
from ..state import slice_
from . import session as ses

STAGES = ('match', 'pinball', 'dicegame', 'siggame', 'roulette', 'slot', 'home_race', 'hell', 'quiz')
TEMP_STAGES = ('roulette', 'slot')
HUD_DEFAULT = {'ranking': True, 'gauge': True, 'account': True, 'notice': False, 'donor_rank': False,
               'sig_tally': False, 'best': False, 'fundjar': False}
ALERT_KEYS = ('popup', 'takeover', 'reaction_title', 'small')
NOTICE_MAX, NOTICE_LEN = 30, 120

slice_('show', True, lambda: {'stage': None, 'ret': None, 'hud': dict(HUD_DEFAULT), 'alerts': {k: True for k in ALERT_KEYS}})
slice_('notice', True, lambda: {'msgs': ['계좌로 보내실 때 *닉네임+플레이어* 를 적어 주세요'], 'period': 300, 'speed': 130, 'now': None})
slice_('account', True, lambda: {'bank': '', 'acc_num': '', 'name': ''})
slice_('look', True, lambda: {'theme': 'default'})


def set_stage(ctx, stage, temp=False):
    """무대에 올린다(None 이면 비운다). 잠깐 올라오는 판(룰렛 · 슬롯)은 원래 무대를 기억한다."""
    s = ctx.edit('show')
    if stage is not None and stage not in STAGES:
        raise CommandError('모르는 판입니다: %s' % stage)
    cur = s['stage']
    if temp and stage in TEMP_STAGES:
        if cur not in TEMP_STAGES:
            s['ret'] = cur
    else:
        s['ret'] = None
    s['stage'] = stage
    return cur


def end_temp(ctx, stage):
    s = ctx.edit('show')
    if s['stage'] != stage:
        return None
    s['stage'], s['ret'] = (s['ret'] if s['ret'] in STAGES else None), None
    return s['stage']


@command('show.stage')
def show_stage(ctx, data):
    set_stage(ctx, data.get('stage') or None)


@command('show.hud')
def show_hud(ctx, data):
    k = data.get('key')
    s = ctx.edit('show')
    if k not in s['hud']:
        raise CommandError('모르는 자리입니다: %s' % k)
    s['hud'][k] = bool(data.get('on'))
    if k == 'fundjar' and 'fundjar' in ctx.bus.state.slices:
        ctx.edit('fundjar')['enabled'] = s['hud'][k]          # 모금함 켜기와 같은 스위치


@command('show.alert')
def show_alert(ctx, data):
    k = data.get('key')
    if k not in ALERT_KEYS:
        raise CommandError('모르는 알림입니다: %s' % k)
    ctx.edit('show')['alerts'][k] = bool(data.get('on'))


def _msg(t):
    t = ' '.join(str(t or '').split())
    if not t:
        raise CommandError('공지 글을 적어 주세요')
    return t[:NOTICE_LEN]


@command('notice.add')
def notice_add(ctx, data):
    n = ctx.edit('notice')
    if len(n['msgs']) >= NOTICE_MAX:
        raise CommandError('공지는 %d개까지입니다' % NOTICE_MAX)
    n['msgs'].append(_msg(data.get('text')))


@command('notice.edit')
def notice_edit(ctx, data):
    n = ctx.edit('notice')
    i = int(data.get('index', -1))
    if not 0 <= i < len(n['msgs']):
        raise CommandError('없는 공지입니다', 404)
    n['msgs'][i] = _msg(data.get('text'))


@command('notice.remove')
def notice_remove(ctx, data):
    n = ctx.edit('notice')
    i = int(data.get('index', -1))
    if not 0 <= i < len(n['msgs']):
        raise CommandError('없는 공지입니다', 404)
    n['msgs'].pop(i)


@command('notice.move')
def notice_move(ctx, data):
    n = ctx.edit('notice')
    i, d = int(data.get('index', -1)), int(data.get('dir', 0))
    j = i + (1 if d > 0 else -1)
    if not (0 <= i < len(n['msgs']) and 0 <= j < len(n['msgs'])):
        raise CommandError('옮길 수 없습니다')
    n['msgs'][i], n['msgs'][j] = n['msgs'][j], n['msgs'][i]


@command('notice.every')
def notice_every(ctx, data):
    n = ctx.edit('notice')
    if 'period' in data:
        n['period'] = max(20, min(3600, int(data.get('period') or 300)))   # 옛 방송판 최소 20초
    if 'speed' in data:
        n['speed'] = max(40, min(400, int(data.get('speed') or 130)))


@command('notice.now')
def notice_now(ctx, data):
    """진행자가 '지금 띄우기' — 방송판은 now.ts 가 바뀌면 그 줄을 바로 흘린다."""
    n = ctx.edit('notice')
    i = int(data.get('index', 0))
    if data.get('text'):
        n['now'] = {'ts': int(ctx.now * 1000), 'idx': -1, 'text': _msg(data.get('text'))}
        return
    if not 0 <= i < len(n['msgs']):
        raise CommandError('없는 공지입니다', 404)
    n['now'] = {'ts': int(ctx.now * 1000), 'idx': i}


@command('account.set')
def account_set(ctx, data):
    a = ctx.edit('account')
    for k in ('bank', 'acc_num', 'name'):
        if k in data:
            a[k] = ' '.join(str(data.get(k) or '').split())[:40]


@command('look.theme')
def look_theme(ctx, data):
    ctx.edit('look')['theme'] = str(data.get('theme') or 'default')[:30]


def _reset(ctx, data):
    s = ctx.edit('show')
    s['stage'], s['ret'] = None, None
    ctx.edit('notice')['now'] = None


ses.ON_START.append(_reset)
ses.ON_END.append(_reset)


# ── 위젯 자리(편집기) — 방송판 layers.js 의 기본 자리를 덮어쓴다 ──
slice_('layout', True, lambda: {'widgets': {}})
LAYOUT_KEYS = ('x', 'y', 'scale')


@command('layout.set')
def layout_set(ctx, data):
    """한 위젯의 자리 · 크기. {id, x?, y?, scale?} — 숫자만, 화면(1080×1920) 밖으로 크게 못 나가게."""
    wid = str(data.get('id') or '').strip()[:40]
    if not wid:
        raise CommandError('위젯 이름이 필요합니다')
    w = ctx.edit('layout')['widgets'].setdefault(wid, {})
    for k, lo, hi in (('x', -540, 1620), ('y', -960, 2880), ('scale', 0.2, 4.0)):
        if k in data:
            try:
                v = float(data[k])
            except (TypeError, ValueError):
                raise CommandError('%s 는 숫자여야 합니다' % k)
            if v != v:                                  # NaN
                raise CommandError('%s 가 숫자가 아닙니다' % k)
            w[k] = round(max(lo, min(hi, v)), 3)


@command('layout.reset')
def layout_reset(ctx, data):
    """한 위젯(id) 또는 전부를 기본 자리로."""
    wid = data.get('id')
    lay = ctx.edit('layout')
    if wid:
        lay['widgets'].pop(str(wid), None)
    elif data.get('all') is True:
        lay['widgets'] = {}
    else:
        raise CommandError('어느 위젯인지(id) 적거나, 전부 되돌릴 때는 all 을 켜 주세요')
