/* 🔥 지옥탈출 · 🏃 퇴근빵 — 목표를 넘기면 **서버가** 대기함에 '탈출 성공 · 퇴근 성공' 카드를 만든다(송출은 대기함에서).

   지옥탈출: [시작] hell.start{targets:[1등, 2등, 3등, 4등…]}(지금 점수 순으로 목표 · 시작 뒤 받은 점수만) ·
            줄마다 목표 hell.goal{name, goal}(0 = 목표 없음) · [화면에서 내리기 / 다시 띄우기] hell.show{on}(셈 · 카드는 계속) ·
            [끝내기] hell.off(기록은 남음) · [이어서 하기] hell.resume
   퇴근빵:   [방송에 띄우기/내리기] home.on{on} · 줄마다 퇴근 목표 home.goal{name, goal}(0 = 지움 · 목표를 올리면 다시 카드를 받을 수 있다)
   10-17 — 두 판은 무대(한 번에 하나)가 아니다. 대결 · 룰렛 · 퀴즈를 켜도 안 꺼지고, 무대를 뺏지도 않는다(그래서 묻지 않는다).
           주사위판 동안 · 시그니처가 나오는 동안은 방송판에서 잠깐 숨는다. 둘 다 켜면 지옥탈출이 먼저 보인다.
   ⚠️ 이름은 data 로만 넘긴다(글자로 끼워 넣지 않는다) — 따옴표 · & 가 든 이름도 그대로. */
import { h, num } from '../../util.js';
import { head, memo, syncVal, numInput, toInt, onEnter } from './common.js';

const KEY_T = 'lm2_hell_targets';

export function mountRaces(el, ctx) {
    const paint = memo();
    let hell = {}, home = {}, slices = {};

    /* 🔥 지옥탈출 */
    const hHead = head('🔥 지옥탈출', null);
    let saved = [50, 40, 30, 20];
    try { const v = JSON.parse(localStorage.getItem(KEY_T) || 'null'); if (Array.isArray(v) && v.length === 4) saved = v.map(x => Number(x) || 0); } catch (e) { /* 기억 없음 */ }
    const tIn = saved.map((v, i) => { const x = numInput({ class: 'gm-in num w64', 'aria-label': `${i + 1}등 목표(만원)` }); x.value = String(v); return x; });
    const startB = h('button', { type: 'button', class: 'btn pri gm-hellgo', onclick: hellStart }, '🔥 지옥탈출 시작');
    // 👁 방송판에서 내리기 · 다시 띄우기 — 셈 · 카드는 계속(기록이 안 날아간다)
    const offB = h('button', { type: 'button', class: 'btn gm-hellshow', onclick: async () => {
        const on = hell.shown === false;
        const res = await ctx.run('hell.show', { on });
        if (res.ok) ctx.toast(on ? '🔥 지옥탈출 판을 다시 띄웠어요' : '지옥탈출 판을 내렸어요 — 점수는 계속 세요', on ? 'ok' : 'info');
    } }, '화면에서 내리기');
    // 끝내기(기록은 남음) · 끝낸 판 이어서 하기
    const endB = h('button', { type: 'button', class: 'btn gm-hellend', onclick: async () => {
        if (!hell.on) {
            const res = await ctx.run('hell.resume', {});
            if (res.ok) ctx.toast('🔥 지옥탈출을 이어서 세요 (시작 때 기준 그대로)', 'ok');
            return;
        }
        const ok = await ctx.confirm({
            title: '지옥탈출을 끝낼까요?',
            body: '점수 세기를 멈추고 방송판에서 내려요.\n기록(목표 · 탈출)은 남아서 [이어서 하기] 로 다시 셀 수 있어요.',
            ok: '끝내기', cancel: '취소', danger: false,
        });
        if (!ok) return;
        const res = await ctx.run('hell.off', {});
        if (res.ok) ctx.toast('지옥탈출을 끝냈어요 (기록은 남아 있어요)', 'info');
    } }, '끝내기');
    const hNote = h('p', { class: 'gm-info strong' });
    const oNote = h('p', { class: 'gm-info strong' });
    const hRows = h('div', { class: 'gm-race' });
    const hellRowsMap = new Map();

    /* 🏃 퇴근빵 */
    const oHead = head('🏃 퇴근빵', async on => {
        const res = await ctx.run('home.on', { on });
        if (res.ok) ctx.toast(on ? '퇴근빵을 켜고 방송에 띄웠어요' : '퇴근빵을 껐어요', on ? 'ok' : 'info');
    });
    const oRows = h('div', { class: 'gm-race' });
    const homeRowsMap = new Map();

    el.append(h('div', { class: 'gm' },
        h('section', { class: 'gm-box hell' },
            hHead.el,
            h('p', { class: 'gm-info' }, '[시작] 을 누르는 순간의 등수(점수 순)로 목표가 정해지고, 그 뒤에 받은 점수만 셉니다(1점 = 1만 원). 목표를 채우면 대기함에 🔥 탈출 성공 카드가 떠요 — 송출하면 축하 팝업. 목표 0 = 목표 없음. 다른 게임을 켜도 안 꺼져요. 벌칙 룰렛은 룰렛 탭에서.'),
            h('div', { class: 'gm-row' }, h('span', { class: 'gm-lbl' }, '목표(만원)'),
                ...tIn.flatMap((x, i) => [h('span', null, `${i + 1}등`), x]), h('span', { class: 'gm-info' }, '5등부터는 4등과 같아요')),
            h('div', { class: 'gm-row' }, startB, offB, endB),
            hNote,
            hRows),
        h('section', { class: 'gm-box home' },
            oHead.el,
            h('p', { class: 'gm-info' }, '플레이어별 퇴근 목표 점수를 정하면 방송 화면에 진행 막대가 나와요. 목표를 채우면 대기함에 퇴근 카드가 떠요(송출은 대기함에서). 0 이면 목표를 지워요. 다른 게임을 켜도 안 꺼지고, 방송을 새로 시작하면 꺼져요(목표는 남아요).'),
            oNote,
            oRows)));

    async function hellStart() {
        const t = tIn.map(x => toInt(x.value));
        if (t.some(v => v === null || v < 0)) { ctx.toast('목표는 0 이상의 숫자(만원)로 적어 주세요', 'err'); return; }
        try { localStorage.setItem(KEY_T, JSON.stringify(t)); } catch (e) { /* 무시 */ }
        const again = !!hell.on;
        const ok = await ctx.confirm({
            title: again ? '지옥탈출을 처음부터 다시 잴까요?' : '지옥탈출을 시작할까요?',
            body: `지금 등수(점수 순)로 목표를 정해요.\n· 1등 ${t[0]}만 · 2등 ${t[1]}만 · 3등 ${t[2]}만 · 4등부터 ${t[3]}만\n· 이 순간부터 받은 점수만 셉니다` + (again ? '\n· 지난 판 탈출 카드는 대기함에서 걷혀요' : ''),
            ok: '🔥 시작', cancel: '취소', danger: false,
        });
        if (!ok) return;
        const res = await ctx.run('hell.start', { targets: t });
        if (res.ok) ctx.toast('🔥 지옥탈출 시작!', 'ok');
    }

    function hellGot(name) {
        const r = ((slices.players || {}).list || []).find(x => x.name === name);
        return Math.max(0, (r ? Number(r.score) || 0 : 0) - (Number((hell.base || {})[name]) || 0));
    }

    function paintHell() {
        const goals = hell.goals || {};
        const names = Object.keys(goals).sort((a, b) => (Number(goals[b]) || 0) - (Number(goals[a]) || 0) || (Number((hell.base || {})[b]) || 0) - (Number((hell.base || {})[a]) || 0));
        if (!names.length) {
            hRows.replaceChildren(h('p', { class: 'empty' }, hell.on ? '명단이 비어 있어요' : '꺼져 있어요 — [🔥 지옥탈출 시작] 을 누르면 지금 등수로 목표가 정해져요'));
            hellRowsMap.clear();
            return;
        }
        if (hRows.querySelector('.empty')) hRows.replaceChildren();
        for (const [n, r] of hellRowsMap) if (!names.includes(n)) { r.el.remove(); hellRowsMap.delete(n); }
        names.forEach((n, i) => {
            let r = hellRowsMap.get(n);
            if (!r) {
                const goal = numInput({ class: 'gm-in num w64', 'aria-label': `${n} 목표(만원)` });
                const send = async () => {
                    const v = toInt(goal.value);
                    if (v === null || v < 0) { ctx.toast('목표는 0 이상의 숫자(만원)로', 'err'); goal.dataset.sv = ''; ctx.rerender(); return; }
                    if (v === Number((hell.goals || {})[n])) return;
                    const res = await ctx.run('hell.goal', { name: n, goal: v });
                    if (res.ok) ctx.toast(`${n} 목표 ${v}만`, 'ok');
                };
                goal.addEventListener('change', send);
                onEnter(goal, () => goal.blur());
                r = { el: h('div', { class: 'gm-rrow' }), rank: h('span', { class: 'gm-rank' }), got: h('b', { class: 'gm-rgot' }), goal, st: h('span', { class: 'gm-rst' }) };
                r.el.append(r.rank, h('span', { class: 'gm-rn' }, n), r.got, h('span', { class: 'gm-info' }, '/ 목표'), goal, h('span', null, '만'), r.st);
                hellRowsMap.set(n, r);
            }
            const g = Number(goals[n]) || 0, got = hellGot(n);
            const esc = g > 0 && got >= g;
            r.rank.textContent = `${i + 1}등`;
            r.got.textContent = `${num(got)}만`;
            syncVal(r.goal, g);
            r.st.textContent = esc ? '탈출! 😇' : g > 0 ? `남은 ${num(Math.max(0, g - got))}만` : '목표 없음';
            r.el.classList.toggle('done', esc);
            if (hRows.children[i] !== r.el) hRows.insertBefore(r.el, hRows.children[i] || null);
        });
    }

    function paintHome() {
        const list = (slices.players || {}).list || [];
        const goals = home.goals || {};
        if (!list.length) { oRows.replaceChildren(h('p', { class: 'empty' }, '플레이어가 없어요')); homeRowsMap.clear(); return; }
        if (oRows.querySelector('.empty')) oRows.replaceChildren();
        const names = list.map(x => x.name);
        for (const [n, r] of homeRowsMap) if (!names.includes(n)) { r.el.remove(); homeRowsMap.delete(n); }
        list.forEach((p, i) => {
            const n = p.name;
            let r = homeRowsMap.get(n);
            if (!r) {
                const goal = numInput({ class: 'gm-in num w96', placeholder: '목표 점수', 'aria-label': `${n} 퇴근 목표 점수` });
                const send = async () => {
                    const raw = goal.value.trim();
                    const v = raw === '' ? 0 : toInt(raw);
                    if (v === null || v < 0) { ctx.toast('목표는 0 이상의 숫자(점)로', 'err'); goal.dataset.sv = ''; ctx.rerender(); return; }
                    if (v === (Number((home.goals || {})[n]) || 0)) return;
                    const res = await ctx.run('home.goal', { name: n, goal: v });
                    if (res.ok) ctx.toast(v ? `${n} 퇴근 목표 ${v}점` : `${n} 퇴근 목표를 지웠어요`, 'ok');
                };
                goal.addEventListener('change', send);
                onEnter(goal, () => goal.blur());
                r = { el: h('div', { class: 'gm-rrow' }), cur: h('span', { class: 'gm-info' }), goal, st: h('span', { class: 'gm-rst' }) };
                r.el.append(h('span', { class: 'gm-rn' }, n), r.cur, goal, r.st);
                homeRowsMap.set(n, r);
            }
            const g = Number(goals[n]) || 0, sc = Number(p.score) || 0;
            const done = g > 0 && sc >= g;
            r.cur.textContent = `지금 ${num(sc)}점`;
            syncVal(r.goal, g || '');
            r.st.textContent = done ? ((home.notified || []).includes(n) ? '퇴근! 🎉 (카드 보냄)' : '퇴근! 🎉') : g ? `남은 ${num(g - sc)}점` : '';
            r.el.classList.toggle('done', done);
            if (oRows.children[i] !== r.el) oRows.insertBefore(r.el, oRows.children[i] || null);
        });
    }

    return {
        render(s) {
            slices = s;
            hell = s.hell || {};
            home = s.home || {};
            const stage = (s.show || {}).stage;
            const had = Object.keys(hell.goals || {}).length > 0;      // 시작한 적 있음(끝내도 기록이 남는다)
            const shown = !!hell.on && hell.shown !== false;
            hHead.setPill(hell.on ? (shown ? '진행 중 · 방송판에 보임' : '진행 중 · 숨김') : (had ? '끝남 · 기록 남음' : '꺼짐'), hell.on ? 'hot' : '');
            startB.textContent = (hell.on || had) ? '🔥 처음부터 다시 시작' : '🔥 지옥탈출 시작';
            offB.textContent = (shown || !hell.on) ? '화면에서 내리기' : '👁 다시 띄우기';
            offB.disabled = !hell.on;
            endB.textContent = hell.on ? '끝내기' : '이어서 하기';
            endB.disabled = !had;
            // 방송판에서 잠깐 숨는 때 — 주사위판 동안(대표님 10-17) · 시그니처가 나오는 동안(늘 그랬다)
            const dice = stage === 'dicegame';
            hNote.textContent = shown && dice ? '🎲 주사위판이 떠 있는 동안은 방송판에서 잠깐 숨어요 — 점수는 계속 세요' : '';
            hNote.hidden = !hNote.textContent;
            oHead.setAir(!!home.on);
            oHead.setPill(home.on ? (shown ? '켜짐 · 지옥탈출 뒤에' : '켜짐 · 방송판에 보임') : '꺼짐', home.on ? 'live' : '');
            oNote.textContent = !home.on ? '' : shown ? '🔥 지옥탈출이 같은 자리를 쓰는 중이라 퇴근빵 판은 숨어 있어요 — 셈 · 퇴근 카드는 계속'
                : dice ? '🎲 주사위판이 떠 있는 동안은 방송판에서 잠깐 숨어요 — 셈 · 퇴근 카드는 계속' : '';
            oNote.hidden = !oNote.textContent;
            paintHell();
            paintHome();
        },
    };
}
