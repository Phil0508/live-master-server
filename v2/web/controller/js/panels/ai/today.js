/* 💰 '이번 방송 후원' 숫자 받기 — 랭킹 탭 숫자 카드 ①(kpis.js)이 그린다. 이 파일은 받기만 한다(그림 없음).
   옛 조종실 첫 화면 숫자 칸(skinToday) → 10-17 머리줄 💰 알약을 빼고(w2frame) 카드 ①로 옮겼다(w2center).
   GET /api/ai/board?today=1 의 today — 장부에서 센다(AI 채팅과 같은 셈 · 화면에만 뜬 소액은 빠진다).
     {건수, 합계금액, 많이_쏜_사람, 가장_큰{이름, 금액}|null}  — 받은 값은 common.js 의 today 저장소(subs · set · fresh)에 둔다.
   방송 중 화면 · 창이 보일 때만 10초마다. AI 탭이 열려 있으면 그쪽이 4초마다 받으니 따로 안 묻는다(fresh).
   받기 전에는 '—'(지어내지 않는다 — 그리는 쪽 규칙). */
import { call, today } from './common.js';

const EVERY = 10000;

export function startToday() {
    let live = false, timer = 0, busy = false, again = false;

    async function load(force) {
        if (!live || document.hidden || document.body.dataset.view !== 'live' || (!force && today.fresh(EVERY - 1000))) return;
        if (busy) { if (force) again = true; return; }
        busy = true;
        const r = await call('/api/ai/board?today=1&for=head');      // for=head — 서버는 안 본다(개발자 도구에서 AI 탭 것과 가려 보려고)
        busy = false;
        if (r.ok && 'today' in r.data) today.set(r.data.today === undefined ? null : r.data.today);
        else if (r.status && r.status !== 401 && today.data === undefined) today.set(null);      // 서버가 못 셈 — '못 셌어요'
        if (again) { again = false; load(true); }
    }
    document.addEventListener('visibilitychange', () => { if (!document.hidden) load(); });

    return {
        /** 후원이 새로 들어오거나 배정됐을 때 — 10초를 안 기다리고 바로 */
        refresh() { load(true); },
        render(slices, view) {
            const want = view === 'live' && !!(slices.session || {}).live;
            if (want === live) return;
            live = want;
            clearInterval(timer);
            timer = 0;
            if (live) { load(true); timer = setInterval(load, EVERY); }     // 방송이 새로 시작되면 바로 새 숫자
        },
    };
}
