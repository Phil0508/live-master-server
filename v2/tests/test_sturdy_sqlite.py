# -*- coding: utf-8 -*-
"""🧯 장부(SQLite) 기다림 · 전원 차단 대비 (sturdy 10-17).

- busy_timeout 5000ms — 다른 프로그램(백업 · sqlite3 셸 · 옛 장부 옮기기)이 잠깐 쓰기 잠금을 쥐어도 명령이 바로 실패하지 않고 기다린다.
- synchronous FULL(기본) — 전원이 통째로 나가도 '들어갔다' 고 답한 후원 · 점수는 남는다. LM2_SQLITE_SYNC 로 바꿀 수 있다.
"""
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest import mock

from v2.server import domain  # noqa: F401  (조각 · 명령 등록)
from v2.server.bus import Bus
from v2.server.store import BUSY_TIMEOUT_MS, Store


class Pragmas(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2sql_')
        self.path = os.path.join(self.dir, 'lm2.db')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _store(self):
        s = Store(self.path)
        self.addCleanup(s.close)
        return s

    def test_busy_timeout_wal_full(self):
        s = self._store()
        self.assertEqual(BUSY_TIMEOUT_MS, 5000)
        self.assertEqual(s.db.execute('PRAGMA busy_timeout').fetchone()[0], 5000)
        self.assertEqual(s.db.execute('PRAGMA journal_mode').fetchone()[0].lower(), 'wal')
        self.assertEqual(s.db.execute('PRAGMA synchronous').fetchone()[0], 2)          # 2 = FULL

    def test_sync_switch(self):
        for val, want in (('normal', 1), ('NORMAL', 1), ('full', 2), ('extra', 3), ('엉뚱', 2), ('', 2)):
            with mock.patch.dict(os.environ, {'LM2_SQLITE_SYNC': val}):
                s = Store(self.path)
                try:
                    self.assertEqual(s.db.execute('PRAGMA synchronous').fetchone()[0], want, val)
                finally:
                    s.close()

    def _hold_lock(self, sec):
        """다른 프로그램이 쓰기 잠금을 sec 초 쥐고 있다가 놓는다."""
        other = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False, timeout=0)
        other.execute('BEGIN IMMEDIATE')
        other.execute("INSERT INTO slices(name, value, at) VALUES('t_sturdy_other', '1', 0) "
                      "ON CONFLICT(name) DO UPDATE SET value = excluded.value")
        t = threading.Timer(sec, lambda: (other.execute('COMMIT'), other.close()))
        t.start()
        self.addCleanup(t.join)
        return t

    def test_command_waits_for_other_writer(self):
        s = self._store()
        bus = Bus(s)
        self._hold_lock(0.6)
        t0 = time.time()
        res = bus.run_sync('session.start', {'names': ['하율']})       # 잠금이 풀릴 때까지 기다렸다가 들어간다
        waited = time.time() - t0
        self.assertTrue(res['ok'], res)
        self.assertGreaterEqual(waited, 0.4)
        self.assertLess(waited, BUSY_TIMEOUT_MS / 1000.0)
        self.assertTrue(bus.state.get('session')['live'])

    def test_without_wait_it_would_fail(self):
        """대조군 — 기다림이 없으면(timeout 0) 같은 순간에 'database is locked' 로 실패한다(위 검사가 헛것이 아님)."""
        self._store()
        self._hold_lock(0.4)
        raw = sqlite3.connect(self.path, isolation_level=None, timeout=0)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                raw.execute('BEGIN IMMEDIATE')
        finally:
            raw.close()


if __name__ == '__main__':
    unittest.main()
