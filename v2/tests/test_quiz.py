# -*- coding: utf-8 -*-
"""v2 퀴즈판 — 옛 tests/quiz_test.py 의 핵심을 옮김. 정답 · 순서가 방송판으로 안 새는 것이 제일 중요하다."""
import json
import unittest

from v2.tests.test_flow import Base


class Quiz(Base):
    def test_next_hint_reveal_and_privacy(self):
        c, r = self.cmd('quiz.next', kind='chosung', seed=1)
        self.assertEqual(c, 200, r)
        s = self.st()
        cur = s['quiz_ops']['cur']
        self.assertTrue(cur['answer'])
        self.assertEqual(s['show']['stage'], 'quiz')
        self.assertTrue(all(t['s'] in ('q', 'g') for t in s['quiz']['tiles']))
        pub = self.st(auth=False)
        self.assertNotIn('quiz_ops', pub)
        self.assertNotIn(cur['answer'], json.dumps(pub, ensure_ascii=False))       # ⭐ 정답이 방송판에 없다
        self.cmd('quiz.hint')
        self.assertEqual(self.st()['quiz']['tiles'][0], {'c': cur['answer'][0], 's': 'h'})
        self.cmd('quiz.reveal')
        q = self.st()['quiz']
        self.assertTrue(q['revealed'])
        self.assertEqual(''.join(t['c'] for t in q['tiles']), cur['answer'])

    def test_order_edit(self):
        self.cmd('quiz.prepare', seed=2)
        o = self.st()['quiz_ops']['order']['chosung']
        self.cmd('quiz.order', kind='chosung', action='top', answer=o[5])
        o2 = self.st()['quiz_ops']['order']['chosung']
        self.assertEqual(o2[0], o[5])
        self.cmd('quiz.next', kind='chosung')
        self.assertEqual(self.st()['quiz_ops']['cur']['answer'], o[5])
        self.assertNotIn(o[5], self.st()['quiz_ops']['order']['chosung'])
        self.assertEqual(self.cmd('quiz.order', kind='chosung', action='up', answer='없는말')[0], 404)

    def test_now(self):
        c, r = self.cmd('quiz.now', kind='chosung', text=' 떡 볶이 ')
        self.assertEqual([t['c'] for t in self.st()['quiz']['tiles']], ['ㄸ', 'ㅂ', 'ㅇ'])
        c, r = self.cmd('quiz.now', kind='chosung', text='ㅅㄱㅁㅅ')
        self.assertTrue(r['jamo_only'])
        self.assertEqual(self.cmd('quiz.hint')[0], 400)
        c, r = self.cmd('quiz.now', kind='idiom', text='일석이조')
        self.assertEqual([t['s'] for t in self.st()['quiz']['tiles']], ['g', 'g', 'b', 'b'])
        self.assertEqual(self.cmd('quiz.now', text='abc')[0], 400)
        self.assertEqual(self.cmd('quiz.now', text='가' * 13)[0], 400)

    def test_custom(self):
        c, r = self.cmd('quiz.custom', kind='chosung', text='검사순서 | 검사\nx\n')
        self.assertEqual((r['added'], len(r['bad'])), (1, 1))
        self.cmd('quiz.prepare')
        self.assertEqual(self.st()['quiz_ops']['order']['chosung'][-1], '검사순서')
        c, r = self.cmd('quiz.custom', kind='chosung', mode='clear')
        self.assertEqual(r['cleared'], 1)
        self.assertNotIn('검사순서', self.st()['quiz_ops']['order']['chosung'])

    def test_session_reset_keeps_custom(self):
        self.cmd('quiz.custom', kind='idiom', text='가나다라 | 시험')
        self.cmd('quiz.next', kind='chosung')
        self.cmd('session.end')
        s = self.st()
        self.assertEqual(s['quiz']['tiles'], [])
        self.assertIsNone(s['quiz_ops']['cur'])
        self.assertEqual(len(s['quiz_ops']['custom']['idiom']), 1)


if __name__ == '__main__':
    unittest.main()


class QuizBankAndPicks(unittest.TestCase):
    """게임 탭 도우미가 찾은 구멍 — 기본 문제 뜻 · 시그뒤집기 고른 번호 · 핀볼 밀어내기 기본값."""

    def setUp(self):
        from v2.tests.test_flow import Base
        self.b = Base()
        self.b.setUp()

    def tearDown(self):
        self.b.tearDown()

    def test_bank_route(self):
        from v2.tests.test_flow import H
        r = self.b.c.get('/api/quiz/bank', headers=H).json()
        self.assertTrue(r['bank']['chosung'] and r['bank']['idiom'])
        self.assertEqual(len(r['bank']['idiom'][0]), 2)
        self.assertEqual(self.b.c.get('/api/quiz/bank').status_code, 401)

    def test_picks_visible_to_controller_only(self):
        from v2.tests.test_flow import H
        sigs = [{'id': 1, 'title': 'A', 'image_url': '', 'amount': 10000}, {'id': 2, 'title': 'B', 'image_url': '', 'amount': 20000}]
        self.b.cmd('sig.picks', picks=[2, 1], sigs=sigs)
        st = self.b.c.get('/api/state', headers=H).json()['slices']
        self.assertEqual(st['siggame_picks']['ids'], [2, 1])
        self.assertNotIn('siggame_deck', st)                                   # 카드 속은 여전히 숨김
        self.assertNotIn('siggame_picks', self.b.c.get('/api/state').json()['slices'])   # 방송판(무인증)엔 안 간다

    def test_pinball_push_default_on(self):
        from v2.tests.test_flow import H
        st = self.b.c.get('/api/state', headers=H).json()['slices']
        self.assertTrue(st['pinball']['skills'])
