# -*- coding: utf-8 -*-
"""🤖 무인 방송(autopilot) — 그림자 · 켬 · 채점 · 되돌리기 · AI 길(예약 + 명령 밖) · 금액 게임 · 검사 · 숫자.

⚠️ 진짜 NVIDIA 는 절대 부르지 않는다 — ai._http_post 를 '부르면 실패' 로 막고, AI 를 쓰는 검사만 ai.nim_post 를 가짜로 바꾼다.
⚠️ 서버가 스스로 부르는 명령(ctx.later)은 대부분 붙잡아 두었다가 drain() 으로 하나씩 돌린다(같은 /api/cmd 길 —
   PREFETCH 도 진짜로 다른 갈래에서 돈다). 진짜 예약이 도는지는 RealTimers 가 따로 본다.
돌리기(저장소 루트에서): python -m unittest v2.tests.test_autopilot
"""
import contextlib
import os
import shutil
import tempfile
import threading
import time
import types
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from v2.server import bus as busmod
from v2.server.domain import ai
from v2.server.domain import autopilot as apm
from v2.server.app import create_app
from v2.tests.test_ai import FakeNim, FakeResp, _no_network
from v2.tests.test_flow import Base, H, PW, SECRET, SIGS

FAKE_KEY = 'test-key-not-real'


@contextlib.contextmanager
def clock(t):
    """명령이 보는 지금 시각(ctx.now)을 t 초로 — bus 모듈의 time 만 바꾼다(test_roulette 과 같다)."""
    with mock.patch('v2.server.bus.time', types.SimpleNamespace(time=lambda: t)):
        yield


def _ai_guard(case, key=''):
    """바깥 호출 막기 · 키(기본: 없음 = AI 꺼짐) · 기억 · 한도 · 상태 비우기."""
    for p in (mock.patch.object(ai, '_http_post', _no_network),
              mock.patch.object(ai, 'nim_key', lambda: key),
              mock.patch.object(ai, 'NIM_HEALTH', {'ok': None, 'ms': 0, 'at': 0.0, 'model': '', 'code': 0}),
              mock.patch.object(ai, '_nim_calls', [])):
        p.start()
        case.addCleanup(p.stop)
    ai._SUGGEST_CACHE.clear()
    case.addCleanup(ai._SUGGEST_CACHE.clear)


class AutoBase(Base):
    MODE = 'shadow'
    KEY = ''

    def setUp(self):
        _ai_guard(self, self.KEY)
        self.timers = []
        rec = self.timers

        def later(ctx_self, sec, type_, data=None):
            rec.append((float(sec), type_, dict(data or {})))
        p = mock.patch.object(busmod.Ctx, 'later', later)
        p.start()
        self.addCleanup(p.stop)
        super().setUp()                                   # 앱 · 방송 시작(하율 · 서아 · 채원)
        c, r = self.cmd('auto.set', mode=self.MODE)
        self.assertEqual(c, 200, r)

    # ── 도구 ──
    def drain(self, keep=()):
        """붙잡아 둔 auto.* 예약을 차례로 돌린다(돌리다 생긴 예약까지). keep 에 든 이름은 남겨 둔다."""
        ran, left = [], []
        for _ in range(60):
            if not self.timers:
                break
            sec, t, d = self.timers.pop(0)
            if not t.startswith('auto.') or t in keep:
                left.append((sec, t, d))
                continue
            c, r = self.cmd(t, **d)
            self.assertEqual(c, 200, (t, r))
            ran.append((t, r))
        self.timers[:0] = left
        return ran

    def take(self, type_):
        """그 이름의 예약 하나를 꺼낸다(없으면 None)."""
        for i, (sec, t, d) in enumerate(self.timers):
            if t == type_:
                return self.timers.pop(i)
        return None

    def ap(self):
        return self.st()['autopilot']

    def item(self, pid):
        return next((x for x in self.st()['pending'] if x['id'] == pid), None)

    def row(self, pid):
        return next(r for r in self.ap()['log'] if r['id'] == pid)

    def stats(self, scope='session'):
        return self.ap()['stats'][scope]

    def give(self, name, amount, msg='', tx=None):
        tx = tx or 'toon_%s' % time.time_ns()
        c, r = self.don(name, amount, tx, msg)
        self.assertEqual(c, 200, r)
        return r['id']


# ══ 그림자 ══
class Shadow(AutoBase):
    def test_default_mode_and_off(self):
        self.assertEqual(apm._default()['mode'], 'off')                            # 검사 꾸러미는 off 로 시작(tests/__init__.py)
        with mock.patch.dict(os.environ, {'LM2_AUTOPILOT': ''}):
            self.assertEqual(apm._default()['mode'], 'shadow')                     # 운영 기본은 그림자
        self.cmd('auto.set', mode='off')
        pid = self.give('별빛', 30000, '서아 화이팅')
        self.assertNotIn('auto', self.item(pid))
        self.assertEqual(self.timers, [])
        self.assertEqual(self.stats()['n'], 0)

    def test_records_but_never_assigns(self):
        pid = self.give('별빛', 30000, '서아 화이팅')
        it = self.item(pid)
        self.assertTrue(it['auto']['asking'])                                       # 같은 쪽지에 '판단 중' — 조종실이 AI 를 따로 안 묻는다
        self.assertEqual([t for _, t, _ in self.timers], ['auto.decide'])
        self.drain()
        it = self.item(pid)
        a = it['auto']
        self.assertEqual((a['target'], a['tier'], a['confidence'], a['source'], a['act'], a['mode']),
                         ('서아', 'auto', 0.97, '이름', True, 'shadow'))
        self.assertNotIn('asking', a)
        self.assertNotIn('held', a)
        self.assertEqual(self.player('서아')['score'], 0)                            # ⭐ 그림자는 절대 안 준다
        row = self.row(pid)
        self.assertEqual((row['outcome'], row['target'], row['name'], row['amount']), ('pending', '서아', '별빛', 30000))
        self.assertEqual(self.stats()['n'], 1)
        # 조종실 배지(/api/audit/suggest)는 같은 답을 기억에서 — AI 를 또 안 부른다
        r = self.c.post('/api/audit/suggest', json={'id': pid}, headers=H).json()
        self.assertEqual((r['target'], r['tier'], r.get('cached')), ('서아', 'auto', True))

    def test_human_scoring(self):
        d1 = self.give('a', 10000, '서아 화이팅')
        d2 = self.give('b', 10000, '하율 최고')
        d3 = self.give('c', 10000, '오늘도 응원해요')
        d4 = self.give('d', 10000, '채원 가자')
        d5 = self.give('e', 10000, '좋은 밤')
        d6 = self.give('f', 20000, '하율 사랑해')
        d7 = self.give('g', 20000, '서아 짱')
        self.drain()
        self.assertEqual(self.item(d3)['auto']['held'], 'unsure')
        self.assertIn('AI 가 꺼져 있음', self.item(d3)['auto']['why'])               # 키 없음 = AI 꺼짐(LM2_AI_OFF 와 같은 길)
        self.cmd('pending.assign', id=d1, name='서아')
        self.cmd('pending.assign', id=d2, name='채원')
        self.cmd('pending.assign', id=d3, name='하율')
        self.cmd('pending.ignore', id=d4)
        self.cmd('pending.ignore', id=d5)
        self.cmd('pending.assign', id=d6, names=['하율', '서아'])
        self.cmd('pending.assign', id=d7, names=['하율', '채원'])
        got = {pid: (self.row(pid)['outcome'], self.row(pid).get('human')) for pid in (d1, d2, d3, d4, d5, d6, d7)}
        self.assertEqual(got, {d1: ('agree', '서아'), d2: ('disagree', '채원'), d3: ('unknown', '하율'),
                               d4: ('disagree', '무시함'), d5: ('ignored', '무시함'),
                               d6: ('agree', '하율 · 서아'), d7: ('disagree', '하율 · 채원')})
        self.assertTrue(self.row(d6)['split'])
        want = {'n': 7, 'agree': 2, 'disagree': 3, 'unknown': 1, 'ignored': 1, 'auto_done': 0, 'auto_undone': 0, 'games': 0}
        self.assertEqual(self.stats(), want)
        self.assertEqual(self.stats('total'), want)

    def test_undo_takes_back_the_verdict(self):
        pid = self.give('별빛', 20000, '서아 화이팅')
        self.drain()
        self.cmd('pending.assign', id=pid, name='서아')
        self.assertEqual(self.stats()['agree'], 1)
        c, r = self.cmd('score.undo', ref=pid)
        self.assertEqual(c, 200, r)
        self.assertEqual(self.stats()['agree'], 0)                                  # 판정을 뺐다
        it = self.item(pid)
        self.assertTrue(it['returned'])
        self.assertEqual((it['auto']['target'], it['auto']['held'], it['auto']['undone']), ('서아', 'returned', 1))
        self.assertEqual(self.row(pid)['outcome'], 'pending')
        self.cmd('pending.assign', id=pid, name='하율')                             # 다시 줄 때 다시 센다
        self.assertEqual((self.row(pid)['outcome'], self.stats()['disagree'], self.stats()['n']), ('disagree', 1, 1))

    def test_jar_test_donation_and_client_autopilot(self):
        d1 = self.give('a', 30000, '채원 가자')
        d2 = self.give('b', 30000, '하율 가자')
        d3 = self.give('시험', 30000, '서아 가자', tx='toon_t2_x1')                  # 리스너 시험 후원
        self.drain()
        self.cmd('pending.to_jar', id=d1)                                           # 🏺 고리 밖의 길 — 장부 상태로 가른다
        self.assertEqual((self.row(d1)['outcome'], self.row(d1)['human']), ('disagree', '🏺 모금함'))
        self.cmd('pending.assign', id=d2, name='하율', via='ap')                     # 조종실 🚗 — 사람 판단이 아니다
        self.assertEqual((self.row(d2)['outcome'], self.row(d2)['by']), ('auto', 'ap'))
        self.assertEqual(self.item(d3)['auto']['held'], 'test')
        self.cmd('pending.assign', id=d3, name='서아')
        self.assertEqual(self.row(d3)['outcome'], 'agree')
        s = self.stats()
        self.assertEqual((s['n'], s['disagree'], s['auto_done'], s['agree']), (2, 1, 1, 0))     # 시험 후원은 안 센다

    def test_lost_timer_after_restart_is_rescued(self):
        with clock(1000.0):
            pid = self.give('별빛', 30000, '서아 화이팅')
        self.timers.clear()                                                         # 서버를 다시 켜 예약이 사라졌다
        self.assertTrue(self.item(pid)['auto']['asking'])
        with clock(1030.0):
            p2 = self.give('달빛', 10000, '하율 최고')                                # 30초 — 아직 기다린다
        self.assertEqual([d['id'] for _, t, d in self.timers if t == 'auto.decide'], [p2])
        self.timers.clear()
        with clock(1200.0):
            p3 = self.give('햇빛', 10000, '채원 사랑해')                              # 묵었다 → 다음 후원 때 다시 판단에 건다
        self.assertEqual(sorted(d['id'] for _, t, d in self.timers if t == 'auto.decide'), sorted([pid, p2, p3]))
        self.drain()
        self.assertEqual(self.item(pid)['auto']['target'], '서아')
        self.assertNotIn('asking', self.row(pid))

    def test_hook_failure_never_blocks_donation(self):
        with mock.patch.object(apm, 'match_game', side_effect=RuntimeError('boom')):
            c, r = self.don('별빛', 30000, 'toon_boom', '서아')
        self.assertEqual((c, r['status']), (200, 'success'))
        self.assertEqual(len(self.st()['pending']), 1)

    def test_no_players_no_decision(self):
        self.cmd('players.remove', name='하율')
        self.cmd('players.remove', name='서아')
        self.cmd('players.remove', name='채원')
        pid = self.give('별빛', 30000, '서아')
        self.assertNotIn('auto', self.item(pid))
        self.assertEqual(self.timers, [])


# ══ 켬 ══
class On(AutoBase):
    MODE = 'on'

    def test_assigns_only_sure_and_current(self):
        d1 = self.give('별빛', 30000, '서아 화이팅')
        d2 = self.give('달빛', 20000, '오늘도 응원해요')
        d3 = self.give('햇빛', 20000, '서아화이팅이에요')                            # 글자만 겹침 — 0.75 추천(사람)
        self.cmd('players.remove', name='채원')
        d4 = self.give('눈빛', 20000, '채원 화이팅')                                 # 지금 판에 없는 사람
        ran = self.drain()
        self.assertEqual(ran[0][1].get('auto_assigned'), '서아')
        s = self.st()
        self.assertEqual(self.player('서아', s)['score'], 3)
        self.assertEqual([x['id'] for x in s['pending']], [d2, d3, d4])
        self.assertEqual({x['id']: x['auto']['held'] for x in s['pending']}, {d2: 'unsure', d3: 'unsure', d4: 'unsure'})
        self.assertEqual(s['pending'][1]['auto']['target'], '서아')
        row = self.row(d1)
        self.assertEqual((row['outcome'], row['by'], row['human']), ('auto', 'auto', '서아'))
        self.assertEqual(s['logs'][0]['by'], 'auto')                                # 점수 기록 줄에도 '자동'
        self.assertEqual(self.store_status(d1), ('assigned', '서아'))
        self.assertEqual(self.stats()['auto_done'], 1)
        # 보류된 것을 사람이 주면 '몰라서 보류' 로 센다
        self.cmd('pending.assign', id=d2, name='하율')
        self.assertEqual((self.row(d2)['outcome'], self.stats()['unknown']), ('unknown', 1))

    def store_status(self, pid):
        d = self.c.app.state.store.donation(pid)
        return d['status'], d['player']

    def test_undone_is_never_auto_assigned_again(self):
        pid = self.give('별빛', 30000, '서아 화이팅')
        self.drain()
        self.assertEqual(self.player('서아')['score'], 3)
        self.cmd('score.undo', ref=pid)
        it = self.item(pid)
        self.assertTrue(it['returned'])
        self.assertEqual((it['auto']['held'], it['auto']['was_auto']), ('returned', True))
        self.assertEqual(self.stats()['auto_undone'], 1)
        c, r = self.cmd('auto.decide', id=pid)                                     # 늦게 온 판단(재시도 등)이 와도
        self.assertEqual(c, 200, r)
        self.drain()
        it = self.item(pid)
        self.assertIsNotNone(it)                                                    # ⭐ 대기함에 그대로
        self.assertEqual(it['auto']['held'], 'returned')
        self.assertEqual(self.player('서아')['score'], 0)
        self.cmd('pending.assign', id=pid, name='서아')                             # 사람이 같은 사람에게 → 기계가 맞았다
        self.assertEqual(self.row(pid)['outcome'], 'agree')

    def test_test_donation_and_failed_assign_are_held(self):
        t = self.give('시험', 30000, '서아 가자', tx='toon_t2_y')
        self.drain()
        self.assertEqual(self.item(t)['auto']['held'], 'test')
        pid = self.give('별빛', 30000, '하율 화이팅')
        # 판단 직전에 그 선수가 빠졌다 — pending.assign 이 거절하면 그 부분만 없던 일로 하고 보류
        with mock.patch.object(apm.dn, 'pending_assign', side_effect=apm.CommandError('없는 선수: 하율', 404)):
            self.drain()
        it = self.item(pid)
        self.assertEqual((it['auto']['held'], it['auto']['held_err']), ('failed', '없는 선수: 하율'))
        self.assertEqual(self.player('하율')['score'], 0)
        self.assertEqual(self.stats()['auto_done'], 0)


# ══ AI 길 — 예약 + 명령 밖(PREFETCH) ══
class AiPath(AutoBase):
    KEY = FAKE_KEY

    def test_ai_runs_outside_and_caches(self):
        seen = {}

        def fake(models, body, timeout):
            seen['thread'] = threading.current_thread().name
            seen['prompt'] = body['messages'][0]['content']
            return FakeResp(200, '{"target": "채원", "confidence": 0.97}'), 200, models[0]
        with mock.patch.object(ai, 'nim_post', side_effect=fake) as m:
            pid = self.give('별빛', 20000, '오늘도 응원해요')
            ran = self.drain()
            self.assertEqual([t for t, _ in ran], ['auto.decide', 'auto.ai'])
            self.assertEqual(m.call_count, 1)
            self.assertTrue(seen['thread'].startswith('asyncio'), seen)               # 명령 갈래가 아니라 다른 갈래
            self.assertIn('선수: 하율, 서아, 채원', seen['prompt'])
            a = self.item(pid)['auto']
            self.assertEqual((a['target'], a['tier'], a['confidence'], a['source'], a['held']), ('채원', 'suggest', 0.88, 'AI', 'unsure'))
            r = self.c.post('/api/audit/suggest', json={'id': pid}, headers=H).json()
            self.assertEqual((r['target'], r.get('cached')), ('채원', True))
            self.assertEqual(m.call_count, 1)                                        # 배지는 기억에서 — AI 를 또 안 부른다

    def test_ai_busy_retries_later(self):
        with mock.patch.object(ai, 'nim_post', FakeNim((None, 503, ai.NIM_MODEL_BACKUP))):
            pid = self.give('별빛', 20000, '오늘도 응원해요')
            sec, t, d = self.timers.pop(0)
            self.cmd(t, **d)                                                          # auto.decide
            sec, t, d = self.timers.pop(0)
            self.cmd(t, **d)                                                          # auto.ai (붐빔)
        a = self.item(pid)['auto']
        self.assertEqual((a['target'], a['held'], a['retry']), (None, 'retry', True))
        self.assertIn('AI 서버가 붐빕니다', a['why'])
        self.assertEqual(self.timers, [(20.0, 'auto.decide', {'id': pid, 'attempt': 1})])
        self.assertNotIn(ai._ck('별빛', 20000, '오늘도 응원해요', ['하율', '서아', '채원']), ai._SUGGEST_CACHE)
        with mock.patch.object(ai, 'nim_post', FakeNim((FakeResp(200, '{"target": "하율", "confidence": 0.8}'), 200, 'm'))):
            self.drain()
        a = self.item(pid)['auto']
        self.assertEqual((a['target'], a.get('retry'), a['held']), ('하율', None, 'unsure'))
        self.assertEqual(self.stats()['n'], 1)                                       # 다시 물어도 한 건

    def test_use_ai_off_and_key_off(self):
        self.cmd('auto.set', use_ai=False)
        with mock.patch.object(ai, 'nim_post', FakeNim()) as f:
            pid = self.give('별빛', 20000, '오늘도 응원해요')
            self.drain()
        self.assertEqual(f.calls, [])
        self.assertIn('AI 에게 안 묻기로 함', self.item(pid)['auto']['why'])
        self.cmd('auto.set', use_ai=True)
        with mock.patch.object(ai, 'nim_key', lambda: ''), mock.patch.object(ai, 'nim_post', FakeNim()) as f:
            pid = self.give('달빛', 20000, '좋은 밤')
            ran = self.drain()
        self.assertEqual([t for t, _ in ran], ['auto.decide'])                       # LM2_AI_OFF(키 없음) — AI 단계로 안 간다
        self.assertEqual(f.calls, [])
        self.assertIn('AI 가 꺼져 있음', self.item(pid)['auto']['why'])

    def test_human_first_while_asking(self):
        with mock.patch.object(ai, 'nim_post', FakeNim((FakeResp(200, '{"target": "채원", "confidence": 0.9}'), 200, 'm'))):
            pid = self.give('별빛', 20000, '오늘도 응원해요')
            self.cmd('pending.assign', id=pid, name='서아')                          # 판단 전에 사람이 먼저
            ran = self.drain()
        self.assertTrue(ran[0][1].get('gone'))
        row = self.row(pid)
        self.assertEqual((row['outcome'], row['early']), ('unknown', True))
        self.assertNotIn('asking', row)


# ══ 금액 게임 ══
RULES = [{'min': 50000, 'max': 0, 'game': 'roulette'}, {'min': 20000, 'max': 49999, 'game': 'dice'},
         {'min': 10000, 'max': 19999, 'game': 'slot'}]


class GamesShadow(AutoBase):
    def test_shadow_only_logs(self):
        c, r = self.cmd('auto.games', rules=RULES)
        self.assertEqual(c, 200, r)
        d1 = self.give('a', 50000, '')
        d2 = self.give('b', 15000, '')
        d3 = self.give('c', 30000, '서아')
        self.drain()
        self.assertEqual(self.row(d1)['game']['status'], 'would')
        self.assertEqual(self.row(d1)['game']['text'], '이 후원이면 룰렛을 돌렸을 거예요')
        self.assertEqual(self.item(d1)['auto']['game']['game'], 'roulette')          # 카드에도 보인다
        self.assertEqual(self.row(d2)['game']['text'], '이 후원이면 슬롯을 돌렸을 거예요')
        s = self.st()
        self.assertEqual((s['roulette']['phase'], s['slot']['phase'], s['show']['stage']), ('idle', 'idle', None))
        self.assertEqual(self.stats()['games'], 3)
        self.cmd('pending.assign', id=d3, name='서아')
        self.assertEqual(self.row(d3)['game']['text'], '이 후원이면 주사위판이 무대에 없어서 안 굴렸을 거예요')
        self.cmd('dice.setup')                                                       # 주사위판을 무대에
        d4 = self.give('d', 30000, '하율')
        self.drain()
        self.cmd('pending.assign', id=d4, name='하율')
        self.assertEqual(self.row(d4)['game']['text'], '이 후원이면 하율 말을 굴렸을 거예요')
        self.assertNotEqual(self.st()['dicegame']['action'].get('type'), 'ROLL')       # 그림자는 안 굴린다

    def test_disabled_and_first_match(self):
        self.cmd('auto.games', rules=[{'min': 10000, 'max': 0, 'game': 'roulette', 'on': False},
                                      {'min': 10000, 'max': 0, 'game': 'slot'}, {'min': 10000, 'max': 0, 'game': 'dice'}])
        pid = self.give('a', 10000, '')
        self.assertEqual(self.row(pid)['game']['game'], 'slot')
        self.assertIsNone(apm.match_game(self.ap()['games'], 9999))


class GamesOn(AutoBase):
    MODE = 'on'

    def test_roulette_spins_and_stops(self):
        self.cmd('auto.games', rules=RULES)
        pid = self.give('a', 50000, '')
        self.assertEqual(sorted(t for _, t, _ in self.timers), ['auto.decide', 'auto.roulette'])
        self.drain(keep=('auto.roulette_stop',))
        s = self.st()
        self.assertEqual((s['roulette']['phase'], s['show']['stage']), ('spinning', 'roulette'))
        self.assertEqual(self.row(pid)['game']['status'], 'spin')
        sec, t, d = self.take('auto.roulette_stop')
        self.assertEqual((sec, d['round']), (apm.ROULETTE_STOP_SEC, s['roulette']['round']))
        self.cmd(t, **d)
        s = self.st()
        self.assertEqual(s['roulette']['phase'], 'stopping')
        g = self.row(pid)['game']
        self.assertEqual((g['status'], g['result']), ('done', s['roulette']['stop']['name']))
        self.assertEqual(self.stats()['games'], 1)
        c, r = self.cmd(t, **d)                                                      # 두 번 와도 한 번
        self.assertTrue(r.get('ignored'))

    def test_roulette_skips_when_busy_or_other_stage(self):
        self.cmd('auto.games', rules=RULES)
        self.cmd('show.stage', stage='quiz')
        p1 = self.give('a', 50000, '')
        self.drain()
        self.assertEqual(self.row(p1)['game']['text'], "무대에 '퀴즈' 판이 올라가 있어서 룰렛을 안 돌렸어요")
        self.assertEqual(self.st()['roulette']['phase'], 'idle')
        self.cmd('show.stage', stage=None)
        self.cmd('roulette.spin')
        p2 = self.give('b', 60000, '')
        self.drain(keep=('auto.roulette_stop',))
        self.assertEqual(self.row(p2)['game']['text'], '룰렛이 이미 돌고 있어서 룰렛을 안 돌렸어요')
        self.assertEqual(self.stats()['games'], 0)

    def test_slot_uses_signatures_from_outside(self):
        self.cmd('auto.games', rules=RULES)
        pid = self.give('a', 15000, '')
        self.drain()
        s = self.st()
        self.assertEqual((s['slot']['phase'], s['show']['stage']), ('spinning', 'slot'))
        title = s['slot']['winner']['title']
        self.assertIn(title, [x['title'] for x in SIGS])
        self.assertEqual(self.row(pid)['game']['text'], '슬롯을 돌렸어요 — 당첨: %s' % title)

    def test_dice_rolls_for_receiver(self):
        self.cmd('auto.games', rules=RULES)
        self.cmd('dice.setup', roll_price=20000)
        d1 = self.give('a', 20000, '서아 화이팅')                                   # 자동으로 서아에게 → 서아 말
        self.drain()
        g = self.st()['dicegame']
        self.assertEqual((g['action']['type'], g['action']['piece']), ('ROLL', '서아'))
        self.assertEqual(self.row(d1)['game']['status'], 'done')
        d2 = self.give('b', 30000, '오늘도 응원해요')                                # 보류 → 사람이 하율에게 → 하율 말
        self.drain()
        self.cmd('pending.assign', id=d2, name='하율')
        sec, t, d = self.take('auto.dice')
        self.cmd(t, **d)                                                             # 앞 굴림 연출 중 — 429 → 조금 뒤 다시 예약
        self.assertEqual(self.row(d2)['game']['status'], 'wait')
        sec, t, d = self.take('auto.dice')
        self.assertEqual((sec, d['attempt']), (apm.DICE_RETRY_SEC, 1))
        with clock(time.time() + 60):
            self.cmd(t, **d)
        g = self.st()['dicegame']
        self.assertEqual(g['action']['piece'], '하율')
        self.assertEqual(self.stats()['games'], 2)
        d3 = self.give('c', 20000, '오늘도')                                          # 나눠 주기 — 굴리지 않는다
        self.drain()
        self.cmd('pending.assign', id=d3, names=['하율', '서아'])
        self.assertEqual(self.row(d3)['game']['text'], '나눠 줘서 주사위를 안 굴렸어요')

    def test_dice_below_price_and_off_stage(self):
        self.cmd('auto.games', rules=[{'min': 10000, 'max': 0, 'game': 'dice'}])
        self.cmd('dice.setup', roll_price=20000)
        p1 = self.give('a', 10000, '서아 화이팅')
        self.drain()
        self.assertEqual(self.row(p1)['game']['text'], '한 판 값(20,000원)보다 적어서 주사위를 안 굴렸어요')
        self.cmd('show.stage', stage=None)
        p2 = self.give('b', 30000, '서아 화이팅')
        self.drain()
        self.assertEqual(self.row(p2)['game']['text'], '주사위판이 무대에 없어서 주사위를 안 굴렸어요')


# ══ 검사 · 숫자 ══
class Commands(AutoBase):
    def test_games_validation(self):
        bad = [
            ({'rules': 'x'}, '줄 목록'),
            ({'rules': [{'min': 1, 'game': 'roulette'}] * 21}, '20개'),
            ({'rules': [{'min': 1, 'game': 'bingo'}]}, '1번째 줄: 게임은'),
            ({'rules': [{'min': 10000001, 'game': 'slot'}]}, '0 ~ 10,000,000원'),
            ({'rules': [{'min': -1, 'game': 'slot'}]}, '0 ~ 10,000,000원'),
            ({'rules': [{'min': '1만', 'game': 'slot'}]}, '숫자가 아닙니다'),
            ({'rules': [{'min': True, 'game': 'slot'}]}, '숫자가 아닙니다'),
            ({'rules': [{'min': 1.5, 'game': 'slot'}]}, '정수'),
            ({'rules': [{'game': 'slot'}]}, '최소 금액이 숫자가 아닙니다'),
            ({'rules': [{'min': 5000, 'max': 3000, 'game': 'dice'}]}, '최대 금액이 최소보다 작습니다'),
            ({'rules': [{'min': 1, 'game': 'dice'}, 7]}, '2번째 줄이 이상합니다'),
        ]
        for data, msg in bad:
            c, r = self.cmd('auto.games', **data)
            self.assertEqual(c, 400, data)
            self.assertIn(msg, r['error'], data)
        self.assertEqual(self.ap()['games'], [])                                      # 하나라도 틀리면 아무것도 안 바뀐다
        c, r = self.cmd('auto.games', rules=[{'id': 'a1', 'min': '50,000', 'max': '', 'game': 'roulette'},
                                             {'id': 'a1', 'min': 0, 'max': 10000000, 'game': 'dice', 'on': False}])
        self.assertEqual(c, 200, r)
        g = self.ap()['games']
        self.assertEqual([(x['min'], x['max'], x['game'], x['on']) for x in g], [(50000, 0, 'roulette', True), (0, 10000000, 'dice', False)])
        self.assertEqual(g[0]['id'], 'a1')
        self.assertNotEqual(g[1]['id'], 'a1')                                         # 겹친 번호는 새로
        self.assertEqual(self.cmd('auto.games', rules=[])[0], 200)
        self.assertEqual(self.ap()['games'], [])

    def test_set_and_reset_validation(self):
        for data, msg in (({}, '바꿀 것'), ({'mode': 'auto'}, '모드는'), ({'use_ai': 'yes'}, 'use_ai'),):
            c, r = self.cmd('auto.set', **data)
            self.assertEqual(c, 400, data)
            self.assertIn(msg, r['error'])
        c, r = self.cmd('auto.set', mode='on', use_ai=False)
        self.assertEqual((c, r['mode'], r['use_ai']), (200, 'on', False))
        self.assertEqual(self.cmd('auto.reset_stats', scope='all')[0], 400)
        self.assertEqual(self.c.post('/api/cmd', json={'type': 'auto.set', 'data': {'mode': 'on'}}).status_code, 401)   # 로그인 필요

    def test_off_clears_asking(self):
        pid = self.give('별빛', 20000, '서아')
        self.assertTrue(self.item(pid)['auto']['asking'])
        self.cmd('auto.set', mode='off')
        self.assertNotIn('auto', self.item(pid))
        ran = self.drain()                                                            # 예약된 판단이 와도 아무것도 안 한다
        self.assertTrue(ran[0][1].get('skipped'))
        self.assertNotIn('auto', self.item(pid))

    def test_session_stats_reset(self):
        pid = self.give('별빛', 20000, '서아')
        self.drain()
        self.cmd('pending.assign', id=pid, name='서아')
        self.assertEqual((self.stats()['agree'], self.stats('total')['agree']), (1, 1))
        self.cmd('session.end')
        self.cmd('session.start', names=['하율', '서아'])
        self.assertEqual(self.stats(), apm._zero())                                   # 이번 방송은 0 으로
        self.assertEqual(self.stats('total')['agree'], 1)                             # 전체는 남는다
        self.assertEqual(self.row(pid)['outcome'], 'agree')                           # 기록 줄도 남는다
        self.cmd('auto.reset_stats', scope='total')
        self.assertEqual(self.stats('total'), apm._zero())


# ══ 진짜 예약(ctx.later → loop.call_later)이 도는지 — 붙잡지 않는다 ══
class RealTimers(unittest.TestCase):
    def setUp(self):
        _ai_guard(self)
        self.dir = tempfile.mkdtemp(prefix='lm2auto_')
        self.c = TestClient(create_app(db_path=os.path.join(self.dir, 'lm2.db'), password=PW, secret=SECRET, sig_fetch=lambda: SIGS))
        self.c.__enter__()                                     # 루프를 계속 살려 둔다(요청마다 닫지 않게) — 예약이 진짜로 돈다

    def tearDown(self):
        self.c.__exit__(None, None, None)
        self.c.app.state.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def cmd(self, t, **data):
        return self.c.post('/api/cmd', json={'type': t, 'data': data}, headers=H).json()

    def wait(self, pred, sec=5.0):
        t0 = time.time()
        while time.time() - t0 < sec:
            s = self.c.get('/api/state', headers=H).json()['slices']
            if pred(s):
                return s
            time.sleep(0.05)
        self.fail('시간 안에 안 됐다')

    def test_shadow_then_on_with_real_timers(self):
        self.cmd('session.start', names=['하율', '서아'])
        self.cmd('auto.set', mode='shadow')
        r = self.c.post('/api/donation', json={'name': '별빛', 'amount': 30000, 'message': '서아 화이팅', 'tx_id': 'toon_rt1'}, headers=H).json()
        s = self.wait(lambda s: (s['pending'][0].get('auto') or {}).get('target') == '서아')
        self.assertEqual(s['pending'][0]['id'], r['id'])
        self.cmd('auto.set', mode='on')
        self.c.post('/api/donation', json={'name': '달빛', 'amount': 20000, 'message': '하율 최고', 'tx_id': 'toon_rt2'}, headers=H)
        s = self.wait(lambda s: next(p for p in s['players']['list'] if p['name'] == '하율')['score'] == 2)
        self.assertEqual([x['id'] for x in s['pending']], [r['id']])                # 그림자 때 판단한 것은 그대로(소급하지 않는다)
        self.assertEqual(s['autopilot']['stats']['session']['auto_done'], 1)


if __name__ == '__main__':
    unittest.main()
