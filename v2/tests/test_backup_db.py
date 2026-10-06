# -*- coding: utf-8 -*-
"""v2 장부 백업 — 켜진 장부에서 떠도 깨지지 않고, 오래된 것은 지운다."""
import gzip
import os
import shutil
import sqlite3
import tempfile
import unittest

from v2.server.store import Store
from v2.tools import backup_db as bk


class Backup(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2bk_t_')
        self.db = os.path.join(self.dir, 'lm2.db')
        self.st = Store(self.db)                       # 서버처럼 열어 둔 채로 뜬다
        self.st.db.execute("INSERT INTO donations (id, tx_id, at, name, amount, status) VALUES ('d1', 't1', 1, '별빛', 50000, 'pending')")

    def tearDown(self):
        self.st.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_snapshot_and_prune(self):
        out = os.path.join(self.dir, 'bk')
        p = bk.snapshot(self.db, out)
        raw = os.path.join(self.dir, 'back.db')
        with gzip.open(p, 'rb') as g, open(raw, 'wb') as f:
            shutil.copyfileobj(g, f)
        c = sqlite3.connect(raw)
        self.assertEqual(c.execute('SELECT name FROM donations').fetchone()[0], '별빛')
        c.close()
        for i in range(5):
            open(os.path.join(out, 'lm2-2026010%d-0000.db.gz' % i), 'wb').close()
        self.assertEqual(bk.prune(out, 3), 3)
        self.assertEqual(len(os.listdir(out)), 3)
        self.assertIn(os.path.basename(p), os.listdir(out))   # 방금 뜬 것(가장 새것)은 남는다

    def test_main_missing_db(self):
        self.assertEqual(bk.main(['--db', os.path.join(self.dir, 'none.db')]), 2)


if __name__ == '__main__':
    unittest.main()
