/* ⌨️ Ctrl+K(맥 ⌘K) 빠른 명령 — 어느 화면에서든 상자 하나를 띄워 말로 시킨다(대표님 10-17 시안 B 묶음 D).

   상자에 적는 말은 'AI 에게 물어보기' 글칸과 **같은 규칙**(panels/ai/commands.js 의 runCommand — 복사하지 않는다):
     '밍밍 5' → score.add · '슬롯 돌려' · '룰렛 돌려' · '대결 시작' · '+1분' · '올클리어' · '클립' · '다음 단계'(show.cue) …
   그 밖에 탭 이름('룰렛' · 'BGM' · '장부' …) → 그 탭 열기, 'BGM 다음 곡' · 'BGM 재생' → 조종 줄 BGM 과 같은 일.
   - 입력칸에 커서가 있어도 Ctrl+K 는 연다(대기함 입력 중에도). Esc · 바깥 누르기로 닫는다. ↑↓ 로 고르고 Enter.
   - 🗣️ 10-17 규칙에 안 맞으면 서버(/api/ai/command — 서버 규칙 → AI)에 명령인지 묻는다. 명령이면 상자 안에 카드
     ('🤖 밍밍에게 +5점 [실행] [취소]' · 안전한 건 '✅ … [되돌리기]'). 점수 · 게임은 [실행] 을 눌러야 한다(panels/ai/cards.js).
     물음이거나 AI 가 꺼졌으면 '모르는 말이에요' 와 예시만.
   - 로그인 전(로그인 · 연결 중 화면)에는 안 열린다(비공개 값 · 명령 길을 열지 않는다).
   - 소리 없음. 바깥 글자(선수 이름)는 textContent 로만. */
import { h } from './util.js';
import { runCommand, COMMAND_HINTS } from './panels/ai/commands.js';
import { currentNames } from './panels/ai/common.js';
import { askCommand, autoClient, cardsView } from './panels/ai/cards.js';
import { toggle as bgmToggle, next as bgmNext } from './panels/records/bgm.js';

const MAX_ITEMS = 8;
const LOCAL = [
    { text: 'BGM 다음 곡', run: () => bgmNext(true), msg: '🎵 다음 곡으로 넘겼어요' },
    { text: 'BGM 재생 · 멈춤', run: () => bgmToggle(), msg: '🎵 BGM 재생 · 멈춤' },
];

/** 적은 말 → 고를 거리(순수 — 검사용). names: 지금 판 선수, tabs: [{id,label,short}] 열 수 있는 탭 */
export function suggest(q, names, tabs) {
    q = String(q || '').trim();
    const flat = s => String(s || '').replace(/\s+/g, '').toLowerCase();
    const fq = flat(q);
    const out = [];
    const seen = new Set();
    const push = it => { const k = it.kind + ':' + it.text; if (!seen.has(k)) { seen.add(k); out.push(it); } };
    if (!q) {
        COMMAND_HINTS.slice(0, 5).forEach(t => push({ kind: 'run', text: t, label: t }));
        return out;
    }
    // 탭 이름을 그대로 적었으면 그 탭이 맨 위('룰렛' → 룰렛 탭 열기, 돌리기는 '룰렛 돌려')
    const tabHit = (tabs || []).filter(t => flat(t.label).includes(fq) || flat(t.short).includes(fq) || t.id === q);
    tabHit.filter(t => flat(t.label) === fq || flat(t.short) === fq || t.id === q)
        .forEach(t => push({ kind: 'tab', text: t.id, label: `${t.label} 탭 열기` }));
    // 선수 이름 — '밍 5' → '밍밍 5'(바로 실행) · '밍' → '밍밍 '(숫자를 이어 적게)
    const pm = q.match(/^([가-힣A-Za-z0-9]+?)\s*\+?(\d+)?\s*점?$/);
    if (pm) {
        const hit = (names || []).filter(n => n.indexOf(pm[1]) !== -1);
        hit.sort((a, b) => (a === pm[1] ? -1 : 0) - (b === pm[1] ? -1 : 0));
        hit.slice(0, 4).forEach(n => {
            if (pm[2]) push({ kind: 'run', text: `${n} ${pm[2]}`, label: `${n} +${pm[2]}점 주기` });
            else push({ kind: 'fill', text: `${n} `, label: `${n} — 점수 주기(숫자를 이어서 적어요)` });
        });
    }
    COMMAND_HINTS.filter(t => flat(t).includes(fq) || fq.includes(flat(t))).forEach(t => push({ kind: 'run', text: t, label: t }));
    LOCAL.filter(t => flat(t.text).includes(fq) || (fq.length >= 2 && flat(t.text).startsWith(fq.slice(0, 3)))).forEach(t => push({ kind: 'local', text: t.text, label: t.text }));
    tabHit.forEach(t => push({ kind: 'tab', text: t.id, label: `${t.label} 탭 열기` }));
    // 맨 끝 — 적은 말 그대로 해 보기(규칙에 맞으면 명령, 아니면 '모르는 말')
    if (!out.some(it => it.kind === 'run' && flat(it.text) === fq)) push({ kind: 'run', text: q, label: `'${q}' 그대로 하기` });
    return out.slice(0, MAX_ITEMS);
}

export function mountCmdk(ctx) {
    const input = h('input', { type: 'text', class: 'cmdk-in', autocomplete: 'off', spellcheck: 'false', enterkeyhint: 'go',
        placeholder: '무엇을 할까요? 예: 밍밍 5 · 룰렛 돌려 · +1분 · BGM', 'aria-label': '빠른 명령', role: 'combobox',
        'aria-expanded': 'true', 'aria-controls': 'cmdk-list', 'aria-autocomplete': 'list' });
    const list = h('ul', { class: 'cmdk-list', id: 'cmdk-list', role: 'listbox', 'aria-label': '고를 거리' });
    const out = h('p', { class: 'cmdk-out', role: 'status', 'aria-live': 'polite' });
    const cardsBox = h('div', { class: 'cmdk-cards', hidden: true });
    const closeBtn = h('button', { type: 'button', class: 'btn xs cmdk-close', 'aria-label': '닫기' }, '닫기');
    const box = h('div', { class: 'cmdk-box', role: 'dialog', 'aria-modal': 'true', 'aria-label': '빠른 명령' },
        h('div', { class: 'cmdk-head' }, h('span', { class: 'cmdk-k', 'aria-hidden': 'true' }, 'Ctrl K'), input, closeBtn),
        list, out, cardsBox,
        h('p', { class: 'cmdk-foot' }, 'Enter 실행 · ↑↓ 고르기 · Esc 닫기 — 모르는 말은 AI 가 명령으로 바꿔요(점수 · 게임은 [실행])'));
    const wrap = h('div', { class: 'cmdk', id: 'cmdk', hidden: true }, box);
    document.body.append(wrap);

    let items = [], sel = 0, busy = false, back = null;

    const isOpen = () => !wrap.hidden;
    const authed = () => { const v = document.body.dataset.view; return v === 'setup' || v === 'live'; };

    function tabsNow() {
        const T = ctx.tabs;
        if (!T || !T.panels) return [];
        return T.panels.filter(p => !(T.locked && T.locked(p.id))).map(p => ({ id: p.id, label: p.label || p.id, short: p.short || '' }));
    }

    function paint() {
        items = suggest(input.value, currentNames(ctx.slices || {}), tabsNow());
        if (sel >= items.length) sel = 0;
        list.replaceChildren(...items.map((it, i) => {
            const b = h('button', { type: 'button', class: 'cmdk-item k-' + it.kind, tabindex: '-1' },
                h('span', { class: 'cmdk-ic', 'aria-hidden': 'true' }, it.kind === 'tab' ? '↗' : it.kind === 'fill' ? '✎' : '▶'),
                h('span', { class: 'cmdk-t' }, it.label));
            b.addEventListener('mousedown', e => e.preventDefault());            // 입력칸 커서를 뺏지 않게
            b.addEventListener('click', () => { sel = i; pick(); });
            return h('li', { role: 'option', id: 'cmdk-o' + i, 'aria-selected': i === sel ? 'true' : 'false', class: i === sel ? 'on' : '' }, b);
        }));
        input.setAttribute('aria-activedescendant', items.length ? 'cmdk-o' + sel : '');
    }
    function mark() {
        [...list.children].forEach((li, i) => { li.classList.toggle('on', i === sel); li.setAttribute('aria-selected', i === sel ? 'true' : 'false'); });
        const on = list.children[sel];
        if (on && on.scrollIntoView) on.scrollIntoView({ block: 'nearest' });
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
        say('');
        showCards(null);
        paint();
        input.focus();
    }
    function close() {
        if (!isOpen()) return;
        wrap.hidden = true;
        const b = back;
        back = null;
        if (b && b.focus && document.contains(b)) { try { b.focus({ preventScroll: true }); } catch (e) { /* 무시 */ } }
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
        if (it.kind === 'local') {
            const L = LOCAL.find(x => x.text === it.text);
            if (L) { L.run(); ctx.toast(L.msg, 'ok', 1800); close(); }
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
                        : `'${it.text}' 은(는) 모르는 말이에요 — 예: 밍밍 5 · ${COMMAND_HINTS.slice(0, 4).join(' · ')} · 탭 이름`, 'bad');
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

    input.addEventListener('input', () => { sel = 0; say(''); showCards(null); paint(); });
    input.addEventListener('keydown', e => {
        if (e.isComposing || e.keyCode === 229) return;          // 한글 조합 중 Enter · 화살표는 조합에 맡긴다
        if (e.key === 'ArrowDown') { e.preventDefault(); if (items.length) { sel = (sel + 1) % items.length; mark(); } }
        else if (e.key === 'ArrowUp') { e.preventDefault(); if (items.length) { sel = (sel - 1 + items.length) % items.length; mark(); } }
        else if (e.key === 'Enter') { e.preventDefault(); pick(); }
        else if (e.key === 'Tab') { e.preventDefault(); const it = items[sel]; if (it && it.kind !== 'tab' && it.kind !== 'local') { input.value = it.text; paint(); } }
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

    return { open, close, isOpen };
}
