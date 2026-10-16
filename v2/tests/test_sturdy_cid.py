# -*- coding: utf-8 -*-
"""🔁 명령 번호(cid) — '응답이 없습니다 — 다시 눌러 주세요' 뒤 다시 눌러도 점수가 두 번 안 들어가는지 (sturdy 10-17).

조종실(shared/client.js)은 명령마다 번호를 붙이고, 답을 못 받은 명령을 1분 안에 똑같이 다시 누르면 같은 번호를 다시 쓴다.
서버(bus)는 같은 이름 · 같은 번호면 다시 하지 않고 첫 결과를 돌려준다(dup: True). 성공한 것은 장부(cmd_ids)에도 적어
그사이 서버가 다시 켜져도 기억한다. 실패한 명령은 아무것도 안 바꿨으니 기억하지 않는다(다시 오면 다시 해 본다).
"""
import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest

from fastapi.testclient import TestClient

from v2.server import bus as busmod
from v2.server import domain  # noqa: F401  (조각 · 명령 등록)
from v2.server.app import create_app
from v2.server.bus import Bus, cid_key, command
from v2.server.state import slice_
from v2.server.store import Store

PW, SECRET = 'testpw', 'testsecret-0123456789'
H = {'Authorization': 'Bearer ' + SECRET}
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLIENT_JS = os.path.join(ROOT, 'v2', 'web', 'shared', 'client.js')

slice_('t_sturdy_cid', False, lambda: {'n': 0})


@command('t_sturdy.slow')
def _t_slow(ctx, data):
    ctx.edit('t_sturdy_cid')['n'] += 1


def _slow_prefetch(bus, data):
    time.sleep(0.2)                    # 바깥 조회처럼 오래 걸린다 — 그동안 같은 번호가 또 온다
    return data


busmod.PREFETCH['t_sturdy.slow'] = _slow_prefetch


class Http(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lm2cid_')
        self.db = os.path.join(self.dir, 'lm2.db')
        self.c = TestClient(create_app(db_path=self.db, password=PW, secret=SECRET))
        self.cmd('session.start', {'names': ['하율', '서아']})

    def tearDown(self):
        self.c.app.state.store.close()
        shutil.rmtree(self.dir, ignore_errors=True)

    def cmd(self, t, data, cid=None, headers=H, c=None):
        body = {'type': t, 'data': data}
        if cid is not None:
            body['cid'] = cid
        r = (c or self.c).post('/api/cmd', json=body, headers=headers)
        return r.status_code, r.json()

    def score(self, name, c=None):
        s = (c or self.c).get('/api/state', headers=H).json()['slices']
        return next(p['score'] for p in s['players']['list'] if p['name'] == name)

    def logs(self, c=None):
        return len((c or self.c).get('/api/state', headers=H).json()['slices']['logs'])

    def test_same_cid_runs_once(self):
        code, r1 = self.cmd('score.add', {'name': '하율', 'delta': 5}, cid='c-abc-1')
        self.assertEqual(code, 200, r1)
        code, r2 = self.cmd('score.add', {'name': '하율', 'delta': 5}, cid='c-abc-1')
        self.assertEqual(code, 200, r2)
        self.assertTrue(r2.get('dup'))
        self.assertNotIn('dup', r1)
        self.assertEqual(r2['seq'], r1['seq'])
        self.assertEqual(self.score('하율'), 5)
        self.assertEqual(self.logs(), 1)

    def test_different_cid_or_none_runs_again(self):
        self.cmd('score.add', {'name': '하율', 'delta': 1}, cid='c-one-1')
        self.cmd('score.add', {'name': '하율', 'delta': 1}, cid='c-one-2')
        self.cmd('score.add', {'name': '하율', 'delta': 1})
        self.cmd('score.add', {'name': '하율', 'delta': 1})
        self.assertEqual(self.score('하율'), 4)

    def test_cid_is_per_command_name(self):
        self.cmd('score.add', {'name': '하율', 'delta': 1}, cid='c-same-1')
        code, r = self.cmd('score.add', {'name': '서아', 'delta': 2, 'list': None}, cid='c-same-1')
        self.assertTrue(r.get('dup'))           # 같은 명령 이름 · 같은 번호 = 같은 누름
        code, r = self.cmd('goal.set', {'target': 100}, cid='c-same-1')
        self.assertFalse(r.get('dup'))          # 다른 명령은 다른 열쇠
        self.assertEqual(self.score('서아'), 0)

    def test_failed_command_is_not_remembered(self):
        code, r = self.cmd('score.add', {'name': '없는사람', 'delta': 3}, cid='c-fail-1')
        self.assertNotEqual(code, 200)
        self.assertEqual(self.cmd('players.add', {'name': '없는사람'})[0], 200)
        code, r = self.cmd('score.add', {'name': '없는사람', 'delta': 3}, cid='c-fail-1')
        self.assertEqual(code, 200, r)          # 다시 오면 다시 해 본다(첫 번째는 아무것도 안 바꿨다)
        self.assertFalse(r.get('dup'))
        self.assertEqual(self.score('없는사람'), 3)

    def test_remembered_across_restart(self):
        self.cmd('score.add', {'name': '하율', 'delta': 7}, cid='c-restart-1')
        self.c.app.state.store.close()
        c2 = TestClient(create_app(db_path=self.db, password=PW, secret=SECRET))
        self.addCleanup(c2.app.state.store.close)
        code, r = self.cmd('score.add', {'name': '하율', 'delta': 7}, cid='c-restart-1', c=c2)
        self.assertEqual(code, 200)
        self.assertTrue(r.get('dup'))
        self.assertEqual(self.score('하율', c=c2), 7)
        self.c = c2                              # tearDown 이 닫는다

    def test_unauthed_gets_401_not_cached_result(self):
        self.cmd('score.add', {'name': '하율', 'delta': 1}, cid='c-auth-1')
        code, r = self.cmd('score.add', {'name': '하율', 'delta': 1}, cid='c-auth-1', headers={})
        self.assertEqual(code, 401)
        self.assertNotIn('seq', r)

    def test_bad_cid_is_ignored(self):
        for bad in ('', 'ab', 'x' * 200, ['c-list-1'], {'a': 1}, True):
            code, r = self.cmd('score.add', {'name': '하율', 'delta': 1}, cid=bad)
            self.assertEqual(code, 200, (bad, r))
            self.assertFalse(r.get('dup'))
        self.assertEqual(self.score('하율'), 6)

    def test_websocket_same_cid(self):
        with self.c.websocket_connect('/ws?kind=controller', headers=H) as ws:
            self.assertEqual(ws.receive_json()['t'], 'snapshot')
            ws.send_json({'t': 'cmd', 'id': 1, 'cid': 'c-ws-1', 'type': 'score.add', 'data': {'name': '서아', 'delta': 2}})
            ws.send_json({'t': 'cmd', 'id': 2, 'cid': 'c-ws-1', 'type': 'score.add', 'data': {'name': '서아', 'delta': 2}})
            res = {}
            for _ in range(10):
                m = ws.receive_json()
                if m.get('t') == 'result':
                    res[m['id']] = m
                if len(res) == 2:
                    break
        self.assertTrue(res[1]['ok'] and not res[1].get('dup'))
        self.assertTrue(res[2]['ok'] and res[2].get('dup'))
        self.assertEqual(self.score('서아'), 2)


class InFlight(unittest.TestCase):
    def test_same_cid_while_first_still_running(self):
        """첫 명령이 아직 처리 중(바깥 조회)일 때 같은 번호가 또 오면 기다렸다가 첫 결과를 같이 받는다."""
        s = Store(':memory:')
        self.addCleanup(s.close)
        b = Bus(s)

        async def main():
            return await asyncio.gather(b.run('t_sturdy.slow', {}, cid='c-slow-1'), b.run('t_sturdy.slow', {}, cid='c-slow-1'))
        r1, r2 = asyncio.run(main())
        self.assertTrue(r1['ok'] and r2['ok'])
        self.assertEqual(sorted([bool(r1.get('dup')), bool(r2.get('dup'))]), [False, True])
        self.assertEqual(r1['seq'], r2['seq'])
        self.assertEqual(b.state.get('t_sturdy_cid')['n'], 1)

    def test_key_rules(self):
        self.assertEqual(cid_key('score.add', 'c-1234'), 'score.add|c-1234')
        self.assertEqual(cid_key('score.add', 12345), 'score.add|12345')
        for bad in (None, '', 'abc', 'x' * 101, True, 1.5, ['x'], 'a\nbcd'):
            self.assertIsNone(cid_key('score.add', bad), bad)


NODE_TEST = r"""
const fs = require('fs'), vm = require('vm');
const sent = [], fetched = [];
class FakeWS {
    constructor(url) { this.url = url; this.readyState = 1; FakeWS.last = this; }
    send(s) { sent.push(JSON.parse(s)); }
    close() { this.readyState = 3; }
}
globalThis.WebSocket = FakeWS;
globalThis.location = { protocol: 'http:', host: 'x.test' };
let fetchMode = 'fail';
globalThis.fetch = (url, o) => {
    fetched.push(JSON.parse(o.body));
    if (fetchMode === 'fail') return Promise.reject(new Error('down'));
    return Promise.resolve({ json: () => Promise.resolve({ ok: true, seq: 9 }) });
};
vm.runInThisContext(fs.readFileSync(process.argv[2], 'utf8'));
const out = {};
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
    // ① 기억장(순수) — 시계를 넣어 1분 넘김까지
    let t = 1000;
    const book = LM._cid.makeCidBook(() => t);
    const a = book.take('score.add', { name: '하율', delta: 1 });
    const a2 = book.take('score.add', { name: '하율', delta: 1 });
    out.book_fresh_differs = a.cid !== a2.cid && !a.reused;
    book.unsure(a.sig, a.cid);
    const b = book.take('score.add', { delta: 1, name: '하율' });          // 키 순서만 다르다
    out.book_reuse = b.cid === a.cid && b.reused;
    out.book_other_data = book.take('score.add', { name: '하율', delta: 2 }).cid !== a.cid;
    out.book_other_type = book.take('score.undo', { name: '하율', delta: 1 }).cid !== a.cid;
    t += LM._cid.UNSURE_MS + 1;
    out.book_expired = book.take('score.add', { name: '하율', delta: 1 }).cid !== a.cid;
    t = 1000; book.unsure(a.sig, a.cid); book.settled(a.sig, a.cid);
    out.book_settled = book.take('score.add', { name: '하율', delta: 1 }).cid !== a.cid;
    out.cid_len_ok = a.cid.length >= 4 && a.cid.length <= 100;

    // ② 진짜 연결 — 답이 없으면 같은 번호로 다시, 답을 받으면 새 번호
    const lm = LM.connect({ kind: 'controller' });
    const ws = FakeWS.last;
    ws.onopen();
    const r1 = await lm.cmd('score.add', { name: '하율', delta: 5 }, 30);          // 답 없음
    out.timeout_msg = !r1.ok && /다시 눌러/.test(r1.error);
    const p2 = lm.cmd('score.add', { name: '하율', delta: 5 }, 1000);               // 다시 누름
    const m1 = sent[0], m2 = sent[1];
    out.ws_has_cid = typeof m1.cid === 'string' && m1.cid.length >= 4;
    out.ws_retry_same_cid = m2.cid === m1.cid;
    ws.onmessage({ data: JSON.stringify({ t: 'result', id: m2.id, ok: true, seq: 3, dup: true }) });
    const r2 = await p2;
    out.ws_dup_passed = r2.ok === true && r2.dup === true;
    const p3 = lm.cmd('score.add', { name: '하율', delta: 5 }, 1000);               // 답을 받은 뒤 또 누름 = 새 누름
    const m3 = sent[2];
    out.ws_new_after_answer = m3.cid !== m1.cid;
    ws.onmessage({ data: JSON.stringify({ t: 'result', id: m3.id, ok: true, seq: 4 }) });
    await p3;

    // ③ 연결이 없으면 HTTP — 닿지 않았으면 같은 번호로 다시
    ws.readyState = 3;
    const h1 = await lm.cmd('goal.set', { target: 5 });
    const h2p = lm.cmd('goal.set', { target: 5 });
    out.http_has_cid = typeof fetched[0].cid === 'string' && fetched[0].type === 'goal.set';
    out.http_retry_same_cid = fetched[1].cid === fetched[0].cid;
    await h2p;
    fetchMode = 'ok';
    await lm.cmd('goal.set', { target: 5 });
    await lm.cmd('goal.set', { target: 5 });
    out.http_ok_then_new = fetched[3].cid !== fetched[2].cid;
    lm.close();
    console.log(JSON.stringify(out));
    process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
"""


class ClientJs(unittest.TestCase):
    def test_client_reuses_cid_only_after_no_answer(self):
        import shutil as _sh
        node = _sh.which('node')
        if not node:
            self.skipTest('node 가 없습니다')
        d = tempfile.mkdtemp(prefix='lm2cidjs_')
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, 'cid_test.js')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(NODE_TEST)
        r = subprocess.run([node, p, CLIENT_JS], capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        out = json.loads(r.stdout.strip().splitlines()[-1])
        bad = [k for k, v in out.items() if v is not True]
        self.assertEqual(bad, [], out)
        self.assertEqual(len(out), 15)


if __name__ == '__main__':
    unittest.main()
