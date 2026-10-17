/* 📡 v2 화면 공용 연결 — 방송판 · 조종실이 같이 쓴다.
   - 붙으면 통째(snapshot)를 받고, 그 뒤엔 바뀐 조각(patch)만 받는다.
   - 쪽지 번호(seq)가 하나 건너뛰면 '빠진 쪽지' — 통째를 다시 달라고 한다(resync).
   - 45초 동안 아무것도 못 받으면(서버는 15초마다 ping) 죽은 연결로 보고 다시 붙는다.
     ⚠️ 반쯤 끊긴 연결은 close() 를 불러도 브라우저가 닫기 인사를 기다리느라 onclose 가 한참(실측 ~1분) 늦게 온다.
        그래서 옛 소켓의 귀(onmessage · onclose · onerror)를 떼고 곧바로 새로 연다(conn 10-17) — 옛 소켓은 닫기만 시도.
        귀를 뗐으니 두 소켓이 같이 쪽지를 넣는 일은 없고, 새 소켓은 늘 통째(snapshot)부터 받는다.
   - 끊기면 1초 · 2초 · 4초 … 최대 10초 간격으로 다시 붙는다.
   ⚠️ 옛 방송판은 연결이 반쯤 끊겨도 몰랐다(09-30). 여기선 화면이 스스로 안다.

   쓰는 법:
     const lm = LM.connect({ kind: 'overlay' });
     lm.on('players', p => draw(p));          // 그 조각이 바뀔 때마다(처음 한 번 포함)
     lm.on('*', slices => …);                 // 아무 조각이나 바뀔 때
     await lm.cmd('score.add', { player: '하율', delta: 5 });   // 조종실만(로그인)
     lm.serverNow()                           // 서버 시계(ms) — 타이머 · 끝 시각 계산용

   🔁 명령 번호(cid · sturdy 10-17) — 명령마다 고유 번호를 붙인다. 서버는 같은 이름 · 같은 번호를 두 번 하지 않고 첫 결과를 돌려준다.
      8초 안에 답이 없거나(응답 없음) 서버에 닿지 않으면 그 명령은 '들어갔는지 모름' 으로 기억해 두었다가,
      1분 안에 **똑같은 명령**(이름 · 내용이 같은 것)을 다시 누르면 그 번호를 그대로 다시 쓴다 → 이미 들어갔으면 서버가 첫 결과만 돌려준다.
      ⚠️ 전에는 '다시 눌러 주세요' 뒤 다시 누르면 점수가 두 번 들어갈 수 있었다(첫 명령이 늦게라도 들어간 경우).
      답을 받은 명령은 잊는다 — 일부러 두 번 누르는 +1 · +1 은 번호가 달라 두 번 다 들어간다.
*/
(function (global) {
    'use strict';
    const DEAD_MS = 45000;
    const UNSURE_MS = 60000;                  // '들어갔는지 모름' 명령을 기억하는 시간

    /* 명령 번호 — 이 탭 · 이 순간에 하나뿐인 글자(서버는 4~100자만 받는다) */
    function newCid() {
        let r = '';
        try {
            const a = new Uint32Array(2);
            global.crypto.getRandomValues(a);
            r = a[0].toString(36) + a[1].toString(36);
        } catch (e) {
            r = Math.random().toString(36).slice(2) + Math.random().toString(36).slice(2);
        }
        return 'c' + Date.now().toString(36) + '-' + r;
    }

    /* 같은 명령인가 — 이름 + 내용(JSON). 키 순서가 달라도 같게 본다 */
    function cmdSig(type, data) {
        const norm = v => {
            if (Array.isArray(v)) return v.map(norm);
            if (v && typeof v === 'object') {
                const o = {};
                Object.keys(v).sort().forEach(k => { o[k] = norm(v[k]); });
                return o;
            }
            return v;
        };
        let body = '';
        try { body = JSON.stringify(norm(data || {})); } catch (e) { body = newCid(); }   // 못 적는 내용이면 늘 다른 것으로
        return type + '\n' + body;
    }

    /* '들어갔는지 모름' 기억장 — 화면 없이 도는 순수 묶음(node 로 검사한다: v2/tests/test_sturdy_cid.py) */
    function makeCidBook(now) {
        now = now || (() => Date.now());
        const unsure = new Map();             // cmdSig → {cid, at}
        return {
            /* 이번에 쓸 번호 — 1분 안에 답을 못 받은 똑같은 명령이 있으면 그 번호 */
            take(type, data) {
                const sig = cmdSig(type, data), t = now();
                for (const [k, v] of unsure) if (t - v.at > UNSURE_MS) unsure.delete(k);
                const old = unsure.get(sig);
                return { sig, cid: old ? old.cid : newCid(), reused: !!old };
            },
            /* 답이 없었다 · 닿지 않았다 — 기억해 둔다 */
            unsure(sig, cid) { unsure.set(sig, { cid, at: now() }); },
            /* 답을 받았다(성공이든 거절이든) — 잊는다 */
            settled(sig, cid) { const v = unsure.get(sig); if (v && v.cid === cid) unsure.delete(sig); },
            get size() { return unsure.size; },
        };
    }

    function connect(opts) {
        opts = opts || {};
        const kind = opts.kind || 'other';
        const subs = {};                      // 조각 이름 → [함수]
        const statusSubs = [];
        const pending = new Map();            // 명령 id → {resolve, timer}
        const book = makeCidBook();           // 🔁 답을 못 받은 명령의 번호(다시 누르면 같은 번호로)
        const deadMs = opts.deadMs || DEAD_MS, tickMs = opts.tickMs || 5000;   // 검사용으로만 바꾼다
        let ws = null, seq = -1, slices = {}, authed = false, lastMsg = 0, backoff = 1000, nextId = 1, closedByUs = false, openedAt = 0;
        // 서버 시계 — 쪽지에 찍힌 now 와 받은 때의 차. 늦게 온 쪽지일수록 차가 작아지므로 **가장 큰 값**이 실제에 가깝다.
        // 1분마다 조금씩 낮춰(덜 믿어) PC 시계가 움직여도 따라간다.
        let clockOff = null, clockAt = 0;
        function clock(now) {
            if (typeof now !== 'number' || !isFinite(now)) return;
            const off = now - Date.now(), t = Date.now();
            if (clockOff === null || off > clockOff || t - clockAt > 60000) { clockOff = off; clockAt = t; }
        }

        function emit(name, value) {
            (subs[name] || []).forEach(fn => { try { fn(value, slices); } catch (e) { console.error('[lm] ' + name, e); } });
        }
        function status(s) { statusSubs.forEach(fn => { try { fn(s); } catch (e) {} }); }

        function apply(changed, full) {
            const names = Object.keys(changed || {});
            if (full) slices = {};
            names.forEach(k => { slices[k] = changed[k]; });
            names.forEach(k => emit(k, slices[k]));
            if (names.length || full) emit('*', slices);
        }

        function url() {
            const u = new URL((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
            u.searchParams.set('kind', kind);
            if (opts.monitor) u.searchParams.set('monitor', '1');
            if (opts.token) u.searchParams.set('token', opts.token);
            return u.toString();
        }

        function open() {
            closedByUs = false;
            status('connecting');
            openedAt = Date.now();
            let sock;
            try { sock = ws = new WebSocket(url()); } catch (e) { return retry(); }
            const mine = () => ws === sock;                 // 버린 옛 소켓에서 온 것은 무시
            sock.onopen = () => { if (!mine()) return; backoff = 1000; lastMsg = Date.now(); };
            sock.onmessage = ev => {
                if (!mine()) return;
                lastMsg = Date.now();
                let m; try { m = JSON.parse(ev.data); } catch (e) { return; }
                clock(m.now);
                if (m.t === 'snapshot') {
                    seq = m.seq; authed = !!m.authed;
                    apply(m.slices, true);
                    status('live');
                } else if (m.t === 'patch') {
                    if (seq < 0 || m.seq <= seq) return;               // 통째 받기 전이거나 이미 본 것
                    if (m.seq !== seq + 1) { seq = -1; send({ t: 'resync' }); return; }   // 빠진 쪽지
                    seq = m.seq;
                    apply(m.slices, false);
                } else if (m.t === 'result') {
                    const p = pending.get(m.id);
                    if (p) { clearTimeout(p.timer); pending.delete(m.id); p.resolve(m); }
                }
            };
            sock.onclose = () => { if (!mine()) return; status('down'); if (!closedByUs) retry(); };
            sock.onerror = () => { try { sock.close(); } catch (e) {} };
        }

        /* 죽은 소켓 버리기 — 귀를 떼고 닫기만 시도, 기다리지 않고 바로 새로 연다 */
        function drop() {
            const old = ws;
            ws = null;
            if (old) {
                old.onopen = old.onmessage = old.onclose = old.onerror = null;
                try { old.close(); } catch (e) {}
            }
            status('down');
            if (!closedByUs) open();
        }

        function retry() {
            setTimeout(open, backoff);
            backoff = Math.min(backoff * 2, 10000);
        }

        function send(obj) {
            if (ws && ws.readyState === 1) { ws.send(JSON.stringify(obj)); return true; }
            return false;
        }

        // 죽은 연결 지키기 — ping 도 안 오면 버리고 곧바로 다시 붙는다(onclose 를 기다리지 않는다)
        // 붙는 중(readyState 0)에서 멈춘 것도 같다 — 서버 · 중간 다리가 손 인사에 답을 안 하면 onclose 가 몇 분 뒤에나 와서
        // 그동안 다시 붙기를 아예 안 했다(검토 10-17). 45초 넘게 '붙는 중' 이면 버리고 새로.
        setInterval(() => {
            if (!ws) return;
            const t = Date.now();
            if (ws.readyState === 1 && t - lastMsg > deadMs) drop();
            else if (ws.readyState === 0 && t - openedAt > deadMs) drop();
        }, tickMs);

        open();

        return {
            on(name, fn) {
                (subs[name] = subs[name] || []).push(fn);
                if (name === '*' && Object.keys(slices).length) fn(slices, slices);
                else if (slices[name] !== undefined) fn(slices[name], slices);
            },
            onStatus(fn) { statusSubs.push(fn); },
            get(name) { return slices[name]; },
            get authed() { return authed; },
            get seq() { return seq; },
            /* 서버 시계(ms) — 쪽지를 아직 못 받았으면 이 PC 시계 */
            serverNow() { return Date.now() + (clockOff || 0); },
            /* 명령 — 실시간 연결로 보내고, 안 붙어 있으면 HTTP 로. 결과: {ok, error?, dup?, ...}
               dup: true = 같은 번호로 이미 들어가 있던 것(서버가 첫 결과를 돌려줬다 — 두 번 안 들어갔다) */
            cmd(type, data, timeoutMs) {
                const id = nextId++;
                const { sig, cid } = book.take(type, data);
                const msg = { t: 'cmd', id, cid, type, data: data || {} };
                if (send(msg)) {
                    return new Promise(resolve => {
                        const timer = setTimeout(() => {
                            pending.delete(id);
                            book.unsure(sig, cid);
                            resolve({ ok: false, error: '응답이 없습니다 — 다시 눌러 주세요(이미 들어갔으면 두 번 들어가지 않아요)' });
                        }, timeoutMs || 8000);
                        pending.set(id, { resolve: m => { book.settled(sig, cid); resolve(m); }, timer });
                    });
                }
                return fetch('/api/cmd', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type, cid, data: data || {} }) })
                    .then(r => r.json())
                    .then(m => { book.settled(sig, cid); return m; })
                    .catch(() => { book.unsure(sig, cid); return { ok: false, error: '서버에 닿지 않습니다' }; });
            },
            close() { closedByUs = true; try { if (ws) ws.close(); } catch (e) {} },
        };
    }

    global.LM = { connect, _cid: { newCid, cmdSig, makeCidBook, UNSURE_MS } };   // _cid — 검사용(node)
})(typeof window !== 'undefined' ? window : globalThis);
