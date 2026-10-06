# -*- coding: utf-8 -*-
"""🃏 시그 뒤집기 — 시그니처를 덮어 깔고 몇 장을 뒤집는다. 뒤집힌 것이 이번 판의 '목표'이고,
제한 시간 안에 그 시그니처를 후원으로 받아내면 달성이다.

조각
  siggame      (공개)  방송판이 보는 것 — cols · rows · opacity · target · compact · cards · timer · action
                       cards 는 정본을 가린 것: 덮인 카드는 번호와 '덮임'만(옛 mask_siggame 과 같은 모양)
  siggame_deck (비공개) 정답 — picks(고른 시그니처) · cards(카드 속: sig_id · title · image · amount · state · flippedAt · doneAt)
  ⚠️ 카드의 정본은 비공개 조각이다. 공개 조각의 cards 는 sig.* 명령이 끝날 때마다 _publish 가 정본에서 **다시 만든다**
     (옛 것은 내보낼 때마다 mask_siggame 을 돌렸다 — 경로 하나에서 빠뜨려 세 번 샜다, server.py:1096-1108).
     그래서 명령은 @_sig 로만 만든다 — 새 명령을 만들어도 가리기를 잊을 수 없다.

규칙(옛 것 그대로 — features/siggame.py)
  - 고르기 sig.picks: 1~36장(:32 · :57-98). 목록에 없는 번호는 빼고 missing 으로 알려 준다.
  - 깔기 sig.deal: 고른 것을 무작위 자리에 깔고 전부 덮는다. 열 = ⌈√n⌉, 줄 = ⌈n/열⌉.
    타이머 0~180분(기본 10) · 뒤집을 장수(target) 1~고른 장수(기본 5). 깔면 무대를 차지하고 '목표만 올리기' 는 풀린다(:101-140).
  - 섞기 sig.shuffle: 자리를 다시 섞고 전부 덮는다 — 달성 기록도 지운다(새 판이나 마찬가지, :143-165). 연출 번호 1~4.
  - 뒤집기 sig.flip: 뒤집은 카드가 목표. target 장을 넘겨 못 뒤집는다 — 돈이 걸려 되돌리기보다 막는다(:168-214).
    이미 열린 카드는 already. '크게 보이는 2.6초' 는 상태로 두지 않는다(flippedAt 만 — 화면이 판단).
  - 달성 sig.done: **사람이 누른다.** 후원이 들어와도 자동으로 찍지 않는다 — 시그는 대기줄에 쌓였다 나중에 나오므로
    자동이면 아직 안 나온 시그가 달성된 것처럼 보인다(:217-244). 열린 카드만. done 을 안 주면 뒤집기(토글).
  - 올클리어 sig.allclear: 남은 목표를 한꺼번에 달성 처리하고 연출 신호 — '한 방에 몰아 쏜 후원' 용 버튼(:247-276).
    다 채웠다고 저 혼자 터지지 않는다.
  - 목표만 올리기 sig.lift: 목표 1~5장일 때만(한 줄에 6장부터는 알아볼 수 없다, :281-311). 언제 올릴지는 진행자가.
  - 나머지 까보기 sig.peek: 안 뽑힌 카드를 6초만 보여 준다. 목표 판정과 무관(:314-335 · server.py:1041 SIGGAME_PEEK_MS).
  - 전부 공개 sig.reveal: 남은 카드를 연다 — 구경용이라 flippedAt 을 안 남긴다(목표가 아니다, :338-358).
  - 타이머 sig.timer: START · PAUSE · STOP. 서버는 1초씩 세지 않고 '끝나는 시각'(expiresAt, 서버 ms)만 둔다(:361-394).
  - 설정 sig.set: 투명도 0.1~1 · target 1~깔린 장수(안 깔렸으면 36). 숫자가 아니면 그대로 둔다(:397-426).
  - 치우기 sig.clear: 카드 · 신호 · 타이머(10분)를 비우고 무대에서 내린다. 고른 시그니처는 다음 판에 다시 쓴다(:429-440).
  - 방송 시작 · 끝: 카드 · 신호 · 올리기 · 타이머를 비운다. 고른 시그니처 · 투명도 · target 은 남긴다(server.py:2100-2103).
  - 시그 대기줄 · 점수 · 기여도에는 손대지 않는다 — 옛 것도 그랬다. 후원은 평소 흐름(donation.add)대로 들어오고,
    달성은 방송판 표시일 뿐이다.
  - 무작위는 서버가 정한다. 검사는 data.seed 로 같은 배치를 다시 만든다.

v2 에서 바뀐 것(옛 구조 때문에 있던 것)
  - enabled 칸이 없다 — 무대는 show.stage 하나(sig.show 가 올리고 내린다. 옛 /api/siggame/set {enabled}).
  - picks 를 공개 조각에 안 싣는다 — 옛 것은 조종실이 쓰라고 번호만 남겨 무인증으로 내보냈다(server.py:1085-1092).
    조종실은 이제 비공개 조각을 받는다. 방송판은 picks 를 안 쓴다.
  - 까보기가 끝나면 공개 조각을 다시 덮어야 한다 — 옛 것은 내보낼 때마다 시각을 보고 가렸지만 v2 조각은 바뀔 때만 나간다.
    그래서 sig.peek_end(로그인 없이 — 방송판이 6초 뒤에 부른다)가 다시 덮는다. 0.3초보다 일찍 부르면 무시(남이 일찍 끌 수 없게).
    다른 sig.* 명령도 끝날 때 시각을 보고 다시 덮는다.
  - 올클리어 때 클립 기록(_clip_log) — 클립 모듈(domain/clip.py)이 ON_ALLCLEAR 에 걸어 적는다.
  - _siggame_state(옛 저장본 키 보정) · print 로그 · file_lock — 조각 기본값 · 명령 기록(events) · 명령 줄이 대신한다.
  - STOP 의 분도 깔기와 같이 0~180 으로 자른다(옛 것은 STOP 만 위를 안 잘랐다).

화면 약속(방송판 · 조종실)
  - 판 보이기: show.stage == 'siggame' 이고 siggame.cards 가 있을 때. 투명도 = siggame.opacity.
  - cards[i] 덮인 카드: {id, state:'HIDDEN'} — 번호만 그린다.
           까보기 중(action.type == 'PEEK' 이고 closed 가 아님)에는 image · title · amount · flippedAt · doneAt 도 실린다.
           ⚠️ state 는 HIDDEN 그대로 온다 — 까보기가 끝나면 원래대로 덮는다.
           열린 카드: {id, state:'REVEALED', image, title, amount, flippedAt, doneAt}.
  - 목표 = flippedAt 이 있는 카드. 전부 공개로 열린 카드는 flippedAt == null(목표 아님 · 도장 없음).
  - 배치: compact 이고 목표가 있고 까보기 중이 아니면 목표만 한 줄(금액 싼 것부터, 같으면 번호), 아니면 cols 열.
  - 왼쪽 숫자(앞으로 받아야 할 돈) = Σ 목표 amount 중 doneAt 이 없는 것. 받아내면 줄어든다(사장님 규칙, tests/sg_test.py:188).
  - 진행 점 = max(target, 목표 수)개, 앞에서부터 doneAt 수만큼 채운다.
  - 타이머: status 'PLAYING' 이면 남은 초 = (expiresAt − 서버 시각)/1000, 아니면 timeLeft.
           급함(urgent · 빨강) = PLAYING 이고 0 < 남은 ≤ URGENT_SEC(30). 끝남(timeup · 회색 '시간 종료') = PLAYING 이고 남은 ≤ 0.
           서버는 시간이 다 돼도 status 를 바꾸지 않는다. 시각은 전부 서버 시계 — 화면은 시계 차이를 보정한다.
  - 연출 신호 action {type, ts(서버 ms), …}: PLACE · SHUFFLE{animIndex 1~4} · FLIP{id} · DONE{id} · ALLCLEAR{count} ·
           LIFT{on} · PEEK{count, closed?} · REVEAL. ts 가 새로울 때만 한 번 튼다. 달성 취소는 action = null.
           flippedAt 부터 2.6초 크게 · doneAt 부터 8초 안이면 도장 · ALLCLEAR 는 ts 부터 8초 안일 때만.
  - 까보기 끝: ts + PEEK_MS(6000) 가 지나면 방송판이 {type:'sig.peek_end'} 를 보낸다(로그인 없이, 여러 화면이 보내도 괜찮다).
  - 조종실: 덮인 카드의 속은 siggame_deck 에 있다. ⚠️ 그리지 말 것 — 사장님도 모르는 편이 공정하고 화면 공유로 샌다
           (옛 조종실도 번호만 보였다, controller.html:10258).

명령: sig.picks{picks:[id…], sigs} · sig.deal{minutes?, target?, seed?} · sig.shuffle{seed?} · sig.flip{id} · sig.done{id, done?} ·
      sig.allclear · sig.lift{on?} · sig.peek · sig.peek_end(로그인 없이) · sig.reveal · sig.timer{action, minutes?} ·
      sig.set{opacity?, target?} · sig.show{on} · sig.clear
주소: POST /api/siggame/picks {picks:[id…]} — 시그니처 목록(바깥 왕복)을 명령 밖에서 찾아 sig.picks 에 넘긴다.
"""
import asyncio
import math
import random

from ..bus import CommandError, command
from ..state import slice_
from . import session as ses
from . import show as sh
from .legacy import route

MAX_CARDS = 36           # 6x6. 이보다 크면 상태가 무거워지고 OBS 가 버벅인다(features/siggame.py:32)
LIFT_MAX = 5             # 한 줄에 나란히 세워도 알아볼 만한 장수(:281)
PEEK_MS = 6000           # 까보기 시간 — 방송판 SG_PEEK_MS 와 같아야 한다(server.py:1041 · overlay.html:4726)
PEEK_GRACE_MS = 300      # 방송판 시계가 조금 어긋나도 끝낼 수 있게
URGENT_SEC = 30          # 화면 약속 — 남은 30초부터 빨강(overlay.html:4432). 서버는 쓰지 않는다
MINUTES_MAX = 180
DEFAULT_MINUTES = 10
DEFAULT_TARGET = 5


def _timer(minutes=DEFAULT_MINUTES):
    return {'status': 'STOPPED', 'timeLeft': int(minutes) * 60, 'expiresAt': None}


slice_('siggame', True, lambda: {'cols': 4, 'rows': 4, 'opacity': 1.0, 'target': DEFAULT_TARGET, 'compact': False,
                                 'cards': [], 'timer': _timer(), 'action': None})
slice_('siggame_deck', False, lambda: {'picks': [], 'cards': []}, hidden=True)
slice_('siggame_picks', False, lambda: {'ids': []})   # 고른 시그니처 번호만 — 조종실이 다른 기기에서도 이어 고른다(카드 속 · 자리는 안 담는다)   # 조종실에도 안 간다(옛 것과 같다 — '사장님도 모르는 편이 공정')

ON_ALLCLEAR = []         # 올클리어 때 같이 할 일 fn(ctx, 장수) — 예: 클립 모듈이 '올클리어' 클립을 적는다

_RNG = random.SystemRandom()


# ── 작은 도구 ──
def _ms(ctx):
    return int(ctx.now * 1000)


def _rng(data):
    """서버가 섞는다. 검사는 seed 로 같은 배치를 다시 만든다."""
    return random.Random(data['seed']) if data.get('seed') is not None else _RNG


def _amount(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def _clamp_int(v, lo, hi, fallback):
    try:
        x = int(v)
    except (TypeError, ValueError):
        x = fallback
    return max(lo, min(hi, x))


def _card_id(data):
    try:
        return int(data.get('id'))
    except (TypeError, ValueError):
        raise CommandError('카드 번호가 필요합니다')


def _find(deck, cid):
    return next((c for c in deck['cards'] if c['id'] == cid), None)


def _face(c):
    return {'sig_id': c.get('sig_id'), 'title': c.get('title') or '', 'image': c.get('image') or '', 'amount': c.get('amount')}


def _fresh(cid, face):
    """새로 깐 카드 — 덮임 · 목표 아님 · 달성 아님."""
    return dict(_face(face), id=cid, state='HIDDEN', flippedAt=None, doneAt=None)


def _off_stage(ctx):
    """시그뒤집기가 지금 무대면 내린다(다른 판이 올라와 있으면 그대로 — 옛 showmod.clear_stage)."""
    if ctx.read('show').get('stage') == 'siggame':
        sh.set_stage(ctx, None)


# ── 가리기 ──
def peeking(g, now_ms):
    """까보기 창이 열려 있나 — 신호가 PEEK 이고, 아직 안 닫았고, 6초가 안 지났다."""
    a = g.get('action') or {}
    return a.get('type') == 'PEEK' and not a.get('closed') and 0 <= now_ms - int(a.get('ts') or 0) < PEEK_MS


def mask(cards, peek=False):
    """정본 카드 → 방송판에 보일 카드(옛 mask_siggame 의 카드 부분, server.py:1070-1081).
       ⚠️ state 는 원래 값 그대로 — 까보기 중이라고 REVEALED 로 바꾸면 끝난 뒤에도 열린 것으로 여긴다."""
    out = []
    for c in cards:
        if c['state'] == 'REVEALED' or peek:
            out.append({'id': c['id'], 'state': c['state'], 'image': c.get('image'), 'title': c.get('title') or '',
                        'amount': c.get('amount'), 'flippedAt': c.get('flippedAt'), 'doneAt': c.get('doneAt')})
        else:
            out.append({'id': c['id'], 'state': 'HIDDEN'})
    return out


def _publish(ctx):
    """공개 조각의 cards 를 정본에서 다시 만든다 — 바뀐 게 없으면 손대지 않는다(쪽지가 안 나간다)."""
    g = ctx.read('siggame')
    want = mask(ctx.read('siggame_deck')['cards'], peeking(g, _ms(ctx)))
    if want != g['cards']:
        ctx.edit('siggame')['cards'] = want


def _sig(name, auth=True):
    """시그뒤집기 명령 — 끝나면 반드시 _publish(가리기)를 거친다."""
    def deco(fn):
        def run(ctx, data):
            fn(ctx, data)
            _publish(ctx)
        run.__name__, run.__doc__ = fn.__name__, fn.__doc__
        command(name, auth)(run)
        return fn
    return deco


# ── 명령 ──
@_sig('sig.picks')
def picks(ctx, data):
    """이번 판에 깔 시그니처를 고른다. {picks:[id…], sigs:[{id, title, image_url, amount}…]}
       sigs 는 명령 밖에서 찾아 온다(/api/siggame/picks — 바깥 왕복이라). 같은 번호를 두 번 고르면 두 장이 된다(옛 것과 같다)."""
    ids = data.get('picks')
    if not isinstance(ids, list) or not ids:
        raise CommandError('시그니처를 하나 이상 골라주세요')
    if len(ids) > MAX_CARDS:
        raise CommandError('카드는 최대 %d장까지입니다 (지금 %d장)' % (MAX_CARDS, len(ids)))
    by_id = {}
    for s in data.get('sigs') or []:
        if isinstance(s, dict):
            try:
                by_id[int(s.get('id'))] = s
            except (TypeError, ValueError):
                pass
    out, missing = [], []
    for raw in ids:
        try:
            sid = int(raw)
        except (TypeError, ValueError):
            continue
        s = by_id.get(sid)
        if not s:
            missing.append(sid)             # 고른 뒤 지워졌거나 바뀐 시그 — 조용히 빠지면 판이 한 장 모자란 채 깔린다
            continue
        out.append({'sig_id': sid, 'title': str(s.get('title') or ''), 'image': str(s.get('image_url') or ''),
                    'amount': _amount(s.get('amount'))})
    if not out:
        raise CommandError('고른 시그니처를 찾을 수 없습니다')
    ctx.edit('siggame_deck')['picks'] = out
    ctx.put('siggame_picks', {'ids': [p['sig_id'] for p in out]})
    ctx.notes.update({'count': len(out), 'missing': missing, 'requested': len(ids)})


@_sig('sig.deal')
def deal(ctx, data):
    """고른 시그니처를 무작위 자리에 깔고 전부 덮는다. {minutes?, target?, seed?}
       ⚠️ 이미 깔린 판은 뒤집은 것 · 달성까지 사라진다 — 조종실이 먼저 묻는다(controller.html:10377)."""
    pk = list(ctx.read('siggame_deck')['picks'])
    if not pk:
        raise CommandError('먼저 시그니처를 골라주세요 (아래 목록에서 선택)')
    minutes = _clamp_int(data.get('minutes', DEFAULT_MINUTES), 0, MINUTES_MAX, DEFAULT_MINUTES)
    g = ctx.edit('siggame')
    target = _clamp_int(data.get('target', g.get('target') or DEFAULT_TARGET), 1, len(pk), DEFAULT_TARGET)
    _rng(data).shuffle(pk)                  # 자리를 섞는다 — 번호만 보고는 무엇인지 알 수 없어야 한다
    n = len(pk)
    cols = int(math.ceil(math.sqrt(n)))
    rows = int(math.ceil(n / cols))
    ctx.edit('siggame_deck')['cards'] = [_fresh(i + 1, p) for i, p in enumerate(pk)]
    sh.set_stage(ctx, 'siggame')            # 📺 카드를 깔면 무대를 차지한다
    g.update({'cols': cols, 'rows': rows, 'target': target, 'compact': False, 'timer': _timer(minutes),
              'action': {'type': 'PLACE', 'ts': _ms(ctx)}})
    ctx.notes.update({'count': n, 'target': target, 'cols': cols, 'rows': rows})


@_sig('sig.shuffle')
def shuffle(ctx, data):
    """자리를 다시 섞고 전부 덮는다 — 달성 기록도 지운다(새 판이나 마찬가지). {seed?}"""
    deck = ctx.edit('siggame_deck')
    cards = deck['cards']
    if not cards:
        raise CommandError('먼저 카드를 깔아주세요')
    rng = _rng(data)
    faces = [_face(c) for c in cards]
    rng.shuffle(faces)
    deck['cards'] = [_fresh(c['id'], f) for c, f in zip(cards, faces)]
    g = ctx.edit('siggame')
    g['compact'] = False                    # 섞으면 목표가 사라지므로 올린 것도 푼다
    g['action'] = {'type': 'SHUFFLE', 'ts': _ms(ctx), 'animIndex': rng.randint(1, 4)}


@_sig('sig.flip')
def flip(ctx, data):
    """카드 한 장을 뒤집는다 — 이번 판의 목표가 된다. {id}
       ⚠️ target 장을 넘겨 못 뒤집는다. 하나 더 뒤집으면 참가자가 받아야 할 돈이 는다 — 되돌리기보다 막는다."""
    cid = _card_id(data)
    cards = ctx.read('siggame_deck')['cards']
    found = next((c for c in cards if c['id'] == cid), None)
    if found is None:
        raise CommandError('%d번 카드가 없습니다' % cid, 404)
    if found['state'] == 'REVEALED':
        ctx.notes.update({'id': cid, 'already': True, 'title': found.get('title') or ''})
        return
    opened = sum(1 for c in cards if c['state'] == 'REVEALED')
    target = int(ctx.read('siggame').get('target') or DEFAULT_TARGET)
    if opened >= target:
        raise CommandError('이미 %d장을 뒤집었습니다 (목표 %d장)' % (opened, target))
    now = _ms(ctx)
    c = _find(ctx.edit('siggame_deck'), cid)
    c['state'], c['flippedAt'] = 'REVEALED', now
    ctx.edit('siggame')['action'] = {'type': 'FLIP', 'ts': now, 'id': cid}
    ctx.notes.update({'id': cid, 'title': c.get('title') or '', 'amount': c.get('amount'),
                      'remaining_flips': target - (opened + 1)})


@_sig('sig.done')
def done(ctx, data):
    """받아냈다고 표시 · 취소 — 사람만 누른다(후원으로 자동으로 찍지 않는다). {id, done?}(없으면 뒤집기)"""
    cid = _card_id(data)
    c = _find(ctx.edit('siggame_deck'), cid)
    if c is None:
        raise CommandError('%d번 카드가 없습니다' % cid, 404)
    if c['state'] != 'REVEALED':
        raise CommandError('아직 뒤집지 않은 카드입니다')
    want = data.get('done')
    on = (not c.get('doneAt')) if want is None else bool(want)
    now = _ms(ctx)
    c['doneAt'] = now if on else None
    ctx.edit('siggame')['action'] = {'type': 'DONE', 'ts': now, 'id': cid} if on else None
    ctx.notes.update({'id': cid, 'done': on})


@_sig('sig.allclear')
def allclear(ctx, data):
    """남은 목표를 전부 달성 처리하고 올클리어 연출 — '한 방' 버튼. 다 채웠다고 저 혼자 터지지 않는다."""
    goals = [c for c in ctx.edit('siggame_deck')['cards'] if c.get('flippedAt')]
    if not goals:
        raise CommandError('뒤집은 카드가 없습니다')
    now = _ms(ctx)
    left = [c for c in goals if not c.get('doneAt')]
    for c in left:
        c['doneAt'] = now
    ctx.edit('siggame')['action'] = {'type': 'ALLCLEAR', 'ts': now, 'count': len(goals)}
    ctx.notes.update({'count': len(goals), 'filled': len(left)})
    for fn in ON_ALLCLEAR:
        fn(ctx, len(goals))


@_sig('sig.lift')
def lift(ctx, data):
    """목표만 한 줄로 올리기(on) · 판 전체로(off). {on?}(없으면 뒤집기)
       ⚠️ 옛날엔 목표를 다 뒤집는 순간 화면이 저 혼자 올렸다 — 멘트 칠 새도 없었다. 이제 진행자가 정한다."""
    g = ctx.edit('siggame')
    goals = [c for c in ctx.read('siggame_deck')['cards'] if c.get('flippedAt')]
    want = data.get('on')
    on = (not g.get('compact')) if want is None else bool(want)
    if on:
        if not goals:
            raise CommandError('뒤집은 목표가 없습니다')
        if len(goals) > LIFT_MAX:
            raise CommandError('목표가 %d장이라 올리지 않습니다. 한 줄에 %d장까지만 알아볼 만합니다' % (len(goals), LIFT_MAX))
    g['compact'] = on
    g['action'] = {'type': 'LIFT', 'ts': _ms(ctx), 'on': on}
    ctx.notes.update({'compact': on, 'goals': len(goals)})


@_sig('sig.peek')
def peek(ctx, data):
    """안 뽑힌 카드를 6초만 보여 준다('나머지 궁금하죠?'). 전부 공개와 달리 판을 닫지 않고 목표도 안 건드린다."""
    cards = ctx.read('siggame_deck')['cards']
    if not cards:
        raise CommandError('깔린 카드가 없습니다')
    rest = [c for c in cards if not c.get('flippedAt')]
    if not rest:
        raise CommandError('안 뽑힌 카드가 없습니다')
    ts = _ms(ctx)
    ctx.edit('siggame')['action'] = {'type': 'PEEK', 'ts': ts, 'count': len(rest)}
    ctx.notes.update({'count': len(rest), 'until': ts + PEEK_MS})
    ctx.later(PEEK_MS / 1000.0 + 0.05, 'sig.peek_end')     # 방송판이 없어도 서버가 6초 뒤에 덮는다


@_sig('sig.peek_end', auth=False)
def peek_end(ctx, data):
    """까보기 6초가 끝났다 — 방송판이 부른다(로그인 없이). 덮기만 하므로 누가 불러도 새는 일이 없고,
       창이 아직 0.3초 넘게 남았으면 아무것도 안 한다(남이 일찍 끌 수 없게)."""
    g = ctx.read('siggame')
    a = g.get('action') or {}
    if a.get('type') != 'PEEK' or a.get('closed'):
        ctx.notes['ignored'] = True
        return
    left = int(a.get('ts') or 0) + PEEK_MS - _ms(ctx)
    if left > PEEK_GRACE_MS:
        ctx.notes.update({'ignored': True, 'left_ms': left})
        return
    ctx.edit('siggame')['action']['closed'] = True       # ts 는 그대로 — 화면이 연출을 다시 틀지 않는다


@_sig('sig.reveal')
def reveal(ctx, data):
    """남은 카드를 전부 연다(게임이 끝난 뒤 무엇이 있었는지). 목표 추가가 아니다 — flippedAt 을 안 남긴다."""
    deck = ctx.edit('siggame_deck')
    if not deck['cards']:
        raise CommandError('깔린 카드가 없습니다')
    for c in deck['cards']:
        if c['state'] != 'REVEALED':
            c['state'], c['flippedAt'] = 'REVEALED', None
    ctx.edit('siggame')['action'] = {'type': 'REVEAL', 'ts': _ms(ctx)}


@_sig('sig.timer')
def timer(ctx, data):
    """타이머 START · PAUSE · STOP{minutes?}. 서버는 끝나는 시각만 둔다 — 늦게 붙은 화면도 시간이 안 어긋난다."""
    action = str(data.get('action') or '').upper()
    if action not in ('START', 'PAUSE', 'STOP'):
        raise CommandError('action 은 START/PAUSE/STOP')
    now = _ms(ctx)
    t = ctx.edit('siggame')['timer']
    if action == 'START' and t.get('status') != 'PLAYING':
        left = max(0, int(t.get('timeLeft') or 0))
        if left <= 0:
            raise CommandError('남은 시간이 없습니다')
        t.update({'status': 'PLAYING', 'expiresAt': now + left * 1000})
    elif action == 'PAUSE' and t.get('status') == 'PLAYING':
        left = max(0, int(((t.get('expiresAt') or now) - now) / 1000))
        t.update({'status': 'PAUSED', 'timeLeft': left, 'expiresAt': None})
    elif action == 'STOP':
        if data.get('minutes') is not None:
            left = _clamp_int(data.get('minutes'), 0, MINUTES_MAX, DEFAULT_MINUTES) * 60
        else:
            left = int(t.get('timeLeft') or 0)
        t.update({'status': 'STOPPED', 'timeLeft': max(0, left), 'expiresAt': None})
    ctx.notes['timer'] = dict(t)


@_sig('sig.set')
def set_(ctx, data):
    """투명도 · 뒤집을 장수. {opacity?, target?} — 숫자가 아니면 그대로 둔다.
       ⚠️ target 은 깔린 장수를 못 넘는다 — 넘기면 '뒤집으세요 (5/10)' 에서 영원히 멈춘다."""
    g = ctx.edit('siggame')
    if 'opacity' in data:
        try:
            g['opacity'] = max(0.1, min(1.0, float(data['opacity'])))
        except (TypeError, ValueError):
            pass
    if 'target' in data:
        try:
            cap = len(ctx.read('siggame_deck')['cards']) or MAX_CARDS
            g['target'] = max(1, min(cap, int(data['target'])))
        except (TypeError, ValueError):
            pass
    ctx.notes.update({'opacity': g['opacity'], 'target': g['target']})


@_sig('sig.show')
def show_(ctx, data):
    """방송에 띄우기 · 내리기 {on} — 무대(show.stage)에 올린다. 카드가 없어도 켜지긴 한다(조종실이 알려 준다)."""
    if data.get('on', True):
        sh.set_stage(ctx, 'siggame')
    else:
        _off_stage(ctx)
    ctx.notes.update({'on': ctx.read('show').get('stage') == 'siggame', 'cards': len(ctx.read('siggame_deck')['cards'])})


@_sig('sig.clear')
def clear(ctx, data):
    """판을 치운다. 고른 시그니처는 남겨 다음 판에 그대로 쓴다."""
    ctx.edit('siggame_deck')['cards'] = []
    ctx.edit('siggame').update({'action': None, 'compact': False, 'timer': _timer()})
    _off_stage(ctx)


# ── 방송 시작 · 끝 — 판은 방송 1회분, 고른 시그니처 · 투명도 · target 은 설정이라 남긴다 ──
def _reset(ctx, data):
    ctx.edit('siggame_deck')['cards'] = []
    ctx.edit('siggame').update({'cards': [], 'action': None, 'compact': False, 'timer': _timer()})


ses.ON_START.append(_reset)
ses.ON_END.append(_reset)


# ── 주소 — 시그니처 목록은 바깥 왕복이라 명령 밖에서 찾아 넘긴다 ──
@route('/api/siggame/picks')
async def picks_route(req, bus, authed, answer):
    """POST {picks:[id…]} → sig.picks. 답은 /api/cmd 와 같은 모양({ok, seq, count, missing, requested})."""
    if not authed(req):
        return answer({'ok': False, 'error': '로그인이 필요합니다', 'code': 401})
    try:
        body = await req.json()
    except Exception:
        body = None
    body = body if isinstance(body, dict) else {}
    ids = body.get('picks')
    sigs = []
    if isinstance(ids, list) and 0 < len(ids) <= MAX_CARDS:     # 거를 것은 명령이 거른다 — 여기선 쓸데없는 조회만 안 한다
        want = set()
        for x in ids:
            try:
                want.add(int(x))
            except (TypeError, ValueError):
                pass
        rows = await asyncio.to_thread(bus.sigs.rows)
        for r in rows or []:
            try:
                rid = int(r.get('id'))
            except (TypeError, ValueError):
                continue
            if rid in want:                  # 고른 것만 넘긴다 — 명령 기록(events)에 목록 전체가 쌓이지 않게
                sigs.append({k: r.get(k) for k in ('id', 'title', 'image_url', 'amount')})
    return answer(await bus.run('sig.picks', {'picks': ids, 'sigs': sigs}, by='http', authed=True))
