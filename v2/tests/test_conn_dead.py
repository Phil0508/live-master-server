# -*- coding: utf-8 -*-
"""🔌 반쯤 끊긴 연결 — 무응답이면 onclose 를 기다리지 않고 곧바로 다시 붙는지 (conn 10-17).

전에는 45초 무응답이면 ws.close() 만 부르고 다시 붙기는 onclose 에서만 했다. 반쯤 끊긴 연결은 브라우저가
닫기 인사를 기다리느라 onclose 가 한참 늦게 와서, 알아채고 다시 붙는 데 약 106초가 걸렸다.
이제는 옛 소켓의 귀를 떼고(onmessage · onclose · onerror) 곧바로 새로 연다. 옛 소켓에서 늦게 온 쪽지 · 닫힘은 무시한다.
shared/client.js 는 방송판 · 조종실이 같이 쓴다 — 실제 파일을 node 로 불러 가짜 소켓으로 돌린다.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CLIENT_JS = os.path.join(ROOT, 'v2', 'web', 'shared', 'client.js')

NODE_TEST = r"""
const fs = require('fs'), vm = require('vm');
const socks = [];
class FakeWS {
    constructor(url) { this.url = url; this.readyState = 0; this.closed = 0; this.sent = []; socks.push(this); }
    send(s) { this.sent.push(JSON.parse(s)); }
    close() { this.closed++; }          // 반쯤 끊긴 연결 — 닫기를 불러도 onclose 가 안 온다
}
globalThis.WebSocket = FakeWS;
globalThis.location = { protocol: 'http:', host: 'x.test' };
vm.runInThisContext(fs.readFileSync(process.argv[2], 'utf8'));
const out = {};
const sleep = ms => new Promise(r => setTimeout(r, ms));
const snap = (ws, seq, n) => ws.onmessage({ data: JSON.stringify({ t: 'snapshot', seq, authed: false, slices: { n: { v: n } } }) });
(async () => {
    const st = [];
    const lm = LM.connect({ kind: 'overlay', deadMs: 120, tickMs: 20 });
    lm.onStatus(s => st.push(s));
    const a = socks[0];
    a.readyState = 1; a.onopen();
    snap(a, 5, 1);
    out.first_live = lm.get('n').v === 1 && st[st.length - 1] === 'live';
    // 쪽지가 오는 동안은 그대로
    for (let i = 0; i < 6; i++) { await sleep(40); a.onmessage({ data: JSON.stringify({ t: 'ping' }) }); }
    out.alive_kept = socks.length === 1;
    // 무응답 — onclose 없이도 바로 새 소켓
    const lateMsg = a.onmessage, lateClose = a.onclose, lateErr = a.onerror;
    const t0 = Date.now();
    while (socks.length < 2 && Date.now() - t0 < 2000) await sleep(5);
    const took = Date.now() - t0;
    out.reopened = socks.length === 2;
    out.reopened_fast = took < 400;                           // deadMs 120 + tick 20 언저리(onclose 를 안 기다림)
    out.old_close_tried = a.closed >= 1;
    out.old_detached = a.onmessage === null && a.onclose === null && a.onerror === null;
    out.status_down_then_connecting = st.slice(-2).join(',') === 'down,connecting';
    const b = socks[1];
    out.new_url = /kind=overlay/.test(b.url);
    // 새 소켓이 붙어 통째를 받는다
    b.readyState = 1; b.onopen();
    snap(b, 9, 2);
    out.new_snapshot = lm.get('n').v === 2 && lm.seq === 9 && st[st.length - 1] === 'live';
    // 옛 소켓에서 늦게 온 쪽지 · 닫힘 · 오류는 무시(두 소켓이 같이 쪽지를 넣지 않는다)
    lateMsg({ data: JSON.stringify({ t: 'snapshot', seq: 99, slices: { n: { v: 3 } } }) });
    lateMsg({ data: JSON.stringify({ t: 'patch', seq: 10, slices: { n: { v: 4 } } }) });
    out.old_msg_ignored = lm.get('n').v === 2 && lm.seq === 9;
    const nst = st.length;
    lateClose(); lateErr();
    await sleep(60);
    out.old_close_ignored = st.length === nst && socks.length === 2 && b.closed === 0;
    // 새 소켓의 쪽지는 그대로 들어간다
    b.onmessage({ data: JSON.stringify({ t: 'patch', seq: 10, slices: { n: { v: 5 } } }) });
    out.new_patch = lm.get('n').v === 5 && lm.seq === 10;
    // 명령은 새 소켓으로
    const p = lm.cmd('x.y', { a: 1 }, 500);
    out.cmd_new_sock = b.sent.length === 1 && a.sent.length === 0;
    b.onmessage({ data: JSON.stringify({ t: 'result', id: b.sent[0].id, ok: true }) });
    out.cmd_answered = (await p).ok === true;
    // 진짜로 닫힌 경우(onclose 가 온 경우)는 예전처럼 기다렸다 다시
    b.readyState = 3; b.onclose();
    out.real_close_down = st[st.length - 1] === 'down' && socks.length === 2;
    await sleep(1100);
    out.real_close_retry = socks.length === 3;
    // 우리가 닫으면 무응답이어도 다시 안 붙는다
    const c = socks[2]; c.readyState = 1; c.onopen(); snap(c, 11, 6);
    lm.close();
    await sleep(300);
    out.closed_by_us_stays = socks.length === 3;
    console.log(JSON.stringify(out));
    process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
"""


class DeadConn(unittest.TestCase):
    def test_dead_socket_reopens_without_waiting_onclose(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('node 가 없습니다')
        d = tempfile.mkdtemp(prefix='lm2conn_')
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, 'conn_test.js')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(NODE_TEST)
        r = subprocess.run([node, p, CLIENT_JS], capture_output=True, text=True, encoding='utf-8', timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])
        out = json.loads(r.stdout.strip().splitlines()[-1])
        bad = [k for k, v in out.items() if v is not True]
        self.assertEqual(bad, [], out)
        self.assertEqual(len(out), 17)

    def test_default_dead_time_unchanged(self):
        src = open(CLIENT_JS, encoding='utf-8').read()
        self.assertTrue('const DEAD_MS = 45000;' in src, '무응답 기준 45초가 바뀌었다(서버 ping 15초)')
        self.assertTrue('opts.deadMs || DEAD_MS' in src)


if __name__ == '__main__':
    unittest.main()
