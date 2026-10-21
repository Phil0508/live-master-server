# -*- coding: utf-8 -*-
"""🏦📚 계좌 입금 '배운 짝' — 입금자명(holder) → 대표님이 실제로 송출한 닉네임 (10-17).

왜: 계좌 후원자는 대개 같은 통장에서 다시 보낸다. 대표님이 한 번 [채우기] → 고쳐서 [송출] 한 이름이
    그 사람의 진짜 닉네임이다(메모에 닉네임이 없어도 · 별명을 써도). 다음 카드에 같은 입금자면 그 이름을 먼저 추천한다.

표 bank_learn (같은 SQLite 장부 · 서버만 읽는다 — 조각 · 명령 기록 · 답 · 화면 어디에도 안 간다)
  hk    입금자명 지문 — sha256('lm2-bank-learn|' + 띄어쓰기 뺀 입금자명) 앞 32자. ⚠️ 실명 글자는 표에 없다.
        (그래서 장부 백업에 그대로 들어가도 실명이 안 남고, 배운 것이 백업에서 같이 살아난다)
  name  실제로 보낸 닉네임(공개 이름 — 방송판에 이미 나간 글자)
  card  배운 카드 번호(b + 12자) · 미리 배우기 도구는 'old:<번호>' / 'v2:<번호>'
  at    배운 때 — 같은 입금자면 **가장 최근 것이 이긴다**
  n     몇 번 배웠나(참고)
규칙
  · 한 카드에서는 **첫 이름**만 배운다 — 한 입금을 여러 번(×N · 나눠 보내기) 보내도 처음 보낸 이름.
  · 익명 · 수동송출 · 빈 이름은 안 배운다.
  · 서버는 이 표를 메모리에 쥐지 않는다(매번 읽는다) → 켜진 서버 옆에서 미리 배우기 도구가 써도 덮어쓰이지 않는다.
⚠️ 이 파일은 print 하지 않는다 — 실명 · 지문이 기록에 남지 않게. 부르는 쪽도 건수만 적는다.
"""
import hashlib
import re
import time

SCHEMA = ("CREATE TABLE IF NOT EXISTS bank_learn ("
          " hk TEXT PRIMARY KEY, name TEXT NOT NULL, card TEXT NOT NULL DEFAULT '',"
          " at REAL NOT NULL, n INTEGER NOT NULL DEFAULT 1)")
SKIP_NAMES = ('익명', '수동송출')
NAME_MAX = 40
_TX_RE = re.compile(r'^manual_bank_(.+?)(?:_\d{1,3})?$')


def ensure(db):
    """표가 없으면 만든다(한 줄 — 열린 BEGIN 을 몰래 끝내지 않는다)."""
    db.execute(SCHEMA)


# 간편송금 회사 — 토스 · 카카오페이 등으로 보내면 예금주 칸에 사람이 아니라 회사 이름이 찍힌다.
# 이걸로 짝을 배우면 그 회사로 오는 모든 입금이 한 닉네임으로 추천된다(10-21 토스 입금마다 '앞뒤' 로 채워지던 것).
_PASS_THROUGH = re.compile(r'비바리퍼블리카|카카오페이|네이버파이낸셜|엔에이치엔페이코|페이코|쿠팡페이|^(?:\(주\)|（주）|㈜)?토스$')


def is_pass_through(holder):
    """예금주 칸이 사람 아닌 간편송금 회사인가."""
    return bool(_PASS_THROUGH.search(''.join(str(holder or '').split())))


def holder_key(holder):
    """입금자명 → 지문. 띄어쓰기는 빼고 본다('김 진짜' = '김진짜'). 비었거나 간편송금 회사면 ''(배우지도 찾지도 않는다)."""
    h = ''.join(str(holder or '').split())
    if not h or is_pass_through(h):
        return ''
    return hashlib.sha256(('lm2-bank-learn|' + h).encode('utf-8')).hexdigest()[:32]


def clean_name(name):
    n = ' '.join(str(name or '').split())[:NAME_MAX]
    return '' if n in SKIP_NAMES else n


def card_of_tx(tx):
    """'manual_bank_b0123456789ab' · 'manual_bank_b0123456789ab_2'(×N) → 카드 번호. 계좌 송출이 아니면 ''."""
    m = _TX_RE.match(str(tx or '').strip())
    return m.group(1) if m else ''


def lookup(db, holder):
    """배운 닉네임(없으면 '')."""
    hk = holder_key(holder)
    if not hk:
        return ''
    try:
        r = db.execute('SELECT name FROM bank_learn WHERE hk = ?', (hk,)).fetchone()
    except Exception:          # 표가 아직 없다(처음) — 모른다
        return ''
    return str(r[0]) if r else ''


def learn(db, holder, name, card='', at=None):
    """입금자명 → 닉네임 한 짝을 적는다. 돌려주는 값: 적었나(True) · 안 적었나(False).
       같은 카드로 이미 배웠으면(첫 이름 규칙) · 더 최근에 배운 짝이 있으면 그대로 둔다."""
    hk, nm = holder_key(holder), clean_name(name)
    if not hk or not nm:
        return False
    at = time.time() if at is None else float(at)
    card = str(card or '')
    ensure(db)
    r = db.execute('SELECT name, card, at FROM bank_learn WHERE hk = ?', (hk,)).fetchone()
    if r:
        if card and str(r[1]) == card:
            return False                       # 이 카드에서는 첫 이름만
        if float(r[2]) > at:
            return False                       # 더 최근에 배운 것이 이긴다(미리 배우기가 옛 기록으로 덮지 않게)
        db.execute('UPDATE bank_learn SET name = ?, card = ?, at = ?, n = n + 1 WHERE hk = ?', (nm, card, at, hk))
        return True
    db.execute('INSERT INTO bank_learn (hk, name, card, at, n) VALUES (?, ?, ?, ?, 1)', (hk, nm, card, at))
    return True


def count(db):
    try:
        return int(db.execute('SELECT COUNT(*) FROM bank_learn').fetchone()[0])
    except Exception:
        return 0
