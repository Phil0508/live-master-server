# -*- coding: utf-8 -*-
"""🎱 구슬 핀볼 — 먼저(또는 끝까지 남아) 도착한 순서로 순위.

pinball 조각(공개): names · balls(펼친 구슬) · picks · rule(first|last) · map · skills · seed · round_id · running ·
                   started_at · result(도착 순서) · winners · cut('' 제대로 갈림 | 'stall' 구슬이 껴서 그 자리 순위로 끝냄)
⏱ 시간으로 판을 자르지 않는다(옛 10-11 커밋 992bf7c, 대표님 "제한 없이 끝까지"). 10-08 52판(구슬 186개 · 끝까지 남기)이
   멀쩡히 굴러가는데 180.0초에 잘려 2개가 남은 채 엉뚱한 우승자가 굳었다. 방송판은 끼인 판만(20초 정체, 물리 걸음으로 센다)
   끝내고 cut='stall' 로 알린다 → 우승 딱지 아랫줄이 '⏱ 구슬이 껴서 지금 자리로 결정' 이 된다.
⚠️ 물리는 방송판이 굴린다(같은 씨앗 → 모든 화면이 같은 경기). 그래서 결과는 방송판이 알려 주고,
   서버는 **지금 판(round_id)의 첫 보고 하나만** 받는다(옛 것과 같은 문지기).
옛 규칙 그대로: 구슬 800개까지 · '양양*3' = 구슬 3개 · 뽑기 1~(구슬-1)명 · 끝까지 남기는 뒤에서부터 뒤집어서 ·
맵 -1~3, 막아 둔 맵(2)은 우리 코스로 · 굴러가는 중엔 명단을 못 바꾼다.
"""
import random
import re

from ..bus import CommandError, command
from ..state import slice_
from . import session as ses
from . import show as sh

PINBALL_MAX, MAPS, BLOCKED, RULES = 800, 4, (2,), ('first', 'last')

slice_('pinball', True, lambda: {'names': [], 'balls': [], 'picks': 1, 'rule': 'first', 'map': -1, 'skills': True,
                                 'seed': 0, 'round_id': 0, 'running': False, 'started_at': 0, 'result': [], 'winners': [],
                                 'cut': ''})
CUTS = ('stall',)          # 방송판이 알릴 수 있는 '끊긴 까닭' — 모르는 값은 '' (제대로 갈림)으로 받는다(옛 것과 같다)


def names_of(raw):
    items = re.split(r'[,\n\r]+', raw) if isinstance(raw, str) else [str(x) for x in raw] if isinstance(raw, (list, tuple)) else []
    return [str(it).strip()[:20] for it in items if str(it).strip()][:PINBALL_MAX]


def expand(names):
    out = []
    for raw in names or []:
        nm, cnt = str(raw).strip(), 1
        m = re.search(r'\*\s*(\d+)\s*$', nm)
        if m:
            nm = nm[:m.start()].strip()
            cnt = max(1, min(PINBALL_MAX, int(m.group(1))))
        if not nm:
            continue
        for _ in range(cnt):
            out.append(nm[:20])
            if len(out) >= PINBALL_MAX:
                return out
    return out


def winners(order, rule, picks):
    if not order:
        return []
    k = max(1, min(int(picks or 1), len(order)))
    return list(reversed(order[len(order) - k:])) if rule == 'last' else order[:k]


def _map(v):
    try:
        v = int(v)
    except (TypeError, ValueError):
        return -1
    return -1 if v in BLOCKED or not -1 <= v < MAPS else v


def _apply_opts(g, data):
    if data.get('names') is not None:
        g['names'] = names_of(data.get('names'))
    if data.get('map') is not None:
        g['map'] = _map(data.get('map'))
    if data.get('rule') is not None:
        g['rule'] = str(data.get('rule')).strip().lower() if str(data.get('rule')).strip().lower() in RULES else 'first'
    if data.get('picks') is not None:
        g['picks'] = data.get('picks')
    if data.get('skills') is not None:
        g['skills'] = bool(data.get('skills'))
    g['balls'] = expand(g['names'])
    try:
        p = int(g['picks'])
    except (TypeError, ValueError):
        p = 1
    g['picks'] = max(1, min(p, max(1, len(g['balls']) - 1)))


@command('pinball.setup')
def setup(ctx, data):
    g = ctx.edit('pinball')
    if g['running']:
        raise CommandError('굴러가는 중에는 명단을 못 바꿉니다', 409)
    _apply_opts(g, data)
    g['result'], g['winners'], g['cut'] = [], [], ''


@command('pinball.show')
def show(ctx, data):
    if data.get('on'):
        sh.set_stage(ctx, 'pinball')
    else:
        if ctx.read('show')['stage'] == 'pinball':
            sh.set_stage(ctx, None)
        ctx.edit('pinball')['running'] = False


@command('pinball.start')
def start(ctx, data):
    g = ctx.edit('pinball')
    _apply_opts(g, data)
    if len(g['balls']) < 2:
        raise CommandError('구슬이 둘 이상이어야 합니다')
    sh.set_stage(ctx, 'pinball')
    rng = random.Random(data.get('seed_rng')) if data.get('seed_rng') is not None else random.Random()
    g.update({'running': True, 'result': [], 'winners': [], 'cut': '', 'round_id': int(g['round_id']) + 1,
              'seed': rng.randint(1, 2000000000), 'started_at': int(ctx.now * 1000)})


@command('pinball.result', auth=False)
def result(ctx, data):
    """방송판이 보내는 도착 순서 — 굴러가는 중 · 지금 판 번호일 때 **첫 보고만**."""
    g = ctx.read('pinball')
    if not g['running']:
        raise CommandError('지금은 핀볼이 굴러가고 있지 않습니다', 409)
    rid = data.get('round_id')
    if rid is not None and int(rid) != int(g['round_id']):
        raise CommandError('지난 판의 결과입니다', 409)
    order = names_of(data.get('result'))
    if not order:
        raise CommandError('결과가 비어 있습니다')
    g = ctx.edit('pinball')
    g['running'], g['result'] = False, order
    g['winners'] = winners(order, g['rule'], g['picks'])
    # ⏱ 구슬이 껴서 끊은 판인가 — 아는 값만 받는다(모르는 글자는 '제대로 갈림')
    g['cut'] = str(data.get('cut') or '') if str(data.get('cut') or '') in CUTS else ''
    took = max(0, int(ctx.now * 1000) - int(g['started_at']))
    ctx.notes['took_ms'] = took
    ctx.notes['cut'] = g['cut']
    print("🎱 [핀볼] %d판 끝 — 1등 %s (%.1f초)%s" % (int(g['round_id']), (g['winners'] or order)[0], took / 1000.0,
                                                 ' (구슬이 껴서 그 자리로 결정)' if g['cut'] else ''), flush=True)


@command('pinball.reset')
def reset(ctx, data):
    g = ctx.edit('pinball')
    g.update({'running': False, 'result': [], 'winners': [], 'cut': ''})


def _reset(ctx, data):
    g = ctx.edit('pinball')
    g.update({'running': False, 'result': [], 'winners': [], 'cut': ''})


ses.ON_START.append(_reset)
ses.ON_END.append(_reset)
