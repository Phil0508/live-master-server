# -*- coding: utf-8 -*-
"""🧪 무인 방송 미리 채점(tools/backtest_autopilot) — 앞의 기록만 알고 판단 · 방송 가르기 · 나눠 줌 묶기 · 읽기만 · 이름 안 찍기."""
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

from v2.server.domain import donor_memory as dm
from v2.tools import backtest_autopilot as bt

DAY = 86400
T0 = 1790000000.0


class Backtest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2bt_')
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.db = os.path.join(self.dir, 'lm2.db')
        conn = sqlite3.connect(self.db)
        dm.ensure(types.SimpleNamespace(db=conn))
        rows = [
            (T0 + 0, '비밀후원자', '서아', 10000, '서아 화이팅', 'don_1'),   # 이름 → 자동 맞힘
            (T0 + 60, '비밀후원자', '서아', 10000, '', 'don_2'),            # 이력 1번 → 모름(AI 에게 물었을 것)
            (T0 + 120, '비밀후원자', '서아', 10000, '', 'don_3'),           # 이력 2번 → 0.80 추천 맞힘
            (T0 + 180, '비밀후원자', '서아', 10000, '', 'don_4'),           # 이력 3번 → 0.87 추천 맞힘
            (T0 + 240, '비밀후원자', '하율', 10000, '', 'don_5'),           # 이력 4번 → 0.93 자동 — 그런데 하율 → 틀림
            (T0 + 300, '숨은손님', '하율', 5000, '하율 서아', 'old:10'),       # 옛 줄 둘 = 나눠 준 한 건 → 두 이름 → 모름
            (T0 + 300, '숨은손님', '서아', 5000, '하율 서아', 'old:11'),
            (T0 + 2 * DAY, '비밀후원자', '서아', 10000, '', 'don_9'),       # 다른 방송(명단 서아뿐) — 이력 4/1 중 서아만 → 자동 맞힘
        ]
        conn.executemany('INSERT INTO donor_memory(at, donor, player, amount, message, ref) VALUES(?, ?, ?, ?, ?, ?)', rows)
        conn.commit()
        conn.close()

    def _hash(self):
        with open(self.db, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()

    def test_replay_counts(self):
        before = self._hash()
        r = bt.run(bt.load(self.db), examples=5)
        self.assertEqual(self._hash(), before)                                   # 장부는 읽기만
        t = r['total']
        self.assertEqual((t['n'], t['auto_ok'], t['auto_bad'], t['sug_ok'], t['sug_bad'], t['unknown'], t['ai']),
                         (7, 2, 1, 2, 0, 2, 1))
        self.assertEqual([(b['n'], b['roster']) for b in r['broadcasts']], [(6, 2), (1, 1)])
        self.assertEqual(len(r['bad_examples']), 1)
        self.assertEqual(r['bad_examples'][0]['source'], '이력')

    def test_report_has_no_donor_names(self):
        r = bt.run(bt.load(self.db), examples=5)
        text = bt.report(r)
        self.assertIn('자동 정확도 66.7%', text)
        for secret in ('비밀후원자', '숨은손님', '10,000', '10000'):
            self.assertNotIn(secret, text)

    def test_main_empty_and_json(self):
        empty = os.path.join(self.dir, 'empty.db')
        conn = sqlite3.connect(empty)
        dm.ensure(types.SimpleNamespace(db=conn))
        conn.commit()
        conn.close()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(bt.main(['--db', empty]), 1)
            self.assertEqual(bt.main(['--db', self.db, '--json']), 0)
        self.assertEqual(json.loads(out.getvalue().split('\n', 1)[1])['total']['n'], 7)


if __name__ == '__main__':
    unittest.main()
