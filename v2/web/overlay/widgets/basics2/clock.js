/* ⏱️ 서버 시계 — 안내 전광판 · 시작 화면 카운트다운이 같이 쓴다(옛 serverTimeOffset).
   왜: 전광판은 '지금이 몇 번째 회차인가' 를 시계로 계산한다. 방송판이 몇 개든(OBS · 폰 미리보기) 같은 문구가
       같은 순간에 같은 자리를 흐르려면 모두 **서버 시계**로 세야 한다. 카운트다운도 OBS 컴퓨터 시계가 틀려도 같은 초.
   어떻게: 공용 연결의 lm.serverNow()(쪽지 · ping 마다 오는 서버 now 로 맞춘 시계)를 쓴다.
           그게 없는 옛 client.js 면 GET /api/time 을 세 번 재서 왕복이 제일 짧았던 것을 믿는다(10분마다 다시).
   ⚠️ 못 맞췄으면(서버가 안 닿음) 이 컴퓨터 시계 그대로 — 화면이 멈추지는 않는다. */

let offset = 0;
let lmRef = null;
let started = false;

export function serverNow() {
    if (lmRef && typeof lmRef.serverNow === 'function') {
        const v = Number(lmRef.serverNow());
        if (v > 0) return v;
    }
    return Date.now() + offset;
}

async function syncOnce() {
    let best = null;
    for (let i = 0; i < 3; i++) {
        try {
            const t0 = performance.now(), w0 = Date.now();
            const r = await fetch('/api/time', { cache: 'no-store' });
            const rtt = performance.now() - t0;
            const j = await r.json();
            const now = Number(j && j.now) || 0;
            if (now > 0 && (!best || rtt < best.rtt)) best = { rtt, off: now - Math.round(w0 + rtt / 2) };
        } catch (e) { /* 다음 번에 다시 */ }
    }
    if (best) offset = best.off;
}

export function startClock(lm) {
    if (lm) lmRef = lm;
    if (started) return;
    started = true;
    if (lmRef && typeof lmRef.serverNow === 'function') return;     // 공용 연결이 맞춰 준다
    syncOnce();
    setInterval(syncOnce, 10 * 60 * 1000);
}
