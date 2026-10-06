/* 🔊 이 묶음의 효과음 — 목표 달성('goal') · 모금함 쨍그랑('jar-coin'). 옛 playSfx 그대로.
   ① /sfx/list 에 같은 이름의 음원 파일(예: sounds/goal.mp3)이 있으면 그 파일을 튼다(파일만 넣으면 코드를 안 고쳐도 바뀐다).
   ② 없으면 아래 적어 둔 음으로 브라우저가 만든다(옛 SFX_TUNE 의 두 줄).
   - ?monitor=1(미리보기)은 소리를 안 낸다. 소리는 실패해도 방송이 멈추면 안 된다 — 전부 감싼다.
   - 🔇 조종실 [효과음] 스위치(look.sfx = false)면 안 낸다 — 무대(stage.sfxOn)에게 그때그때 묻는다(옛 sfx_enabled).
   - 🔊 방송판이 여러 개면 소리 담당 창 하나만 낸다(audio_lead.js — 옛 isAudioLeader). */

import { isLeader } from '../../audio_lead.js';   // 🔊 방송판이 여러 개면 소리는 담당 창 하나만

// [주파수, 시작 지연 ms, 길이 초, 크기, 파형]
const TUNE = {
    // 🪙 동전이 유리병에 떨어지는 소리 — 쇳소리라 높은 배음을 겹친다
    'jar-coin': [[2489, 0, .05, .20], [4186, 8, .04, .09], [3322, 16, .07, .15], [1661, 34, .13, .17]],
    'goal':     [[523, 0, .14, .30], [784, 140, .14, .30], [1047, 280, .14, .30], [1319, 420, .55, .32]],
};

let muted = false, actx = null, files = null, stageRef = null;
const fileAudio = {};

export function sfxInit(opts) {
    if (opts && opts.monitor) muted = true;
    if (opts && opts.stage) stageRef = opts.stage;      // 🔇 효과음 스위치를 물어볼 곳
    if (files || muted) return;
    files = {};
    // ⚠️ 하나씩 받아보지 않는다 — 없는 것마다 404 가 쌓인다. 한 번 묻고 있는 것만 받아 둔다
    fetch('/sfx/list', { cache: 'no-store' }).then(r => r.json()).then(j => {
        files = (j && j.files) || {};
        Object.keys(TUNE).forEach(name => {
            if (!files[name]) return;
            try {
                const a = new Audio('/sfx/' + files[name]);
                a.preload = 'auto';
                a.addEventListener('canplaythrough', () => { fileAudio[name] = a; }, { once: true });
            } catch (e) {}
        });
    }).catch(() => {});
}

function blip(freq, dur, vol, type) {
    try {
        if (!actx) actx = new (window.AudioContext || window.webkitAudioContext)();
        if (actx.state === 'suspended') actx.resume();
        const t0 = actx.currentTime;
        const osc = actx.createOscillator(), gain = actx.createGain();
        osc.type = type || 'triangle';
        osc.frequency.setValueAtTime(freq, t0);
        gain.gain.setValueAtTime(0.0001, t0);
        gain.gain.exponentialRampToValueAtTime(vol, t0 + 0.012);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
        osc.connect(gain); gain.connect(actx.destination);
        osc.start(t0); osc.stop(t0 + dur + 0.02);
    } catch (e) { /* 소리 하나 때문에 방송이 멈추면 안 된다 */ }
}

export function playSfx(name, scale) {
    if (muted) return;
    if (stageRef && stageRef.sfxOn && !stageRef.sfxOn()) return;      // 🔇 조종실에서 효과음을 껐다
    if (!isLeader()) return;                                           // 🔊 다른 방송판 창이 소리 담당
    try {
        const f = fileAudio[name];
        if (f) {
            const a = f.cloneNode();                    // 겹쳐 나야 하므로 매번 복제(하나를 쓰면 앞 소리가 끊긴다)
            a.volume = Math.max(0, Math.min(1, 0.85 * (scale || 1)));
            const p = a.play();
            if (p && p.catch) p.catch(() => {});
            return;
        }
        (TUNE[name] || []).forEach(n => setTimeout(() => blip(n[0], n[2], n[3] * (scale || 1), n[4]), n[1]));
    } catch (e) {}
}
