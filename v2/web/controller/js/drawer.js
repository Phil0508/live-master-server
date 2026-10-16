/* 🗄 오른쪽 칸 자리 잡기 · 📱 폰 아래 서랍 — 시안 B(10-17 · 묶음 C w2side).

   넓은 화면(900 이상) — 오른쪽 칸(#side) 위에서부터
     #say-slot 화면에 한마디 · #con-mini 후원 콘솔 미니 · section#pending 대기함(제목 줄 오른쪽에 section#undo ↩ 작은 단추) · #queue-fold 시그 대기줄(접힘)
   폰(900 아래) — 화면 아래에 늘 붙어 있는 서랍(#drawer)
     머리: [대기함 N │ 시그 송출 │ 한마디] · [↩ 무엇](되돌리기) · [전체 ▴]
     접힘 = 맨 앞 후원 한 장(선수 단추 · 나눠 주기 · 무시까지) · [전체 보기] = 화면 85% 까지 펼쳐 전부
     본문은 서랍 높이만큼 아래를 비워(--drawer-h) 점수판 마지막 줄(모금함 · 금액)이 서랍에 안 가린다.
   ⚠️ 칸은 **옮기기만** 한다(노드 이동 — 다시 만들지 않는다). 그래서 대기함 얼림 · 입력 중인 글 · 누르는 길 · 클릭 기록 구역(section id)이 그대로다.
   ⚠️ 서랍이 늘 보이므로 phone.js 의 '📥 새 후원 띠' 는 서랍이 있으면 안 띄운다.
   다른 파일이 서랍을 열 때: document.dispatchEvent(new CustomEvent('lm:drawer', {detail: {pane: 'pend' | 'con' | 'say', open: true}}))
     (숫자 카드 ③ '배정 기다리는 후원' 을 폰에서 누르면 — [B] kpis.js) */
import { h } from './util.js';
import { mountConsole } from './panels/ops/console.js';

const PHONE = '(max-width: 899px)';
const PANES = [['pend', '대기함'], ['con', '시그 송출'], ['say', '한마디']];

export function mountDrawer(ctx) {
    const $ = id => document.getElementById(id);
    const side = $('side'), drawer = $('drawer'), pending = $('pending'), undo = $('undo');
    const conMini = $('con-mini'), say = $('say-slot'), fold = $('queue-fold');
    if (!side || !drawer || !pending) return { render() {} };

    // 💸 후원 콘솔 미니 — 보내는 길은 후원 콘솔과 같은 함수(console.js)
    let mini = null;
    if (conMini) {
        const box = h('div', { class: 'cm', 'data-panel': 'con-mini' });     // 클릭 기록 구역 'con-mini'(uistats areaOf)
        conMini.append(box);
        try { mini = mountConsole(box, ctx, { mini: true }); } catch (e) { console.error('[후원 콘솔 미니]', e); }
    }

    // ── 서랍 뼈대 ──
    const count = h('b', { class: 'dr-n' }, '0');
    const tabs = PANES.map(([k, t]) => h('button', { type: 'button', class: 'dr-tab', role: 'tab', 'data-pane': k, 'aria-selected': 'false',
        onclick: () => setPane(k, k !== 'pend') }, t, k === 'pend' ? count : null));
    const undoSlot = h('div', { class: 'dr-undo' });
    const moreBtn = h('button', { type: 'button', class: 'btn xs dr-more', 'aria-expanded': 'false', title: '서랍을 펼쳐 대기함 전부 보기', onclick: () => setOpen(!open) }, '전체 ▴');
    const grab = h('button', { type: 'button', class: 'dr-grab', 'aria-label': '서랍 펼치기 · 접기', onclick: () => setOpen(!open) });
    const panes = {};
    for (const [k] of PANES) panes[k] = h('div', { class: 'dr-pane', 'data-pane': k, role: 'tabpanel', hidden: k !== 'pend' });
    drawer.replaceChildren(
        grab,
        h('div', { class: 'dr-head' }, h('div', { class: 'dr-tabs', role: 'tablist', 'aria-label': '서랍' }, tabs), undoSlot, moreBtn),
        h('div', { class: 'dr-body' }, Object.values(panes)));

    let pane = 'pend', open = false, onPhone = null, lastH = -1;
    const mq = window.matchMedia ? matchMedia(PHONE) : { matches: false };

    function setPane(k, autoOpen) {
        pane = k;
        drawer.dataset.pane = k;
        tabs.forEach(b => b.setAttribute('aria-selected', String(b.dataset.pane === k)));
        for (const [p, el] of Object.entries(panes)) el.hidden = p !== k;
        // 콘솔 · 한마디는 한 장보다 길다 — 고르면 내용만큼 편다(접을 땐 대기함으로)
        if (autoOpen) setOpen(true, true);
    }
    function setOpen(v, keepPane) {
        open = !!v;
        drawer.classList.toggle('open', open);
        moreBtn.textContent = open ? '접기 ▾' : '전체 ▴';
        moreBtn.setAttribute('aria-expanded', String(open));
        if (!open && !keepPane && pane !== 'pend') setPane('pend', false);
    }
    document.addEventListener('lm:drawer', e => {
        const d = (e && e.detail) || {};
        if (d.pane && panes[d.pane]) setPane(d.pane, false);
        if ('open' in d) setOpen(d.open, true);
    });
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && open && onPhone) setOpen(false); });

    // ── 칸 옮기기 ──
    function place() {
        const phone = mq.matches;
        if (phone === onPhone) return;
        onPhone = phone;
        if (phone) {
            panes.pend.append(pending);
            if (conMini) panes.con.append(conMini);
            if (say) panes.say.append(say);
            if (undo) undoSlot.append(undo);
        } else {
            // 제자리(오른쪽 칸) — 한마디 · 콘솔 미니 · 대기함 · 시그 대기줄 순서
            const before = fold && fold.parentNode === side ? fold : null;
            [say, conMini, pending].forEach(el => { if (el) side.insertBefore(el, before); });
            const slot = pending.querySelector('.undo-slot');
            if (undo && slot) slot.append(undo);
            setOpen(false);
            document.documentElement.style.removeProperty('--drawer-h');
            lastH = -1;
        }
    }
    place();
    if (mq.addEventListener) mq.addEventListener('change', () => { place(); ctx.rerender(); });

    // 본문 아래 여백 = 접힌 서랍 높이(펼친 동안엔 그대로 둔다 — 화면이 튀지 않게)
    function measure() {
        if (!onPhone || drawer.hidden || open) return;
        const hh = Math.round(drawer.getBoundingClientRect().height);
        if (hh && hh !== lastH) { lastH = hh; document.documentElement.style.setProperty('--drawer-h', hh + 'px'); }
    }
    if ('ResizeObserver' in window) new ResizeObserver(measure).observe(drawer);

    return {
        render(slices) {
            if (onPhone !== mq.matches) place();
            const live = document.body.dataset.view === 'live';
            const want = !(onPhone && live);
            if (drawer.hidden !== want) drawer.hidden = want;
            document.body.classList.toggle('has-drawer', !want);
            const n = (slices.pending || []).length;
            if (count.textContent !== String(n)) count.textContent = n;
            count.classList.toggle('zero', !n);
            // 한마디 칸이 비어 있으면(그 기능이 없으면) 탭을 숨긴다
            const sayTab = tabs[2];
            const sayEmpty = !say || !say.children.length;
            if (sayTab.hidden !== sayEmpty) sayTab.hidden = sayEmpty;
            if (sayEmpty && pane === 'say') setPane('pend', false);
            if (mini) { try { mini.render(slices); } catch (e) { console.error('[후원 콘솔 미니]', e); } }
            measure();
        },
        open: (k, v = true) => { if (k) setPane(k, false); setOpen(v, true); },
    };
}
