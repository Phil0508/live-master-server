/* 📡 v2 화면 공용 연결 — 방송판 · 조종실이 같이 쓴다.
   - 붙으면 통째(snapshot)를 받고, 그 뒤엔 바뀐 조각(patch)만 받는다.
   - 쪽지 번호(seq)가 하나 건너뛰면 '빠진 쪽지' — 통째를 다시 달라고 한다(resync).
   - 45초 동안 아무것도 못 받으면(서버는 15초마다 ping) 죽은 연결로 보고 다시 붙는다.
   - 끊기면 1초 · 2초 · 4초 … 최대 10초 간격으로 다시 붙는다.
   ⚠️ 옛 방송판은 연결이 반쯤 끊겨도 몰랐다(09-30). 여기선 화면이 스스로 안다.

   쓰는 법:
     const lm = LM.connect({ kind: 'overlay' });
     lm.on('players', p => draw(p));          // 그 조각이 바뀔 때마다(처음 한 번 포함)
     lm.on('*', slices => …);                 // 아무 조각이나 바뀔 때
     await lm.cmd('score.add', { player: '하율', delta: 5 });   // 조종실만(로그인)
     lm.serverNow()                           // 서버 시계(ms) — 타이머 · 끝 시각 계산용
*/
(function (global) {
    'use strict';
    const DEAD_MS = 45000;

    function connect(opts) {
        opts = opts || {};
        const kind = opts.kind || 'other';
        const subs = {};                      // 조각 이름 → [함수]
        const statusSubs = [];
        const pending = new Map();            // 명령 id → {resolve, timer}
        let ws = null, seq = -1, slices = {}, authed = false, lastMsg = 0, backoff = 1000, nextId = 1, closedByUs = false;
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
            try { ws = new WebSocket(url()); } catch (e) { return retry(); }
            ws.onopen = () => { backoff = 1000; lastMsg = Date.now(); };
            ws.onmessage = ev => {
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
            ws.onclose = () => { status('down'); if (!closedByUs) retry(); };
            ws.onerror = () => { try { ws.close(); } catch (e) {} };
        }

        function retry() {
            setTimeout(open, backoff);
            backoff = Math.min(backoff * 2, 10000);
        }

        function send(obj) {
            if (ws && ws.readyState === 1) { ws.send(JSON.stringify(obj)); return true; }
            return false;
        }

        // 죽은 연결 지키기 — ping 도 안 오면 끊고 다시 붙는다
        setInterval(() => {
            if (ws && ws.readyState === 1 && Date.now() - lastMsg > DEAD_MS) { try { ws.close(); } catch (e) {} }
        }, 5000);

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
            /* 명령 — 실시간 연결로 보내고, 안 붙어 있으면 HTTP 로. 결과: {ok, error?, ...} */
            cmd(type, data, timeoutMs) {
                const id = nextId++;
                const msg = { t: 'cmd', id, type, data: data || {} };
                if (send(msg)) {
                    return new Promise(resolve => {
                        const timer = setTimeout(() => { pending.delete(id); resolve({ ok: false, error: '응답이 없습니다 — 다시 눌러 주세요' }); }, timeoutMs || 8000);
                        pending.set(id, { resolve, timer });
                    });
                }
                return fetch('/api/cmd', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ type, data: data || {} }) })
                    .then(r => r.json()).catch(() => ({ ok: false, error: '서버에 닿지 않습니다' }));
            },
            close() { closedByUs = true; try { ws.close(); } catch (e) {} },
        };
    }

    global.LM = { connect };
})(window);
