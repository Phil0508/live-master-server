/* 📚 학습 성적 — 오늘(이번 방송) · 전체 · 지난 방송(그날마다). 서버가 센 것을 그대로 보여 준다(화면은 세지 않는다).
   대표님 10-22 "본인도 한번 넣어보고 채점까지 해서 그날에 얼마나 맞췄나".
     큰 숫자 = 기계 답 맞힘 — 기계의 1순위 답(확실하든 아니든)이 사람이 준 사람과 같았던 비율(guess_hit · guess_miss)
     확실했던 것 — 기계가 '거의 확실' 이라 휴식 때 혼자 줬을 것의 채점(agree · disagree). 휴식을 믿어도 되나 보는 숫자
     몰라서 답 없음 — 기계가 답을 못 낸 것(사람이 정했다)
     ☕ 휴식 때 기계가 줌 · 그중 되돌림(= 틀렸던 것)
   지난 방송 — 방송 끝마다 서버가 days 에 한 줄(최근 30번).
   지우기: auto.reset_stats {scope} — 기록 줄 · 설정 · 지난 방송 줄은 남는다. */
import { h, num, hitRate, guessRate, noAnswer } from './common.js';
import { blockHead, sigOf, fill, once } from '../ops/common.js';

const SCOPES = [['session', '오늘 (이번 방송)'], ['total', '전체 (지금까지)']];

function pctText(r) { return r ? `${num(r.judged)}건 중 ${num(r.hit)}건 맞힘(${r.pct}%)` : '아직 없음'; }

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
            h('div', { class: 'au-pct-row' }, h('span', { class: 'au-pct-k' }, '기계 답 맞힘'), pct, sub),
            h('span', { class: 'au-bar', 'aria-hidden': 'true' }, bar),
            main, more);
    }));
    const daysList = h('ol', { class: 'au-days' });
    const daysEmpty = h('p', { class: 'empty' }, '아직 끝난 방송이 없어요 — 방송이 끝나면 그날 성적이 한 줄씩 쌓여요.');
    const el = h('section', { class: 'ops-blk' },
        blockHead('📚 학습 성적', '기계도 후원마다 답을 적고, 사람이 준 것과 맞춰 채점해요'), grid,
        h('h4', { class: 'au-days-h' }, '지난 방송'), daysList, daysEmpty);

    async function reset(scope, label) {
        const ok = await ctx.confirm({ title: `${label} 숫자를 지울까요?`, body: '맞힘 · 틀림 · 몰라서 · 휴식 때 준 것 숫자가 0 이 돼요.\n판단 기록 줄 · 지난 방송 성적 · 설정은 그대로 남아요.', ok: '지우기', cancel: '그대로 두기' });
        if (!ok) return;
        const res = await ctx.run('auto.reset_stats', { scope });
        if (res.ok) ctx.toast(`${label} 숫자를 지웠어요`, 'info');
    }

    const chip = (cls, k, v) => h('span', { class: 'au-n ' + cls }, h('small', null, k), h('b', null, num(v || 0)));
    let last = '';
    function render(ap) {
        const st = ap.stats || {};
        const days = Array.isArray(ap.days) ? ap.days : [];
        const sig = sigOf(st, days.length, days[0] && days[0].sid);
        if (sig === last) return;
        last = sig;
        SCOPES.forEach(([k]) => {
            const s = st[k] || {};
            const c = cards[k];
            const g = guessRate(s);
            c.pct.textContent = g ? g.pct + '%' : '—';
            c.sub.textContent = g ? `(${num(g.judged)}건 중 ${num(g.hit)}건)` : '아직 채점된 게 없어요';
            c.bar.style.width = (g ? g.pct : 0) + '%';
            c.bar.className = g ? (g.pct >= 95 ? 'good' : g.pct >= 85 ? 'warn' : 'bad') : '';
            fill(c.main, chip('good', '✓ 맞힘', s.guess_hit), chip('bad', '✗ 틀림', s.guess_miss), chip('hold', '몰라서 답 없음', noAnswer(s)),
                chip('auto', '☕ 휴식 때 기계가 줌', s.auto_done), chip('bad', '그중 되돌림', s.auto_undone));
            fill(c.more, '확실했던 것(휴식 때 혼자 줄 것): ', h('b', null, pctText(hitRate(s))),
                h('br'), `본 후원 ${num(s.n || 0)} · 무시 ${num(s.ignored || 0)} · 🤖 AI 채점: 맞힘 ${num(s.ai_agree || 0)} · 틀림 ${num(s.ai_disagree || 0)}`);
        });
        daysEmpty.hidden = days.length > 0;
        daysList.replaceChildren(...days.slice(0, 10).map(d => {
            const s = d.stats || {};
            const g = guessRate(s), r = hitRate(s);
            return h('li', null,
                h('span', { class: 'au-day-d' }, String(d.date || '').slice(5).replace('-', '/')),
                h('span', { class: 'au-day-v' }, '기계 답 ', h('b', null, g ? g.pct + '%' : '—'), g ? ` (${num(g.judged)}건 중 ${num(g.hit)})` : ''),
                h('span', { class: 'au-day-v' }, '확실 ', h('b', null, r ? r.pct + '%' : '—'), r ? ` (${num(r.judged)}건 중 ${num(r.hit)})` : ''),
                Number(s.auto_done) ? h('span', { class: 'au-day-v' }, `☕ 기계가 줌 ${num(s.auto_done)} · 되돌림 ${num(s.auto_undone || 0)}`) : null);
        }));
    }
    return { el, render };
}
