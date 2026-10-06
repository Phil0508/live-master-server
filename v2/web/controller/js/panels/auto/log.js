/* 🤖 자동 진행 — 최근 판단 기록(서버가 60건 들고 있다). 한 줄 = 후원 하나:
     기계가 뭐라고 판단했나(→ 하율 · 보류) · 까닭 · 사람이 한 일(누구에게 · 무시) · 판정(맞힘 · 틀림 …) · 금액 게임
   [틀린 것만] 으로 좁혀 볼 수 있다(이 컴퓨터에서만 기억). */
import { h, num, won, GAMES, HELD, outcomeOf, hm } from './common.js';
import { josaRo } from '../ai/common.js';
import { blockHead, sigOf, fill } from '../ops/common.js';

const FILTERS = [['all', '전체'], ['bad', '✗ 틀린 것만'], ['hold', '보류만'], ['auto', '🤖 자동으로 준 것']];
const KEY = 'lm2_auto_log_filter';

export function mountLog(ctx) {
    let filter = 'all';
    try { filter = localStorage.getItem(KEY) || 'all'; } catch (e) { filter = 'all'; }
    const chips = {};
    const bar = h('div', { class: 'ops-chips au-filter' }, FILTERS.map(([k, label]) => {
        const b = h('button', { type: 'button', class: 'ops-chip sm', 'aria-pressed': 'false', onclick: () => {
            filter = k;
            try { localStorage.setItem(KEY, k); } catch (e) { /* 개인 창 — 기억 못 해도 된다 */ }
            last = '';
            ctx.rerender();
        } }, label);
        chips[k] = b;
        return b;
    }));
    const list = h('ol', { class: 'au-log' });
    const empty = h('p', { class: 'empty' });
    const el = h('section', { class: 'ops-blk' },
        blockHead('최근 판단 기록', '기계가 한 판단 · 사람이 한 일 — 최근 60건'), bar, list, empty);

    function pass(r) {
        if (filter === 'bad') return r.outcome === 'disagree';
        if (filter === 'hold') return r.outcome === 'unknown' || (r.outcome === 'pending' && r.held);
        if (filter === 'auto') return r.outcome === 'auto' || r.was_auto;
        return true;
    }

    function machine(r) {
        if (r.asking) return [h('span', { class: 'au-m wait' }, '🤖 보는 중…')];
        if (!('target' in r)) return [h('span', { class: 'au-m dim' }, '🤖 판단 전에 사람이 먼저 처리')];
        const conf = Math.round((Number(r.confidence) || 0) * 100);
        const src = r.source ? ` · ${r.source}` : '';
        if (r.act) {
            return [h('span', { class: 'au-m go' }, '🤖 → ', h('b', null, r.target), ` (거의 확실 ${conf}%${src})`),
                r.held && r.held !== 'unsure' ? h('span', { class: 'au-m dim' }, ' — ' + (HELD[r.held] || r.held)) : null];
        }
        const guess = r.target ? [' — ', h('b', null, r.target), `${josaRo(r.target)} 보임 ${conf}%${src}`] : ' — 누구 것인지 모름';
        return [h('span', { class: 'au-m hold' }, '🤖 보류', guess),
            r.held && r.held !== 'unsure' ? h('span', { class: 'au-m dim' }, ' · ' + (HELD[r.held] || r.held)) : null];
    }

    function line(r, sid) {
        const [txt, cls] = outcomeOf(r, sid);
        const g = r.game;
        const gi = g ? (GAMES[g.game] || {}).icon || '🎮' : '';
        return h('li', { class: 'au-row o-' + (r.outcome || 'pending') },
            h('div', { class: 'au-r1' },
                h('span', { class: 'au-t' }, hm(r.at)),
                h('b', { class: 'au-who' }, r.name || '익명'),
                h('span', { class: 'au-amt' }, won(r.amount)),
                r.mode === 'on' ? h('span', { class: 'au-tagm on' }, '켬') : h('span', { class: 'au-tagm' }, '그림자'),
                h('span', { class: 'au-o ' + cls }, txt)),
            h('div', { class: 'au-r2' }, machine(r)),
            r.why ? h('div', { class: 'au-why' }, '까닭: ' + r.why + (r.held_err ? ` (${r.held_err})` : '')) : null,
            r.human ? h('div', { class: 'au-human' }, '👤 사람: ', h('b', null, r.human), r.split ? ' (나눠 줌)' : '', r.early ? ' (기계보다 먼저)' : '') : null,
            r.undone ? h('div', { class: 'au-human' }, `↩ 되돌림 ${num(r.undone)}번` + (r.was_auto ? ' — 기계가 준 것을 사람이 되돌렸어요' : '')) : null,
            g ? h('div', { class: 'au-game s-' + (g.status || '') }, gi + ' ', g.text || '') : null,
            r.test ? h('div', { class: 'au-why' }, '🧪 시험 후원 — 숫자에는 안 세요') : null);
    }

    let last = '';
    function render(ap, slices) {
        const rows = Array.isArray(ap.log) ? ap.log : [];
        const sid = ((slices || {}).session || {}).id || '';
        const sig = sigOf(rows, filter, sid);
        if (sig === last) return;
        last = sig;
        Object.entries(chips).forEach(([k, b]) => { b.classList.toggle('on', k === filter); b.setAttribute('aria-pressed', k === filter ? 'true' : 'false'); });
        const shown = rows.filter(pass);
        fill(list, shown.map(r => line(r, sid)));
        empty.hidden = shown.length > 0;
        empty.textContent = rows.length ? '이 조건에 맞는 기록이 없어요' : '아직 판단한 후원이 없어요 — 자동 진행이 그림자 · 켬이면 후원이 들어올 때마다 여기에 적혀요';
    }
    return { el, render };
}
