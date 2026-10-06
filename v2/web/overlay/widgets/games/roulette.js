/* 🎡 룰렛 — roulette 조각 {source, weight, custom, round, phase(idle|spinning|stopping|done), items, spin_at,
   stop{at, ends_at, index, name, angle, duration_ms}}. **당첨은 서버가 정한다** — 방송판은 그 자리에 세우기만 한다.
   옛 RouletteWidget(귀여운 금테 판 · 전구 47개 · 바늘이 못에 걸려 튕김)을 모습 그대로 옮겼다.

   서버 화면 약속(v2/server/domain/roulette.py)
     1. 쉬는 판(idle · done): source=custom 이면 custom 칸 · 같은 넓이. bj 면 번외 판(extra_active) 아니면 본판 선수,
        넓이 = weight==contrib ? max(1, 기여도) : 1. 도는 판(spinning · stopping)은 반드시 items(얼린 칸)로 그린다.
     2. round 가 바뀌고 phase=spinning → 판을 띄우고 0.9초 가속 → 초당 660°(옛 MAX_SPEED).
     3. stop 이 생기면 원판의 angle(12시 칸 경계에서 시계 방향, 도) 지점이 바늘 밑에 오도록 고르게 감속해
        **서버 시각 stop.ends_at** 에 선다(바퀴 수만 창이 고른다 — 서는 자리는 angle 하나라 어느 창이든 같다).
        늦게 붙은 창: ends_at 이 남았으면 남은 시간 동안 감속, 지났으면 그 자리에 바로 세운다.
     4. 다 서면 '이름 당첨!'(roulette-win 칸) · 폭죽 · roulette.done{round}(?monitor=1 은 안 보낸다 · 서버도 스스로 닫는다).
        판은 4초(HOLD_MS) 더 보여 준 뒤(무대가 바뀌었어도) stage 가 roulette 가 아니면 내린다.
        이름 글자는 ends_at 전에 띄우지 않는다(바늘 밑 알약은 도는 동안 지나가는 칸을 보여 줄 뿐 — 옛 것과 같다).

   다른 칸과 나누는 것(stage 로만)
     - setMode('roulette-game')   판이 떠 있다(선 자리 4초 포함) — 뒤 어둡게(roulette-dim) · 후원 순위 비키기(games_a.css)
     - use('rouletteWin').show(name)   '이름 당첨!' 큰 글씨(옛 #roulette-winner-message-layer)
   ⚠️ 옛 '딸깍' 소리(tickSound)는 옮기지 않았다 — 옛 것도 클릭 전엔 AudioContext 가 없어 OBS 에서 실제로 안 났다. */
import { serverNow, boom, screenCovered } from './slot-roulette-kit.js';

const MAX_SPEED = 660;        // 초당 약 1.8바퀴(원본과 같다)
const ACCEL_SEC = 0.9;
const HOLD_MS = 4000;         // 선 자리 보여 주기(서버 HOLD_MS 와 같다)
const S = 640;                // 원판 캔버스 한 변(px)
const PAL = ['#f4807f', '#86c1ec', '#f8d56b', '#9ed8ad', '#c4a6ea', '#f9ae7c', '#f59bc1', '#7fd2cf'];
const FACE = "'Jua', 'Black Han Sans', 'Pretendard', sans-serif";

const BULB_DEFS = '<defs>'
    + '<radialGradient id="rwBulbHalo" cx="50%" cy="50%" r="50%">'
    + '<stop offset="0%" stop-color="#fffef1" stop-opacity="1"></stop><stop offset="24%" stop-color="#fff9bd" stop-opacity=".98"></stop>'
    + '<stop offset="52%" stop-color="#ffd84d" stop-opacity=".78"></stop><stop offset="78%" stop-color="#ffb300" stop-opacity=".28"></stop>'
    + '<stop offset="100%" stop-color="#ff9d00" stop-opacity="0"></stop></radialGradient>'
    + '<radialGradient id="rwBulbCore" cx="42%" cy="35%" r="68%">'
    + '<stop offset="0%" stop-color="#ffffff"></stop><stop offset="44%" stop-color="#fffbd9"></stop><stop offset="100%" stop-color="#ffd84b"></stop>'
    + '</radialGradient></defs>';

function color(i, n) {
    let c = i % PAL.length;
    if (n > 1 && i === n - 1 && c === 0) c = 2;   // 마지막 칸이 첫 칸과 붙어 같은 색이 되는 것 방지
    return PAL[c];
}

export function mount(root, lm, opts) {
    root.innerHTML = '<div class="roulette-wrap gm-board">'
        + '<h1 class="rw-title">🎡 행운의 돌림판</h1>'
        + '<div class="rw-stage">'
        +   '<canvas class="rw-disc" width="' + S + '" height="' + S + '"></canvas>'
        +   '<img class="rw-frame-glow" src="/vendor/roulette/frame.webp" alt="" aria-hidden="true">'
        +   '<img class="rw-frame" src="/vendor/roulette/frame.webp" alt="">'
        +   '<svg class="rw-bulbs" viewBox="0 0 1024 1024" aria-hidden="true" focusable="false">' + BULB_DEFS + '<g class="rw-bulb-g"></g></svg>'
        +   '<div class="rw-pointer"><div class="rw-pointer-spring"><img src="/vendor/roulette/pointer.webp" alt=""></div></div>'
        + '</div>'
        + '<div class="rw-now"></div>'
        + '</div>';
    const $ = s => root.querySelector(s);
    const board = root.firstElementChild;
    const titleEl = $('.rw-title'), stageEl = $('.rw-stage'), canvas = $('.rw-disc');
    const ctx = canvas.getContext('2d');
    const pointer = $('.rw-pointer'), spring = $('.rw-pointer-spring'), nowEl = $('.rw-now');

    const W = {
        rotation: 0, angularVelocity: 0, mode: 'idle',     // idle | accelerating | spinning | stopping | stopped
        items: [], ticks: [0, 90, 180, 270], current: '', sig: null,
        raf: 0, lastT: 0, accelAt: 0, accelFrom: 0, plan: null,
        drag: 0, snapTimer: 0, winTimer: 0, stopTimer: 0,
    };
    let seenRound = null;         // 마지막으로 본 판 번호
    let stopRound = null;         // 정지를 이미 건 판
    let holdUntil = 0;            // 서버 시각 — 이때까지는 무대가 바뀌어도 선 자리를 보여 준다
    let holdTimer = 0;
    let shown = false;
    let doneRound = 0;
    let finishInfo = null;        // 이번 판의 {round, name, ends_at} — 다 서면 쓴다

    const rolling = () => W.mode === 'accelerating' || W.mode === 'spinning' || W.mode === 'stopping';

    // ── 전구 47개 — 원본 좌표(1024 기준) 그대로. 바늘 밑 큰 전구 하나는 그림에 가려 뺀다 ──
    (function buildBulbs() {
        const g0 = $('.rw-bulb-g');
        const NS = 'http://www.w3.org/2000/svg';
        const mk = (name, at) => { const el = document.createElementNS(NS, name); for (const k in at) el.setAttribute(k, String(at[k])); return el; };
        let vis = 0;
        for (let slot = 0; slot < 48; slot++) {
            const big = slot % 2 === 0;
            if (big && slot === 0) continue;
            const rad = slot * 7.5 * Math.PI / 180;
            const x = 512 + 398.5 * Math.sin(rad), y = 512 - 398.5 * Math.cos(rad);
            const g = mk('g', { class: 'rw-bulb' });
            g.style.setProperty('--delay', `${-(slot * 27)}ms`);
            g.style.setProperty('--burst-delay', `${vis * 4}ms`);
            g.appendChild(mk('circle', { fill: 'url(#rwBulbHalo)', cx: x.toFixed(2), cy: y.toFixed(2), r: big ? 31 : 18 }));
            g.appendChild(mk('circle', { fill: 'url(#rwBulbCore)', cx: x.toFixed(2), cy: y.toFixed(2), r: big ? 10.8 : 5.8 }));
            if (big) g.appendChild(mk('path', { class: 'rw-bulb-spark', d: `M ${x - 17} ${y} L ${x + 17} ${y} M ${x} ${y - 17} L ${x} ${y + 17}` }));
            g0.appendChild(g);
            vis++;
        }
    })();

    // ── 칸 ──
    function setItems(list) {
        const w = list.map(it => Math.max(0, Number(it.w) || 0));
        const sum = w.reduce((a, b) => a + b, 0);
        let angleSum = 0;
        const items = list.map((it, i) => {
            const angle = sum > 0 ? 360 * w[i] / sum : 0;
            angleSum += angle;
            return { name: String(it.name == null ? '' : it.name), angle, angleSum, color: color(i, list.length) };
        });
        const sig = items.map(it => it.name + ':' + it.angle.toFixed(3)).join('|');
        if (sig === W.sig) return;
        W.sig = sig;
        W.items = items;
        // 바늘이 걸리는 못 — 칸 경계마다, 넓은 칸은 30° 안쪽 간격으로 더 박는다
        const t = [];
        items.forEach(it => {
            const sub = Math.max(1, Math.ceil(it.angle / 30 - 1e-6));
            for (let k = 0; k < sub; k++) t.push(it.angleSum - it.angle + k * it.angle / sub);
        });
        W.ticks = t.length ? t : [0, 90, 180, 270];
        drawDisc();
        updateCurrent();
    }

    /* 쉬는 판 칸 — 서버 wheel() 과 같은 셈(화면 약속 1) */
    function idleItems(r) {
        if (r.source === 'custom') return (r.custom || []).map(n => ({ name: n, w: 1 }));
        const p = lm.get('players') || {};
        const rows = (p.extra_active ? p.extra : p.list) || [];
        const contrib = r.weight === 'contrib';
        return rows.map(x => ({ name: x.name, w: contrib ? Math.max(1, parseInt(x.contribution, 10) || 0) : 1 }));
    }

    // ── 그리기(옛 drawDisc · drawLabel · drawHub 그대로) ──
    function drawDisc() {
        const c = S / 2, R = c - 1, D = Math.PI / 180;
        ctx.clearRect(0, 0, S, S);
        ctx.save();
        ctx.translate(c, c);
        const items = W.items;
        if (!items.length) { ctx.beginPath(); ctx.arc(0, 0, R, 0, 2 * Math.PI); ctx.fillStyle = '#fbe9c8'; ctx.fill(); }
        let a0 = -90;
        items.forEach(it => {
            ctx.beginPath(); ctx.moveTo(0, 0);
            ctx.arc(0, 0, R, a0 * D, (a0 + it.angle) * D);
            ctx.closePath(); ctx.fillStyle = it.color; ctx.fill();
            a0 += it.angle;
        });
        // 입체감 — 가운데는 살짝 밝게, 가장자리는 금테 밑 그늘
        const g = ctx.createRadialGradient(0, 0, R * 0.2, 0, 0, R);
        g.addColorStop(0, 'rgba(255,255,255,0.24)');
        g.addColorStop(0.6, 'rgba(255,255,255,0)');
        g.addColorStop(0.88, 'rgba(120,60,20,0.06)');
        g.addColorStop(1, 'rgba(90,40,10,0.30)');
        ctx.beginPath(); ctx.arc(0, 0, R, 0, 2 * Math.PI); ctx.fillStyle = g; ctx.fill();
        // 칸 경계 — 갈색 테 위에 금선
        if (items.length > 1) {
            [['#9a6224', 9], ['#f6cf6a', 4]].forEach(([col, lw]) => {
                ctx.strokeStyle = col; ctx.lineWidth = lw; ctx.lineCap = 'round';
                let a = -90;
                items.forEach(it => {
                    const r = a * D;
                    ctx.beginPath(); ctx.moveTo(Math.cos(r) * R * 0.25, Math.sin(r) * R * 0.25);
                    ctx.lineTo(Math.cos(r) * R, Math.sin(r) * R); ctx.stroke();
                    a += it.angle;
                });
            });
        }
        a0 = -90;
        items.forEach(it => { drawLabel(it.name, a0 + it.angle / 2, it.angle, R); a0 += it.angle; });
        drawHub(R);
        ctx.restore();
    }

    /* 칸 이름 — 가운데에서 바깥으로 읽는 방향. 칸이 좁거나 이름이 길면 줄이고, 그래도 안 되면 … */
    function drawLabel(text, midDeg, spanDeg, R) {
        if (!text) return;
        const r0 = R * 0.30, r1 = R * 0.93, L = r1 - r0;
        const span = Math.min(spanDeg, 170) * Math.PI / 180;
        const room = 2 * (r0 + L * 0.3) * Math.sin(span / 2) * 0.82;
        let s = Math.max(16, Math.min(50, room));
        ctx.font = `${s}px ${FACE}`;
        let w = ctx.measureText(text).width;
        if (w > L) { s = Math.max(18, Math.floor(s * L / w)); ctx.font = `${s}px ${FACE}`; w = ctx.measureText(text).width; }
        let t = text;
        if (w > L) {
            while (t.length > 1 && ctx.measureText(t + '…').width > L) t = t.slice(0, -1);
            t += '…';
        }
        ctx.save();
        ctx.rotate(midDeg * Math.PI / 180);
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.lineJoin = 'round';
        const x = (r0 + r1) / 2;
        ctx.lineWidth = Math.max(5, s * 0.26); ctx.strokeStyle = '#5a2d14';
        ctx.strokeText(t, x, 1);
        ctx.fillStyle = '#fff9ec';
        ctx.fillText(t, x, 1);
        ctx.restore();
    }

    /* 가운데 메달 — 금테 + 분홍 + 별 (바늘 그림과 한 벌) */
    function drawHub(R) {
        const r1 = R * 0.24, r2 = R * 0.18;
        ctx.save();
        ctx.shadowColor = 'rgba(60,25,5,.4)'; ctx.shadowBlur = 16; ctx.shadowOffsetY = 5;
        const gold = ctx.createLinearGradient(-r1, -r1, r1, r1);
        gold.addColorStop(0, '#fff0b5'); gold.addColorStop(0.45, '#f2c461'); gold.addColorStop(1, '#c0802a');
        ctx.beginPath(); ctx.arc(0, 0, r1, 0, 2 * Math.PI); ctx.fillStyle = gold; ctx.fill();
        ctx.restore();
        ctx.lineWidth = 5; ctx.strokeStyle = '#8a5a1c';
        ctx.beginPath(); ctx.arc(0, 0, r1, 0, 2 * Math.PI); ctx.stroke();
        const pink = ctx.createRadialGradient(-r2 * 0.3, -r2 * 0.4, r2 * 0.1, 0, 0, r2);
        pink.addColorStop(0, '#ffb3c0'); pink.addColorStop(0.55, '#f2687f'); pink.addColorStop(1, '#cf3f58');
        ctx.beginPath(); ctx.arc(0, 0, r2, 0, 2 * Math.PI); ctx.fillStyle = pink; ctx.fill();
        ctx.lineWidth = 3.5; ctx.strokeStyle = '#8a3444'; ctx.stroke();
        ctx.beginPath();
        for (let k = 0; k < 10; k++) {
            const r = k % 2 ? r2 * 0.28 : r2 * 0.66, a = (-90 + k * 36) * Math.PI / 180;
            if (k) ctx.lineTo(Math.cos(a) * r, Math.sin(a) * r); else ctx.moveTo(Math.cos(a) * r, Math.sin(a) * r);
        }
        ctx.closePath();
        const star = ctx.createLinearGradient(0, -r2 * 0.66, 0, r2 * 0.6);
        star.addColorStop(0, '#fff6c8'); star.addColorStop(1, '#f7c948');
        ctx.fillStyle = star; ctx.fill();
        ctx.lineJoin = 'round'; ctx.lineWidth = 4; ctx.strokeStyle = '#a8661c'; ctx.stroke();
        ctx.beginPath(); ctx.arc(0, 0, r1 - 6, -2.6, -1.6);
        ctx.lineWidth = 4; ctx.strokeStyle = 'rgba(255,255,255,.55)'; ctx.stroke();
    }

    function applyRotation() { canvas.style.transform = `rotate(${W.rotation.toFixed(3)}deg)`; }

    /* 바늘 밑 칸 = 원판 기준 (360 - 돈 각도) 자리 */
    function updateCurrent() {
        let p = (360 - W.rotation) % 360; if (p < 0) p += 360;
        let cur = null;
        for (const it of W.items) { if (p >= it.angleSum - it.angle && p < it.angleSum) { cur = it; break; } }
        if (!cur && W.items.length) cur = W.items[W.items.length - 1];
        W.current = cur ? cur.name : '';
        const txt = W.mode === 'idle' ? '' : W.current;
        if (nowEl.textContent !== txt) nowEl.textContent = txt;
    }

    function setRunning(on) {
        stageEl.classList.toggle('rw-running', on);
        if (on) stageEl.classList.remove('rw-win');
        nowEl.classList.remove('won');
    }

    // ── 돌리기 · 세우기 ──
    /* sinceMs: 서버가 [돌리기] 를 받은 뒤 지난 시간 — 늦게 붙은 창은 가속을 그만큼 건너뛴다 */
    function launch(sinceMs) {
        if (W.mode === 'stopping') return;
        W.plan = null;
        clearPointer();
        holdUntil = 0;
        const since = Math.max(0, Number(sinceMs) || 0);
        if (since >= ACCEL_SEC * 1000) {
            W.angularVelocity = MAX_SPEED;
            W.mode = 'spinning';
        } else {
            W.accelFrom = Math.max(0, W.angularVelocity);
            W.accelAt = performance.now() - since;
            W.mode = 'accelerating';
        }
        setRunning(true);
        schedule();
    }

    /* 서버가 정한 자리(angle)에 서버 시각 ends_at 까지 고르게 감속해 선다. 바퀴 수만 여기서 고른다. */
    function stopAt(st) {
        if (!W.items.length || W.mode === 'stopping') return;
        const selectAngle = Number(st.angle) || 0;
        const target = ((360 - selectAngle) % 360 + 360) % 360;
        const left = (Number(st.ends_at) || 0) - serverNow();
        if (left <= 30) {                               // 이미 섰어야 할 때 — 그 자리에 바로 세운다
            W.rotation = target;
            W.angularVelocity = 0;
            if (W.raf) { cancelAnimationFrame(W.raf); W.raf = 0; }
            finish(true);
            return;
        }
        if (!rolling()) { W.angularVelocity = MAX_SPEED; setRunning(true); }
        const duration = left / 1000;
        const nowNorm = ((W.rotation % 360) + 360) % 360;
        const delta = ((target - nowNorm) % 360 + 360) % 360;
        const entry = Math.max(W.angularVelocity, MAX_SPEED * 0.78);
        let best = null;
        for (let turns = 0; turns <= 5; turns++) {
            const dist = delta + turns * 360, v0 = 2 * dist / duration;
            const score = Math.abs(v0 - entry);
            if (!best || score < best.score) best = { dist, v0, score };
        }
        W.plan = { start: W.rotation, dist: best.dist, v0: best.v0, duration, at: performance.now() };
        W.angularVelocity = best.v0;
        W.mode = 'stopping';
        schedule();
        // ⚠️ 그림(requestAnimationFrame)은 가려진 창 · 백그라운드 탭에서 멈춘다 — 그래도 ends_at 에는 서게 시계로 한 번 더 본다
        clearTimeout(W.stopTimer);
        const plan = W.plan;
        W.stopTimer = setTimeout(() => {
            if (W.mode !== 'stopping' || W.plan !== plan) return;
            if (W.raf) { cancelAnimationFrame(W.raf); W.raf = 0; }
            W.rotation = plan.start + plan.dist; W.angularVelocity = 0;
            finish(false);
        }, left + 120);
    }

    function reset() {
        if (W.raf) { cancelAnimationFrame(W.raf); W.raf = 0; }
        clearTimeout(W.stopTimer);
        W.plan = null;
        W.rotation = 0; W.angularVelocity = 0;
        W.mode = 'idle';
        holdUntil = 0;
        finishInfo = null;
        stageEl.classList.remove('rw-running', 'rw-win');
        nowEl.classList.remove('won');
        clearPointer();
        applyRotation();
        updateCurrent();
    }

    function schedule() {
        if (!W.raf) {
            W.lastT = performance.now();
            W.raf = requestAnimationFrame(loop);
        }
    }

    function loop(now) {
        W.raf = 0;
        const dt = Math.min(Math.max(0, now - W.lastT) / 1000, 0.05);
        W.lastT = now;
        const prev = W.rotation;
        let done = false;
        if (W.mode === 'accelerating') {
            const t = Math.min(1, Math.max(0, (now - W.accelAt) / 1000 / ACCEL_SEC));
            const e = t * t * (3 - 2 * t);
            W.angularVelocity = W.accelFrom + (MAX_SPEED - W.accelFrom) * e;
            W.rotation += W.angularVelocity * dt;
            if (t >= 1) { W.angularVelocity = MAX_SPEED; W.mode = 'spinning'; }
        } else if (W.mode === 'spinning') {
            W.angularVelocity = MAX_SPEED;
            W.rotation += W.angularVelocity * dt;
        } else if (W.mode === 'stopping' && W.plan) {
            // 일정하게 감속 — 시작 속도를 남은 거리로 정했으니 정확히 목표 자리에 선다
            const p = W.plan, n = Math.min(1, Math.max(0, (now - p.at) / 1000 / p.duration));   // 그림 시각이 계획 시각보다 앞설 수 있다 — 뒤로 안 돌게
            W.rotation = p.start + p.dist * (2 * n - n * n);
            W.angularVelocity = p.v0 * (1 - n);
            if (n >= 1) { W.rotation = p.start + p.dist; W.angularVelocity = 0; done = true; }
        }
        movePointer(prev, W.rotation);
        applyRotation();
        updateCurrent();
        if (done) { finish(false); return; }
        if (W.mode === 'spinning' && W.rotation > 1e7) W.rotation %= 360;
        if (rolling()) schedule();
    }

    function finish(late) {
        clearTimeout(W.stopTimer);
        W.plan = null;
        W.rotation = ((W.rotation % 360) + 360) % 360;
        applyRotation();
        updateCurrent();
        W.mode = 'stopped';
        const info = finishInfo || {};
        holdUntil = (Number(info.ends_at) || serverNow()) + HOLD_MS;
        snapPointer(0, W.drag, true);
        stageEl.classList.remove('rw-running', 'rw-win');
        void stageEl.offsetWidth;
        stageEl.classList.add('rw-win');
        clearTimeout(W.winTimer);
        W.winTimer = setTimeout(() => stageEl.classList.remove('rw-win'), 1300);
        nowEl.classList.add('won');
        visible();                                   // 선 자리 4초(holdUntil)를 먼저 반영 — 늦게 붙은 창도 판이 보이게
        try { onStop(info, late); } catch (e) { console.warn('[룰렛] 마무리 실패 — 원판은 그대로 섭니다:', e); }
    }

    function onStop(info, late) {
        const name = info.name || W.current;
        const fresh = serverNow() - (Number(info.ends_at) || 0) < 1500;   // 늦게 붙은 창이 지난 폭죽을 터뜨리지 않게
        if (fresh && shown) boom({ particleCount: 150, spread: 80, origin: { y: 0.6 } });
        // '이름 당첨!' — 선 자리를 보여 주는 4초 동안만(늦게 붙었으면 남은 만큼)
        const leftShow = holdUntil - serverNow();
        const win = opts.stage.use('rouletteWin');
        if (win && name && leftShow > 300 && shown) win.show(name, Math.min(HOLD_MS, leftShow));
        if (!opts.monitor && info.round && doneRound !== info.round) {
            doneRound = info.round;
            lm.cmd('roulette.done', { round: info.round }).catch(() => {});
        }
    }

    // ── 바늘: 못에 걸려 밀리다가(drag) 넘는 순간 튕긴다(snap) — 원본 계산 그대로 ──
    function maxDeflect(v) { const slow = 1 - Math.min(1, Math.max(0, v / MAX_SPEED)); return 1.7 + slow * 9.6; }
    function setDrag(d) {
        W.drag = Number.isFinite(d) ? d : 0;
        pointer.style.transform = `rotate(${W.drag.toFixed(3)}deg)`;
    }
    function clearPointer() {
        clearTimeout(W.snapTimer);
        spring.classList.remove('snap'); spring.style.transform = 'rotate(0deg)';
        setDrag(0);
    }
    function snapPointer(v, from, final) {
        const slow = 1 - Math.min(1, Math.max(0, v / MAX_SPEED));
        const max = maxDeflect(v);
        const start = Math.min(Number.isFinite(from) ? from : 0, -(max * (final ? 0.92 : 0.68)));
        const kick = final ? 6.1 : 1.25 + slow * 4.65;
        const dur = final ? 430 : Math.round(Math.min(317, Math.max(62, 62 + slow * 255)));
        const st = spring.style;
        st.setProperty('--snap-from', `${start.toFixed(3)}deg`);
        st.setProperty('--snap-kick', `${kick.toFixed(3)}deg`);
        st.setProperty('--snap-rebound', `${(-kick * 0.47).toFixed(3)}deg`);
        st.setProperty('--snap-kick-small', `${(kick * 0.2).toFixed(3)}deg`);
        st.setProperty('--snap-rebound-small', `${(-kick * 0.075).toFixed(3)}deg`);
        st.setProperty('--snap-down', `${(0.35 + slow * 1.25).toFixed(3)}px`);
        st.setProperty('--snap-duration', `${dur}ms`);
        spring.classList.remove('snap'); void spring.offsetWidth; spring.classList.add('snap');
        clearTimeout(W.snapTimer);
        W.snapTimer = setTimeout(() => { spring.classList.remove('snap'); spring.style.transform = 'rotate(0deg)'; }, dur + 24);
        setDrag(0);
    }
    function movePointer(prevRot, nextRot) {
        const d = nextRot - prevRot;
        if (!(d > 0)) { setDrag(0); return; }
        const mod = x => ((x % 360) + 360) % 360;
        const p0 = mod(360 - prevRot), p1 = mod(360 - nextRot);
        let crossed = false, remain = 360, gap = 360;
        const T = W.ticks;
        for (let i = 0; i < T.length; i++) {
            const a = mod(p0 - T[i]);
            if (a > 0 && a <= d) crossed = true;
            const r = mod(p1 - T[i]);
            if (r > 0 && r < remain) remain = r;
            if (T.length > 1) { const g = mod(T[(i + 1) % T.length] - T[i]); if (g > 0 && g < gap) gap = g; }
        }
        const v = W.angularVelocity;
        if (crossed) { snapPointer(v, Math.min(W.drag, -maxDeflect(v) * 0.7), false); return; }
        const slow = 1 - Math.min(1, Math.max(0, v / MAX_SPEED));
        const arc = Math.min(7.5 + slow * 7.5, gap * 0.8);
        if (remain > arc) { setDrag(0); return; }
        const prog = Math.min(1, Math.max(0, 1 - remain / arc));
        setDrag(-maxDeflect(v) * Math.pow(prog, 1.45));
    }

    // ── 보이기 · 숨기기 ──
    /* 무대가 roulette 이거나, 방금 서서 선 자리를 보여 주는 4초 동안(무대가 바뀌었어도). 도는 중이면 무대와 상관없이 보인다
       (서버는 도는 판을 무대에 올려 둔다 — 조종실이 무대를 손으로 바꿨어도 서는 것까지는 보여 준다). */
    function visible() {
        const st = (lm.get('show') || {}).stage;
        const hold = holdUntil - serverNow();
        const on = st === 'roulette' || rolling() || hold > 0;
        shown = on && !screenCovered(lm);
        board.classList.toggle('on', shown);
        opts.stage.setMode('roulette-game', shown);
        clearTimeout(holdTimer);
        if (hold > 0 && st !== 'roulette') holdTimer = setTimeout(visible, hold + 30);
        if (!on && W.mode === 'stopped') { W.mode = 'idle'; updateCurrent(); stageEl.classList.remove('rw-win'); nowEl.classList.remove('won'); }
    }

    // ── 조각 ──
    function render(r) {
        r = r || {};
        titleEl.textContent = r.source === 'custom' ? '😈 벌칙 룰렛' : '🎡 행운의 돌림판';
        const live = r.phase === 'spinning' || r.phase === 'stopping';
        // 도는 판은 얼린 칸, 쉬는 판은 지금 설정 — 단 선 자리를 보여 주는 동안은 판을 안 바꾼다(바늘 밑 칸이 바뀌면 안 된다)
        if (live) setItems(r.items || []);
        else if (!rolling() && holdUntil - serverNow() <= 0) setItems(idleItems(r));

        const rnd = Number(r.round) || 0;
        if (rnd !== seenRound) {
            const first = seenRound === null;
            seenRound = rnd;
            stopRound = null;
            if (r.phase === 'spinning') {
                finishInfo = null;
                if (W.mode === 'stopping') { W.mode = 'idle'; W.plan = null; }
                launch(serverNow() - (Number(r.spin_at) || serverNow()));
            } else if (r.phase === 'stopping' && first) {
                finishInfo = null;
                launch(ACCEL_SEC * 1000);     // 서는 중에 붙은 창 — 돌던 것처럼 이어서 같은 자리에 세운다
            }
        }
        if (r.phase === 'stopping' && r.stop && stopRound !== rnd) {
            stopRound = rnd;
            finishInfo = { round: rnd, name: r.stop.name, ends_at: Number(r.stop.ends_at) || 0 };
            stopAt(r.stop);
        }
        if (r.phase === 'idle' && rolling()) reset();      // [초기화] · 방송 시작/끝 — 도는 중이었으면 멈춘다
        visible();
    }

    lm.on('roulette', render);
    lm.on('players', () => {
        const r = lm.get('roulette');
        if (r && r.source !== 'custom' && !(r.phase === 'spinning' || r.phase === 'stopping') && !rolling() && holdUntil - serverNow() <= 0) {
            setItems(idleItems(r));
        }
    });
    lm.on('show', visible);
    lm.on('screen', visible);

    // 글꼴이 늦게 오면 칸 글씨가 기본 글꼴로 그려진 채 남는다 — 도착하면 한 번 더 그린다
    try { document.fonts.load("40px 'Jua'", '벌칙').then(() => drawDisc()).catch(() => {}); } catch (e) {}
    drawDisc();
    applyRotation();
}
