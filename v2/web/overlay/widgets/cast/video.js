/* 🐉 대형 연출 영상 — cast.video {id, name, at, stop?}(10-23 대표님 — 드리미나로 만든 용 연출).
   /overlay/fxvideos/<이름>.webm 을 한 번 튼다. 영상은 검은 배경을 뺀 투명 webm(VP9 + 알파)이라 방송 화면 위에 용 · 빛만 남는다.
   다 틀면(ended) · 걷기(stop) · 20초 안전장치로 내린다. 소리는 소리 담당 창 하나만(audio_lead) · 미리보기(?monitor=1)는 소리 없이.
   새 신호만(watchCast — 다시 붙었을 때 지난 연출이 또 나오지 않게).
   영상이 커서(하나에 20~30MB · 60프레임) 방송판이 뜨고 5초 뒤 미리 통째로 받아 둔다 — 처음 틀 때 끊기지 않게. 미리보기 창은 안 받는다(틀 때 받는다).
   🏦🐉 stage.provide('castVideo') — 시그니처 재생(widgets/signature.js)이 계좌 대형 연출(대기줄 줄의 fx_video)을 시그니처 앞에 튼다:
       has(name) · play(name) → 다 틀면(끝 · 오류 · 걷기 · 20초 안전장치) 풀리는 약속 · stop(). */
import { watchCast } from './fresh.js';
import { isLeader } from '../../audio_lead.js';

const FILES = { dragon: '/overlay/fxvideos/dragon.webm', angel: '/overlay/fxvideos/angel.webm', emblem: '/overlay/fxvideos/emblem.webm' };
const SAFETY_MS = 20000;
const PRELOAD_MS = 5000;

export function mount(root, lm, opts) {
    root.classList.add('cast-video');
    root.setAttribute('aria-hidden', 'true');
    const v = document.createElement('video');
    v.className = 'cv-video';
    v.playsInline = true;
    v.preload = 'auto';
    root.appendChild(v);
    let timer = 0;
    const ready = {};                                       // 미리 받아 둔 것(blob 주소)
    if (!opts.monitor) setTimeout(() => {
        for (const [k, u] of Object.entries(FILES)) {
            fetch(u).then(r => (r.ok ? r.blob() : null)).then(b => { if (b) ready[k] = URL.createObjectURL(b); }).catch(() => { /* 틀 때 받는다 */ });
        }
    }, PRELOAD_MS);
    let onEnd = null;                                       // 시그니처 앞 연출 — 내려갈 때 풀어 줄 약속
    const hide = () => {
        clearTimeout(timer);
        v.classList.remove('on');
        try { v.pause(); } catch (e) { /* 이미 멈춤 */ }
        const f = onEnd;
        onEnd = null;
        if (f) f();
    };
    v.addEventListener('ended', hide);
    v.addEventListener('error', hide);                      // 못 틀면 바로 내린다(시그니처가 20초 기다리지 않게)

    function play(row) {
        if (!row || row.stop || !FILES[row.name]) { hide(); return; }
        start(row.name);
    }
    function start(name) {
        v.src = ready[name] || FILES[name];
        v.currentTime = 0;
        v.muted = !!opts.monitor || !isLeader();
        v.classList.add('on');
        const go = v.play();
        if (go && go.catch) go.catch(() => { v.muted = true; v.play().catch(() => hide()); });   // 자동재생이 막히면 소리 없이라도
        clearTimeout(timer);
        timer = setTimeout(hide, SAFETY_MS);
    }
    watchCast(lm, opts, 'video', play);
    opts.stage.provide('castVideo', {
        has: name => !!FILES[name],
        play(name) {
            return new Promise(res => {
                if (!FILES[name]) { res(false); return; }
                hide();                                     // 틀던 것이 있으면 내리고(그 약속은 풀고) 새로
                onEnd = () => res(true);
                start(name);
            });
        },
        stop() { hide(); },
    });
}
