# -*- coding: utf-8 -*-
"""v2 옛 설정 옮겨 오기 — 옛 조종실 [백업] 파일 모양 그대로 넣어 본다."""
import unittest

from v2.tests.test_flow import Base

OLD = {
    'account': {'bank': '국민', 'acc_num': '464-068673-04-016', 'name': '엔젤컴퍼니'},
    'target_goal': 1000, 'theme': 'pink', 'donor_rank_anon': True,
    'notice_msgs': ['계좌로 보내실 때 닉네임 적어 주세요', '  ', '10시 스페셜'], 'notice_period': 120, 'notice_speed': 999,
    'home_goals': {'하율': 30, '서아': 0},
    'quiz': {'custom': {'chosung': [['떡볶이', '음식'], ['x']], 'idiom': [['일석이조', '한 번에 둘']]}},
    'account_video_tiers': [{'min': 200000, 'label': '20만', 'video': 'https://v/a.mp4'}],
    'fundjar': {'name': '모금함', 'enabled': True, 'seed': 300000, 'score': 999},
    'bottom_fixed': {'name': '운영비', 'score': 77},
    'roulette': {'custom_items': ['벌칙 A', '벌칙 B'], 'item_source': 'custom', 'weight_type': 'contrib'},
    'slot_price': 30000, 'slot_pool': [1, 2],
    'show': {'hud': {'best': True, 'nope': True}, 'alerts': {'small': False}},
    'bjs': [{'name': '하율', 'score': 50}],              # 점수는 안 옮긴다
}


class Migrate(Base):
    def test_import(self):
        c, r = self.cmd('admin.import_old', state=OLD)
        self.assertEqual(c, 200, r)
        s = self.st()
        self.assertEqual(s['account']['bank'], '국민')
        self.assertEqual((s['goal']['target'], s['look']['theme']), (1000, 'rose'))
        self.assertEqual(s['notice']['msgs'], ['계좌로 보내실 때 닉네임 적어 주세요', '10시 스페셜'])
        self.assertEqual((s['notice']['period'], s['notice']['speed']), (120, 400))
        self.assertEqual(s['home']['goals'], {'하율': 30})
        self.assertEqual(s['quiz_ops']['custom']['chosung'], [['떡볶이', '음식']])
        self.assertEqual(s['fundjar']['score'], 0)                              # 후원분은 안 옮긴다
        self.assertEqual((s['fundjar']['seed'], s['fundjar']['enabled']), (300000, True))
        self.assertEqual(s['players']['bottom']['score'], 0)
        self.assertEqual((s['roulette']['custom'], s['roulette']['source'], s['roulette']['weight']), (['벌칙 A', '벌칙 B'], 'custom', 'contrib'))
        self.assertEqual((s['slot_ops']['price'], s['slot_ops']['pool']), (30000, ['1', '2']))
        self.assertTrue(s['show']['hud']['best'])
        self.assertFalse(s['show']['alerts']['small'])
        self.assertEqual(self.player('하율', s)['score'], 0)
        self.assertIn('계좌', r['imported'])

    def test_bad(self):
        self.assertEqual(self.cmd('admin.import_old', state='x')[0], 400)
        self.assertEqual(self.cmd('admin.import_old', state={'random': 1})[0], 400)


if __name__ == '__main__':
    unittest.main()
