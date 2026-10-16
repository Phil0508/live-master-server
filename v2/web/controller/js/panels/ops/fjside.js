/* 🏺 모금함 깃발 왼쪽 / 오른쪽 — 옛 조종실 모금함 줄 [◀ 왼쪽][오른쪽 ▶](옛 /api/fundjar/side, 대표님 10-03).
   누르면 fundjar.side {side} — 서버가 점수판 · 깃발 자리(layout 조각)를 한 줄로 같이 적는다(v2/server/domain/oldlayout.py).
   왼쪽이면 점수판이 깃발 폭만큼 오른쪽으로 비킨다. 편집기에서 손으로 다시 옮기면 그게 이긴다(그때는 '따로 놓임').
   지금 어느 쪽인지는 layout 조각으로 센다 — sideNow 는 서버 side_now 와 **같은 셈**이다(검사 test_oldlayout 이 node 로 맞대 본다). */
import { h, once, blockHead } from './common.js';

const RANK_W = 878, FLAG_W = 108;
const RANK_DEFAULT = [1038, 167, 1];     // layers.js ranking(오른쪽 끝 · 위 · 배율)

const n = (v, d) => { const f = Number(v); return (v === null || v === undefined || v === '' || !isFinite(f)) ? d : f; };

/** layout.widgets → 'left' · 'right' · 'free'(따로 놓임 · 기본 자리) */
export function sideNow(lay) {
    lay = (lay && typeof lay === 'object') ? lay : {};
    const r = (lay.ranking && typeof lay.ranking === 'object') ? lay.ranking : {};
    let rs = ('scale' in r) ? n(r.scale, RANK_DEFAULT[2]) : RANK_DEFAULT[2];
    if (!(rs > 0)) rs = 1;
    const rx = (('x' in r) ? n(r.x, RANK_DEFAULT[0]) : RANK_DEFAULT[0]) - RANK_W * rs;
    const ry = ('y' in r) ? n(r.y, RANK_DEFAULT[1]) : RANK_DEFAULT[1];
    const f = (lay.fundjar && typeof lay.fundjar === 'object') ? lay.fundjar : null;
    if (!f || !('x' in f)) return 'free';
    const fx = n(f.x, 0), fy = n(f.y, 0), fs = n(f.scale, 1) || 1;
    if (Math.abs(fy - ry) > 40) return 'free';
    const gl = rx - (fx + FLAG_W * fs);
    if (gl >= 0 && gl <= 60) return 'left';
    const gr = fx - (rx + RANK_W * rs);
    if (gr >= 0 && gr <= 60) return 'right';
    return 'free';
}

/** opts.compact — 점수판 모금함 줄(#jar-side-slot, 10-17 w2center)에 [◀ 왼쪽][오른쪽 ▶] 두 단추만(같은 명령 · 같은 확인 상자) */
export function mountFjSide(ctx, opts) {
    const compact = !!(opts && opts.compact);
    let side = 'free';
    const bc = compact ? 'btn xs' : 'btn sm';
    const left = h('button', { type: 'button', class: bc, 'aria-pressed': 'false', onclick: () => once(left, () => go('left')) }, '◀ 왼쪽');
    const right = h('button', { type: 'button', class: bc, 'aria-pressed': 'false', onclick: () => once(right, () => go('right')) }, '오른쪽 ▶');
    const now = h('span', { class: 'ops-dim' });
    const el = compact
        ? h('span', { class: 'fj-seg', role: 'group', 'aria-label': '방송판 깃발 자리' }, left, right)
        : h('section', { class: 'ops-blk fj-side' },
            blockHead('방송판 깃발 자리', '점수판 왼쪽 · 오른쪽에 한 줄로 붙여요 — 왼쪽이면 점수판이 깃발 폭만큼 비켜요'),
            h('div', { class: 'ops-row wrap' }, left, right, now));

    async function go(want) {
        if (side === 'free') {
            const ok = await ctx.confirm({ title: '🏺 깃발 ' + (want === 'left' ? '왼쪽' : '오른쪽') + '으로',
                body: '편집기에서 손으로 옮겨 둔 점수판 · 깃발 자리가 바뀝니다.\n방송 화면에서 바로 움직여요.', ok: '옮기기', cancel: '그만두기', danger: false });
            if (!ok) return;
        }
        const res = await ctx.run('fundjar.side', { side: want });
        if (res.ok) ctx.toast('🏺 깃발을 점수판 ' + (want === 'left' ? '왼쪽' : '오른쪽') + '에 세웠어요', 'ok');
    }

    function render(slices) {
        side = sideNow(((slices || {}).layout || {}).widgets);
        [[left, 'left'], [right, 'right']].forEach(([b, k]) => {
            b.classList.toggle('pri', side === k);
            b.setAttribute('aria-pressed', String(side === k));
        });
        now.textContent = side === 'free' ? '지금: 따로 놓임(편집기 자리 · 기본 자리)' : '지금: 점수판 ' + (side === 'left' ? '왼쪽' : '오른쪽');
        if (compact) el.title = '방송판 깃발 자리 — ' + now.textContent;
    }
    return { el, render };
}
