# -*- coding: utf-8 -*-
"""📚 계좌 입금 '배운 짝' 미리 배우기 — 지난 계좌 송출에서 입금자명 → 닉네임 짝을 v2 장부(bank_learn)에 넣는다 (10-17).

왜: 계좌 카드 추천은 '이 입금자가 전에 대표님이 보낸 닉네임' 을 가장 먼저 믿는다(domain/bank_learn.py).
    v2 는 오늘부터 송출할 때마다 배우지만, 그 전 기록에도 짝이 많다 — 운영 서버에서 이것을 **한 번** 돌려 미리 배운다.

읽는 것(**읽기만**)
  카드(입금자명이 있는 곳)
    · 옛 bank_inbox.json(저장소 루트) — items 의 id · ref · holder
    · v2 장부의 bank_inbox 표 — id · ref · holder (오늘 v2 로 받은 카드. --no-v2 로 뺀다)
  송출(실제 보낸 이름) — tx_id 가 'manual_bank_<카드 id 또는 ref>[_N]'
    · 옛 장부(DATABASE_URL 의 Postgres, 또는 --sqlite) — donation_archive · donation_history 의 tx_id · name · timestamp
    · v2 장부의 donations 표 — tx_id · name · at
  짝 맞추기: tx_id 안의 번호 → 카드 id, 아니면 ref(source:ref 또는 ref) → 그 카드의 holder.
            한 카드는 **첫 이름**(가장 이른 줄 — ×N · 나눠 보내기), 같은 입금자는 **가장 최근 카드**의 이름.
쓰는 것: v2 장부 bank_learn 표만(입금자명은 지문 · bank_learn.holder_key). 이미 더 최근에 배운 짝(방송 중 송출)은 덮지 않는다.

쓰는 법(운영 서버 저장소 폴더에서)
  DATABASE_URL=... python -m v2.tools.import_bank_learning                 # 세어 보기만(아무것도 안 바꾼다)
  DATABASE_URL=... python -m v2.tools.import_bank_learning --write         # 진짜로 넣는다
  옵션: --inbox <옛 bank_inbox.json> · --v2-db <v2 장부> · --sqlite <옛 SQLite 장부> · --db-tz utc|kst(옛 장부 시각, 기본 utc) · --no-v2

⚠️ 실명 · 닉네임은 화면에 찍지 않는다 — 건수만.
⚠️ v2 서버가 켜져 있어도 된다(import_old_db 와 다르다). 까닭:
   · bank_learn 은 조각(메모리에 쥐고 있다가 덮어쓰는 것)이 아니라 따로 된 표이고, 서버는 입금이 올 때마다 이 표를 새로 읽는다.
   · 쓰기는 BEGIN IMMEDIATE 한 번(수백 줄 · 1초 안) — 서버는 잠금을 5초까지 기다린다(store.BUSY_TIMEOUT_MS). 명령 기록 · 조각은 건드리지 않는다.
   · 서버가 방송 중에 배운 짝(더 최근)은 이 도구가 덮지 않는다(bank_learn.learn 의 '가장 최근 것이 이긴다').
"""
import argparse
import json
import os
import sqlite3
import sys

from v2.server.domain import bank_learn as bl
from v2.tools.import_old_db import Old, to_epoch

HERE = os.path.dirname(os.path.abspath(__file__))
V2 = os.path.dirname(HERE)
REPO = os.path.dirname(V2)
OLD_TABLES = ('donation_archive', 'donation_history')


# ── 읽기 ──────────────────────────────────────────────
def read_inbox(path):
    """옛 bank_inbox.json → [{id, ref, holder}] (holder 있는 것만). 파일이 없거나 깨졌으면 []."""
    try:
        with open(path, encoding='utf-8') as f:
            box = json.load(f)
    except Exception:
        return []
    items = box.get('items') if isinstance(box, dict) and isinstance(box.get('items'), list) else []
    out = []
    for it in items:
        if isinstance(it, dict) and it.get('id') and str(it.get('holder') or '').strip():
            out.append({'id': str(it['id']), 'ref': str(it.get('ref') or ''), 'holder': str(it['holder'])})
    return out


def _ro(path):
    c = sqlite3.connect('file:%s?mode=ro' % path, uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def _table(db, name):
    return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)).fetchone())


def read_v2(path):
    """v2 장부 → (카드들, 송출 줄들). 읽기 전용으로 연다."""
    cards, sends = [], []
    db = _ro(path)
    try:
        if _table(db, 'bank_inbox'):
            for r in db.execute("SELECT id, ref, holder FROM bank_inbox WHERE holder != ''"):
                cards.append({'id': r['id'], 'ref': r['ref'] or '', 'holder': r['holder']})
        if _table(db, 'donations'):
            for r in db.execute("SELECT tx_id, name, at FROM donations WHERE tx_id LIKE 'manual\\_bank\\_%' ESCAPE '\\'"):
                sends.append({'tx': r['tx_id'], 'name': r['name'], 'at': float(r['at'] or 0)})
    finally:
        db.close()
    return cards, sends


def read_old(old, tz):
    """옛 장부 → 송출 줄들 [{tx, name, at}] (SELECT 만)."""
    out = []
    for t in OLD_TABLES:
        for r in old.rows("SELECT tx_id, name, timestamp FROM %s WHERE tx_id LIKE 'manual_bank_%%'" % t):
            if not str(r.get('tx_id') or '').startswith('manual_bank_'):
                continue
            out.append({'tx': str(r['tx_id']), 'name': r.get('name'), 'at': to_epoch(r.get('timestamp'), tz) or 0.0})
    return out


# ── 짝 맞추기 ───────────────────────────────────────────
def plan(cards, sends):
    """카드 · 송출 줄 → {pairs: {holder: (at, name, card)}, ...세기}. 아직 안 쓴다."""
    by_id, by_ref, refs = {}, {}, []
    for c in cards:
        by_id.setdefault(c['id'], c)
        ref = c.get('ref') or ''
        if ref:
            by_ref.setdefault(ref, c)
            raw = ref.split(':', 1)[1] if ':' in ref else ref
            if raw:
                by_ref.setdefault(raw, c)
                if len(raw) >= 6:
                    refs.append((raw, c))
    refs.sort(key=lambda x: len(x[0]), reverse=True)

    def find(tx):
        rest = str(tx)[len('manual_bank_'):]
        base = bl.card_of_tx(tx)
        for k in (base, rest):
            if k in by_id:
                return by_id[k]
            if k in by_ref:
                return by_ref[k]
        for cid, c in by_id.items():           # 번호가 tx_id 안 어딘가에
            if len(cid) >= 6 and cid in rest:
                return c
        for raw, c in refs:
            if raw in rest:
                return c
        return None

    first = {}                                  # 카드 id → (at, name) 가장 이른 줄
    hit = miss = skipped = 0
    for s in sends:
        nm = bl.clean_name(s.get('name'))
        c = find(s['tx'])
        if not c:
            miss += 1
            continue
        if not nm:
            skipped += 1
            continue
        hit += 1
        at = float(s.get('at') or 0)
        cur = first.get(c['id'])
        if cur is None or at < cur[0]:
            first[c['id']] = (at, nm, c['holder'])
    pairs = {}                                  # 입금자 지문 → (at, name, card, holder) 가장 최근 카드
    for cid, (at, nm, holder) in first.items():
        hk = bl.holder_key(holder)
        if not hk:
            continue
        cur = pairs.get(hk)
        if cur is None or at > cur[0]:
            pairs[hk] = (at, nm, cid, holder)
    return {'pairs': pairs, 'cards': len(by_id), 'sends': len(sends), 'hit': hit, 'miss': miss, 'skipped': skipped,
            'card_n': len(first)}


def write(v2db, p):
    """bank_learn 에 넣는다 — 한 번에(BEGIN IMMEDIATE). 돌려주는 값: {new, changed, kept}."""
    db = sqlite3.connect(v2db, timeout=10, isolation_level=None)
    got = {'new': 0, 'changed': 0, 'kept': 0}
    try:
        db.execute('PRAGMA busy_timeout=10000')
        bl.ensure(db)
        db.execute('BEGIN IMMEDIATE')
        try:
            for hk, (at, nm, cid, holder) in sorted(p['pairs'].items(), key=lambda kv: kv[1][0]):
                had = db.execute('SELECT 1 FROM bank_learn WHERE hk = ?', (hk,)).fetchone()
                if bl.learn(db, holder, nm, cid, at):
                    got['changed' if had else 'new'] += 1
                else:
                    got['kept'] += 1
            db.execute('COMMIT')
        except Exception:
            db.execute('ROLLBACK')
            raise
    finally:
        db.close()
    return got


def main(argv=None):
    ap = argparse.ArgumentParser(description='계좌 입금 배운 짝 미리 배우기 (한 번)')
    ap.add_argument('--inbox', default=os.path.join(REPO, 'bank_inbox.json'), help='옛 bank_inbox.json')
    ap.add_argument('--v2-db', default=os.path.join(V2, 'data', 'lm2.db'))
    ap.add_argument('--sqlite', help='옛 장부가 SQLite 파일이면 그 경로(없으면 DATABASE_URL 의 Postgres)')
    ap.add_argument('--db-tz', choices=('utc', 'kst'), default='utc', help='옛 장부 시각의 기준(운영 서버 utc · 이 PC kst)')
    ap.add_argument('--no-v2', action='store_true', help='v2 장부의 카드 · 송출은 안 본다(옛 것만)')
    ap.add_argument('--write', action='store_true', help='진짜로 넣는다(빼면 세어 보기만)')
    a = ap.parse_args(argv)
    if not os.path.isfile(a.v2_db):
        print('v2 장부가 없습니다(%s) — --v2-db 로 알려 주세요' % a.v2_db)
        return 2
    cards = read_inbox(a.inbox)
    n_old_cards = len(cards)
    sends = []
    url = None if a.sqlite else os.environ.get('DATABASE_URL')
    if a.sqlite or url:
        old = Old(a.sqlite, url)
        try:
            sends = read_old(old, a.db_tz)
        finally:
            old.conn.close()            # 읽기는 여기까지 — 옛 장부를 붙잡고 있지 않는다
    else:
        print('옛 장부를 모릅니다(DATABASE_URL · --sqlite 없음) — 옛 장부 송출은 건너뜁니다')
    n_old_sends = len(sends)
    n_v2_cards = n_v2_sends = 0
    if not a.no_v2:
        vc, vs = read_v2(a.v2_db)
        n_v2_cards, n_v2_sends = len(vc), len(vs)
        cards += vc
        sends += vs
    p = plan(cards, sends)
    print('읽은 것: 카드 %d장(옛 파일 %d · v2 %d) · 계좌 송출 %d줄(옛 장부 %d · v2 %d)'
          % (p['cards'], n_old_cards, n_v2_cards, p['sends'], n_old_sends, n_v2_sends))
    print('짝 맞추기: 카드를 찾은 줄 %d · 못 찾은 줄 %d · 이름 없음(익명 등) %d → 카드 %d장 → 입금자 %d명의 짝'
          % (p['hit'], p['miss'], p['skipped'], p['card_n'], len(p['pairs'])))
    if not a.write:
        print('세어 보기만 했습니다 — 넣으려면 --write 를 붙여 다시 돌리세요(v2 서버는 켜 둔 채로 괜찮습니다)')
        return 0
    got = write(a.v2_db, p)
    print('넣은 것: 새 짝 %(new)d · 바꾼 짝 %(changed)d · 그대로(더 최근에 배운 것 · 같은 카드) %(kept)d' % got)
    return 0


if __name__ == '__main__':
    sys.exit(main())
