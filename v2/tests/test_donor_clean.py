# -*- coding: utf-8 -*-
"""🧹 후원 장부 청소(donor_clean) · 옛 기억 잇기(tools/relink_old_memory) · 시험 이름 목록(tools/report_test_names)."""
import contextlib
import hashlib
import io
import json
import os
import shutil
import sqlite3
import tempfile
import types
import unittest

from v2.server.domain import donor_clean as dc
from v2.server.domain import donor_memory as dm
from v2.tools import relink_old_memory as rl
from v2.tools import report_test_names as rt

T0 = 1790000000.0


class RealDonation(unittest.TestCase):
    def test_not_real(self):
        self.assertFalse(dc.is_real_donation({'source': 'mobile', 'amount': 30, 'message': '수동 점수 조작'}))
        self.assertFalse(dc.is_real_donation({'source': 'mobile', 'amount': 30, 'message': ''}))
        self.assertFalse(dc.is_real_donation({'source': 'toonation_test', 'amount': 10000}))
        self.assertFalse(dc.is_real_donation({'source': 'toonation', 'amount': 10000, 'tx_id': 'toon_t2_abc'}))
        self.assertFalse(dc.is_real_donation({'source': 'toonation', 'amount': 10000, 'message': '수동 점수 조작 -3'}))
        self.assertFalse(dc.is_real_donation({'source': 'toonation', 'amount': 0, 'message': '[시그니처 신청: ioi]'}))
        self.assertFalse(dc.is_real_donation({'source': 'manual', 'amount': -20000}))
        self.assertFalse(dc.is_real_donation({'source': 'manual', 'amount': 'x'}))
        self.assertFalse(dc.is_real_donation(None))

    def test_real(self):
        self.assertTrue(dc.is_real_donation({'source': 'toonation', 'amount': 10600, 'message': '밍밍', 'tx_id': 'abc'}))
        self.assertTrue(dc.is_real_donation({'source': 'manual', 'amount': 1000, 'message': None, 'tx_id': None}))
        self.assertTrue(dc.is_real_donation({'source': 'toonation', 'amount': 3000, 'status': 'display'}))  # 화면에만 떠도 돈은 들어왔다

    def test_sqlite_row(self):
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.row_factory = sqlite3.Row
        conn.execute('CREATE TABLE d (source TEXT, amount INTEGER, message TEXT)')     # tx_id 칸이 없어도 된다
        conn.execute("INSERT INTO d VALUES ('toonation', 50000, '앙앙'), ('mobile', -30, '수동 점수 조작')")
        rows = conn.execute('SELECT * FROM d ORDER BY rowid').fetchall()
        self.assertEqual([dc.is_real_donation(r) for r in rows], [True, False])


class TestNames(unittest.TestCase):
    def test_donor_names(self):
        for n in ('1', '11', '1111', '123', '123546789', ' 12 님'):
            self.assertEqual(dc.test_name_reason(n), '숫자만', n)
        for n in ('Player 1', 'player2', 'PLAYER 10'):
            self.assertEqual(dc.test_name_reason(n), 'Player N', n)
        for n in ('테스트', '후원테스트', 'Test', 'tester'):
            self.assertEqual(dc.test_name_reason(n), '테스트 글자', n)
        for n in ('밍밍', '7싸단', '영원', '쏘랑왕자님', '익명', '', None, '이래 추는 기다~~~~~설향', 'Player'):
            self.assertEqual(dc.test_name_reason(n), '', n)

    def test_player_names(self):
        roster = ['밍밍', '앙앙']
        self.assertEqual(dc.test_player_reason('고수달', roster), '명단에 없음')
        self.assertEqual(dc.test_player_reason('Player 2', roster), 'Player N')
        self.assertEqual(dc.test_player_reason('밍밍', roster), '')
        self.assertEqual(dc.test_player_reason('고수달', []), '')          # 방송이 끝나 명단이 비었으면 명단으로 판단 안 함
        self.assertEqual(dc.test_player_reason('Player 2', []), 'Player N')


DONATIONS_SQL = ("CREATE TABLE donations (id TEXT PRIMARY KEY, tx_id TEXT UNIQUE, at REAL NOT NULL, name TEXT NOT NULL,"
                 " amount INTEGER NOT NULL, message TEXT NOT NULL DEFAULT '', source TEXT NOT NULL DEFAULT '',"
                 " status TEXT NOT NULL, player TEXT, session TEXT NOT NULL DEFAULT '', no INTEGER)")


def _db(dir_, donations, memory, players=None):
    path = os.path.join(dir_, 'lm2.db')
    conn = sqlite3.connect(path)
    conn.execute(DONATIONS_SQL)
    conn.execute('CREATE TABLE slices (name TEXT PRIMARY KEY, value TEXT NOT NULL, at REAL NOT NULL)')
    dm.ensure(types.SimpleNamespace(db=conn))
    for i, (did, at, name, amount, msg, source, status) in enumerate(donations):
        conn.execute('INSERT INTO donations(id, tx_id, at, name, amount, message, source, status, player, session, no)'
                     ' VALUES(?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)', (did, did, at, name, amount, msg, source, status, 's1', i))
    conn.executemany('INSERT INTO donor_memory(at, donor, player, amount, message, ref) VALUES(?, ?, ?, ?, ?, ?)', memory)
    if players is not None:
        conn.execute("INSERT INTO slices VALUES('players', ?, 0)",
                     (json.dumps({'list': [{'name': p} for p in players], 'extra': []}, ensure_ascii=False),))
    conn.execute("INSERT INTO slices VALUES('donor_rules', ?, 0)", (json.dumps({'excluded': ['엔젤컴퍼니']}, ensure_ascii=False),))
    conn.commit()
    conn.close()
    return path


def _hash(path):
    with open(path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()


class Relink(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2rl_')
        self.addCleanup(shutil.rmtree, self.dir, True)
        A = 'archived'
        long_msg = '가' * 400
        donations = [
            ('old_a1', T0, '철수', 30000, '밍밍', 'toonation', A),                 # 하나만 맞음
            ('old_a2', T0 + 100, '영희', 40000, '둘이 반띵', 'toonation', A),       # 나눠 준 한 건(2+2)
            ('old_a3', T0 + 200, '하데스', 10300, '밍밍이', 'toonation', A),        # 똑같은 셋 → 셋 다 밍밍
            ('old_a4', T0 + 203, '하데스', 10300, '밍밍이', 'toonation', A),
            ('old_a5', T0 + 206, '하데스', 10300, '밍밍이', 'toonation', A),
            ('old_a6', T0 + 300, '두리', 10000, '', 'toonation', A),               # 똑같은 둘인데 받은 사람이 다름 → 애매
            ('old_a7', T0 + 301, '두리', 10000, '', 'toonation', A),
            ('old_a8', T0 + 400, '늦게', 10000, '앙앙', 'toonation', A),            # 기억이 15분 뒤 → 시각 안 맞음
            ('old_a9', T0 + 500, '금액', 50000, '앙앙', 'toonation', A),            # 점수 3 ≠ 5 → 금액 안 맞음
            ('old_a10', T0 + 600, '앙앙', 30, '수동 점수 조작', 'mobile', A),       # 손 점수 → 진짜 후원 아님
            ('old_a11', T0 + 700, '긴글', 20000, long_msg, 'toonation', A),        # 기억은 300자에서 자른다
            ('old_a12', T0 + 800, '1111', 20000, '', 'toonation', A),              # 시험 이름
            ('don_x1', T0 + 900, '찬바람', 54000, '밍ㅋ', 'manual', 'assigned'),    # v2 기억(ref = 장부 id)
        ]
        memory = [
            (T0 + 9, '철수', '밍밍', 3, '밍밍', 'old:1'),
            (T0 + 115, '영희', '밍밍', 2, '둘이 반띵', 'old:2'),
            (T0 + 115, '영희', '앙앙', 2, '둘이 반띵', 'old:3'),
            (T0 + 210, '하데스', '밍밍', 1, '밍밍이', 'old:4'),
            (T0 + 212, '하데스', '밍밍', 1, '밍밍이', 'old:5'),
            (T0 + 214, '하데스', '밍밍', 1, '밍밍이', 'old:6'),
            (T0 + 310, '두리', '밍밍', 1, '', 'old:7'),
            (T0 + 312, '두리', '앙앙', 1, '', 'old:8'),
            (T0 + 400 + 900, '늦게', '앙앙', 1, '앙앙', 'old:9'),
            (T0 + 510, '금액', '앙앙', 3, '앙앙', 'old:10'),
            (T0 + 610, '앙앙', '앙앙', 0, '수동 점수 조작', 'old:11'),
            (T0 + 710, '긴글', '쏘랑', 2, long_msg[:300], 'old:12'),
            (T0 + 810, '1111', '한명', 2, '', 'old:13'),
            (T0 + 905, '찬바람', '밍밍', 5, '밍ㅋ', 'don_x1'),
            (T0 + 1000, '없는사람', '밍밍', 1, '', 'old:14'),
        ]
        self.db = _db(self.dir, donations, memory, players=['밍밍', '앙앙', '쏘랑'])

    def _plan(self):
        conn = rl.open_db(self.db)
        try:
            mem, dons = rl.load(conn)
            return rl.plan(mem, dons), mem
        finally:
            conn.close()

    def test_plan(self):
        before = _hash(self.db)
        res, mem = self._plan()
        self.assertEqual(_hash(self.db), before)                                   # 보기만 — 장부는 그대로
        got = {r['ref']: r['final'] for r in res['links']}
        self.assertEqual(got, {
            'old_a1': ['밍밍'], 'old_a2': ['밍밍', '앙앙'],
            'old_a3': ['밍밍'], 'old_a4': ['밍밍'], 'old_a5': ['밍밍'],
            'old_a11': ['쏘랑'], 'don_x1': ['밍밍'],
        })
        self.assertEqual(res['reasons'], {'ambiguous': 2, 'no_time': 1, 'no_amount': 1, 'not_real': 1,
                                          'test_name': 1, 'no_name': 1})
        c = res['counts']
        self.assertEqual((c['memory'], c['memory_linked'], c['links'], c['direct'], c['split'], c['same_cluster']),
                         (15, 8, 7, 1, 1, 3))
        text = rl.report(res, mem)
        self.assertIn('15줄 중 8줄', text)
        for secret in ('철수', '하데스', '밍밍이'):                                  # 이름 · 메시지는 안 찍는다
            self.assertNotIn(secret, text)

    def test_write_idempotent_and_keeps_human(self):
        conn = sqlite3.connect(self.db)
        rl.ensure(conn)
        conn.execute("INSERT INTO answer_log(ref, at, name, final, how) VALUES('old_a1', 1, '철수', '[\"앙앙\"]', 'human')")
        conn.commit()
        conn.close()
        res, _ = self._plan()
        conn = rl.open_db(self.db, write=True)
        try:
            self.assertEqual(rl.write(conn, res['links']), {'written': 6, 'kept': 1})
            snap1 = conn.execute('SELECT * FROM answer_log ORDER BY ref').fetchall()
            self.assertEqual(rl.write(conn, res['links']), {'written': 6, 'kept': 1})   # 또 돌려도 같다
            snap2 = conn.execute('SELECT * FROM answer_log ORDER BY ref').fetchall()
            self.assertEqual([tuple(r) for r in snap1], [tuple(r) for r in snap2])
            row = conn.execute("SELECT * FROM answer_log WHERE ref = 'old_a2'").fetchone()
            self.assertEqual((row['how'], json.loads(row['final']), row['amount'], row['name'], row['session'],
                              row['guess'], row['changed'], row['undone']),
                             ('relink', ['밍밍', '앙앙'], 40000, '영희', 's1', None, None, 0))
            human = conn.execute("SELECT how, final FROM answer_log WHERE ref = 'old_a1'").fetchone()
            self.assertEqual(tuple(human), ('human', '["앙앙"]'))                    # 사람이 적은 줄은 그대로
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM donor_memory').fetchone()[0], 15)   # 기억은 안 건드림
        finally:
            conn.close()

    def test_cli_dry_run_and_write(self):
        before = _hash(self.db)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rl.main(['--db', self.db, '--json'])
        self.assertEqual(_hash(self.db), before)
        self.assertEqual(json.loads(out.getvalue())['counts']['links'], 7)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rl.main(['--db', self.db, '--write'])
        self.assertIn('정답지에 씀: 7줄', out.getvalue())
        conn = sqlite3.connect(self.db)
        try:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM answer_log WHERE how = 'relink'").fetchone()[0], 7)
        finally:
            conn.close()

    def test_schema_matches_spec(self):
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        rl.ensure(conn)
        cols = [r[1] for r in conn.execute('PRAGMA table_info(answer_log)')]
        self.assertEqual(cols, ['ref', 'at', 'session', 'name', 'amount', 'source', 'guess', 'guess_conf', 'guess_how',
                                'final', 'how', 'changed', 'undone'])
        self.assertIn('answer_log_name', [r[1] for r in conn.execute('PRAGMA index_list(answer_log)')])


class ReportTestNames(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2tn_')
        self.addCleanup(shutil.rmtree, self.dir, True)
        A = 'archived'
        self.donations = [
            ('d1', T0, '1111', 23000, '', 'manual', A),
            ('d2', T0 + 1, 'Player 1', 30, '수동 점수 조작', 'mobile', A),
            ('d3', T0 + 2, '밍밍팬', 10000, '', 'toonation', A),
            ('d4', T0 + 3, '엔젤컴퍼니', 10600, '후원 테스트 입니다.', 'toonation', A),
        ]
        self.memory = [
            (T0, '1111', '한명', 2, '', 'x'),
            (T0, '밍밍팬', '밍밍', 1, '', 'y'),
            (T0, '테스트', 'Player 2', 1, '', 'z'),
        ]

    def test_with_roster(self):
        db = _db(self.dir, self.donations, self.memory, players=['밍밍'])
        before = _hash(db)
        conn = rt.open_ro(db)
        try:
            res = rt.collect(conn)
        finally:
            conn.close()
        self.assertEqual(_hash(db), before)                                        # 읽기만
        donors = {r['name']: (r['why'], r['ledger_real'], r['ledger'], r['memory']) for r in res['donors']}
        self.assertEqual(donors, {'1111': ('숫자만', 1, 1, 1), 'Player 1': ('Player N', 0, 1, 0),
                                  '테스트': ('테스트 글자', 0, 0, 1)})
        self.assertEqual({r['name']: r['why'] for r in res['players']}, {'한명': '명단에 없음', 'Player 2': 'Player N'})
        self.assertEqual(res['excluded'], [{'name': '엔젤컴퍼니', 'why': '', 'ledger': 1, 'won': 10600}])
        self.assertIn('1111 · 숫자만', rt.report(res))

    def test_empty_roster_lists_all_players(self):
        db = _db(self.dir, self.donations, self.memory, players=[])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rt.main(['--db', db])
        text = out.getvalue()
        self.assertIn('명단으로는 판단 못 함', text)
        self.assertIn('선수 칸 전체', text)
        self.assertIn('한명 · 기억 1건', text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rt.main(['--db', db, '--roster', '밍밍', '--json'])
        res = json.loads(out.getvalue())
        self.assertEqual(sorted(r['name'] for r in res['players']), ['Player 2', '한명'])


if __name__ == '__main__':
    unittest.main()
