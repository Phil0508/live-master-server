# -*- coding: utf-8 -*-
"""⏰ 예약(ctx.later)이 서버를 다시 켜도 살아남는지 (sturdy 10-17).

전에는 예약이 메모리(loop.call_later)에만 있어서, 방송 중 서버가 다시 켜지면(감시 장치 · 버전 바꾸기) 룰렛 · 슬롯이 끝나도
무대가 안 돌아오고(게임 화면에 멈춤), 시그뒤집기 까보기가 안 덮였다. 이제 예약은 명령과 같은 묶음으로 장부(timers)에 적히고,
다시 켜지면 남은 시간대로 다시 걸리며, 지난 것은 바로 불린다. 부른 명령과 같은 묶음에서 지워져 두 번 불리지 않는다.
'다시 켜기' 는 같은 장부 파일로 Bus 를 새로 만드는 것으로 흉내 낸다(run_sync 는 예약을 적기만 하고 걸지 않는다 = 걸기 전에 꺼졌다).
"""
import asyncio
import os
import shutil
import tempfile
import time
import types
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from v2.server import bus as busmod
from v2.server import domain  # noqa: F401  (조각 · 명령 등록)
from v2.server.app import create_app
from v2.server.bus import Bus, CommandError, command
from v2.server.state import slice_
from v2.server.store import Store

slice_('t_sturdy_timer', False, lambda: {'n': 0, 'log': []})


@command('t_sturdy.arm')
def _t_arm(ctx, data):
    for tag in (data.get('tags') or [data.get('tag', 'x')]):
        ctx.later(float(data.get('sec', 0.1)), 't_sturdy.tick', {'tag': tag})
    ctx.edit('t_sturdy_timer')['armed'] = True
    if data.get('fail'):
        raise CommandError('일부러 실패')        # 실패한 명령의 예약은 장부에 안 남는다


@command('t_sturdy.tick')
def _t_tick(ctx, data):
    tag = data.get('tag')
    if tag == 'bad':
        raise CommandError('거절')
    if tag == 'boom':
        raise RuntimeError('넘어짐')
    t = ctx.edit('t_sturdy_timer')
    t['n'] += 1
    t['log'].append(tag)


class Timers(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2tim_')
        self.path = os.path.join(self.dir, 'lm2.db')
        self.stores = []

    def tearDown(self):
        for s in self.stores:
            try:
                s.close()
            except Exception:
                pass
        shutil.rmtree(self.dir, ignore_errors=True)

    def bus(self):
        s = Store(self.path)
        self.stores.append(s)
        return Bus(s)

    def restart(self, old):
        old.store.close()
        return self.bus()

    def t(self, b):
        return b.state.get('t_sturdy_timer')

    def test_written_with_command(self):
        b = self.bus()
        t0 = time.time()
        self.assertTrue(b.run_sync('t_sturdy.arm', {'sec': 5, 'tag': 'a'})['ok'])
        rows = b.store.timers()
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['type'], rows[0]['data']), ('t_sturdy.tick', {'tag': 'a'}))
        self.assertAlmostEqual(rows[0]['due'], t0 + 5, delta=1.0)

    def test_failed_command_leaves_no_timer(self):
        b = self.bus()
        self.assertFalse(b.run_sync('t_sturdy.arm', {'sec': 5, 'fail': True})['ok'])
        self.assertEqual(b.store.timers(), [])
        self.assertNotIn('armed', self.t(b))

    def test_fires_once_and_is_removed(self):
        b = self.bus()

        async def main():
            res = await b.run('t_sturdy.arm', {'sec': 0.05, 'tag': 'a'})
            self.assertTrue(res['ok'])
            await asyncio.sleep(0.4)
        asyncio.run(main())
        self.assertEqual((self.t(b)['n'], self.t(b)['log']), (1, ['a']))
        self.assertEqual(b.store.timers(), [])
        ev = [dict(r) for r in b.store.db.execute("SELECT type, by FROM events WHERE type = 't_sturdy.tick'")]
        self.assertEqual(ev, [{'type': 't_sturdy.tick', 'by': 'timer'}])
        b2 = self.restart(b)                      # 이미 부른 것은 다시 켜도 안 부른다

        async def again():
            self.assertEqual(b2.arm_timers(), {'due': 0, 'later': 0})
            await asyncio.sleep(0.1)
        asyncio.run(again())
        self.assertEqual(self.t(b2)['n'], 1)

    def test_restart_rearms_remaining_time(self):
        b = self.bus()
        b.run_sync('t_sturdy.arm', {'sec': 0.6, 'tag': 'a'})        # 걸기 전에 꺼졌다
        b2 = self.restart(b)

        async def main():
            self.assertEqual(b2.arm_timers(), {'due': 0, 'later': 1})
            await asyncio.sleep(0.2)
            self.assertEqual(self.t(b2)['n'], 0, '남은 시간 전에 불렀다')
            await asyncio.sleep(0.8)
        asyncio.run(main())
        self.assertEqual(self.t(b2)['log'], ['a'])
        self.assertEqual(b2.store.timers(), [])

    def test_restart_fires_past_due_in_order(self):
        b = self.bus()
        b.run_sync('t_sturdy.arm', {'sec': 30, 'tag': 'a'})
        b.run_sync('t_sturdy.arm', {'sec': 40, 'tag': 'b'})
        b.run_sync('t_sturdy.arm', {'sec': 3600, 'tag': 'later'})
        b2 = self.restart(b)
        real = time.time
        # 서버가 1분 동안 꺼져 있었다 — a · b 는 이미 지났다(장부 시각이 아니라 '지금' 을 옮긴다)
        with mock.patch.object(busmod, 'time', types.SimpleNamespace(time=lambda: real() + 60)):
            async def main():
                self.assertEqual(b2.arm_timers(), {'due': 2, 'later': 1})
                await asyncio.sleep(0.3)
            asyncio.run(main())
        self.assertEqual(self.t(b2)['log'], ['a', 'b'])
        self.assertEqual([r['data']['tag'] for r in b2.store.timers()], ['later'])

    def test_failing_timer_is_removed_and_others_still_fire(self):
        b = self.bus()
        b.run_sync('t_sturdy.arm', {'sec': 0, 'tags': ['bad', 'boom', 'ok']})
        b2 = self.restart(b)

        async def main():
            self.assertEqual(b2.arm_timers()['due'], 3)
            await asyncio.sleep(0.3)
        with mock.patch('builtins.print'):        # '예약 명령 실패' 한 줄 — 검사 출력만 조용히
            asyncio.run(main())
        self.assertEqual(self.t(b2)['log'], ['ok'])
        self.assertEqual(b2.store.timers(), [], '실패 · 넘어진 예약이 남아 켤 때마다 다시 불린다')

    def test_roulette_stage_comes_back_after_restart(self):
        """진짜 룰렛 — [정지] 뒤 서버가 꺼졌다 켜져도(서는 시간이 지난 뒤) 서버가 스스로 판을 닫고 무대를 돌려놓는다."""
        b = self.bus()
        self.assertTrue(b.run_sync('session.start', {'names': ['하율', '서아', '채원']})['ok'])
        self.assertTrue(b.run_sync('roulette.spin', {})['ok'])
        self.assertEqual(b.state.get('show')['stage'], 'roulette')
        res = b.run_sync('roulette.stop', {'seed': 7})
        self.assertTrue(res['ok'], res)
        rows = b.store.timers()
        self.assertEqual([r['type'] for r in rows], ['roulette.done'])
        self.assertEqual(rows[0]['data'], {'round': b.state.get('roulette')['round']})
        b2 = self.restart(b)
        self.assertEqual(b2.state.get('roulette')['phase'], 'stopping')
        real = time.time
        with mock.patch.object(busmod, 'time', types.SimpleNamespace(time=lambda: real() + 30)):
            async def main():
                self.assertEqual(b2.arm_timers()['due'], 1)
                await asyncio.sleep(0.3)
            asyncio.run(main())
        self.assertEqual(b2.state.get('roulette')['phase'], 'done')
        self.assertNotEqual(b2.state.get('show')['stage'], 'roulette')
        self.assertEqual(b2.store.timers(), [])

    def test_siggame_peek_is_covered_after_restart(self):
        """시그뒤집기 까보기 — 6초 뒤 덮기가 다시 켠 뒤에도 불린다."""
        b = self.bus()
        b.run_sync('session.start', {'names': ['하율']})
        sigs = [{'id': i, 'amount': 10000 + i, 'title': 's%d' % i, 'image_url': ''} for i in range(1, 5)]
        self.assertTrue(b.run_sync('sig.picks', {'picks': [1, 2, 3, 4], 'sigs': sigs})['ok'])
        self.assertTrue(b.run_sync('sig.deal', {'seed': 3})['ok'])
        res = b.run_sync('sig.peek', {})
        self.assertTrue(res['ok'], res)
        self.assertEqual([r['type'] for r in b.store.timers()], ['sig.peek_end'])
        b2 = self.restart(b)
        real = time.time
        with mock.patch.object(busmod, 'time', types.SimpleNamespace(time=lambda: real() + 10)):
            async def main():
                b2.arm_timers()
                await asyncio.sleep(0.3)
            asyncio.run(main())
        self.assertTrue(b2.state.get('siggame')['action'].get('closed'))


class AppBoot(unittest.TestCase):
    """서버 입구(app) — 켜질 때(lifespan) 장부에 남은 예약을 건다."""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2timapp_')
        self.path = os.path.join(self.dir, 'lm2.db')

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_lifespan_arms_timers(self):
        s = Store(self.path)
        b = Bus(s)
        b.run_sync('t_sturdy.arm', {'sec': 0, 'tag': 'boot'})
        s.close()
        app = create_app(db_path=self.path, password='pw', secret='s' * 32)
        H = {'Authorization': 'Bearer ' + 's' * 32}
        with mock.patch('builtins.print'):
            with TestClient(app) as c:
                deadline = time.time() + 3
                got = None
                while time.time() < deadline:
                    got = c.get('/api/state', headers=H).json()['slices']['t_sturdy_timer']
                    if got['n']:
                        break
                    time.sleep(0.05)
        app.state.store.close()
        self.assertEqual(got['log'], ['boot'])


if __name__ == '__main__':
    unittest.main()
