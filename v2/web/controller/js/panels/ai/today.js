/* 💰 머리줄 '이번 방송 후원' 칸 — 옛 조종실 첫 화면 숫자 칸(skinToday)을 옮겼다.
   GET /api/ai/board?today=1 의 today — 장부에서 센다(AI 채팅과 같은 셈 · 화면에만 뜬 소액은 빠진다).
   방송 중 화면 · 창이 보일 때만 10초마다. AI 탭이 열려 있으면 그쪽이 4초마다 받으니 따로 안 묻는다.
   받기 전에는 '—'(지어내지 않는다). 폰(900px 아래)에서는 머리줄이 좁아 숨긴다 — AI 탭 위에 같은 숫자가 있다. */
import { h, call, today } from './common.js';
import { won, num } from '../../util.js';

const EVERY = 10000;

export function mountTodayPill(before) {
    const v = h('b', null, '—');
    const s = h('span', { class: 'tp-s' });
    const el = h('span', { class: 'pill today-pill', hidden: true, title: '이번 방송 후원 — 장부에서 센 것 (화면에만 뜬 소액은 빠져요)' },
        h('span', { 'aria-hidden': 'true' }, '💰'), v, s);
    if (before && before.parentNode) before.parentNode.insertBefore(el, before);
    let live = false, timer = 0, busy = false;

    function paint(t) {
        if (t === undefined || t === null) { v.textContent = '—'; s.textContent = t === null ? '못 셌어요' : ''; return; }
        v.textContent = won(t['합계금액']);
        s.textContent = num(t['건수']) + '건';
    }
    today.subs.add(paint);

    async function load(force) {
        if (busy || !live || document.hidden || (!force && today.fresh(EVERY - 1000))) return;
        busy = true;
        const r = await call('/api/ai/board?today=1&for=head');      // for=head — 서버는 안 본다(개발자 도구에서 AI 탭 것과 가려 보려고)
        busy = false;
        if (r.ok && 'today' in r.data) today.set(r.data.today === undefined ? null : r.data.today);
    }
    document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });

    return {
        render(slices, view) {
            const want = view === 'live' && !!(slices.session || {}).live;
            if (want === live) return;
            live = want;
            el.hidden = !live;
            clearInterval(timer);
            timer = 0;
            if (live) { paint(today.data); load(true); timer = setInterval(load, EVERY); }     // 방송이 새로 시작되면 바로 새 숫자
        },
    };
}
