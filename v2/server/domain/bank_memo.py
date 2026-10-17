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
⚠️ split_memo 의 숫자 · 낱말 목록 · 순서는 옛 것과 똑같다 — 고칠 때는 옛 tests/bank_memo_test.py 의 경우를 같이 본다.

📚 10-17 새 순서 smart_split — split_memo **앞에** 셋을 더 둔다(운영 실측 65건: 맞은 닉네임 40% → 86%).
   가장 흔한 실수는 붙여 쓴 메모('하루밍밍화이팅')를 통째로 닉네임에 넣는 name_only 였다.
  A) learned      배운 짝 — 이 입금자명으로 대표님이 전에 실제로 보낸 닉네임(bank_learn.py). 메모에 없어도(별명) 된다.
  B) known_name   지난 기록 — 예전 후원 이름 중 메모 **어디든** 들어 있는 가장 긴 것(2자 이상, 선수 · 운영비 이름 빼고).
                  두 글자 이름은 앞뒤가 떨어져 있을 때만('영원히사랑해' 의 '영원' 은 아니다 — 옛 경계 규칙).
  C) player_strip 선수 이름 떼기 — 메모에서 지금 선수 이름(긴 것부터 · '아' '야' '님' 같은 꼬리 같이)을 지우고 남은 첫 덩어리.
                  첫 덩어리가 응원 말이면 마지막 덩어리('밍밍 화이팅 별사탕' → 별사탕), 덩어리 안 응원 말 앞에서 자른다('하루화이팅' → 하루).
  셋 다 안 되면 옛 split_memo 그대로(known · player_cut · first · message · name_only).
  A · B · C 의 할 말 = 메모에서 닉네임 · 선수 이름(· 입금자 실명)을 뺀 나머지, 선수 이름은 target('누구 몫' 추천)으로 간다.
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


# ── 📚 10-17 새 순서(A 배운 짝 → B 지난 기록 → C 선수 이름 떼기 → 옛 split_memo) ─────────────
_SEPCH = r'[\s,./!?~\-()\[\]"\'·:;♡♥|]'
# 선수 이름 뒤에 붙어 같이 지우는 꼬리 — 늘(부르는 말 · 존칭) / 뒤가 떨어져 있을 때만(조사)
_TAIL_ALWAYS = ('님께', '에게', '한테', '이랑', '님', '아', '야', '랑', '께', '씨')
_TAIL_EDGE = ('이', '가', '도', '은', '는', '을', '를', '의', '만')


def _player_re(pl):
    if not pl:
        return None
    names = '|'.join(re.escape(p) for p in sorted(pl, key=len, reverse=True))
    always = '|'.join(re.escape(t) for t in _TAIL_ALWAYS)
    edge = '|'.join(re.escape(t) for t in _TAIL_EDGE)
    return re.compile('(?:%s)(?:(?:%s)|(?:%s)(?=%s|$))?' % (names, always, edge, _SEPCH))


def _tidy(s):
    """지우고 남은 글 — 겹친 띄어쓰기 · 앞뒤 문장부호 정리."""
    s = ' '.join(str(s or '').split())
    s = re.sub(r'\s*([,/·|])\s*(?=[,/·|]|$)', '', s)          # 지운 자리에 남은 빈 쉼표 · 빗금
    return _strip_edges(s).strip()


def _first_player(text, pl):
    """메모에 나온 선수 중 가장 앞에 있는 것(같은 자리면 긴 이름)."""
    best = None
    for p in pl:
        i = text.find(p)
        if i >= 0 and (best is None or i < best[0] or (i == best[0] and len(p) > len(best[1]))):
            best = (i, p)
    return best[1] if best else None


def _cut(text, start, end):
    return text[:start] + ' ' + text[end:]


def _drop(text, word):
    """text 에서 word 를 (처음 한 번) 지운다. 없으면 그대로."""
    if not word:
        return text
    i = text.find(word)
    if i < 0:
        flat_w = ''.join(word.split())
        i = text.find(flat_w) if flat_w else -1
        if i < 0:
            return text
        word = flat_w
    end = i + len(word)
    if text[end:end + 1] == '님':
        end += 1
    return _cut(text, i, end)


def _message(text, name, pl, holder):
    """할 말 = 메모 − 닉네임 − 선수 이름 − 입금자 실명."""
    t = _drop(text, name)
    if holder and len(''.join(holder.split())) >= 2:
        t = _drop(t, holder)
    rx = _player_re(pl)
    if rx:
        t = rx.sub(' ', t)
    return _tidy(t)


def _known_anywhere(text, pl, dn):
    """B — 메모 어디든 들어 있는 가장 긴 예전 이름. 두 글자 이름은 앞뒤 경계가 있어야."""
    for d in dn:
        start = 0
        while True:
            i = text.find(d, start)
            if i < 0:
                break
            start = i + 1
            end = i + len(d)
            name = d
            if text[end:end + 1] == '님':
                name, end = d + '님', end + 1
            if len(d) >= 3:
                return name
            if _boundary_before(text[:i], pl) and _boundary_after(text[end:], pl):
                return name
    return None


def _chunk_name(chunk):
    """덩어리 하나 → 닉네임(응원 말이면 ''). 덩어리 가운데 응원 말이 있으면 그 앞까지('하루화이팅' → '하루')."""
    c = _strip_edges(chunk)
    if len(c) < 2 or _cheer(c):
        return ''
    at = [c.find(w) for w in _CHEER if len(w) >= 2 and c.find(w) > 0]
    if at:
        c = _strip_edges(c[:min(at)])
    return c if len(c) >= 2 and not _cheer(c) else ''


def _strip_players_name(text, pl):
    """C — 선수 이름을 지우고 남은 첫 덩어리(응원 말이면 마지막 덩어리)."""
    rx = _player_re(pl)
    if not rx or not rx.search(text):
        return None
    rest = rx.sub(' ', text)
    chunks = [c for c in re.split(_SEPCH + '+', rest) if c]
    if not chunks:
        return None
    nm = _chunk_name(chunks[0])
    if not nm and len(chunks) >= 2:
        nm = _chunk_name(chunks[-1])
    return nm or None


def smart_split(memo, players=(), donors=(), learned='', holder='', exclude=()):
    """메모 한 줄 → {'name', 'message', 'how', 'sure', 'target'} — A → B → C → 옛 split_memo.

       learned  배운 짝(이 입금자명으로 전에 보낸 닉네임, 없으면 '')
       holder   입금자 실명 — 할 말에서 뺀다(방송판에 실명이 나가지 않게). 메모가 실명뿐이면(메모 없이 보냄) no_memo.
       exclude  닉네임 후보에서 뺄 이름(번외 판 선수 · 운영비 이름 등 — 지금 판 선수는 늘 빠진다)
       target   메모에 나온 선수(가장 앞) — '누구 몫' 추천. 옛 길(split_memo)로 떨어지면 None(AI · 규칙 예상이 붙인다)"""
    text = clean(memo)
    hold = clean(holder)
    pl = _players(players)
    no_memo = bool(hold) and (not text or text.replace(' ', '') == hold.replace(' ', ''))
    tgt = _first_player(text, pl) if text else None
    lv = clean(learned)
    if lv:                                              # A) 배운 짝
        msg = '' if no_memo else _message(text, lv, pl, hold)
        return {'name': lv, 'message': msg, 'how': 'learned', 'sure': True, 'target': tgt}
    if no_memo:
        return {'name': hold, 'message': '', 'how': 'no_memo', 'sure': False, 'target': None}
    if not text:
        return {'name': '', 'message': '', 'how': 'empty', 'sure': False, 'target': None}
    skip = set(pl) | {_norm(x) for x in (exclude or ()) if x}
    dn = sorted({_norm(d) for d in (donors or ())
                 if len(_norm(d)) >= 2 and _norm(d) != '익명' and _norm(d) not in skip and not _cheer(_norm(d))},
                key=len, reverse=True)
    nm = _known_anywhere(text, pl, dn)                  # B) 지난 기록
    if nm:
        return {'name': nm, 'message': _message(text, nm, pl, hold), 'how': 'known_name', 'sure': True, 'target': tgt}
    nm = _strip_players_name(text, pl)                  # C) 선수 이름 떼기
    if nm:
        return {'name': nm, 'message': _message(text, nm, pl, hold), 'how': 'player_strip', 'sure': False, 'target': tgt}
    sp = split_memo(text, pl, dn)                       # 옛 규칙
    sp['target'] = None
    return sp
