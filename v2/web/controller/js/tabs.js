/* 🗂️ 게임 · 도구 탭 — 대기함 · 점수판 아래에 탭 줄 하나.

   탭(panel) 하나 = { id, label, icon, group, mount(el, ctx) → { render(slices) } }
   panels/games.js · panels/tools.js 가 목록(PANELS)을 내보낸다 — 여기는 목록을 받아 줄을 세우기만 한다.
   ⚠️ 열린 탭만 그린다(조각이 올 때마다 모든 탭을 그리면 느려진다). 다른 탭은 열 때 한 번 그린다.
   ⚠️ 탭을 못 그려도(오류) 다른 탭 · 대기함 · 점수판은 그대로 돈다 — 탭마다 따로 감싼다.
   마지막에 연 탭은 이 컴퓨터에만 기억한다(새로 열면 그 탭부터). */
import { h } from './util.js';

const KEY = 'lm2_tab';

export function mountTabs(root, ctx, panels) {
    let active = null;
    try { active = localStorage.getItem(KEY); } catch (e) { active = null; }
    if (!panels.some(p => p.id === active)) active = panels.length ? panels[0].id : null;

    const bar = h('div', { class: 'tabbar', role: 'tablist' });
    const body = h('div', { class: 'tabbody' });
    root.append(bar, body);
    const made = {};          // id → { el, api }
    const btns = {};

    let lastGroup = null;
    panels.forEach(p => {
        if (p.group && p.group !== lastGroup) {
            if (lastGroup !== null) bar.append(h('span', { class: 'tabsep', 'aria-hidden': 'true' }));
            lastGroup = p.group;
        }
        const b = h('button', { type: 'button', class: 'tab', role: 'tab', 'data-tab': p.id, onclick: () => open(p.id) },
            p.icon ? h('span', { class: 'tab-ic', 'aria-hidden': 'true' }, p.icon) : null, p.label);
        btns[p.id] = b;
        bar.append(b);
    });

    function ensure(id) {
        if (made[id]) return made[id];
        const p = panels.find(x => x.id === id);
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

    function open(id) {
        active = id;
        try { localStorage.setItem(KEY, id); } catch (e) { /* 개인 창 등 — 기억 못 해도 된다 */ }
        Object.entries(btns).forEach(([k, b]) => { b.classList.toggle('on', k === id); b.setAttribute('aria-selected', k === id ? 'true' : 'false'); });
        Object.entries(made).forEach(([k, m]) => { m.el.hidden = k !== id; });
        const m = ensure(id);
        m.el.hidden = false;
        draw(ctx.slices);
    }

    function draw(slices) {
        if (!active) return;
        const m = ensure(active);
        if (m.api && m.api.render) {
            try { m.api.render(slices); } catch (e) { console.error('[탭 ' + active + ']', e); }
        }
    }

    if (active) open(active);
    return { render: draw, open };
}
