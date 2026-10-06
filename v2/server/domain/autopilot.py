# -*- coding: utf-8 -*-
"""🤖 무인 방송(자동 진행 · autopilot) — 대표님 10-07 "모든 걸 맡기고 쉴 정도의 자동화".

고른 것 두 가지
  (1) 후원 → 누구 점수인지를 **기계가** 정한다(사람이 누르던 대기함 이름 단추)
  (2) 후원 금액으로 게임을 건다(룰렛 · 슬롯 · 주사위)
시작은 **그림자 모드** — 기계는 '했을 일' 만 적고 사람이 그대로 누른다. 2~3주 뒤 맞힌 비율을 보고 **켬** 으로 바꾼다.

조각 autopilot (비공개 — 조종실만)
  mode     'off'(끔) · 'shadow'(그림자, 기본) · 'on'(켬)      — 처음 값은 LM2_AUTOPILOT 로 바꿀 수 있다(검사는 off)
  use_ai   True — 이름 · 별명 · 이력으로 못 풀면 AI 에게도 묻는다(LM2_AI_OFF · 키 없음이면 저절로 안 묻는다)
  games    [{id, min, max(0 = 끝없음), game: roulette|slot|dice, on}] — 위에서부터 처음 맞는 줄 하나만
  stats    {session:{…}, total:{…}} — n(본 후원) · agree(맞힘) · disagree(틀림) · unknown(몰라서 보류) · ignored(무시)
           · auto_done(자동으로 줌) · auto_undone(자동으로 준 것을 사람이 되돌림) · games(게임 — 그림자는 '했을 것')
           ⚠️ session 은 방송 시작 때 0 으로, total 은 지우기 전까지 남는다. 시험 후원(toon_t2_)은 안 센다.
  log      최근 60건 [{at(ms), id, name, amount, sid, mode, target, confidence, tier, source, why, act, held?,
                       outcome: pending|agree|disagree|unknown|ignored|auto, human?, by?, game?, undone?, …}]
대기함 카드(pending 조각)에 붙는 것: auto {target, confidence, tier, source, why, history, at, act, mode, held?, retry?,
                                          asking?(판단 중), game?} — 조종실 배지가 이걸 읽고 /api/audit/suggest 를 안 부른다.

판단 흐름(명령 줄을 막지 않는다 — bus.py)
  1. 후원이 대기함에 들어오는 그 명령 안(donation.AFTER_DONATION): 금액 게임 줄을 맞춰 보고(그림자면 '했을 것' 만 적고,
     켬이면 auto.roulette · auto.slot 을 예약), 카드에 '판단 중' 표시를 붙이고 auto.decide 를 0초 뒤로 예약한다.
  2. auto.decide {id} — 규칙 단계(donor_memory.suggest_rules — 장부 읽기라 명령 안에서 바로).
     풀리면 적는다. 못 풀고 AI 를 쓰면 auto.ai 를 0초 뒤로 예약 — 그 PREFETCH 가 **명령 밖 · 다른 갈래**에서
     ai.nim_suggest_target 을 부른다(네트워크만, 장부는 안 읽는다). auto.ai 는 suggest_after_ai 로 마무리해 적는다.
     AI 가 붐비면(retry) 20초 × n 뒤 다시(세 번까지) — 조종실 배지와 같은 규칙.
     답은 ai._SUGGEST_CACHE 에도 넣는다(열쇠가 /api/audit/suggest 와 같다 → 폰 · PC 조종실 · 상황판이 AI 를 또 안 부른다).
  3. 켬: tier 'auto'(0.90↑ — ai · donor_memory 와 같은 문턱) · 지금 판 선수 · 되돌려 돌아온 것 아님 · 시험 후원 아님 →
     **같은 명령 안에서** pending.assign 처리 함수를 그대로 부른다(점수 · 기록 · 되돌리기 · 후원자 기억이 사람이 누른 것과 똑같다).
     그 밖은 대기함에 그대로 둔다(보류) — 틀리게 주는 것보다 안 주고 기다리는 게 언제나 낫다.
     ⚠️ AI 답은 최대 0.88 이라(donor_memory) AI 혼자서는 절대 자동으로 주지 않는다.
  4. 그림자 채점: 사람이 그 카드를 주거나(donation.ON_ASSIGN) 무시하면(donation.ON_IGNORE) 맞힘 · 틀림을 센다.
     - 기계가 '줬을 것'(act) 이면: 한 사람에게 줬으면 이름이 같을 때 맞힘. 나눠 주기는 그 안에 기계가 고른 사람이 있으면 맞힘
       (일부만 맞아도 '사람을 맞혔다' 로 본다 — 기록 줄에 '나눠 줌' 표시). 무시 · 모금함이면 틀림(기계라면 점수를 줬다).
     - 기계가 '보류' 였으면: 사람이 주면 몰라서 보류(unknown) · 무시하면 무시(ignored).
     - 조종실 🚗 오토파일럿(브라우저 쪽)이 준 것(via:'ap')은 사람 판단이 아니라 '자동으로 줌' 으로 센다.
     - 되돌리면(score.undo): 그 판정을 빼고 카드가 대기함으로 돌아오며 판단을 다시 붙인다 — 사람이 다시 줄 때 다시 센다.
       자동으로 준 것을 되돌리면 auto_undone 을 하나 센다(켬을 계속 둘지 보는 숫자).
  5. 금액 게임(켬): 룰렛 — 무대가 비었거나 룰렛일 때만 돌리고 6초 뒤 auto.roulette_stop(그 판 번호일 때만 멈춘다).
     슬롯 — 시그니처 목록은 auto.slot 의 PREFETCH 가 명령 밖에서 받는다(/api/slot/spin 과 같은 길).
     주사위 — 주사위판이 무대에 있고, 받는 사람이 정해지고(자동이든 사람이든), 금액 ≥ 한 판 값일 때 그 사람 말을 굴린다.
     이미 도는 중 · 다른 판이 무대에 있으면 안 하고 까닭을 적는다. 자동으로 한 일은 전부 log 에 남는다.

명령: auto.set {mode?, use_ai?} · auto.games {rules:[…]} · auto.reset_stats {scope:'session'|'total'}
      (서버가 스스로 부르는 것) auto.decide · auto.ai · auto.roulette · auto.roulette_stop · auto.slot · auto.dice
"""
import copy
import os
import re
import time
import uuid

from ..bus import AFTER, PREFETCH, CommandError, command
from ..state import slice_
from . import ai
from . import ai_facts as af
from . import dicegame as dg
from . import donation as dn
from . import donor_memory as dm
from . import players as pl
from . import roulette as rl
from . import session as ses
from . import slot as sl

MODES = ('off', 'shadow', 'on')
GAMES = ('roulette', 'slot', 'dice')
GAME_LABEL = {'roulette': '룰렛', 'slot': '슬롯', 'dice': '주사위'}
RULES_MAX = 20
AMOUNT_MAX = 10000000
LOG_MAX = 60
AI_RETRY_MAX, AI_RETRY_SEC = 3, 20          # 조종실 배지(suggest.js)와 같은 규칙 — 20초 × n, 세 번까지
ROULETTE_STOP_SEC = 6.0                     # 룰렛을 돌리고 저절로 멈추기까지
DICE_RETRY_MAX, DICE_RETRY_SEC = 5, 2.5     # 앞 굴림 연출이 안 끝났으면(429) 조금 뒤 다시
STAT_KEYS = ('n', 'agree', 'disagree', 'unknown', 'ignored', 'auto_done', 'auto_undone', 'games')
HELD = {                                    # 기계가 스스로 안 준 까닭(켬일 때 배지 · 그림자일 때 '자동이라면 보류')
    'unsure': '확실하지 않아서',
    'returned': '되돌려 돌아온 후원이라 사람이 다시 정해요',
    'test': '시험 후원이라 자동으로 안 줘요',
    'failed': '자동으로 주려다 막혔어요',
    'retry': 'AI 가 붐벼 조금 뒤 다시 물어봐요',
}


def _zero():
    return {k: 0 for k in STAT_KEYS}


def _default():
    # 처음 값 — 검사(v2/tests/__init__.py)는 off 로 시작한다(후원마다 서버가 스스로 움직이면 다른 검사가 들쭉날쭉해진다)
    m = (os.environ.get('LM2_AUTOPILOT') or 'shadow').strip().lower()
    return {'mode': m if m in MODES else 'shadow', 'use_ai': True, 'games': [],
            'stats': {'session': _zero(), 'total': _zero()}, 'log': []}


slice_('autopilot', False, _default)


# ── 작은 도구 ──
def _ms(ctx):
    return int(ctx.now * 1000)


def _safe(fn):
    """고리(다른 명령 안에서 불리는 것)는 넘어져도 그 명령을 망치지 않는다 — 후원 · 점수가 먼저다."""
    def run(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:
            print('⚠️ [무인 방송] %s 실패 — 후원 · 점수는 그대로 갑니다: %s' % (fn.__name__, type(e).__name__), flush=True)
            return None
    run.__name__ = fn.__name__
    return run


def _is_donation(it):
    """후원 카드인가 — 퇴근 · 탈출 카드 · 기여도 카드 · 화면에만 뜬 것은 판단하지 않는다(ai.py audit_suggest 와 같다)."""
    return isinstance(it, dict) and it.get('type') != 'off_work' and it.get('kind') != 'contrib' and not it.get('display_only')


def _names(ctx):
    """지금 판 선수 — 번외 판이 켜져 있으면 번외 판(pending.assign 이 기본으로 주는 판 · AI 배지와 같다)."""
    return af.current_names({'players': ctx.read('players')})


def _pending(ctx, pid, edit=False):
    lst = ctx.edit('pending') if edit else ctx.read('pending')
    return next((x for x in lst if isinstance(x, dict) and x.get('id') == pid), None)


def _row(ap, pid):
    return next((r for r in ap.get('log') or [] if r.get('id') == pid), None)


def _bump(ctx, ap, key, row=None, d=1):
    """숫자 세기 — 이번 방송(그 줄의 방송이 지금 방송일 때만) · 전체. 시험 후원은 안 센다."""
    if row is not None and row.get('test'):
        return
    st = ap.setdefault('stats', {})
    sid = ses.session_id(ctx)
    for scope in ('session', 'total'):
        if scope == 'session' and row is not None and row.get('sid') != sid:
            continue
        s = st.setdefault(scope, _zero())
        s[key] = max(0, int(s.get(key) or 0) + d)


def _new_row(ctx, ap, it):
    row = {'id': it['id'], 'at': _ms(ctx), 'name': str(it.get('name') or '')[:40], 'amount': int(it.get('amount') or 0),
           'sid': ses.session_id(ctx), 'mode': ap.get('mode'), 'outcome': 'pending'}
    if it.get('test'):
        row['test'] = True
    ap.setdefault('log', []).insert(0, row)
    del ap['log'][LOG_MAX:]
    _bump(ctx, ap, 'n', row)
    return row


def _row_for(ctx, ap, it):
    return _row(ap, it.get('id')) or _new_row(ctx, ap, it)


def _try(ctx, fn, data):
    """다른 명령의 처리 함수를 이 명령 안에서 부른다. 거절(CommandError)되면 **그 부분만** 없던 일로 —
       장부는 SAVEPOINT 로, 조각 작업본 · 덧붙임 · 예약은 부르기 전 것으로 되돌린다(이 명령의 나머지는 그대로 간다).
       돌려받는 값: (거절 까닭 | None, 코드). ⚠️ 실패하면 부르기 전에 쥐고 있던 조각 참조는 낡는다 — 다시 꺼내 쓸 것."""
    saved = {k: copy.deepcopy(v) for k, v in ctx.work.copies.items()}
    notes, timers = dict(ctx.notes), list(ctx.timers)
    db = ctx.store.db
    db.execute('SAVEPOINT lm_autopilot')
    try:
        fn(ctx, data)
    except CommandError as e:
        db.execute('ROLLBACK TO lm_autopilot')
        db.execute('RELEASE lm_autopilot')
        ctx.work.copies = saved
        ctx.notes.clear()
        ctx.notes.update(notes)
        ctx.timers[:] = timers
        return str(e), int(getattr(e, 'code', 400) or 400)
    db.execute('RELEASE lm_autopilot')
    return None, 200


def _cache(name, amount, message, names, res):
    """AI 배지와 같은 기억 — 열쇠도 같다(ai._ck). 잠깐 막힌 답(retry)은 기억하지 않는다(ai.suggest 와 같다)."""
    if res.get('retry'):
        return
    if len(ai._SUGGEST_CACHE) > ai.SUGGEST_CACHE_MAX:
        ai._SUGGEST_CACHE.clear()
    keep = {k: res.get(k) for k in ('target', 'confidence', 'tier', 'source', 'why', 'history')}
    ai._SUGGEST_CACHE[ai._ck(name, amount, message, names)] = (time.time(), keep)


def _cached(name, amount, message, names):
    hit = ai._SUGGEST_CACHE.get(ai._ck(name, amount, message, names))
    if hit and time.time() - hit[0] < ai.SUGGEST_TTL:
        return dict(hit[1])
    return None


def _stage_label(stage):
    return dg.STAGE_LABEL.get(stage, stage)


# ── 금액 게임 ──
def match_game(rules, amount):
    """위에서부터 처음 맞는 줄 하나(켜진 줄만) — min ≤ 금액 ≤ max (max 0 = 끝없음)."""
    a = int(amount or 0)
    for r in rules or []:
        if r.get('on') is False:
            continue
        mn, mx = int(r.get('min') or 0), int(r.get('max') or 0)
        if a >= mn and (mx == 0 or a <= mx):
            return r
    return None


def _would_text(game):
    return {'roulette': '이 후원이면 룰렛을 돌렸을 거예요', 'slot': '이 후원이면 슬롯을 돌렸을 거예요',
            'dice': '이 후원이면 받는 사람 말을 굴렸을 거예요'}[game]


def _set_game(ctx, pid, **fields):
    """게임 상태를 기록 줄 · (아직 대기함에 있으면) 카드에 같이 적는다. text 앞에는 그림 글자를 안 붙인다(화면이 🎡 · 🎰 · 🎲 를 붙인다)."""
    ap = ctx.edit('autopilot')
    row = _row(ap, pid)
    if row is not None:
        row['game'] = dict(row.get('game') or {}, **fields)
    it = _pending(ctx, pid)
    if it is not None and isinstance(it.get('auto'), dict):
        it = _pending(ctx, pid, edit=True)
        it['auto']['game'] = dict(it['auto'].get('game') or {}, **fields)
    return row


def _start_game(ctx, ap, row, it, rule):
    mode = ap.get('mode')
    g = {'game': rule['game'], 'rule': rule.get('id'), 'min': int(rule.get('min') or 0), 'max': int(rule.get('max') or 0),
         'mode': mode, 'at': _ms(ctx)}
    if mode == 'shadow':
        g.update(status='would', text=_would_text(rule['game']))
        _bump(ctx, ap, 'games', row)
    elif rule['game'] == 'dice':
        g.update(status='wait', text='받는 사람이 정해지면 그 사람 말을 굴려요')
    else:
        g.update(status='wait', text='%s을 돌리는 중…' % GAME_LABEL[rule['game']])
        ctx.later(0, 'auto.' + rule['game'], {'id': it['id']})
    row['game'] = g
    return g


def _dice_after_assign(ctx, pid, amount, names):
    """🎲 받는 사람이 정해졌다 — 이 후원에 주사위 줄이 걸려 있으면 그 사람 말을 굴린다(켬) · '굴렸을 것' 을 적는다(그림자)."""
    row = _row(ctx.read('autopilot'), pid)
    g = (row or {}).get('game') or {}
    if g.get('game') != 'dice' or g.get('status') not in ('would', 'wait'):
        return
    who = names[0] if len(names) == 1 else None
    d = ctx.read('dicegame')
    price = int(d.get('roll_price') or 0)
    stage = ctx.read('show').get('stage')
    why = None
    if who is None:
        why = '나눠 줘서'
    elif stage != 'dicegame':
        why = '주사위판이 무대에 없어서' if not stage else "무대에 '%s' 판이 올라가 있어서" % _stage_label(stage)
    elif int(amount or 0) < price:
        why = '한 판 값(%s원)보다 적어서' % format(price, ',')
    if g.get('status') == 'would':
        _set_game(ctx, pid, player=who, text=('이 후원이면 %s 안 굴렸을 거예요' % why) if why else
                  '이 후원이면 %s 말을 굴렸을 거예요' % who)
        return
    if ctx.read('autopilot').get('mode') != 'on':
        _set_game(ctx, pid, status='skip', text='자동 진행이 켬이 아니라 주사위를 안 굴렸어요')
        return
    if why:
        _set_game(ctx, pid, status='skip', player=who, text='%s 주사위를 안 굴렸어요' % why)
        return
    _set_game(ctx, pid, status='wait', player=who, text='%s 말을 굴리는 중…' % who)
    ctx.later(0, 'auto.dice', {'id': pid, 'player': who})


# ── 고리 1: 후원이 들어온 그 명령 안 ──
STALE_ASKING_MS = 90000     # '판단 중' 이 이만큼 묵었으면 예약이 사라진 것(서버를 다시 켰다) — 조종실은 60초면 직접 묻는다


def _rescue_stale(ctx, skip_id):
    """예약(ctx.later)은 메모리에만 있어 서버를 다시 켜면 사라진다 — 다음 후원이 올 때 묵은 '판단 중' 카드를 다시 판단에 건다."""
    now = _ms(ctx)
    for x in ctx.read('pending'):
        a = x.get('auto') if isinstance(x, dict) else None
        if not isinstance(a, dict) or not a.get('asking') or x.get('id') == skip_id:
            continue
        if now - int(a.get('at') or 0) < STALE_ASKING_MS:
            continue
        cur = _pending(ctx, x['id'], edit=True)
        cur['auto']['at'] = now
        ctx.later(0, 'auto.decide', {'id': x['id']})


@_safe
def _on_donation(ctx, name, amount):
    ap_r = ctx.read('autopilot')
    if ap_r.get('mode') not in ('shadow', 'on') or not ctx.read('session').get('live'):
        return
    pid = ctx.notes.get('id')
    _rescue_stale(ctx, pid)
    it = _pending(ctx, pid, edit=True)
    if not _is_donation(it):
        return
    names = _names(ctx)
    rule = match_game(ap_r.get('games'), it.get('amount'))
    if not names and not rule:
        return                                  # 판단할 선수도 걸린 게임도 없다(선수 없는 방송)
    ap = ctx.edit('autopilot')
    row = _row_for(ctx, ap, it)
    auto = {'at': _ms(ctx), 'mode': ap.get('mode')}
    if rule:
        auto['game'] = _start_game(ctx, ap, row, it, rule)
    if names:
        auto['asking'] = True           # 조종실은 이 표시가 있으면 /api/audit/suggest 를 안 부르고 기다린다
        row['asking'] = True
        ctx.later(0, 'auto.decide', {'id': pid})
    it['auto'] = auto


dn.AFTER_DONATION.append(_on_donation)


# ── 판단 ──
def _drop_asking(ctx, pid):
    """판단을 안 하기로 했다(꺼짐 · 선수 없음) — '판단 중' 표시만 걷는다(게임 표시는 남긴다)."""
    it = _pending(ctx, pid)
    if it is not None and isinstance(it.get('auto'), dict) and it['auto'].get('asking'):
        it = _pending(ctx, pid, edit=True)
        it['auto'].pop('asking', None)
        if set(it['auto']) <= {'at', 'mode'}:
            it.pop('auto', None)
    ap = ctx.read('autopilot')
    row = _row(ap, pid)
    if row is not None and row.get('asking'):
        _row(ctx.edit('autopilot'), pid).pop('asking', None)


@command('auto.decide')
def decide(ctx, data):
    """규칙 단계(이름 · 별명 · 이력 — 장부 읽기라 여기서 바로). 못 풀고 AI 를 쓰면 auto.ai 로 넘긴다."""
    pid = str(data.get('id') or '')
    attempt = int(data.get('attempt') or 0)
    ap = ctx.read('autopilot')
    it = _pending(ctx, pid)
    if it is None:
        ctx.notes['gone'] = True                  # 그새 사람이 줬거나 무시했다
        _drop_asking(ctx, pid)
        return
    if ap.get('mode') not in ('shadow', 'on') or not _is_donation(it):
        _drop_asking(ctx, pid)
        ctx.notes['skipped'] = True
        return
    names = _names(ctx)
    if not names:
        _drop_asking(ctx, pid)
        ctx.notes['skipped'] = True
        return
    name, amount, message = str(it.get('name') or ''), af._int(it.get('amount')), str(it.get('message') or '')
    res = _cached(name, amount, message, names)
    if res is None:
        res, pre = dm.suggest_rules(ctx.store, name, message, names)
        if res is None:
            if ap.get('use_ai', True) and ai.nim_key():
                # ④ AI — 명령 밖 · 다른 갈래(PREFETCH)에서 부른다. 장부는 거기서 안 읽으므로 재료를 지금 싸서 넘긴다
                ctx.later(0, 'auto.ai', {'id': pid, 'attempt': attempt, 'name': name, 'amount': amount, 'message': message,
                                         'names': names, 'known': [list(x) for x in pre['known']], 'hints': pre['hints'],
                                         'context': af.game_context({k: ctx.read(k) for k in ('show', 'siggame', 'match', 'home', 'hell')
                                                                     if k in ctx.bus.state.slices})})
                ctx.notes['ai'] = True
                return
            res = dm.suggest_after_ai(pre, {'target': None, 'confidence': 0.0, 'skipped': True})
            if not ap.get('use_ai', True) and not res.get('target'):
                res['why'] = 'AI 에게 안 묻기로 함 — 이름·별명·이력으로는 못 찾음'
        _cache(name, amount, message, names, res)
    _record(ctx, pid, res, names, attempt)


def _pre_ai(bus, data):
    """명령 **밖** · 다른 갈래 — AI 에게만 묻는다(네트워크). ⚠️ 장부(SQLite)는 여기서 읽지 않는다.
       언제나 dict 를 돌려준다(여기서 넘어지면 명령이 아예 안 돌아 판단 중 표시가 남는다)."""
    out = dict(data)
    try:
        hist = [tuple(x) for x in (data.get('known') or []) if isinstance(x, (list, tuple)) and len(x) == 2]
        out['ai'] = ai.nim_suggest_target(str(data.get('name') or ''), af._int(data.get('amount')), str(data.get('message') or ''),
                                          [str(n) for n in (data.get('names') or [])], hist,
                                          list(data.get('context') or []), dict(data.get('hints') or {}))
    except Exception as e:
        out['ai'] = {'target': None, 'confidence': 0.0, 'error': type(e).__name__, 'retry': True}
    return out


@command('auto.ai')
def decide_ai(ctx, data):
    """AI 답으로 마무리 — 그사이 규칙으로 풀리게 됐으면(이력이 늘었다) 규칙 답이 먼저다."""
    pid = str(data.get('id') or '')
    attempt = int(data.get('attempt') or 0)
    ap = ctx.read('autopilot')
    it = _pending(ctx, pid)
    if it is None:
        ctx.notes['gone'] = True
        _drop_asking(ctx, pid)
        return
    names = _names(ctx)
    if ap.get('mode') not in ('shadow', 'on') or not names:
        _drop_asking(ctx, pid)
        ctx.notes['skipped'] = True
        return
    name, amount, message = str(it.get('name') or ''), af._int(it.get('amount')), str(it.get('message') or '')
    res, pre = dm.suggest_rules(ctx.store, name, message, names)
    if res is None:
        ans = dict(data.get('ai') or {'target': None, 'confidence': 0.0, 'error': 'no-response', 'retry': True})
        if ans.get('target') not in names:        # 그새 선수가 바뀌었다 · 환각
            ans['target'] = None
        res = dm.suggest_after_ai(pre, ans)
    _cache(name, amount, message, names, res)
    _record(ctx, pid, res, names, attempt)


def _record(ctx, pid, res, names, attempt):
    """판단을 카드 · 기록에 적는다. 켬이고 확실하면 같은 명령 안에서 준다(pending.assign 처리 함수 그대로)."""
    it = _pending(ctx, pid)
    if it is None:
        return
    target, tier = res.get('target'), res.get('tier') or 'unknown'
    act = bool(target) and tier == 'auto' and target in names
    retry = bool(res.get('retry')) and attempt < AI_RETRY_MAX     # AI 가 붐볐다 — 20초 × n 뒤 다시(세 번까지)
    if retry:
        ctx.later(AI_RETRY_SEC * (attempt + 1), 'auto.decide', {'id': pid, 'attempt': attempt + 1})
    held = None
    if it.get('test'):
        held = 'test'
    elif it.get('returned'):
        held = 'returned'                 # ⚠️ 사람이 되돌린 것은 사람이 다시 정한다 — 켬이어도 자동으로 안 준다
    elif retry and not target:
        held = 'retry'
    elif not act:
        held = 'unsure'
    mode = ctx.read('autopilot').get('mode')
    dec = {'target': target, 'confidence': round(float(res.get('confidence') or 0), 2), 'tier': tier,
           'source': res.get('source'), 'why': res.get('why'), 'act': act, 'mode': mode}
    err = None
    if mode == 'on' and act and not held:
        ctx._autopilot_assign = pid                   # 고리(ON_ASSIGN)가 '사람이 준 것' 으로 세지 않게
        try:
            err, _code = _try(ctx, dn.pending_assign, {'id': pid, 'name': target})
        finally:
            ctx._autopilot_assign = None
        if err is None and not ctx.notes.get('already'):
            ap = ctx.edit('autopilot')
            row = _row_for(ctx, ap, it)
            row.pop('asking', None)
            row.pop('retry', None)
            row.update(dec, outcome='auto', by='auto', human=target, decided_at=_ms(ctx))
            _bump(ctx, ap, 'auto_done', row)
            for lg in ctx.edit('logs'):                # 조종실 점수 기록 줄에 '자동' 표시
                if lg.get('ref') == pid:
                    lg['by'] = 'auto'
            ctx.notes['auto_assigned'] = target
            _dice_after_assign(ctx, pid, it.get('amount'), [target])
            return
        held = 'failed'
    ap = ctx.edit('autopilot')
    row = _row_for(ctx, ap, it)
    row.pop('asking', None)
    row.update(dec)
    if retry:
        row['retry'] = True
    else:
        row.pop('retry', None)
    if held:
        row['held'] = held
    else:
        row.pop('held', None)
    if err:
        row['held_err'] = str(err)[:80]
    cur = _pending(ctx, pid, edit=True)
    if cur is None:
        return
    a = dict(dec, history=res.get('history') or [], at=_ms(ctx))
    if held:
        a['held'] = held
    if err:
        a['held_err'] = str(err)[:80]
    if retry:
        a['retry'] = True
    old = cur.get('auto') if isinstance(cur.get('auto'), dict) else {}
    if old.get('game'):
        a['game'] = old['game']
    cur['auto'] = a
    ctx.notes['decided'] = {'target': target, 'tier': tier, 'act': act, 'held': held}


# ── 고리 2: 사람이 주거나 무시했다 — 그림자 채점 ──
def _judge(ctx, it, outcome, human, extra=None):
    ap = ctx.edit('autopilot')
    row = _row_for(ctx, ap, it)
    if row.get('outcome') != 'pending':
        return row
    a = it.get('auto') or {}
    for k in ('target', 'confidence', 'tier', 'source', 'why', 'act'):
        if k in a and k not in row:
            row[k] = a[k]
    row.update(outcome=outcome, human=str(human or '')[:60], decided_at=_ms(ctx))
    row.pop('asking', None)
    row.update(extra or {})
    _bump(ctx, ap, 'auto_done' if outcome == 'auto' else outcome, row)
    return row


@_safe
def _on_assign(ctx, it, items, data):
    a = it.get('auto') if isinstance(it, dict) else None
    if not isinstance(a, dict) or getattr(ctx, '_autopilot_assign', None) == it.get('id'):
        return
    got = [x['name'] for x in items if int(x.get('delta') or 0) or int(x.get('contrib') or 0)] or [x['name'] for x in items]
    via = str((data or {}).get('via') or '')
    extra = {}
    if via == 'ap':
        outcome, extra = 'auto', {'by': 'ap'}             # 조종실 🚗 오토파일럿 — 사람 판단이 아니다
    elif a.get('asking'):
        outcome, extra = 'unknown', {'early': True}       # 기계가 판단하기 전에 사람이 먼저 줬다
    elif not a.get('act'):
        outcome = 'unknown'
    elif len(got) == 1:
        outcome = 'agree' if got[0] == a.get('target') else 'disagree'
    else:
        outcome = 'agree' if a.get('target') in got else 'disagree'
        extra = {'split': True}
    _judge(ctx, it, outcome, ' · '.join(got), extra)
    _dice_after_assign(ctx, it['id'], it.get('amount'), got)


@_safe
def _on_ignore(ctx, it):
    a = it.get('auto') if isinstance(it, dict) else None
    if not isinstance(a, dict):
        return
    # 기계라면 점수를 줬을 후원을 사람이 무시했다 → 틀림(켰다면 잘못 준 것이 된다). 기계도 보류였으면 그냥 무시
    _judge(ctx, it, 'disagree' if a.get('act') and not a.get('asking') else 'ignored', '무시함')
    _set_game_done_if_waiting(ctx, it['id'], '무시한 후원이라 주사위는 안 굴려요')


def _set_game_done_if_waiting(ctx, pid, text):
    row = _row(ctx.read('autopilot'), pid)
    g = (row or {}).get('game') or {}
    if g.get('game') == 'dice' and g.get('status') == 'wait':
        _set_game(ctx, pid, status='skip', text=text)


dn.ON_ASSIGN.append(_on_assign)
dn.ON_IGNORE.append(_on_ignore)


@_safe
def _after(ctx):
    """그 밖의 길로 대기함에서 빠진 카드(🏺 모금함 등) — 고리가 못 본 것만. 장부 상태로 가른다.
       방송 시작 · 끝에 비워진 것(장부가 아직 pending)은 사람이 정한 게 아니라 그대로 둔다."""
    if 'pending' not in ctx.work.copies:
        return
    before = ctx.bus.state.slices.get('pending') or []
    gone = [x for x in before if isinstance(x, dict) and isinstance(x.get('auto'), dict) and x.get('id')]
    if not gone:
        return
    now_ids = {x.get('id') for x in ctx.work.copies['pending'] if isinstance(x, dict)}
    for x in gone:
        if x['id'] in now_ids:
            continue
        row = _row(ctx.read('autopilot'), x['id'])
        if row is None or row.get('outcome') != 'pending':
            continue
        d = ctx.store.donation(x['id'])
        if not d or d.get('status') == 'pending':
            continue
        who = str(d.get('player') or '') if d.get('status') == 'assigned' else '무시함'
        jar = (ctx.read('fundjar') or {}).get('name') if 'fundjar' in ctx.bus.state.slices else None
        if jar and who == jar:
            who = '🏺 ' + who
        a = x['auto']
        _judge(ctx, x, 'disagree' if a.get('act') and not a.get('asking') else 'ignored', who)


AFTER.append(_after)


# ── 고리 3: 되돌리기 — 그 판정을 빼고 카드에 판단을 다시 붙인다 ──
@_safe
def _on_undo(ctx, ref):
    pid = str(ref or '')
    if not pid.startswith('don_'):
        return
    row = _row(ctx.read('autopilot'), pid)
    if row is None or row.get('outcome') not in ('agree', 'disagree', 'unknown', 'auto'):
        return
    ap = ctx.edit('autopilot')
    row = _row(ap, pid)
    prev = row['outcome']
    if prev == 'auto':
        _bump(ctx, ap, 'auto_undone', row)
        row['was_auto'] = True
    else:
        _bump(ctx, ap, prev, row, -1)
    row['outcome'] = 'pending'
    row['undone'] = int(row.get('undone') or 0) + 1
    for k in ('human', 'decided_at', 'split', 'early', 'by'):
        row.pop(k, None)
    it = _pending(ctx, pid, edit=True)              # donation 모듈이 먼저 대기함에 돌려놓았다(returned)
    if it is not None and 'target' in row:
        it['auto'] = {k: row.get(k) for k in ('target', 'confidence', 'tier', 'source', 'why', 'act', 'mode')}
        it['auto'].update(at=_ms(ctx), history=[], held='returned', undone=row['undone'])
        if prev == 'auto':
            it['auto']['was_auto'] = True


pl.ON_UNDO.append(_on_undo)


# ── 방송 시작 — 이번 방송 숫자만 0 으로(전체 · 기록 · 설정은 남는다) ──
def _on_start(ctx, data):
    ap = ctx.edit('autopilot')
    ap.setdefault('stats', {})['session'] = _zero()


ses.ON_START.append(_on_start)


# ── 금액 게임 — 서버가 스스로 부르는 명령 ──
def _game_gate(ctx, pid, label):
    """켬이 아니면 안 한다(그새 껐다)."""
    if ctx.read('autopilot').get('mode') != 'on':
        _set_game(ctx, pid, status='skip', text='자동 진행이 켬이 아니라 %s을 안 돌렸어요' % label)
        return False
    return True


@command('auto.roulette')
def auto_roulette(ctx, data):
    pid = str(data.get('id') or '')
    if not _game_gate(ctx, pid, '룰렛'):
        return
    r = ctx.read('roulette')
    stage = ctx.read('show').get('stage')
    now = _ms(ctx)
    why = None
    if r.get('phase') == 'spinning':
        why = '룰렛이 이미 돌고 있어서'
    elif r.get('phase') == 'stopping' and int((r.get('stop') or {}).get('ends_at') or 0) > now:
        why = '룰렛이 서는 중이라서'
    elif stage not in (None, 'roulette'):
        why = "무대에 '%s' 판이 올라가 있어서" % _stage_label(stage)       # 진행 중인 판을 끊지 않는다
    err = None
    if why is None:
        err, _ = _try(ctx, rl.spin, {})
    if why or err:
        _set_game(ctx, pid, status='skip', text='%s 룰렛을 안 돌렸어요' % why if why else '룰렛을 못 돌렸어요 — %s' % err)
        ctx.notes['skipped'] = why or err
        return
    rnd = ctx.read('roulette')['round']
    _set_game(ctx, pid, status='spin', round=rnd, text='룰렛을 돌렸어요 — %d초 뒤 저절로 멈춰요' % int(ROULETTE_STOP_SEC))
    ctx.later(ROULETTE_STOP_SEC, 'auto.roulette_stop', {'id': pid, 'round': rnd})


@command('auto.roulette_stop')
def auto_roulette_stop(ctx, data):
    """기계가 돌린 그 판(round)이 아직 돌고 있을 때만 멈춘다 — 사람이 먼저 멈췄거나 새로 돌렸으면 손대지 않는다.
       ⚠️ 그새 자동 진행을 껐어도 자기가 돌린 판은 멈춘다(안 그러면 판이 계속 돈다)."""
    pid = str(data.get('id') or '')
    r = ctx.read('roulette')
    try:
        rnd = int(data.get('round'))
    except (TypeError, ValueError):
        rnd = None
    if r.get('round') != rnd or r.get('phase') != 'spinning':
        _set_game(ctx, pid, status='done', text='룰렛 — 사람이 먼저 멈췄어요')
        ctx.notes['ignored'] = True
        return
    err, _ = _try(ctx, rl.stop, {})
    if err:
        _set_game(ctx, pid, status='skip', text='룰렛을 못 멈췄어요 — %s' % err)
        return
    name = ctx.notes.get('name')
    _set_game(ctx, pid, status='done', result=name, text='룰렛 결과: %s' % name)
    ap = ctx.edit('autopilot')
    _bump(ctx, ap, 'games', _row(ap, pid))


def _pre_slot(bus, data):
    """명령 밖 — 시그니처 목록(바깥 왕복 · 10분 기억). /api/slot/spin 과 같은 길. 실패하면 빈 목록(명령이 까닭을 적는다)."""
    out = dict(data)
    try:
        sigs = getattr(bus, 'sigs', None)
        out['sigs'] = sigs.rows() if sigs is not None else []
    except Exception:
        out['sigs'] = []
    return out


@command('auto.slot')
def auto_slot(ctx, data):
    pid = str(data.get('id') or '')
    if not _game_gate(ctx, pid, '슬롯'):
        return
    s = ctx.read('slot')
    stage = ctx.read('show').get('stage')
    why = None
    if s.get('phase') == 'spinning' and int(s.get('ends_at') or 0) > _ms(ctx):
        why = '슬롯이 아직 돌고 있어서'
    elif stage not in (None, 'slot'):
        why = "무대에 '%s' 판이 올라가 있어서" % _stage_label(stage)
    err = None
    if why is None:
        err, _ = _try(ctx, sl.spin, {'sigs': data.get('sigs') or []})
    if why or err:
        _set_game(ctx, pid, status='skip', text='%s 슬롯을 안 돌렸어요' % why if why else '슬롯을 못 돌렸어요 — %s' % err)
        ctx.notes['skipped'] = why or err
        return
    w = ctx.read('slot').get('winner') or {}
    _set_game(ctx, pid, status='done', result=w.get('title'), text='슬롯을 돌렸어요 — 당첨: %s' % (w.get('title') or '?'))
    ap = ctx.edit('autopilot')
    _bump(ctx, ap, 'games', _row(ap, pid))


@command('auto.dice')
def auto_dice(ctx, data):
    pid = str(data.get('id') or '')
    who = str(data.get('player') or '').strip()
    attempt = int(data.get('attempt') or 0)
    if ctx.read('autopilot').get('mode') != 'on':
        _set_game(ctx, pid, status='skip', text='자동 진행이 켬이 아니라 주사위를 안 굴렸어요')
        return
    stage = ctx.read('show').get('stage')
    if stage != 'dicegame':
        _set_game(ctx, pid, status='skip', text='주사위판이 무대에서 내려가 안 굴렸어요')
        return
    err, code = _try(ctx, dg.roll, {'piece': who, 'player': who})
    if err and code == 429 and attempt < DICE_RETRY_MAX:
        _set_game(ctx, pid, status='wait', text='앞 굴림 연출이 끝나면 %s 말을 굴려요' % who)
        ctx.later(DICE_RETRY_SEC, 'auto.dice', {'id': pid, 'player': who, 'attempt': attempt + 1})
        return
    if err:
        _set_game(ctx, pid, status='skip', text='주사위를 못 굴렸어요 — %s' % err)
        return
    eyes = ctx.notes.get('dice') or []
    _set_game(ctx, pid, status='done', result=eyes, text='%s 말을 굴렸어요 — 눈 %s' % (who, ' + '.join(str(x) for x in eyes)))
    ap = ctx.edit('autopilot')
    _bump(ctx, ap, 'games', _row(ap, pid))


PREFETCH['auto.ai'] = _pre_ai
PREFETCH['auto.slot'] = _pre_slot


# ── 조종실이 부르는 명령 ──
@command('auto.set')
def auto_set(ctx, data):
    """{mode?: off|shadow|on, use_ai?: true|false} — 켬은 조종실이 그림자 기록(맞힌 비율)을 먼저 보여 주고 한 번 묻는다."""
    if 'mode' not in data and 'use_ai' not in data:
        raise CommandError('바꿀 것(mode · use_ai)을 보내 주세요')
    ap = ctx.edit('autopilot')
    if 'mode' in data:
        m = str(data.get('mode') or '').strip().lower()
        if m not in MODES:
            raise CommandError('모드는 끔(off) · 그림자(shadow) · 켬(on) 중 하나입니다')
        if ap.get('mode') != m:
            ap['mode'] = m
            ap['mode_at'] = _ms(ctx)
            if m == 'off':                              # 판단 중 표시가 남지 않게(예약된 판단은 와서 그냥 걷는다)
                for x in ctx.read('pending'):
                    if isinstance(x, dict) and isinstance(x.get('auto'), dict) and x['auto'].get('asking'):
                        _drop_asking(ctx, x['id'])
    if 'use_ai' in data:
        if not isinstance(data.get('use_ai'), bool):
            raise CommandError('use_ai 는 true · false 입니다')
        ap['use_ai'] = data['use_ai']
    ctx.notes.update({'mode': ap['mode'], 'use_ai': ap.get('use_ai', True)})


def _amount(v, i, what):
    if isinstance(v, bool) or v is None or v == '':
        if what == '최대' and (v is None or v == ''):
            return 0
        raise CommandError('%d번째 줄: %s 금액이 숫자가 아닙니다' % (i, what))
    if isinstance(v, (int, float)):
        if isinstance(v, float) and v != int(v):
            raise CommandError('%d번째 줄: %s 금액은 원 단위 정수입니다' % (i, what))
        n = int(v)
    else:
        t = str(v).strip().replace(',', '').replace('원', '')
        if not re.fullmatch(r'\d{1,9}', t):
            raise CommandError('%d번째 줄: %s 금액이 숫자가 아닙니다' % (i, what))
        n = int(t)
    if not 0 <= n <= AMOUNT_MAX:
        raise CommandError('%d번째 줄: 금액은 0 ~ %s원입니다' % (i, format(AMOUNT_MAX, ',')))
    return n


@command('auto.games')
def auto_games(ctx, data):
    """금액 → 게임 줄을 통째로 바꾼다. {rules:[{id?, min, max(0 = 끝없음), game, on?}]} — 하나라도 틀리면 아무것도 안 바뀐다."""
    rules = data.get('rules')
    if not isinstance(rules, list):
        raise CommandError('줄 목록(rules)이 필요합니다')
    if len(rules) > RULES_MAX:
        raise CommandError('줄은 %d개까지입니다' % RULES_MAX)
    out, used = [], set()
    for i, r in enumerate(rules, 1):
        if not isinstance(r, dict):
            raise CommandError('%d번째 줄이 이상합니다' % i)
        game = str(r.get('game') or '').strip()
        if game not in GAMES:
            raise CommandError('%d번째 줄: 게임은 룰렛(roulette) · 슬롯(slot) · 주사위(dice) 중 하나입니다' % i)
        mn = _amount(r.get('min'), i, '최소')
        mx = _amount(r.get('max'), i, '최대')
        if mx and mx < mn:
            raise CommandError('%d번째 줄: 최대 금액이 최소보다 작습니다 (최대를 비우거나 0 이면 끝없음)' % i)
        rid = str(r.get('id') or '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,24}', rid) or rid in used:
            rid = 'g' + uuid.uuid4().hex[:8]
        used.add(rid)
        out.append({'id': rid, 'min': mn, 'max': mx, 'game': game, 'on': r.get('on', True) is not False})
    ctx.edit('autopilot')['games'] = out
    ctx.notes['rules'] = out


@command('auto.reset_stats')
def auto_reset_stats(ctx, data):
    """숫자 지우기 — scope 'session'(이번 방송) · 'total'(전체). 기록 줄 · 설정은 남는다."""
    scope = str(data.get('scope') or '')
    if scope not in ('session', 'total'):
        raise CommandError("scope 는 'session'(이번 방송) · 'total'(전체) 중 하나입니다")
    ctx.edit('autopilot').setdefault('stats', {})[scope] = _zero()
