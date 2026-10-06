# -*- coding: utf-8 -*-
"""📒 장부 — SQLite(WAL) 한 파일. 한 프로세스가 한 줄로 쓴다(명령은 bus 가 하나씩 넘긴다).

표
  slices      조각마다 지금 내용(JSON) — 서버가 켜질 때 여기서 읽는다
  events      명령 기록(번호 · 때 · 누가 · 무엇) — 무슨 일이 있었는지 · 되돌리기의 근거
  donations   후원 장부 — tx_id 는 유일(같은 후원이 두 번 들어가지 못한다)
  score_log   점수 · 기여도 기록 — 되돌리기는 여기서 거꾸로 한다

⚠️ 옛 서버는 Postgres(운영) · SQLite(개발)가 달라 개발에선 되는데 운영에서 다른 일이 있었다.
   v2 는 어디서나 같은 SQLite 다. 한 서버 · 한 프로세스라 충분하고, 왕복이 없어 빠르다.
"""
import json
import os
import sqlite3
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS slices (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at REAL NOT NULL,
    type TEXT NOT NULL,
    by TEXT NOT NULL DEFAULT '',
    data TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS donations (
    id TEXT PRIMARY KEY,
    tx_id TEXT UNIQUE,
    at REAL NOT NULL,
    name TEXT NOT NULL,
    amount INTEGER NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,              -- pending · assigned · ignored · display
    player TEXT,                       -- 배정된 선수
    session TEXT NOT NULL DEFAULT ''   -- 어느 방송에 들어온 것인가
);
CREATE INDEX IF NOT EXISTS donations_session ON donations(session, at);
CREATE TABLE IF NOT EXISTS score_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at REAL NOT NULL,
    player TEXT NOT NULL,
    field TEXT NOT NULL,               -- score · contribution
    list TEXT NOT NULL DEFAULT 'list', -- list(본 명단) · extra(추가 명단) · bottom(운영비) · jar(모금함)
    delta INTEGER NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    ref TEXT NOT NULL DEFAULT '',      -- 후원 id 등
    undone INTEGER NOT NULL DEFAULT 0,
    session TEXT NOT NULL DEFAULT ''
);
"""


class Store:
    def __init__(self, path):
        self.path = path
        if path != ':memory:':
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        # check_same_thread=False — 명령은 bus 가 한 줄로 넘기므로 동시에 쓰지 않는다
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=NORMAL')
        self.db.executescript(SCHEMA)

    # ── 조각 ──
    def load_slices(self):
        return {r['name']: json.loads(r['value']) for r in self.db.execute('SELECT name, value FROM slices')}

    def last_seq(self):
        r = self.db.execute('SELECT MAX(seq) AS s FROM events').fetchone()
        return int(r['s'] or 0)

    # ── 한 번에(명령 하나) ──
    def begin(self):
        self.db.execute('BEGIN IMMEDIATE')

    def commit(self):
        self.db.execute('COMMIT')

    def rollback(self):
        try:
            self.db.execute('ROLLBACK')
        except sqlite3.OperationalError:
            pass

    def put_slices(self, slices):
        now = time.time()
        self.db.executemany('INSERT INTO slices(name, value, at) VALUES(?, ?, ?) '
                            'ON CONFLICT(name) DO UPDATE SET value=excluded.value, at=excluded.at',
                            [(k, json.dumps(v, ensure_ascii=False), now) for k, v in slices.items()])

    def add_event(self, type_, by, data):
        cur = self.db.execute('INSERT INTO events(at, type, by, data) VALUES(?, ?, ?, ?)',
                              (time.time(), type_, by or '', json.dumps(data, ensure_ascii=False)))
        return cur.lastrowid

    # ── 후원 장부 ──
    def donation_by_tx(self, tx_id):
        if not tx_id:
            return None
        r = self.db.execute('SELECT * FROM donations WHERE tx_id = ?', (tx_id,)).fetchone()
        return dict(r) if r else None

    def donation(self, did):
        r = self.db.execute('SELECT * FROM donations WHERE id = ?', (did,)).fetchone()
        return dict(r) if r else None

    def add_donation(self, d):
        self.db.execute('INSERT INTO donations(id, tx_id, at, name, amount, message, source, status, player, session) '
                        'VALUES(:id, :tx_id, :at, :name, :amount, :message, :source, :status, :player, :session)', d)

    def set_donation(self, did, **kw):
        cols = ', '.join('%s = :%s' % (k, k) for k in kw)
        self.db.execute('UPDATE donations SET %s WHERE id = :_id' % cols, dict(kw, _id=did))

    def donations(self, session=None, status=None, limit=500):
        q, a = 'SELECT * FROM donations WHERE 1=1', []
        if session is not None:
            q += ' AND session = ?'; a.append(session)
        if status is not None:
            q += ' AND status = ?'; a.append(status)
        q += ' ORDER BY at DESC LIMIT ?'; a.append(limit)
        return [dict(r) for r in self.db.execute(q, a)]

    # ── 점수 기록 ──
    def add_score(self, player, field, delta, reason='', ref='', session='', list_='list'):
        cur = self.db.execute('INSERT INTO score_log(at, player, field, list, delta, reason, ref, session) VALUES(?, ?, ?, ?, ?, ?, ?, ?)',
                              (time.time(), player, field, list_, int(delta), reason, ref, session))
        return cur.lastrowid

    def last_scores(self, session, limit=1):
        """되돌릴 수 있는 마지막 기록(아직 안 되돌린 것)."""
        return [dict(r) for r in self.db.execute(
            'SELECT * FROM score_log WHERE session = ? AND undone = 0 ORDER BY id DESC LIMIT ?', (session, limit))]

    def score_rows(self, ref):
        return [dict(r) for r in self.db.execute('SELECT * FROM score_log WHERE ref = ? AND undone = 0 ORDER BY id', (ref,))]

    def mark_undone(self, ids):
        self.db.executemany('UPDATE score_log SET undone = 1 WHERE id = ?', [(i,) for i in ids])

    def close(self):
        self.db.close()
