/* ⌨️ Ctrl+K(맥 ⌘K) 찾기 · 빠른 명령 — 어느 화면에서든 상자 하나로 **무엇이든** 찾고 말로 시킨다
   (대표님 10-17 시안 B 묶음 D · 10-24 "컨트롤 케이로 검색기능에 모든걸 검색할 수 있게").

   찾는 것(묶음마다 작은 머리 · 묶음마다 몇 개까지만 · 똑같음 > 앞이 같음 > 들어 있음 순)
     ▶ 명령     '밍밍 5' · '룰렛 돌려' · '+1분' · '올클리어' · '클립' · '다음 단계' … — panels/ai/commands.js 규칙 그대로(복사하지 않는다)
     ↗ 탭       모든 탭 + ⚙ 설정 화면 타일(은행 확장 · 테스트 · 연습) — 이름 · 짧은 이름 · 타일 설명 · 묶음 이름으로
     ⚙ 설정    탭 안의 블록 · 스위치 · 칸 · 단추('방송 테두리' · '테마' · '효과음' · '용 연출' · '계좌 열쇠' · '시그니처 최저선' …)
               → 그 탭을 열고 그 자리로 내려가 2초 동안 주황 테두리로 깜빡. 색인은 cmdkindex.js(안 연 탭도 찾게) + 이미 연 탭에서 주운 제목.
     🏅 선수    지금 판 선수 — '밍' → '밍밍 '(숫자를 이어 적게) · '밍 5' → '밍밍 +5점 주기'(바로)
     📥 대기함  기다리는 후원(이름 · 금액 · 메시지) → 그 카드로(폰은 아래 서랍을 펼쳐서)
     📇 후원자  이번 방송 후원자(tallies) + 후원자 장부(donor_tags) → 후원자 카드(donorcard.js). 카드가 없으면 장부에서 그 이름으로
     🎵 시그니처 제목 · 금액('5만' · '50000') · 번호 → 시그니처 관리 탭에서 그 카드만
     📒 장부    이번 방송 후원 줄(이름 · 메시지 · 금액 — 열 때 서버에서 300줄) → 장부 탭을 그 이름으로 걸러서
     📣 공지 · 🎡 룰렛 칸 — 적어 둔 글 → 그 탭 그 줄로
   맞추기는 cmdkcore.js — 띄어쓰기 · 대소문자 · 이모지 무시, 초성('ㅁㅁ' → 밍밍), 치는 중인 마지막 글자, 여러 낱말, 금액 꼴.

   명령은 예전 그대로
     - '룰렛' 처럼 탭 이름을 그대로 적으면 그 탭이 맨 위(돌리기는 '룰렛 돌려'). 바로 하는 말(명령 꼴 — isCommandForm)이면
       '그대로 하기' 가 찾은 설정 · 후원자보다 위 — Enter 가 늘 하던 대로 명령을 한다.
     - 🗣️ 규칙에 안 맞으면 맨 아래 '그대로 하기' → 서버(/api/ai/command — 서버 규칙 → AI)에 명령인지 묻는다. 명령이면 상자 안에 카드
       ('🤖 밍밍에게 +5점 [실행] [취소]' · 안전한 건 '✅ … [되돌리기]'). 점수 · 게임은 [실행] 을 눌러야 한다(panels/ai/cards.js).
       물음이거나 AI 가 꺼졌으면 '모르는 말이에요' 와 예시만.
   - 입력칸에 커서가 있어도 Ctrl+K 는 연다(대기함 입력 중에도). Esc · 바깥 누르기로 닫는다. ↑↓ 로 고르고 Enter.
   - 📱 폰(키보드 단축키가 없다) — 조종 줄 🔍 단추(header.js)가 document 에 'lm:cmdk' 를 쏘면 같은 상자가 열린다.
   - 로그인 전(로그인 · 연결 중 화면)에는 안 열린다(비공개 값 · 명령 길을 열지 않는다).
   - 소리 없음. 바깥 글자(선수 · 후원자 이름 · 메시지)는 textContent 로만. 걸린 메시지(🙈)는 가린 글로만 보이고 찾는다. */
import { h, num, won } from './util.js';
import { runCommand, COMMAND_HINTS } from './panels/ai/commands.js';
import { isCommandForm } from './panels/ai/commands.js';
import { currentNames } from './panels/ai/common.js';
import { askCommand, autoClient, cardsView } from './panels/ai/cards.js';
import { toggle as bgmToggle, next as bgmNext } from './panels/records/bgm.js';
import { norm, hit, scoreEntry, wonOf } from './cmdkcore.js';
import { SPOTS, PLACE } from './cmdkindex.js';
import { GROUPS as TILE_GROUPS, DESC as TILE_DESC, ACTS } from './panels/settings_menu.js';
import { openBankExt } from './bankext.js';
import { openDonor } from './donorcard.js';
import { chipText, isAnon } from './donorcore.js';
import { shownText } from './mask.js';
import { loadSigs, sigsNow, useLm } from './panels/games/common.js';
import { getJSON, hms } from './panels/records/api.js';

const LOCAL = [
    { text: 'BGM 다음 곡', kw: '노래 음악 다음곡 넘기기', run: () => bgmNext(true), msg: '🎵 다음 곡으로 넘겼어요' },
    { text: 'BGM 재생 · 멈춤', kw: '노래 음악 재생 멈춤 틀기 끄기', run: () => bgmToggle(), msg: '🎵 BGM 재생 · 멈춤' },
];

/** 묶음 — [그림, 머리 글자]. 이 순서는 점수가 같을 때만 쓴다(보통은 제일 잘 맞은 묶음이 위) */
export const GROUPS = {
    cmd: ['▶', '명령'], tab: ['↗', '탭'], spot: ['⚙', '설정 · 단추'], player: ['🏅', '선수'], pend: ['📥', '대기함'],
    donor: ['📇', '후원자'], sig: ['🎵', '시그니처'], ledger: ['📒', '장부'], notice: ['📣', '공지'], roul: ['🎡', '룰렛 칸'],
    ask: ['🤖', '말로 시키기'],
};
const ORDER = Object.keys(GROUPS);
const CAP = { cmd: 4, tab: 5, spot: 6, player: 4, pend: 4, donor: 5, sig: 5, ledger: 4, notice: 3, roul: 3, ask: 1 };
const HINT = { run: '실행', fill: '이름 넣기', local: '실행', tab: '열기', act: '열기', spot: '찾아가기', sig: '시그니처 관리',
    pend: '대기함에서', ledger: '장부에서', notice: '공지 탭', roul: '룰렛 탭' };
const cut = (s, n) => { s = String(s || '').replace(/\s+/g, ' ').trim(); return s.length > n ? s.slice(0, n - 1) + '…' : s; };

/** 적은 말 → 고를 거리(순수 — 검사용). 보여 줄 차례대로 · 줄마다 group(묶음) 이 붙어 있다.
 *  names: 지금 판 선수, tabs: [{id,label,short,icon?,desc?,group?,locked?,act?}] 탭,
 *  more: { spots, donors, sigs, pending, ledger, notices, roulette } — 줄마다 {title, kw?, sub?, …}(cmdk 가 조각에서 만든다) */
export function suggest(q, names, tabs, more) {
    q = String(q || '').trim();
    names = names || [];
    more = more || {};
    if (!q) return COMMAND_HINTS.slice(0, 5).map(t => ({ kind: 'run', group: 'cmd', text: t, label: t }));
    const fq = norm(q);
    const best = new Map();                 // kind:text → 줄(점수가 높은 것만 남긴다)
    const add = (it, score) => {
        if (!(score > 0)) return;
        const k = it.kind + ':' + it.text;
        const old = best.get(k);
        if (!old || old.score < score) { it.score = score; best.set(k, it); }
    };

    // ▶ 명령 — 예시 말 · BGM
    for (const t of COMMAND_HINTS) {
        const ft = norm(t);
        let s = hit(ft, fq);
        if (!s && ft && fq.indexOf(ft) !== -1) s = 60;              // '룰렛 돌려줘' → '룰렛 돌려'
        add({ kind: 'run', group: 'cmd', text: t, label: t }, s >= 100 ? 110 : s && s + 4);
    }
    for (const L of LOCAL) {
        const ft = norm(L.text);
        let s = scoreEntry({ title: L.text, kw: L.kw }, q, fq);
        if (!s && fq.length >= 2 && ft.startsWith(fq.slice(0, 3))) s = 50;   // 'bgm 멈춰' → BGM 재생 · 멈춤
        add({ kind: 'local', group: 'cmd', text: L.text, label: L.text, ic: '🎵' }, s && s + 4);
    }
    // 바로 하는 말(명령 꼴)이면 '그대로 하기' 를 위로 — 찾은 설정이 Enter 를 가로채지 않게
    if (isCommandForm(q, names)) add({ kind: 'run', group: 'cmd', text: q, label: `${q} — 바로 하기` }, 116);

    // ↗ 탭 — 이름을 그대로 적었으면 맨 위('룰렛' → 룰렛 탭 열기, 돌리기는 '룰렛 돌려')
    for (const t of tabs || []) {
        const exact = norm(t.label) === fq || (!!t.short && norm(t.short) === fq) || t.id === q;
        const s = exact ? (t.locked ? 100 : 120) : scoreEntry({ title: t.label, kw: [t.short, t.group].join(' '), sub: t.desc }, q, fq);
        add({ kind: t.act ? 'act' : 'tab', group: 'tab', text: t.act || t.id, label: t.label, ic: t.icon || '',
            sub: t.locked ? '방송을 시작하면 열려요' : (t.desc || t.group || ''), locked: !!t.locked }, exact ? s : s && s + 6);
    }

    // 🏅 선수 — '밍 5' → '밍밍 5'(바로 실행) · '밍' · 'ㅁㅁ' → '밍밍 '(숫자를 이어 적게)
    const pm = q.match(/^([가-힣ㄱ-ㅎA-Za-z0-9]+?)\s*\+?(\d+)?\s*점?$/);
    if (pm) {
        const key = norm(pm[1]);
        for (const n of names) {
            const s = hit(norm(n), key);
            if (!s) continue;
            if (pm[2]) add({ kind: 'run', group: 'player', text: `${n} ${pm[2]}`, label: `${n} +${pm[2]}점 주기`, ic: '🏅' }, 118 + s / 100);
            else add({ kind: 'fill', group: 'player', text: `${n} `, label: `${n} — 점수 주기(숫자를 이어서 적어요)`, ic: '✎' }, s + 2);
        }
    }

    // ⚙ 설정 · 단추(색인 + 연 탭에서 주운 것)
    for (const sp of more.spots || []) {
        const s = scoreEntry(sp, q, fq);
        add({ kind: 'spot', group: 'spot', text: sp.key, label: sp.title, sub: sp.where, ic: sp.ic || '⚙', spot: sp }, s && s + (sp.live ? 0 : 3));
    }

    // 금액 꼴('5만' · '50000')이면 금액이 같은 줄을 위로
    const want = wonOf(q);
    const amountScore = (amount, s) => {
        const a = Number(amount) || 0;
        if (want && a === want) return Math.max(s, 96);
        if (/^\d{3,}$/.test(fq) && String(a).startsWith(fq)) return Math.max(s, 56);
        return s;
    };
    // 📥 대기함
    for (const p of more.pending || []) {
        const s = amountScore(p.amount, scoreEntry(p, q, fq));
        const what = p.kind === 'contrib' ? `기여도 ${num(p.contrib || 0)}` : p.type ? '' : won(p.amount);
        add({ kind: 'pend', group: 'pend', text: String(p.id), label: cut(`${p.title} ${what}`, 40), sub: cut(p.sub, 60), ic: '📥' }, s);
    }
    // 📇 후원자
    for (const d of more.donors || []) {
        const s = scoreEntry(d, q, fq);
        add({ kind: 'donor', group: 'donor', text: d.title, label: d.title, sub: d.info || '', pid: d.pid || '', ic: '📇',
            hint: d.pid ? '후원자 카드' : '장부에서' }, s);
    }
    // 🎵 시그니처
    for (const g of more.sigs || []) {
        const s = amountScore(g.amount, scoreEntry(g, q, fq));
        add({ kind: 'sig', group: 'sig', text: String(g.id), label: g.title, sub: `${num(g.amount)}원 · #${g.id}`, ic: '🎵' }, s);
    }
    // 📒 장부(이번 방송)
    for (const r of more.ledger || []) {
        const s = amountScore(r.amount, scoreEntry(r, q, fq));
        add({ kind: 'ledger', group: 'ledger', text: String(r.id), label: cut(`${r.title} ${won(r.amount)}`, 40),
            sub: cut([r.time, r.sub].filter(Boolean).join(' · '), 60), ic: '📒', name: r.title, time: r.time }, s);
    }
    // 📣 공지 · 🎡 룰렛 칸
    for (const n of more.notices || []) {
        add({ kind: 'notice', group: 'notice', text: String(n.i), label: cut(n.title, 50), sub: `${n.i + 1}번 공지`, ic: '📣' }, scoreEntry(n, q, fq));
    }
    for (const r of more.roulette || []) {
        add({ kind: 'roul', group: 'roul', text: r.title, label: r.title, sub: '룰렛 직접 입력 칸', ic: '🎡' }, scoreEntry(r, q, fq));
    }

    // 맨 끝 — 적은 말 그대로 해 보기(규칙에 맞으면 명령, 아니면 서버 · AI 에게)
    if (![...best.values()].some(it => it.kind === 'run' && norm(it.text) === fq)) {
        add({ kind: 'run', group: 'ask', text: q, label: `'${q}' 그대로 하기`, sub: '말로 시키기 — 모르는 말은 AI 가 명령으로 바꿔요' }, 1);
    }

    // 묶기 · 줄 세우기 — 묶음 안은 점수 순(같으면 들어온 순), 묶음끼리는 제일 잘 맞은 줄 순. '그대로 하기' 는 늘 맨 끝
    const byG = new Map();
    let i = 0;
    for (const it of best.values()) {
        it.n = i++;
        if (!byG.has(it.group)) byG.set(it.group, []);
        byG.get(it.group).push(it);
    }
    const groups = [...byG.entries()].map(([g, arr]) => {
        arr.sort((a, b) => b.score - a.score || a.n - b.n);
        return { g, arr: arr.slice(0, CAP[g] || 4), top: arr[0].score };
    });
    groups.sort((a, b) => (a.g === 'ask') - (b.g === 'ask') || b.top - a.top || ORDER.indexOf(a.g) - ORDER.indexOf(b.g));
    return groups.flatMap(x => x.arr);
}

/* ── 화면에서 찾아가기(브라우저) ── */
const PHONE = '(max-width: 899px)';
const isPhone = () => !!(window.matchMedia && matchMedia(PHONE).matches);
const visible = el => !!(el && el.isConnected && (el.offsetParent || el.getClientRects().length));
// 글자로 찾을 때 보는 차례 — 제목 → 이름표 → 단추 → 칸 이름(aria-label · placeholder) → 그 밖 글자
const TIERS = ['h2,h3,h4,summary,legend,.gm-title', 'label,.gm-lbl,.gm-tn,.gm-sub b,.ops-switch-t', 'button,a.btn,.ops-chip',
    '[aria-label],[placeholder]', 'b,strong,span,p,small,li'];

/** root 안에서 찾을 곳 — '#id' · '.class' · 글자 · 함수 */
function locate(root, find) {
    if (!root || !find) return null;
    if (typeof find === 'function') return find() || null;
    if (/^[#.]/.test(find)) return root.querySelector(find) || document.querySelector(find);
    const want = norm(find);
    if (!want) return null;
    for (let ti = 0; ti < TIERS.length; ti++) {
        let best = null, bestLen = 1e9, bestVis = false;
        for (const el of root.querySelectorAll(TIERS[ti])) {
            if (el.closest('.cmdk')) continue;
            const t = norm(ti === 3 ? (el.getAttribute('aria-label') || el.getAttribute('placeholder') || '') : el.textContent);
            if (!t || t.indexOf(want) === -1) continue;
            const vis = visible(el);
            // 보이는 것 먼저 · 그다음 글자가 짧은 것(딱 그 이름에 가까운 것)
            if ((vis && !bestVis) || (vis === bestVis && t.length < bestLen)) { best = el; bestLen = t.length; bestVis = vis; }
        }
        if (best) return best;
    }
    return null;
}

/** 깜빡일 칸 — 제목이면 그 블록 통째, 아니면 그 줄 */
function blockOf(el) {
    if (el.matches('summary, legend')) return el.parentElement || el;
    if (el.matches('h2,h3,h4,.gm-title')) return el.closest('.ops-blk,.gm-box,.sg-blk,.st-grp,.dk-sec,details,section') || el;
    return el.closest('.ops-switch,label,.ops-row,.gm-row,.gm-col,.gm-tile,li,.pcard,.sg-card') || el;
}

/** 보이게 — 접힌 칸 펼치기 · 폰 서랍 · ⋯ 판 열기 → 화면 가운데로. 그래도 안 보이면 false */
function reveal(el) {
    for (let d = el.closest('details'); d; d = d.parentElement && d.parentElement.closest('details')) d.open = true;
    const pane = el.closest('#drawer .dr-pane');
    if (pane) document.dispatchEvent(new CustomEvent('lm:drawer', { detail: { pane: pane.dataset.pane, open: true } }));
    const sheet = el.closest('#ctl-more');
    if (sheet && sheet.hidden) { const mb = document.querySelector('#hdr .cb-more'); if (mb) mb.click(); }
    if (!visible(el)) return false;
    scrollToEl(el);
    return true;
}

/** 그 칸을 가운데로 — 안쪽 스크롤 칸(가운데 칸 · 오른쪽 칸 · 폰 서랍)부터 맞추고, 창은 그래도 안 보일 때만 움직인다.
 *  ⚠️ scrollIntoView({block:'center'}) 는 PC 에서 창 전체까지 밀어 올려 세 칸 틀이 어긋났다(10-24 헤드리스로 봄).
 *  ⚠️ 부드럽게(smooth) 안 한다 — 가려진 창에선 멈춘다(방송 PC 는 OBS 가 앞에 있을 때가 많다). 깜빡이가 눈길을 끈다. */
function scrollToEl(el) {
    for (let sc = el.parentElement; sc && sc !== document.body && sc !== document.documentElement; sc = sc.parentElement) {
        if (!/(auto|scroll)/.test(getComputedStyle(sc).overflowY) || sc.scrollHeight <= sc.clientHeight + 2) continue;
        const r = el.getBoundingClientRect(), cr = sc.getBoundingClientRect();
        if (r.top >= cr.top + 4 && r.bottom <= cr.bottom - 4) continue;              // 그 칸 안에서 이미 보인다
        sc.scrollTop += (r.top - cr.top) - Math.max(8, (sc.clientHeight - r.height) / 2);
    }
    // 창 — 위에 붙은 머리줄 · 폰 탭 줄과 아래 서랍을 빼고 본다
    const stuck = id => { const e = document.getElementById(id); return e && /sticky|fixed/.test(getComputedStyle(e).position) && visible(e) ? e.getBoundingClientRect() : null; };
    const hd = stuck('hdr'), rl = stuck('rail'), dr = el.closest('#drawer') ? null : stuck('drawer');
    const top = Math.max(0, hd ? hd.bottom : 0, rl && rl.top < innerHeight / 3 ? rl.bottom : 0);
    const bottom = dr && dr.top > innerHeight / 3 ? dr.top : innerHeight;
    const r = el.getBoundingClientRect();
    if (r.top < top + 4 || r.bottom > bottom - 4) window.scrollBy(0, r.top - top - Math.max(8, (bottom - top - r.height) / 2));
}

let flashEl = null, flashT = 0;
/** 2초 동안 주황 테두리(css .cmdk-flash) — 가려진 창에서도 꺼지게 시계로 뗀다(animationend 를 기다리지 않는다) */
function flash(el) {
    if (flashEl && flashEl !== el) flashEl.classList.remove('cmdk-flash');
    clearTimeout(flashT);
    el.classList.remove('cmdk-flash');
    void el.offsetWidth;                  // 같은 칸을 또 골라도 처음부터 다시
    el.classList.add('cmdk-flash');
    flashEl = el;
    flashT = setTimeout(() => { el.classList.remove('cmdk-flash'); if (flashEl === el) flashEl = null; }, 2200);
}

export function mountCmdk(ctx) {
    const input = h('input', { type: 'text', class: 'cmdk-in', autocomplete: 'off', spellcheck: 'false', enterkeyhint: 'go',
        placeholder: '무엇이든 찾기 · 시키기 — 예: 테마 · 밍밍 5 · 룰렛 돌려 · 후원자 이름', 'aria-label': '찾기 · 빠른 명령', role: 'combobox',
        'aria-expanded': 'true', 'aria-controls': 'cmdk-list', 'aria-autocomplete': 'list' });
    const list = h('ul', { class: 'cmdk-list', id: 'cmdk-list', role: 'listbox', 'aria-label': '고를 거리' });
    const out = h('p', { class: 'cmdk-out', role: 'status', 'aria-live': 'polite' });
    const cardsBox = h('div', { class: 'cmdk-cards', hidden: true });
    const closeBtn = h('button', { type: 'button', class: 'btn xs cmdk-close', 'aria-label': '닫기' }, '닫기');
    const box = h('div', { class: 'cmdk-box', role: 'dialog', 'aria-modal': 'true', 'aria-label': '찾기 · 빠른 명령' },
        h('div', { class: 'cmdk-head' }, h('span', { class: 'cmdk-k', 'aria-hidden': 'true' }, 'Ctrl K'), input, closeBtn),
        list, out, cardsBox,
        h('p', { class: 'cmdk-foot' }, h('span', { class: 'cmdk-foot-k' }, 'Enter 실행 · ↑↓ 고르기 · Esc 닫기 — '),
            '탭 · 설정 · 선수 · 후원자 · 시그니처 · 대기함 · 장부 · 공지까지 찾아요(초성 ㅁㅁ 도). 모르는 말은 AI 가 명령으로 바꿔요(점수 · 게임은 [실행])'));
    const wrap = h('div', { class: 'cmdk', id: 'cmdk', hidden: true }, box);
    document.body.append(wrap);

    let items = [], opts = [], sel = 0, busy = false, back = null, spots = null;

    const isOpen = () => !wrap.hidden;
    const authed = () => { const v = document.body.dataset.view; return v === 'setup' || v === 'live'; };
    const panelEl = id => document.querySelector(`#tabbody .tabpanel[data-panel="${id}"]`);

    /* ── 찾을 거리 모으기 ── */
    function tabsNow() {
        const T = ctx.tabs;
        if (!T || !T.panels) return [];
        const grpOf = {};
        TILE_GROUPS.forEach(([g, ids]) => ids.forEach(id => { grpOf[id] = g; }));
        const locked = id => !!(T.locked && T.locked(id));
        const out = T.panels.map(p => ({ id: p.id, label: p.label || p.id, short: p.short || '', icon: p.icon || '',
            desc: TILE_DESC[p.id] || '', group: grpOf[p.id] || (p.rail ? '왼쪽 줄' : ''), locked: locked(p.id) }));
        for (const [id, [ic, label, desc]] of Object.entries(ACTS)) {
            out.push({ id, act: id, label, icon: ic, desc, group: grpOf[id] || '설정', locked: id === '@bank' ? locked('ops-system') : false });
        }
        return out;
    }

    // ⚙ 색인(cmdkindex.js) + 이미 연 탭에서 주운 제목 · 이름표 — 상자를 열 때마다 새로(탭 잠김 · 연 탭이 바뀐다)
    const HSEL = 'h2,h3,h4,summary,legend,label,.gm-title,.gm-tn,.gm-lbl,.gm-sub > b';
    const NOISE = '.count-badge,.tab-badge,.ops-sub,.gm-ts,.gm-info,.muted,small,input,select,textarea,.dk-badge,.st-news,.st-last,.ops-slider';
    function ownText(el) {
        let t = '';
        for (const n of el.childNodes) {
            if (n.nodeType === 3) t += n.nodeValue;
            else if (n.nodeType === 1 && !n.matches(NOISE)) t += ' ' + ownText(n);
        }
        return t;
    }
    function buildSpots() {
        const T = ctx.tabs;
        const byId = new Map(((T && T.panels) || []).map(p => [p.id, p]));
        const res = [], seen = new Set();
        for (const [tab, title, kw, find] of SPOTS) {
            const p = byId.get(tab), place = PLACE[tab];
            if (!p && !place) continue;                       // 그 탭이 없어졌다(다른 갈래에서 뺐다) — 건너뛴다
            const where = place ? place[1] : `${p.label} 탭`;
            res.push({ key: tab + '|' + title, tab, title, kw, find, where, ic: place ? place[0] : (p.icon || '⚙'),
                sub: p ? [p.label, p.short, TILE_DESC[tab]].filter(Boolean).join(' ') : place[1] });
            seen.add(tab + '|' + norm(title));
            if (!/^[#.]/.test(find)) seen.add(tab + '|' + norm(find));
        }
        // 이미 연 탭 — 화면에 있는 제목 · 이름표(색인에 없는 것만, 선수 이름이 든 것 · 숫자만인 것은 뺀다)
        const players = currentNames(ctx.slices || {}).map(norm).filter(Boolean);
        document.querySelectorAll('#tabbody .tabpanel[data-panel]').forEach(pn => {
            const tab = pn.dataset.panel, p = byId.get(tab);
            if (!p || tab === 'settings') return;             // 설정 화면 타일 = 탭 찾기와 같다
            const tabNames = [norm(p.label), norm(p.short)].filter(Boolean);      // 탭 맨 위 제목('📒 장부')은 탭 줄과 같다
            pn.querySelectorAll(HSEL).forEach(el => {
                const t = ownText(el).replace(/\s+/g, ' ').trim();
                const n = norm(t);
                if (n.length < 2 || t.length > 40 || /^[\d+\-]+$/.test(n) || tabNames.includes(n) || players.some(x => n.indexOf(x) !== -1)) return;
                if (seen.has(tab + '|' + n)) return;
                seen.add(tab + '|' + n);
                res.push({ key: tab + '|~' + t, tab, title: t, kw: '', find: t, where: `${p.label} 탭`, ic: p.icon || '⚙', sub: p.label, live: true });
            });
        });
        return res;
    }

    const memos = {};
    /** 조각(배열)이 그대로면 만든 줄도 그대로 — 글자마다 다시 만들지 않는다(맞추기 기억 WeakMap 이 줄에 붙어 있다) */
    function memoMap(k, arr, fn) {
        if (!Array.isArray(arr)) return [];
        const m = memos[k];
        if (m && m.src === arr) return m.out;
        const res = [];
        arr.forEach((x, i) => { const e = fn(x, i); if (e) res.push(e); });
        memos[k] = { src: arr, out: res };
        return res;
    }
    let donorMemo = { tags: undefined, tal: undefined, list: [] };
    function donorsNow(s) {
        const tags = s.donor_tags, tal = (s.tallies || {}).donors;
        if (donorMemo.tags === tags && donorMemo.tal === tal) return donorMemo.list;
        const map = new Map();
        if (tal && typeof tal === 'object') {
            for (const [k, v] of Object.entries(tal)) {
                const name = String((v && v.name) || k);
                if (!v || isAnon(name)) continue;
                map.set(k, { title: name, total: Number(v.total) || 0, count: Number(v.count) || 0 });
            }
        }
        if (tags && typeof tags === 'object') {
            for (const [k, e] of Object.entries(tags)) {
                if (!e || typeof e !== 'object' || isAnon(k)) continue;
                const d = map.get(k) || { title: k };
                d.pid = e.pid || '';
                d.chip = chipText(e);
                map.set(k, d);
            }
        }
        const lst = [...map.values()].map(d => ({ title: d.title, pid: d.pid || '',
            info: [d.total ? `이번 방송 ${won(d.total)} · ${num(d.count)}번` : '', d.chip ? d.chip.text : ''].filter(Boolean).join(' · ') }));
        donorMemo = { tags, tal, list: lst };
        return lst;
    }

    // 📒 장부(이번 방송) — 상자를 열 때 받는다(15초 안에 또 열면 받아 둔 것)
    const ledger = { rows: null, at: 0, busy: false };
    async function loadLedger() {
        if (ledger.busy || Date.now() - ledger.at < 15000) return;
        ledger.busy = true;
        try {
            const j = await getJSON('/api/ledger?session=current&limit=300');
            ledger.rows = Array.isArray(j.rows) ? j.rows : [];
        } catch (e) { /* 못 받으면 장부 묶음만 빠진다 — 다음에 열 때 다시 */ }
        ledger.at = Date.now();
        ledger.busy = false;
        if (isOpen()) paint(true);
    }

    function moreNow() {
        const s = ctx.slices || {};
        if (!spots) spots = buildSpots();
        return {
            spots,
            donors: donorsNow(s),
            sigs: memoMap('sig', sigsNow(), g => ({ title: g.title || `${num(g.amount)}원 시그니처`, kw: String(g.id), id: g.id, amount: g.amount })),
            pending: memoMap('pend', s.pending, p => p && p.id != null ? ({ id: p.id, title: p.name || '익명', sub: shownText(p), amount: p.amount,
                kind: p.kind, contrib: p.contrib, type: p.type }) : null),
            ledger: memoMap('ledger', ledger.rows, r => r && r.id != null ? ({ id: r.id, title: r.name || '익명', sub: shownText(r), amount: r.amount,
                time: hms(r.at) }) : null),
            notices: memoMap('notice', (s.notice || {}).msgs, (t, i) => ({ title: String(t || ''), i })),
            roulette: memoMap('roul', (s.roulette || {}).custom, (t, i) => ({ title: String(t || ''), i })),
        };
    }

    /* ── 그리기 ── */
    function paint(keep) {
        const was = keep && items[sel] ? items[sel].kind + ':' + items[sel].text : '';
        items = suggest(input.value, currentNames(ctx.slices || {}), tabsNow(), moreNow());
        sel = was ? Math.max(0, items.findIndex(it => it.kind + ':' + it.text === was)) : 0;
        if (sel >= items.length) sel = 0;
        const rows = [];
        opts = [];
        const heads = !!input.value.trim();
        let g = null;
        items.forEach((it, i) => {
            if (heads && it.group !== g) {
                g = it.group;
                const [gi, gn] = GROUPS[g] || ['', ''];
                rows.push(h('li', { class: 'cmdk-gh', role: 'presentation' }, h('span', { 'aria-hidden': 'true' }, gi), gn));
            }
            const b = h('button', { type: 'button', class: 'cmdk-item k-' + it.kind + (it.locked ? ' locked' : ''), tabindex: '-1' },
                h('span', { class: 'cmdk-ic', 'aria-hidden': 'true' }, it.ic || (it.kind === 'tab' ? '↗' : it.kind === 'fill' ? '✎' : '▶')),
                h('span', { class: 'cmdk-tx' }, h('span', { class: 'cmdk-t' }, it.label), it.sub ? h('span', { class: 'cmdk-sub' }, it.sub) : null),
                h('span', { class: 'cmdk-hint', 'aria-hidden': 'true' }, it.hint || HINT[it.kind] || ''));
            b.addEventListener('mousedown', e => e.preventDefault());            // 입력칸 커서를 뺏지 않게
            b.addEventListener('click', () => { sel = i; pick(); });
            const li = h('li', { role: 'option', id: 'cmdk-o' + i, 'aria-selected': i === sel ? 'true' : 'false', class: i === sel ? 'on' : '' }, b);
            opts.push(li);
            rows.push(li);
        });
        list.replaceChildren(...rows);
        input.setAttribute('aria-activedescendant', items.length ? 'cmdk-o' + sel : '');
        if (keep) mark();
    }
    function mark() {
        opts.forEach((li, i) => { li.classList.toggle('on', i === sel); li.setAttribute('aria-selected', i === sel ? 'true' : 'false'); });
        const on = opts[sel];
        if (on && on.scrollIntoView) {
            // 묶음 첫 줄이면 머리까지 보이게
            const prev = on.previousElementSibling;
            (prev && prev.classList.contains('cmdk-gh') ? prev : on).scrollIntoView({ block: 'nearest' });
        }
        input.setAttribute('aria-activedescendant', items.length ? 'cmdk-o' + sel : '');
    }
    function showCards(res) {
        if (!res) { cardsBox.hidden = true; cardsBox.replaceChildren(); return; }
        cardsBox.replaceChildren(cardsView(ctx, res, { compact: true }));
        cardsBox.hidden = false;
    }
    function say(text, lv) {
        out.textContent = text || '';
        out.dataset.lv = lv || '';
    }

    function open() {
        if (!authed() || isOpen()) return;
        back = document.activeElement;
        wrap.hidden = false;
        input.value = '';
        sel = 0;
        spots = null;                                   // 색인 · 연 탭 다시 줍기
        say('');
        showCards(null);
        paint();
        input.focus();
        // 시그니처 목록 · 이번 방송 장부는 바깥 왕복 — 오면 다시 그린다(고른 줄은 그대로)
        try { useLm(ctx.lm); } catch (e) { /* 무시 */ }
        if (!sigsNow()) loadSigs().then(() => { if (isOpen()) paint(true); }).catch(() => {});
        loadLedger();
    }
    /** 닫기 — restore: 열기 전 커서 자리로 돌려놓기. 찾아가기(설정 · 카드 · 장부 …)는 false — 엉뚱한 입력칸에 커서가 돌아가 폰 자판이 뜨지 않게 */
    function close(restore) {
        if (!isOpen()) return;
        wrap.hidden = true;
        const b = back;
        back = null;
        if (restore === false) { if (document.activeElement === input) input.blur(); return; }
        if (b && b.focus && document.contains(b)) { try { b.focus({ preventScroll: true }); } catch (e) { /* 무시 */ } }
    }

    /* ── 찾아가기 ── */
    /** 탭 열기 — 못 열면(방송 전 잠김) 상자에 까닭 */
    function openTab(id, what) {
        if (ctx.tabs && ctx.tabs.open(id)) return true;
        say(`'${what || id}' 은(는) 지금 열 수 없어요 — 방송을 시작하면 열려요`, 'bad');
        return false;
    }
    /** 찾을 곳에 내려앉기 — 그린 뒤에 찾는다(탭을 막 열었거나 목록을 서버에서 받는 중이면 잠깐씩 다시) */
    function land(root, finds, what, tries) {
        tries = tries || 0;
        const rootEl = typeof root === 'function' ? root() : root;
        let el = null;
        for (const f of [].concat(finds)) {                    // 여럿이면 보이는 것 먼저(없으면 처음 찾은 것)
            const e = locate(rootEl, f);
            if (e && visible(e)) { el = e; break; }
            if (e && !el) el = e;
        }
        // 아직 없다(탭을 막 열었다 · 서버에서 받는 중) → 잠깐씩 다시. 있는데 숨었으면 조금만 기다린다(접힌 칸 · 서랍 · ⋯ 판은 reveal 이 연다)
        const foldable = el && el.closest('details:not([open]), #drawer, #ctl-more');
        if ((!el && tries < 10) || (el && !visible(el) && !foldable && tries < 3)) { setTimeout(() => land(root, finds, what, tries + 1), 150); return; }
        const target = el ? blockOf(el) : null;
        if (target && reveal(target)) { flash(target); return; }
        if (!target) {
            if (rootEl && visible(rootEl)) reveal(rootEl);
            ctx.toast(`'${what}' 자리를 못 찾았어요 — 탭은 열어 뒀어요`, 'info', 2600);
            return;
        }
        // 있는데 숨어 있다(빈 목록 제목 · 고른 모드에서만 보이는 칸 · 방송 전) — 그 둘레의 보이는 블록이라도 보여 준다
        const live = document.body.dataset.view === 'live';
        let up = target.parentElement;
        while (up && up !== rootEl && !visible(up)) up = up.parentElement;
        if (live && up && up !== rootEl && rootEl && rootEl.contains(up) && reveal(up)) {
            flash(up);
            ctx.toast(`'${what}' 은(는) 지금 숨어 있어요 — 쓸 일이 있을 때만 나와요(그 둘레를 보여 드려요)`, 'info', 3200);
            return;
        }
        if (rootEl && visible(rootEl)) reveal(rootEl);
        ctx.toast(live ? `'${what}' 은(는) 지금 숨어 있어요 — 쓸 일이 있을 때만 나와요` : `'${what}' 은(는) 지금 화면에 안 보여요 — 방송을 시작하면 보여요`, 'info', 3200);
    }

    function goSpot(sp) {
        let root;
        if (sp.tab === '@side') root = document.getElementById('v-shell');
        else if (sp.tab === '@hdr') root = document.getElementById('hdr');
        else {
            if (!openTab(sp.tab, sp.where.replace(/ 탭$/, ''))) return;
            root = sp.tab === 'home' ? () => document.getElementById(document.body.dataset.view === 'live' ? 'home' : 'v-setup') : () => panelEl(sp.tab);
        }
        close(false);
        land(root, sp.find, sp.title);
    }
    function goPend(it) {
        close(false);
        if (isPhone()) document.dispatchEvent(new CustomEvent('lm:drawer', { detail: { pane: 'pend', open: true } }));
        const pend = document.getElementById('pending');
        const card = () => [...pend.querySelectorAll('.pcard')].find(c => c.dataset.id === it.text) || null;
        if (!card()) { ctx.toast('그 후원은 이미 처리됐어요 — 장부에서 볼 수 있어요', 'info'); return; }
        land(pend, card, it.label);
    }
    function goSig(it) {
        if (!openTab('sig-admin', '시그니처 관리')) return;
        close(false);
        const pn = () => panelEl('sig-admin');
        const qIn = pn() && pn().querySelector('.sg-q');
        if (qIn) { qIn.value = '#' + it.text; qIn.dispatchEvent(new Event('input', { bubbles: true })); }
        land(pn, () => { const p = pn(); return p && [...p.querySelectorAll('.sg-card')].find(c => { const i = c.querySelector('.sg-id'); return i && i.textContent === '#' + it.text; }); }, it.label);
    }
    function goLedger(name, time, what) {
        if (!openTab('ledger', '장부')) return;
        close(false);
        const pn = () => panelEl('ledger');
        const p0 = pn();
        if (p0) {
            const curBtn = p0.querySelector('.rc-seg-btn');                     // 첫 단추 = 이번 방송
            if (curBtn && curBtn.getAttribute('aria-pressed') !== 'true') curBtn.click();
            const qIn = [...p0.querySelectorAll('.rc-q')].find(visible);
            if (qIn) { qIn.value = name; qIn.dispatchEvent(new Event('input', { bubbles: true })); }
        }
        land(pn, () => {
            const p = pn();
            const rows = p ? [...p.querySelectorAll('li.rc-row')].filter(visible) : [];
            return (time && rows.find(li => { const t = li.querySelector('.rc-time'); return t && t.textContent === time; })) || rows[0] || null;
        }, what || name);
    }
    function goNotice(it) {
        if (!openTab('ops-notice', '공지')) return;
        close(false);
        land(() => panelEl('ops-notice'), () => { const p = panelEl('ops-notice'); return p && p.querySelector(`.ntc-row[data-i="${Number(it.text)}"]`); }, it.label);
    }
    function goRoul(it) {
        if (!openTab('roulette', '룰렛')) return;
        close(false);
        land(() => panelEl('roulette'), ['직접 입력 칸', '설정'], it.label);
    }

    async function pick() {
        if (busy) return;
        const it = items[sel];
        if (!it) return;
        if (it.kind === 'fill') { input.value = it.text; sel = 0; paint(); input.focus(); return; }
        if (it.kind === 'tab') {
            if (ctx.tabs && ctx.tabs.open(it.text)) close();
            else say('그 탭은 지금 열 수 없어요(방송을 시작하면 열려요)', 'bad');
            return;
        }
        if (it.kind === 'act') {
            if (it.text === '@practice') { close(); window.open('/practice/', 'lm-practice'); return; }
            if (it.locked) { say('은행 확장은 방송을 시작하면 열려요', 'bad'); return; }
            close(false);
            openBankExt();
            return;
        }
        if (it.kind === 'local') {
            const L = LOCAL.find(x => x.text === it.text);
            if (L) { L.run(); ctx.toast(L.msg, 'ok', 1800); close(); }
            return;
        }
        if (it.kind === 'spot') { goSpot(it.spot); return; }
        if (it.kind === 'pend') { goPend(it); return; }
        if (it.kind === 'sig') { goSig(it); return; }
        if (it.kind === 'ledger') { goLedger(it.name, it.time, it.label); return; }
        if (it.kind === 'notice') { goNotice(it); return; }
        if (it.kind === 'roul') { goRoul(it); return; }
        if (it.kind === 'donor') {
            if (it.pid) { close(false); openDonor(ctx, it.pid); }
            else goLedger(it.text, '', it.text);
            return;
        }
        busy = true;
        input.disabled = true;
        let last = '';
        try {
            const ok = await runCommand(ctx, it.text, {
                toast: false,
                said: msg => { last = msg; say(msg); return 1; },
                done: (row, msg) => { last = msg; say(msg, /^⚠️/.test(msg) ? 'bad' : ''); },
            });
            if (!ok) {
                say('🤖 무엇을 할지 보는 중…');
                const c = await askCommand(it.text);
                const d = c.data || {};
                if (c.ok && (d.kind === 'command' || d.kind === 'reply')) {
                    autoClient(d);
                    d.at = Date.now();
                    say(d.cards && d.cards.length ? (d.cards.some(x => x.state === 'ask') ? '눌러서 실행해 주세요 — 점수 · 게임은 [실행] 을 눌러야 해요' : '했어요') : (d.reply || ''));
                    showCards(d);
                } else {
                    showCards(null);
                    say(d.kind === 'question' ? `물어보는 말은 AI 도우미 탭에서 물어봐 주세요 — 여기는 시키는 말만 (예: 밍밍 5 · 공지 바꿔: …)`
                        : `'${it.text}' 은(는) 모르는 말이에요 — 예: 밍밍 5 · ${COMMAND_HINTS.slice(0, 4).join(' · ')} · 탭 · 설정 이름`, 'bad');
                }
            } else if (!/^⚠️|…$/.test(last)) {
                ctx.toast(last || '했어요', 'ok', 2200);
                close();
            }
        } finally {
            busy = false;
            input.disabled = false;
            if (isOpen()) input.focus();
        }
    }

    input.addEventListener('input', () => { sel = 0; say(''); showCards(null); paint(); list.scrollTop = 0; });
    input.addEventListener('keydown', e => {
        if (e.isComposing || e.keyCode === 229) return;          // 한글 조합 중 Enter · 화살표는 조합에 맡긴다
        if (e.key === 'ArrowDown') { e.preventDefault(); if (items.length) { sel = (sel + 1) % items.length; mark(); } }
        else if (e.key === 'ArrowUp') { e.preventDefault(); if (items.length) { sel = (sel - 1 + items.length) % items.length; mark(); } }
        else if (e.key === 'Enter') { e.preventDefault(); pick(); }
        else if (e.key === 'Tab') { e.preventDefault(); const it = items[sel]; if (it && (it.kind === 'run' || it.kind === 'fill')) { input.value = it.text; paint(); } }
    });
    closeBtn.addEventListener('click', close);
    wrap.addEventListener('mousedown', e => { if (e.target === wrap) close(); });

    // Ctrl+K · ⌘K — 입력칸 안에서도(브라우저 주소창 검사 단축키를 이 페이지에서는 빼앗는다). 한글 자판이어도 키 자리(KeyK)로 본다.
    document.addEventListener('keydown', e => {
        const k = (e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && (e.code === 'KeyK' || e.key === 'k' || e.key === 'K');
        if (k) {
            if (!authed()) return;
            e.preventDefault();
            e.stopPropagation();
            if (isOpen()) close(); else open();
            return;
        }
        if (e.key === 'Escape' && isOpen()) { e.preventDefault(); e.stopPropagation(); close(); }
    }, true);
    // 📱 폰 · 마우스 — 조종 줄 🔍 단추(header.js)가 쏜다
    document.addEventListener('lm:cmdk', () => open());

    return { open, close, isOpen };
}
