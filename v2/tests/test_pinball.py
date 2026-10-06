# -*- coding: utf-8 -*-
"""v2 핀볼 — 옛 규칙(펼치기 · 뽑기 · 끝까지 남기 · 첫 보고만)."""
import unittest

from v2.server.domain.pinball import expand, winners
from v2.tests.test_flow import Base


class Pinball(Base):
    def test_rules(self):
        self.assertEqual(expand(['밍밍', '양양*3']), ['밍밍', '양양', '양양', '양양'])
        self.assertEqual(len(expand(['많이*999999'])), 800)
        self.assertEqual(winners(['a', 'b', 'c', 'd'], 'first', 2), ['a', 'b'])
        self.assertEqual(winners(['a', 'b', 'c', 'd'], 'last', 2), ['d', 'c'])     # 끝까지 남은 사람이 1등

    def test_round(self):
        self.assertEqual(self.cmd('pinball.start', names='혼자')[0], 400)
        self.cmd('pinball.setup', names='가,나\n다*2', picks=99, rule='last', map=2)
        g = self.st()['pinball']
        self.assertEqual((g['balls'], g['picks'], g['map']), (['가', '나', '다', '다'], 3, -1))   # 막은 맵 → 우리 코스
        self.cmd('pinball.start')
        g = self.st()['pinball']
        self.assertTrue(g['running'])
        self.assertEqual(self.st()['show']['stage'], 'pinball')
        self.assertEqual(self.cmd('pinball.setup', names='x,y')[0], 409)                       # 굴러가는 중엔 못 바꿈
        r = self.c.post('/api/cmd', json={'type': 'pinball.result', 'data': {'round_id': g['round_id'] - 1, 'result': ['가']}})
        self.assertEqual(r.status_code, 409)                                                    # 지난 판
        r = self.c.post('/api/cmd', json={'type': 'pinball.result', 'data': {'round_id': g['round_id'], 'result': ['나', '다', '가', '다']}})
        self.assertEqual(r.status_code, 200)                                                    # 방송판(로그인 없음)
        r = self.c.post('/api/cmd', json={'type': 'pinball.result', 'data': {'round_id': g['round_id'], 'result': ['가']}})
        self.assertEqual(r.status_code, 409)                                                    # 두 번째 화면 보고
        self.assertEqual(self.st()['pinball']['winners'], ['다', '가', '다'])


if __name__ == '__main__':
    unittest.main()
