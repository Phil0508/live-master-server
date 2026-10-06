# -*- coding: utf-8 -*-
"""v2 슬롯머신 — 서버가 뽑는다 · 한 번에 한 판 · 당첨 시그는 릴이 선 뒤 재생 · 기여도 카드 = man_won(당첨 − 한 판 값).

돌리기(저장소 루트에서): python -m unittest v2.tests.test_slot
"""
import contextlib
import json
import types
import unittest
from unittest import mock

from v2.server.domain import roulette as rl          # noqa: F401  (룰렛 위에 슬롯 — 잠깐 무대 겹침 검사)
from v2.server.domain import slot as sl               # ⚠️ 앱을 만들기 전에 불러야 조각 · 명령 · 주소가 등록된다
from v2.tests.test_flow import SIGS, Base, H

T0 = 1800000000.0
MS0 = int(T0 * 1000)


@contextlib.contextmanager
def clock(t):
    """명령(ctx.now)과 /api/slot/spin 의 먼저 보기가 같은 시계를 쓰게 — 두 모듈의 time 만 바꾼다."""
    fake = types.SimpleNamespace(time=lambda: t)
    with mock.patch('v2.server.bus.time', fake), mock.patch('v2.server.domain.slot.time', fake):
        yield


class Pure(unittest.TestCase):
    def test_card_contrib(self):
        # man_won(당첨 − 한 판 값): 6천 원부터 1점 올림, 0 아래는 0
        self.assertEqual([sl.card_contrib(a, p) for a, p in ((50000, 20000), (10300, 20000), (20005, 20000), (25999, 20000),
                                                            (26000, 20000), (20005, 4000), (14000, 4000), (50000, 0))],
                         [3, 0, 0, 0, 1, 2, 1, 5])

    def test_candidates(self):
        self.assertEqual(sl.candidates(SIGS, []), (SIGS, False))
        self.assertEqual(sl.candidates(SIGS, ['3', '1']), ([SIGS[0], SIGS[2]], False))   # 목록 순서 그대로
        self.assertEqual(sl.candidates(SIGS, [3]), ([SIGS[2]], False))                    # 숫자 id 도
        self.assertEqual(sl.candidates(SIGS, ['999']), (SIGS, True))                     # 하나도 안 맞으면 전체


class Slot(Base):
    def sl_(self, auth=True):
        return self.st(auth)['slot']

    def spin(self, t, **data):
        with clock(t):
            return self.cmd('slot.spin', **dict({'sigs': SIGS}, **data))

    def done(self, rnd):
        r = self.c.post('/api/cmd', json={'type': 'slot.done', 'data': {'round': rnd}})
        return r.status_code, r.json()

    def cards(self):
        return [p for p in self.st()['pending'] if p.get('src') == 'slot']

    def test_spin_queue_and_card(self):
        self.cmd('slot.config', pool=[3])                                            # 대박(50,000원)만 후보
        c, r = self.spin(T0, seed=1)
        self.assertEqual(c, 200, r)
        s = self.sl_(auth=False)
        self.assertEqual((s['round'], s['phase'], s['spin_at'], s['ends_at']), (1, 'spinning', MS0, MS0 + 4000))
        self.assertEqual(s['winner'], {'id': 3, 'title': '대박', 'amount': 50000, 'image_url': 'c.png'})
        self.assertEqual(r['winner'], s['winner'])
        self.assertEqual(self.st()['show']['stage'], 'slot')
        # 당첨 시그 → 대기줄(팝업 없이 · 묶지 않고 · 릴이 선 뒤)
        q = self.st()['queue']['items'][-1]
        self.assertEqual((q['id'], q['title'], q['donator'], q['message'], q['amount'], q['audio_url'], q['duration']),
                         (r['queue_id'], '대박', '🎰 슬롯머신', '[슬롯 당첨] 대박', 50000, 'c.mp3', 12.0))
        self.assertEqual((q['skip_popup'], q['play_after'], q['count']), (True, MS0 + 4000, 1))
        self.assertEqual(self.st()['tallies']['sigs'], {})                           # 시그 순위에 안 센다
        self.assertIsNone(self.st()['popup']['donation'])                            # 후원 팝업 없음
        # 기여도 카드 — man_won(50,000 − 20,000) = 3
        cards = self.cards()
        self.assertEqual(len(cards), 1)
        cd = cards[0]
        self.assertEqual((cd['id'], cd['name'], cd['kind'], cd['contrib'], cd['amount'], cd['message'], cd['round'], cd['reveal_at']),
                         (r['card'], '🎰 슬롯 당첨', 'contrib', 3, 0, '대박 (50,000원 − 한 판 20,000원)', 1, MS0 + 4000))
        c, r2 = self.cmd('pending.assign', id=cd['id'], name='하율')
        self.assertEqual(c, 200, r2)
        p = self.player('하율')
        self.assertEqual((p['score'], p['contribution']), (0, 3))                    # 점수(일당)는 안 건드린다

    def test_card_by_price(self):
        t = T0
        for price, sid, want in ((20000, 1, 0), (20000, 2, 0), (4000, 2, 2), (4000, 1, 1), (0, 3, 5), (20000, 3, 3)):
            self.cmd('slot.config', price=price, pool=[sid])
            before = {x['id'] for x in self.cards()}
            c, r = self.spin(t)
            self.assertEqual((c, r['winner']['id']), (200, sid), r)
            got = [x['contrib'] for x in self.cards() if x['id'] not in before]
            self.assertEqual(got, [want] if want else [], (price, sid))
            self.assertEqual(r['card'] is None, not want)
            t += 10                                                                  # 지난 판이 끝난 뒤

    def test_server_picks_uniformly(self):
        seen = {}
        t = T0
        for seed in range(30):
            c, r = self.spin(t, seed=seed)
            seen[r['winner']['id']] = seen.get(r['winner']['id'], 0) + 1
            t += 10
        self.assertEqual(sorted(seen), [1, 2, 3])                                    # 셋 다 나온다
        a = sl.random.Random(5)
        self.assertEqual(self.spin(t, seed=5)[1]['winner']['id'], a.choice(SIGS)['id'])   # 같은 씨앗 → 같은 당첨

    def test_pool_missing_falls_back(self):
        self.cmd('slot.config', pool=['999'])
        c, r = self.spin(T0, seed=2)
        self.assertEqual(c, 200, r)
        self.assertTrue(r['pool_missing'])
        self.assertIn(r['winner']['id'], (1, 2, 3))

    def test_one_round_at_a_time_and_lazy_close(self):
        self.cmd('show.stage', stage='dicegame')
        self.spin(T0)
        sh = self.st()['show']
        self.assertEqual((sh['stage'], sh['ret']), ('slot', 'dicegame'))
        c, r = self.spin(T0 + 3.9)
        self.assertEqual(c, 409)
        self.assertIn('돌고 있어요', r['error'])
        self.assertEqual(self.sl_()['round'], 1)
        self.assertEqual(len(self.st()['queue']['items']), 1)                        # 실패한 판은 아무것도 안 남긴다
        c, r = self.spin(T0 + 4.0)                                                  # 아무도 done 을 안 보냈어도 — 지난 판을 닫고 새 판
        self.assertEqual((c, r['round']), (200, 2))
        sh = self.st()['show']
        self.assertEqual((sh['stage'], sh['ret']), ('slot', 'dicegame'))            # 돌아갈 곳은 그대로
        self.assertTrue(self.done(1)[1].get('ignored'))                             # 지난 판의 늦은 보고

    def test_done_gate(self):
        self.cmd('show.stage', stage='dicegame')
        self.spin(T0)
        with clock(T0 + 2.9):
            self.assertEqual(self.done(1)[0], 409)                                  # 1.1초 남음 — 이르다
        with clock(T0 + 10):
            self.assertTrue(self.done(2)[1].get('ignored'))
        with clock(T0 + 3.0):
            c, r = self.done(1)                                                     # 로그인 없이 · 1초 여유 안
        self.assertEqual(c, 200, r)
        self.assertFalse(r.get('ignored'))
        self.assertEqual(self.sl_()['phase'], 'done')
        sh = self.st()['show']
        self.assertEqual((sh['stage'], sh['ret']), ('dicegame', None))              # 원래 무대로
        self.assertTrue(self.done(1)[1].get('ignored'))                             # 두 번째 창은 무시
        self.assertEqual(len(self.st()['queue']['items']), 1)                       # 당첨 시그는 한 번만

    def test_manual_show_goes_down_after_round(self):
        self.cmd('show.stage', stage='slot')                                         # '띄우기'(기계만 미리 보여 주기)
        self.spin(T0)
        with clock(T0 + 4):
            self.done(1)
        self.assertIsNone(self.st()['show']['stage'])                               # 옛 것과 같다 — 당첨 뒤 내려간다

    def test_slot_over_roulette_keeps_first_return(self):
        self.cmd('show.stage', stage='match')
        with clock(T0):
            self.cmd('roulette.spin')
        self.spin(T0 + 1)
        sh = self.st()['show']
        self.assertEqual((sh['stage'], sh['ret']), ('slot', 'match'))               # 잠깐 위에 잠깐 — 처음 자리를 지킨다
        with clock(T0 + 5):
            self.done(1)
        self.assertEqual(self.st()['show']['stage'], 'match')

    def test_reel_and_privacy(self):
        many = [{'id': 100 + i, 'amount': 10000 + i * 1000, 'title': 'S%d' % i, 'image_url': 'i%d.png' % i,
                 'sound_url': 's%d.mp3' % i, 'duration': 5} for i in range(45)]
        c, r = self.spin(T0, sigs=many, seed=9)
        self.assertEqual(c, 200, r)
        s = self.sl_(auth=False)
        self.assertEqual(len(s['reel']), 30)                                        # 릴 채우기는 30개까지
        self.assertEqual(len({x['id'] for x in s['reel']}), 30)
        self.assertTrue(all(set(x) == {'id', 'title', 'amount', 'image_url'} for x in s['reel'] + [s['winner']]))
        self.assertTrue(1 <= s['seed'] < 2 ** 31)
        pub = self.st(auth=False)
        self.assertNotIn('slot_ops', pub)
        self.assertNotIn('pending', pub)
        self.assertNotIn('sound_url', json.dumps(pub['slot']))
        with clock(T0 + 10):
            self.cmd('session.end')
            self.cmd('session.start', names=['하율'])
        r2 = self.spin(T0 + 20, sigs=many, seed=9)[1]
        s2 = self.sl_()
        self.assertEqual((r2['winner'], s2['reel'], s2['seed']), (r['winner'], s['reel'], s['seed']))   # 같은 씨앗 → 같은 판

    def test_bad_sigs_and_config(self):
        self.assertEqual(self.spin(T0, sigs=[])[0], 400)
        c, r = self.spin(T0, sigs=[{'title': 'id 없음', 'amount': 1}, {'id': 9, 'amount': 'x'}, 'nope'])
        self.assertEqual((c, r['error']), (400, '등록된 시그니처가 없습니다.'))
        self.assertEqual(self.sl_()['phase'], 'idle')
        for bad in ({'price': -1}, {'price': 'abc'}, {'price': 10000001}, {'pool': '3'}, {'pool': [str(i) for i in range(501)]}):
            self.assertEqual(self.cmd('slot.config', **bad)[0], 400, bad)
        self.cmd('slot.config', price=30000, pool=[3, '3', ' 2 ', ''])
        self.assertEqual(self.st()['slot_ops'], {'price': 30000, 'pool': ['3', '2']})

    def test_session_keeps_settings(self):
        self.cmd('slot.config', price=30000, pool=[2])
        self.spin(T0)
        self.cmd('session.end')
        s = self.sl_()
        self.assertEqual((s['phase'], s['winner'], s['reel'], s['ends_at'], s['round']), ('idle', None, [], 0, 1))
        self.assertEqual(self.st()['slot_ops'], {'price': 30000, 'pool': ['2']})
        self.assertIsNone(self.st()['show']['stage'])
        self.assertTrue(self.done(1)[1].get('ignored'))

    def test_auth(self):
        for t, d in (('slot.spin', {'sigs': SIGS}), ('slot.config', {'price': 1})):
            self.assertEqual(self.c.post('/api/cmd', json={'type': t, 'data': d}).status_code, 401, t)
        self.assertTrue(self.done(0)[1].get('ignored'))                             # 방송판은 로그인 없이 보고만

    # ── 옛 주소 /api/slot/spin (조종실 · 폰) ──
    def test_route(self):
        self.assertEqual(self.c.post('/api/slot/spin', json={}).status_code, 401)
        with clock(T0):
            r = self.c.post('/api/slot/spin', json={'winner': SIGS[0]}, headers=H)  # 옛 winner 는 안 듣는다
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual((d['status'], d['round'], d['pool_missing']), ('success', 1, False))
        self.assertIn(d['winner']['id'], (1, 2, 3))
        self.assertEqual(self.sl_()['winner'], d['winner'])
        with clock(T0 + 2):
            r = self.c.post('/api/slot/spin', json={}, headers=H)
        self.assertEqual(r.status_code, 409)                                       # 목록 조회 전에 먼저 막는다
        self.assertEqual(r.json()['status'], 'error')
        self.cmd('slot.config', pool=[2])
        with clock(T0 + 4):
            d = self.c.post('/api/slot/spin', json={}, headers=H).json()
        self.assertEqual((d['round'], d['winner']['title']), (2, '뿅뿅'))


if __name__ == '__main__':
    unittest.main()
