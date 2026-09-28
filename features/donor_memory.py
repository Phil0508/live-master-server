# -*- coding: utf-8 -*-
"""🧠 후원자 기억 — 후원자가 예전에 누구에게 배정됐는지, 별명 토막으로 찾아본다.

server.py 에서 그대로 옮겨 왔다(본문은 안 바꿨다). 공용 도구는 server 에서 빌려 온다.
"""
import re
import time
from server import (
    db_query, get_db_connection,
)


def _norm_donor(name):
    """후원자 표기 정규화. 같은 사람이 '홍길동' / '홍길동님' / ' 홍길동 ' 으로 갈라져
       집계가 쪼개지는 것을 막는다."""
    n = ' '.join(str(name or '').split())
    if n.endswith('님'):
        n = n[:-1].strip()
    return n or '익명'


# ══ 🧠 후원자 기억 ══

# 메시지에서 '이름 후보'가 될 만한 토막을 뽑는다.
# ⚠️ 너무 많이 뽑으면 아무 말이나 별명이 되어 오답을 만든다. 짧고 흔한 말은 버린다.
_ALIAS_STOP = {'화이팅', '파이팅', '감사', '감사합니다', '고생', '고생하셨어요', '수고',
               '수고하셨습니다', '응원', '응원합니다', '축하', '사랑해요', '가즈아', '대박',
               '오늘', '방송', '재밌어요', '잘보고있어요', '님', '언니', '누나', '형', '오빠'}


def alias_tokens(message):
    """메시지에서 별명 후보를 뽑는다."""
    txt = str(message or '')
    out = []
    for w in re.split(r'[\s,./!?~\-()\[\]"\'·:;]+', txt):
        w = w.strip().strip('님아야이가는은를을에게한테')
        if not (2 <= len(w) <= 8):
            continue
        if w in _ALIAS_STOP:
            continue
        if w.isdigit():          # 순수 숫자는 금액·시각일 때가 많다
            continue
        out.append(w)
    return out[:6]


def remember_assignment(donor, player, amount, message):
    """후원 한 건이 누구에게 갔는지 기억한다. 실패해도 배정은 이미 끝났으니 조용히 넘어간다."""
    d = _norm_donor(donor)
    p = str(player or '').strip()
    if not p or d == '익명':      # 익명은 사람을 특정할 수 없어 기억해도 쓸모가 없다
        return
    try:
        now = time.strftime('%Y-%m-%d %H:%M:%S')
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query("INSERT INTO donor_memory (timestamp, donor, player, amount, message)"
                                 " VALUES (?, ?, ?, ?, ?)"),
                        (now, d, p, int(amount or 0), str(message or '')[:300]))
            for tok in alias_tokens(message):
                cur.execute(db_query("SELECT id, hits FROM alias_memory WHERE token = ? AND player = ?"),
                            (tok, p))
                row = cur.fetchone()
                if row:
                    cur.execute(db_query("UPDATE alias_memory SET hits = hits + 1, updated = ? WHERE id = ?"),
                                (now, row[0]))
                else:
                    cur.execute(db_query("INSERT INTO alias_memory (token, player, hits, updated)"
                                         " VALUES (?, ?, 1, ?)"), (tok, p, now))
    except Exception as e:
        print(f"⚠️ [후원자 기억 실패] {e}")


def donor_history(donor, limit=5):
    """이 후원자가 최근 누구에게 갔는지. [(플레이어, 횟수)] 를 많은 순으로."""
    d = _norm_donor(donor)
    if not d or d == '익명':
        return []
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(db_query("SELECT player, COUNT(*) c FROM donor_memory WHERE donor = ?"
                                 " GROUP BY player ORDER BY c DESC LIMIT ?"), (d, limit))
            return [(r[0], int(r[1])) for r in cur.fetchall()]
    except Exception:
        return []


def alias_lookup(message, players):
    """메시지 안의 말이 특정 플레이어로만 이어져 왔는지 본다.
       반환: (플레이어, 적중수, 그 말) 또는 None."""
    toks = alias_tokens(message)
    if not toks:
        return None
    names = {str(p).strip() for p in (players or []) if str(p or '').strip()}
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            ph = ', '.join(['?'] * len(toks))
            cur.execute(db_query(f"SELECT token, player, hits FROM alias_memory WHERE token IN ({ph})"),
                        tuple(toks))
            rows = [r for r in cur.fetchall() if r[1] in names]
    except Exception:
        return None
    if not rows:
        return None
    # 한 말이 여러 사람에게 이어져 왔으면 믿을 수 없다 — 아예 쓰지 않는다.
    by_tok = {}
    for tok, player, hits in rows:
        by_tok.setdefault(tok, []).append((player, int(hits)))
    best = None
    for tok, lst in by_tok.items():
        if len(lst) != 1:
            continue          # 그 말이 두 사람 이상을 가리킨 적이 있다 → 버린다
        player, hits = lst[0]
        if not best or hits > best[1]:
            best = (player, hits, tok)
    return best
