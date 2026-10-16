/* 🎵 BGM — 유튜브 재생 목록 · 반복(옛 조종실 BGM 탭 '유튜브 재생 목록' · 머리줄 미니 플레이어를 옮겼다, 대표님 10-07 "무한반복이랑 리스트").

   ⚠️ 방송판(OBS 소스)이 아니라 이 조종실 창에서 소리가 난다 — 방송 PC 소리로 나간다(옛 것과 같다). 폰으로 열면 폰에서 난다.
   ⚠️ 바깥에서 불러오는 것이 하나 있다: 유튜브 IFrame API(https://www.youtube.com/iframe_api).
      페이지를 열 때는 부르지 않는다 — BGM 탭을 열 때 · 조종 줄 ▶ · 주소 넣기 때만(사람이 누를 때). 그 전엔 기억해 둔 제목 글자만 보여 준다.
   재생 목록(이 브라우저 localStorage 'lm2_bgm' — 소리가 이 창에서 나므로 창을 따라간다, 옛 것도 그랬다)
     - 최대 LIST_MAX(200)곡. 영상 주소 → 한 곡, 재생목록 주소(list=) → 안 보이는 플레이어로 영상 번호들을 읽어 통째로(서버 없이).
     - 반복: all(🔁 전체 — 끝나면 처음으로, 한 곡뿐이면 그 곡을 계속) → one(🔂 한 곡) → off(➡️ 끝까지 한 번).
       ⚠️ 곡이 끝나면(ENDED) 규칙대로 다음 곡 — 예전 v2 는 '끝남' 에서 멈춰 방송 중 BGM 이 끊겼다. 셈은 nextIndex 하나(검사가 부른다).
     - 이전 · 다음 · 순서 바꾸기 · 빼기 · 비우기. 나오는 곡을 빼면 끝까지 두고, 끝나면 그 자리에 온 곡으로(옛 ytlGone).
     - 못 트는 영상(지워짐 · 퍼가기 금지)은 건너뛴다. 목록이 다 막혔으면 멈춘다(끝없이 넘기지 않게).
     - 제목: 재생 때 플레이어(getVideoData)가 알려 준 것을 곡에 적어 기억 + 서버 /api/yt/info(유튜브 공식 oEmbed)로 미리 묻기.
     - 썸네일은 안 그린다(바깥 그림 서버 i.ytimg.com 을 부르지 않는다 — 바깥 불러오기는 IFrame API 하나만).
   - 시그니처가 나오거나(대기줄에 있음) 노래방이 켜지면 잠깐 멈췄다가 끝나면 다시 튼다(옛 enterContentMode · 끌 수 있다).
   - 탭을 옮겨도 소리가 끊기지 않게 BGM 탭은 숨길 때도 화면 밖에 그려 둔다(tools_records.css).
   플레이어는 하나뿐 — 탭(mountBgmPanel)과 조종 줄(mountBgmMini, #ctl-bgm)이 같은 것을 본다.
   조종 줄에서 처음 ▶ 를 누르면 BGM 탭을 화면 밖에 미리 그려(tabs.prepare) 거기에 플레이어를 만든다 — 탭으로 옮겨 가지 않는다. */
import { h } from '../../util.js';

const KEY = 'lm2_bgm';
const API_URL = 'https://www.youtube.com/iframe_api';
const PLAYING = 1, PAUSED = 2, BUFFERING = 3, CUED = 5, ENDED = 0;
export const LIST_MAX = 200;
export const MODES = { all: '🔁 전체 반복', one: '🔂 한 곡 반복', off: '➡️ 반복 끔' };
const MODE_ORDER = ['all', 'one', 'off'];
const ID_RE = /^[\w-]{11}$/;

const B = {
    player: null, ready: false, host: null, want: null,
    id: '', title: '', author: '', state: -1, cur: 0, dur: 0,
    vol: 50, muted: false, auto: true, busy: false, wasPlaying: false,
    err: '', loading: false, subs: new Set(), timer: 0,
    list: [], idx: 0, mode: 'all', gone: false, badRun: 0, msg: '', msgLv: '', msgT: 0,
    ctx: null, preparing: false,
};

(function restore() {
    try {
        const v = JSON.parse(localStorage.getItem(KEY) || '{}');
        if (v && typeof v === 'object') {
            if (Number.isFinite(v.vol)) B.vol = Math.max(0, Math.min(100, Math.round(v.vol)));
            if (typeof v.auto === 'boolean') B.auto = v.auto;
            if (MODES[v.mode]) B.mode = v.mode;
            if (Array.isArray(v.list)) {
                for (const x of v.list) {
                    if (!x || !ID_RE.test(x.id) || B.list.some(y => y.id === x.id)) continue;
                    B.list.push({ id: x.id, title: typeof x.title === 'string' ? x.title.slice(0, 200) : '', author: typeof x.author === 'string' ? x.author.slice(0, 100) : '' });
                    if (B.list.length >= LIST_MAX) break;
                }
            }
            // 예전(한 곡만 기억하던 때)에 올려 둔 곡을 첫 곡으로
            if (!B.list.length && typeof v.id === 'string' && ID_RE.test(v.id)) B.list.push({ id: v.id, title: '', author: '' });
            B.idx = Math.max(0, Math.min(B.list.length - 1, Math.floor(Number(v.idx) || 0)));
            const it = B.list[B.idx];
            if (it) { B.id = it.id; B.title = it.title; B.author = it.author; }
        }
    } catch (e) { /* 기억이 없거나 막혀 있다 — 처음 값으로 */ }
})();

function save() {
    try {
        localStorage.setItem(KEY, JSON.stringify({
            id: B.id, vol: B.vol, auto: B.auto, mode: B.mode, idx: B.idx,
            list: B.list.map(x => ({ id: x.id, title: x.title || '', author: x.author || '' })),
        }));
    } catch (e) { /* 무시 */ }
}

function notify(kind) {
    for (const fn of B.subs) { try { fn(kind || 'state'); } catch (e) { console.error('[BGM]', e); } }
}

/** 탭 안내 글 — 잘된 소식은 9초 뒤 저절로 지운다(오류는 남긴다) */
function say(text, lv) {
    B.msg = text || '';
    B.msgLv = lv || '';
    clearTimeout(B.msgT);
    if (B.msg && B.msgLv !== 'bad') {
        const was = B.msg;
        B.msgT = setTimeout(() => { if (B.msg === was) say(''); }, 9000);
    }
    notify('list');
}

/** 유튜브 주소 → 영상 번호(11자). watch?v= · youtu.be/ · embed/ · live/ · shorts/ · 번호만 */
export function videoId(raw) {
    const s = String(raw || '').trim();
    if (ID_RE.test(s)) return s;
    const m = s.match(/(?:youtu\.be\/|\/v\/|\/u\/\w\/|embed\/|watch\?(?:.*&)?v=|[?&]v=|live\/|shorts\/)([\w-]{11})/);
    return m ? m[1] : null;
}

/** 재생목록 주소의 list= 번호(옛 extractYtListId) */
export function listId(raw) {
    const m = String(raw || '').match(/[?&]list=([A-Za-z0-9_-]{10,64})/);
    return m ? m[1] : null;
}

/** 다음에 틀 곡 번호 — mode: all · one · off, i: 지금 곡, n: 곡 수, manual: 사람이 [다음] 을 눌렀다.
    곡이 끝나서(ENDED) 부를 때: 한 곡 반복이면 그 곡, 전체 반복이면 끝에서 처음으로, 반복 끔이면 끝에서 멈춤(-1).
    [다음] 을 누르면 반복 모드와 상관없이 다음 곡(끝이면 처음으로 — 옛 ytlNext(true)). 곡이 없으면 -1. */
export function nextIndex(mode, i, n, manual) {
    n = Math.floor(Number(n) || 0);
    if (n <= 0) return -1;
    i = Math.max(0, Math.min(n - 1, Math.floor(Number(i) || 0)));
    if (manual) return (i + 1) % n;
    if (mode === 'one') return i;
    if (i + 1 < n) return i + 1;
    return mode === 'off' ? -1 : 0;
}

/** 이전 곡 번호 — 처음에서 누르면 맨 끝(옛 ytlPrev) */
export function prevIndex(i, n) {
    n = Math.floor(Number(n) || 0);
    if (n <= 0) return -1;
    return (((Math.floor(Number(i) || 0) - 1) % n) + n) % n;
}

/** 목록에 영상 번호들을 더한다(순수 — 검사용) → {list, added, firstNew, dup, over} */
export function addTo(list, ids, max) {
    const out = list.slice();
    let added = 0, firstNew = -1, dup = -1, over = 0;
    for (const id of ids || []) {
        if (!ID_RE.test(String(id || ''))) continue;
        const at = out.findIndex(x => x.id === id);
        if (at >= 0) { if (dup < 0) dup = at; continue; }
        if (out.length >= (max || LIST_MAX)) { over++; continue; }
        out.push({ id, title: '', author: '' });
        if (firstNew < 0) firstNew = out.length - 1;
        added++;
    }
    return { list: out, added, firstNew, dup, over };
}

export function fmt(t) {
    t = Math.max(0, Math.floor(Number(t) || 0));
    const p = x => String(x).padStart(2, '0');
    return t >= 3600 ? `${Math.floor(t / 3600)}:${p(Math.floor(t / 60) % 60)}:${p(t % 60)}` : `${Math.floor(t / 60)}:${p(t % 60)}`;
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

function curItem() {
    return B.gone ? null : (B.list[B.idx] || null);
}

function readMeta() {
    try {
        const d = B.player.getVideoData && B.player.getVideoData();
        if (!d) return;
        if (d.title) B.title = d.title;
        if (d.author) B.author = d.author;
        // 목록의 그 곡에도 적어 둔다 — 다음에 페이지를 열면 유튜브를 안 불러도 제목이 보인다
        const it = B.list.find(x => x.id === (d.video_id || B.id));
        if (it && d.title && (it.title !== d.title || it.author !== (d.author || ''))) {
            it.title = String(d.title).slice(0, 200);
            it.author = String(d.author || '').slice(0, 100);
            save();
            notify('list');
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
    const it = B.list.find(x => x.id === id);
    B.id = id;
    B.title = (it && it.title) || '';
    B.author = (it && it.author) || '';
    B.err = '';
    B.cur = 0;
    B.dur = 0;
    B.want = { id, play: !!play };
    save();
    notify();
    if (B.player && B.ready) return applyWant();
    if (B.player || B.loading) return;           // 만드는 중 — 준비되면 want 를 튼다
    if (!B.host && B.ctx && B.ctx.tabs && B.ctx.tabs.prepare) {
        // 조종 줄에서 처음 ▶ — BGM 탭을 화면 밖에 미리 그려 플레이어 자리를 만든다(탭으로 옮겨 가지 않는다)
        B.preparing = true;
        try { B.ctx.tabs.prepare('bgm'); } finally { B.preparing = false; }
    }
    if (!B.host) return;                        // 아직 플레이어 자리가 없다(탭을 열면 올린다)
    B.loading = true;
    notify();
    let YT;
    try { YT = await loadApi(); } catch (e) {
        B.loading = false;
        B.err = '유튜브 플레이어를 못 불러왔어요 — 인터넷 연결을 확인하고 다시 눌러 주세요';
        notify();
        return;
    }
    if (B.player || !B.host) { B.loading = false; return; }
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
                if (ev.data === PLAYING) {
                    B.err = '';
                    B.badRun = 0;
                    const c = curItem();
                    if (c && c.bad) { c.bad = false; notify('list'); }
                }
                tickTime();
                notify();
                if (ev.data === ENDED) onEnded();          // 🔁 반복 · 다음 곡
            },
            onError(ev) {
                B.err = ERRORS[ev.data] || '틀지 못했어요(오류 ' + ev.data + ')';
                notify();
                onBad();
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

/* ── 재생 목록 ── */
/** 목록의 i 번째 곡 — autoplay=false 면 올려만 둔다 */
export function playAt(i, autoplay) {
    if (!B.list.length) return;
    B.idx = ((Math.floor(i) % B.list.length) + B.list.length) % B.list.length;
    B.gone = false;
    if (autoplay !== false) B.wasPlaying = false;   // 손으로 고른 곡 — 시그니처 끝나고 저절로 다시 트는 것과 섞이지 않게
    notify('list');
    openVideo(B.list[B.idx].id, autoplay !== false);
}

/** 다음 곡 — manual: 사람이 눌렀다(반복 모드와 상관없이 다음) */
export function next(manual) {
    const n = B.list.length;
    if (!n) return;
    if (B.gone) { playAt(B.idx, true); return; }       // 나오던 곡을 뺐다 — 그 자리에 온 곡이 다음이다
    const j = nextIndex(B.mode, B.idx, n, manual);
    if (j < 0) { say('목록 끝까지 다 틀었어요 (반복 끔)'); return; }
    if (j === B.idx && !manual && B.player && B.ready && B.id === B.list[j].id) {   // 한 곡 반복 · 한 곡뿐인 전체 반복 — 같은 곡을 처음부터
        try { B.player.seekTo(0, true); B.player.playVideo(); return; } catch (e) { /* 아래로 */ }
    }
    playAt(j, true);
}

export function prev() {
    if (!B.list.length) return;
    playAt(B.gone ? B.idx - 1 : prevIndex(B.idx, B.list.length), true);
}

function onEnded() {
    if (!B.list.length) return;
    next(false);
}

function onBad() {
    const c = curItem();
    if (c) { c.bad = true; notify('list'); }
    B.badRun++;
    if (!B.list.length || B.badRun >= B.list.length) {
        say('목록의 영상을 틀지 못했어요 — 주소를 확인해 주세요', 'bad');
        return;
    }
    say('못 트는 영상이라 다음 곡으로 넘어가요', 'bad');
    setTimeout(() => next(false), 800);
}

export function cycleMode() {
    B.mode = MODE_ORDER[(MODE_ORDER.indexOf(B.mode) + 1) % MODE_ORDER.length];
    save();
    notify('list');
}

export function setMode(m) {
    if (!MODES[m]) return;
    B.mode = m;
    save();
    notify('list');
}

export function addIds(ids) {
    const r = addTo(B.list, ids, LIST_MAX);
    const wasEmpty = !B.list.length;
    B.list = r.list;
    if (r.added && wasEmpty) B.idx = 0;                     // 빈 목록에 처음 넣었다
    save();
    notify('list');
    fillTitles();
    return r;
}

export function move(i, d) {
    const j = i + d;
    if (i < 0 || j < 0 || i >= B.list.length || j >= B.list.length) return;
    const it = B.list.splice(i, 1)[0];
    B.list.splice(j, 0, it);
    if (B.idx === i) B.idx = j; else if (B.idx === j) B.idx = i;
    save();
    notify('list');
}

export function remove(i) {
    if (i < 0 || i >= B.list.length) return;
    if (i === B.idx && !B.gone && isPlaying()) B.gone = true;    // 나오는 곡은 끝까지 두고, 끝나면 이 자리 곡으로
    B.list.splice(i, 1);
    if (i < B.idx) B.idx--;
    B.idx = Math.max(0, Math.min(B.idx, B.list.length - 1));
    if (!B.list.length) B.gone = false;
    save();
    notify('list');
}

export function clearList() {
    B.list = [];
    B.idx = 0;
    B.gone = false;
    save();
    say('목록을 비웠어요 — 지금 나오는 곡은 끝까지 나와요');
}

/** 지금 목록 모습(검사 · 화면 확인용 — 복사본) */
export function listState() {
    return { list: B.list.map(x => Object.assign({}, x)), idx: B.idx, mode: B.mode, gone: B.gone, id: B.id, state: B.state };
}

/* 제목 미리 묻기 — 서버가 유튜브 공식 oEmbed 에 묻는다(/api/yt/info). 못 받으면 '영상 번호' 로 둔다(재생하면 채워진다) */
const titleTried = new Set();
let titleBusy = false;
async function fillTitles() {
    if (titleBusy) return;
    titleBusy = true;
    try {
        for (;;) {
            const it = B.list.find(x => !x.title && !titleTried.has(x.id));
            if (!it) break;
            titleTried.add(it.id);
            try {
                const r = await fetch('/api/yt/info?id=' + encodeURIComponent(it.id), { cache: 'no-store', credentials: 'same-origin' });
                const j = r.ok ? await r.json() : null;
                if (j && j.title && !it.title) {
                    it.title = String(j.title).slice(0, 200);
                    it.author = String(j.author || '').slice(0, 100);
                    if (it.id === B.id && !B.title) { B.title = it.title; B.author = it.author; }
                    save();
                    notify('list');
                }
            } catch (e) { /* 다음에 */ }
        }
    } finally { titleBusy = false; }
}

/** 유튜브 재생목록(list=) — 안 보이는 플레이어로 영상 번호들만 읽어 와 목록 뒤에 붙인다(최대 LIST_MAX) */
export async function importPlaylist(lid) {
    say('재생목록을 읽는 중…');
    let YT;
    try { YT = await loadApi(); } catch (e) { say('유튜브 플레이어를 못 불러왔어요 — 인터넷 연결을 확인하고 다시 넣어 주세요', 'bad'); return; }
    const wasIdle = !isPlaying();
    const holder = h('div', { class: 'bgm-probe', 'aria-hidden': 'true' });
    const inner = h('div');
    holder.append(inner);
    document.body.append(holder);
    let done = false, p = null, poll = 0;
    const finish = ids => {
        if (done) return;
        done = true;
        clearInterval(poll);
        try { if (p && p.destroy) p.destroy(); } catch (e) { /* 무시 */ }
        holder.remove();
        ids = (ids || []).filter(id => ID_RE.test(String(id || '')));
        if (!ids.length) { say('재생목록을 못 읽었어요 — 비공개이거나 없는 목록이에요', 'bad'); return; }
        const r = addIds(ids);
        const left = ids.length - r.added;
        say(`재생목록에서 ${r.added}곡을 넣었어요` + (left ? ` (이미 있던 곡 · 넘친 곡 ${left}개는 뺐어요)` : '') +
            (r.over ? ` — 목록은 ${LIST_MAX}곡까지예요` : ''), r.added ? '' : 'bad');
        if (wasIdle && r.firstNew >= 0) playAt(r.firstNew, true);
    };
    try {
        p = new YT.Player(inner, {
            width: 320, height: 180,
            playerVars: { listType: 'playlist', list: lid, autoplay: 0 },
            events: {
                onReady() {
                    let n = 0;
                    poll = setInterval(() => {
                        let ids = null;
                        try { ids = p.getPlaylist(); } catch (e) { ids = null; }
                        if ((ids && ids.length) || ++n > 30) finish(ids);
                    }, 300);
                },
                onError() { finish(null); },
            },
        });
    } catch (e) { finish(null); }
    setTimeout(() => finish(null), 15000);
}

export function toggle() {
    if (!B.player || !B.ready) {
        // 아직 플레이어가 없다 — 지금 곡을 처음으로 튼다(여기서 처음 유튜브를 부른다)
        if (B.list.length) playAt(B.idx, true);
        else if (B.id) openVideo(B.id, true);
        return;
    }
    if (B.busy) B.wasPlaying = false;           // 시그니처 동안 손으로 누르면 끝나고 저절로 다시 틀지 않는다
    try {
        if (isPlaying()) B.player.pauseVideo();
        else if (B.state === ENDED && B.gone) next(false);
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

/** main.js 가 한 번 부른다 — 조종 줄 ▶ 가 BGM 탭을 미리 그리고(ctx.tabs.prepare) 제목을 누르면 탭을 연다 */
export function bindBgm(ctx) {
    B.ctx = ctx;
}

/* ── 그림(아이콘) — 고정 글자라 innerHTML 로 넣어도 된다 ── */
const ICON = {
    play: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.4-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5z" fill="currentColor"/></svg>',
    pause: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="6.5" y="5" width="4" height="14" rx="1.2" fill="currentColor"/><rect x="13.5" y="5" width="4" height="14" rx="1.2" fill="currentColor"/></svg>',
    next: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5.5v13l10-6.5z" fill="currentColor"/><rect x="16.6" y="5.5" width="2.6" height="13" rx="1" fill="currentColor"/></svg>',
    prev: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M19 5.5v13L9 12z" fill="currentColor"/><rect x="4.8" y="5.5" width="2.6" height="13" rx="1" fill="currentColor"/></svg>',
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
    return ['', '대기'];
}

function songTitle() {
    if (B.title) return B.title;
    if (!B.id) return '선택된 영상 없음';
    return B.loading ? '불러오는 중…' : '영상 ' + B.id;
}

/* ── BGM 탭 ── */
export function mountBgmPanel(el, ctx) {
    if (!B.ctx) B.ctx = ctx;
    const input = h('input', { type: 'text', placeholder: '유튜브 영상 · 재생목록 주소를 붙여 넣으세요', autocomplete: 'off', enterkeyhint: 'go', 'aria-label': '유튜브 주소' });
    const loadBtn = h('button', { type: 'submit', class: 'btn pri' }, '＋ 목록에 넣기');
    const msg = h('p', { class: 'bgm-msg', role: 'status' });
    const tag = h('span', { class: 'tag plain' }, '없음');
    const screen = h('div', { class: 'bgm-screen' },
        h('div', { class: 'bgm-empty' }, h('span', { class: 'bgm-empty-ic', 'aria-hidden': 'true' }), '▶ 를 누르면 여기에 영상이 나와요'));
    screen.querySelector('.bgm-empty-ic').innerHTML = ICON.note;
    const host = h('div', { class: 'bgm-host' });
    screen.append(host);
    const title = h('b', { class: 'bgm-title' }, '선택된 영상 없음');
    const author = h('span', { class: 'bgm-author muted small' });
    const cur = h('span', { class: 'bgm-time' }, '0:00');
    const dur = h('span', { class: 'bgm-time' }, '0:00');
    const prog = h('input', { type: 'range', min: 0, max: 1000, step: 1, value: 0, class: 'bgm-prog', 'aria-label': '재생 위치' });
    const prevBtn = iconBtn('btn bgm-prev', '이전 곡', ICON.prev, () => prev());
    const backBtn = h('button', { type: 'button', class: 'btn bgm-skip', title: '10초 뒤로', onclick: () => skip(-10) }, '« 10초');
    const playBtn = h('button', { type: 'button', class: 'btn pri bgm-play', onclick: toggle });
    const fwdBtn = h('button', { type: 'button', class: 'btn bgm-skip', title: '10초 앞으로', onclick: () => skip(10) }, '10초 »');
    const nextBtn = iconBtn('btn bgm-next', '다음 곡', ICON.next, () => next(true));
    const muteBtn = iconBtn('icon-btn bgm-mute', '소리 끄기', ICON.vol, toggleMute);
    const vol = h('input', { type: 'range', min: 0, max: 100, step: 1, value: B.vol, class: 'bgm-vol', 'aria-label': 'BGM 소리 크기' });
    const volOut = h('output', { class: 'bgm-volout' }, B.vol + '%');
    const auto = h('input', { type: 'checkbox' });
    auto.checked = B.auto;

    // 재생 목록
    const modeBtn = h('button', { type: 'button', class: 'btn sm bgm-mode', title: '누를 때마다 전체 반복 → 한 곡 반복 → 반복 끔', onclick: cycleMode });
    const count = h('span', { class: 'bgm-count' });
    const clearBtn = h('button', { type: 'button', class: 'btn sm bgm-clear', title: '목록을 다 지웁니다(지금 나오는 곡은 끝까지 나와요)' }, '비우기');
    const ol = h('ol', { class: 'bgm-list', 'aria-label': 'BGM 재생 목록' });
    const empty = h('p', { class: 'empty bgm-list-empty' }, '유튜브에서 영상이나 재생목록 주소를 복사해 위에 붙여 넣으세요. 넣은 순서대로 이어서 나와요.');
    let lastList = null;
    const allBtn = h('button', { type: 'button', class: 'btn xs bgm-all', hidden: true,
        onclick: () => { const l = lastList; lastList = null; paintList(); if (l) importPlaylist(l); } }, '이 재생목록 전체 넣기');

    el.classList.add('bgm-panel');
    el.append(
        h('div', { class: 'sec-head' }, h('h2', null, '🎵 BGM ', h('small', { class: 'muted' }, '유튜브 재생 목록')), tag),
        h('form', { class: 'bgm-load', onsubmit: e => { e.preventDefault(); load(); } }, input, loadBtn),
        h('div', { class: 'bgm-msgrow' }, msg, allBtn),
        h('div', { class: 'bgm-grid' },
            screen,
            h('div', { class: 'bgm-side' },
                h('div', { class: 'bgm-meta' }, title, author),
                h('div', { class: 'bgm-seek' }, cur, prog, dur),
                h('div', { class: 'bgm-ctrl' }, prevBtn, backBtn, playBtn, fwdBtn, nextBtn),
                h('div', { class: 'bgm-volrow' }, muteBtn, vol, volOut),
                h('label', { class: 'bgm-auto' }, auto, h('span', null, '시그니처 · 노래방이 나오는 동안 잠깐 멈추기')),
                h('p', { class: 'muted small bgm-note' }, '소리는 방송판(OBS 소스)이 아니라 이 조종실 창에서 나요. 이 창을 닫거나 새로 고치면 멈춥니다.'))),
        h('div', { class: 'bgm-listbox' },
            h('div', { class: 'bgm-listbar' }, h('b', { class: 'bgm-listcap' }, '재생 목록'), modeBtn, count, clearBtn),
            empty, ol));

    function load() {
        const raw = input.value.trim();
        if (!raw) { input.focus(); return; }
        const id = videoId(raw), lid = listId(raw);
        if (!id && !lid) {
            say('유튜브 주소를 알아보지 못했어요 — 주소를 다시 확인해 주세요', 'bad');
            input.setAttribute('aria-invalid', 'true');
            return;
        }
        input.removeAttribute('aria-invalid');
        input.value = '';
        lastList = null;
        if (!id) { importPlaylist(lid); return; }              // 재생목록 주소 — 통째로
        const idle = !isPlaying();
        const r = addIds([id]);
        if (r.added) {
            if (idle) { playAt(r.firstNew, true); say(`목록 ${r.firstNew + 1}번에 넣고 바로 틀었어요`); }
            else say(`목록 ${r.firstNew + 1}번에 넣었어요 — 앞 곡이 끝나면 차례로 나와요`);
        } else if (r.dup >= 0) {
            say(`이미 목록 ${r.dup + 1}번에 있어요 — 그 줄을 누르면 바로 틀어요`);
        } else {
            say(`목록이 가득 찼어요(${LIST_MAX}곡) — 몇 곡 빼고 넣어 주세요`, 'bad');
        }
        lastList = lid;                                         // 재생목록 안의 영상 주소 — 원하면 목록 전체도
        paintList();
    }
    input.addEventListener('input', () => input.removeAttribute('aria-invalid'));

    clearBtn.addEventListener('click', async () => {
        if (!B.list.length) return;
        const ok = await ctx.confirm({ title: '재생 목록 비우기', body: `재생 목록 ${B.list.length}곡을 다 지웁니다.\n지금 나오는 곡은 끝까지 나와요.`, ok: '비우기', cancel: '그대로' });
        if (ok) clearList();
    });

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
        el.inert = el.hidden;
        new MutationObserver(() => { el.inert = el.hidden; }).observe(el, { attributes: true, attributeFilter: ['hidden'] });
    } catch (e) { /* 오래된 브라우저 — 무시 */ }

    /* 목록 줄 — 곡 id 로 줄을 기억해 바뀐 줄만 다시 쓴다(200줄을 통째로 갈지 않는다) */
    const rows = new Map();
    function rowOf(id) {
        let r = rows.get(id);
        if (r) return r;
        const no = h('span', { class: 'bgm-no' });
        const t = h('b', { class: 'bgm-lt' });
        const a = h('span', { class: 'bgm-la' });
        const pick = h('button', { type: 'button', class: 'bgm-pick', title: '눌러서 이 곡 틀기' }, no, h('span', { class: 'bgm-ltx' }, t, a));
        const up = h('button', { type: 'button', class: 'bgm-act', title: '위로', 'aria-label': '위로' }, '↑');
        const down = h('button', { type: 'button', class: 'bgm-act', title: '아래로', 'aria-label': '아래로' }, '↓');
        const del = h('button', { type: 'button', class: 'bgm-act bgm-del', title: '목록에서 빼기', 'aria-label': '목록에서 빼기' }, '✕');
        const li = h('li', { class: 'bgm-row', 'data-id': id }, pick, h('span', { class: 'bgm-acts' }, up, down, del));
        const at = () => B.list.findIndex(x => x.id === id);
        pick.addEventListener('click', () => { const i = at(); if (i >= 0) playAt(i, true); });
        up.addEventListener('click', () => move(at(), -1));
        down.addEventListener('click', () => move(at(), 1));
        del.addEventListener('click', () => remove(at()));
        r = { li, no, t, a, up, down, sig: '' };
        rows.set(id, r);
        return r;
    }
    function paintMsg() {
        const text = B.msg || B.err || '';
        if (msg.textContent !== text) msg.textContent = text;
        msg.dataset.lv = B.msg ? B.msgLv : (B.err ? 'bad' : '');
        allBtn.hidden = !lastList;
    }
    function paintList() {
        const keep = new Set(B.list.map(x => x.id));
        for (const [id, r] of rows) if (!keep.has(id)) { r.li.remove(); rows.delete(id); }
        B.list.forEach((it, i) => {
            const r = rowOf(it.id);
            const now = i === B.idx && !B.gone;
            const sig = [i, now, it.title, it.author, !!it.bad, B.list.length].join('|');
            if (sig !== r.sig) {
                r.sig = sig;
                r.li.classList.toggle('now', now);
                r.li.classList.toggle('bad', !!it.bad);
                r.no.textContent = now ? '▶' : String(i + 1);
                r.t.textContent = it.title || ('영상 ' + it.id);
                r.t.title = r.t.textContent;
                r.a.textContent = it.bad ? '못 트는 영상이라 건너뛰어요' : (it.author || '');
                r.up.disabled = i === 0;
                r.down.disabled = i === B.list.length - 1;
            }
            if (ol.children[i] !== r.li) ol.insertBefore(r.li, ol.children[i] || null);
        });
        empty.hidden = B.list.length > 0;
        clearBtn.disabled = !B.list.length;
        modeBtn.textContent = MODES[B.mode];
        modeBtn.classList.toggle('on', B.mode !== 'off');
        modeBtn.setAttribute('aria-label', '반복: ' + MODES[B.mode] + ' — 누르면 바뀜');
        count.textContent = B.list.length ? `${B.gone ? '—' : B.idx + 1} / ${B.list.length}곡 · 최대 ${LIST_MAX}` : '';
        paintMsg();
    }

    let last = '';
    function paint(kind) {
        if (kind === 'list') { paintList(); kind = 'state'; }
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
        paintMsg();
        const [lv, text] = stateText();
        const key = [lv, text, B.title, B.author, B.err, B.id, B.ready, isPlaying(), B.list.length, B.loading, !!B.player].join('|');
        if (key === last) return;
        last = key;
        tag.className = 'tag ' + (lv || 'plain');
        tag.textContent = text;
        screen.classList.toggle('has', !!B.player);
        title.textContent = songTitle();
        title.title = title.textContent;
        author.textContent = B.author || '';
        const playing = isPlaying();
        playBtn.innerHTML = (playing ? ICON.pause : ICON.play) + (playing ? ' 멈춤' : ' 재생');
        playBtn.setAttribute('aria-label', playing ? 'BGM 멈춤' : 'BGM 재생');
        playBtn.disabled = (!B.list.length && !B.id) || B.loading;
        for (const b of [backBtn, fwdBtn]) b.disabled = !B.ready || !B.id;
        for (const b of [prevBtn, nextBtn]) b.disabled = B.list.length < 1;
    }
    B.subs.add(paint);

    // 이 탭이 플레이어 자리. 조종 줄 ▶ 로 미리 그리는 중이면(preparing) 부른 쪽이 마저 튼다.
    // 그냥 탭을 열었으면 지난번 곡을 올려만 둔다(저절로 틀지 않는다) — 이때 처음 유튜브를 부른다.
    B.host = host;
    if (!B.player && !B.preparing) {
        if (B.want) openVideo(B.want.id, B.want.play);
        else if (B.id) openVideo(B.id, false);
    }
    paint('list');
    fillTitles();

    return { render() { /* 플레이어 소식(notify)으로 그린다 — 조각과는 상관없다 */ } };
}

/* ── 조종 줄 BGM(#ctl-bgm, 시안 B) — 제목 · 1:42 / 3:58 · ▶/⏸ · ⏭ 다음 곡 · 'BGM 소리' 막대.
   목록에 곡이 있으면 보인다(유튜브를 아직 안 불렀어도 기억해 둔 제목으로). 제목을 누르면 BGM 탭. ── */
export function mountBgmMini(host) {
    const ic = h('span', { class: 'bgm-mini-ic', 'aria-hidden': 'true' });
    ic.innerHTML = ICON.note;
    const nameT = h('b', { class: 'bgm-mini-t' }, 'BGM');
    const timeT = h('em', { class: 'bgm-mini-time' }, '');
    const name = h('button', { type: 'button', class: 'bgm-mini-name', title: 'BGM 탭 열기',
        onclick: () => {
            if (B.ctx && B.ctx.tabs) { B.ctx.tabs.open('bgm'); return; }
            const t = document.querySelector('.tabbar .tab[data-tab="bgm"]');
            if (t) t.click();
        } },
        nameT, timeT);
    const play = iconBtn('bgm-mini-btn bgm-mini-play', 'BGM 재생', ICON.play, toggle);
    const nxt = iconBtn('bgm-mini-btn bgm-mini-next', '다음 곡', ICON.next, () => next(true));
    const volCap = h('span', { class: 'lbl bgm-mini-lbl' }, 'BGM 소리');
    const vol = h('input', { type: 'range', class: 'sld bgm-mini-vol', min: 0, max: 100, step: 1, value: B.vol, 'aria-label': 'BGM 소리 크기' });
    const el = h('div', { class: 'bgm-mini', hidden: true, role: 'group', 'aria-label': 'BGM' }, ic, name, play, nxt, volCap, vol);
    host.prepend(el);
    let holding = false;
    vol.addEventListener('pointerdown', () => { holding = true; });
    vol.addEventListener('pointerup', () => { holding = false; });
    vol.addEventListener('blur', () => { holding = false; });
    vol.addEventListener('input', () => setVolume(vol.value));

    let last = '';
    function paint(kind) {
        if (kind === 'vol' || kind === 'state' || kind === 'list') {
            if (!holding && document.activeElement !== vol && vol.value !== String(B.vol)) vol.value = String(B.vol);
            vol.classList.toggle('muted', B.muted);
        }
        const t = B.dur ? `${fmt(B.cur)} / ${fmt(B.dur)}` : (B.list.length ? `${B.gone ? '—' : B.idx + 1} / ${B.list.length}곡` : '');
        const tt = t + (B.mode === 'one' ? ' · 🔂' : (B.mode === 'all' && B.list.length > 1 ? ' · 🔁' : ''));
        if (timeT.textContent !== tt) timeT.textContent = tt;
        if (kind === 'time' || kind === 'vol') return;
        const playing = isPlaying();
        const show = !!(B.list.length || (B.player && B.id));
        const key = [show, playing, B.title, B.id, B.busy && B.wasPlaying, B.ready, B.list.length, B.loading, B.err].join('|');
        if (key === last) return;
        last = key;
        el.hidden = !show;
        el.classList.toggle('on', playing);
        nameT.textContent = songTitle();
        name.title = (B.title || 'BGM') + ' — 누르면 BGM 탭';
        play.innerHTML = playing ? ICON.pause : ICON.play;
        play.title = playing ? 'BGM 멈춤' : (B.busy && B.wasPlaying ? '시그니처 동안 멈춤 — 누르면 지금 틀기' : 'BGM 재생');
        play.setAttribute('aria-label', play.title);
        play.disabled = !!B.loading;
        nxt.disabled = B.list.length < 1;
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
