/* 📊 많이 누른 것 — (1) 조종실 클릭 세기 (2) [📊 누른 것] 탭: 방송별 순위.
   옛 controller.html 의 클릭 기록 스크립트 · uistats.html 을 옮겼다(서버 domain/uistats.py).

   (1) 세기 — installClickStats() 한 번(tools_more.js 가 조종실을 열 때 부른다)
     · 단추 · 탭 · 스위치를 누르면 '무엇' 만 센다. 이름 · 금액 · 입력한 글자는 안 적는다:
         보이는 글자를 쓰되 따옴표 안('하율' 을 뺄까요?) · 숫자(금액 · 시각 · 번호) · 지금 화면의 사람 이름(점수판 · 대기함)은 지운다.
         멤버 이름이 박힌 배정 단추(.pbtn)는 '멤버 단추' 하나로 묶는다. 입력칸 · 고르기 칸의 **값** 은 절대 안 본다.
     · 확인 창 단추는 창 제목을 붙인다(옛 것: '확인' 65번이 어느 창인지 몰랐다).
     · 20초마다 묶어서 서버로(창을 숨길 때도 한 번 — sendBeacon). 실패하면 조용히 다음에 같이 보낸다.
       한 번에 200가지까지 · 쌓아 두는 것도 400가지까지(서버가 오래 안 받아도 메모리가 안 붓게).
     ⚠️ 방송 조작을 절대 막으면 안 된다 — 전부 try 안, 사건은 '지켜보기(capture · passive)' 만.
   (2) 탭 — GET /api/uistats(방송 목록) · ?session=(순위). 칸(영역)으로 거르기. */
import { h, num } from '../../util.js';
import { getJSON, sessionLabel } from '../records/api.js';

const FLUSH_MS = 20000;
const MAX_KEYS = 200;            // 서버 UI_CLICK_MAX_KEYS 와 같다
const PEND_MAX = 400;
const AREA = {
    tabbar: '탭 줄', top: '머리줄', pending: '대기함', scores: '점수판', undo: '되돌리기', logs: '최근 기록', goal: '목표',
    queue: '시그 대기줄', modal: '확인 창', setup: '방송 전', login: '로그인', etc: '그 밖',
};

// ── (1) 세기 ──
const pend = new Map();          // key → {key, label, tab, n}
let installed = false, sending = false;

function areaOf(el) {
    if (el.closest('.modal-wrap')) return 'modal';
    if (el.closest('.tabbar')) return 'tabbar';
    const p = el.closest('[data-panel]');
    if (p) return p.dataset.panel;
    if (el.closest('#hdr')) return 'top';
    const s = el.closest('section[id]');
    if (s) return s.id.replace(/^v-/, '');
    return 'etc';
}

/** 지금 화면에 보이는 사람 이름 — 선수(점수판) · 후원자(대기함 · 후원자 · 장부 · 대기줄). 단추 글자에서 지운다 */
function namesOnScreen() {
    const out = new Set();
    document.querySelectorAll('#scores .nm, .pc-name, .dn-name, .rc-name, .q-who').forEach(e => {
        const t = (e.textContent || '').trim();
        if (t && t.length <= 30) out.add(t);
    });
    return [...out].sort((a, b) => b.length - a.length);       // 긴 이름부터('하율이' 를 '하율' 보다 먼저)
}

export function scrub(t, names) {
    let s = String(t || '').replace(/\s+/g, ' ').trim();
    s = s.replace(/(['"‘“「『]).*?(['"’”」』])/g, '…');       // 따옴표 안 — 이름 · 퀴즈 답 같은 것
    for (const n of names || []) if (n && s.includes(n)) s = s.split(n).join('○');
    s = s.replace(/₩?\d[\d,.:]*/g, '#');                       // 숫자 — 금액 · 시각 · 번호
    return s.slice(0, 40);
}

function textOf(el) {
    const vis = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim();
    return vis || el.getAttribute('aria-label') || el.getAttribute('title') || '';
}

export function describe(el, kind) {
    if (el.matches('.tab[data-tab]')) {
        return { key: 'tab:' + el.dataset.tab, label: '탭: ' + scrub(textOf(el), []), tab: 'tabbar' };
    }
    const area = areaOf(el);
    const names = namesOnScreen();
    let label;
    if (el.classList.contains('pbtn')) label = '멤버 단추';
    else if (kind === 'change') {
        // 스위치 · 고르기 — 값은 안 본다. 이름표(aria-label 또는 감싼 label 글자)만
        const lab = el.getAttribute('aria-label') || ((el.closest('label') || {}).textContent || '');
        label = scrub(lab, names) || (el.type === 'checkbox' ? '스위치' : '고르기');
        label += el.tagName === 'SELECT' ? ' (고르기)' : ' (스위치)';
    } else {
        label = scrub(textOf(el), names) || ('.' + String(el.className || el.tagName).split(/\s+/)[0]);
    }
    let key = area + '|' + label;
    if (area === 'modal') {
        const t = scrub((document.getElementById('mdl-t') || {}).textContent || '', names);
        if (t) { key += '|' + t; label += ' — ' + t; }
    }
    return { key: key.slice(0, 80), label: label.slice(0, 60), tab: area.slice(0, 30) };
}

function count(el, kind) {
    try {
        const d = describe(el, kind);
        let row = pend.get(d.key);
        if (!row) {
            if (pend.size >= PEND_MAX) return;
            row = { key: d.key, label: d.label, tab: d.tab, n: 0 };
            pend.set(d.key, row);
        }
        row.n++;
    } catch (e) { /* 세기가 넘어져도 누른 일은 그대로 */ }
}

function batch() {
    return [...pend.values()].slice(0, MAX_KEYS).map(x => ({ key: x.key, label: x.label, tab: x.tab, n: x.n }));
}
function settle(sent) {
    sent.forEach(s => { const p = pend.get(s.key); if (p) { p.n -= s.n; if (p.n <= 0) pend.delete(s.key); } });
}

export async function flush() {
    if (!pend.size || sending) return;
    const sent = batch();
    sending = true;
    try {
        const r = await fetch('/api/uistats', { method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
            body: JSON.stringify({ counts: sent }), keepalive: true });
        if (r.ok) settle(sent);
    } catch (e) { /* 조용히 — 다음에 같이 */ }
    sending = false;
}

export function installClickStats() {
    if (installed) return;
    installed = true;
    document.addEventListener('click', e => {
        try {
            const el = e.target && e.target.closest && e.target.closest('button, a[href], summary, [role=tab], [role=button]');
            if (!el || el.matches('input, select, textarea, label')) return;
            count(el, 'click');
        } catch (err) { /* 무시 */ }
    }, { capture: true, passive: true });
    document.addEventListener('change', e => {
        try {
            const el = e.target;
            if (!el || !el.matches || !el.matches('input[type=checkbox], input[type=radio], select')) return;
            count(el, 'change');
        } catch (err) { /* 무시 */ }
    }, { capture: true, passive: true });
    setInterval(flush, FLUSH_MS);
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState !== 'hidden' || !pend.size || !navigator.sendBeacon) return;
        try {
            const sent = batch();
            if (navigator.sendBeacon('/api/uistats', new Blob([JSON.stringify({ counts: sent })], { type: 'application/json' }))) settle(sent);
        } catch (err) { /* 무시 */ }
    });
}

/* 테스트 · 점검용 — 지금 쌓인 것 */
export function pending() { return batch(); }

// ── (2) 탭 ──
function sessName(id) {
    const m = /^off-(\d{4})(\d{2})(\d{2})$/.exec(String(id || ''));
    if (m) return `방송 밖 · ${+m[2]}월 ${+m[3]}일`;
    return sessionLabel(id);
}

function areaName(t) {
    if (AREA[t]) return AREA[t];
    const b = document.querySelector('.tab[data-tab="' + String(t).replace(/["\\]/g, '') + '"]');
    return b ? '탭: ' + (b.textContent || '').replace(/\s+/g, ' ').trim() : t;
}

export function mountUiStats(el, ctx) {
    el.classList.add('mo');
    const sel = h('select', { class: 'mo-select', 'aria-label': '방송 고르기' });
    const refresh = h('button', { type: 'button', class: 'btn sm' }, '새로 고침');
    const sum = h('span', { class: 'muted small' });
    const chips = h('div', { class: 'rc-chips', role: 'group', 'aria-label': '칸으로 거르기' });
    const status = h('p', { class: 'rc-status', role: 'status', hidden: true });
    const ol = h('ol', { class: 'mo-rank' });
    const empty = h('p', { class: 'empty', hidden: true });
    el.append(
        h('div', { class: 'sec-head' }, h('h2', null, '📊 많이 누른 것'), sum),
        h('p', { class: 'muted small mo-lead' }, '조종실에서 방송 중에 무엇을 몇 번 눌렀는지예요. 이름 · 금액 · 입력한 글자는 안 적어요. ',
            '자주 누르는 건 앞으로, 거의 안 누르는 건 접어 두는 데 씁니다. 20초마다 쌓여요.'),
        h('div', { class: 'rc-bar' }, sel, refresh), chips, status, ol, empty);

    let sessions = [], rows = [], filt = '', loaded = false, cur = '';
    sel.addEventListener('change', () => loadRows(sel.value));
    refresh.addEventListener('click', async () => { await flush(); loadList(true); });
    chips.addEventListener('click', e => {
        const b = e.target.closest('.rc-chip');
        if (!b) return;
        filt = b.dataset.t || '';
        draw();
    });

    function say(msg) { status.textContent = msg || ''; status.hidden = !msg; status.dataset.lv = msg ? 'bad' : ''; }

    async function loadList(keep) {
        let d;
        try { d = await getJSON('/api/uistats'); } catch (e) { say(e.message); return; }
        say('');
        sessions = d.sessions || [];
        const want = keep && cur && sessions.some(s => s.session === cur) ? cur
            : ((sessions.find(s => !/^off-/.test(s.session)) || sessions[0] || {}).session || d.now);
        sel.replaceChildren(...(sessions.length ? sessions : [{ session: d.now, total: 0 }]).map(s =>
            h('option', { value: s.session }, sessName(s.session) + (s.total ? ` · ${num(s.total)}번` : ''))));
        sel.value = want;
        await loadRows(want);
    }

    async function loadRows(session) {
        cur = session;
        try { rows = (await getJSON('/api/uistats?session=' + encodeURIComponent(session))).rows || []; say(''); } catch (e) { rows = []; say(e.message); }
        loaded = true;
        filt = '';
        draw();
    }

    function draw() {
        const list = filt ? rows.filter(r => r.tab === filt) : rows;
        const max = Math.max(1, ...list.map(r => r.n));
        const total = list.reduce((a, r) => a + r.n, 0);
        sum.textContent = total ? `모두 ${num(total)}번 · ${num(list.length)}가지` : '';
        const tabs = [...new Set(rows.map(r => r.tab).filter(Boolean))];
        chips.replaceChildren(...(rows.length ? [['', '전체'], ...tabs.map(t => [t, areaName(t)])] : []).map(([t, l]) =>
            h('button', { type: 'button', class: 'rc-chip' + (filt === t ? ' on' : ''), 'data-t': t, 'aria-pressed': filt === t ? 'true' : 'false' }, l)));
        ol.replaceChildren(...list.slice(0, 300).map((r, i) => h('li', { class: 'mo-rrow' + (i < 3 ? ' top' : '') },
            h('span', { class: 'mo-rk' }, String(i + 1)),
            h('span', { class: 'mo-nm' }, h('b', null, r.label || r.key), h('small', null, areaName(r.tab)),
                h('span', { class: 'mo-track' }, h('i', { style: `width:${(r.n / max * 100).toFixed(1)}%` }))),
            h('b', { class: 'mo-n' }, num(r.n)))));
        empty.hidden = !loaded || list.length > 0;
        empty.textContent = '아직 기록이 없어요. 조종실에서 단추를 누르면 20초 안에 쌓이기 시작해요.';
    }

    loadList(false);
    return { render() { /* 서버 표를 읽는다 — 조각이 바뀌어도 다시 안 읽는다([새로 고침]) */ } };
}
