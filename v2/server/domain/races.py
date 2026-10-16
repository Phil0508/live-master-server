# -*- coding: utf-8 -*-
"""🏃 퇴근빵 · 🔥 지옥탈출 · 🎯 목표 달성 축하 — 목표를 넘기면 대기함에 '송출' 카드가 생긴다.

조각
  home (공개) on(진행 + 방송판에 보임) · goals{이름: 퇴근 목표 점수} · notified[이미 카드를 받은 사람]
  hell (공개) on(진행 중) · shown(방송판에 보임) · started_at · base{이름: 시작 때 점수} · goals{이름: 목표(점=만원)} · escaped[탈출한 사람]
  popup.offwork{name, kind, at} · popup.goal{at, target} — 방송판 연출 신호(players 의 popup 조각에 칸을 더 쓴다)
옛 규칙 그대로
  - 지옥탈출 시작: 지금 점수 높은 순(같으면 줄 순서)으로 목표 50 · 40 · 30 · 20(5등부터 20). 시작 뒤 받은 점수만 센다.
    등수 · 진행은 점수(score) — 기여도가 아니다(옛 98166d3 '번 돈으로만' · 대표님 10-17 '옛 것 그대로').
  - 판정 · 벌칙 없음 — 채우면 탈출(대표님 09-22). 목표를 올리면 다시 '진행 중'.
  - 퇴근빵 목표(home.goals)는 방송이 바뀌어도 남긴다. 누가 카드를 받았나(notified)는 방송마다 비운다.
  - 번외 판 점수는 안 센다 — 본판(list)만. 번외 판을 [끝]내 본판에 합쳐지면 그때 센다(옛 것도 본판 bjs 만 봤다).
v2 에서 고친 것
  - 목표를 넘겼는지 **서버가 점수 바뀔 때 바로** 본다(옛 것은 조종실 화면이 보고 카드를 만들어 달라고 했다 —
    조종실이 꺼져 있으면 카드가 안 생겼다).
  - 10-17 무대에서 뺐다 — 퇴근빵 · 지옥탈출은 무대(show.stage, 한 번에 하나)가 아니라 **늘 붙는 칸**이다.
    대결 · 룰렛 · 퀴즈를 켜도 꺼지지 않는다(대표님 '다른 게임을 켜면 꺼진다'). 보이기 = home.on · (hell.on 이고 hell.shown).
    옛 순서표 · 무대 단추가 보내는 show.stage{'hell' | 'home_race'} 는 이 스위치로 바꿔 받는다(show.RACE_ON).
  - 다시 판정(_recheck) 하나 — 점수가 바뀐 모든 길(점수 · 되돌리기 · 번외 판 끝/취소 · 이름 바꾸기 · 목표 바꾸기)에서
    ① 목표 밑으로 내려간 사람은 탈출/퇴근 명단에서 빼고 **아직 안 보낸** 카드를 걷는다(거짓 축하가 방송에 안 나가게)
    ② 목표를 넘긴 사람에게 카드. 목표 0 = 목표 없음(판정 안 함).
"""
import math
import uuid

from ..bus import AFTER as BUS_AFTER
from ..bus import CommandError, command
from ..state import slice_
from . import players as pl
from . import session as ses
from . import show as sh

HELL_TARGETS = (50, 40, 30, 20)
GOAL_MAX = 100000

slice_('home', True, lambda: {'on': False, 'goals': {}, 'notified': []})
slice_('hell', True, lambda: {'on': False, 'shown': False, 'started_at': 0, 'base': {}, 'goals': {}, 'escaped': []})


def _goal(v, unit='점'):
    """목표 숫자 하나 — 0 ~ 10만. 글자 · 무한대 · NaN 은 거절(옛 것은 inf 에서 서버 오류 500 이 났다)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        raise CommandError('목표는 숫자(%s)로 넣어 주세요' % unit)
    if not math.isfinite(f):
        raise CommandError('목표는 숫자(%s)로 넣어 주세요' % unit)
    return max(0, min(GOAL_MAX, int(f)))


def _is_card(d, name, kind):
    return d.get('type') == 'off_work' and d.get('name') == name and d.get('kind') == kind


def _card(ctx, name, kind):
    pend = ctx.edit('pending')
    if any(_is_card(d, name, kind) for d in pend):
        return
    pend.insert(0, {'id': 'off_%d_%s' % (int(ctx.now * 1000), uuid.uuid4().hex[:4]), 'type': 'off_work', 'kind': kind,
                    'name': name, 'amount': 0, 'message': '탈출 성공' if kind == 'hell' else '퇴근 성공', 'at': int(ctx.now * 1000)})


def _drop_card(ctx, name, kind):
    """아직 안 보낸 카드를 걷는다(이미 [송출] 한 카드는 대기함에 없다)."""
    pend = ctx.read('pending')
    if any(_is_card(d, name, kind) for d in pend):
        ctx.put('pending', [d for d in pend if not _is_card(d, name, kind)])


def hell_got(ctx):
    h = ctx.read('hell')
    base = h.get('base') or {}
    return {r['name']: max(0, int(r['score']) - int(base.get(r['name']) or 0))
            for r in ctx.read('players')['list'] if r['name'] in (h.get('goals') or {})}


def _recheck(ctx, *_):
    """점수 · 목표 · 명단이 바뀐 뒤 — 퇴근 · 탈출 판정을 지금 값으로 다시 맞춘다.
       ① 목표(>0) 밑으로 내려갔거나 목표가 0 이 된 사람 → 명단에서 빼고 안 보낸 카드를 걷는다(꺼져 있어도 — 기록이 거짓이 안 되게)
       ② 목표(>0) 이상인데 아직 명단에 없는 사람 → 명단에 넣고 카드(켜져 있을 때만)
       명단(본판)에서 빠진 사람은 손대지 않는다."""
    rows = {r['name']: int(r['score']) for r in ctx.read('players')['list']}

    home = ctx.read('home')
    for n in list(home.get('notified') or []):
        if n not in rows:
            continue
        g = int(home['goals'].get(n) or 0)
        if not (g > 0 and rows[n] >= g):
            ctx.edit('home')['notified'].remove(n)
            _drop_card(ctx, n, 'home')
    if ctx.read('home').get('on'):
        for n, sc in rows.items():
            hm = ctx.read('home')
            g = int(hm['goals'].get(n) or 0)
            if g > 0 and sc >= g and n not in hm['notified']:
                ctx.edit('home')['notified'].append(n)
                _card(ctx, n, 'home')

    got = hell_got(ctx)
    h = ctx.read('hell')
    for n in list(h.get('escaped') or []):
        if n not in got:
            continue
        g = int(h['goals'].get(n) or 0)
        if not (g > 0 and got[n] >= g):
            ctx.edit('hell')['escaped'].remove(n)
            _drop_card(ctx, n, 'hell')
    if ctx.read('hell').get('on'):
        for n, v in got.items():
            he = ctx.read('hell')
            g = int(he['goals'].get(n) or 0)
            if g > 0 and v >= g and n not in he['escaped']:
                ctx.edit('hell')['escaped'].append(n)
                _card(ctx, n, 'hell')


pl.AFTER_SCORE.append(_recheck)       # 점수 · 기여도
pl.ON_UNDO.append(_recheck)           # 되돌리기 — 잘못 준 점수로 생긴 거짓 카드를 걷는다
pl.ON_ROSTER.append(_recheck)         # 번외 판 시작 · 끝(본판에 합침) · 취소 · 선수 넣기 · 빼기 · 이름 바꾸기


def _renamed(names, old, new):
    """명단 속 옛 이름을 새 이름으로 — 새 이름이 (빠진 선수의 기록으로) 이미 있으면 한 번만 남긴다."""
    out = []
    for n in names:
        n = new if n == old else n
        if n not in out:
            out.append(n)
    return out


def _rename(ctx, old, new):
    """이름을 바꾸면 지옥 · 퇴근 기록도 따라간다 — 기준점 · 목표 · 탈출/퇴근 명단 · 대기함 카드."""
    home = ctx.read('home')
    if old in (home.get('goals') or {}) or old in (home.get('notified') or []):
        hm = ctx.edit('home')
        if old in hm['goals']:
            hm['goals'][new] = hm['goals'].pop(old)
        hm['notified'] = _renamed(hm['notified'], old, new)
    h = ctx.read('hell')
    if old in (h.get('goals') or {}) or old in (h.get('base') or {}):
        he = ctx.edit('hell')
        for k in ('goals', 'base'):
            if old in he[k]:
                he[k][new] = he[k].pop(old)
        he['escaped'] = _renamed(he['escaped'], old, new)
    if any(d.get('type') == 'off_work' and d.get('name') == old for d in ctx.read('pending')):
        seen, keep = set(), []
        for d in ctx.read('pending'):
            if d.get('type') == 'off_work':
                if d.get('name') == old:
                    d = dict(d, name=new)
                if (d['name'], d.get('kind')) in seen:
                    continue                    # 같은 사람 · 같은 판 카드는 한 장만
                seen.add((d['name'], d.get('kind')))
            keep.append(d)
        ctx.put('pending', keep)


pl.ON_RENAME.append(_rename)


def _home_set(ctx, on):
    ctx.edit('home')['on'] = bool(on)
    _recheck(ctx)


def _hell_show(ctx, on, strict=True):
    """방송판에 지옥탈출 판 보이기 · 숨기기 — 셈 · 카드는 그대로 돈다.
       끝낸 판(on=False)을 보이면 같은 기준점으로 이어서 센다(옛 /api/show 'hell' 이 hell.on 을 되살린 것과 같다)."""
    if on and not (ctx.read('hell').get('goals') or {}):
        if strict:
            raise CommandError('지옥탈출을 먼저 시작해 주세요', 409)
        return
    he = ctx.edit('hell')
    he['shown'] = bool(on)
    if on and not he.get('on'):
        he['on'] = True
        _recheck(ctx)


# 옛 무대 이름 → 스위치(show.stage · 순서표 · 스트림덱 같은 옛 단추가 부른다). strict=False 면 시작 전이어도 실패하지 않고 넘어간다
sh.RACE_ON['home_race'] = lambda ctx, strict=True: _home_set(ctx, True)
sh.RACE_ON['hell'] = lambda ctx, strict=True: _hell_show(ctx, True, strict)


@command('home.on')
def home_on(ctx, data):
    """퇴근빵 켜기/끄기 — 켜면 방송판에 판이 뜨고 카드를 만든다. 무대는 안 건드린다(다른 게임과 같이 떠 있다)."""
    _home_set(ctx, data.get('on', True) is not False)


@command('home.goal')
def home_goal(ctx, data):
    """한 사람 퇴근 목표(점). 0 이면 지운다. 목표를 올리면 다시 카드를 받을 수 있다."""
    name = str(data.get('name') or '').strip()
    if not name:
        raise CommandError('이름이 필요합니다')
    g = _goal(data.get('goal'), '점')
    home = ctx.edit('home')
    if g:
        home['goals'][name] = g
    else:
        home['goals'].pop(name, None)
    _recheck(ctx)


@command('hell.start')
def hell_start(ctx, data):
    """지금 등수로 목표를 정하고 처음부터 센다. 방송판에 바로 보인다. 무대는 안 건드린다."""
    raw = data.get('targets') or HELL_TARGETS
    if not isinstance(raw, (list, tuple)):
        raise CommandError('목표는 숫자(만원) 목록으로 넣어 주세요')
    targets = [_goal(x, '만원') for x in raw][:12] or list(HELL_TARGETS)
    rows = ctx.read('players')['list']
    if not rows:
        raise CommandError('선수가 없습니다 — 방송 시작부터 해 주세요', 409)
    ranked = sorted(enumerate(rows), key=lambda t: (-int(t[1]['score']), t[0]))
    h = {'on': True, 'shown': True, 'started_at': int(ctx.now * 1000), 'base': {}, 'goals': {}, 'escaped': []}
    for rank, (_, r) in enumerate(ranked):
        h['base'][r['name']] = int(r['score'])
        h['goals'][r['name']] = targets[min(rank, len(targets) - 1)]
    ctx.put('hell', h)
    # 지난 판 '탈출 성공' 카드가 대기함에 남아 있으면 헷갈린다 — 걷는다
    ctx.put('pending', [d for d in ctx.read('pending') if not (d.get('type') == 'off_work' and d.get('kind') == 'hell')])
    _recheck(ctx)


@command('hell.goal')
def hell_goal(ctx, data):
    name = str(data.get('name') or '').strip()
    g = _goal(data.get('goal'), '만원')
    h = ctx.edit('hell')
    if name not in h['goals']:
        raise CommandError('지옥탈출 명단에 없는 이름입니다', 404)
    h['goals'][name] = g
    _recheck(ctx)


@command('hell.show')
def hell_show(ctx, data):
    """👁 방송판에 보이기/숨기기 {on} — 기록 · 셈 · 카드는 계속(숨겼다 다시 띄워도 기록이 안 날아간다)."""
    _hell_show(ctx, data.get('on', True) is not False)


@command('hell.off')
def hell_off(ctx, data):
    """지옥탈출 끝 — 셈을 멈추고 방송판에서 내린다. 기록(기준점 · 목표 · 탈출)은 남는다 → [이어서 하기](hell.resume)."""
    he = ctx.edit('hell')
    he['on'] = False
    he['shown'] = False


@command('hell.resume')
def hell_resume(ctx, data):
    """끝낸 지옥탈출을 같은 기준점으로 이어서 — 방송판에도 다시 띄운다."""
    _hell_show(ctx, True)


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
    """방송 시작 · 끝 — 퇴근빵은 끄고(목표는 남김, 옛 2fa794e) 지옥탈출은 비운다.
       옛 것은 '퇴근빵 켜짐 = 무대' 라 방송 시작이 무대를 비울 때 같이 꺼졌다 — 켜짐만 남고 판은 안 보이던 어긋남을 막는다."""
    home = ctx.edit('home')
    home['notified'] = []
    home['on'] = False
    ctx.put('hell', {'on': False, 'shown': False, 'started_at': 0, 'base': {}, 'goals': {}, 'escaped': []})


ses.ON_START.append(_reset)
ses.ON_END.append(_reset)


def _migrate_stage(ctx):
    """옛 저장본 옮겨 담기(명령마다 한 번 보지만, 할 일이 없으면 바로 돌아간다).
       - 무대(show.stage · ret)에 'hell' · 'home_race' 가 남아 있으면 비우고 스위치로 옮긴다.
       - hell 조각에 shown 칸이 없으면(10-17 전 저장본) 한 번만: 그때 무대에 있던 판만 보이게(옛 보이기 그대로)."""
    s = ctx.read('show')
    st, ret = s.get('stage'), s.get('ret')
    first = 'shown' not in ctx.read('hell')
    if not first and st not in sh.RACE_STAGES and ret not in sh.RACE_STAGES:
        return
    was = {st, ret}
    if first:
        he = ctx.edit('hell')
        he['shown'] = bool(he.get('on')) and 'hell' in was
        if ctx.read('home').get('on') and 'home_race' not in was:
            ctx.edit('home')['on'] = False             # 옛 것은 무대에 없으면 판이 안 보였다
    else:
        if 'hell' in was and ctx.read('hell').get('goals'):
            he = ctx.edit('hell')
            he['on'] = he['shown'] = True
        if 'home_race' in was:
            ctx.edit('home')['on'] = True
    if st in sh.RACE_STAGES or ret in sh.RACE_STAGES:
        se = ctx.edit('show')
        if se.get('stage') in sh.RACE_STAGES:
            se['stage'] = None
        if se.get('ret') in sh.RACE_STAGES:
            se['ret'] = None


BUS_AFTER.append(_migrate_stage)
