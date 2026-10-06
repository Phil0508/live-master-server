# -*- coding: utf-8 -*-
"""v2 룰렛 — 서버가 [정지] 때 칸 · 각도를 정한다 · 선관위는 비공개 · 판 번호 문지기 · 잠깐 무대.

돌리기(저장소 루트에서): python -m unittest v2.tests.test_roulette
"""
import contextlib
import json
import random
import types
import unittest
from unittest import mock

from v2.server.domain import roulette as rl          # ⚠️ 앱을 만들기 전에 불러야 조각 · 명령이 등록된다
from v2.tests.test_flow import Base

T0 = 1800000000.0                                     # 검사용 시계(초)


@contextlib.contextmanager
def clock(t):
    """명령이 보는 지금 시각(ctx.now)을 t 초로 — bus 모듈의 time 만 바꾼다."""
    with mock.patch('v2.server.bus.time', types.SimpleNamespace(time=lambda: t)):
        yield


def items(*pairs):
    return [{'name': n, 'w': w} for n, w in pairs]


class Decide(unittest.TestCase):
    """순수 함수 decide — 칸 · 각도 · 감속 시간."""

    def test_equal_slices_and_edge(self):
        it = items(('A', 1), ('B', 1), ('C', 1), ('D', 1))            # 90° 씩 · 경계 여유 min(16.2, 6) = 6°
        for seed in range(300):
            i, a, d, picked = rl.decide(it, random.Random(seed))
            self.assertTrue(i * 90 + 6 <= a <= i * 90 + 84, (seed, i, a))
            self.assertTrue(3850 <= d <= 4350, d)
            self.assertFalse(picked)

    def test_same_seed_same_result(self):
        it = items(('하율', 5), ('채원', 3), ('서아', 1))
        self.assertEqual(rl.decide(it, random.Random(42)), rl.decide(it, random.Random(42)))

    def test_weighted_distribution(self):
        it = items(('하율', 5), ('서아', 1), ('채원', 3))              # 기대 5/9 · 1/9 · 3/9
        n, cnt = 3000, [0, 0, 0]
        for seed in range(n):
            cnt[rl.decide(it, random.Random(seed))[0]] += 1
        for c, e in zip(cnt, (5 / 9, 1 / 9, 3 / 9)):
            self.assertAlmostEqual(c / n, e, delta=0.03)

    def test_narrow_slice_edge(self):
        it = items(('a', 1), ('b', 29))                                  # a = 12° → 여유 18% = 2.16°
        for seed in range(100):
            i, a, _, picked = rl.decide(it, random.Random(seed), pick='a')
            self.assertEqual((i, picked), (0, True))
            self.assertTrue(2.16 - 1e-6 <= a <= 9.84 + 1e-6, a)
            i, a, _, _ = rl.decide(it, random.Random(seed), pick='b')     # b = 348° → 여유 6°
            self.assertEqual(i, 1)
            self.assertTrue(18 <= a <= 354, a)

    def test_pick_duplicates_and_missing(self):
        it = items(('꽝', 1), ('커피', 1), ('꽝', 1))
        got = {rl.decide(it, random.Random(s), pick='꽝')[0] for s in range(60)}
        self.assertEqual(got, {0, 2})                                    # 같은 이름이 여럿이면 그중에서
        i, _, _, picked = rl.decide(it, random.Random(1), pick='없는칸')
        self.assertFalse(picked)                                         # 판에 없으면 무작위


class Roulette(Base):
    def ro(self, auth=True):
        return self.st(auth)['roulette']

    def ops(self):
        return self.st()['roulette_ops']

    def done(self, rnd):
        """방송판처럼 로그인 없이 '다 섰다'."""
        r = self.c.post('/api/cmd', json={'type': 'roulette.done', 'data': {'round': rnd}})
        return r.status_code, r.json()

    # ── 한 판 흐름 ──
    def test_spin_stop_done(self):
        self.cmd('show.stage', stage='match')
        with clock(T0):
            c, r = self.cmd('roulette.spin')
        self.assertEqual((c, r['round']), (200, 1), r)
        ro = self.ro(auth=False)
        self.assertEqual((ro['phase'], ro['spin_at'], ro['stop']), ('spinning', int(T0 * 1000), None))
        self.assertEqual(ro['items'], items(('하율', 1), ('서아', 1), ('채원', 1)))
        sh = self.st()['show']
        self.assertEqual((sh['stage'], sh['ret']), ('roulette', 'match'))            # 잠깐 무대 — 돌아갈 곳을 기억
        self.assertTrue(self.cmd('roulette.spin')[1].get('already'))                 # 두 번 눌러도 한 판
        self.assertEqual(self.ro()['round'], 1)
        with clock(T0 + 5):
            c, r = self.cmd('roulette.stop', seed=7)
        self.assertEqual(c, 200, r)
        st = self.ro()['stop']
        at = int((T0 + 5) * 1000)
        self.assertEqual((st['at'], st['ends_at'] - st['at'], self.ro()['phase']), (at, st['duration_ms'], 'stopping'))
        self.assertTrue(3850 <= st['duration_ms'] <= 4350)
        self.assertEqual(st['name'], ['하율', '서아', '채원'][st['index']])
        self.assertTrue(st['index'] * 120 + 6 <= st['angle'] <= st['index'] * 120 + 114)   # 120° 칸 · 여유 6°
        self.assertEqual((r['name'], r['ends_at']), (st['name'], st['ends_at']))
        self.assertEqual(rl.decide(items(('하율', 1), ('서아', 1), ('채원', 1)), random.Random(7))[:3],
                         (st['index'], st['angle'], st['duration_ms']))             # 같은 씨앗 → 같은 결과
        h = self.ops()['history'][0]
        self.assertEqual((h['round'], h['name'], h['picked']), (1, st['name'], False))   # [정지] 때 바로 확정
        self.assertTrue(self.cmd('roulette.stop')[1].get('already'))
        # 방송판 보고 — 판 번호 · 시각 문지기
        with clock((st['ends_at'] - 1001) / 1000.0):
            self.assertEqual(self.done(1)[0], 409)                                 # 1.001초 남음 — 이르다
        with clock((st['ends_at'] + 5000) / 1000.0):
            self.assertTrue(self.done(2)[1].get('ignored'))                        # 다른 판
            self.assertTrue(self.done('x')[1].get('ignored'))
        with clock((st['ends_at'] - 1000) / 1000.0):
            c, r = self.done(1)                                                    # 1초 여유 안 — 받는다
        self.assertEqual(c, 200, r)
        self.assertFalse(r.get('ignored'))
        self.assertEqual(self.ro()['phase'], 'done')
        sh = self.st()['show']
        self.assertEqual((sh['stage'], sh['ret']), ('match', None))                # 원래 무대로
        self.assertTrue(self.done(1)[1].get('ignored'))                            # 두 번째 창의 보고는 무시
        self.assertEqual(self.ops()['history'][0]['name'], st['name'])             # 결과는 그대로

    def test_stop_needs_spin_and_spin_waits_while_stopping(self):
        self.assertEqual(self.cmd('roulette.stop')[0], 409)                        # 안 도는데 정지
        self.cmd('show.stage', stage='dicegame')
        with clock(T0):
            self.cmd('roulette.spin')
        with clock(T0 + 1):
            self.cmd('roulette.stop', seed=3)
        ends = self.ro()['stop']['ends_at']
        with clock((ends - 1) / 1000.0):
            c, r = self.cmd('roulette.spin')
        self.assertEqual(c, 409)                                                   # 서는 중엔 다시 못 돌린다
        self.assertIn('서는 중', r['error'])
        with clock(ends / 1000.0):
            c, r = self.cmd('roulette.spin')                                       # 아무도 done 을 안 보냈어도 — 지난 판을 닫고 새 판
        self.assertEqual((c, r['round']), (200, 2))
        sh = self.st()['show']
        self.assertEqual((sh['stage'], sh['ret']), ('roulette', 'dicegame'))
        self.assertTrue(self.done(1)[1].get('ignored'))                            # 지난 판의 늦은 보고

    # ── 선관위 ──
    def test_pick_is_private_and_wins(self):
        c, r = self.cmd('roulette.pick', name='서아')
        self.assertEqual(c, 200, r)
        self.assertEqual(self.ops()['pick'], '서아')
        pub = self.st(auth=False)
        self.assertNotIn('roulette_ops', pub)
        self.assertNotIn('pick', json.dumps(pub['roulette'], ensure_ascii=False))
        t = T0
        for seed in range(6):
            with clock(t):
                self.cmd('roulette.spin')
            with clock(t + 1):
                c, r = self.cmd('roulette.stop', seed=seed)
            self.assertEqual(r['name'], '서아')
            st = self.ro(auth=False)['stop']
            self.assertEqual((st['index'], st['name']), (1, '서아'))
            self.assertTrue(126 <= st['angle'] <= 234)                             # 서아 칸 120~240° · 여유 6°
            self.assertNotIn('picked', json.dumps(self.ro(auth=False), ensure_ascii=False))   # 조작 여부는 방송판에 없다
            t += 10
        self.assertEqual([h['picked'] for h in self.ops()['history']], [True] * 6)
        self.assertEqual(self.ops()['pick'], '서아')                                # 판이 끝나도 남는다(옛 것과 같다)
        self.cmd('roulette.pick', name=None)
        self.assertIsNone(self.ops()['pick'])
        self.assertEqual(self.cmd('roulette.pick', name='없는사람')[0], 404)

    def test_pick_while_spinning_and_stopping(self):
        with clock(T0):
            self.cmd('roulette.spin')
        self.cmd('roulette.pick', name='채원')                                      # 도는 중 — 이번 판에 든다
        with clock(T0 + 1):
            self.assertEqual(self.cmd('roulette.stop')[1]['name'], '채원')
        c, r = self.cmd('roulette.pick', name='하율')                               # 이미 정해짐 — 다음 판부터
        self.assertTrue(r.get('next_round'))
        self.assertEqual(self.ro()['stop']['name'], '채원')

    # ── 칸 · 넓이 ──
    def test_contrib_weights_frozen_on_spin(self):
        self.cmd('score.add', name='하율', delta=5)
        self.cmd('score.add', name='채원', delta=3)
        self.cmd('roulette.config', weight='contrib')
        with clock(T0):
            self.cmd('roulette.spin')
        self.assertEqual(self.ro()['items'], items(('하율', 5), ('채원', 3), ('서아', 1)))   # 기여도 0 → 넓이 1
        self.cmd('score.add', name='서아', delta=10)                                 # 도는 중 점수가 바뀌어도
        self.cmd('roulette.config', weight='equal')                                  # 설정이 바뀌어도
        self.assertEqual(self.ro()['items'], items(('하율', 5), ('채원', 3), ('서아', 1)))   # 이번 판 칸은 그대로
        with clock(T0 + 1):
            self.cmd('roulette.stop', seed=11)
        st = self.ro()['stop']
        lo, hi = {0: (0, 200), 1: (200, 320), 2: (320, 360)}[st['index']]           # 200° · 120° · 40°
        self.assertTrue(lo + 6 <= st['angle'] <= hi - 6, st)
        with clock(T0 + 10):
            self.cmd('roulette.spin')                                                # 다음 판은 새 설정 · 새 점수
        self.assertEqual(self.ro()['items'], items(('서아', 1), ('하율', 1), ('채원', 1)))

    def test_extra_list(self):
        self.cmd('score.add', name='하율', delta=7)                                  # 본판
        self.cmd('extra.start')
        self.cmd('score.add', name='서아', delta=4)                                  # 번외 판
        self.cmd('roulette.config', weight='contrib')
        with clock(T0):
            self.cmd('roulette.spin')
        self.assertEqual(self.ro()['items'], items(('서아', 4), ('하율', 1), ('채원', 1)))   # 번외 판으로 돈다

    def test_custom_config(self):
        self.cmd('roulette.config', weight='contrib')
        c, r = self.cmd('roulette.config', source='custom', custom='꽝\n  커피   쏘기 \n\n팔굽혀펴기 20개\n꽝')
        self.assertEqual(c, 200, r)
        ro = self.ro(auth=False)
        self.assertEqual((ro['source'], ro['weight']), ('custom', 'equal'))         # 직접 입력이면 같은 확률로
        self.assertEqual(ro['custom'], ['꽝', '커피 쏘기', '팔굽혀펴기 20개', '꽝'])      # 같은 이름은 남긴다
        self.assertEqual(self.cmd('roulette.config', weight='contrib')[0], 400)
        self.assertEqual(self.cmd('roulette.config', custom=[])[0], 400)
        self.assertEqual(self.cmd('roulette.config', custom=['  ', ''])[0], 400)
        self.assertEqual(self.cmd('roulette.config', custom=['칸%d' % i for i in range(31)])[0], 400)
        self.assertEqual(self.cmd('roulette.config', custom=5)[0], 400)
        self.assertEqual(self.cmd('roulette.config', source='zz')[0], 400)
        self.assertEqual(self.cmd('roulette.config', source='bj', weight='zz')[0], 400)
        self.assertEqual(self.ro()['source'], 'custom')                              # 실패한 명령은 아무것도 안 바꾼다
        self.assertEqual(self.cmd('roulette.config', custom=['칸%d' % i for i in range(30)])[0], 200)    # 30칸까지는 된다
        self.assertEqual(len(self.ro()['custom']), 30)
        self.cmd('roulette.config', custom=['A' * 50, 'B'])
        self.assertEqual(self.ro()['custom'], ['A' * 30, 'B'])                       # 30자까지
        with clock(T0):
            self.cmd('roulette.spin')
        self.assertEqual(self.ro()['items'], items(('A' * 30, 1), ('B', 1)))
        self.cmd('roulette.config', custom=['C'])
        self.assertEqual(self.ro()['items'], items(('A' * 30, 1), ('B', 1)))         # 도는 판은 그대로

    def test_empty_wheel(self):
        self.cmd('session.end')
        c, r = self.cmd('roulette.spin')
        self.assertEqual(c, 409)
        self.assertIn('비어', r['error'])
        self.cmd('roulette.config', source='custom')                                 # 기본 벌칙 1~5 로는 돈다
        self.assertEqual(self.cmd('roulette.spin')[0], 200)
        self.assertEqual([x['name'] for x in self.ro()['items']], ['벌칙 %d' % i for i in range(1, 6)])

    # ── 초기화 · 방송 시작/끝 ──
    def test_reset(self):
        self.cmd('show.stage', stage='match')
        with clock(T0):
            self.cmd('roulette.spin')
        self.cmd('roulette.pick', name='하율')
        with clock(T0 + 1):
            self.cmd('roulette.stop')
        self.cmd('roulette.reset')
        ro = self.ro()
        self.assertEqual((ro['phase'], ro['items'], ro['stop'], ro['round']), ('idle', [], None, 1))
        self.assertIsNone(self.ops()['pick'])
        self.assertTrue(self.ops()['history'][0]['cancelled'])                      # 서는 중에 거둔 판
        self.assertEqual(self.st()['show']['stage'], 'match')                        # 도는 중 초기화 → 원래 무대로
        self.assertTrue(self.done(1)[1].get('ignored'))
        self.cmd('show.stage', stage='roulette')                                     # 판만 띄워 둔 것(돌리기 전)
        self.cmd('roulette.reset')
        self.assertEqual(self.st()['show']['stage'], 'roulette')                     # 쉬는 중 초기화는 무대를 안 건드린다

    def test_session_resets_round_keeps_config(self):
        self.cmd('roulette.config', source='custom', custom=['꽝', '커피'])
        self.cmd('roulette.pick', name='꽝')
        with clock(T0):
            self.cmd('roulette.spin')
        with clock(T0 + 1):
            self.cmd('roulette.stop')
        self.cmd('session.end')
        ro, ops = self.ro(), self.ops()
        self.assertEqual((ro['phase'], ro['items'], ro['stop']), ('idle', [], None))
        self.assertEqual(ops, {'pick': None, 'history': []})
        self.assertEqual((ro['source'], ro['custom']), ('custom', ['꽝', '커피']))      # 설정은 남는다
        self.assertIsNone(self.st()['show']['stage'])
        self.cmd('session.start', names=['가', '나'])
        with clock(T0 + 100):
            self.assertEqual(self.cmd('roulette.spin')[1]['round'], 2)              # 판 번호는 이어서 센다

    def test_auth(self):
        for t, d in (('roulette.spin', {}), ('roulette.stop', {}), ('roulette.pick', {'name': '하율'}),
                     ('roulette.config', {'source': 'custom'}), ('roulette.reset', {})):
            r = self.c.post('/api/cmd', json={'type': t, 'data': d})
            self.assertEqual(r.status_code, 401, t)
        c, r = self.done(0)
        self.assertEqual(c, 200)                                                     # 방송판은 로그인 없이 보고만
        self.assertTrue(r.get('ignored'))
        self.assertEqual(self.ro()['phase'], 'idle')


if __name__ == '__main__':
    unittest.main()
