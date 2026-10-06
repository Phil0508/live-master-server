/* 🎯 목표 — 목표 점수를 정하면(goal.set {target}) 방송판 게이지가 그만큼 찬다.
   게이지 값 = 운영비 + 본판 점수 합 + 보정값(offset) — 서버 · 방송판과 같은 식. 번외 판 · 기여도는 안 들어간다.
   🏆 막대가 목표를 채우면 '달성!' 상자 — [▶ 승인(송출)] = goal.celebrate(방송판 축하 연출) · [닫기] = goal.dismiss(연출 없이 처리).
      둘 다 goal.done 에 그 목표를 적는다 → 목표를 바꾸면 다시 뜬다(옛 approveGoalEvent · dismissGoalEvent). */
import { num } from './util.js';

export function gaugeValue(slices) {
    const P = slices.players || {};
    const g = slices.goal || {};
    const sum = (P.list || []).reduce((a, p) => a + (Number(p.score) || 0), 0);
    return (Number((P.bottom || {}).score) || 0) + sum + (Number(g.offset) || 0);
}

export function mountGoal(root, ctx) {
    root.innerHTML = `
        <div class="sec-head"><h2>목표</h2><span class="muted small offset-note" hidden></span></div>
        <div class="gauge" role="meter" aria-label="목표 게이지" aria-valuemin="0">
            <div class="gbar"><i></i></div>
            <div class="gnum"><b class="cur">0</b><span class="sep">/</span><span class="tgt">목표 없음</span><span class="pct"></span></div>
        </div>
        <form class="goal-form">
            <label><span>목표 점수</span><input type="text" inputmode="numeric" placeholder="0 = 목표 없음" autocomplete="off"></label>
            <button class="btn pri" type="submit">정하기</button>
        </form>
        <p class="muted small">게이지 = 운영비 + 본판 점수 합 (번외 판 · 기여도는 안 들어가요)</p>
        <div class="goal-win" hidden>
            <div class="gw-head">🏆 목표치 100% 달성! <span>축하합니다 🎉</span></div>
            <p>방송 화면에 <b>게이지가 가운데로 커지는 축하 연출</b>을 띄울까요?</p>
            <div class="gw-btns"><button class="btn pri gw-go" type="button">▶ 승인 (송출)</button><button class="btn gw-no" type="button">닫기</button></div>
        </div>`;
    const form = root.querySelector('form');
    const input = form.querySelector('input');
    const meter = root.querySelector('.gauge');
    const bar = root.querySelector('.gbar i');
    const cur = root.querySelector('.cur');
    const tgt = root.querySelector('.tgt');
    const pct = root.querySelector('.pct');
    const offNote = root.querySelector('.offset-note');
    const win = root.querySelector('.goal-win');
    let lastTarget = null, winBusy = false;
    async function handle(type, msg) {
        if (winBusy) return;
        winBusy = true;
        const res = await ctx.run(type, {});
        winBusy = false;
        if (res.ok) ctx.toast(msg, 'ok');
    }
    root.querySelector('.gw-go').addEventListener('click', () => handle('goal.celebrate', '🏆 축하 연출을 방송에 띄웠어요'));
    root.querySelector('.gw-no').addEventListener('click', () => handle('goal.dismiss', '달성 알림을 닫았어요 (연출은 안 띄움)'));

    form.addEventListener('submit', async e => {
        e.preventDefault();
        const t = String(input.value).replace(/[,\s]/g, '');
        if (!/^\d{0,9}$/.test(t)) { ctx.toast('목표는 0 이상의 숫자로 적어 주세요', 'err'); return; }
        const target = Number(t || 0);
        const res = await ctx.run('goal.set', { target });
        if (res.ok) { ctx.toast(target ? `목표를 ${num(target)}점으로 정했어요` : '목표를 없앴어요', 'ok'); input.blur(); }
    });

    return {
        render(slices) {
            const g = slices.goal || {};
            const target = Number(g.target) || 0;
            const v = gaugeValue(slices);
            cur.textContent = num(v);
            tgt.textContent = target ? num(target) + '점' : '목표 없음';
            const p = target ? Math.max(0, Math.min(100, Math.round(v / target * 100))) : 0;
            pct.textContent = target ? ` ${Math.round(v / target * 100)}%` : '';
            bar.style.width = p + '%';
            meter.classList.toggle('reached', !!target && v >= target);
            win.hidden = !(target && v >= target && Number(g.done) !== target && !!(slices.session || {}).live);
            meter.setAttribute('aria-valuenow', String(v));
            if (target) meter.setAttribute('aria-valuemax', String(target)); else meter.removeAttribute('aria-valuemax');
            const off = Number(g.offset) || 0;
            offNote.hidden = !off;
            offNote.textContent = off ? `보정값 ${off > 0 ? '+' : ''}${num(off)} 포함` : '';
            // 적는 중이 아니면 서버 값으로 맞춘다
            if (document.activeElement !== input && target !== lastTarget) {
                input.value = target ? String(target) : '';
                lastTarget = target;
            }
        },
    };
}
