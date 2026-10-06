/* 🏺 모금함 — 회사 종잣돈(seed) + 후원분(score). 금액은 전부 **원**이다(점수 아님).
   켜기 → fundjar.set {enabled} + show.hud {fundjar}(옛 조종실은 스위치 하나였다 — setJar 가 둘을 같이 맞춘다)
   이름 · 종잣돈 → fundjar.set {name, seed}
   후원 얹기/빼기 → fundjar.add {delta(원), reason} — 점수 기록에 남아 [되돌리기] 로 되돌릴 수 있다
   후원분 비우기 → 확인 상자 → fundjar.reset (종잣돈은 그대로)
   대기함 카드의 [🏺 모금함] 은 켜져 있을 때만 보인다(pending.js → pending.to_jar). */
import { h, won, sigOf, onEnter, setVal, once, switchEl, parseWon, setJar, blockHead } from './common.js';

export function mountFundjar(el, ctx) {
    const sw = switchEl('모금함 쓰기', async on => {
        const res = await setJar(ctx, on);
        if (res.ok) ctx.toast(on ? '🏺 모금함을 켰어요 — 방송판 깃발 · 대기함 [모금함] 단추' : '🏺 모금함을 껐어요', on ? 'ok' : 'info');
        else sw.input.checked = !on;
    }, '켜면 방송판에 모금함 깃발이 뜨고, 대기함 카드에 [🏺 모금함] 단추가 생겨요');
    const hudWarn = h('p', { class: 'ops-note warn', hidden: true });
    const total = h('b', { class: 'fj-total' }, '₩0');
    const parts = h('span', { class: 'ops-dim' });
    const nameIn = h('input', { type: 'text', maxlength: '20', placeholder: '모금함', autocomplete: 'off', 'aria-label': '모금함 이름' });
    const seedIn = h('input', { type: 'text', inputmode: 'numeric', autocomplete: 'off', placeholder: '200000', 'aria-label': '종잣돈(원)' });
    const saveBtn = h('button', { type: 'button', class: 'btn sm', onclick: () => once(saveBtn, save) }, '이름 · 종잣돈 저장');
    const addIn = h('input', { type: 'text', inputmode: 'numeric', autocomplete: 'off', placeholder: '+ 금액 (빼려면 -3000)', 'aria-label': '얹을 금액(원)' });
    const reasonIn = h('input', { type: 'text', maxlength: '40', autocomplete: 'off', placeholder: '까닭 (선택) — 예) 계좌 후원 김OO', class: 'grow', 'aria-label': '까닭' });
    const addBtn = h('button', { type: 'button', class: 'btn pri sm fj-add', onclick: () => once(addBtn, add) }, '더하기');
    const resetBtn = h('button', { type: 'button', class: 'btn sm ghost-danger', onclick: () => once(resetBtn, reset) }, '후원분 비우기');
    let dirty = false;
    [nameIn, seedIn].forEach(i => {
        i.addEventListener('input', () => { dirty = true; saveBtn.classList.add('pri'); });
        onEnter(i, () => once(saveBtn, save));
    });
    onEnter(addIn, () => once(addBtn, add));
    onEnter(reasonIn, () => once(addBtn, add));

    el.classList.add('ops', 'ops-fundjar');
    el.append(
        h('div', { class: 'ops-toprow' }, sw.el),
        hudWarn,
        h('div', { class: 'fj-big' }, h('span', { class: 'ops-lbl' }, '방송판 금액'), total, parts),
        h('section', { class: 'ops-blk' }, blockHead('이름 · 종잣돈', '종잣돈(회사 상금)은 방송을 껐다 켜도 남아요'),
            h('div', { class: 'ops-grid2' }, h('label', { class: 'ops-field' }, h('span', null, '이름'), nameIn),
                h('label', { class: 'ops-field' }, h('span', null, '종잣돈 (원)'), seedIn)),
            h('div', { class: 'ops-row end' }, saveBtn)),
        h('section', { class: 'ops-blk' }, blockHead('후원 얹기', '계좌로 받은 것 등 — 원 단위. [되돌리기] 로 되돌릴 수 있어요'),
            h('div', { class: 'ops-row wrap' }, addIn, reasonIn, addBtn)),
        h('section', { class: 'ops-blk' }, blockHead('비우기', '후원분만 0 으로 — 종잣돈은 그대로 남아요'), h('div', { class: 'ops-row' }, resetBtn)),
    );

    async function save() {
        const seed = parseWon(seedIn.value);
        if (seed == null) { ctx.toast('종잣돈은 0 이상의 숫자(원)로 적어 주세요', 'err'); seedIn.focus(); return; }
        const res = await ctx.run('fundjar.set', { name: nameIn.value.trim() || '모금함', seed });
        if (res.ok) { dirty = false; saveBtn.classList.remove('pri'); last = ''; ctx.toast('🏺 저장했어요', 'ok'); ctx.rerender(); }
    }

    async function add() {
        const d = parseWon(addIn.value, true);
        if (!d) { ctx.toast('얹을 금액을 원 단위 숫자로 적어 주세요 (빼려면 -3000)', 'err'); addIn.focus(); return; }
        const res = await ctx.run('fundjar.add', { delta: d, reason: reasonIn.value.trim() || '조종실에서' });
        if (res.ok) {
            ctx.toast(`🏺 ${d > 0 ? '+' : '−'}${won(Math.abs(d))} → 모금함`, 'ok');
            addIn.value = '';
            reasonIn.value = '';
        }
    }

    async function reset() {
        const j = ctx.slices.fundjar || {};
        const ok = await ctx.confirm({ title: '모금함 후원분을 비울까요?',
            body: `후원분 ${won(j.score || 0)} 을 0 으로 되돌립니다.\n종잣돈 ${won(j.seed || 0)} 은 그대로 남아요.`, ok: '비우기', cancel: '그대로 두기' });
        if (!ok) return;
        const res = await ctx.run('fundjar.reset', {});
        if (res.ok) ctx.toast('🏺 모금함 후원분을 비웠어요 (종잣돈은 그대로)', 'info');
    }

    let last = '';
    function render(slices) {
        const j = slices.fundjar || {};
        const hudOn = !!((slices.show || {}).hud || {}).fundjar;
        sw.set(!!j.enabled);
        const sig = sigOf(j, hudOn);
        if (sig === last) return;
        last = sig;
        total.textContent = won((Number(j.seed) || 0) + (Number(j.score) || 0));
        parts.textContent = `종잣돈 ${won(j.seed || 0)} + 후원 ${won(j.score || 0)}`;
        if (!dirty) { setVal(nameIn, j.name || '모금함'); setVal(seedIn, String(Number(j.seed) || 0)); }
        // 옛 것은 스위치 하나였다 — 둘이 어긋나 있으면 알려 준다(다른 화면 · 무대 탭에서 하나만 바꾼 경우)
        hudWarn.hidden = !!j.enabled === hudOn;
        hudWarn.textContent = j.enabled ? '모금함은 켜져 있는데 방송판 고정 자리(모금함)가 꺼져 있어요 — 무대 탭에서 켜거나 스위치를 껐다 켜 주세요'
                                        : '모금함은 꺼져 있는데 방송판 고정 자리(모금함)가 켜져 있어요';
        resetBtn.disabled = !(Number(j.score) || 0);
    }
    return { render };
}
