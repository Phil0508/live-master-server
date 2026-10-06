# -*- coding: utf-8 -*-
"""v2 실제 서버(uvicorn)로 — 화면 300개 · 쪽지 번호 · 갑자기 끊긴 화면 · 반만 끊긴 화면(09-30 사고).

⚠️ 옛 서버(09-30): 앞단이 반만 끊은 연결이 CLOSE-WAIT 로 161개 쌓여 점수가 안 들어갔다.
   여기서는 (1) 정상 300개가 쪽지를 빠짐없이 받는지 (2) 소켓을 그냥 버린 화면 · 반만 끊은 화면이
   서버에서 저절로 빠지는지 본다.
"""
import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

import websockets

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SECRET = 'testsecret-0123456789'
H = {'Authorization': 'Bearer ' + SECRET, 'Content-Type': 'application/json'}


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Live(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix='lm2live_')
        cls.port = free_port()
        env = dict(os.environ, LM2_PORT=str(cls.port), LM2_DB=os.path.join(cls.dir, 'live.db'), ADMIN_PASSWORD='pw',
                   SESSION_SECRET=SECRET, LM2_WS_PING='2', PYTHONIOENCODING='utf-8')
        cls.proc = subprocess.Popen([sys.executable, '-m', 'v2.server.app'], cwd=ROOT, env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.base = 'http://127.0.0.1:%d' % cls.port
        for _ in range(100):
            try:
                urllib.request.urlopen(cls.base + '/health', timeout=1)
                break
            except Exception:
                time.sleep(0.1)
        cls.call('/api/cmd', {'type': 'session.start', 'data': {'names': ['하율', '서아']}})

    @classmethod
    def tearDownClass(cls):
        cls.proc.kill()
        cls.proc.wait(timeout=10)
        shutil.rmtree(cls.dir, ignore_errors=True)

    @classmethod
    def call(cls, path, body=None):
        req = urllib.request.Request(cls.base + path, json.dumps(body).encode() if body is not None else None, H)
        return json.loads(urllib.request.urlopen(req, timeout=10).read())

    def screens(self):
        return json.loads(urllib.request.urlopen(self.base + '/health', timeout=5).read())['screens']['total']

    def wait_screens(self, n, sec):
        t0 = time.time()
        while time.time() - t0 < sec:
            if self.screens() == n:
                return True
            time.sleep(0.2)
        return False

    def test_1_many_screens_get_every_patch(self):
        """화면 300개 — 점수 50번을 빠짐없이 · 번호 순서대로 받는다."""
        N, K = 300, 50

        async def run():
            url = 'ws://127.0.0.1:%d/ws?kind=overlay' % self.port
            socks = await asyncio.gather(*[websockets.connect(url, max_queue=None) for _ in range(N)])
            snaps = await asyncio.gather(*[s.recv() for s in socks])
            seq0 = [json.loads(m)['seq'] for m in snaps]
            t0 = time.time()
            for i in range(K):
                await asyncio.to_thread(self.call, '/api/cmd', {'type': 'score.add', 'data': {'name': '하율', 'delta': 1}})

            async def drain(s, start):
                got = []
                while len(got) < K:
                    m = json.loads(await asyncio.wait_for(s.recv(), 20))
                    if m['t'] == 'patch':
                        got.append(m['seq'])
                return got == list(range(start + 1, start + K + 1))
            ok = await asyncio.gather(*[drain(s, q) for s, q in zip(socks, seq0)])
            dt = time.time() - t0
            last = None
            await asyncio.gather(*[s.close() for s in socks])
            return all(ok), dt, last

        ok, dt, _ = asyncio.run(run())
        self.assertTrue(ok, '빠지거나 순서가 틀린 쪽지가 있다')
        self.assertLess(dt, 20)
        self.assertTrue(self.wait_screens(0, 5), self.screens())

    def test_2_abandoned_and_half_closed(self):
        """소켓을 그냥 버린 화면 · 반만 끊은 화면(09-30) — 서버에서 저절로 빠진다."""
        base = self.screens()
        raws = []
        for i in range(20):
            s = socket.create_connection(('127.0.0.1', self.port), timeout=5)
            s.sendall(('GET /ws?kind=overlay HTTP/1.1\r\nHost: 127.0.0.1\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n'
                       'Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
            s.recv(4096)
            raws.append(s)
        time.sleep(0.5)
        self.assertEqual(self.screens(), base + 20)
        for s in raws[:10]:
            s.shutdown(socket.SHUT_WR)          # 반만 끊기 — 읽기 쪽은 열어 둔다(Caddy 가 하던 짓)
        # 나머지 10개는 아무것도 안 하고 버린다(답도 안 한다 — ping 에 pong 이 없다)
        ok = self.wait_screens(base, 15)
        for s in raws:
            try:
                s.close()
            except Exception:
                pass
        self.assertTrue(ok, '죽은 화면이 안 빠졌다: %s' % self.screens())

    def test_3_commands_still_work_after(self):
        before = self.call('/api/state')['slices']['players']['list']
        r = self.call('/api/cmd', {'type': 'score.add', 'data': {'name': '서아', 'delta': 2}})
        self.assertTrue(r['ok'])
        after = self.call('/api/state')['slices']['players']['list']
        self.assertEqual(next(p for p in after if p['name'] == '서아')['score'],
                         next(p for p in before if p['name'] == '서아')['score'] + 2)


if __name__ == '__main__':
    unittest.main()
