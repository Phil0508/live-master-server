/* 🧰 게임판(주사위 · 시그뒤집기 · 대결 · 퇴근빵 · 지옥탈출) 공용 도구 — 화면(DOM)을 따로 만들지 않는다.
   (주사위판을 옮기며 만들었고, 같은 묶음의 다른 판도 같이 쓴다 — 파일 이름이 dice_ 로 시작하는 까닭)

   1) 서버 시계  serverNow()
      시그뒤집기 타이머(expiresAt) · 카드 뒤집은 때(flippedAt) · 대결 끝 시각(end_ms)은 전부 **서버 시계**로 찍혀 온다.
      OBS PC 시계가 몇 초 어긋나면 Date.now() 로 그냥 빼서는 남은 시간이 통째로 틀린다(옛 serverTimeOffset 과 같은 이유).
      GET /api/time 의 now(ms)로 잰다(왕복을 재서 반만큼 보정 — client.js 의 serverNow 보다 정확하다).
      왕복이 가장 짧았던 것을 믿는다(반 왕복만큼이 오차의 상한). 처음 세 번 · 그 뒤 2분마다.
      ⚠️ 주사위 굴림은 이 시계를 **안 쓴다** — 서버 약속대로 '받은 때' 부터 plan 을 잰다(시계를 비교해 기다리면 늦게 나왔다).
         시계는 '20초 넘게 묵은 굴림인가' 와 시그뒤집기 · 대결에만 쓴다.

   2) 소리  sfx(name) · blip() · beep() · explosion() · sgClear(i) · sgAllClear()
      옛 방송판의 만든 소리(SFX_TUNE · sgBlip · playBeep · playExplosion)를 그대로 옮겼다 — 파일 없이 브라우저가 만든다.
      시그뒤집기 CLEAR 는 /sfx/list 에 clear1~5 가 다 있으면 그 음원을 쓴다(옛 것과 같다).
      🔇 조종실 [효과음] 스위치(look.sfx = false)면 이 파일의 소리를 전부 안 낸다(주사위 · 대결 삑 · 펑 · 시그뒤집기 CLEAR) —
         무대(stage.sfxOn)에게 그때그때 묻는다. ⚠️ 옛 스위치는 이름 붙은 효과음만 막아 대결 삑 · CLEAR 는 계속 울렸다 — v2 는 다 막는다.
      ⚠️ ?monitor=1(미리보기)은 소리를 안 낸다(옛 IS_MONITOR). ⚠️ 옛 '소리 담당 창'(여러 창 중 하나만 소리)은 아직 없다 —
         v2 시그니처 재생도 같다. 방송판을 둘 띄우면 둘 다 운다.

   3) 판 보이기  makeFader(wrap, stage)
      opacity/visibility 를 0.4초에 걸쳐 바꾸고, 다 숨으면 display:none — 칸 상자가 0 이 되어야
      게이지 딱지(stage.bands)가 안 보이는 판을 피해 다니지 않는다.

   4) 시작 · 끝 화면  coverOn(lm) — screen.mode 가 start/end 면 판을 내린다(옛 body.stage-on). */

import { isLeader } from '../../audio_lead.js';   // 🔊 방송판이 여러 개면 소리는 담당 창 하나만

// ── 1) 서버 시계 ──
let clockOffset = 0, clockRtt = Infinity, clockStarted = false;

async function clockSample() {
    const t0 = Date.now();
    try {
        const r = await fetch('/api/time', { cache: 'no-store' });
        const j = await r.json();
        const t1 = Date.now();
        const rtt = t1 - t0;
        if (j && typeof j.now === 'number' && isFinite(j.now)) {
            // 더 짧은 왕복이거나, 지난 값이 오래돼 믿기 어려우면(1.5배까지) 바꾼다
            if (rtt <= clockRtt * 1.5) {
                clockOffset = j.now - (t0 + t1) / 2;
                clockRtt = Math.min(clockRtt, rtt);
            }
        }
    } catch (e) { /* 못 재면 지난 값(처음엔 0 — 같은 PC 면 맞다) */ }
}

export function startClock() {
    if (clockStarted) return;
    clockStarted = true;
    clockSample();
    setTimeout(clockSample, 1500);
    setTimeout(clockSample, 4000);
    setInterval(() => { clockRtt = clockRtt * 2 + 50; clockSample(); }, 120000);   // 오래된 값은 덜 믿는다
}

export function serverNow() { return Date.now() + clockOffset; }

// ── 2) 소리 ──
let muted = false, actx = null, stageRef = null;
const sfxOff = () => !!(stageRef && stageRef.sfxOn && !stageRef.sfxOn()) || !isLeader();   // 🔇 조종실에서 효과음을 껐거나 · 소리 담당 창이 아니다

function ac() {
    if (muted || sfxOff()) return null;
    try {
        if (!actx) actx = new (window.AudioContext || window.webkitAudioContext)();
        if (actx && actx.state === 'suspended') actx.resume();
    } catch (e) { actx = null; }
    return actx;
}

export function soundInit(opts) {
    if (opts && opts.monitor) muted = true;
    if (opts && opts.stage) stageRef = opts.stage;      // 🔇 효과음 스위치를 물어볼 곳
}

/* 짧은 삑 — 옛 sgBlip(freq, dur, vol, type) */
export function blip(freq, dur, vol, type) {
    try {
        const c = ac();
        if (!c) return;
        const t0 = c.currentTime;
        const osc = c.createOscillator(), gain = c.createGain();
        osc.type = type || 'triangle';
        osc.frequency.setValueAtTime(freq, t0);
        gain.gain.setValueAtTime(0.0001, t0);
        gain.gain.exponentialRampToValueAtTime(vol, t0 + 0.012);
        gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
        osc.connect(gain); gain.connect(c.destination);
        osc.start(t0); osc.stop(t0 + dur + 0.02);
    } catch (e) { /* 소리는 실패해도 게임은 계속된다 */ }
}

// [주파수, 시작 지연 ms, 길이 초, 크기, 파형] — 옛 SFX_TUNE 의 주사위 소리
const SFX_TUNE = {
    'dice-roll':  [[300, 0, .05, .10, 'square'], [380, 60, .05, .10, 'square'], [460, 120, .06, .10, 'square']],
    'dice-score': [[784, 0, .10, .26], [1047, 90, .18, .26]],
    'dice-sig':   [[659, 0, .10, .26], [880, 90, .10, .26], [1175, 180, .26, .28]],
    'dice-key':   [[1319, 0, .08, .24], [1568, 80, .08, .24], [2093, 160, .24, .20, 'sine']],
    'dice-miss':  [[220, 0, .16, .22, 'sawtooth'], [155, 130, .30, .20, 'sawtooth']],
    // 🏁 한 바퀴 — 제일 크게
    'dice-start': [[523, 0, .12, .30], [659, 120, .12, .30], [784, 240, .12, .30], [1047, 360, .50, .32]],
};

export function sfx(name, scale) {
    if (muted) return;
    try {
        const tune = SFX_TUNE[name];
        if (!tune) return;
        tune.forEach(n => setTimeout(() => blip(n[0], n[2], n[3] * (scale || 1), n[4]), n[1]));
    } catch (e) {}
}

/* 대결 타이머 삑 · 펑 — 옛 playBeep · playExplosion */
export function beep(freq, type, dur, vol) {
    try {
        const c = ac();
        if (!c) return;
        const osc = c.createOscillator(), gain = c.createGain();
        osc.type = type; osc.frequency.setValueAtTime(freq, c.currentTime);
        gain.gain.setValueAtTime(vol, c.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, c.currentTime + dur);
        osc.connect(gain); gain.connect(c.destination);
        osc.start(); osc.stop(c.currentTime + dur);
    } catch (e) {}
}

export function explosion() {
    try {
        const c = ac();
        if (!c) return;
        const size = c.sampleRate * 2.0;
        const buffer = c.createBuffer(1, size, c.sampleRate);
        const data = buffer.getChannelData(0);
        for (let i = 0; i < size; i++) data[i] = Math.random() * 2 - 1;
        const noise = c.createBufferSource(); noise.buffer = buffer;
        const filter = c.createBiquadFilter(); filter.type = 'lowpass'; filter.frequency.value = 800;
        const gain = c.createGain();
        gain.gain.setValueAtTime(2.0, c.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, c.currentTime + 1.5);
        noise.connect(filter); filter.connect(gain); gain.connect(c.destination);
        noise.start();
    } catch (e) {}
}

/* 🃏 시그뒤집기 CLEAR — 음원 파일 5개(sounds/siggame/clear1~5.mp3, 1~4 짧은 타격 · 5 긴 마무리)를 먼저 쓴다.
   ⚠️ 하나씩 받아보지 않는다 — /sfx/list 로 한 번 묻고 있는 것만(없는 것마다 404 가 쌓인다).
   ⚠️ 다섯 개가 다 준비돼야 파일 방식. 아니면 몇 번째냐에 따라 음이 올라가는 삑(옛 것과 같다). */
const SG_N = 5;
const sgFiles = [];
let sgReady = false, sgLoading = false;

function sgLoad() {
    if (sgLoading || muted) return;
    sgLoading = true;
    fetch('/sfx/list', { cache: 'no-store' }).then(r => r.json()).then(j => {
        const files = (j && j.files) || {};
        const have = [];
        for (let i = 1; i <= SG_N; i++) { const f = files['siggame/clear' + i]; if (!f) return; have.push(f); }
        let ok = 0, done = 0;
        have.forEach((f, i) => {
            const a = new Audio('/sfx/' + f);
            a.preload = 'auto';
            const fin = good => { if (a._n) return; a._n = 1; done++; if (good) ok++; if (done === SG_N) sgReady = ok === SG_N; };
            a.addEventListener('canplaythrough', () => fin(true), { once: true });
            a.addEventListener('error', () => fin(false), { once: true });
            sgFiles[i] = a;
        });
    }).catch(() => {});
}

function sgPlayFile(index) {
    const src = sgFiles[Math.min(index, SG_N - 1)];
    if (!sgReady || !src) return false;
    try {
        const a = src.cloneNode();          // 겹쳐 나야 한다(올클리어는 0.35초 간격으로 다섯 번)
        a.volume = 0.85;
        const p = a.play();
        if (p && p.catch) p.catch(() => {});
        return true;
    } catch (e) { return false; }
}

export function sgSoundsPrepare() { sgLoad(); }
export function sgClear(index) {
    if (muted || sfxOff()) return;
    sgLoad();
    if (sgPlayFile(index)) return;
    const scale = [523, 587, 659, 784, 880, 988, 1047];   // 도레미…
    blip(scale[Math.min(index, scale.length - 1)], 0.16, 0.30);
}
export function sgAllClear() {
    if (muted) return;
    if (sgReady) return;        // 파일이면 마지막 clear5(4.5초 마무리음)가 그대로 울린다 — 겹치지 않게
    [523, 659, 784, 1047].forEach((f, i) => setTimeout(() => blip(f, 0.5, 0.34, 'sawtooth'), i * 70));
}

// ── 3) 판 보이기 ──
export function makeFader(wrap, stage) {
    let on = null, timer = null;
    wrap.style.display = 'none';
    return function set(want) {
        want = !!want;
        if (want === on) return;
        on = want;
        clearTimeout(timer);
        if (want) {
            wrap.style.display = '';
            void wrap.offsetWidth;                 // 처음 보일 때도 스르륵(트랜지션의 출발점)
            wrap.classList.add('gb-on');
        } else {
            wrap.classList.remove('gb-on');
            timer = setTimeout(() => {
                if (on) return;
                wrap.style.display = 'none';
                if (stage && stage.layoutChanged) stage.layoutChanged();
            }, 450);
        }
        if (stage && stage.layoutChanged) stage.layoutChanged();
    };
}

// ── 4) 시작 · 끝 화면 ──
export function coverOn(lm) {
    const m = (lm.get('screen') || {}).mode;
    return m === 'start' || m === 'end';
}

/* 지금 오는 것이 실시간 쪽지인가(붙은 직후 통째로 받은 것이 아니라) — main.js 의 isFresh 가 실시간이면 무엇이든 true 다 */
export function isLive(opts) {
    try { return !!(opts && opts.isFresh && opts.isFresh(0)); } catch (e) { return false; }
}

/* 캔버스(1080×1920) 좌표로 잰 상자 — 배율이 걸려 있어도 캔버스 기준 */
export function canvasRect(el) {
    const cv = document.getElementById('canvas');
    if (!cv || !el) return { x: 0, y: 0, w: 0, h: 0 };
    const cr = cv.getBoundingClientRect();
    const sc = (cr.width / 1080) || 1;
    const r = el.getBoundingClientRect();
    return { x: (r.left - cr.left) / sc, y: (r.top - cr.top) / sc, w: r.width / sc, h: r.height / sc };
}
