# -*- coding: utf-8 -*-
"""⏪ [방송 끝] 되살리기 — 방송을 실수로 끝냈을 때 조종실 단추 한 번으로 끝내기 직전으로 (sturdy 10-17).

옛 것(server.py end_broadcast): 끝내기 직전 상태(pre_state)를 '방송 종료 자동 백업' 복구 지점으로 남기고,
  조종실 타임머신 [복구] 로 통째 되돌렸다(/api/snapshots/restore). 다음 방송을 시작하면 복구 지점을 지웠다.
v2
  - session.end 가 바꾼 조각마다 바로 전 값(pre) · 바로 뒤 값(post)을 장부 restore_points 표에 **같은 묶음**으로 적는다
    (bus.BEFORE_COMMIT — 끝내기가 실패하면 지점도 안 남는다).
  - session.undo_end — 마지막 '방송 끝' 지점으로 되살린다. 점수판 · 대기함 · 점수 기록 · 시그니처 대기줄 · 무대 · 게임판 · 집계.
  - 장부 표(donations · score_log)는 끝낼 때도 되살릴 때도 안 건드린다(v2 원칙) — 회차 번호(session.id)가 그대로라
    되살린 뒤의 되돌리기(score.undo) · 장부 보기도 이어진다.
  - 끝낸 뒤 들어온 후원은 잃지 않는다: 끝낸 뒤 바뀐 조각은 '끝낸 뒤 바뀐 만큼' 만 얹는다(merge3) —
    대기함 카드 · 시그니처 대기줄은 이어 붙이고, 후원 순위 · 시그 집계는 늘어난 만큼 더하고, 한 방 최고는 큰 쪽.
조각
  endundo (비공개) ready · at(끝낸 때, 초) · until(이때까지만) · sid · started_at · players · score_total · pending · queue · undone_at
규칙
  - 방송 중이면 안 된다(409). 끝낸 뒤 새 방송을 시작했으면 안 된다(시작하면 ready 가 꺼지고, 회차 번호가 달라진다).
  - 끝낸 지 UNDO_MAX_SEC(12시간)이 지나면 안 된다 — 며칠 뒤 잘못 눌러 지난 방송이 '방송 중' 으로 살아나지 않게(배포 잠금도 걸린다).
  - 한 번 되살리면 그 지점은 다 쓴 것(두 번 눌러도 한 번).
  - 팝업(popup)은 되살리지 않는다 — 지난 후원 알림이 방송판에 다시 뜨지 않게.
  - 끝낸 뒤 끝 화면을 띄웠으면 내린다(방송 중으로 돌아왔으니).
  - 룰렛 · 슬롯이 서는 중이었으면 '다 섰다' 예약을, 시그뒤집기 까보기 중이었으면 '덮기' 예약을 다시 건다.
"""
import copy

from ..bus import BEFORE_COMMIT, COMMANDS, CommandError, command
from ..state import SLICES, slice_
from . import session as ses
from .rules import NOTICE_DONORS_MAX

KIND = 'end'
UNDO_MAX_SEC = 12 * 3600
SKIP = ('popup', 'endundo')          # 되살리지 않는 조각

slice_('endundo', False, lambda: {'ready': False})

_M = object()                         # '그 칸이 없었다'


# ── 세 갈래 합치기: 끝내기 전(pre) · 끝낸 직후(post) · 지금(cur) ──
def _keys(*ds):
    out = []
    for d in ds:
        for k in d:
            if k not in out:
                out.append(k)
    return out


def _all_ids(lst):
    return all(isinstance(x, dict) and 'id' in x for x in lst)


def _list_merge(pre, post, cur):
    """목록 — 끝내기 전 것에, 끝낸 뒤 새로 생긴 것을 이어 붙인다. 끝낸 뒤 빠진 것은 뺀다.
       id 가 있는 목록(대기함 · 대기줄)은 id 로 맞춘다(끝낸 뒤 고친 카드는 고친 것으로)."""
    if _all_ids(pre) and _all_ids(post) and _all_ids(cur):
        post_ids = {x['id'] for x in post}
        cur_ids = {x['id'] for x in cur}
        gone = post_ids - cur_ids
        edited = {x['id']: x for x in cur if x['id'] in post_ids and x not in post}
        out = [edited.get(x['id'], x) for x in pre if x['id'] not in gone]
        have = {x['id'] for x in out}
        return out + [x for x in cur if x['id'] not in post_ids and x['id'] not in have]
    removed = [x for x in post if x not in cur]
    added = [x for x in cur if x not in post]
    out = [x for x in pre if x not in removed]
    return out + [x for x in added if x not in out]


def merge3(pre, post, cur):
    """끝낸 뒤 아무도 안 건드렸으면(cur == post) 끝내기 전으로. 끝내기가 안 바꾼 칸(pre == post)은 지금 것.
       둘 다 바뀌었으면 사전은 칸마다, 목록은 이어 붙이기, 나머지(글자 · 숫자)는 지금 것(나중에 고친 것이 이긴다)."""
    if cur == post:
        return pre
    if pre == post:
        return cur
    if isinstance(pre, dict) and isinstance(post, dict) and isinstance(cur, dict):
        out = {}
        for k in _keys(pre, cur, post):
            v = merge3(pre.get(k, _M), post.get(k, _M), cur.get(k, _M))
            if v is not _M:
                out[k] = v
        return out
    if isinstance(pre, list) and isinstance(post, list) and isinstance(cur, list):
        return _list_merge(pre, post, cur)
    return cur


def _int(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


TALLY_COUNTED = ('donors', 'best', 'notice_donors', 'sigs')


def merge_tallies(pre, post, cur):
    """후원 집계 — 끝낼 때 0 으로 비웠다가 그 뒤 후원이 쌓였으면, 끝내기 전 값에 **늘어난 만큼** 더한다."""
    pre, post, cur = pre or {}, post or {}, cur or {}
    out = {}
    for k in _keys(pre, cur, post):
        if k in TALLY_COUNTED:
            continue
        v = merge3(pre.get(k, _M), post.get(k, _M), cur.get(k, _M))
        if v is not _M:
            out[k] = v
    donors = copy.deepcopy(pre.get('donors') or {})
    pd = post.get('donors') or {}
    for key, v in (cur.get('donors') or {}).items():
        b = pd.get(key) or {}
        if v == b:
            continue
        d = donors.setdefault(key, {'name': v.get('name') or key, 'total': 0, 'count': 0})
        d['total'] = _int(d.get('total')) + _int(v.get('total')) - _int(b.get('total'))
        d['count'] = _int(d.get('count')) + _int(v.get('count')) - _int(b.get('count'))
        if v.get('name'):
            d['name'] = v['name']
    out['donors'] = donors
    best, cb = pre.get('best'), cur.get('best')
    if cb and cb != post.get('best') and (not best or _int(cb.get('amount')) > _int(best.get('amount'))):
        best = cb
    out['best'] = best
    out['notice_donors'] = _list_merge(pre.get('notice_donors') or [], post.get('notice_donors') or [],
                                       cur.get('notice_donors') or [])[-NOTICE_DONORS_MAX:]
    sigs = copy.deepcopy(pre.get('sigs') or {})
    ps = post.get('sigs') or {}
    for sid, v in (cur.get('sigs') or {}).items():
        b = ps.get(sid) or {}
        if v == b:
            continue
        st = sigs.setdefault(sid, dict(copy.deepcopy(v), count=0, donors={}))
        st['count'] = _int(st.get('count')) + _int(v.get('count')) - _int(b.get('count'))
        dons = st.setdefault('donors', {})
        for dk, dc in (v.get('donors') or {}).items():
            dons[dk] = _int(dons.get(dk)) + _int(dc) - _int((b.get('donors') or {}).get(dk))
    out['sigs'] = sigs
    return out


MERGE = {'tallies': merge_tallies}


# ── 끝낼 때 ──
def _on_end(ctx, data):
    """조종실이 [방송 끝 되돌리기] 상자에 보여 줄 요약 — 끝내기 직전(이 명령 전) 상태로 센다."""
    pre = ctx.bus.state.slices
    p = pre.get('players') or {}
    rows = list(p.get('list') or []) + list(p.get('extra') or [])
    ctx.put('endundo', {'ready': True, 'at': ctx.now, 'until': ctx.now + UNDO_MAX_SEC,
                        'sid': (pre.get('session') or {}).get('id') or '',
                        'started_at': (pre.get('session') or {}).get('started_at') or 0,
                        'players': len(p.get('list') or []),
                        'score_total': sum(_int(r.get('score')) for r in rows) + _int((p.get('bottom') or {}).get('score')),
                        'pending': len(pre.get('pending') or []),
                        'queue': len((pre.get('queue') or {}).get('items') or [])})


def _on_start(ctx, data):
    ctx.put('endundo', {'ready': False})


def _save_point(ctx, type_, changed):
    """[방송 끝] 이 바꾼 조각의 바로 전 · 바로 뒤 값을 장부에 — 끝내기와 같은 묶음(실패하면 같이 안 남는다)."""
    if type_ != 'session.end':
        return
    before = ctx.bus.state.slices                 # 이 명령 전 — 아직 아무것도 안 바뀌었다
    pre = {k: before.get(k) for k in changed if k not in SKIP}
    post = {k: v for k, v in changed.items() if k not in SKIP}
    ctx.store.add_restore_point(KIND, (before.get('session') or {}).get('id') or '', pre, post)


ses.ON_END.append(_on_end)
ses.ON_START.append(_on_start)
BEFORE_COMMIT.append(_save_point)


# ── 되살리기 ──
def _rearm(ctx):
    """되살린 판이 '서는 중 · 까보는 중' 이었다 — 끝낼 때 비워져 헛돈 예약 대신 새로 건다(그때 다시 조건을 본다)."""
    now_ms = int(ctx.now * 1000)
    if 'roulette' in SLICES and 'roulette.done' in COMMANDS:
        r = ctx.read('roulette')
        st = r.get('stop') or {}
        if r.get('phase') == 'stopping' and st.get('ends_at'):
            ctx.later(max(0, _int(st['ends_at']) - now_ms) / 1000.0 + 0.3, 'roulette.done', {'round': r.get('round')})
    if 'slot' in SLICES and 'slot.done' in COMMANDS:
        s = ctx.read('slot')
        if s.get('phase') == 'spinning' and s.get('ends_at'):
            ctx.later(max(0, _int(s['ends_at']) - now_ms) / 1000.0 + 0.3, 'slot.done', {'round': s.get('round')})
    if 'siggame' in SLICES and 'sig.peek_end' in COMMANDS:
        from .siggame import PEEK_MS
        a = ctx.read('siggame').get('action') or {}
        if a.get('type') == 'PEEK' and not a.get('closed'):
            ctx.later(max(0, _int(a.get('ts')) + PEEK_MS - now_ms) / 1000.0 + 0.05, 'sig.peek_end')
    if 'auto.decide' in COMMANDS:
        for x in ctx.read('pending'):
            a = x.get('auto') if isinstance(x, dict) else None
            if isinstance(a, dict) and a.get('asking'):
                ctx.later(0, 'auto.decide', {'id': x['id']})      # 🤖 '판단 중' 이던 카드 — 다시 판단에 건다


@command('session.undo_end')
def undo_end(ctx, data):
    s = ctx.read('session')
    if s.get('live'):
        raise CommandError('방송 중이에요 — 되살릴 [방송 끝] 이 없어요', 409)
    rp = ctx.store.last_restore_point(KIND)
    if not rp or rp.get('used_at'):
        raise CommandError('되살릴 [방송 끝] 기록이 없어요', 404)
    if rp['session'] != (s.get('id') or ''):
        raise CommandError('그 뒤에 다른 방송이 있었어요 — 되살리지 않아요', 409)
    if ctx.now - rp['at'] > UNDO_MAX_SEC:
        raise CommandError('끝낸 지 %d시간이 넘어 되살리지 않아요(점수 · 후원 기록은 장부에 그대로 있어요)' % (UNDO_MAX_SEC // 3600), 409)
    restored, merged = [], []
    for name, post in rp['post'].items():
        if name in SKIP or name not in SLICES or name not in rp['pre']:
            continue
        pre, cur = rp['pre'][name], ctx.read(name)
        if cur == post:
            new = pre
        else:
            new = MERGE.get(name, merge3)(pre, post, cur)
            merged.append(name)
        ctx.put(name, copy.deepcopy(new))
        restored.append(name)
    # 끝낸 뒤 [끝 화면] 을 띄웠으면 내린다 — 방송 중으로 돌아왔다
    pre_sc = rp['pre'].get('screen')
    if isinstance(pre_sc, dict) and 'screen' in SLICES:
        sc = ctx.read('screen')
        if sc.get('mode') == 'end' and pre_sc.get('mode') != 'end':
            ctx.edit('screen')['mode'] = pre_sc.get('mode') or 'off'
    if 'tallies' in merged:
        from .donors import recompute_vip
        recompute_vip(ctx)                         # 등급은 합계에서 나온다 — 합친 합계로 다시 매긴다
    _rearm(ctx)
    ctx.put('endundo', dict(ctx.read('endundo'), ready=False, undone_at=ctx.now))
    ctx.store.mark_restore_point_used(rp['id'], ctx.now)
    ctx.notes.update({'restored': sorted(restored), 'merged': sorted(merged), 'session': rp['session']})
