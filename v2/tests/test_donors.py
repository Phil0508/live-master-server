# -*- coding: utf-8 -*-
"""v2 특별 후원자 등급 · 순위에서 빼기."""
import unittest

from v2.tests.test_flow import Base, H


class Donors(Base):
    def test_vip_ranks_with_ties(self):
        for i, (n, a) in enumerate((('가', 50000), ('나', 50000), ('다', 30000), ('라', 20000))):
            self.don(n, a, 'toon_v%d' % i)
        v = self.st(auth=False)['tallies']['vip']
        self.assertEqual({k: (x['rank'], x['grade']) for k, x in v.items()},
                         {'가': (1, 'VVIP'), '나': (1, 'VVIP'), '다': (3, 'VIP'), '라': (4, 'DIAMOND')})

    def test_exclude_include(self):
        self.don('운영자', 100000, 'toon_e1')
        self.don('별빛', 30000, 'toon_e2')
        self.cmd('donor.exclude', name='운영자님')
        t = self.st()['tallies']
        self.assertNotIn('운영자', t['donors'])
        self.assertEqual(t['best']['name'], '별빛')                       # 한 방 최고도 다음 사람
        self.assertEqual(t['vip']['별빛']['rank'], 1)
        self.don('운영자', 5000, 'manual_e3')                              # 뺀 뒤 들어온 것도 안 센다
        self.assertNotIn('운영자', self.st()['tallies']['donors'])
        self.cmd('donor.include', name='운영자')
        t = self.st()['tallies']
        self.assertEqual(t['donors']['운영자']['total'], 105000)          # 장부에서 다시 센다
        self.assertEqual(t['best']['name'], '운영자')
        self.assertNotIn('donor_rules', self.st(auth=False))


if __name__ == '__main__':
    unittest.main()


class ManualVip(Base):
    """직접 준 등급(옛 vip_donators) — 순위에 못 든 사람에게만."""

    def test_manual_only_outside_top10(self):
        for i in range(10):
            self.don('후원%02d' % i, 100000 - i * 1000, 'toon_mv%d' % i)
        self.don('작은손', 1000, 'toon_mvx')
        self.cmd('vip.set', name='작은손님', grade='diamond')
        self.cmd('vip.set', name='후원00', grade='BRONZE')               # 이미 1위 — 순위 등급이 이긴다
        v = self.st()['tallies']['vip']
        self.assertEqual((v['작은손']['grade'], v['작은손']['rank'], v['작은손']['manual']), ('DIAMOND', 0, True))
        self.assertEqual(v['작은손']['color'], '#5ac8fa')
        self.assertEqual(v['후원00']['grade'], 'VVIP')
        self.cmd('vip.set', name='아직안옴', grade='VIP')                  # 후원 전이어도 등급은 있다
        self.assertEqual(self.st()['tallies']['vip']['아직안옴']['total'], 0)
        self.cmd('donor.exclude', name='작은손')
        self.assertNotIn('작은손', self.st()['tallies']['vip'])            # 순위에서 뺀 이름엔 안 붙인다
        self.cmd('vip.remove', name='아직안옴')
        self.assertNotIn('아직안옴', self.st()['tallies']['vip'])

    def test_bad_grade(self):
        r = self.c.post('/api/cmd', json={'type': 'vip.set', 'data': {'name': '가', 'grade': 'KING'}}, headers=H).json()
        self.assertFalse(r['ok'])
