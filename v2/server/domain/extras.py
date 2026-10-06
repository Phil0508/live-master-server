# -*- coding: utf-8 -*-
"""🏺 모금함 · 🎬 시작 전 · 끝 화면.

조각
  fundjar (공개) name · enabled · seed(회사 종잣돈, 원) · score(후원분, **원** — 점수가 아니다)
  screen  (공개) mode(off · start · end) · title · shown_at · start_at(카운트다운 끝, ms) · names(시작 화면 출연자) ·
                 snap(방송을 끝낸 뒤 끝 화면이 보여 줄 '오늘의 기록' — 끝내는 순간 얼린다)
옛 규칙 그대로
  - 모금함 금액 = seed + score. 방송 시작 · 끝에 score 만 0(종잣돈은 그대로).
  - 대기함 후원을 모금함으로 → 금액(원)이 그대로 들어간다(점수 아님). 되돌리기는 점수와 같은 장부로.
  - 끝 화면 '오늘의 기록': 기여도 상위 3명 · 후원 순위 8명(익명 넣기 · 금액 보이기 설정을 따른다) · 한 방 최고.
v2 에서 고친 것
  - 방송 중 끝 화면은 방송판이 **지금 조각들**(players · tallies)로 그린다 — 옛 것은 서버가 매번 다시 만들어 보냈다.
    방송을 끝내는 순간에만 한 장 얼려(snap) 둔다.
"""
import uuid

from ..bus import CommandError, command
from ..state import slice_
from . import session as ses

TITLE_MAX, MINUTES_MAX, SNAP_DONORS = 40, 180, 8

slice_('fundjar', True, lambda: {'name': '모금함', 'enabled': False, 'seed': 200000, 'score': 0})
slice_('screen', True, lambda: {'mode': 'off', 'title': '', 'shown_at': 0, 'start_at': 0, 'names': [], 'snap': None})


# ── 모금함 ──
@command('fundjar.set')
def fundjar_set(ctx, data):
    j = ctx.edit('fundjar')
    if 'enabled' in data:
        j['enabled'] = bool(data.get('enabled'))
        ctx.edit('show')['hud']['fundjar'] = j['enabled']      # 옛 것은 스위치가 하나였다 — 방송판 자리도 같이
    if 'seed' in data:
        j['seed'] = max(0, int(data.get('seed') or 0))
    if 'name' in data:
        j['name'] = ' '.join(str(data.get('name') or '').split())[:20] or '모금함'


@command('fundjar.add')
def fundjar_add(ctx, data):
    d = int(data.get('delta') or 0)
    if not d:
        raise CommandError('금액을 적어 주세요')
    ref = 'act_' + uuid.uuid4().hex[:10]
    j = ctx.edit('fundjar')
    j['score'] += d
    ctx.store.add_score(j['name'], 'score', d, str(data.get('reason') or '조종실에서'), ref, ses.session_id(ctx), 'jar')
    ctx.notes['ref'] = ref


@command('fundjar.reset')
def fundjar_reset(ctx, data):
    ctx.edit('fundjar')['score'] = 0


@command('pending.to_jar')
def pending_to_jar(ctx, data):
    """대기함 후원을 모금함으로 — 금액(원) 그대로."""
    pid = data.get('id')
    pend = ctx.edit('pending')
    it = next((x for x in pend if x['id'] == pid), None)
    if it is None:
        ctx.notes['already'] = True
        return
    j = ctx.edit('fundjar')
    amt = int(it.get('amount') or 0)
    j['score'] += amt
    ctx.store.add_score(j['name'], 'score', amt, '후원 %s' % it['name'], pid, ses.session_id(ctx), 'jar')
    pend.remove(it)
    if ctx.store.donation(pid):
        ctx.store.set_donation(pid, status='assigned', player=j['name'])


# ── 시작 · 끝 화면 ──
@command('screen.set')
def screen_set(ctx, data):
    mode = str(data.get('mode') or 'off')
    if mode not in ('off', 'start', 'end'):
        raise CommandError('화면은 off · start · end 중 하나입니다')
    s = ctx.edit('screen')
    now = int(ctx.now * 1000)
    if mode != 'off':
        s['title'] = ' '.join(str(data.get('title') or '').split())[:TITLE_MAX]
        s['shown_at'] = now
    if mode == 'start':
        try:
            minutes = max(0, min(MINUTES_MAX, int(float(data.get('minutes') or 0))))
        except (TypeError, ValueError):
            minutes = 0
        s['start_at'] = (now + minutes * 60000) if minutes else 0
        names = []
        for nm in (data.get('names') if isinstance(data.get('names'), list) else [])[:10]:
            nm = ' '.join(str(nm or '').split())[:20]
            if nm and nm not in names:
                names.append(nm)
        s['names'] = names
    s['mode'] = mode


def snapshot(ctx):
    """끝 화면 '오늘의 기록' 한 장(옛 _stage_snapshot 과 같은 모양)."""
    look = ctx.read('look')
    with_anon, show_amt = bool(look.get('donor_anon')), look.get('donor_amount') is not False
    rows = sorted(ctx.read('players')['list'], key=lambda r: -int(r['contribution']))
    members = [{'name': r['name'], 'score': r['score'], 'contribution': r['contribution']} for r in rows[:3]]
    t = ctx.read('tallies')
    donors = [{'name': v.get('name') or k, 'total': int(v.get('total') or 0)} for k, v in (t.get('donors') or {}).items()
              if int(v.get('total') or 0) > 0 and (with_anon or k != '익명')]
    donors.sort(key=lambda r: (-r['total'], r['name']))
    b = t.get('best') or None
    return {'at': int(ctx.now * 1000), 'members': members,
            'donors': [{'name': r['name'], 'total': r['total'] if show_amt else None} for r in donors[:SNAP_DONORS]],
            'donor_count': len(donors), 'show_amount': show_amt,
            'best': {'name': b['name'], 'amount': b['amount'], 'member': b.get('member', '')} if b and b.get('amount') else None}


def _freeze_before_end(ctx, data):
    ctx.edit('screen')['snap'] = snapshot(ctx)


def _on_start(ctx, data):
    ctx.edit('fundjar')['score'] = 0
    s = ctx.edit('screen')
    if s['mode'] == 'end':
        s['mode'] = 'off'
    s['snap'] = None


def _on_end(ctx, data):
    ctx.edit('fundjar')['score'] = 0


ses.ON_START.append(_on_start)
ses.ON_END.insert(0, _freeze_before_end)       # ⚠️ 다른 조각을 비우기 **전에** 얼린다
ses.ON_END.append(_on_end)
