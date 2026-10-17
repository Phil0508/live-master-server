/* 🎬 엔딩 크레딧 흐름 셈 — 화면을 안 만진다(검사가 node 로 바로 부른다 · test_credits.Web).
   서버(credits.py)는 '언제(at) · 몇 px(offset) 흘렀나 · 멈춤 · 속도' 만 적는다. 지금 자리는 방송판이 서버 시계로 센다
   → OBS 가 다시 붙어도 · 방송판이 여러 개여도 같은 자리.
   ⚠️ 속도 값은 서버 credits.py SPEEDS 와 같아야 한다(검사가 맞대 본다). */

export const CANVAS_H = 1920;
// 폰 안전지대(115~954) — 그 아래는 채팅에 가린다. 마무리 글은 이 가운데에서 멈춘다.
export const SAFE_TOP = 115, SAFE_BOTTOM = 954;
export const SAFE_MID = (SAFE_TOP + SAFE_BOTTOM) / 2;
export const SPEEDS = { slow: 45, normal: 75, fast: 130 };   // px/초(1080×1920 기준)

/** 멈출 자리(px) — 마무리 글 가운데(내용 위끝에서 잰 값)가 안전지대 가운데에 올 때. 못 쟀으면 내용 끝으로. */
export function stopAt(contentH, outroMid) {
    const mid = Number(outroMid) > 0 ? Number(outroMid) : Number(contentH) || 0;
    return Math.max(0, CANVAS_H - SAFE_MID + mid);
}

/** 지금 흐른 거리(px) — 0 ~ stop 사이로 자른다 */
export function posAt(c, nowMs, stop) {
    if (!c) return 0;
    let p = Number(c.offset) || 0;
    if (c.on && !c.paused) p += Math.max(0, (Number(nowMs) - (Number(c.at) || 0)) / 1000) * (SPEEDS[c.speed] || SPEEDS.normal);
    const max = Number(stop);
    if (isFinite(max) && max >= 0) p = Math.min(p, max);
    return Math.max(0, p);
}

/** 내용 위끝의 화면 y — 처음(0)엔 화면 바로 아래(1920)에서 시작해 위로 올라간다 */
export function shiftY(pos) {
    return CANVAS_H - (Number(pos) || 0);
}
