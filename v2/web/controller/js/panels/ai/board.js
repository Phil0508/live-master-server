/* 📋 상황판(B안) — AI 탭 위 네 칸 + 'AI 상태' 점 + 이번 방송 후원(화면 약속 2).
   GET /api/ai/board?today=1 — 서버가 사실표에서 바로 센다(AI 를 안 부른다).
   ⚠️ 탭이 열려 있고 보일 때만 4초마다 묻는다. 다른 탭으로 가거나 창이 가려지면 멈추고, 다시 보이면 바로 한 번 묻는다.
   칸 네 개는 늘 이 순서 · 이 intent(대기함 · 대결 · 목표 · 퇴근빵). 칸을 누르면 그 intent 로 물어본다(⚡ 서버 계산 답).
   ai.text 는 머리 점 옆 글자 — 마지막 AI 호출 결과(꺼짐 · 대기 · 연결됨 · 붐빔). */
import { h, call, today, INTENTS } from './common.js';
import { won, num } from '../../util.js';

const ORDER = ['pending', 'match', 'goal', 'race'];
const EVERY = 4000;

export function mountBoard(ctx, ask) {
    const tiles = {};
    const grid = h('div', { class: 'ai-board', role: 'group', 'aria-label': '상황판 — 누르면 자세히' });
    ORDER.forEach(intent => {
        const k = h('span', { class: 'k' }, INTENTS[intent]);
        const v = h('span', { class: 'v' }, '…');
        const s = h('span', { class: 's' });
        const bar = h('span', { class: 'bar', hidden: true }, h('i'));
        const el = h('button', { type: 'button', class: 'ai-tile', 'data-intent': intent, title: '누르면 자세히 알려줘요 (⚡ 서버 계산)',
            onclick: () => ask(intent) }, k, v, s, bar);
        tiles[intent] = { el, k, v, s, bar };
        grid.append(el);
    });

    const dot = h('span', { class: 'ai-health', 'data-state': 'idle', title: '마지막 AI 호출 결과예요. 위 칸 · ⚡ 단추는 AI 없이 서버가 계산해서 AI 가 붐벼도 돼요.' },
        h('i', { 'aria-hidden': 'true' }), h('span', null, '확인 중…'));
    const note = h('p', { class: 'ai-board-note', hidden: true });
    const todayEl = h('div', { class: 'ai-today', title: '장부에서 센 것 — 화면에만 뜬 소액은 빠져요' },
        h('span', { class: 'ai-today-k' }, '💰 이번 방송 후원'), h('b', { class: 'ai-today-v' }, '—'), h('span', { class: 'ai-today-s' }, '불러오는 중'));
    let intents = Object.assign({}, INTENTS);
    const intentSubs = new Set();

    let timer = 0, busy = false, shown = () => false;

    async function load() {
        if (busy) return;
        busy = true;
        const r = await call('/api/ai/board?today=1');
        busy = false;
        if (r.ok) {
            note.hidden = true;
            paint(r.data);
        } else {
            note.hidden = false;
            note.textContent = r.status === 401 ? '로그인이 풀렸어요 — 새로 고쳐 다시 들어가 주세요'
                : r.status === 0 ? '서버에 닿지 않아요 — 4초마다 다시 해 봐요 (마지막으로 받은 값을 보여 줘요)'
                : '상황판을 못 받았어요 — 4초마다 다시 해 봐요 (마지막으로 받은 값을 보여 줘요)';
        }
    }

    function paint(d) {
        (d.tiles || []).forEach(t => {
            const x = tiles[t.intent];
            if (!x) return;
            x.k.textContent = t.k || INTENTS[t.intent];
            x.v.textContent = t.v || '';
            x.s.textContent = t.s || '';
            x.el.classList.toggle('hot', !!t.hot);
            x.bar.hidden = t.pct == null;
            x.bar.firstElementChild.style.width = Math.max(0, Math.min(100, Number(t.pct) || 0)) + '%';
        });
        if (d.ai) {
            dot.dataset.state = d.ai.state || 'idle';
            dot.lastElementChild.textContent = d.ai.text || '';
        }
        if (d.intents && typeof d.intents === 'object') {
            intents = Object.assign({}, INTENTS, d.intents);
            intentSubs.forEach(fn => fn(intents));
        }
        if ('today' in d) today.set(d.today === undefined ? null : d.today);
    }

    function paintToday(t) {
        const v = todayEl.querySelector('.ai-today-v'), s = todayEl.querySelector('.ai-today-s');
        if (t === undefined) { v.textContent = '—'; s.textContent = '불러오는 중'; return; }
        if (!t) { v.textContent = '—'; s.textContent = '장부를 못 셌어요 (잠시 뒤 다시)'; return; }
        v.textContent = won(t['합계금액']);
        const top = (t['많이_쏜_사람'] || []).slice(0, 3).map(x => `${x['이름']} ${won(x['금액합'])}${x['횟수'] > 1 ? ` (${x['횟수']}번)` : ''}`);
        s.textContent = `${num(t['건수'])}건` + (top.length ? ' · 많이 쏜 사람: ' + top.join(' · ') : '');
    }
    today.subs.add(paintToday);
    paintToday(today.data);

    function tick() {
        if (!shown()) { stop(); return; }
        if (document.hidden) return;
        load();
    }
    function stop() { clearInterval(timer); timer = 0; }

    // 창이 다시 보이면 바로 한 번(가려진 창은 타이머가 느려진다)
    document.addEventListener('visibilitychange', () => { if (!document.hidden && timer && shown()) load(); });

    return {
        els: { grid, dot, note, today: todayEl },
        get intents() { return intents; },
        onIntents(fn) { intentSubs.add(fn); fn(intents); },
        /** 탭이 그려질 때마다 — 보이면 4초 타이머를 (다시) 건다 */
        wake(isShown) {
            shown = isShown;
            if (!timer && shown()) { load(); timer = setInterval(tick, EVERY); }
        },
        refresh: load,
        get polling() { return !!timer; },
    };
}
