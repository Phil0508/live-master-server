# -*- coding: utf-8 -*-
"""🏦 계좌 입금 메모 나누기 — '영원 밍밍 화이팅' → 닉네임 '영원' · 메시지 '밍밍 화이팅' (옛 features/bank_memo.py 그대로 옮김, 10-17).

계좌 후원자는 통장 표시(메모) 한 줄에 닉네임과 할 말을 같이 적는다. 모양은 섞여 있다(대표님 10-13):
  '영원 밍밍 화이팅'(닉네임 먼저) · '밍밍 화이팅'(할 말만) · '영원밍밍화이팅'(붙여 씀) · '구름빵'(이름만) …
그래서 이 결과는 '추천' 이다. 후원 콘솔이 원래 메모를 같이 보여주고 대표님이 고쳐서 송출한다.

나누는 순서(확실한 것부터)
  ① 예전에 후원한 닉네임(후원자 기억)이 메모 앞이나 뒤에 있다 — 띄어 쓰든 붙여 쓰든 찾는다.
  ② 띄어 썼고 첫 낱말이 선수 이름도, 흔한 응원 말도 아니다 → 첫 낱말을 닉네임으로 본다(확실하지 않음).
  ②-2 붙여 쓴 한 낱말 가운데에 선수 이름이 있다('스트밍밍플러' = 스트 + 밍밍플러) → 앞은 닉네임(확실하지 않음).
       10-14 실제 입금: 은행이 통장 표시의 띄어쓰기를 없애고 보여준다.
  ③ 선수를 부르거나 응원 말로 시작한다('밍밍 화이팅' · '밍밍최고') → 할 말만, 닉네임은 모른다.
  ④ 선수와 상관없는 한 낱말('구름빵' · '홍길동') → 이름만. 메모 없이 보내 실명이 찍힌 것일 수도 있다.

⚠️ 이 파일은 서버 · 장부를 부르지 않는다(순수 함수). 검사가 서버 없이 부른다(v2/tests/test_bank.py MemoSplit).
⚠️ 숫자 · 낱말 목록 · 순서는 옛 것과 똑같다 — 고칠 때는 옛 tests/bank_memo_test.py 의 경우를 같이 본다.
"""
import re

from .ai_facts import name_forms

MEMO_MAX = 40            # 통장 표시는 짧다 — 이보다 길면 표 칸 여러 개가 붙은 것이니 자른다
_SEP = re.compile(r'\s*[\s/,·|]\s*')     # 닉네임과 할 말 사이 — 띄어쓰기 · 빗금 · 쉼표
_EDGE = re.compile(r'^[\s,./!?~\-()\[\]"\'·:;♡♥]*')
# 닉네임이 아니라 '할 말' 로 시작하는 흔한 말. 첫 낱말이 이것이면 닉네임으로 보지 않는다.
_CHEER = ('화이팅', '파이팅', '홧팅', '사랑', '응원', '감사', '축하', '최고', '고생', '수고',
          '힘내', '오늘', '항상', '언제나', '늘', '방송', '생일', '가즈아', '대박', '좋아')


def clean(s):
    """줄바꿈 · 겹친 띄어쓰기를 하나로, 길이는 MEMO_MAX 까지."""
    return ' '.join(str(s or '').split())[:MEMO_MAX]


def _norm(name):
    n = clean(name)
    if n.endswith('님'):
        n = n[:-1].strip()
    return n


def _players(players):
    out = []
    for p in players or ():
        n = clean(p.get('name') if isinstance(p, dict) else p)
        if len(n) >= 2:
            out.append(n)
    return out


def mentions_player(word, players):
    """낱말이 선수를 부르는가 — '밍밍' · '밍밍아' · '밍밍최고' · '예지랑이랑'."""
    w = clean(word)
    if not w:
        return False
    forms = name_forms(w)
    return any(p in forms or p in w for p in players)


def _cheer(word):
    w = clean(word)
    return any(w.startswith(c) for c in _CHEER)


def _boundary_after(rest, players):
    """닉네임 뒤에 남은 글이 '따로 떨어진 말' 인가 — 띄어 썼거나, 선수 이름 · 응원 말로 시작한다.
       ⚠️ 이게 없으면 '영원히사랑해' 가 알려진 닉네임 '영원' + '히사랑해' 로 잘린다."""
    if not rest:
        return True
    if _EDGE.match(rest).end():
        return True
    return any(rest.startswith(p) for p in players) or _cheer(rest)


def _boundary_before(front, players):
    if not front:
        return True
    if re.search(r'[\s,./!?~\-()\[\]"\'·:;♡♥]$', front):
        return True
    return mentions_player(front, players) or _cheer(front)


def _strip_edges(s):
    s = _EDGE.sub('', s)
    return re.sub(r'[\s,./!?~\-()\[\]"\'·:;]+$', '', s)


def _known_split(text, players, donors):
    """① 알려진 닉네임이 앞이나 뒤에 있는가. 긴 이름부터 본다('밍밍바라기' 가 '밍밍' 보다 먼저)."""
    # ⚠️ 후원자 기억은 '홍길동님 = 홍길동' 으로 님을 떼고 적힌다. 메모에 님이 붙어 있으면 적힌 그대로
    #    돌려준다 — '새손님' 이 '새손' 이 되면 남의 이름이다(자기 닉네임에 존칭을 붙여 보내는 사람은 드물다).
    for d in donors:
        if not text.startswith(d):
            continue
        rest, name = text[len(d):], d
        if rest.startswith('님'):
            rest, name = rest[1:], d + '님'
        if _boundary_after(rest, players):
            return name, _strip_edges(rest)
    for d in donors:
        if not text.endswith(d):
            continue
        front = text[:-len(d)]
        if _boundary_before(front, players):
            return d, _strip_edges(front)
    return None


def split_memo(memo, players=(), donors=()):
    """메모 한 줄 → {'name', 'message', 'how', 'sure'}.

       how  — 'known'(예전 닉네임) · 'first'(첫 낱말) · 'message'(할 말만) · 'name_only'(이름만) · 'empty'
       sure — 닉네임을 믿어도 되는가(예전에 본 이름일 때만 True)"""
    text = clean(memo)
    if not text:
        return {'name': '', 'message': '', 'how': 'empty', 'sure': False}
    pl = _players(players)
    plset = set(pl)
    dn = sorted({_norm(d) for d in (donors or ())
                 if len(_norm(d)) >= 2 and _norm(d) != '익명' and _norm(d) not in plset},
                key=len, reverse=True)

    hit = _known_split(text, pl, dn)
    if hit:
        return {'name': hit[0], 'message': hit[1], 'how': 'known', 'sure': True}

    # ⚠️ 닉네임은 적힌 그대로 둔다 — '새손님' 의 '님' 을 떼면 남의 이름이 된다(뗀 모양은 기억과 맞대 볼 때만 쓴다)
    # 띄어쓰기뿐 아니라 '영원/밍밍화이팅' · '영원,밍밍' 처럼 빗금 · 쉼표로 나눠 적기도 한다
    cut = _SEP.search(text)
    first = text[:cut.start()] if cut else text
    if not cut:
        at = [first.find(p) for p in pl if p in first]
        if at and min(at) > 0:
            front = _strip_edges(first[:min(at)])
            if front and not _cheer(front) and not any(c in front for c in _CHEER if len(c) >= 2):
                return {'name': front, 'message': first[min(at):], 'how': 'player_cut', 'sure': False}
    if mentions_player(first, pl) or _cheer(first):
        return {'name': '', 'message': text, 'how': 'message', 'sure': False}
    if cut:
        return {'name': first, 'message': text[cut.end():], 'how': 'first', 'sure': False}
    # 한 낱말 — 응원 말이 가운데 섞여 있으면('영원히사랑해') 이름이 아니라 할 말이다
    if any(c in first for c in _CHEER if len(c) >= 2):
        return {'name': '', 'message': text, 'how': 'message', 'sure': False}
    return {'name': first, 'message': '', 'how': 'name_only', 'sure': False}


def ai_split_ok(memo, name, message):
    """AI 가 나눈 결과를 믿어도 되는가 — 지어낸 글자가 없어야 한다.
       닉네임은 메모의 맨 앞이나 맨 뒤 토막이고, 닉네임 + 메시지 = 메모(띄어쓰기 빼고)."""
    flat = lambda s: re.sub(r'[\s/,·|]+', '', str(s or ''))
    m, n, g = flat(memo), flat(name), flat(message)
    if not m:
        return False
    if not n:
        return g == m
    if m.startswith(n):
        return g == m[len(n):].lstrip('님')
    if m.endswith(n):
        return g == m[:-len(n)]
    return False
