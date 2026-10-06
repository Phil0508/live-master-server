# -*- coding: utf-8 -*-
"""🎡 룰렛 — 멤버 돌림판 · 벌칙 룰렛. **당첨은 서버가 정하고** 방송판은 그 자리에 세우기만 한다.

조각
  roulette     (공개)  source(bj|custom) · weight(equal|contrib) · custom[칸 이름…]   ← 설정(방송이 바뀌어도 남는다)
                       round · phase(idle|spinning|stopping|done) · items[{name, w}](이번 판에 얼린 칸) · spin_at(ms)
                       stop{at, ends_at, index, name, angle, duration_ms} | None
  roulette_ops (비공개) pick(🗳️ 선관위가 정해 둔 칸 이름 | None) · history[{round, name, at, picked, cancelled?}] 최근 20

명령: roulette.config{source?, weight?, custom?} · roulette.pick{name|None} · roulette.spin{seed?}(seed 는 검사용) ·
      roulette.stop{seed?} · roulette.done{round}(로그인 없이) · roulette.reset

옛 규칙 그대로
  - 칸: 멤버(bj) = 본판 선수, 번외 판이 켜져 있으면 번외 판 선수(overlay.html:6995).
        직접 입력(custom) = 한 줄에 하나, 기본 '벌칙 1~5'(server.py:1563 DEFAULT_STATE['roulette']).
  - 넓이: 같은 확률이면 1, 기여도 비례면 max(1, 기여도)(overlay.html:6590). 직접 입력은 같은 확률만 — 바꾸면 equal 로(controller.html:5745).
  - 칸 순서 = 목록 순서, 12시에서 시계 방향. 바늘은 칸 경계에서 min(칸 넓이×18%, 6°) 안쪽에 선다(overlay.html:6780).
  - [정지] 뒤 3.85~4.35초 고르게 감속해 선다(overlay.html:6785) · 선 자리를 4초 더 보여 준다(overlay.html:6858).
  - 🗳️ 선관위: 이름으로 칸을 정해 두면 거기 선다. 판에 없는 이름이면 무작위(overlay.html:6761 stop(riggedIndex)).
    정해 둔 것은 [초기화] · 방송 시작/끝 때만 풀린다(controller.html:5767 · server.py:3175-3180).
  - [돌리기] = 무대에 잠깐(temp) 올린다(show.py:252 ingest_roulette) → 결과가 나면 원래 무대로(features/effects.py:150).
  - 한 판에 결과 하나 — 판 번호(round) 문지기(features/effects.py:94-145). 서는 중에 다시 돌리지 못한다(overlay.html:6745 launch).
  - 설정(source · weight · custom)은 방송이 바뀌어도 남고, 판 상태 · 선관위 · 결과만 비운다(server.py:3175-3180 · 3250-3255).
v2 에서 고친 것
  - ⭐ 옛 것은 방송판(창마다)이 서는 칸을 뽑아 /api/roulette/winner 로 보고했다 → 창 두 개가 다른 당첨자를 보고했고,
    판 번호 문지기(round_id)는 그 땜질이었다. v2 는 [정지] 순간 **서버가** 칸 · 멈출 각도 · 감속 시간을 정해 공개 조각에 싣는다.
    창이 몇 개든 같은 각도에 서므로 같은 칸이다. 보고(roulette.done)는 결과를 바꿀 수 없다 — 무대만 돌려놓는다.
  - 칸(items)을 [돌리기] 순간에 얼린다 — 도는 중에 점수 · 설정이 바뀌어도 이번 판 칸은 그대로(옛 방송판도 도는 중엔 칸을 안 바꿨다).
  - 결과는 점수 기록(logs)에 '🎡 룰렛 결과' 줄로 섞지 않고 roulette_ops.history 에 둔다(점수가 아니다 — 되돌리기 목록과 섞이지 않게).
  - 도는 중 [초기화] 는 원래 무대로 돌려놓는다(옛 것은 빈 판이 떠 있는 채로 남아 손으로 내려야 했다).

왜 '서버가 혼자 끝내기' 가 아니라 roulette.done 인가
  v2 서버에는 타이머가 없다(명령이 올 때만 움직인다). 무대를 [정지] 순간에 미리 돌려 두면 감속하는 4초 동안
  원래 판(주사위 등)이 룰렛 밑에서 같이 떠 버린다. 그래서 결과는 [정지] 때 확정하고(history), 무대 돌려놓기만
  다 선 뒤의 done 으로 한다. done 은 로그인 없이 받되 ① 지금 판(round) ② 서는 중 ③ ends_at − 1초가 지났을 때만 받는다.
  방송판이 꺼져 있어 아무도 done 을 안 보내도 막히지 않는다 — 조종실이 ends_at 뒤 한 번 보내고,
  그래도 안 오면 다음 [돌리기] 가 지난 판을 마저 닫는다.

화면 약속(방송판 · web/overlay/widgets/roulette.js 가 지킬 것)
  1. 쉬는 판(phase idle · done) 그림: source=custom 이면 custom 칸 · 같은 넓이. bj 면 players.extra(extra_active) 아니면
     players.list, 넓이 = weight==contrib ? max(1, contribution) : 1. 위 '칸 순서' 와 같게. (서버 wheel() 과 같은 셈)
     phase 가 spinning · stopping 이면 반드시 items(얼린 칸)로 그린다.
  2. round 가 바뀌고 phase=spinning: 판을 띄우고 0.9초 가속 → 초당 660° 로 계속 돈다(옛 MAX_SPEED).
  3. stop 이 생기면: 원판의 angle(12시 칸 경계에서 시계 방향, 도) 지점이 바늘 밑에 오도록 duration_ms 동안 고르게 감속
     (지금 회전에서 3~4바퀴 더 — 바퀴 수는 창이 고른다. 서는 자리는 angle 하나라 어느 창이든 같다).
     늦게 붙은 창: now < ends_at 이면 남은 시간 동안 감속, 지났으면 그 자리에 바로 세운다.
  4. 다 서면 'items[index].name 당첨!' · 꽃가루 · roulette.done{round}. 판은 4초(HOLD_MS) 더 보여 준 뒤(무대가 바뀌었어도)
     stage 가 roulette 가 아니면 내린다. 이름 글자는 ends_at 전에 띄우지 않는다.
  5. 조종실도 ends_at + 1초에 roulette.done{round} 를 한 번 보낸다 — 먼저 온 하나만 받고 나머지는 ignored.
  ⚠️ 스포일러: stop.index · angle 은 감속을 그리려면 [정지] 순간 방송판에 가야 한다(서는 자리를 모르면 감속을 못 그린다).
     그래서 결과는 [정지] 때부터 공개다 — name 은 index 와 같은 정보라 같이 싣는다. [돌리기] 때는 아직 정하지 않는다
     (선관위를 도는 중에 바꿀 수 있어야 한다 — 옛 조종실 안내 그대로).
     🗳️ 선관위(pick) · 조작 여부(picked)는 **비공개 조각에만** 있다 — 방송판이 받는 것만으로는 조작인지 알 수 없다.
"""
import random

from ..bus import CommandError, command
from ..state import slice_
from . import session as ses
from . import show as sh

SOURCES, WEIGHTS = ('bj', 'custom'), ('equal', 'contrib')
CUSTOM_DEFAULT = ['벌칙 1', '벌칙 2', '벌칙 3', '벌칙 4', '벌칙 5']
CUSTOM_MAX, ITEM_LEN = 30, 30      # 칸이 더 많으면 글씨가 안 읽힌다(옛 것은 한도가 없었다)
STOP_MS = (3850, 4350)             # [정지] 뒤 서기까지(옛 3.85~4.35초)
EDGE_RATIO, EDGE_MAX = 0.18, 6.0   # 칸 경계에서 min(칸×18%, 6°) 안쪽에 선다 — 경계에 걸치면 눈으로 헷갈린다
HOLD_MS = 4000                     # 선 자리 보여 주기(방송판 몫 — 서버는 쓰지 않고 약속으로만 둔다)
DONE_GRACE_MS = 1000               # 방송판 시계 · 전송 지연 몫 — ends_at 1초 전부터 done 을 받는다
HISTORY_MAX = 20
IDLE = {'phase': 'idle', 'items': [], 'spin_at': 0, 'stop': None}

slice_('roulette', True, lambda: dict({'source': 'bj', 'weight': 'equal', 'custom': list(CUSTOM_DEFAULT), 'round': 0}, **IDLE))
slice_('roulette_ops', False, lambda: {'pick': None, 'history': []})


def _ms(ctx):
    return int(ctx.now * 1000)


def _clean(name):
    return ' '.join(str(name or '').split())[:ITEM_LEN]


def _rng(data):
    return random.Random(data.get('seed')) if data.get('seed') is not None else random.Random()


def _custom(raw):
    """직접 입력 칸 — 줄글(한 줄에 하나) 또는 목록. 빈 줄은 버리고, 같은 이름은 남긴다(꽝 ×3 으로 넓히는 쓰임)."""
    if isinstance(raw, str):
        raw = raw.splitlines()
    if not isinstance(raw, (list, tuple)):
        raise CommandError('칸 목록이 필요합니다')
    items = [c for c in (_clean(x) for x in raw) if c]
    if not items:
        raise CommandError('칸을 하나 이상 적어 주세요')
    if len(items) > CUSTOM_MAX:
        raise CommandError('칸은 %d개까지입니다' % CUSTOM_MAX)
    return items


def wheel(ctx):
    """지금 설정으로 만든 판 [{name, w}] — 방송판의 쉬는 판 그림과 같은 셈(화면 약속 1)."""
    r = ctx.read('roulette')
    if r['source'] == 'custom':
        return [{'name': n, 'w': 1} for n in r['custom']]
    p = ctx.read('players')
    rows = p['extra'] if p.get('extra_active') else p['list']
    contrib = r['weight'] == 'contrib'
    return [{'name': x['name'], 'w': max(1, int(x.get('contribution') or 0)) if contrib else 1} for x in rows]


def decide(items, rng, pick=None):
    """칸 · 멈출 각도 · 감속 시간을 정한다(순수 함수 — 검사가 바로 부른다).
       pick 이 판에 있으면 그 칸(같은 이름이 여럿이면 그중 무작위), 없으면 넓이(w)에 비례해 뽑는다.
       angle = 12시 칸 경계에서 시계 방향 각도(도). 돌려받는 값: (index, angle, duration_ms, picked)"""
    total = float(sum(it['w'] for it in items))
    hits = [i for i, it in enumerate(items) if pick is not None and it['name'] == pick]
    if hits:
        idx = hits[0] if len(hits) == 1 else rng.choice(hits)
    else:
        r, acc, idx = rng.random() * total, 0, len(items) - 1
        for i, it in enumerate(items):
            acc += it['w']
            if r < acc:
                idx = i
                break
    start = 360.0 * sum(it['w'] for it in items[:idx]) / total
    span = 360.0 * items[idx]['w'] / total
    m = min(span * EDGE_RATIO, EDGE_MAX)
    angle = start + m + rng.random() * max(0.0, span - 2 * m)
    dur = int(round(STOP_MS[0] + rng.random() * (STOP_MS[1] - STOP_MS[0])))
    return idx, round(angle, 3), dur, bool(hits)


def _finish(ctx):
    """다 섰다 — 판을 닫고 원래 무대로(결과는 [정지] 때 이미 적었다)."""
    ctx.edit('roulette')['phase'] = 'done'
    sh.end_temp(ctx, 'roulette')


# ── 명령 ──
@command('roulette.config')
def config(ctx, data):
    """설정 — 다음 [돌리기] 부터 적용된다(도는 판은 얼린 칸 그대로). {source?, weight?, custom?}"""
    r = ctx.edit('roulette')
    if 'source' in data:
        src = str(data.get('source') or '')
        if src not in SOURCES:
            raise CommandError('룰렛 대상은 bj(멤버) · custom(직접 입력) 중 하나입니다')
        r['source'] = src
        if src == 'custom':
            r['weight'] = 'equal'          # 옛 조종실: 직접 입력이면 같은 확률로 바꾸고 고르기를 막았다
    if 'weight' in data:
        w = str(data.get('weight') or '')
        if w not in WEIGHTS:
            raise CommandError('확률은 equal(같은 확률) · contrib(기여도 비례) 중 하나입니다')
        if w == 'contrib' and r['source'] == 'custom':
            raise CommandError('직접 입력 칸은 같은 확률만 됩니다')
        r['weight'] = w
    if 'custom' in data:
        r['custom'] = _custom(data.get('custom'))


@command('roulette.pick')
def pick(ctx, data):
    """🗳️ 선관위 — 이 칸에 서게 한다. name 이 없거나 비면 무작위로 되돌린다. 비공개 조각에만 적는다.
       도는 중(spinning)이면 이번 판 칸에서, 아니면 다음 판 칸(지금 설정)에서 찾는다."""
    name = _clean(data.get('name'))
    ops = ctx.edit('roulette_ops')
    if not name:
        ops['pick'] = None
        return
    r = ctx.read('roulette')
    items = r['items'] if r['phase'] == 'spinning' else wheel(ctx)
    if not any(it['name'] == name for it in items):
        raise CommandError('판에 없는 칸입니다: %s' % name, 404)
    ops['pick'] = name
    if r['phase'] == 'stopping':
        ctx.notes['next_round'] = True     # 이번 판은 이미 정해졌다 — 다음 판부터


@command('roulette.spin')
def spin(ctx, data):
    """돌리기 — 칸을 얼리고 무대에 잠깐 올린다. 아직 당첨은 안 정한다([정지] 때 정한다)."""
    r = ctx.read('roulette')
    if r['phase'] == 'spinning':
        ctx.notes.update({'already': True, 'round': r['round']})     # 두 번 눌러도 한 판
        return
    if r['phase'] == 'stopping':
        left = r['stop']['ends_at'] - _ms(ctx)
        if left > 0:
            raise CommandError('룰렛이 서는 중입니다 — %.1f초 뒤에 다시 눌러 주세요' % (left / 1000.0), 409)
        _finish(ctx)                       # 아무 화면도 '다 섰다' 를 못 알렸다 — 지난 판을 여기서 마저 닫는다
    items = wheel(ctx)
    if not items:
        raise CommandError('룰렛 칸이 비어 있습니다 — 선수를 넣거나 직접 입력 칸을 적어 주세요', 409)
    r = ctx.edit('roulette')
    r.update({'round': r['round'] + 1, 'phase': 'spinning', 'items': items, 'spin_at': _ms(ctx), 'stop': None})
    sh.set_stage(ctx, 'roulette', temp=True)
    ctx.notes['round'] = r['round']


@command('roulette.stop')
def stop(ctx, data):
    """정지 — 여기서 서버가 칸 · 각도 · 감속 시간을 정하고 결과를 적는다(바로 확정)."""
    r = ctx.read('roulette')
    if r['phase'] == 'stopping':
        ctx.notes.update({'already': True, 'round': r['round']})
        return
    if r['phase'] != 'spinning':
        raise CommandError('룰렛이 돌고 있지 않습니다', 409)
    idx, angle, dur, picked = decide(r['items'], _rng(data), ctx.read('roulette_ops').get('pick'))
    now = _ms(ctx)
    name = r['items'][idx]['name']
    r = ctx.edit('roulette')
    r['phase'] = 'stopping'
    r['stop'] = {'at': now, 'ends_at': now + dur, 'index': idx, 'name': name, 'angle': angle, 'duration_ms': dur}
    ops = ctx.edit('roulette_ops')
    ops['history'].insert(0, {'round': r['round'], 'name': name, 'at': now, 'picked': picked})
    del ops['history'][HISTORY_MAX:]
    ctx.notes.update({'round': r['round'], 'name': name, 'ends_at': now + dur})
    ctx.later(dur / 1000.0 + 0.3, 'roulette.done', {'round': r['round']})   # 화면이 없어도 서버가 무대를 돌려놓는다


@command('roulette.done', auth=False)
def done(ctx, data):
    """방송판(또는 조종실)이 '다 섰다' — 지금 판 · 서는 중 · ends_at 이 됐을 때만. 결과는 못 바꾸고 무대만 돌린다.
       지난 판 · 이미 닫힌 판의 보고는 조용히 무시(ignored) — 창 여러 개가 같이 보내도 한 번."""
    r = ctx.read('roulette')
    try:
        rnd = int(data.get('round'))
    except (TypeError, ValueError):
        rnd = None
    if rnd != r['round'] or r['phase'] != 'stopping':
        ctx.notes['ignored'] = True
        return
    left = r['stop']['ends_at'] - _ms(ctx)
    if left > DONE_GRACE_MS:
        raise CommandError('아직 서는 중입니다(%.1f초 남음)' % (left / 1000.0), 409)
    _finish(ctx)


@command('roulette.reset')
def reset(ctx, data):
    """회전판 초기화 — 판 상태 · 선관위를 비운다(설정 · 지난 결과 기록은 남는다).
       도는 중이었으면 원래 무대로 돌려놓는다. 서는 중에 눌렀으면 그 판 기록에 cancelled 를 단다."""
    r = ctx.edit('roulette')
    phase, rnd = r['phase'], r['round']
    r.update(IDLE, items=[])
    ops = ctx.edit('roulette_ops')
    ops['pick'] = None
    if phase == 'stopping' and ops['history'] and ops['history'][0]['round'] == rnd:
        ops['history'][0]['cancelled'] = True
    if phase in ('spinning', 'stopping'):
        sh.end_temp(ctx, 'roulette')


# ── 방송 시작 · 끝 ── 설정은 남기고 판 · 선관위 · 결과만 비운다. round 는 계속 센다(지난 방송의 늦은 done 이 새 판에 안 맞게)
def _reset(ctx, data):
    ctx.edit('roulette').update(IDLE, items=[])
    ctx.put('roulette_ops', {'pick': None, 'history': []})


ses.ON_START.append(_reset)
ses.ON_END.append(_reset)
