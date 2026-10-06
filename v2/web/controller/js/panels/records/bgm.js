/* 🎵 BGM — 유튜브 링크를 붙여 넣으면 조종실 창 안에서 튼다(옛 조종실 BGM 탭 · 머리줄 미니 플레이어를 옮겼다).

   ⚠️ 방송판(OBS 소스)이 아니라 이 조종실 창에서 소리가 난다 — 방송 PC 소리로 나간다(옛 것과 같다).
   ⚠️ 바깥에서 불러오는 것이 하나 있다: 유튜브 IFrame API(https://www.youtube.com/iframe_api).
      옛 조종실도 같은 길로 틀었다. 페이지를 열 때가 아니라 BGM 탭을 처음 열 때(또는 링크를 불러올 때)만 부른다.
   - 불러오기 · 재생/멈춤 · 10초 앞뒤 · 위치 막대 · 소리 크기 · 소리 끄기. 마지막 영상 · 소리 크기는 이 컴퓨터에 기억한다.
   - 시그니처가 나오거나(대기줄에 있음) 노래방이 켜지면 잠깐 멈췄다가 끝나면 다시 튼다(옛 enterContentMode · 끌 수 있다).
   - 탭을 옮겨도 소리가 끊기지 않게 BGM 탭은 숨길 때도 화면 밖에 그려 둔다(tools_records.css).
   플레이어는 하나뿐 — 탭(mountBgmPanel)과 머리줄 미니(mountBgmMini)가 같은 것을 본다. */
import { h } from '../../util.js';

const KEY = 'lm2_bgm';
const API_URL = 'https://www.youtube.com/iframe_api';
const PLAYING = 1, PAUSED = 2, BUFFERING = 3, CUED = 5, ENDED = 0;

const B = {
    player: null, ready: false, host: null, want: null,
    id: '', title: '', author: '', state: -1, cur: 0, dur: 0,
    vol: 50, muted: false, auto: true, busy: false, wasPlaying: false,
    err: '', loading: false, subs: new Set(), timer: 0,
};

(function restore() {
    try {
        const v = JSON.parse(localStorage.getItem(KEY) || '{}');
        if (v && typeof v === 'object') {
            if (typeof v.id === 'string' && /^[\w-]{11}$/.test(v.id)) B.id = v.id;
            if (Number.isFinite(v.vol)) B.vol = Math.max(0, Math.min(100, Math.round(v.vol)));
            if (typeof v.auto === 'boolean') B.auto = v.auto;
        }
    } catch (e) { /* 기억이 없거나 막혀 있다 — 처음 값으로 */ }
})();

function save() {
    try { localStorage.setItem(KEY, JSON.stringify({ id: B.id, vol: B.vol, auto: B.auto })); } catch (e) { /* 무시 */ }
}

function notify(kind) {
    for (const fn of B.subs) { try { fn(kind || 'state'); } catch (e) { console.error('[BGM]', e); } }
}

/** 유튜브 주소 → 영상 번호(11자). watch?v= · youtu.be/ · embed/ · live/ · shorts/ · 번호만 */
export function videoId(raw) {
    const s = String(raw || '').trim();
    if (/^[\w-]{11}$/.test(s)) return s;
    const m = s.match(/(?:youtu\.be\/|\/v\/|\/u\/\w\/|embed\/|watch\?(?:.*&)?v=|[?&]v=|live\/|shorts\/)([\w-]{11})/);
    return m ? m[1] : null;
}

export function fmt(t) {
    t = Math.max(0, Math.floor(Number(t) || 0));
    const p = x => String(x).padStart(2, '0');
    return t >= 3600 ? `${Math.floor(t / 3600)}:${p(Math.floor(t / 60) % 60)}:${p(t % 60)}` : `${p(Math.floor(t / 60))}:${p(t % 60)}`;
}

/* ── 유튜브 IFrame API — 한 번만 부른다(다른 칸이 이미 불렀으면 그것을 쓴다) ── */
let apiP = null;
function loadApi() {
    if (window.YT && window.YT.Player) return Promise.resolve(window.YT);
    if (apiP) return apiP;
    apiP = new Promise((resolve, reject) => {
        const prev = window.onYouTubeIframeAPIReady;
        window.onYouTubeIframeAPIReady = function () {
            try { if (typeof prev === 'function') prev(); } catch (e) { /* 남의 것 — 무시 */ }
            resolve(window.YT);
        };
        if (!document.querySelector('script[src="' + API_URL + '"]')) {
            const s = document.createElement('script');
            s.src = API_URL;
            s.async = true;
            s.onerror = () => reject(new Error('load'));
            document.head.append(s);
        }
        setTimeout(() => reject(new Error('timeout')), 15000);
    }).catch(e => { apiP = null; throw e; });
    return apiP;
}

const ERRORS = {
    2: '영상 주소가 이상해요 — 다시 복사해 주세요',
    5: '이 영상은 여기서 틀 수 없어요(플레이어 오류)',
    100: '영상을 찾을 수 없어요(지워졌거나 비공개)',
    101: '이 영상은 다른 곳에서 틀 수 없게 막혀 있어요 — 다른 영상을 골라 주세요',
    150: '이 영상은 다른 곳에서 틀 수 없게 막혀 있어요 — 다른 영상을 골라 주세요',
};

function readMeta() {
    try {
        const d = B.player.getVideoData && B.player.getVideoData();
        if (d) {
            if (d.title) B.title = d.title;
            if (d.author) B.author = d.author;
        }
    } catch (e) { /* 아직 모른다 */ }
}

function tickTime() {
    if (!B.player || !B.ready) return;
    try {
        B.cur = B.player.getCurrentTime() || 0;
        B.dur = B.player.getDuration() || 0;
    } catch (e) { return; }
    notify('time');
}

function startTimer() {
    clearInterval(B.timer);
    B.timer = setInterval(tickTime, 500);
}

/** 영상 열기 — play=false 면 올려만 둔다(지난번 것을 되살릴 때) */
export async function openVideo(id, play) {
    B.id = id;
    B.title = '';
    B.author = '';
    B.err = '';
    B.cur = 0;
    B.dur = 0;
    B.want = { id, play: !!play };
    save();
    notify();
    if (B.player && B.ready) return applyWant();
    if (B.player || !B.host) return;           // 만드는 중(준비되면 want 를 튼다) · 아직 탭을 안 열었다
    B.loading = true;
    notify();
    let YT;
    try { YT = await loadApi(); } catch (e) {
        B.loading = false;
        B.err = '유튜브 플레이어를 못 불러왔어요 — 인터넷 연결을 확인하고 다시 눌러 주세요';
        notify();
        return;
    }
    if (B.player || !B.host) return;
    const target = h('div', { class: 'bgm-yt' });
    B.host.replaceChildren(target);
    B.player = new YT.Player(target, {
        width: '100%', height: '100%',
        playerVars: { playsinline: 1, controls: 1, rel: 0 },
        events: {
            onReady() {
                B.ready = true;
                B.loading = false;
                try {
                    B.player.setVolume(B.vol);
                    if (B.muted) B.player.mute();
                } catch (e) { /* 무시 */ }
                applyWant();
                startTimer();
                notify();
            },
            onStateChange(ev) {
                B.state = ev.data;
                if (ev.data === PLAYING || ev.data === CUED || ev.data === PAUSED) readMeta();
                if (ev.data === PLAYING) B.err = '';
                tickTime();
                notify();
            },
            onError(ev) {
                B.err = ERRORS[ev.data] || '틀지 못했어요(오류 ' + ev.data + ')';
                notify();
            },
        },
    });
}

function applyWant() {
    const w = B.want;
    if (!w || !B.player || !B.ready) return;
    B.want = null;
    try {
        if (w.play) B.player.loadVideoById(w.id);
        else B.player.cueVideoById(w.id);
    } catch (e) { B.err = '틀지 못했어요 — 다시 눌러 주세요'; }
    notify();
}

export function isPlaying() {
    return B.state === PLAYING || B.state === BUFFERING;
}

export function toggle() {
    if (!B.player || !B.ready) return;
    if (B.busy) B.wasPlaying = false;           // 시그니처 동안 손으로 누르면 끝나고 저절로 다시 틀지 않는다
    try {
        if (isPlaying()) B.player.pauseVideo();
        else B.player.playVideo();
    } catch (e) { /* 무시 */ }
}

export function skip(sec) {
    if (!B.player || !B.ready) return;
    try {
        const t = Math.max(0, (B.player.getCurrentTime() || 0) + sec);
        B.player.seekTo(B.dur ? Math.min(t, B.dur - 1) : t, true);
        setTimeout(tickTime, 120);
    } catch (e) { /* 무시 */ }
}

export function seekPct(pct) {
    if (!B.player || !B.ready || !B.dur) return;
    try { B.player.seekTo((Number(pct) / 100) * B.dur, true); } catch (e) { /* 무시 */ }
}

export function setVolume(v) {
    B.vol = Math.max(0, Math.min(100, Math.round(Number(v) || 0)));
    save();
    if (B.player && B.ready) {
        try {
            B.player.setVolume(B.vol);
            if (B.muted && B.vol > 0) { B.player.unMute(); B.muted = false; }
        } catch (e) { /* 무시 */ }
    }
    notify('vol');
}

export function toggleMute() {
    B.muted = !B.muted;
    if (B.player && B.ready) {
        try { B.muted ? B.player.mute() : B.player.unMute(); } catch (e) { /* 무시 */ }
    }
    notify('vol');
}

/** 시그니처 · 노래방이 나오는 동안(busy) 잠깐 멈추기 — 끝나면 멈추기 전에 틀고 있었을 때만 다시 튼다 */
export function setBusy(busy) {
    busy = !!busy;
    if (busy === B.busy) return;
    B.busy = busy;
    if (!B.player || !B.ready) { B.wasPlaying = false; return; }
    try {
        if (busy) {
            B.wasPlaying = B.auto && isPlaying();
            if (B.wasPlaying) B.player.pauseVideo();
        } else if (B.wasPlaying) {
            B.wasPlaying = false;
            B.player.playVideo();
        }
    } catch (e) { B.wasPlaying = false; }
    notify();
}

function busyFrom(slices) {
    const q = (slices.queue || {}).items || [];
    return q.length > 0 || !!(slices.karaoke && slices.karaoke.on);
}

/* ── 그림(아이콘) — 고정 글자라 innerHTML 로 넣어도 된다 ── */
const ICON = {
    play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.4-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5z" fill="currentColor"/></svg>',
    pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6.5" y="5" width="4" height="14" rx="1.2" fill="currentColor"/><rect x="13.5" y="5" width="4" height="14" rx="1.2" fill="currentColor"/></svg>',
    back: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 6.5v11L3.5 12zM20 6.5v11L12.5 12z" fill="currentColor"/></svg>',
    fwd: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 6.5v11l7.5-5.5zM4 6.5v11l7.5-5.5z" fill="currentColor"/></svg>',
    vol: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" fill="currentColor"/><path d="M15.5 8.5a5 5 0 0 1 0 7M18 6a8.5 8.5 0 0 1 0 12" stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round"/></svg>',
    mute: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" fill="currentColor"/><path d="M16 9.5l5 5M21 9.5l-5 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    note: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 17.5V6l10-2v11.5" stroke="currentColor" stroke-width="2" fill="none" stroke-linejoin="round"/><circle cx="6.5" cy="17.5" r="2.5" fill="currentColor"/><circle cx="16.5" cy="15.5" r="2.5" fill="currentColor"/></svg>',
};

function iconBtn(cls, label, icon, onclick) {
    const b = h('button', { type: 'button', class: cls, title: label, 'aria-label': label, onclick });
    b.innerHTML = icon;
    return b;
}

function stateText() {
    if (B.err) return ['bad', '오류'];
    if (B.loading) return ['', '불러오는 중'];
    if (!B.id) return ['', '없음'];
    if (B.busy && B.wasPlaying) return ['warn', '시그니처 동안 멈춤'];
    if (B.state === PLAYING) return ['live', '재생 중'];
    if (B.state === BUFFERING) return ['live', '불러오는 중'];
    if (B.state === ENDED) return ['', '끝남'];
    if (B.state === PAUSED) return ['warn', '멈춤'];
    return ['', B.ready ? '대기' : '준비 중'];
}

/* ── BGM 탭 ── */
export function mountBgmPanel(el, ctx) {
    const input = h('input', { type: 'text', placeholder: '유튜브 주소를 붙여 넣으세요', autocomplete: 'off', enterkeyhint: 'go', 'aria-label': '유튜브 주소' });
    const loadBtn = h('button', { type: 'button', class: 'btn pri' }, '불러오기');
    const msg = h('p', { class: 'bgm-msg', role: 'status' });
    const tag = h('span', { class: 'tag plain' }, '없음');
    const screen = h('div', { class: 'bgm-screen' },
        h('div', { class: 'bgm-empty' }, h('span', { class: 'bgm-empty-ic', 'aria-hidden': 'true' }), '불러온 영상이 없어요'));
    screen.querySelector('.bgm-empty-ic').innerHTML = ICON.note;
    const host = h('div', { class: 'bgm-host' });
    screen.append(host);
    const title = h('b', { class: 'bgm-title' }, '선택된 영상 없음');
    const author = h('span', { class: 'bgm-author muted small' });
    const cur = h('span', { class: 'bgm-time' }, '00:00');
    const dur = h('span', { class: 'bgm-time' }, '00:00');
    const prog = h('input', { type: 'range', min: 0, max: 1000, step: 1, value: 0, class: 'bgm-prog', 'aria-label': '재생 위치' });
    const backBtn = h('button', { type: 'button', class: 'btn', onclick: () => skip(-10) }, '« 10초');
    const playBtn = h('button', { type: 'button', class: 'btn pri bgm-play', onclick: toggle });
    const fwdBtn = h('button', { type: 'button', class: 'btn', onclick: () => skip(10) }, '10초 »');
    const muteBtn = iconBtn('icon-btn bgm-mute', '소리 끄기', ICON.vol, toggleMute);
    const vol = h('input', { type: 'range', min: 0, max: 100, step: 1, value: B.vol, class: 'bgm-vol', 'aria-label': 'BGM 소리 크기' });
    const volOut = h('output', { class: 'bgm-volout' }, B.vol + '%');
    const auto = h('input', { type: 'checkbox' });
    auto.checked = B.auto;

    el.classList.add('bgm-panel');
    el.append(
        h('div', { class: 'sec-head' }, h('h2', null, '🎵 BGM ', h('small', { class: 'muted' }, '유튜브')), tag),
        h('form', { class: 'bgm-load', onsubmit: e => { e.preventDefault(); load(); } }, input, loadBtn),
        msg,
        h('div', { class: 'bgm-grid' },
            screen,
            h('div', { class: 'bgm-side' },
                h('div', { class: 'bgm-meta' }, title, author),
                h('div', { class: 'bgm-seek' }, cur, prog, dur),
                h('div', { class: 'bgm-ctrl' }, backBtn, playBtn, fwdBtn),
                h('div', { class: 'bgm-volrow' }, muteBtn, vol, volOut),
                h('label', { class: 'bgm-auto' }, auto, h('span', null, '시그니처 · 노래방이 나오는 동안 잠깐 멈추기')),
                h('p', { class: 'muted small bgm-note' }, '소리는 방송판(OBS 소스)이 아니라 이 조종실 창에서 나요. 이 창을 닫거나 새로 고치면 멈춥니다.'))));

    function load() {
        const raw = input.value.trim();
        if (!raw) { input.focus(); return; }
        const id = videoId(raw);
        if (!id) {
            msg.textContent = '유튜브 주소를 알아보지 못했어요 — 주소를 다시 확인해 주세요';
            msg.dataset.lv = 'bad';
            input.setAttribute('aria-invalid', 'true');
            return;
        }
        input.removeAttribute('aria-invalid');
        input.value = '';
        msg.textContent = '';
        openVideo(id, true);
        ctx.toast('BGM 을 불러왔어요', 'ok', 1800);
    }
    input.addEventListener('input', () => input.removeAttribute('aria-invalid'));

    let dragging = false;
    prog.addEventListener('input', () => { dragging = true; cur.textContent = fmt((Number(prog.value) / 1000) * B.dur); });
    prog.addEventListener('change', () => { seekPct(Number(prog.value) / 10); dragging = false; });
    prog.addEventListener('blur', () => { dragging = false; });
    vol.addEventListener('input', () => { volOut.textContent = vol.value + '%'; setVolume(vol.value); });
    auto.addEventListener('change', () => {
        B.auto = auto.checked;
        save();
        ctx.toast(B.auto ? '시그니처 · 노래방 동안 BGM 을 잠깐 멈춰요' : '시그니처 · 노래방 동안에도 BGM 을 계속 틀어요', 'info', 2200);
    });

    // 탭이 숨겨질 때 키보드 초점이 화면 밖 칸으로 들어가지 않게(숨긴 동안에도 플레이어는 그려 둔다 — css)
    try {
        new MutationObserver(() => { el.inert = el.hidden; }).observe(el, { attributes: true, attributeFilter: ['hidden'] });
    } catch (e) { /* 오래된 브라우저 — 무시 */ }

    let last = '';
    function paint(kind) {
        if (kind === 'time' || kind === 'state') {
            if (!dragging && document.activeElement !== prog) {
                const v = B.dur ? String(Math.round((B.cur / B.dur) * 1000)) : '0';
                if (prog.value !== v) prog.value = v;
                const c = fmt(B.cur);
                if (cur.textContent !== c) cur.textContent = c;
            }
            const d = fmt(B.dur);
            if (dur.textContent !== d) dur.textContent = d;
            prog.disabled = !B.ready || !B.dur;
            if (kind === 'time') return;
        }
        if (kind === 'vol' || kind === 'state') {
            if (document.activeElement !== vol && vol.value !== String(B.vol)) { vol.value = String(B.vol); volOut.textContent = B.vol + '%'; }
            muteBtn.innerHTML = B.muted ? ICON.mute : ICON.vol;
            muteBtn.setAttribute('aria-pressed', B.muted ? 'true' : 'false');
            muteBtn.title = B.muted ? '소리 켜기' : '소리 끄기';
            muteBtn.setAttribute('aria-label', muteBtn.title);
            vol.classList.toggle('muted', B.muted);
            if (kind === 'vol') return;
        }
        const [lv, text] = stateText();
        const key = [lv, text, B.title, B.author, B.err, B.id, B.ready, isPlaying()].join('|');
        if (key === last) return;
        last = key;
        tag.className = 'tag ' + (lv || 'plain');
        tag.textContent = text;
        screen.classList.toggle('has', !!B.player);
        title.textContent = B.title || (B.id ? (B.loading || !B.ready ? '불러오는 중…' : '유튜브 영상') : '선택된 영상 없음');
        author.textContent = B.author || '';
        const playing = isPlaying();
        playBtn.innerHTML = (playing ? ICON.pause : ICON.play) + (playing ? ' 멈춤' : ' 재생');
        playBtn.setAttribute('aria-label', playing ? 'BGM 멈춤' : 'BGM 재생');
        for (const b of [backBtn, playBtn, fwdBtn]) b.disabled = !B.ready || !B.id;
        if (B.err) { msg.textContent = B.err; msg.dataset.lv = 'bad'; }
        else if (msg.dataset.lv === 'bad' && !input.getAttribute('aria-invalid')) { msg.textContent = ''; msg.dataset.lv = ''; }
    }
    B.subs.add(paint);

    // 이 탭이 플레이어 자리 — 지난번 영상이 있으면 올려만 둔다(저절로 틀지 않는다)
    B.host = host;
    if (B.id && !B.player) openVideo(B.id, false);
    paint('state');

    return { render() { /* 플레이어 소식(notify)으로 그린다 — 조각과는 상관없다 */ } };
}

/* ── 머리줄 미니 플레이어 — 영상이 올라와 있을 때만 보인다. 이름을 누르면 BGM 탭으로 ── */
export function mountBgmMini(host) {
    const ic = h('span', { class: 'bgm-mini-ic', 'aria-hidden': 'true' });
    ic.innerHTML = ICON.note;
    const name = h('button', { type: 'button', class: 'bgm-mini-name', title: 'BGM 탭 열기',
        onclick: () => { const t = document.querySelector('.tabbar .tab[data-tab="bgm"]'); if (t) { t.click(); t.scrollIntoView({ block: 'nearest', behavior: 'smooth' }); } } }, 'BGM');
    const back = iconBtn('bgm-mini-btn bgm-mini-skip', '10초 뒤로', ICON.back, () => skip(-10));
    const play = iconBtn('bgm-mini-btn bgm-mini-play', 'BGM 재생', ICON.play, toggle);
    const fwd = iconBtn('bgm-mini-btn bgm-mini-skip', '10초 앞으로', ICON.fwd, () => skip(10));
    const mute = iconBtn('bgm-mini-btn', '소리 끄기', ICON.vol, toggleMute);
    const el = h('div', { class: 'bgm-mini', hidden: true, role: 'group', 'aria-label': 'BGM' }, ic, name, back, play, fwd, mute);
    host.prepend(el);

    let last = '';
    function paint(kind) {
        if (kind === 'time') return;
        const playing = isPlaying();
        const show = !!(B.player && B.id);
        const key = [show, playing, B.title, B.muted, B.busy && B.wasPlaying, B.ready].join('|');
        if (key === last) return;
        last = key;
        el.hidden = !show;
        el.classList.toggle('on', playing);
        name.textContent = B.title || 'BGM';
        play.innerHTML = playing ? ICON.pause : ICON.play;
        play.title = playing ? 'BGM 멈춤' : (B.busy && B.wasPlaying ? '시그니처 동안 멈춤 — 누르면 지금 틀기' : 'BGM 재생');
        play.setAttribute('aria-label', play.title);
        mute.innerHTML = B.muted ? ICON.mute : ICON.vol;
        mute.title = B.muted ? '소리 켜기' : '소리 끄기';
        mute.setAttribute('aria-label', mute.title);
        mute.setAttribute('aria-pressed', B.muted ? 'true' : 'false');
        for (const b of [back, play, fwd]) b.disabled = !B.ready;
    }
    B.subs.add(paint);
    paint('state');

    return {
        /** 머리줄이 조각마다 부른다 — 시그니처 · 노래방 동안 잠깐 멈추기 */
        render(slices, view) {
            setBusy(view === 'live' && busyFrom(slices || {}));
        },
    };
}
