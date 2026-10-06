/* 💡 조명 위젯(네온 · 아우디)이 같이 쓰는 작은 도구 — 화면(DOM)은 만들지 않는다.

   lights 조각(서버 domain/lights.py): color('#rrggbb' · 'RAINBOW' · 'OFF') · audi · speed(초) · colors[9]
   조명이 보이는 때(옛 handleData 그대로):
     - 방송 중이고(옛 것은 방송 꺼짐이면 조명 코드까지 오지 않았다)
     - 시그니처가 나오는 동안(stage 'reaction' — 옛 reaction_mode)
     - 네온은 color 가 OFF 가 아닐 때, 아우디는 audi 가 켜졌을 때 */

export const SPEED_DEFAULT = 1.5;

export function lightsOf(lm) {
    return lm.get('lights') || { color: 'OFF', audi: false, speed: SPEED_DEFAULT };
}

/* 조명 속도(초) — 옛 방송판: d.neon_speed || 1.5 */
export function speedOf(L) {
    const v = Number(L && L.speed);
    return v > 0 && isFinite(v) ? v : SPEED_DEFAULT;
}

/* 조명을 켤 자리인가(방송 중 · 시그니처 중) — 네온 · 아우디 공통 */
export function reactionLive(lm, stage) {
    return !!((lm.get('session') || {}).live) && stage.mode('reaction');
}

/* 지금 나오는(또는 곧 나올) 시그니처 — 대기줄 맨 앞(옛 reaction_queue[0]) */
export function headItem(lm) {
    const q = lm.get('queue') || {};
    return (q.items || [])[0] || null;
}

/* 금액대별 네온 연출. 색이 아니라 '움직임' 으로 등급을 보여 준다
   (색은 시청자가 서열로 못 읽지만 움직임은 바로 읽힌다. 색은 조명 단추 몫). 기준은 여기만 고치면 된다(옛 neonTierClass). */
export function neonTierClass(amount) {
    const a = parseInt(amount, 10) || 0;
    if (a >= 2000000) return 'tier-charge';   // 200만 · 차징→폭발
    if (a >= 1000000) return 'tier-pulse';    // 100만 · 맥동
    if (a >= 500000)  return 'tier-wave';     //  50만 · 파동
    if (a >= 300000)  return 'tier-blink';    //  30만 · 점멸
    if (a >= 200000)  return 'tier-spark';    //  20만 · 반짝임
    if (a >= 100000)  return 'tier-sweep';    //  10만 · 듀얼 스윕
    return 'tier-flow';                       //  그 미만 · 흐름
}
export const TIERS = ['tier-flow', 'tier-sweep', 'tier-spark', 'tier-blink', 'tier-wave', 'tier-pulse', 'tier-charge'];

/* 지금 상태가 바뀔 때마다 fn() — 조각(lights · session · queue) · 무대 모드(reaction) */
export function watch(lm, stage, fn) {
    const run = () => { try { fn(); } catch (e) { console.error('[조명]', e); } };
    lm.on('lights', run);
    lm.on('session', run);
    lm.on('queue', run);
    stage.onMode(name => { if (name === 'reaction') run(); });
    run();
}
