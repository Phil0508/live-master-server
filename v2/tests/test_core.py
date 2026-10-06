# -*- coding: utf-8 -*-
"""v2 뼈대 — 장부 · 조각 · 명령 · 실시간 · 로그인 · 배포 잠금.

돌리기(저장소 루트에서):  python -m unittest discover -s v2/tests -t .
"""
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from v2.server.app import create_app
from v2.server.bus import CommandError, command
from v2.server.state import slice_

PW, SECRET = 'testpw', 'testsecret-0123456789'
BEARER = {'Authorization': 'Bearer ' + SECRET}

# 검사용 조각 · 명령 — 비공개 조각이 방송판으로 안 새는지 본다
slice_('t_secret', False, lambda: {'answer': ''})
slice_('t_public', True, lambda: {'n': 0})


@command('t.set')
def _t_set(ctx, data):
    if data.get('fail'):
        ctx.edit('t_public')['n'] = -999        # 바꿨다가
        raise CommandError('일부러 실패')        # 실패 → 되돌아가야 한다
    ctx.edit('t_secret')['answer'] = data.get('answer', '')
    ctx.edit('t_public')['n'] += 1


def make(db):
    return TestClient(create_app(db_path=db, password=PW, secret=SECRET))


class Core(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2test_')
        self.db = os.path.join(self.dir, 'lm2.db')
        self.c = make(self.db)

    def tearDown(self):
        self.c.app.state.store.close()
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_login(self):
        r = self.c.post('/api/cmd', json={'type': 't.set', 'data': {'answer': 'x'}})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.c.post('/login', json={'password': 'nope'}).status_code, 401)
        self.assertEqual(self.c.post('/login', json={'password': PW}).status_code, 200)
        r = self.c.post('/api/cmd', json={'type': 't.set', 'data': {'answer': 'x'}})
        self.assertEqual(r.status_code, 200, r.text)

    def test_bearer_and_unknown(self):
        r = self.c.post('/api/cmd', json={'type': 'nope.nope'}, headers=BEARER)
        self.assertEqual(r.status_code, 404)

    def test_failed_command_changes_nothing(self):
        seq0 = self.c.get('/api/state', headers=BEARER).json()['seq']
        r = self.c.post('/api/cmd', json={'type': 't.set', 'data': {'fail': True}}, headers=BEARER)
        self.assertEqual(r.status_code, 400)
        st = self.c.get('/api/state', headers=BEARER).json()
        self.assertEqual(st['seq'], seq0)
        self.assertEqual(st['slices']['t_public']['n'], 0)

    def test_public_private(self):
        self.c.post('/api/cmd', json={'type': 't.set', 'data': {'answer': '떡볶이'}}, headers=BEARER)
        pub = self.c.get('/api/state').json()
        self.assertNotIn('t_secret', pub['slices'])
        self.assertNotIn('떡볶이', str(pub))
        full = self.c.get('/api/state', headers=BEARER).json()
        self.assertEqual(full['slices']['t_secret']['answer'], '떡볶이')

    def test_session_and_deploy_lock(self):
        self.assertEqual(self.c.get('/api/deploy/ok').status_code, 200)
        self.assertEqual(self.c.post('/api/cmd', json={'type': 'session.start', 'data': {'names': ['하율', '서아']}}, headers=BEARER).status_code, 200)
        self.assertEqual(self.c.post('/api/cmd', json={'type': 'session.start', 'data': {'names': ['하율', '서아']}}, headers=BEARER).status_code, 409)
        self.assertEqual(self.c.get('/api/deploy/ok').status_code, 409)
        self.assertTrue(self.c.get('/health').json()['live'])
        self.assertEqual(self.c.post('/api/cmd', json={'type': 'session.end'}, headers=BEARER).status_code, 200)
        self.assertEqual(self.c.get('/api/deploy/ok').status_code, 200)

    def test_persist(self):
        self.c.post('/api/cmd', json={'type': 't.set', 'data': {'answer': 'a'}}, headers=BEARER)
        self.c.post('/api/cmd', json={'type': 'session.start', 'data': {'names': ['하율', '서아']}}, headers=BEARER)
        seq = self.c.get('/api/state', headers=BEARER).json()['seq']
        self.c.app.state.store.close()
        c2 = make(self.db)
        st = c2.get('/api/state', headers=BEARER).json()
        self.assertEqual(st['seq'], seq)
        self.assertTrue(st['slices']['session']['live'])
        self.assertEqual(st['slices']['t_public']['n'], 1)
        c2.app.state.store.close()
        self.c = make(self.db)

    def test_websocket(self):
        with self.c.websocket_connect('/ws?kind=overlay') as ov, \
                self.c.websocket_connect('/ws?kind=controller&token=' + SECRET) as ct:
            s1, s2 = ov.receive_json(), ct.receive_json()
            self.assertEqual(s1['t'], 'snapshot')
            self.assertFalse(s1['authed'])
            self.assertNotIn('t_secret', s1['slices'])
            self.assertIn('t_secret', s2['slices'])
            # 조종실이 WebSocket 으로 명령 → 결과 · 쪽지(seq 가 하나씩)
            ct.send_json({'t': 'cmd', 'id': 7, 'type': 't.set', 'data': {'answer': '비밀'}})
            msgs = [ct.receive_json(), ct.receive_json()]
            res = next(m for m in msgs if m['t'] == 'result')
            patch = next(m for m in msgs if m['t'] == 'patch')
            self.assertTrue(res['ok'])
            self.assertEqual(res['id'], 7)
            self.assertEqual(patch['seq'], s2['seq'] + 1)
            self.assertEqual(patch['slices']['t_secret']['answer'], '비밀')
            p_ov = ov.receive_json()
            self.assertEqual(p_ov['seq'], s1['seq'] + 1)
            self.assertNotIn('t_secret', p_ov['slices'])
            self.assertEqual(p_ov['slices']['t_public']['n'], 1)
            # 방송판(로그인 없음)은 명령을 못 보낸다
            ov.send_json({'t': 'cmd', 'id': 1, 'type': 't.set', 'data': {}})
            r = ov.receive_json()
            self.assertEqual(r['t'], 'result')
            self.assertFalse(r['ok'])
            # 다시 달라고 하면 통째
            ov.send_json({'t': 'resync'})
            self.assertEqual(ov.receive_json()['t'], 'snapshot')


if __name__ == '__main__':
    unittest.main()


class Later(unittest.TestCase):
    def test_server_runs_command_later(self):
        """ctx.later — 잠시 뒤 서버가 스스로 명령을 부른다(까보기 6초 뒤 덮기 같은 것)."""
        import asyncio
        from v2.server.bus import Bus
        from v2.server.store import Store

        @command('t.later_start')
        def _a(ctx, data):
            ctx.edit('t_public')['n'] = 100
            ctx.later(0.1, 't.later_end', {'to': 7})

        @command('t.later_end')
        def _b(ctx, data):
            ctx.edit('t_public')['n'] = data['to']

        @command('t.later_fail')
        def _c(ctx, data):
            ctx.later(0.05, 't.later_end', {'to': 999})
            raise CommandError('실패하면 예약도 없다')

        async def run():
            bus = Bus(Store(':memory:'))
            await bus.run('t.later_start')
            self.assertEqual(bus.state.get('t_public')['n'], 100)
            await bus.run('t.later_fail')
            await asyncio.sleep(0.3)
            return bus.state.get('t_public')['n']
        self.assertEqual(asyncio.run(run()), 7)


class HealthPage(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient
        from v2.server.app import create_app
        self.c = TestClient(create_app(':memory:', password='pw', secret='s' * 32))

    def test_json_and_page(self):
        h = self.c.get('/api/health').json()
        for k in ('uptime_sec', 'db', 'screens', 'counts', 'listener', 'spool', 'live'):
            self.assertIn(k, h)
        self.assertEqual(self.c.get('/health').json()['screens']['total'], 0)
        r = self.c.get('/health', headers={'accept': 'text/html'})
        self.assertIn('서버 상태', r.text)

    def test_no_private(self):
        self.c.post('/login', json={'password': 'pw'})
        self.c.post('/api/cmd', json={'type': 'session.start', 'data': {}})
        self.c.post('/api/donation', json={'name': '비밀이름', 'amount': 30000, 'message': '비밀메시지', 'tx_id': 'toon_hz1'})
        txt = self.c.get('/api/health').text
        self.assertNotIn('비밀이름', txt)
        self.assertNotIn('비밀메시지', txt)
        self.assertNotIn('30000', txt)


class NoStaleScreens(unittest.TestCase):
    def test_screens_revalidate(self):
        c = TestClient(create_app(':memory:', password='pw', secret='s' * 32))
        self.assertEqual(c.get('/controller/js/util.js').headers.get('cache-control'), 'no-cache')
        self.assertEqual(c.get('/overlay/').headers.get('cache-control'), 'no-cache')
        self.assertEqual(c.get('/shared/client.js').headers.get('cache-control'), 'no-cache')


class Events(unittest.TestCase):
    def test_recent_events(self):
        c = TestClient(create_app(':memory:', password='pw', secret='s' * 32))
        h = {'Authorization': 'Bearer ' + 's' * 32}
        c.post('/api/cmd', json={'type': 'session.start', 'data': {'names': ['하율']}}, headers=h)
        c.post('/api/cmd', json={'type': 'notice.add', 'data': {'text': '가' * 300}}, headers=h)
        r = c.get('/api/events?limit=5', headers=h).json()['events']
        self.assertEqual(r[0]['type'], 'notice.add')                 # 최근 것부터
        self.assertLessEqual(len(r[0]['data']), 120)
        self.assertEqual(c.get('/api/events').status_code, 401)


class Trial(unittest.TestCase):
    """🧪 시험판 — 옛 프로그램과 같이 쓰는 것을 바꾸는 주소만 잠근다."""

    def test_trial_blocks_shared_writes(self):
        from unittest import mock
        h = {'Authorization': 'Bearer ' + 's' * 32}
        with mock.patch.dict(os.environ, {'LM2_TRIAL': '1'}):
            c = TestClient(create_app(':memory:', password='pw', secret='s' * 32))
            for path, body in (('/api/version/switch', {'sha': 'x'}), ('/api/version/latest', {}), ('/api/toon/accounts', {'enabled': False}),
                               ('/api/sigadmin/restore', {'lid': 'x'})):
                r = c.post(path, json=body, headers=h)
                self.assertEqual(r.status_code, 403, path)
                self.assertTrue(r.json()['trial'])
            self.assertEqual(c.delete('/api/signatures/delete/5', headers=h).status_code, 403)
            self.assertEqual(c.get('/api/toon/accounts', headers=h).status_code, 200)       # 읽기는 된다
            self.assertTrue(c.get('/api/health').json()['trial'])
        c2 = TestClient(create_app(':memory:', password='pw', secret='s' * 32))
        self.assertFalse(c2.get('/api/health').json()['trial'])
