/* 💸 후원 콘솔 따로 열기(console.html) — 옛 manual_send.html(/manual · /manual_send) 처럼 후원 콘솔만 있는 페이지(대표님 10-24
   "그 안에 있던 모습들 전부 다"). 옛 탭 여섯을 같은 순서 · 같은 이름으로 세우고, 속은 조종실 탭을 그대로 얹는다(새로 안 만든다).
     수동 송출    panels/ops/console.js(🏦 계좌 입금 추천 · 열쇠 · 미리보기 · 빠른 선택 · ×N · 장부에 넣기)
                  + 접힌 칸: 🏦 은행 확장 거울 · 📱 폰 입금알림 앱(panels/ops/bankmirror.js — 조종실 🖥️ 시스템 탭과 같은 칸)
     대기열       queue.js(멈춤 · 건너뛰기 · 전부 지우기 · 빼기 · ×N 다 틀기 · 소리) + 여기서 더한 것: 멈춤 안내 줄 · 시그 사진
     후원 순위    panels/records/donors.js(이번 방송 순위 · 순위에서 빼기) + 여기서 더한 것: 합계 · 후원자 수 카드 · 1~3위 메달
     이펙트       panels/ops/opfx.js(조종실 후원 연출 · 대형 연출 영상)
     고액 영상    panels/ops/media.js(금액대 영상 틀기 · 멈추기 · 주소 · 파일 올리기 · 노래방)
     시그니처 관리 panels/sig/admin.js(목록 · 찾기 · 새로 · 고치기 · 방송에 틀기 · 지우기 · 되살리기)
   틀은 sigpage.js(sig.html)와 같다 — 연결 하나(kind 'console' — 🖥️ 시스템 탭 '💸 후원 콘솔'), 조각이 오면 열린 탭만 다시 그린다.
   탭 배지는 닫혀 있어도 늘 고친다: 수동 송출 '🏦 2'(아직 안 쓴 계좌 입금 — bankBadge) · 대기열 '3'(시그니처 대기줄 수).
   마지막 탭은 이 브라우저에 기억(lm2_console_tab — 개인 창 등에서 못 쓰면 그냥 첫 탭). 주소 끝 #queue 처럼 탭 id 를 붙이면 그 탭부터.
   로그인 안 됐으면 이 페이지에서 바로 비밀번호(login.js — 조종실과 같은 쿠키, 한 번이면 둘 다 된다).
   ⚠️ 탭을 못 그려도(오류) 다른 탭은 그대로 — 탭마다 따로 감싼다. ⚠️ alert() · confirm() 금지(util.js confirmBox) · 소리 없음. */
import { h, num, toast, confirmBox, makeRun } from './util.js';
import { mountLogin } from './login.js';
import { mountConsole } from './panels/ops/console.js';
import { bankBadge } from './panels/ops/bank.js';
import { mountBankMirror, mountBankApp } from './panels/ops/bankmirror.js';
import { mountQueue } from './queue.js';
import { mountDonors } from './panels/records/donors.js';
import { mountOpFx } from './panels/ops/opfx.js';
import { mountMedia } from './panels/ops/media.js';
import { mountSigAdmin } from './panels/sig/admin.js';
import { initBack, tabChanged } from './backnav.js';       // ◀ 뒤로가기 — 창 닫기 → 이전 탭 → '한 번 더 누르면 나가요'(10-24)

const KEY = 'lm2_console_tab';

/* ── 탭 여섯(옛 manual_send.html 순서 · 이름 그대로) ── */
const TABS = [
    { id: 'send', label: '수동 송출', icon: '📤', mount: mountSend, badge: bankBadge },
    { id: 'queue', label: '대기열', icon: '🎵', mount: mountQueueTab, badge: queueBadge, badgeCls: 'q' },
    { id: 'rank', label: '후원 순위', icon: '🏆', mount: mountRank },
    { id: 'fx', label: '이펙트', icon: '✨', mount: (el, ctx) => mountOpFx(el, ctx) },
    { id: 'video', label: '고액 영상', icon: '🎬', mount: (el, ctx) => mountMedia(el, ctx) },
    { id: 'manage', label: '시그니처 관리', icon: '💿', mount: (el, ctx) => mountSigAdmin(el, ctx) },
];
// 조종실 탭 이름 → 여기 탭(console.js 미니의 [전체 열기] 같은 길이 ctx.tabs.open('ops-console') 을 부를 때)
const ALIAS = { 'ops-console': 'send', 'ops-opfx': 'fx', 'ops-media': 'video', 'sig-admin': 'manage', donors: 'rank' };

function queueBadge(slices) {
    const n = (((slices || {}).queue || {}).items || []).length;
    return n ? String(n) : '';
}

/* ── 수동 송출 — 후원 콘솔 탭 그대로 + 접힌 은행 확장 · 폰 앱 칸 ── */
function mountSend(el, ctx) {
    const con = mountConsole(el, ctx, { solo: true });         // solo — '따로 열기' 링크를 안 붙인다(이미 따로 열린 페이지)
    const mirror = mountBankMirror(ctx), app = mountBankApp(ctx);
    const more = h('details', { class: 'cp-more' },
        h('summary', null, '🏦 은행 확장 · 📱 폰 입금알림 앱 ', h('small', null, '자동 조회 켜기 · 간격 · 지금 조회 · 앱 QR — 조종실 🖥️ 시스템 탭과 같은 칸')),
        h('div', { class: 'cp-more-body' }, mirror.el, app.el));
    // 펼쳤을 때만 읽는다(접혀 있는 동안 /api/bank/ext 를 괜히 부르지 않게)
    const paintMore = () => { if (more.open) { mirror.render(); app.render(); } };
    more.addEventListener('toggle', paintMore);
    el.append(more);
    return { render(slices) { con.render(slices); paintMore(); } };
}

/* ── 대기열 — 조종실 시그니처 대기줄 그대로 + 멈춤 안내 줄 · 시그 사진(옛 대기열 모습) ── */
function mountQueueTab(el, ctx) {
    const note = h('p', { class: 'cp-note', hidden: true, role: 'status' },
        '⏸ 시그니처가 멈춰 있어요 — 후원은 계속 쌓여요. [다시 틀기] 를 누르면 순서대로 이어서 나가요.');
    const sec = h('section', { class: 'sec cp-queue', 'aria-label': '시그니처 대기열' });
    el.append(note, sec);
    // 머리 조종 줄(#ctl-sig)이 없는 페이지 — 건너뛰기 · 소리 막대가 목록 칸(멈춤 · 전부 지우기 옆)으로 온다(queue.js)
    const q = mountQueue(sec, ctx);
    return {
        render(slices) {
            q.render(slices);
            const qs = slices.queue || {};
            note.hidden = !qs.paused;
            paintThumbs(sec, qs.items || []);
        },
    };
}

/** 줄마다 맨 앞에 시그 사진(없으면 🎵) — queue.js 가 줄을 다시 그리면 사진이 빠지므로 그릴 때마다 맞춘다 */
function paintThumbs(root, items) {
    const by = new Map(items.map(it => [String(it.id), it]));
    root.querySelectorAll('.qlist > .qitem').forEach(li => {
        const it = by.get(String(li.dataset.id || ''));
        const src = it && it.image_url ? String(it.image_url) : '';
        let th = li.querySelector(':scope > .cp-qthumb');
        if (th && (th.tagName === 'IMG') !== !!src) { th.remove(); th = null; }
        if (!th) {
            th = src ? h('img', { class: 'cp-qthumb', alt: '', loading: 'lazy', decoding: 'async' })
                     : h('span', { class: 'cp-qthumb none', 'aria-hidden': 'true' }, '🎵');
            li.prepend(th);
        }
        if (src && th.getAttribute('src') !== src) th.setAttribute('src', src);
        li.classList.add('has-thumb');
    });
}

/* ── 후원 순위 — 조종실 👑 후원자 탭 그대로 + 합계 · 후원자 수 카드 · 1~3위 메달(옛 후원 순위 모습) ── */
function mountRank(el, ctx) {
    const total = h('b', { class: 'v gold' }, '0원');
    const people = h('b', { class: 'v' }, '0명');
    el.append(h('div', { class: 'cp-stats' },
        h('div', { class: 'cp-stat' }, h('span', { class: 'k' }, '누적 후원 합계'), total),
        h('div', { class: 'cp-stat' }, h('span', { class: 'k' }, '후원자 수'), people),
        h('p', { class: 'cp-live' }, '🔄 후원이 들어오면 바로 바뀌어요 — 새로 고칠 필요 없어요')));
    const body = h('div', { class: 'cp-rank' });
    el.append(body);
    const d = mountDonors(body, ctx);
    return {
        render(slices) {
            d.render(slices);
            // 합계 · 사람 수 — 후원자 탭과 같은 셈(이번 방송 · 0원 넘는 사람만 · 순위에서 뺀 이름은 서버가 이미 뺐다)
            const rows = Object.values(((slices.tallies || {}).donors) || {}).map(v => Number((v || {}).total) || 0).filter(t => t > 0);
            const sum = rows.reduce((a, b) => a + b, 0);
            const ts = num(sum) + '원', ps = num(rows.length) + '명';
            if (total.textContent !== ts) total.textContent = ts;
            if (people.textContent !== ps) people.textContent = ps;
            // 🥇🥈🥉 — 순위 칸의 숫자(동점은 같은 순위)를 보고 붙인다
            body.querySelectorAll('.dn-list > li').forEach(li => {
                const r = ((li.querySelector('.dn-rank') || {}).textContent || '').trim();
                const m = r === '1' || r === '2' || r === '3' ? r : '';
                if ((li.dataset.medal || '') !== m) { if (m) li.dataset.medal = m; else delete li.dataset.medal; }
            });
        },
    };
}

/* ══ 페이지 틀 ══ */
const lm = window.LM.connect({ kind: 'console' });
const $ = id => document.getElementById(id);
const root = $('cp-root');
const conn = document.querySelector('.conn');
let slices = {}, snapped = false, status = 'connecting', scheduled = false, built = false, loginShown = false;
let active = '';
let ui = null;               // { bar, body } — 탭 줄 · 탭 칸
const made = {};             // id → { el, api }
const btns = {};             // id → { b, badge }

const ctx = {
    lm,
    toast,
    confirm: confirmBox,
    // 로그인이 풀리면 이 페이지에서 다시 들어간다(비밀번호 칸이 여기 있다)
    run: makeRun(lm, () => { toast('로그인이 풀렸어요 — 다시 들어가 주세요', 'err'); setTimeout(() => location.reload(), 1500); }),
    rerender: schedule,
    get slices() { return slices; },
    tabs: {
        open: id => open(ALIAS[id] || id, true),
        active: () => active,
        prepare: () => false,
        locked: () => false,
    },
};

const CONN = { connecting: '연결 중', live: '연결됨', down: '끊김 · 다시 붙는 중' };
lm.onStatus(s => {
    status = s;
    if (s === 'live') snapped = true;
    conn.dataset.s = s in CONN ? s : 'connecting';
    conn.querySelector('.t').textContent = CONN[s] || CONN.connecting;
    schedule();
});
lm.on('*', s => { slices = s; schedule(); });

function schedule() {
    if (scheduled) return;
    scheduled = true;
    // ⚠️ requestAnimationFrame 은 가려진 창에서 멈춘다 — 마이크로태스크로 모은다(main.js 와 같다)
    Promise.resolve().then(() => { scheduled = false; render(); });
}

function safe(fn, what) {
    try { return fn(); } catch (e) { console.error('[후원 콘솔' + (what ? ' ' + what : '') + ']', e); return undefined; }
}

function lastTab() {
    const hash = decodeURIComponent((location.hash || '').slice(1));
    if (TABS.some(t => t.id === hash)) return hash;
    try { const v = localStorage.getItem(KEY); if (TABS.some(t => t.id === v)) return v; } catch (e) { /* 개인 창 등 — 기억 못 해도 된다 */ }
    return TABS[0].id;
}
function remember(id) {
    try { localStorage.setItem(KEY, id); } catch (e) { /* 기억 못 해도 된다 */ }
}

function build() {
    built = true;
    document.body.dataset.view = 'console';
    const bar = h('nav', { class: 'cp-tabs', role: 'tablist', 'aria-label': '후원 콘솔 탭' });
    const body = h('div', { class: 'cp-body' });
    for (const t of TABS) {
        const badge = t.badge ? h('span', { class: 'tab-badge' + (t.badgeCls ? ' ' + t.badgeCls : ''), hidden: true }) : null;
        const b = h('button', { type: 'button', class: 'cp-tab', role: 'tab', id: 'cp-tab-' + t.id, 'data-tab': t.id,
            'aria-selected': 'false', 'aria-controls': 'cp-pane-' + t.id, onclick: () => open(t.id, true) },
            h('span', { class: 'cp-ic', 'aria-hidden': 'true' }, t.icon), h('span', null, t.label), badge);
        btns[t.id] = { b, badge };
        bar.append(b);
    }
    ui = { bar, body };
    root.replaceChildren(bar, body);
    open(lastTab(), false);
}

function ensure(id) {
    if (made[id]) return made[id];
    const t = TABS.find(x => x.id === id);
    const el = h('div', { class: 'tabpanel cp-pane', role: 'tabpanel', id: 'cp-pane-' + id, 'aria-labelledby': 'cp-tab-' + id, 'data-panel': id, hidden: true });
    ui.body.append(el);
    const api = safe(() => t.mount(el, ctx), id) || null;
    if (!api) el.textContent = '이 탭을 여는 중에 문제가 생겼어요 — 새로 고쳐 주세요';
    made[id] = { el, api };
    return made[id];
}

/** 탭 열기 — user: 사람이 눌렀다(기억하고, 폰에서는 탭 줄이 보이게 위로) */
function open(id, user) {
    if (!TABS.some(t => t.id === id)) return false;
    if (!built) return false;
    if (user && active && id !== active) tabChanged(active, id);      // ◀ 뒤로가기가 돌아올 탭(10-24)
    active = id;
    const m = ensure(id);
    for (const [k, x] of Object.entries(made)) x.el.hidden = k !== id;
    m.el.hidden = false;
    for (const [k, { b }] of Object.entries(btns)) {
        const on = k === id;
        b.classList.toggle('on', on);
        b.setAttribute('aria-selected', on ? 'true' : 'false');
        b.tabIndex = on ? 0 : -1;
    }
    // 고른 탭 단추가 줄 밖(폰 — 줄을 옆으로 민다)이면 보이게. ⚠️ scrollIntoView 는 페이지도 굴려서 안 쓴다
    const b = btns[id].b, bar = ui.bar;
    if (b.offsetLeft < bar.scrollLeft || b.offsetLeft + b.offsetWidth > bar.scrollLeft + bar.clientWidth) bar.scrollLeft = Math.max(0, b.offsetLeft - 16);
    if (user) {
        remember(id);
        if (history.replaceState) { try { history.replaceState(null, '', '#' + id); } catch (e) { /* 무시 */ } }
        // 아래로 내려가 있었으면 새 탭 첫머리부터 보이게(탭 줄은 위에 붙어 있다)
        if (root.getBoundingClientRect().top < 0) { try { root.scrollIntoView({ block: 'start', behavior: 'smooth' }); } catch (e) { root.scrollIntoView(); } }
    }
    draw();
    return true;
}

function paintBadges() {
    for (const t of TABS) {
        const x = btns[t.id];
        if (!x || !x.badge) continue;
        const s = String(safe(() => t.badge(slices), t.id + ' 배지') || '');
        if (x.badge.textContent !== s) x.badge.textContent = s;
        if (x.badge.hidden !== !s) x.badge.hidden = !s;
    }
}

function draw() {
    paintBadges();
    const m = made[active];
    if (m && m.api && m.api.render) safe(() => m.api.render(slices), active);
}

function showLogin() {
    if (loginShown) return;
    loginShown = true;
    document.body.dataset.view = 'login';
    const box = h('div', { class: 'cp-login' });
    root.replaceChildren(box);
    mountLogin(box);
    // login.js 는 body data-view 가 'login' 으로 바뀔 때 칸에 커서를 둔다 — 이미 바뀐 뒤라 여기서 한 번
    setTimeout(() => { const i = box.querySelector('input'); if (i) i.focus(); }, 30);
}

function render() {
    $('cp-down').hidden = !(snapped && status === 'down');
    if (!snapped) return;
    if (!lm.authed) { showLogin(); return; }
    if (!built) build();
    else if (root.firstChild !== ui.bar) {           // 로그인 화면을 거쳐 다시 붙었다(다른 탭에서 로그인) — 만들어 둔 탭을 되돌린다
        loginShown = false;
        document.body.dataset.view = 'console';
        root.replaceChildren(ui.bar, ui.body);
    }
    draw();
    const hh = document.querySelector('.hdr').offsetHeight;
    if (hh && hh !== render._hh) { render._hh = hh; document.documentElement.style.setProperty('--hdr-h', hh + 'px'); }
}

window.addEventListener('resize', schedule);
// 주소 끝 #queue 처럼 바꾸면 그 탭으로(즐겨찾기 · 다른 화면에서 건 링크)
initBack({ name: '후원 콘솔', toast, goTab: id => open(id, false) });

window.addEventListener('hashchange', () => {
    const id = decodeURIComponent((location.hash || '').slice(1));
    if (built && id !== active && TABS.some(t => t.id === id)) open(id, false);
});
// 탭 줄 ← → 로 옮기기(키보드)
document.addEventListener('keydown', e => {
    if (!built || !e.target || !e.target.classList || !e.target.classList.contains('cp-tab')) return;
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const i = TABS.findIndex(t => t.id === active);
    const n = TABS[(i + (e.key === 'ArrowRight' ? 1 : TABS.length - 1)) % TABS.length].id;
    open(n, true);
    btns[n].b.focus();
});
