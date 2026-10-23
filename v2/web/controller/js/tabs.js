/* 🗂️ 탭 — 시안 B: 왼쪽 아이콘 줄(PC) · 위 가로 글자 줄(폰) + 가운데 칸.

   탭(panel) 하나 = { id, label, icon, group, mount(el, ctx) → { render(slices) }, badge?(slices) → 글자,
                      rail?, pre?, short?, home? }
     rail  — 왼쪽 줄에 보인다(아니면 ⚙ 설정 화면의 타일로 연다)
     pre   — 방송 전(방송 준비 화면)에도 열린다. 아닌 탭은 흐리게 + '방송을 시작하면 열려요'
     short — 줄에 쓰는 짧은 글자(없으면 label)
     home  — 그리는 탭이 아니라 첫 화면(방송 중 = #home 랭킹, 방송 전 = #v-setup 방송 준비)
     badge — 단추 옆 작은 숫자(예: 후원 콘솔 '2' = 아직 안 쓴 계좌 입금). 빈 글자면 숨긴다. 탭이 닫혀 있어도 늘 고친다.
   줄 순서는 RAIL_ORDER 한 곳 — '|' 는 구분선, '>' 다음은 맨 아래(설정 · 백업).
   줄에 없는 탭도 단추를 하나씩 만들어 숨겨 둔다(.tab-off) — 다른 파일이 `.tabbar .tab[data-tab="ai"]` 를
   눌러 여는 길(AI · 자동 진행 · 계좌 거울 · BGM)이 그대로 돈다. 숨은 탭에 새 소식(배지 · 안 읽은 AI 알림)이 있으면 '설정' 에 점.
   ⚠️ 열린 탭만 그린다(조각이 올 때마다 모든 탭을 그리면 느려진다). 다른 탭은 열 때 한 번 그린다.
   ⚠️ 탭을 못 그려도(오류) 다른 탭 · 대기함 · 점수판은 그대로 돈다 — 탭마다 따로 감싼다.
   페이지를 열면 늘 첫 화면(랭킹 · 방송 준비)부터. 마지막 탭 기억(lm2_tab)은 설정 화면의 '최근' 타일 표시에만 쓴다.
   클릭 기록(uistats)은 단추 class `tab` + data-tab 으로 센다 → 탭 id 를 바꾸지 말 것. */
import { h } from './util.js';
import { icon } from './icons.js';
import { tabChanged } from './backnav.js';     // ◀ 뒤로가기 — 지나온 탭(10-24)

const KEY = 'lm2_tab';
const PHONE = '(max-width: 899px)';

export const RAIL_ORDER = ['home', 'bgm', 'match', 'roulette', 'slot', 'dice', 'siggame', 'quiz', '|',
    'races', 'pinball', 'logs', 'ops-console', 'sigdisp', '>', 'settings', 'restore'];

/** 설정 화면에서 마지막으로 고른 타일 */
export function lastTile() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
}
function remember(id) {
    try { localStorage.setItem(KEY, id); } catch (e) { /* 개인 창 등 — 기억 못 해도 된다 */ }
}

export function mountTabs(els, ctx, panels) {
    const { rail, body, center } = els;
    const byId = new Map(panels.map(p => [p.id, p]));
    const made = {};          // id → { el, api }
    const btns = {};
    const badges = [];        // [panel, 배지 칸]
    let active = 'home', view = '';

    rail.setAttribute('role', 'tablist');
    rail.setAttribute('aria-label', '화면 고르기');

    const badgeOf = p => {
        if (!p.badge) return null;
        const b = h('span', { class: 'tab-badge', hidden: true });
        badges.push([p, b]);
        return b;
    };
    function railBtn(p) {
        const ic = icon(p.id) || (p.icon ? h('span', { class: 'tab-emo' }, p.icon) : null);
        const b = h('button', { type: 'button', class: 'tab', role: 'tab', 'data-tab': p.id, title: p.label, 'aria-selected': 'false',
            onclick: () => open(p.id, true) },
            ic ? h('span', { class: 'tab-ic', 'aria-hidden': 'true' }, ic) : null,
            h('span', { class: 'tab-t' }, p.short || p.label),
            badgeOf(p),
            h('span', { class: 'tab-dot', hidden: true, 'aria-hidden': 'true' }));
        btns[p.id] = b;
        return b;
    }

    // 왼쪽 줄 — 순서표대로, 순서표에 없는 rail 탭은 '>' 앞에
    const listed = new Set(RAIL_ORDER);
    const extraRail = panels.filter(p => p.rail && !listed.has(p.id));
    let pushed = false;
    for (const id of RAIL_ORDER) {
        if (id === '|') { rail.append(h('span', { class: 'tabsep', 'aria-hidden': 'true' })); continue; }
        if (id === '>') {
            extraRail.forEach(p => rail.append(railBtn(p)));
            rail.append(h('span', { class: 'rail-push', 'aria-hidden': 'true' }));
            pushed = true;
            continue;
        }
        const p = byId.get(id);
        if (p && p.rail) rail.append(railBtn(p));
    }
    if (!pushed) extraRail.forEach(p => rail.append(railBtn(p)));
    // 줄에 없는 탭 — 숨은 단추(다른 파일이 눌러 여는 길 · 배지)
    panels.filter(p => !btns[p.id]).forEach(p => {
        const b = h('button', { type: 'button', class: 'tab tab-off', 'data-tab': p.id, hidden: true, tabindex: '-1',
            onclick: () => open(p.id, true) }, p.label, badgeOf(p));
        btns[p.id] = b;
        rail.append(b);
    });

    // 설정에서 연 탭 — 가운데 칸 맨 위 '← 설정' 줄
    const crumbT = h('b');
    const crumb = h('div', { class: 'tab-crumb', hidden: true },
        h('button', { type: 'button', class: 'btn xs tab crumb-back', 'data-tab': 'settings', onclick: () => open('settings', true) },
            icon('back'), '설정'),
        crumbT);
    body.append(crumb);

    const isLocked = p => view === 'setup' && !p.pre;
    const isRail = id => { const p = byId.get(id); return !!(p && p.rail); };

    function ensure(id) {
        if (made[id]) return made[id];
        const p = byId.get(id);
        const el = h('div', { class: 'tabpanel', role: 'tabpanel', 'data-panel': id, hidden: true });
        body.append(el);
        let api = null;
        try { api = p.mount(el, ctx) || null; } catch (e) {
            console.error('[탭 ' + id + ']', e);
            el.textContent = '이 탭을 여는 중에 문제가 생겼어요 — 새로 고쳐 주세요';
        }
        made[id] = { el, api };
        return made[id];
    }

    function paintSel() {
        const railOn = isRail(active) ? active : 'settings';
        for (const [k, b] of Object.entries(btns)) {
            const on = k === railOn && !b.hidden;
            b.classList.toggle('on', on);
            if (b.getAttribute('role') === 'tab') b.setAttribute('aria-selected', on ? 'true' : 'false');
            const p = byId.get(k);
            const lock = !!p && isLocked(p);
            b.classList.toggle('locked', lock);
            if (lock) { b.setAttribute('aria-disabled', 'true'); b.title = (p.label || '') + ' — 방송을 시작하면 열려요'; }
            else if (b.hasAttribute('aria-disabled')) { b.removeAttribute('aria-disabled'); b.title = p ? p.label : ''; }
        }
        const home = btns.home;
        if (home) {
            const t = view === 'setup' ? '준비' : ((byId.get('home') || {}).short || '랭킹');
            const tt = home.querySelector('.tab-t');
            if (tt && tt.textContent !== t) tt.textContent = t;
            home.title = view === 'setup' ? '방송 준비' : '랭킹 — 점수판 첫 화면';
        }
    }

    /** 탭 열기 — user: 사람이 눌렀다(잠긴 탭이면 까닭을 알린다 · 폰은 그 칸으로 내려 준다) */
    function open(id, user) {
        const p = byId.get(id);
        if (!p) return false;
        if (isLocked(p)) {
            if (user) ctx.toast(`'${p.label}' 은(는) 방송을 시작하면 열려요`, 'info');
            return false;
        }
        if (!p.rail && !p.home && id !== 'settings') remember(id);
        if (user && id !== active) tabChanged(active, id);       // ◀ 뒤로가기가 돌아올 탭
        active = id;
        center.dataset.tab = id;
        for (const [k, m] of Object.entries(made)) m.el.hidden = k !== id;
        if (!p.home) ensure(id).el.hidden = false;
        crumb.hidden = !!p.rail || !!p.home;
        crumbT.textContent = crumb.hidden ? '' : p.label;
        paintSel();
        draw(ctx.slices);
        if (user) bringIntoView();
        return true;
    }

    // 폰 — 위 탭 줄을 누르면 그 칸이 화면 밖일 때 내려 준다(대기함이 먼저 서 있다)
    function bringIntoView() {
        if (!window.matchMedia || !matchMedia(PHONE).matches) return;
        const top = center.getBoundingClientRect().top;
        if (top < 0 || top > innerHeight * 0.6) {
            try { center.scrollIntoView({ block: 'start', behavior: 'smooth' }); } catch (e) { center.scrollIntoView(); }
        }
    }

    function paintBadges(slices) {
        for (const [p, el] of badges) {
            let t = '';
            try { t = String(p.badge(slices || {}) || ''); } catch (e) { t = ''; }
            if (el.textContent !== t) el.textContent = t;
            if (el.hidden !== !t) el.hidden = !t;
        }
        paintNews();
    }

    /** 숨은(설정 안) 탭의 새 소식 — 배지 글자 또는 안 읽은 AI 알림 */
    function newsText(id) {
        const b = btns[id];
        if (!b) return '';
        const u = b.querySelector('.ai-unread');
        if (u && u.textContent) return u.textContent;
        const g = b.querySelector('.tab-badge');
        return g && !g.hidden ? g.textContent : '';
    }
    function paintNews() {
        const dot = btns.settings && btns.settings.querySelector('.tab-dot');
        if (!dot) return;
        const any = panels.some(p => !p.rail && newsText(p.id));
        if (dot.hidden === any) dot.hidden = !any;
    }
    // 안 읽은 AI 알림은 chatlog.js 가 단추에 바로 붙인다 — 붙고 떨어질 때 '설정' 점을 맞춘다
    if ('MutationObserver' in window) {
        new MutationObserver(muts => {
            if (muts.some(m => !(m.target.classList && m.target.classList.contains('tab-dot')))) paintNews();
        }).observe(rail, { childList: true, subtree: true, characterData: true });
    }

    function draw(slices) {
        paintBadges(slices);
        const p = byId.get(active);
        if (!p || p.home) return;
        const m = ensure(active);
        if (m.api && m.api.render) {
            try { m.api.render(slices); } catch (e) { console.error('[탭 ' + active + ']', e); }
        }
    }

    open('home');
    return {
        /** main.js 가 조각마다 부른다 — v: 'setup' | 'live' */
        render(slices, v) {
            if (v && v !== view) {
                view = v;
                const p = byId.get(active);
                if (!p || isLocked(p)) open('home');
                else paintSel();
            }
            draw(slices);
        },
        open: id => open(id, true),
        /** ◀ 뒤로가기로 돌아가기 — 지나온 길에 또 적지 않는다 */
        back: id => open(id, false),
        /** 탭을 열지 않고 미리 그려만 둔다(숨긴 채) — 조종 줄 BGM ▶ 가 플레이어 자리를 만들 때([D] bgm.js) */
        prepare: id => { const p = byId.get(id); if (!p || p.home || isLocked(p)) return false; ensure(id); return true; },
        active: () => active,
        locked: id => { const p = byId.get(id); return !p || isLocked(p); },
        newsText,
        panels,
    };
}
