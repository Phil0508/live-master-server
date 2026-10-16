# -*- coding: utf-8 -*-
"""💱 정산 차액(대표님 10-17 · w2center) — 실제 받은 돈 · 점수로 들어간 돈 · 차액과 그 까닭.

서버가 센다(v2/server/domain/ledger.py settle · GET /api/ledger/settle). 조종실 랭킹 탭 숫자 카드 밑 한 줄은 받아 적기만.
지키는 것: 까닭들의 합 == 차액(언제나) · 화면에만 · 다시 보기 · 테스트는 '실제 받은 돈' 에서 빠짐 · 로그인 없이는 못 본다.
"""
import os
import shutil
import tempfile
import unittest

from fastapi.testclient import TestClient

from v2.server.domain import ledger as lg
from v2.server.domain.rules import man_won
from v2.server.app import create_app
from v2.tests.test_ai import _guard, PW, SECRET, H, SIGS


def why(s):
    return {w['key']: (w['won'], w['n']) for w in s['why']}


class Pure(unittest.TestCase):
    def test_rule_is_man_won(self):
        # 만 원 단위 규칙 — (금액 + 4000) // 10000
        for a, p in [(5999, 0), (6000, 1), (15999, 1), (16000, 2), (100009, 10), (0, 0)]:
            self.assertEqual(man_won(a), p, a)
            self.assertEqual(man_won(a), (a + 4000) // 10000)

    def test_sum_of_reasons_is_diff(self):
        rows = [
            {'id': 'don_1', 'amount': 15000, 'status': 'assigned', 'source': 'toonation'},   # 1점 · 5천 버림
            {'id': 'don_2', 'amount': 6000, 'status': 'assigned', 'source': 'manual'},       # 1점 · 4천 올림
            {'id': 'don_3', 'amount': 5000, 'status': 'assigned', 'source': 'toonation'},    # 0점 · 5천 버림(소액)
            {'id': 'don_4', 'amount': 50000, 'status': 'pending', 'source': 'toonation'},    # 대기함
            {'id': 'don_5', 'amount': 20000, 'status': 'ignored', 'source': 'toonation'},    # 무시
            {'id': 'don_6', 'amount': 3000, 'status': 'display', 'source': 'display'},       # 화면에만 — 안 센다
            {'id': 'don_7', 'amount': 90000, 'status': 'display', 'source': 'toonation_replay'},   # 다시 보기 — 안 센다
            {'id': 'don_8', 'amount': 30000, 'status': 'assigned', 'source': 'toonation_test'},    # 🧪 테스트를 준 것
            {'id': 'don_9', 'amount': 10000, 'status': 'pending', 'source': 'toonation_test'},     # 🧪 대기 — 아무 데도 안 셈
            {'id': 'don_10', 'amount': 100009, 'status': 'assigned', 'source': 'toonation'},  # 10점 · 9원 버림
        ]
        s = lg.settle(rows)
        self.assertEqual(s['real'], 15000 + 6000 + 5000 + 50000 + 20000 + 100009)
        self.assertEqual(s['real_n'], 6)
        self.assertEqual(s['scored_pts'], 1 + 1 + 0 + 3 + 10)
        self.assertEqual(s['scored'], s['scored_pts'] * 10000)
        self.assertEqual(s['diff'], s['real'] - s['scored'])
        w = why(s)
        self.assertEqual(w['cut'], (5000 + 5000 + 9, 3))
        self.assertEqual(w['up'], (-4000, 1))
        self.assertEqual(w['pending'], (50000, 1))
        self.assertEqual(w['ignored'], (20000, 1))
        self.assertEqual(w['test'], (-30000, 1))
        self.assertEqual(s['small_zero_n'], 1)
        self.assertEqual(sum(x['won'] for x in s['why']), s['diff'])      # ⭐ 까닭들의 합 == 차액

    def test_empty_and_hand_note(self):
        s = lg.settle([])
        self.assertEqual((s['real'], s['scored'], s['diff']), (0, 0, 0))
        self.assertTrue(all(x['won'] == 0 for x in s['why']))
        # 점수 기록에 규칙과 다른 점수가 남았으면(나눠 줄 때 손으로 바꿈) 참고로만 — 차액 셈은 그대로
        rows = [{'id': 'don_a', 'amount': 30000, 'status': 'assigned', 'source': 'toonation'}]
        s = lg.settle(rows, {'don_a': 5})
        self.assertEqual(s['hand'], {'won': -20000, 'n': 1})
        self.assertEqual(s['diff'], 0)


class Route(unittest.TestCase):
    def setUp(self):
        _guard(self)
        self.dir = tempfile.mkdtemp(prefix='lm2settle_')
        self.c = TestClient(create_app(db_path=os.path.join(self.dir, 'lm2.db'), password=PW, secret=SECRET,
                                       sig_fetch=lambda: SIGS))
        self.cmd('session.start', names=['하율', '서아', '채원'])

    def tearDown(self):
        self.c.app.state.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def cmd(self, t, **data):
        r = self.c.post('/api/cmd', json={'type': t, 'data': data}, headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def don(self, amount, tx, **kw):
        r = self.c.post('/api/donation', json=dict({'name': '별빛', 'amount': amount, 'message': '', 'tx_id': tx}, **kw), headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json().get('id')

    def settle(self):
        r = self.c.get('/api/ledger/settle', headers=H)
        self.assertEqual(r.status_code, 200, r.text)
        b = r.json()
        self.assertEqual(b['status'], 'success')
        return b['settle']

    def test_login_needed(self):
        self.assertEqual(self.c.get('/api/ledger/settle').status_code, 401)

    def test_live_flow(self):
        a = self.don(15000, 'toon_s1')
        b = self.don(6000, 'toon_s2')
        c = self.don(50000, 'toon_s3')
        d = self.don(20000, 'toon_s4')
        self.don(3000, 'toon_s5', display_only=True)                 # 화면에만(1만 원 미만)
        self.don(90000, 'toon_s6', replay=True)                      # 🔁 다시 보기 — 화면에만
        t = self.don(30000, 'toon_t2_s7')                            # 🧪 투네이션 테스트 — 대기함에 들어오지만 실제 돈 아님
        self.cmd('pending.assign', id=a, name='하율')
        self.cmd('pending.assign', id=b, names=['서아', '채원'])     # 나눠 주기 — 1점을 나눠도 후원 하나는 1점
        self.cmd('pending.ignore', id=d)
        self.cmd('pending.assign', id=t, name='하율')
        s = self.settle()
        self.assertEqual(s['real'], 15000 + 6000 + 50000 + 20000)
        self.assertEqual(s['scored'], (1 + 1 + 3) * 10000)
        w = why(s)
        self.assertEqual(w['cut'], (5000, 1))
        self.assertEqual(w['up'], (-4000, 1))
        self.assertEqual(w['pending'], (50000, 1))
        self.assertEqual(w['ignored'], (20000, 1))
        self.assertEqual(w['test'], (-30000, 1))
        self.assertEqual(sum(x['won'] for x in s['why']), s['diff'])
        self.assertEqual(s['hand'], {'won': 0, 'n': 0})
        # 숫자 카드 ① '이번 방송 후원' 합계와 💱 '실제 받은 돈' 은 같은 셈(🧪 테스트 · 화면에만 · 다시 보기 빼고) — 대표님 눈에 두 숫자가 달라 보이지 않게
        b = self.c.get('/api/ai/board?today=1', headers=H).json()['today']
        self.assertEqual((b['합계금액'], b['건수']), (s['real'], s['real_n']))
        self.assertEqual(b['가장_큰'], {'이름': '별빛', '금액': 50000})      # 테스트 30,000 · 다시 보기 90,000 은 '가장 큰 후원' 이 못 된다
        # 되돌리면 그 후원은 대기함으로 — 점수에서 빠지고 '대기함' 까닭으로 옮겨 간다
        self.cmd('score.undo', ref=a)
        s2 = self.settle()
        self.assertEqual(s2['scored'], (1 + 3) * 10000)
        self.assertEqual(why(s2)['pending'], (65000, 2))
        self.assertEqual(why(s2)['cut'], (0, 0))
        self.assertEqual(sum(x['won'] for x in s2['why']), s2['diff'])
        self.assertTrue(c)                                            # 안 고른 후원은 그대로 대기함


if __name__ == '__main__':
    unittest.main()
