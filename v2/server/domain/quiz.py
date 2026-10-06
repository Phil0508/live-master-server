# -*- coding: utf-8 -*-
"""🧩 퀴즈판 — 초성 · 사자성어 (옛 features/quiz.py 를 v2 로 옮김, 2026-10-07).

방송판에는 **네모칸만**(대표님 10-06: 바탕 · 제목 · 분류 · 남은 초 · 정답자 · 점수 없음).
조각
  quiz      (공개)  tiles[{c, s}] · revealed      ← 방송판은 이것만 받는다(정답이 안 실린다)
  quiz_ops  (비공개) kind · cur{kind, answer, note, q?} · used{kind:[…]} · custom{kind:[[답, 뜻]]} · order{kind:[…]}
칸 상태 s: q 초성 · g 처음부터 보여 줌 · b 빈칸 · h 힌트로 연 글자 · o 정답 공개
⚠️ 옛 것은 상태 한 덩어리 안에 정답 · 순서를 두고 strip_private_state 로 거르다 보니, 거르기를 잊으면 샐 수 있었다.
   v2 는 정답 · 순서가 처음부터 **비공개 조각**에 있다.
옛 규칙 그대로: 순서는 처음에 섞어서 세우고 [다음 문제]는 맨 앞 · 그날 나온 문제는 다시 안 나옴(다 돌면 처음부터) ·
지금 바로 띄우기(정답 → 초성, 초성만 → 그대로 · 힌트/공개 안 됨) · 내 문제 500개까지 · 12칸까지(방송판이 줄인다).
"""
import random

from ..bus import CommandError, command
from ..state import slice_
from . import session as ses
from . import show as sh
from .legacy import route
from .quiz_bank import CHOSUNG, IDIOMS

KINDS = ('chosung', 'idiom')
CUSTOM_MAX, NOW_MAX = 500, 12
_INITIALS = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'

slice_('quiz', True, lambda: {'tiles': [], 'revealed': False})
slice_('quiz_ops', False, lambda: {'kind': 'chosung', 'cur': None, 'used': {k: [] for k in KINDS},
                                   'custom': {k: [] for k in KINDS}, 'order': {k: [] for k in KINDS}})


def _syl(ch):
    return '가' <= ch <= '힣'


def _jamo(ch):
    return 'ㄱ' <= ch <= 'ㅣ'


def _cho(ch):
    return _INITIALS[(ord(ch) - 0xAC00) // 588] if _syl(ch) else ch


def _bank(ops, kind):
    base = CHOSUNG if kind == 'chosung' else IDIOMS
    out, seen = [], set()
    for a, b in list(base) + [tuple(x) for x in ops['custom'][kind] if isinstance(x, list) and len(x) == 2]:
        if a not in seen:
            seen.add(a)
            out.append((a, b))
    return out


def _order(ops, kind, rng, wrap=False):
    names = [a for a, _ in _bank(ops, kind)]
    have, used = set(names), set(ops['used'][kind])
    o, seen = [], set()
    for a in ops['order'][kind]:
        if a in have and a not in used and a not in seen:
            seen.add(a)
            o.append(a)
    wrapped = False
    if not o:
        rest = [a for a in names if a not in used]
        if not rest and wrap and names:
            ops['used'][kind] = []
            rest, wrapped = list(names), True
        rng.shuffle(rest)
        o = rest
    ops['order'][kind] = o
    return o, wrapped


def _tiles(kind, answer):
    chars = [c for c in str(answer) if not c.isspace()]
    if kind == 'idiom':
        return [{'c': c, 's': 'g'} if i < 2 else {'c': '', 's': 'b'} for i, c in enumerate(chars)]
    return [{'c': _cho(c), 's': 'q'} if _syl(c) else {'c': c, 's': 'g'} for c in chars]


def _rng(data):
    return random.Random(data.get('seed')) if data.get('seed') is not None else random.Random()


def _put(ctx, ops, kind, answer, note, tiles, q=None):
    if answer:
        if answer in ops['order'][kind]:
            ops['order'][kind].remove(answer)
        if answer not in ops['used'][kind] and answer in dict(_bank(ops, kind)):
            ops['used'][kind].append(answer)
    ops['kind'] = kind
    ops['cur'] = dict({'kind': kind, 'answer': answer, 'note': note}, **({'q': q} if q else {}))
    ctx.put('quiz', {'tiles': tiles, 'revealed': False})
    sh.set_stage(ctx, 'quiz')


def _ensure_orders(ctx, ops, rng):
    for k in KINDS:
        _order(ops, k, rng)


@command('quiz.next')
def quiz_next(ctx, data):
    ops = ctx.edit('quiz_ops')
    kind = data.get('kind') if data.get('kind') in KINDS else ops['kind']
    rng = _rng(data)
    o, wrapped = _order(ops, kind, rng, wrap=True)
    if not o:
        raise CommandError('문제가 없습니다')
    answer = o[0]
    _put(ctx, ops, kind, answer, dict(_bank(ops, kind)).get(answer, ''), _tiles(kind, answer))
    _ensure_orders(ctx, ops, rng)
    ctx.notes['wrapped'] = wrapped


@command('quiz.order')
def quiz_order(ctx, data):
    """순서 고치기 — up · down · top · remove(오늘은 빼기) · play(지금 띄우기) · shuffle."""
    kind, action, answer = data.get('kind'), data.get('action'), str(data.get('answer') or '')
    if kind not in KINDS or action not in ('up', 'down', 'top', 'remove', 'play', 'shuffle'):
        raise CommandError('종류 · 할 일을 다시 골라 주세요')
    ops = ctx.edit('quiz_ops')
    rng = _rng(data)
    o, _ = _order(ops, kind, rng)
    if action == 'shuffle':
        rng.shuffle(o)
        return
    if answer not in o:
        raise CommandError("'%s' 은(는) 순서에 없습니다" % answer[:20], 404)
    i = o.index(answer)
    if action == 'up' and i > 0:
        o[i - 1], o[i] = o[i], o[i - 1]
    elif action == 'down' and i < len(o) - 1:
        o[i + 1], o[i] = o[i], o[i + 1]
    elif action == 'top':
        o.insert(0, o.pop(i))
    elif action == 'remove':
        o.pop(i)
        ops['used'][kind].append(answer)
    elif action == 'play':
        _put(ctx, ops, kind, answer, dict(_bank(ops, kind)).get(answer, ''), _tiles(kind, answer))
    _ensure_orders(ctx, ops, rng)


@command('quiz.now')
def quiz_now(ctx, data):
    """지금 바로 띄우기 — 정답을 적으면 초성으로, 초성만 적으면 그대로(정답을 모르니 힌트 · 공개 안 됨)."""
    text = ''.join(str(data.get('text') or '').split())
    kind = data.get('kind') if data.get('kind') in KINDS else 'chosung'
    note = str(data.get('note') or '').strip()[:60]
    if not text:
        raise CommandError('띄울 글자를 적어 주세요')
    if len(text) > NOW_MAX:
        raise CommandError('%d글자까지만 됩니다(방송 화면 폭)' % NOW_MAX)
    jamo_only = all(_jamo(c) for c in text)
    if not jamo_only and not any(_syl(c) for c in text):
        raise CommandError('한글 정답이나 초성(ㄱ~ㅎ)을 적어 주세요')
    ops = ctx.edit('quiz_ops')
    if jamo_only:
        _put(ctx, ops, 'chosung', '', note, [{'c': c, 's': 'q'} for c in text], q=text)
    else:
        k = 'idiom' if kind == 'idiom' and len(text) == 4 and all(_syl(c) for c in text) else 'chosung'
        _put(ctx, ops, k, text, note or dict(_bank(ops, k)).get(text, ''), _tiles(k, text))
    _ensure_orders(ctx, ops, _rng(data))
    ctx.notes['jamo_only'] = jamo_only


@command('quiz.hint')
def quiz_hint(ctx, data):
    cur = ctx.read('quiz_ops')['cur']
    q = ctx.read('quiz')
    if not cur or q['revealed']:
        raise CommandError('열 글자가 없습니다 — [다음 문제]부터 눌러 주세요')
    if not cur.get('answer'):
        raise CommandError('초성만 적어 띄운 문제라 정답을 몰라요 — 열 수 없습니다')
    chars = [c for c in cur['answer'] if not c.isspace()]
    qq = ctx.edit('quiz')
    for i, t in enumerate(qq['tiles']):
        if t.get('s') in ('q', 'b') and i < len(chars):
            qq['tiles'][i] = {'c': chars[i], 's': 'h'}
            return
    raise CommandError('이미 다 열었습니다 — [정답 공개]를 눌러 주세요')


@command('quiz.reveal')
def quiz_reveal(ctx, data):
    cur = ctx.read('quiz_ops')['cur']
    if not cur:
        raise CommandError('아직 문제가 없습니다')
    if not cur.get('answer'):
        raise CommandError('초성만 적어 띄운 문제라 정답을 몰라요 — 열 수 없습니다')
    chars = [c for c in cur['answer'] if not c.isspace()]
    qq = ctx.edit('quiz')
    qq['tiles'] = [{'c': chars[i], 's': 'g' if t.get('s') == 'g' else 'o'} if i < len(chars) else t for i, t in enumerate(qq['tiles'])]
    qq['revealed'] = True


@command('quiz.show')
def quiz_show(ctx, data):
    if data.get('on'):
        if not ctx.read('quiz')['tiles']:
            raise CommandError('띄울 문제가 없습니다 — [다음 문제]를 눌러 주세요')
        sh.set_stage(ctx, 'quiz')
    elif ctx.read('show')['stage'] == 'quiz':
        sh.set_stage(ctx, None)


@command('quiz.custom')
def quiz_custom(ctx, data):
    """내 문제 더하기 — 한 줄에 하나 '정답 | 분류 · 뜻'. mode='clear' 면 비운다. 더한 문제는 순서 맨 끝."""
    kind = data.get('kind')
    if kind not in KINDS:
        raise CommandError('종류(초성 · 사자성어)를 골라 주세요')
    ops = ctx.edit('quiz_ops')
    mine = ops['custom'][kind]
    rng = _rng(data)
    if data.get('mode') == 'clear':
        ctx.notes['cleared'] = len(mine)
        mine.clear()
        ops['order'][kind] = []
        _ensure_orders(ctx, ops, rng)
        return
    _order(ops, kind, rng)
    have = {a for a, _ in _bank(ops, kind)}
    added, bad = 0, []
    for raw in str(data.get('text') or '').splitlines():
        line = raw.strip()
        if not line:
            continue
        a, _, b = line.partition('|')
        a, b = ''.join(a.split()), b.strip()[:60]
        ok = (len(a) == 4 and all(_syl(c) for c in a)) if kind == 'idiom' else (2 <= len(a) <= 10 and any(_syl(c) for c in a))
        if not ok:
            bad.append(line[:30])
            continue
        if a in have:
            continue
        if len(mine) >= CUSTOM_MAX:
            bad.append(line[:30] + ' (가득 참)')
            continue
        mine.append([a, b])
        ops['order'][kind].append(a)
        have.add(a)
        added += 1
    ctx.notes.update({'added': added, 'bad': bad[:10]})


@command('quiz.prepare')
def quiz_prepare(ctx, data):
    """조종실이 탭을 열 때 — 순서가 비어 있으면 세워 둔다(바뀐 게 없으면 아무것도 안 보낸다)."""
    ops = ctx.edit('quiz_ops')
    _ensure_orders(ctx, ops, _rng(data))


def _reset(ctx, data):
    ctx.put('quiz', {'tiles': [], 'revealed': False})
    ops = ctx.edit('quiz_ops')
    ops.update({'cur': None, 'used': {k: [] for k in KINDS}, 'order': {k: [] for k in KINDS}})


ses.ON_START.append(_reset)
ses.ON_END.append(_reset)


@route('/api/quiz/bank', methods=('GET',))
async def quiz_bank_route(req, bus, authed, answer):
    """기본 문제 목록(정답 · 분류/뜻) — 조종실 '다음 순서' 에 뜻을 같이 보여 준다(로그인). 내 문제는 quiz_ops.custom 에 있다."""
    if not authed(req):
        from fastapi.responses import JSONResponse
        return JSONResponse({'status': 'error', 'message': '로그인이 필요합니다'}, status_code=401)
    return {'status': 'success', 'bank': {'chosung': [list(x) for x in CHOSUNG], 'idiom': [list(x) for x in IDIOMS]}}
