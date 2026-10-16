/* 🔢 숫자 카드 4장 + 💱 정산 차액 한 줄 — 랭킹 탭 첫 화면(#kpis) · 시안 B 묶음 B(10-17 w2center).
   대표님 10-17: 카드 4장은 **랭킹 탭에서만**(다른 탭을 열면 #home 째로 숨는다).

   ① 이번 방송 후원 — 합계 · N건 · 가장 큰 후원(이름 · 금액)
      값: GET /api/ai/board?today=1 의 today(서버가 장부에서 센 것 그대로 — ai_facts.today_summary). 받기 전 '—', 못 세면 '못 셌어요'.
   ② 지금 1등 — players.list[0](서버가 기여도 순으로 세운 줄 = 점수판 첫 줄 = 방송판 순위) · 아랫줄 '2등 ○○ N점'
      ⚠️ 차이를 빼서 보여 주지 않는다(기여도 순이라 점수 차가 음수가 될 수 있다). 번외 판 중이면 '본판 기준'.
   ③ 배정 기다리는 후원 — 대기함 중 후원 카드(퇴근 · 탈출 · 기여도 카드 빼고) 건수 · 금액 합 · 제일 먼저 온 시각. 0건이면 회색.
   ④ 목표까지 — 목표 − 게이지(goal.js gaugeValue — 서버 · 방송판과 같은 식). 목표 0 이면 [정하기], 넘으면 '달성!'.
   💱 정산 차액(대표님 10-17) — 실제 받은 돈 / 점수로 들어간 돈 / 차액 · [까닭] 을 누르면 왜 다른지.
      값: GET /api/ledger/settle(로그인 · 서버가 셈 — ledger.settle). 화면은 받아 적기만 한다. 까닭들의 합 = 차액(서버 검사가 지킨다).

   그리기 규칙: 카드는 처음 한 번 만들고 render 때 **글자만** 바꾼다(innerHTML 통째 금지). 소리 없음. */
import { h, num, clock } from './util.js';
import { gaugeValue, openBasic } from './goal.js';
import { hicon } from './homeicons.js';
import { call, today, isDonation } from './panels/ai/common.js';
import { startToday } from './panels/ai/today.js';

const SETTLE_EVERY = 15000;

function setText(el, t) {
    t = String(t);
    if (el.textContent !== t) el.textContent = t;
}

function card(key, label, ic) {
    const kv = h('div', { class: 'kv' });
    const ks = h('div', { class: 'ks' });
    const el = h('div', { class: 'kpi kpi-' + key, 'data-kpi': key },
        h('div', { class: 'kl' }, h('span', { class: 'kl-t' }, label), h('span', { class: 'ki' }, hicon(ic))), kv, ks);
    return { el, kv, ks };
}

export function mountKpis(root, ctx) {
    const feed = startToday();

    /* ① 이번 방송 후원 */
    const c1 = card('today', '이번 방송 후원', 'won');
    const c1v = h('span', { class: 'kn' }, '—'), c1u = h('small', null, '원');
    c1.kv.append(c1v, c1u);
    const c1n = h('b', null, ''), c1big = h('span', { class: 'kbig' }, '');
    c1.ks.append(c1n, c1big);
    c1.el.title = '이번 방송 장부에서 센 합계 — 화면에만 뜬 소액 · 다시 보기는 빠져요';

    /* ② 지금 1등 */
    const c2 = card('top', '지금 1등', 'crown');
    const c2n = h('span', { class: 'kn' }, '아직 없음'), c2s = h('small', null, '');
    c2.kv.classList.add('kvn');
    c2.kv.append(c2n, c2s);
    const c2note = h('span', { class: 'kxtra', hidden: true }, '본판 기준');
    c2.el.querySelector('.kl-t').after(c2note);

    /* ③ 배정 기다리는 후원 */
    const c3 = card('wait', '배정 기다리는 후원', 'bell');
    const c3v = h('span', { class: 'kn' }, '0'), c3u = h('small', null, '건');
    c3.kv.append(c3v, c3u);
    c3.el.setAttribute('role', 'button');
    c3.el.tabIndex = 0;
    c3.el.title = '대기함 보기';
    const toPending = () => {
        // 폰 서랍(묶음 C)이 있으면 그쪽이 듣고 펼친다 — 없으면 대기함으로 굴려 간다
        const ev = new CustomEvent('lm-drawer', { detail: { open: 'full' }, cancelable: true });
        if (!window.dispatchEvent(ev)) return;
        const p = document.getElementById('pending');
        if (p) try { p.scrollIntoView({ block: 'start', behavior: 'smooth' }); } catch (e) { p.scrollIntoView(); }
    };
    c3.el.addEventListener('click', toPending);
    c3.el.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toPending(); } });

    /* ④ 목표까지 */
    const c4 = card('goal', '목표까지', 'flag');
    const c4v = h('span', { class: 'kn' }, '—'), c4u = h('small', null, '');
    c4.kv.append(c4v, c4u);
    const c4bar = h('i');
    const bar = h('div', { class: 'kbar' }, c4bar);
    const c4set = h('button', { type: 'button', class: 'btn xs kset', hidden: true, onclick: () => openBasic('.target-form input') }, '정하기');
    c4.ks.before(bar);
    c4.ks.append(h('span', { class: 'kgoal' }), c4set);
    const c4txt = c4.ks.querySelector('.kgoal');

    root.append(c1.el, c2.el, c3.el, c4.el);

    /* 💱 정산 차액 — 카드 밑 한 줄(폰에서는 카드 밀기 줄 밖) */
    const st = mountSettle(ctx);
    root.after(st.el);

    today.subs.add(paintToday);
    function paintToday(t) {
        if (t === undefined) { setText(c1v, '—'); c1u.hidden = true; setText(c1n, ''); setText(c1big, '받는 중…'); return; }
        if (t === null) { setText(c1v, '—'); c1u.hidden = true; setText(c1n, ''); setText(c1big, '못 셌어요 — 잠시 뒤 다시 셉니다'); return; }
        c1u.hidden = false;
        setText(c1v, num(t['합계금액']));
        setText(c1n, num(t['건수']) + '건');
        const b = t['가장_큰'];
        setText(c1big, b && b['금액'] ? ` · 가장 큰 후원 ${num(b['금액'])}원 (${b['이름'] || '익명'})` : '');
        c1big.title = b && b['금액'] ? `가장 큰 후원 — ${b['이름'] || '익명'} ${num(b['금액'])}원` : '';
    }
    paintToday(today.data);

    let lastSig = '';
    return {
        render(slices) {
            feed.render(slices, document.body.dataset.view);
            const P = slices.players || {};
            const list = P.list || [];

            /* ② */
            const a = list[0], b = list[1];
            const has = a && (Number(a.score) || Number(a.contribution));
            setText(c2n, has ? a.name : '아직 없음');
            c2n.title = has ? a.name : '';
            setText(c2s, has ? num(a.score) + '점' : '');
            setText(c2.ks, has && b ? `2등 ${b.name} ${num(b.score)}점` : has ? '2등 없음' : '점수가 들어오면 보여요');
            c2.ks.title = c2.ks.textContent;
            c2note.hidden = !P.extra_active;

            /* ③ */
            const pend = (slices.pending || []).filter(isDonation);
            const sum = pend.reduce((s, it) => s + (Number(it.amount) || 0), 0);
            const first = pend.reduce((m, it) => (Number(it.at) && (!m || Number(it.at) < m) ? Number(it.at) : m), 0);
            setText(c3v, num(pend.length));
            setText(c3.ks, pend.length ? `${num(sum)}원 · 제일 먼저 ${clock(first)}` : '기다리는 후원 없음');
            c3.el.classList.toggle('hot', pend.length > 0);

            /* ④ */
            const target = Number((slices.goal || {}).target) || 0;
            const v = gaugeValue(slices);
            c4set.hidden = !!target;
            bar.hidden = !target;
            c4.el.classList.toggle('done', !!target && v >= target);
            if (!target) { setText(c4v, '목표 없음'); setText(c4u, ''); setText(c4txt, ''); }
            else if (v >= target) { setText(c4v, '달성!'); setText(c4u, ''); setText(c4txt, `${num(v)} / ${num(target)}점`); }
            else { setText(c4v, num(target - v)); setText(c4u, '점 남음'); setText(c4txt, `${num(v)} / ${num(target)}점`); }
            const pct = target ? Math.max(0, Math.min(100, Math.round(v / target * 100))) : 0;
            const w = pct + '%';
            if (c4bar.style.width !== w) c4bar.style.width = w;

            /* 후원이 들어오거나 배정되면 ① · 💱 을 바로 새로(10초 · 15초를 안 기다린다) */
            const sig = (slices.pending || []).map(x => x.id).join(',') + '|' + list.reduce((s, p) => s + (Number(p.score) || 0), 0) +
                '|' + (P.extra || []).reduce((s, p) => s + (Number(p.score) || 0), 0) + '|' + ((slices.session || {}).id || '');
            if (sig !== lastSig) {
                const first = !lastSig;
                lastSig = sig;
                if (!first) feed.refresh();
                st.poke();
            }
            st.render(slices);
        },
    };
}

/* 💱 정산 차액 한 줄 + 까닭 펼침 */
function mountSettle(ctx) {
    const real = h('b', { class: 'sv' }, '—'), scored = h('b', { class: 'sv' }, '—'), diff = h('b', { class: 'sv sd' }, '—');
    const pts = h('small', { class: 'sp' }, '');
    const toggle = h('button', { type: 'button', class: 'btn xs st-why', 'aria-expanded': 'false', title: '차액이 생긴 까닭 보기' }, '까닭');
    const list = h('ul', { class: 'st-list' });
    const note = h('p', { class: 'st-note' }, '');
    const pop = h('div', { class: 'st-pop', hidden: true }, list, note);
    const el = h('div', { class: 'settle', id: 'settle', 'aria-label': '정산 차액' },
        h('div', { class: 'st-line' },
            h('span', { class: 'st-ic' }, hicon('scale')),
            h('span', { class: 'st-k' }, '정산'),
            h('span', { class: 'st-it', title: '이번 방송 장부에 들어온 실제 돈 — 화면에만 · 다시 보기 · 테스트는 빼고' }, '실제 받은 돈 ', real),
            h('span', { class: 'st-it', title: '배정한 후원마다 만 원 단위 점수((금액+4000)÷1만, 나머지 버림) × 1만 원' }, '점수로 들어간 돈 ', scored, pts),
            h('span', { class: 'st-it st-d' }, '차액 ', diff),
            toggle),
        pop);
    toggle.addEventListener('click', () => {
        const open = pop.hidden;
        pop.hidden = !open;
        toggle.setAttribute('aria-expanded', String(open));
        el.classList.toggle('open', open);
        if (open) load(true);
    });

    let data = null, busy = false, again = false, at = 0, timer = 0, failed = false;

    async function load(force) {
        if (document.hidden || document.body.dataset.view !== 'live') return;
        if (!force && Date.now() - at < SETTLE_EVERY - 1000) return;
        if (busy) { if (force) again = true; return; }
        busy = true;
        const r = await call('/api/ledger/settle');
        busy = false;
        at = Date.now();
        if (r.ok && r.data.settle) { data = r.data.settle; failed = false; paint(); }
        else if (r.status !== 401) { failed = true; paint(); }
        if (again) { again = false; load(true); }
    }
    let pokeT = 0;
    function poke() {
        // 같은 순간에 조각이 여러 번 와도 한 번만(1.2초 모아서)
        clearTimeout(pokeT);
        pokeT = setTimeout(() => load(true), 1200);
    }
    document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });

    function paint() {
        if (!data) {
            setText(real, '—'); setText(scored, '—'); setText(diff, failed ? '못 셌어요' : '—'); setText(pts, '');
            return;
        }
        setText(real, num(data.real) + '원');
        setText(scored, num(data.scored) + '원');
        setText(pts, `(${num(data.scored_pts)}점)`);
        const d = Number(data.diff) || 0;
        setText(diff, d ? (d > 0 ? '+' : '−') + num(Math.abs(d)) + '원' : '없음 ✓');
        el.classList.toggle('zero', !d);
        el.classList.toggle('neg', d < 0);
        // 까닭 — 0 이 아닌 것만, 큰 순서
        const rows = (data.why || []).filter(w => Number(w.won)).sort((x, y) => Math.abs(y.won) - Math.abs(x.won));
        const kids = rows.map(w => h('li', { 'data-why': w.key },
            h('span', { class: 'sw-l' }, h('b', null, w.label), h('small', null, w.hint)),
            h('span', { class: 'sw-n' }, num(w.n) + '건'),
            h('span', { class: 'sw-v' + (w.won < 0 ? ' neg' : '') }, (w.won > 0 ? '+' : '−') + num(Math.abs(w.won)) + '원')));
        if (!kids.length) kids.push(h('li', { class: 'st-empty' }, '차액이 없어요 — 받은 돈이 모두 점수로 들어갔어요'));
        list.replaceChildren(...kids);
        const parts = [];
        if (data.small_zero_n) parts.push(`그중 ${num(data.small_zero_n)}건은 5,999원 이하라 0점이었어요.`);
        if (data.hand && data.hand.n) parts.push(`참고: 나눠 줄 때 점수를 손으로 바꾼 배정 ${num(data.hand.n)}건(${(data.hand.won > 0 ? '+' : '−') + num(Math.abs(data.hand.won))}원) — 위 셈은 만 원 규칙대로예요.`);
        parts.push('+ 는 받았지만 점수에 안 들어간 돈, − 는 받은 것보다 점수가 더 들어간 몫이에요. 합하면 차액과 같아요.');
        setText(note, parts.join(' '));
    }
    paint();

    return {
        el,
        poke,
        render() {
            if (!timer) timer = setInterval(() => load(false), SETTLE_EVERY);
            if (!data && !busy && !at) load(true);
        },
    };
}
