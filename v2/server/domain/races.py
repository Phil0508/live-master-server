# -*- coding: utf-8 -*-
"""🏃 퇴근빵 · 🔥 지옥탈출 · 🎯 목표 달성 축하 — 목표를 넘기면 대기함에 '송출' 카드가 생긴다.

조각
  home (공개) on · goals{이름: 퇴근 목표 점수} · notified[이미 카드를 받은 사람]
  hell (공개) on · started_at · base{이름: 시작 때 점수} · goals{이름: 목표(점=만원)} · escaped[탈출한 사람]
  popup.offwork{name, kind, at} · popup.goal{at, target} — 방송판 연출 신호(players 의 popup 조각에 칸을 더 쓴다)
옛 규칙 그대로
  - 지옥탈출 시작: 지금 점수 높은 순(같으면 줄 순서)으로 목표 50 · 40 · 30 · 20(5등부터 20). 시작 뒤 받은 점수만 센다.
  - 판정 · 벌칙 없음 — 채우면 탈출(대표님 09-22). 목표를 올리면 다시 '진행 중'.
  - 퇴근빵 목표(home.goals)는 방송이 바뀌어도 남긴다. 누가 카드를 받았나(notified)는 방송마다 비운다.
v2 에서 고친 것
  - 목표를 넘겼는지 **서버가 점수 바뀔 때 바로** 본다(옛 것은 조종실 화면이 보고 카드를 만들어 달라고 했다 —
    조종실이 꺼져 있으면 카드가 안 생겼다).
"""
import uuid

from ..bus import CommandError, command
from ..state import slice_
from . import players as pl
from . import session as ses

HELL_TARGETS = (50, 40, 30, 20)

slice_('home', True, lambda: {'on': False, 'goals': {}, 'notified': []})
slice_('hell', True, lambda: {'on': False, 'started_at': 0, 'base': {}, 'goals': {}, 'escaped': []})


def _card(ctx, name, kind):
    pend = ctx.edit('pending')
    if any(d.get('type') == 'off_work' and d.get('name') == name and d.get('kind') == kind for d in pend):
        return
    pend.insert(0, {'id': 'off_%d_%s' % (int(ctx.now * 1000), uuid.uuid4().hex[:4]), 'type': 'off_work', 'kind': kind,
                    'name': name, 'amount': 0, 'message': '탈출 성공' if kind == 'hell' else '퇴근 성공', 'at': int(ctx.now * 1000)})


def hell_got(ctx):
    h = ctx.read('hell')
    base = h.get('base') or {}
    return {r['name']: max(0, int(r['score']) - int(base.get(r['name']) or 0))
            for r in ctx.read('players')['list'] if r['name'] in (h.get('goals') or {})}


def _check(ctx):
    """점수가 바뀐 뒤 — 퇴근 목표 · 지옥탈출 목표를 넘긴 사람에게 카드."""
    home = ctx.read('home')
    if home.get('on'):
        for r in ctx.read('players')['list']:
            g = home['goals'].get(r['name'])
            if g and r['score'] >= int(g) and r['name'] not in home['notified']:
                ctx.edit('home')['notified'].append(r['name'])
                _card(ctx, r['name'], 'home')
    h = ctx.read('hell')
    if h.get('on'):
        for n, got in hell_got(ctx).items():
            if got >= int(h['goals'].get(n) or 0) and n not in h['escaped']:
                ctx.edit('hell')['escaped'].append(n)
                _card(ctx, n, 'hell')


pl.AFTER_SCORE.append(_check)


@command('home.on')
def home_on(ctx, data):
    from . import show as sh
    ctx.edit('home')['on'] = bool(data.get('on', True))
    if data.get('on', True):
        sh.set_stage(ctx, 'home_race')
    elif ctx.read('show')['stage'] == 'home_race':
        sh.set_stage(ctx, None)
    _check(ctx)


@command('home.goal')
def home_goal(ctx, data):
    """한 사람 퇴근 목표(점). 0 이면 지운다. 목표를 올리면 다시 카드를 받을 수 있다."""
    name = str(data.get('name') or '').strip()
    try:
        g = max(0, int(float(data.get('goal'))))
    except (TypeError, ValueError):
        raise CommandError('목표는 숫자(점)로 넣어 주세요')
    home = ctx.edit('home')
    if g:
        home['goals'][name] = g
    else:
        home['goals'].pop(name, None)
    r = next((x for x in ctx.read('players')['list'] if x['name'] == name), None)
    if r and name in home['notified'] and r['score'] < g:
        home['notified'].remove(name)
    _check(ctx)


@command('hell.start')
def hell_start(ctx, data):
    from . import show as sh
    raw = data.get('targets') or HELL_TARGETS
    try:
        targets = [max(0, int(float(x))) for x in raw][:12] or list(HELL_TARGETS)
    except (TypeError, ValueError):
        raise CommandError('목표는 숫자(만원)로 넣어 주세요')
    rows = ctx.read('players')['list']
    if not rows:
        raise CommandError('선수가 없습니다 — 방송 시작부터 해 주세요', 409)
    ranked = sorted(enumerate(rows), key=lambda t: (-int(t[1]['score']), t[0]))
    h = {'on': True, 'started_at': int(ctx.now * 1000), 'base': {}, 'goals': {}, 'escaped': []}
    for rank, (_, r) in enumerate(ranked):
        h['base'][r['name']] = int(r['score'])
        h['goals'][r['name']] = targets[min(rank, len(targets) - 1)]
    ctx.put('hell', h)
    # 지난 판 '탈출 성공' 카드가 대기함에 남아 있으면 헷갈린다 — 걷는다
    ctx.put('pending', [d for d in ctx.read('pending') if not (d.get('type') == 'off_work' and d.get('kind') == 'hell')])
    sh.set_stage(ctx, 'hell')


@command('hell.goal')
def hell_goal(ctx, data):
    name = str(data.get('name') or '').strip()
    try:
        g = max(0, int(float(data.get('goal'))))
    except (TypeError, ValueError):
        raise CommandError('목표는 숫자(만원)로 넣어 주세요')
    h = ctx.edit('hell')
    if name not in h['goals']:
        raise CommandError('지옥탈출 명단에 없는 이름입니다', 404)
    h['goals'][name] = g
    if hell_got(ctx).get(name, 0) < g and name in h['escaped']:
        h['escaped'].remove(name)
    _check(ctx)


@command('hell.off')
def hell_off(ctx, data):
    from . import show as sh
    ctx.edit('hell')['on'] = False
    if ctx.read('show')['stage'] == 'hell':
        sh.set_stage(ctx, None)


@command('offwork.send')
def offwork_send(ctx, data):
    """대기함의 퇴근 · 탈출 카드 [송출] — 방송판 연출 신호를 주고 카드를 치운다."""
    pend = ctx.edit('pending')
    it = next((x for x in pend if x['id'] == data.get('id') and x.get('type') == 'off_work'), None)
    if it is None:
        ctx.notes['already'] = True
        return
    pend.remove(it)
    ctx.edit('popup')['offwork'] = {'name': it['name'], 'kind': it['kind'], 'at': int(ctx.now * 1000)}


@command('goal.celebrate')
def goal_celebrate(ctx, data):
    """목표 100% 달성 연출 — 조종실이 눌러야 나간다(옛 것과 같다)."""
    g = ctx.edit('goal')
    g['done'] = g['target']
    ctx.edit('popup')['goal'] = {'at': int(ctx.now * 1000), 'target': g['target']}


@command('goal.dismiss')
def goal_dismiss(ctx, data):
    """목표 달성 알림 [닫기] — 연출은 안 내보내고 '처리했음' 만 남긴다(옛 dismissGoalEvent). 목표를 바꾸면 다시 뜬다."""
    g = ctx.edit('goal')
    g['done'] = g['target']


def _reset(ctx, data):
    ctx.edit('home')['notified'] = []
    ctx.put('hell', {'on': False, 'started_at': 0, 'base': {}, 'goals': {}, 'escaped': []})


ses.ON_START.append(_reset)
ses.ON_END.append(_reset)
