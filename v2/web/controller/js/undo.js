/* ↩ 되돌리기 · 최근 기록.

   - 큰 [↩ 되돌리기] 단추 아래에 '무엇이 되돌려지는지' 를 미리 적어 둔다(누르기 전에 본다).
   - 누르면 score.undo {ref} — 화면에 보이는 그 묶음(ref)을 콕 집어 보낸다.
     ⚠️ ref 없이 보내면 '서버의 마지막 것' 이 되돌려진다. 두 번 눌리면(더블클릭 · 느린 연결) 그 앞 것까지 지워진다.
        ref 를 실어 보내면 두 번째 누름은 서버가 '이미 되돌렸습니다' 로 막는다.
   - 후원을 준 것을 되돌리면 그 후원은 대기함으로 돌아온다(서버가 한다) — 알림에 그렇게 적는다.
   - 최근 기록: 마지막 10줄 — "하율 +5 (3→8)" */
import { h, signed, num, clock } from './util.js';

const SHOW = 10;

export function describe(l) {
    const pre = l.list === 'extra' ? '[번외] ' : '';
    if (l.kind === 'contrib' || (!l.val && l.cval)) {
        return `${pre}${l.name} 기여도 ${signed(l.cval)} (${num(l.cbefore)}→${num(l.cafter)})`;
    }
    let s = `${pre}${l.name} ${signed(l.val)} (${num(l.before)}→${num(l.after)})`;
    if (l.cval != null && l.cval !== l.val) s += ` · 기여도 ${signed(l.cval)}`;
    return s;
}

function group(logs, ref) {
    return logs.filter(l => l.ref === ref);
}

function short(rows) {
    // 같은 묶음 = 한 번 누른 것(나눠 주기면 여러 명). 위에서부터 서버가 넣은 순서의 거꾸로라 뒤집어 읽는다
    return rows.slice().reverse().map(l => `${l.list === 'extra' ? '[번외] ' : ''}${l.name} ${l.kind === 'contrib' ? '기여도 ' + signed(l.cval) : signed(l.val)}`).join(' · ');
}

function source(ref) {
    return String(ref || '').startsWith('don_') ? '후원' : '손으로';
}

export function mountUndo(root, logsRoot, ctx) {
    root.innerHTML = `
        <button class="undo-btn" type="button" disabled>
            <span class="ic" aria-hidden="true">↩</span>
            <span class="tx"><b>되돌리기</b><small class="what">되돌릴 것이 없어요</small></span>
        </button>`;
    logsRoot.innerHTML = `
        <div class="sec-head"><h2>최근 기록</h2><span class="muted small">마지막 ${SHOW}줄</span></div>
        <ol class="loglist"></ol>
        <p class="empty">아직 기록이 없어요</p>`;
    const btn = root.querySelector('.undo-btn');
    const what = root.querySelector('.what');
    const ol = logsRoot.querySelector('.loglist');
    const empty = logsRoot.querySelector('.empty');
    let busy = false, lastKey = '';

    btn.addEventListener('click', async () => {
        if (busy) return;
        const logs = ctx.slices.logs || [];
        if (!logs.length) return;
        const ref = logs[0].ref;
        const rows = group(logs, ref);
        // ⚠️ 끝난(또는 취소한) 번외 판의 기록 — 서버는 번외 판 명단이 비어 있어 점수를 못 빼고 기록만 지운다.
        //    본판에 더해진 점수는 그대로라, 모르고 누르면 '되돌렸다' 고 믿게 된다 → 먼저 알린다.
        const P = ctx.slices.players || {};
        if (rows.some(l => l.list === 'extra') && !P.extra_active) {
            const go = await ctx.confirm({
                title: '끝난 번외 판의 기록이에요',
                body: `${short(rows)}\n번외 판이 이미 끝나서, 되돌려도 점수는 바뀌지 않고 이 기록만 지워집니다.\n본판 점수를 고치려면 점수판의 [+점수] 칸에 빼기(-)로 적어 주세요.`,
                ok: '기록만 지우기', cancel: '그대로 두기',
            });
            if (!go) return;
        }
        busy = true;
        btn.disabled = true;
        btn.classList.add('sending');
        const res = await ctx.run('score.undo', { ref });
        busy = false;
        btn.classList.remove('sending');
        if (res.ok) {
            const back = String(ref).startsWith('don_') ? ' — 후원은 대기함으로 돌아갔어요' : '';
            ctx.toast(`되돌렸어요: ${short(rows)}${back}`, 'ok', 5000);
        }
        ctx.rerender();
    });

    return {
        render(slices) {
            const logs = slices.logs || [];
            btn.disabled = busy || !logs.length;
            if (logs.length) {
                const rows = group(logs, logs[0].ref);
                const stale = rows.some(l => l.list === 'extra') && !(slices.players || {}).extra_active;
                what.textContent = `${source(logs[0].ref)} · ${short(rows)}${stale ? ' (끝난 번외 판)' : ''}`;
            } else {
                what.textContent = '되돌릴 것이 없어요';
            }
            const key = JSON.stringify(logs.slice(0, SHOW));
            if (key === lastKey) return;
            lastKey = key;
            empty.hidden = logs.length > 0;
            ol.replaceChildren(...logs.slice(0, SHOW).map(l => h('li', { class: 'log' + ((l.val || l.cval || 0) < 0 ? ' neg' : '') },
                h('span', { class: 'lt' }, clock(l.at, true)),
                h('span', { class: 'lx' }, describe(l)),
                h('span', { class: 'ls tag plain' }, l.list === 'bottom' ? '운영비' : (l.kind === 'contrib' ? (l.why || '기여도') : source(l.ref))))));
        },
    };
}
