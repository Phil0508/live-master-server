# -*- coding: utf-8 -*-
"""v2 퇴근빵 · 지옥탈출 — 목표를 넘기면 서버가 바로 대기함에 카드를 만든다."""
import unittest

from v2.tests.test_flow import Base


class Races(Base):
    def cards(self):
        return [(d['name'], d['kind']) for d in self.st()['pending'] if d.get('type') == 'off_work']

    def test_home(self):
        self.cmd('home.goal', name='하율', goal=10)
        self.cmd('home.on', on=True)
        self.cmd('score.add', name='하율', delta=9)
        self.assertEqual(self.cards(), [])
        self.cmd('score.add', name='하율', delta=1)
        self.assertEqual(self.cards(), [('하율', 'home')])
        self.cmd('score.add', name='하율', delta=5)                       # 또 넘겨도 한 번
        self.assertEqual(self.cards(), [('하율', 'home')])
        cid = self.st()['pending'][0]['id']
        self.cmd('offwork.send', id=cid)
        s = self.st()
        self.assertEqual(s['popup']['offwork']['name'], '하율')
        self.assertEqual(self.cards(), [])
        self.cmd('session.end')
        self.assertEqual(self.st()['home']['goals'], {'하율': 10})          # 목표는 남는다

    def test_hell(self):
        self.cmd('score.add', name='서아', delta=7)
        c, r = self.cmd('hell.start')
        self.assertEqual(c, 200, r)
        h = self.st()['hell']
        self.assertEqual(h['goals'], {'서아': 50, '하율': 40, '채원': 30})   # 지금 점수 순 · 같으면 줄 순서
        self.assertEqual(self.st()['show']['stage'], 'hell')
        self.cmd('hell.goal', name='채원', goal=3)
        self.cmd('score.add', name='채원', delta=3)
        self.assertEqual(self.cards(), [('채원', 'hell')])
        self.cmd('hell.goal', name='채원', goal=10)                         # 목표를 올리면 다시 진행 중
        self.assertNotIn('채원', self.st()['hell']['escaped'])
        self.cmd('hell.start')                                               # 다시 시작하면 지난 카드는 걷는다
        self.assertEqual(self.cards(), [])
        self.assertEqual(self.cmd('hell.goal', name='없음', goal=1)[0], 404)


if __name__ == '__main__':
    unittest.main()
