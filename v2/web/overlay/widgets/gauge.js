/* 💰 목표 게이지 — players · goal 조각.
   합 = 운영비(bottom) + 본판 점수 합 + goal.offset, 목표 = goal.target(0 이면 막대를 숨긴다).
   - 막대 안쪽은 위아래 3px 씩 들어가 있어 (100% - 6px) 를 비율만큼 채운다(옛 것과 같다).
   - 금액 딱지는 채움 꼭대기를 따라 올라간다(수은주). 막대 안 4.5%~95.5% 에 가둔다.
     그 높이에 판(점수판 · 후원 순위 …)이 있으면 위나 아래 가까운 빈자리로 비키고, 빈자리가 없으면 숨는다(옛 placeGoalTip).
     어느 판이 어디 있는지는 무대(stage.bands)에 묻는다 — 남의 판 속은 안 본다.
   - 목표를 처음 넘는 순간 막대가 세 번 번쩍인다(옛 goal-flash). 처음 그림에서는 안 번쩍인다(OBS 를 켤 때마다 뜨지 않게). */
import { formatNum, gaugeTotal, restartClass } from '../util.js';

export function mount(root, lm, opts) {
    root.innerHTML = '<div class="gauge-wrap"><div class="goal-rail">'
        + '<div class="goal-rail-fill"></div>'
        + '<div class="goal-rail-tip"><span class="goal-rail-amt">💰 <span class="g-num">0</span></span></div>'
        + '</div></div>';
    const wrap = root.firstElementChild;
    const rail = root.querySelector('.goal-rail');
    const fill = root.querySelector('.goal-rail-fill');
    const tip = root.querySelector('.goal-rail-tip');
    const num = root.querySelector('.g-num');
    let reached = null;           // 지난번에 목표를 넘어 있었나(null = 아직 한 번도 안 그림)
    let tipF = 0.045;

    function placeTip() {
        const railTop = root.offsetTop + rail.offsetTop;
        const railH = rail.offsetHeight || 837;
        if (!rail.offsetHeight) return;                       // 막대가 숨어 있다(목표 없음)
        const half = (tip.offsetHeight || 76) / 2;
        const want = railTop + 3 + (railH - 6) * (1 - tipF);  // 딱지 가운데가 올 y(캔버스 좌표)
        const x2 = root.offsetLeft - 10, x1 = x2 - (tip.offsetWidth || 240);
        const taken = opts.stage.bands ? opts.stage.bands(x1, x2, opts.layer.id) : [];
        const hits = y => taken.some(([t, b]) => y + half > t && y - half < b);
        const lo = railTop + half, hi = railTop + railH - half;
        let y = Math.min(hi, Math.max(lo, want));
        if (hits(y)) {
            let down = y, up = y;
            while (down <= hi && hits(down)) down += 8;
            while (up >= lo && hits(up)) up -= 8;
            const okD = down <= hi, okU = up >= lo;
            if (!okD && !okU) { tip.style.opacity = '0'; return; }
            y = (okD && (!okU || down - want <= want - up)) ? down : up;
        }
        tip.style.opacity = '';
        tip.style.bottom = Math.round(railTop + railH - 1 - y) + 'px';   // translateY(50%) 라 가운데가 그 높이에 온다
    }

    function render() {
        const players = lm.get('players'), goal = lm.get('goal') || {};
        const tgt = Math.max(0, Number(goal.target) || 0);
        const tot = gaugeTotal(players, goal);
        wrap.classList.toggle('no-target', tgt <= 0);
        num.textContent = formatNum(tot);
        const f = tgt > 0 ? Math.min(1, Math.max(0, tot / tgt)) : 0;
        fill.style.height = 'calc((100% - 6px) * ' + f + ')';
        tipF = Math.min(0.955, Math.max(0.045, f));
        placeTip();

        const now = tgt > 0 && tot >= tgt;
        if (now && reached === false) restartClass(rail, 'goal-flash');
        reached = tgt > 0 ? now : false;
    }

    lm.on('players', render);
    lm.on('goal', render);
    if (opts.stage.onLayout) opts.stage.onLayout(placeTip);
}
