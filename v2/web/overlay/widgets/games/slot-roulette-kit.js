/* 🧰 퀴즈 · 핀볼 · 룰렛 · 슬롯 위젯이 같이 쓰는 작은 도구(games_a 묶음 전용) — 화면(DOM)은 만들지 않는다.

   - serverNow()   서버 시계(ms). 룰렛이 서는 순간(stop.ends_at) · 슬롯 릴이 서는 순간(ends_at) · 핀볼 시작(started_at)은
                   **서버 시각**이라 OBS PC 시계가 몇 초 틀려도 창마다 같은 때 서게 하려면 서버 시계로 재야 한다.
                   games_b 의 dice_kit.js 시계(GET /api/time · 왕복이 가장 짧은 잼)를 같이 쓴다 — 창 하나에 시계 하나.
   - loadScript()  /vendor 의 스크립트를 한 번만 붙인다(폭죽 · box2d · 핀볼 맵). index.html 은 다른 묶음 몫이라 여기서 붙인다.
   - screenCovered(lm)  시작 · 끝 화면이 떠 있나(dice_kit 의 coverOn — 옛 body.stage-on 이 게임판을 내리던 것).
   - rng(seed)     씨앗 난수(mulberry32 — 옛 pbRng 그대로). 같은 씨앗이면 어느 창에서든 같은 수.
   - boom(opts)    폭죽(옛 confetti 호출) — 파일을 못 읽었어도 게임은 그대로 간다. */
import { startClock, serverNow as kitNow, coverOn } from './dice_kit.js';

startClock();
export function serverNow() { return kitNow(); }
export function screenCovered(lm) { return coverOn(lm); }

const scripts = {};
/* ready: 이미 읽혔는지 알아보는 함수(예: () => typeof Box2D === 'function') — 남이 먼저 붙여 다 읽힌 뒤면
   load 가 다시 안 오므로 그걸로 본다. */
export function loadScript(src, ready) {
    if (scripts[src]) return scripts[src];
    scripts[src] = new Promise((resolve, reject) => {
        try { if (ready && ready()) return resolve(); } catch (e) {}
        const have = [...document.scripts].find(s => s.getAttribute('src') === src);
        if (have && have.dataset.loaded === '1') return resolve();
        const s = have || document.createElement('script');
        s.addEventListener('load', () => { s.dataset.loaded = '1'; resolve(); }, { once: true });
        s.addEventListener('error', () => { delete scripts[src]; reject(new Error('못 읽음: ' + src)); }, { once: true });
        if (!have) { s.src = src; document.head.appendChild(s); }
    });
    return scripts[src];
}


export function rng(seed) {
    let a = (seed >>> 0) || 1;
    return function () {
        a |= 0; a = (a + 0x6D2B79F5) | 0;
        let t = Math.imul(a ^ (a >>> 15), 1 | a);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}

/* 🎉 폭죽 — canvas-confetti 1.9.3(vendor). 처음 부를 때 파일을 받는다. */
const CONFETTI = '/vendor/confetti.browser.min.js';
const confettiReady = () => typeof window.confetti === 'function';
loadScript(CONFETTI, confettiReady).catch(() => {});
export function boom(o) {
    try {
        if (confettiReady()) window.confetti(o);
        else loadScript(CONFETTI, confettiReady).then(() => { try { window.confetti(o); } catch (e) {} }).catch(() => {});
    } catch (e) { /* 폭죽이 안 터져도 판은 끝나야 한다 */ }
}

export function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, m =>
        ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
}
