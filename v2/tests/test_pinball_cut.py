# -*- coding: utf-8 -*-
"""🎱 핀볼 — 시간(3분)으로 판을 자르지 않는다 · 구슬이 껴서 끊은 판은 우승 딱지에 밝힌다(옛 10-11 커밋 992bf7c).

10-08 52판(구슬 186개 · 끝까지 남기)이 멀쩡히 굴러가는데 180.0초에 잘려 2개가 남은 채 엉뚱한 우승자가 굳었다.
방송판은 끼인 판만(20초 정체 — 물리 걸음으로 센다) 끝내고 cut='stall' 로 알린다. 서버는 그 표시를 받아 적는다.
"""
import os
import re
import unittest

from v2.tests.test_flow import Base

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _src(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as f:
        return f.read()


class Cut(Base):
    def _round(self, **kw):
        self.cmd('pinball.setup', names='가,나,다', rule='last')
        self.cmd('pinball.start')
        rid = self.st()['pinball']['round_id']
        r = self.c.post('/api/cmd', json={'type': 'pinball.result', 'data': dict({'round_id': rid, 'result': ['나', '다', '가']}, **kw)})
        return r.status_code, r.json()

    def test_stall_is_recorded(self):
        c, r = self._round(cut='stall')
        self.assertEqual((c, r.get('cut')), (200, 'stall'))
        g = self.st()['pinball']
        self.assertEqual((g['cut'], g['winners'], g['running']), ('stall', ['가'], False))
        self.assertEqual(self.st(auth=False)['pinball']['cut'], 'stall')          # 방송판(로그인 없음)이 딱지에 쓴다

    def test_unknown_or_missing_cut_is_clean(self):
        self.assertEqual(self._round(cut='timeout')[1].get('cut'), '')            # 모르는 값은 '제대로 갈림'
        self.assertEqual(self.st()['pinball']['cut'], '')
        self.assertEqual(self._round()[1].get('cut'), '')

    def test_cleared_on_new_round_setup_reset_session(self):
        self._round(cut='stall')
        self.cmd('pinball.start')
        self.assertEqual(self.st()['pinball']['cut'], '')                          # 새 판
        self._round(cut='stall')
        self.cmd('pinball.setup', names='x,y')
        self.assertEqual(self.st()['pinball']['cut'], '')                          # 명단 바꾸기
        self._round(cut='stall')
        self.cmd('pinball.reset')
        self.assertEqual(self.st()['pinball']['cut'], '')                          # 초기화
        self._round(cut='stall')
        self.cmd('session.end')
        self.assertEqual(self.st()['pinball']['cut'], '')                          # 방송 끝

    def test_old_saved_slice_without_cut(self):
        """cut 칸이 없던 옛 저장본(10-17 전 v2 DB)에서도 결과를 받는다."""
        store = self.c.app.state.bus.state.slices
        g = dict(store['pinball'])
        g.pop('cut', None)
        store['pinball'] = g
        c, r = self._round(cut='stall')
        self.assertEqual(c, 200, r)
        self.assertEqual(self.st()['pinball']['cut'], 'stall')


class OverlaySource(unittest.TestCase):
    """방송판 pinball.js — 판을 끝내는 길이 '승부 갈림' 과 '정체(끼임)' 둘뿐인가."""
    OV = _src('v2', 'web', 'overlay', 'widgets', 'games', 'pinball.js')

    def test_no_time_or_step_cap(self):
        self.assertNotIn('PB_MAX_MS', self.OV)
        self.assertNotIn('PB_MAX_STEPS', self.OV)
        self.assertNotRegex(self.OV, r'now\s*-\s*pbStartedAt\s*>')               # 벽시계로 자르지 않는다
        self.assertNotRegex(self.OV, r'pbSteps\s*>')                              # 걸음 수로 자르지 않는다
        self.assertIn('const PB_STALL_STEPS = 100 * 20;', self.OV)               # 정상 판 최장 정체 7초 — 20초면 안 끊는다

    def test_stall_reported_and_shown(self):
        self.assertIn("pbReport(pbLiveRound, 'stall')", self.OV)
        self.assertIn("pbReport(pbLiveRound, '')", self.OV)
        self.assertIn("cut: cut || ''", self.OV)
        self.assertIn("cut === 'stall'", self.OV)
        self.assertIn('구슬이 껴서 지금 자리로 결정', self.OV)
        self.assertRegex(self.OV, r'pbShowWinner\([^;]*g\.cut\)')
        # 보고하는 곳은 하나 — 판을 끝내는 조건이 둘(갈림 0.7초 뒤 · 정체)뿐이다
        self.assertEqual(len(re.findall(r'pbReport\(pbLiveRound', self.OV)), 2)

    def test_controller_says_so(self):
        ctl = _src('v2', 'web', 'controller', 'js', 'panels', 'games', 'pinball.js')
        self.assertIn("g.cut === 'stall'", ctl)


if __name__ == '__main__':
    unittest.main()
