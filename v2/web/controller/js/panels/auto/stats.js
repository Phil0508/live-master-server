/* 🤖 자동 진행 — 숫자(이번 방송 · 전체). 서버가 센 것을 그대로 보여 준다(화면은 세지 않는다).
     맞힘 = 기계가 '줬을' 사람에게 사람도 줬다 · 틀림 = 다른 사람에게 줬거나 무시했다
     몰라서 보류 = 기계가 모르겠다고 남긴 것을 사람이 줬다 · 자동으로 줌 = 켬에서 기계가 준 것
   지우기: auto.reset_stats {scope} — 기록 줄 · 설정은 남는다. */
import { h, num, hitRate } from './common.js';
import { blockHead, sigOf, fill, once } from '../ops/common.js';

const SCOPES = [['session', '이번 방송'], ['total', '전체(지금까지)']];

export function mountStats(ctx) {
    const cards = {};
    const grid = h('div', { class: 'au-stats' }, SCOPES.map(([k, label]) => {
        const pct = h('b', { class: 'au-pct' });
        const sub = h('span', { class: 'au-pct-sub' });
        const bar = h('i');
        const main = h('div', { class: 'au-nums' });
        const more = h('p', { class: 'au-more' });
        const clr = h('button', { type: 'button', class: 'ops-mini', title: `${label} 숫자를 0 으로`, onclick: () => once(clr, () => reset(k, label)) }, '지우기');
        cards[k] = { pct, sub, bar, main, more };
        return h('div', { class: 'au-card', 'data-scope': k },
            h('div', { class: 'au-card-h' }, h('h4', null, label), clr),
            h('div', { class: 'au-pct-row' }, h('span', { class: 'au-pct-k' }, '맞힌 비율'), pct, sub),
            h('span', { class: 'au-bar', 'aria-hidden': 'true' }, bar),
            main, more);
    }));
    const el = h('section', { class: 'ops-blk' },
        blockHead('숫자', '맞힌 비율 = 기계가 줬을 후원 중 사람도 같은 사람에게 준 비율'), grid);

    async function reset(scope, label) {
        const ok = await ctx.confirm({ title: `${label} 숫자를 지울까요?`, body: '맞힘 · 틀림 · 보류 · 자동으로 줌 숫자가 0 이 돼요.\n아래 판단 기록 줄과 설정은 그대로 남아요.', ok: '지우기', cancel: '그대로 두기' });
        if (!ok) return;
        const res = await ctx.run('auto.reset_stats', { scope });
        if (res.ok) ctx.toast(`${label} 숫자를 지웠어요`, 'info');
    }

    const chip = (cls, k, v) => h('span', { class: 'au-n ' + cls }, h('small', null, k), h('b', null, num(v || 0)));
    let last = '';
    function render(ap) {
        const st = ap.stats || {};
        const sig = sigOf(st);
        if (sig === last) return;
        last = sig;
        SCOPES.forEach(([k]) => {
            const s = st[k] || {};
            const c = cards[k];
            const r = hitRate(s);
            c.pct.textContent = r ? r.pct + '%' : '—';
            c.sub.textContent = r ? `(${num(r.judged)}건 중 ${num(r.hit)}건)` : '아직 채점된 게 없어요';
            c.bar.style.width = (r ? r.pct : 0) + '%';
            c.bar.className = r ? (r.pct >= 95 ? 'good' : r.pct >= 85 ? 'warn' : 'bad') : '';
            fill(c.main, chip('good', '✓ 맞힘', s.agree), chip('bad', '✗ 틀림', s.disagree), chip('hold', '몰라서 보류', s.unknown), chip('auto', '🤖 자동으로 줌', s.auto_done));
            fill(c.more, `본 후원 ${num(s.n || 0)} · 무시 ${num(s.ignored || 0)} · 자동으로 준 것 되돌림 ${num(s.auto_undone || 0)} · 금액 게임 ${num(s.games || 0)}`);
        });
    }
    return { el, render };
}
