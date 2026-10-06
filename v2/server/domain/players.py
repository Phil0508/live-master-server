# -*- coding: utf-8 -*-
"""🏆 선수 · 점수 · 기여도 · 되돌리기 · 번외 판 · 목표.

조각
  players (공개)  list[{name, score, contribution}] · extra(번외 판) · extra_active · bottom(운영비)
  logs    (비공개) 조종실 점수 기록(최근 200줄)
  popup   (공개)  donation(후원 팝업) · score(점수 팝업) · takeover(1등 탈환)
  goal    (공개)  target(목표 점수, 0 = 없음) · offset

규칙(옛 것 그대로)
  - score = 그날 일당(점수), contribution = 점수 + 게임 보너스. 순위는 contribution 큰 순(같으면 순서 유지).
  - 점수를 주면 기여도도 같이 오른다(기여도만 따로 주는 경우는 contrib 를 따로 준다).
  - 게이지 = 운영비 + 본판 점수 합 + offset (번외 판 · 기여도는 안 들어간다).
v2 에서 고친 것
  - 되돌리기가 서버 장부(score_log)에 있다 — 조종실을 새로 고쳐도 되돌릴 수 있다(옛 것은 브라우저에만 20개).
  - 후원 배정을 되돌리면 그 후원이 **대기함으로 돌아온다**(옛 것은 점수만 빠지고 후원은 사라졌다).
"""
import uuid

from ..bus import CommandError, command
from ..state import slice_
from . import session as ses
from .rules import LOG_MAX, split_points

slice_('players', True, lambda: {'list': [], 'extra': [], 'extra_active': False, 'bottom': {'name': '운영비', 'score': 0}})
slice_('logs', False, lambda: [])
slice_('popup', True, lambda: {'donation': None, 'score': None, 'takeover': None})
slice_('goal', True, lambda: {'target': 0, 'offset': 0, 'done': 0})   # done = 조종실이 '달성' 을 처리한 목표(축하 송출 · 닫기)

NAME_MAX = 20
PLAYERS_MAX = 10


def _clean(name):
    return ' '.join(str(name or '').split())[:NAME_MAX]


def _sort(rows):
    rows.sort(key=lambda p: -int(p.get('contribution') or 0))


def _list_key(players, want=None):
    """어느 판에 줄까 — 번외 판이 켜져 있으면 번외 판(따로 'main' 을 고르면 본판)."""
    if want in ('main', 'extra'):
        return 'list' if want == 'main' else 'extra'
    return 'extra' if players.get('extra_active') else 'list'


def apply_scores(ctx, items, reason='', ref=None, popup=True, takeover=True, want_list=None):
    """점수 · 기여도를 준다. items = [{name, delta, contrib?}] — 하나라도 없는 이름이면 아무것도 안 준다.
       돌려받는 값: 되돌리기 묶음 번호(ref)"""
    p = ctx.edit('players')
    key = _list_key(p, want_list)
    rows = p[key]
    by_name = {r['name']: r for r in rows}
    missing = [it.get('name') for it in items if _clean(it.get('name')) not in by_name]
    if missing:
        raise CommandError('없는 선수: %s' % ', '.join(str(m) for m in missing), 404)
    ref = ref or ('act_' + uuid.uuid4().hex[:10])
    sid = ses.session_id(ctx)
    top_before = rows[0]['name'] if rows else None
    logs = ctx.edit('logs')
    best = None
    for it in items:
        r = by_name[_clean(it['name'])]
        d = int(it.get('delta') or 0)
        c = int(it['contrib']) if it.get('contrib') is not None else d
        if not d and not c:
            continue
        before, cbefore = r['score'], r['contribution']
        r['score'] += d
        r['contribution'] += c
        if d:
            ctx.store.add_score(r['name'], 'score', d, reason, ref, sid, key)
        if c:
            ctx.store.add_score(r['name'], 'contribution', c, reason, ref, sid, key)
        row = {'at': ctx.now, 'name': r['name'], 'val': d, 'before': before, 'after': r['score'],
               'cval': c, 'cbefore': cbefore, 'cafter': r['contribution'], 'ref': ref, 'list': key}
        if not d:
            row.update({'kind': 'contrib', 'why': str(reason or '조종실에서')[:80]})
        logs.insert(0, row)
        if d > 0 and (best is None or d > best[1]):
            best = (r['name'], d)
    del logs[LOG_MAX:]
    _sort(rows)
    pop = ctx.edit('popup')
    if popup and best:
        pop['score'] = {'name': best[0], 'diff': best[1], 'at': int(ctx.now * 1000)}
    if takeover and key == 'list' and rows and top_before and rows[0]['name'] != top_before and best:
        pop['takeover'] = {'name': rows[0]['name'], 'at': int(ctx.now * 1000)}
    ctx.notes['ref'] = ref
    for fn in AFTER_SCORE:
        fn(ctx)
    return ref


AFTER_SCORE = []     # 점수가 바뀐 뒤 같이 볼 일(퇴근빵 · 지옥탈출 목표 넘김 → 대기함 카드)


# ── 명령 ──
@command('score.add')
def score_add(ctx, data):
    """조종실 점수 칸 · 기여도 고치기. {name, delta, contrib?, reason?, list?} 또는 {target:'bottom', delta}"""
    if data.get('target') == 'bottom':
        b = ctx.edit('players')['bottom']
        d = int(data.get('delta') or 0)
        b['score'] += d
        ref = 'act_' + uuid.uuid4().hex[:10]
        ctx.store.add_score(b['name'], 'score', d, str(data.get('reason') or ''), ref, ses.session_id(ctx), 'bottom')
        ctx.edit('logs').insert(0, {'at': ctx.now, 'name': b['name'], 'val': d, 'before': b['score'] - d, 'after': b['score'],
                                    'ref': ref, 'list': 'bottom'})
        ctx.notes['ref'] = ref
        return
    items = data.get('items') or [{'name': data.get('name'), 'delta': data.get('delta'), 'contrib': data.get('contrib')}]
    apply_scores(ctx, items, str(data.get('reason') or ''), popup=data.get('popup', True) is not False,
                 takeover=data.get('takeover', True) is not False, want_list=data.get('list'))


@command('score.undo')
def score_undo(ctx, data):
    """마지막 묶음(또는 ref 로 고른 묶음)을 거꾸로. 후원 배정이었으면 그 후원은 대기함으로 돌아온다."""
    sid = ses.session_id(ctx)
    ref = data.get('ref')
    if not ref:
        last = ctx.store.last_scores(sid, 1)
        if not last:
            raise CommandError('되돌릴 것이 없습니다', 404)
        ref = last[0]['ref']
    rows = ctx.store.score_rows(ref)
    if not rows:
        raise CommandError('이미 되돌렸거나 없는 기록입니다', 404)
    p = ctx.edit('players')
    done, skipped = [], []
    for r in rows:
        if r['list'] == 'bottom':
            p['bottom']['score'] -= r['delta']
            done.append({'name': r['player'], 'field': 'score', 'delta': r['delta'], 'list': 'bottom'})
            continue
        if r['list'] == 'jar':                       # 모금함(원) — extras 모듈의 조각
            ctx.edit('fundjar')['score'] -= r['delta']
            continue
        key = 'list' if r['list'] in ('list', 'main') else 'extra'
        if key == 'extra' and not p['extra_active']:
            # 번외 판이 끝난 뒤 — [끝]이면 그 점수는 본판에 더해졌으니 본판에서 빼고, [취소]면 이미 사라졌으니 손댈 게 없다
            closed = (p.get('extra_closed') or {}).get(r['player'])
            if closed != 'merged':
                skipped.append(r['player'])
                continue
            key = 'list'
        target = next((x for x in p[key] if x['name'] == r['player']), None)
        if target is None:
            skipped.append(r['player'])
            continue                     # 그 사이 선수가 빠졌다 — 남은 사람만 되돌린다
        target['score' if r['field'] == 'score' else 'contribution'] -= r['delta']
        done.append({'name': r['player'], 'field': r['field'], 'delta': r['delta'], 'list': key})
    _sort(p['list'])
    _sort(p['extra'])
    ctx.store.mark_undone([r['id'] for r in rows])
    ctx.put('logs', [l for l in ctx.read('logs') if l.get('ref') != ref])
    ctx.notes.update({'undone': ref, 'rows': done, 'skipped': sorted(set(skipped))})   # 무엇을 되돌렸나(조종실 알림용)
    for fn in ON_UNDO:
        fn(ctx, ref)


ON_UNDO = []         # 되돌릴 때 같이 할 일(예: 후원을 대기함으로)
ON_ROSTER = []       # 명단(본판 · 번외 판)이 바뀐 뒤 fn(ctx) — 주사위 말 맞추기 등
ON_RENAME = []       # 이름을 바꾼 뒤 fn(ctx, 옛 이름, 새 이름) — 주사위 말 · 전용 판 점수 물려주기 등


def _roster_changed(ctx):
    for fn in ON_ROSTER:
        fn(ctx)


@command('players.add')
def players_add(ctx, data):
    name = _clean(data.get('name'))
    p = ctx.edit('players')
    if not name:
        raise CommandError('이름을 적어 주세요')
    if any(r['name'] == name for r in p['list']):
        raise CommandError('이미 있는 이름입니다', 409)
    if len(p['list']) >= PLAYERS_MAX:
        raise CommandError('플레이어는 %d명까지입니다' % PLAYERS_MAX)
    p['list'].append({'name': name, 'score': 0, 'contribution': 0})
    if p['extra_active']:
        p['extra'].append({'name': name, 'score': 0, 'contribution': 0})
    _roster_changed(ctx)


@command('players.remove')
def players_remove(ctx, data):
    name = _clean(data.get('name'))
    p = ctx.edit('players')
    if not any(r['name'] == name for r in p['list']):
        raise CommandError('없는 선수입니다', 404)
    p['list'] = [r for r in p['list'] if r['name'] != name]
    p['extra'] = [r for r in p['extra'] if r['name'] != name]
    _roster_changed(ctx)


@command('players.rename')
def players_rename(ctx, data):
    """이름만 바꾼다 — 점수 · 기여도는 그대로(옛 것은 '하나 빠지고 하나 생기면 이름 바꾸기' 로 짐작했다)."""
    old, new = _clean(data.get('from')), _clean(data.get('to'))
    p = ctx.edit('players')
    if not new:
        raise CommandError('새 이름을 적어 주세요')
    if any(r['name'] == new for r in p['list']):
        raise CommandError('이미 있는 이름입니다', 409)
    hit = False
    for key in ('list', 'extra'):
        for r in p[key]:
            if r['name'] == old:
                r['name'] = new
                hit = True
    if not hit:
        raise CommandError('없는 선수입니다', 404)
    for fn in ON_RENAME:
        fn(ctx, old, new)
    _roster_changed(ctx)


@command('players.order')
def players_order(ctx, data):
    """같은 기여도끼리 순서를 손으로 — 이름 목록 순서대로 세운 뒤 기여도로 다시 줄 세운다(같으면 손 순서 유지)."""
    names = [_clean(n) for n in (data.get('names') or [])]
    p = ctx.edit('players')
    pos = {n: i for i, n in enumerate(names)}
    p['list'].sort(key=lambda r: pos.get(r['name'], 999))
    _sort(p['list'])


@command('extra.start')
def extra_start(ctx, data):
    p = ctx.edit('players')
    if p['extra_active']:
        raise CommandError('번외 판이 이미 켜져 있습니다', 409)
    p['extra'] = [{'name': r['name'], 'score': 0, 'contribution': 0} for r in p['list']]
    p['extra_active'] = True
    p['extra_closed'] = {}
    _roster_changed(ctx)


@command('extra.end')
def extra_end(ctx, data):
    """번외 판 끝 — 같은 이름의 본판에 더한다."""
    p = ctx.edit('players')
    if not p['extra_active']:
        raise CommandError('번외 판이 꺼져 있습니다', 409)
    main = {r['name']: r for r in p['list']}
    for r in p['extra']:
        m = main.get(r['name'])
        if m:
            m['score'] += r['score']
            m['contribution'] += r['contribution']
    _sort(p['list'])
    p['extra_closed'] = {r['name']: 'merged' for r in p['extra']}
    p['extra'], p['extra_active'] = [], False
    _roster_changed(ctx)


@command('extra.cancel')
def extra_cancel(ctx, data):
    p = ctx.edit('players')
    p['extra_closed'] = {r['name']: 'cancelled' for r in p['extra']}
    p['extra'], p['extra_active'] = [], False
    _roster_changed(ctx)


@command('goal.set')
def goal_set(ctx, data):
    g = ctx.edit('goal')
    if 'target' in data:
        g['target'] = max(0, int(data.get('target') or 0))
    if 'offset' in data:
        g['offset'] = int(data.get('offset') or 0)


# ── 방송 시작 · 끝 ──
def _on_start(ctx, data):
    names = [_clean(n) for n in (data.get('names') or []) if _clean(n)]
    if not 1 <= len(names) <= PLAYERS_MAX or len(set(names)) != len(names):
        raise CommandError('플레이어 이름 1~%d명(겹치지 않게)을 적어 주세요' % PLAYERS_MAX)
    ctx.put('players', {'list': [{'name': n, 'score': 0, 'contribution': 0} for n in names], 'extra': [],
                        'extra_active': False, 'bottom': dict(ctx.read('players')['bottom'], score=0)})
    ctx.put('logs', [])
    ctx.put('popup', {'donation': None, 'score': None, 'takeover': None})
    ctx.edit('goal').update({'offset': 0, 'done': 0})


def _on_end(ctx, data):
    ctx.put('players', {'list': [], 'extra': [], 'extra_active': False, 'bottom': dict(ctx.read('players')['bottom'], score=0)})
    ctx.put('logs', [])
    ctx.put('popup', {'donation': None, 'score': None, 'takeover': None})
    ctx.edit('goal').update({'offset': 0, 'done': 0})


ses.ON_START.append(_on_start)
ses.ON_END.append(_on_end)
