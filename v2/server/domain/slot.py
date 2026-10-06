# -*- coding: utf-8 -*-
"""🎰 시그니처 슬롯머신 — **서버가** 당첨 시그니처를 뽑고, 방송판은 릴을 그 자리에 세우기만 한다.

조각
  slot     (공개)  round · phase(idle|spinning|done) · spin_at · ends_at(ms) · winner{id, title, amount, image_url} | None
                   reel[{id, title, amount, image_url}](릴을 채울 후보, 30개까지) · seed(릴 채우기 순서 — 창마다 같게)
  slot_ops (비공개) price(한 판 값, 기본 20,000원) · pool[시그니처 id(문자열)](이번 방송 후보 — 비면 전체)

명령: slot.config{price?, pool?} · slot.spin{sigs, seed?}(sigs 는 명령 밖에서 받아 온다 — 주소 /api/slot/spin) ·
      slot.done{round}(로그인 없이)
주소: POST /api/slot/spin (로그인) — 옛 조종실 · 폰(mobile.html) 과 같은 주소. 시그니처 목록을 명령 **밖에서** 받아 넘긴다.

옛 규칙 그대로
  - 후보: 고른 후보(pool)가 있으면 그 안에서만, 목록에 하나도 없으면 전체에서(features/reaction.py:155-162).
  - 당첨: 후보 중 고르게 하나(random.choice — features/reaction.py:164).
  - 한 번에 한 판 — 도는 중 [돌리기] 는 409 '슬롯이 아직 돌고 있어요'(features/reaction.py:110-141).
    목록 조회 **전에** 먼저 본다(느린 길이라 그 사이에 한 번 더 들어온다 — features/reaction.py:135).
  - 돌리면 무대에 잠깐(temp) 올리고(features/reaction.py:180), 4초 뒤(SLOT_RESULT_DELAY_SEC — server.py:616) 원래 무대로(server.py:637).
  - 당첨 시그니처는 대기줄로: 보낸 이 '🎰 슬롯머신' · 메시지 '[슬롯 당첨] 제목' · 후원 팝업 없이(skip_popup) ·
    시그 순위에 안 셈(count_tally=False) (server.py:638-639). 묶이지도 않는다(reaction.enqueue 규칙).
  - 기여도 카드: man_won(당첨 값 − 한 판 값) 이 0보다 크면 대기함에 '🎰 슬롯 당첨' 카드(점수 0 · 기여도만).
    한 판 값을 빼는 까닭 — 한 판을 산 후원이 들어올 때 이미 점수 · 기여도가 올라갔다(두 번 세지 않게).
    받을 사람은 조종실이 고른다 — 굴린 사람이 없다(server.py:640-660 · features/dicegame.py:470 _contrib_alert).
  - 한 판 값 · 후보는 방송이 바뀌어도 남는다(server.py:3191-3194). 판 상태만 비운다.
  - 한 판은 후원(기본 2만 원)으로 사지만 **자동으로 돌지 않는다** — 그 후원은 평소처럼 배정되고, 운영자가 [돌리기] 를 누른다
    (옛 후원 경로 어디에도 슬롯을 부르는 곳이 없다). 그래서 donation 에 걸 고리가 필요 없다.
v2 에서 고친 것
  - ⭐ 옛 조종실은 브라우저에서 당첨을 뽑아 winner · candidates 로 보냈다(controller.html:4171 triggerSlotSpin) → 없앴다. 서버만 뽑는다.
  - 당첨 처리를 4초 타이머로 미루지 않는다 — [돌리기] 한 번에 다 한다(대기줄 · 카드). 대기줄 항목에 play_after=ends_at 을
    달아 방송판이 릴이 선 뒤에 튼다. 옛 타이머는 서버를 다시 켜면 사라졌고, 늦게 깨면 두 번 불릴 뻔해 판 번호 문지기를
    따로 둬야 했다(features/reaction.py:110-127). 이제 결과는 명령 하나 안에서 생기고, 실패하면 아무것도 안 남는다.
  - 무대 돌려놓기만 slot.done 으로 — 로그인 없이 받되 ① 지금 판(round) ② 도는 중 ③ ends_at − 1초가 지났을 때만.
    결과는 이미 정해져 있어 done 으로는 바꿀 수 없다. 아무도 done 을 안 보내도 다음 [돌리기] 가 지난 판을 닫는다.
  ⚠️ 순서가 옛 것과 조금 다르다: 당첨 시그가 [돌리기] 순간 대기줄에 들어가므로, 릴이 도는 4초 사이 들어온 후원 시그는
     그 **뒤에** 선다(옛 것은 4초 뒤에 넣어 그 앞에 섰다). 슬롯 소리가 릴 바로 뒤에 나오는 편이 맞다고 봤다.

화면 약속(방송판 · web/overlay/widgets/slot.js 가 지킬 것)
  1. round 가 바뀌고 phase=spinning: 슬롯판을 띄우고 릴 셋을 reel 카드로 채운다(seed 로 섞은 순서 — 창마다 같게),
     각 릴 맨 끝 칸 = winner. 0.1초 뒤 0.25초 간격으로 1.5 · 1.9 · 2.3초 동안 세우고, 3.2초에 '[제목] 당첨!!' · 꽃가루
     (옛 overlay.html:11113-11193 그대로). 카드 높이 120px 고정 — 서는 좌표가 그 숫자에 묶여 있다.
  2. ends_at(= spin_at + 4초)에 slot.done{round} — 로그인 없이. 조종실도 ends_at + 1초에 한 번(방송판이 꺼져 있어도 무대가 돌아오게).
     먼저 온 하나만 받고 나머지는 ignored. 무대(stage)가 slot 이 아니게 되면 슬롯판을 내린다.
  3. 당첨 시그니처 소리는 슬롯판이 직접 틀지 않는다 — 대기줄(queue) 항목이 play_after(=ends_at) 뒤에 평소처럼 나온다
     (옛 slot.html 처럼 직접 틀면 두 번 난다).
  4. 늦게 붙은 창: now ≥ ends_at 이면 릴을 돌리지 말고 당첨 칸을 바로 보여 준다(그리고 done).
  ⚠️ 스포일러: winner 는 [돌리기] 순간 공개 조각에 실린다 — 릴 끝 칸에 그려야 하니 피할 수 없다(옛 것도 slot_spin 이벤트로
     바로 보냈다). 방송판은 3.2초 전에 제목 글자를 띄우지 않는다. 한 판 값 · 후보 목록은 방송판이 쓸 일이 없어 비공개 조각에.
     대기함 카드(비공개)도 [돌리기] 순간 생긴다 — 조종실은 ends_at 전에 카드를 흐리게 둘 수 있다(card.reveal_at).
"""
import asyncio
import random
import time

from fastapi.responses import JSONResponse

from ..bus import CommandError, command
from ..state import slice_
from . import donation as dn
from . import reaction as rx
from . import session as ses
from . import show as sh
from .legacy import route
from .rules import man_won

SLOT_RESULT_DELAY_MS = 4000      # 릴 정지 + 당첨 배너(약 3.3초) 뒤 무대를 돌려놓기까지(옛 SLOT_RESULT_DELAY_SEC 4.0)
DONE_GRACE_MS = 1000             # 방송판 시계 · 전송 지연 몫 — ends_at 1초 전부터 done 을 받는다
PRICE_DEFAULT, PRICE_MAX = 20000, 10000000
POOL_MAX, REEL_MAX = 500, 30
DONATOR, CARD_NAME = '🎰 슬롯머신', '🎰 슬롯 당첨'
CARD_FIELDS = ('id', 'title', 'amount', 'image_url')     # 방송판에 싣는 것 — 소리 주소는 대기줄이 들고 간다
IDLE = {'phase': 'idle', 'spin_at': 0, 'ends_at': 0, 'winner': None, 'reel': [], 'seed': 0}

slice_('slot', True, lambda: dict({'round': 0}, **IDLE))
slice_('slot_ops', False, lambda: {'price': PRICE_DEFAULT, 'pool': []})


def _ms(ctx):
    return int(ctx.now * 1000)


def _card(sig):
    c = {k: sig.get(k) for k in CARD_FIELDS}
    c['title'] = str(c['title'] or '시그니처')
    c['amount'] = int(c['amount'] or 0)
    c['image_url'] = str(c['image_url'] or '')
    return c


def _sigs(raw):
    """명령 밖에서 받아 온 시그니처 목록 — id · 금액이 없는 줄은 버린다."""
    out = []
    for s in raw if isinstance(raw, (list, tuple)) else []:
        if not isinstance(s, dict) or s.get('id') is None:
            continue
        try:
            int(s.get('amount'))
        except (TypeError, ValueError):
            continue
        out.append(s)
    return out


def candidates(sigs, pool):
    """후보 — pool 이 있으면 그 안에서만, 하나도 안 맞으면 전체. 돌려받는 값: (후보, pool 이 빗나갔나)"""
    if not pool:
        return sigs, False
    want = set(str(x) for x in pool)
    hit = [s for s in sigs if str(s.get('id')) in want]
    return (hit, False) if hit else (sigs, True)


def card_contrib(amount, price):
    """기여도 카드 값 — man_won(당첨 값 − 한 판 값), 0 아래는 0."""
    return max(0, man_won(int(amount or 0) - int(price or 0)))


def _finish(ctx):
    ctx.edit('slot')['phase'] = 'done'
    sh.end_temp(ctx, 'slot')


# ── 명령 ──
@command('slot.config')
def config(ctx, data):
    """한 판 값 · 이번 방송 후보. {price?, pool?:[id…]} — pool 은 통째로 바꾼다(빈 목록 = 전체에서)."""
    ops = ctx.edit('slot_ops')
    if 'price' in data:
        try:
            price = int(data.get('price'))
        except (TypeError, ValueError):
            raise CommandError('한 판 값은 숫자입니다')
        if not 0 <= price <= PRICE_MAX:
            raise CommandError('한 판 값은 0 ~ %s원입니다' % format(PRICE_MAX, ','))
        ops['price'] = price
    if 'pool' in data:
        raw = data.get('pool')
        if not isinstance(raw, (list, tuple)):
            raise CommandError('후보는 시그니처 id 목록입니다')
        pool = []
        for x in raw:
            k = str(x).strip()
            if k and k not in pool:
                pool.append(k)
        if len(pool) > POOL_MAX:
            raise CommandError('후보는 %d개까지입니다' % POOL_MAX)
        ops['pool'] = pool


@command('slot.spin')
def spin(ctx, data):
    """돌리기 — 당첨을 뽑고, 무대에 잠깐 올리고, 당첨 시그를 대기줄에(릴이 선 뒤 재생) · 기여도 카드를 대기함에. 한 번에 다 한다.
       sigs 는 명령 밖에서 받아 온다(바깥 왕복은 명령 안에서 하지 않는다)."""
    s = ctx.read('slot')
    now = _ms(ctx)
    if s['phase'] == 'spinning':
        left = s['ends_at'] - now
        if left > 0:
            raise CommandError('슬롯이 아직 돌고 있어요 — %.1f초 뒤에 다시 눌러 주세요' % (left / 1000.0), 409)
        _finish(ctx)                       # 아무 화면도 '다 섰다' 를 못 알렸다 — 지난 판을 여기서 마저 닫는다
    sigs = _sigs(data.get('sigs'))
    if not sigs:
        raise CommandError('등록된 시그니처가 없습니다.')
    ops = ctx.read('slot_ops')
    cands, missed = candidates(sigs, ops['pool'])
    rng = random.Random(data.get('seed')) if data.get('seed') is not None else random.Random()
    win = rng.choice(cands)
    reel = [_card(x) for x in rng.sample(cands, min(REEL_MAX, len(cands)))]
    ends = now + SLOT_RESULT_DELAY_MS
    s = ctx.edit('slot')
    s.update({'round': s['round'] + 1, 'phase': 'spinning', 'spin_at': now, 'ends_at': ends, 'winner': _card(win),
              'reel': reel, 'seed': rng.randrange(1, 2 ** 31)})
    sh.set_stage(ctx, 'slot', temp=True)
    title = s['winner']['title']
    amount = s['winner']['amount']
    rx.enqueue(ctx, win, amount=amount, donator=DONATOR, message='[슬롯 당첨] %s' % title,
               skip_popup=True, play_after=ends, count_tally=False)
    price = int(ops['price'])
    c = card_contrib(amount, price)
    cid = None
    if c:
        cid = dn.add_pending_card(ctx, CARD_NAME, c, '%s (%s원 − 한 판 %s원)' % (title[:40], format(amount, ','), format(price, ',')),
                                  src='slot', round=s['round'], reveal_at=ends)
    ctx.notes.update({'round': s['round'], 'winner': s['winner'], 'ends_at': ends, 'card': cid,
                      'queue_id': ctx.read('queue')['items'][-1]['id']})
    ctx.later(SLOT_RESULT_DELAY_MS / 1000.0 + 0.3, 'slot.done', {'round': s['round']})   # 화면이 없어도 서버가 무대를 돌려놓는다
    if missed:
        ctx.notes['pool_missing'] = True   # 고른 후보가 목록에 하나도 없어 전체에서 뽑았다


@command('slot.done', auth=False)
def done(ctx, data):
    """방송판(또는 조종실)이 '릴이 다 섰다' — 지금 판 · 도는 중 · ends_at 이 됐을 때만 무대를 돌려놓는다.
       지난 판 · 이미 닫힌 판의 보고는 조용히 무시(ignored)."""
    s = ctx.read('slot')
    try:
        rnd = int(data.get('round'))
    except (TypeError, ValueError):
        rnd = None
    if rnd != s['round'] or s['phase'] != 'spinning':
        ctx.notes['ignored'] = True
        return
    left = s['ends_at'] - _ms(ctx)
    if left > DONE_GRACE_MS:
        raise CommandError('아직 릴이 돌고 있습니다(%.1f초 남음)' % (left / 1000.0), 409)
    _finish(ctx)


# ── 방송 시작 · 끝 ── 한 판 값 · 후보는 남기고 판 상태만 비운다. round 는 계속 센다
def _reset(ctx, data):
    ctx.edit('slot').update(IDLE, reel=[])


ses.ON_START.append(_reset)
ses.ON_END.append(_reset)


# ── 주소 — 시그니처 목록(바깥 왕복)을 명령 밖에서 받아 slot.spin 에 넘긴다 ──
def _err(msg, code):
    return JSONResponse({'status': 'error', 'message': msg}, status_code=code)


@route('/api/slot/spin')
async def slot_spin_route(req, bus, authed, answer):
    """[돌리기] — 로그인 필요. 몸통은 안 본다(옛 winner · candidates 는 받지 않는다 — 서버만 뽑는다)."""
    if not authed(req):
        return _err('로그인이 필요합니다', 401)
    s = bus.state.get('slot')
    left = s['ends_at'] - int(time.time() * 1000)
    if s['phase'] == 'spinning' and left > 0:          # 느린 목록 조회 전에 먼저 본다(옛 것과 같다)
        return _err('슬롯이 아직 돌고 있어요 — %.1f초 뒤에 다시 눌러 주세요' % (left / 1000.0), 409)
    rows = await asyncio.to_thread(bus.sigs.rows)
    res = await bus.run('slot.spin', {'sigs': rows}, by='http', authed=True)
    if not res.get('ok'):
        return _err(res.get('error') or '실패', int(res.get('code') or 400))
    return {'status': 'success', 'winner': res.get('winner'), 'round': res.get('round'),
            'pool_missing': bool(res.get('pool_missing'))}
