# -*- coding: utf-8 -*-
"""🙈 메시지 금칙어 · [가리기] — 방송판에 나가는 후원 메시지만 거른다(대표님 10-17 안전 꾸러미 mask).

원칙
  - 장부 · 대기함(조종실)에는 **원문 그대로**. 거르는 것은 '내보낼 때' 만든 사본(state.VIEWS)이다 —
    방송판(로그인 없음 · 방송판 종류 화면 hub.ON_AIR_KINDS)은 원문을 아예 못 받는다(통째 · 쪽지 모두).
  - 거르는 곳(공개 조각): popup.donation.message(후원 카드 · 소액 띠) · queue.items[].message · msgs[](시그니처 카드 ·
    출연진 전광판 ?only=sig) · cast.fx.message(조종실 후원 연출) · screen 안의 message · msgs(끝 화면 — 엔딩 크레딧이 메시지를 실을 때).
  - 이름(닉네임)은 건드리지 않는다 — 닉네임 거르기는 대표님 결정으로 남겨 뒀다.
  - 걸린 부분은 ●●● 로. 무엇에 걸렸는지(hits)는 조종실에만.

거르는 것(RULES — 설정에서 하나씩 끌 수 있다)
  ① phone   전화번호 — 010-1234-5678 · 010 1234 5678 · 010.1234.5678 · +82 10 … · 02-123-4567 · 031-… · 070-…
  ② account 계좌번호 꼴 숫자 — 숫자 10~16자리(사이에 - . 한 칸 띄어쓰기 하나씩까지). 쉼표(1,000,000)는 금액이라 안 건드린다.
            띄어쓰기로 이은 것은 5자리 넘는 덩어리가 있을 때만(날짜 · 시각 '2025-10-17 21' 을 계좌로 안 보게).
  ③ url     인터넷 주소 · 메일 — http(s):// · www. · abc.com · abc.co.kr · t.me/… · 이름@메일 · 'abc 닷컴'
  ④ words   대표님 금칙어 목록(설정 화면에서 더하고 빼기, 기본 빈 목록) — 대소문자 무시, 글자 사이에 숫자 · 기호가
            두 개까지 끼어도 잡는다('시1발' · '시.발'). 띄어쓰기를 끼운 것은 안 잡는다('이 시 발표' 를 가리지 않게).
            [추천 목록 넣기] = RECOMMENDED(흔한 욕설 몇 개)를 한 번에.

[가리기] — mask.hide {id, on}
  - 후원 하나(장부 id don_…)의 메시지를 방송판에서 **통째로** 숨긴다(빈 메시지로 나간다). 지금 떠 있는 팝업 · 시그니처 카드 ·
    대기줄 · 출연진 전광판에서도 바로 — mask 조각이 바뀌면 popup · queue · cast · screen 을 새 사본으로 다시 보낸다(state.DEPENDS).
  - 묶인 시그니처 줄(×N)은 don_ids(msgs 와 같은 차례)로 그 후원 차례만. 다시 송출(encore)은 원래 후원 id(src · don_ids)로 같이 숨는다.
  - 대기줄 줄 id(rq_ — 후원 콘솔 '바로 틀기' 처럼 장부가 없는 것)도 받는다.
  - 투네이션 · 계좌 · 손 송출 모두 장부 id 가 같은 모양이라 똑같이 된다.

조각 mask(비공개 — 조종실만): {words[], rules{phone, account, url}, hidden[id…](최근 HIDDEN_MAX), ver}
"""
import functools
import re

from fastapi.responses import JSONResponse

from ..bus import CommandError, command
from ..state import DEPENDS, VIEWS, slice_
from .legacy import route

MASK = '●●●'
RULE_KEYS = ('phone', 'account', 'url')
WORD_MAX, WORDS_MAX, HIDDEN_MAX = 20, 300, 500
# 🤬 [추천 목록 넣기] — 흔한 욕설 몇 개만(대표님이 보고 빼거나 더한다). 기본 목록은 비워 둔다.
RECOMMENDED = ('시발', '씨발', '씨바', 'ㅅㅂ', 'ㅆㅂ', '병신', '븅신', 'ㅂㅅ', '좆', '존나', '개새끼', '지랄',
               '미친놈', '미친년', '니애미', '느금마', '썅')

slice_('mask', False, lambda: {'words': [], 'rules': {k: True for k in RULE_KEYS}, 'hidden': [], 'ver': 0})

# ── 거르기 규칙 ─────────────────────────────────────────────
_SEP = r'[\s.\-]*'
PHONE_RE = re.compile(r'(?<![0-9])(?:\+\s*82' + _SEP + r'0?|0)' + _SEP + r'(?:1[016789]|2|[3-6][1-5]|70)'
                      r'(?:' + _SEP + r'[0-9]){7,8}(?![0-9])')
NUMRUN_RE = re.compile(r'(?<![0-9])[0-9](?:[ .\-]?[0-9])+(?![0-9])')
_TLD = ('com|net|org|kr|io|me|tv|gg|ly|xyz|shop|site|link|app|info|biz|co|cc|to|be|ai|live|club|online|store|page|so|'
        'us|jp|cn|fun|top|vip|pro|world|dev|kakao|naver|youtube|youtu')
URL_RE = re.compile(
    r'(?:https?://|www\.)[^\s]+'
    r'|[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}'
    r'|(?<![a-z0-9@.\-])(?:[a-z0-9](?:[a-z0-9\-]*[a-z0-9])?\.)+(?:' + _TLD + r')(?![a-z0-9])(?:[/?#][^\s]*)?'
    r'|[a-z0-9\-]+\s*닷\s*(?:컴|넷|케이알|kr)', re.IGNORECASE)
_GAP = r'[^\sㄱ-ㅎㅏ-ㅣ가-힣a-zA-Z]{0,2}'        # 글자 사이에 끼운 숫자 · 기호(띄어쓰기는 안 됨)


def _account_spans(text):
    out = []
    for m in NUMRUN_RE.finditer(text):
        s = m.group(0)
        digits = sum(ch.isdigit() for ch in s)
        if not 10 <= digits <= 16:
            continue
        if ' ' in s and max(len(g) for g in re.split(r'[ .\-]', s)) < 5:
            continue                                # '2025-10-17 21' 같은 날짜 · 시각
        out.append((m.start(), m.end()))
    return out


def clean_word(w):
    w = ' '.join(str(w or '').split())
    return w[:WORD_MAX]


@functools.lru_cache(maxsize=64)
def _words_re(words):
    pats = []
    for w in sorted(set(words), key=len, reverse=True):
        chars = [re.escape(ch) for ch in w if not ch.isspace()]
        if chars:
            pats.append(_GAP.join(chars))
    return re.compile('|'.join(pats), re.IGNORECASE) if pats else None


@functools.lru_cache(maxsize=4096)
def _check(text, words, rules):
    spans = []                                      # (시작, 끝, 종류)
    if 'url' in rules:
        spans += [(m.start(), m.end(), 'url') for m in URL_RE.finditer(text)]
    phones = [(m.start(), m.end()) for m in PHONE_RE.finditer(text)] if 'phone' in rules else []
    spans += [(a, b, 'phone') for a, b in phones]
    if 'account' in rules:                          # 전화번호로 잡힌 숫자는 계좌로 또 세지 않는다
        spans += [(a, b, 'account') for a, b in _account_spans(text) if not any(a < pb and pa < b for pa, pb in phones)]
    rx = _words_re(words) if words else None
    if rx is not None:
        spans += [(m.start(), m.end(), 'word') for m in rx.finditer(text) if m.end() > m.start()]
    if not spans:
        return text, ()
    spans.sort()
    merged = []
    for a, b, k in spans:
        if merged and a < merged[-1][1]:            # 겹치면 하나로(먼저 시작한 것 종류)
            merged[-1][1] = max(merged[-1][1], b)
            merged[-1][2].add(k)
        else:
            merged.append([a, b, {k}])
    out, last, hits = [], 0, []
    for a, b, ks in merged:
        out.append(text[last:a])
        out.append(MASK)
        last = b
        for k in ('phone', 'account', 'url', 'word'):
            if k in ks and k not in hits:
                hits.append(k)
    out.append(text[last:])
    return ''.join(out), tuple(hits)


def _cfg(m):
    m = m or {}
    words = tuple(w for w in (m.get('words') or []) if isinstance(w, str) and w.strip())
    r = m.get('rules') or {}
    rules = tuple(k for k in RULE_KEYS if r.get(k, True) is not False)
    return words, rules


def check(text, m=None):
    """(가린 글, 걸린 종류들) — m = mask 조각(없으면 기본 규칙 · 빈 금칙어)."""
    text = '' if text is None else str(text)
    if not text:
        return text, ()
    words, rules = _cfg(m)
    return _check(text, words, rules)


def masked(text, m=None):
    return check(text, m)[0]


HIT_LABEL = {'phone': '전화번호', 'account': '계좌번호', 'url': '인터넷 주소', 'word': '금칙어'}


def note(text, m=None):
    """조종실에 붙일 표시 — 걸렸으면 {'hits': [...], 'text': 가린 글}, 아니면 None."""
    t, hits = check(text, m)
    return {'hits': list(hits), 'text': t} if hits else None


# ── 보여 주는 사본 ────────────────────────────────────────────
def _hidden(m):
    return set((m or {}).get('hidden') or [])


def _pop_view(v, m):
    d = v.get('donation') if isinstance(v, dict) else None
    if not isinstance(d, dict):
        return None
    hid = _hidden(m)
    d2 = {k: x for k, x in d.items() if k not in ('src',)}
    if d.get('id') in hid or (d.get('src') and d.get('src') in hid):
        d2['message'] = ''
    elif d.get('message'):
        d2['message'] = masked(d.get('message'), m)
    return dict(v, donation=d2)


def _queue_item(it, m, hid):
    it2 = {k: x for k, x in it.items() if k != 'don_ids'}
    ids = it.get('don_ids') if isinstance(it.get('don_ids'), list) else []
    whole = it.get('id') in hid
    first_hidden = whole or (ids and ids[0] in hid)
    it2['message'] = '' if first_hidden else masked(it.get('message') or '', m)
    msgs = it.get('msgs')
    if isinstance(msgs, list):
        out = []
        for i, x in enumerate(msgs):
            if whole or (i < len(ids) and ids[i] in hid):
                out.append('')
            else:
                out.append(masked(x or '', m))
        it2['msgs'] = out
    return it2


def _queue_view(v, m):
    if not isinstance(v, dict) or not isinstance(v.get('items'), list):
        return None
    hid = _hidden(m)
    return dict(v, items=[_queue_item(it, m, hid) if isinstance(it, dict) else it for it in v['items']])


def _deep_view(v, m, hid):
    """screen(끝 화면 · 엔딩 크레딧)처럼 모양이 바뀔 수 있는 조각 — message · msgs 칸을 끝까지 찾아 거른다."""
    if isinstance(v, list):
        return [_deep_view(x, m, hid) for x in v]
    if not isinstance(v, dict):
        return v
    out = {}
    gone = v.get('id') in hid or v.get('don_id') in hid
    for k, x in v.items():
        if k in ('message', 'msg') and isinstance(x, str):
            out[k] = '' if gone else masked(x, m)
        elif k == 'msgs' and isinstance(x, list) and all(isinstance(y, str) for y in x):
            out[k] = ['' if gone else masked(y, m) for y in x]
        else:
            out[k] = _deep_view(x, m, hid)
    return out


def _cast_view(v, m):
    fx = v.get('fx') if isinstance(v, dict) else None
    if not isinstance(fx, dict) or not fx.get('message'):
        return None
    return dict(v, fx=dict(fx, message=masked(fx['message'], m)))


def _blank(name, v):
    """거르다 넘어졌을 때(있어선 안 되지만) — 방송판에는 메시지 칸을 다 비운 사본을 준다(원문을 흘리지 않게)."""
    if name == 'popup' and isinstance(v, dict) and isinstance(v.get('donation'), dict):
        return dict(v, donation=dict(v['donation'], message=''))
    if name == 'queue' and isinstance(v, dict) and isinstance(v.get('items'), list):
        return dict(v, items=[dict(it, message='', msgs=['' for _ in (it.get('msgs') or [])]) if isinstance(it, dict) else it
                              for it in v['items']])
    if name == 'cast' and isinstance(v, dict) and isinstance(v.get('fx'), dict):
        return dict(v, fx=dict(v['fx'], message=''))
    return None


def _pending_view(v, m):
    """조종실 대기함 — 원문은 그대로 두고 걸린 카드에만 mask{hits, text}(⚠ · 방송에 나가는 글)를 붙인다."""
    if not isinstance(v, list):
        return None
    out, any_ = [], False
    for it in v:
        n = note(it.get('message'), m) if isinstance(it, dict) and it.get('message') else None
        if n:
            out.append(dict(it, mask=n))
            any_ = True
        else:
            out.append(it)
    return out if any_ else None


ON_AIR_VIEWS = {'popup': _pop_view, 'queue': _queue_view, 'cast': _cast_view}


def view(name, value, slices, on_air):
    m = slices.get('mask') if isinstance(slices, dict) else None
    if not on_air:
        return _pending_view(value, m) if name == 'pending' else None
    if name == 'screen':
        try:
            return _deep_view(value, m, _hidden(m))
        except Exception:
            return None
    fn = ON_AIR_VIEWS.get(name)
    if fn is None:
        return None
    try:
        return fn(value, m)
    except Exception as e:
        print('⚠️ [금칙어 거르기 실패 — 메시지를 비워 내보냄] %s: %s' % (name, type(e).__name__), flush=True)
        return _blank(name, value)


VIEWS.append(view)
DEPENDS['mask'] = ('popup', 'queue', 'cast', 'screen', 'pending')


# ── 명령 ────────────────────────────────────────────────────
def _bump(m):
    m['ver'] = int(m.get('ver') or 0) + 1


def _split_words(raw):
    if isinstance(raw, (list, tuple)):
        items = raw
    else:
        items = re.split(r'[,\n]', str(raw or ''))
    return [w for w in (clean_word(x) for x in items) if w]


@command('mask.word.add')
def word_add(ctx, data):
    """금칙어 더하기 {word}(쉼표 · 줄바꿈으로 여러 개) 또는 {words: [...]}."""
    new = _split_words(data.get('words') if data.get('words') is not None else data.get('word'))
    if not new:
        raise CommandError('더할 낱말을 적어 주세요')
    m = ctx.edit('mask')
    have = list(m.get('words') or [])
    low = {w.casefold() for w in have}
    added = []
    for w in new:
        if w.casefold() not in low:
            have.append(w)
            low.add(w.casefold())
            added.append(w)
    if len(have) > WORDS_MAX:
        raise CommandError('금칙어는 %d개까지예요' % WORDS_MAX)
    m['words'] = have
    if added:
        _bump(m)
    ctx.notes.update({'added': added, 'count': len(have)})


@command('mask.word.remove')
def word_remove(ctx, data):
    w = clean_word(data.get('word'))
    m = ctx.edit('mask')
    before = list(m.get('words') or [])
    m['words'] = [x for x in before if x.casefold() != w.casefold()]
    if len(m['words']) == len(before):
        raise CommandError('목록에 없는 낱말이에요', 404)
    _bump(m)
    ctx.notes['count'] = len(m['words'])


@command('mask.word.recommend')
def word_recommend(ctx, data):
    """[추천 목록 넣기] — 흔한 욕설 몇 개를 한 번에(이미 있는 것은 건너뛴다)."""
    word_add(ctx, {'words': list(RECOMMENDED)})


@command('mask.word.clear')
def word_clear(ctx, data):
    m = ctx.edit('mask')
    n = len(m.get('words') or [])
    m['words'] = []
    if n:
        _bump(m)
    ctx.notes['removed'] = n


@command('mask.rule')
def rule(ctx, data):
    """{key: phone|account|url, on} — 규칙 하나 켜고 끄기."""
    k = str(data.get('key') or '')
    if k not in RULE_KEYS:
        raise CommandError('모르는 규칙이에요: %s' % k)
    m = ctx.edit('mask')
    r = dict(m.get('rules') or {})
    r[k] = bool(data.get('on', True))
    m['rules'] = r
    _bump(m)


@command('mask.hide')
def hide(ctx, data):
    """[가리기]/[보이기] — {id, on}(on 기본 True). 그 후원의 메시지를 방송판에서 통째로 숨긴다(장부 · 대기함은 그대로)."""
    did = str(data.get('id') or '').strip()
    if not did or len(did) > 80:
        raise CommandError('어느 후원인지 모르겠어요')
    on = bool(data.get('on', True))
    m = ctx.edit('mask')
    hid = [x for x in (m.get('hidden') or []) if x != did]
    if on:
        hid.append(did)
    m['hidden'] = hid[-HIDDEN_MAX:]
    _bump(m)
    ctx.notes.update({'id': did, 'hidden': on})


@route('/api/mask/preview')
async def preview(req, bus, authed, answer):
    """설정 화면 '시험해 보기' — 글을 넣으면 방송에 나갈 모습(로그인 · 장부에 안 적는다)."""
    if not authed(req):
        return JSONResponse({'ok': False, 'error': '로그인이 필요합니다'}, status_code=401)
    try:
        body = await req.json()
    except Exception:
        body = {}
    text = str((body or {}).get('text') or '')[:300]
    t, hits = check(text, bus.state.get('mask'))
    return {'ok': True, 'text': t, 'hits': list(hits)}
