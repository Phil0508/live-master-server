# -*- coding: utf-8 -*-
"""옛 장부 → v2 장부 옮기기 — 가짜 옛 SQLite 를 만들어 옮기고, v2 가 그걸 제대로 읽는지 본다."""
import calendar
import os
import shutil
import sqlite3
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from v2.server.app import create_app
from v2.tools import import_old_db as imp

PW, SECRET = 'pw', 's' * 32
H = {'Authorization': 'Bearer ' + SECRET}


def make_old(path):
    db = sqlite3.connect(path)
    db.executescript("""
    CREATE TABLE donation_archive (id INTEGER PRIMARY KEY, archived_at TEXT, session_label TEXT, timestamp TEXT, name TEXT,
        amount INTEGER, current_total INTEGER, message TEXT, source TEXT, tx_id TEXT);
    CREATE TABLE donation_history (id INTEGER PRIMARY KEY, timestamp TEXT, name TEXT, amount INTEGER, current_total INTEGER,
        message TEXT, source TEXT, tx_id TEXT);
    CREATE TABLE donor_memory (id INTEGER PRIMARY KEY, timestamp TEXT, donor TEXT, player TEXT, amount INTEGER, message TEXT);
    CREATE TABLE alias_memory (id INTEGER PRIMARY KEY, token TEXT, player TEXT, hits INTEGER, updated TEXT);
    CREATE TABLE donor_excluded (name TEXT PRIMARY KEY, memo TEXT, added_at TEXT);
    CREATE TABLE vip_donators (name TEXT PRIMARY KEY, grade TEXT, custom_color TEXT, badge TEXT);
    """)
    db.executemany('INSERT INTO donation_archive (session_label, timestamp, name, amount, message, source, tx_id) VALUES (?,?,?,?,?,?,?)', [
        ('2026-10-01 수요일', '2026-10-01 12:00:00', '별빛', 50000, '하율 화이팅', 'toonation', 'toon_1'),
        ('2026-10-01 수요일', '2026-10-01 13:00:00', '달빛님', 30000, '', 'toonation', 'toon_2'),
        ('2026-10-01 수요일', '2026-10-01 13:00:00', '달빛님', 30000, '', 'toonation', 'toon_2'),   # 같은 tx 두 번(옛 보관 중복)
        ('2026-09-24 수요일', 'garbage', '깨진줄', 1000, '', 'toonation', 'toon_x'),
    ])
    db.execute("INSERT INTO donation_history (timestamp, name, amount, message, source, tx_id) VALUES ('2026-10-06 11:00:00', '해님', 20000, '', 'toonation', 'toon_3')")
    db.executemany('INSERT INTO donor_memory (timestamp, donor, player, amount, message) VALUES (?,?,?,?,?)', [
        ('2026-10-01 12:00:00', '별빛', '하율', 5, '하율 화이팅'), ('2026-09-24 12:00:00', '별빛', '하율', 3, ''),
        ('2026-09-24 12:00:00', '익명', '서아', 3, '')])
    db.execute("INSERT INTO alias_memory (token, player, hits, updated) VALUES ('율이', '하율', 4, '2026-10-01 12:00:00')")
    db.execute("INSERT INTO donor_excluded (name) VALUES ('테스트계정')")
    db.executemany('INSERT INTO vip_donators VALUES (?,?,?,?)', [('단골손님', 'gold', '#ffd700', '⭐'), ('이상한등급', 'KING', '', '')])
    db.commit()
    db.close()


class ImportOld(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2imp_')
        self.old = os.path.join(self.dir, 'old.db')
        self.v2 = os.path.join(self.dir, 'v2.db')
        make_old(self.old)
        self.clients = []

    def tearDown(self):
        for c in self.clients:                 # ⚠️ 장부를 닫아야 윈도우에서 임시 폴더가 지워진다(안 닫아 74개가 쌓였다)
            c.app.state.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def run_tool(self, *extra):
        return imp.main(['--sqlite', self.old, '--v2-db', self.v2, '--check-url', 'http://127.0.0.1:9/none', *extra])

    def test_dry_run_writes_nothing(self):
        self.assertEqual(self.run_tool(), 0)
        self.assertFalse(os.path.exists(self.v2))

    def test_import_and_read_back(self):
        self.assertEqual(self.run_tool('--write'), 0)
        self.assertEqual(self.run_tool('--write'), 0)           # 두 번 돌려도 그대로
        c = TestClient(create_app(self.v2, password=PW, secret=SECRET))
        self.clients.append(c)
        s = {r['session']: r for r in c.get('/api/sessions', headers=H).json()['sessions']}
        self.assertEqual((s['old-2026-10-01 수요일']['n'], s['old-2026-10-01 수요일']['total']), (2, 80000))   # 중복 tx 는 한 번
        self.assertEqual(s['old-current']['total'], 20000)
        self.assertNotIn('old-2026-09-24 수요일', s)              # 시각을 못 읽은 줄은 건너뛴다
        r = c.get('/api/ledger?session=old-2026-10-01 수요일', headers=H).json()
        first = sorted(r['rows'], key=lambda x: x['at'])[0]
        self.assertEqual(first['at'], float(calendar.timegm(time.strptime('2026-10-01 12:00:00', '%Y-%m-%d %H:%M:%S'))))   # 서버 시계 UTC 그대로
        db = sqlite3.connect(self.v2)
        self.assertEqual(db.execute("SELECT COUNT(*) FROM donor_memory WHERE ref LIKE 'old:%'").fetchone()[0], 2)  # 익명은 안 옮긴다
        self.assertEqual(db.execute("SELECT hits FROM alias_memory WHERE token='율이'").fetchone()[0], 4)        # 두 번 돌려도 4
        db.close()
        c.post('/api/cmd', json={'type': 'session.start', 'data': {'names': ['하율', '서아']}}, headers=H)
        st = c.get('/api/state', headers=H).json()['slices']
        self.assertEqual(st['donor_rules']['excluded'], ['테스트계정'])
        self.assertEqual(st['tallies']['vip']['단골손']['grade'], 'GOLD')          # 방송 시작하자마자 등급이 붙는다(열쇠는 끝 '님' 을 뗀 이름 — 옛 규칙)
        self.assertNotIn('이상한등급', st['donor_rules'].get('manual', {}))

    def test_kst_and_refuse_running(self):
        self.assertEqual(imp.to_epoch('2026-10-01 21:00:00', 'kst'), imp.to_epoch('2026-10-01 12:00:00', 'utc'))
        self.assertIsNone(imp.to_epoch('?', 'utc'))
        import http.server, threading
        srv = http.server.HTTPServer(('127.0.0.1', 0), http.server.SimpleHTTPRequestHandler)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            rc = imp.main(['--sqlite', self.old, '--v2-db', self.v2, '--write', '--check-url', 'http://127.0.0.1:%d/' % srv.server_port])
        finally:
            srv.shutdown()
        self.assertEqual(rc, 3)                                   # 켜진 서버가 있으면 안 한다


if __name__ == '__main__':
    unittest.main()
