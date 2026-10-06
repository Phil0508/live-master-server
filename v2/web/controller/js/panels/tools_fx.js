/* 💡 조명 탭 — 옛 조종실 '조명' 탭(controller.html #tab-neon: 끄기 · 무지개 · 아우디 라이트 · 속도 막대 · 단색 슬롯 9칸)을 옮겼다.
   서버 약속: v2/server/domain/lights.py
     단추 하나 → lights.color {color}   '#hex' · 'RAINBOW' → 그 네온 / 'AUDI' → 아우디 뒤집기 / 'OFF' → 네온 · 아우디 둘 다 끔
     무지개 끄기 → lights.set {color:'OFF'}(네온만 — 옛 단추는 '무지개 끄기' 라고 써 놓고 다시 무지개를 보냈다)
     속도 막대 → lights.set {speed}(0.3~5.0초, 손을 뗄 때 한 번) · 칸 색 고르기 → lights.slot {index, color}
   ⚠️ 방송판에는 **시그니처가 나오는 동안만** 켜진다(방송 중일 때). 옛 단추는 누르면 '리액션 모드' 까지 켜서 시그니처 없이도
      테두리가 켜지고 점수판이 가려졌다 — v2 에는 그 수동 모드가 없다.
   탭 하나 = { id, label, icon, group, mount(el, ctx) → { render(slices) } } — panels/tools.js 가 시그니처 탭 옆에 붙인다. */
import { h, sigOf, once, blockHead, fill } from './ops/common.js';

const DEFAULT_COLORS = ['#ff0055', '#00e5ff', '#ff9100', '#d500f9', '#00ff00', '#ffff00', '#ff0000', '#0000ff', '#ffffff'];
// 금액 등급 → 움직임(방송판 widgets/fx/kit.js neonTierClass 와 같은 기준) — 대표님이 '어떤 연출이 나갈지' 보는 표
const TIERS = [['10만 미만', '흐름 — 한 줄기가 한 바퀴'], ['10만', '듀얼 스윕 — 위에서 갈라져 아래에서 만남'], ['20만', '반짝임'],
    ['30만', '점멸 — 노래 박자에 맞춰'], ['50만', '파동 — 물결 다섯'], ['100만', '맥동 — 가장자리가 숨 쉬듯'], ['200만', '차징 → 폭발']];
const isHex = c => /^#[0-9a-f]{6}$/i.test(String(c || ''));

function mountFx(el, ctx) {
    const now = h('p', { class: 'ops-now fx-now' });
    const offBtn = h('button', { type: 'button', class: 'btn danger fx-big', onclick: () => once(offBtn, () => send('OFF')) }, '⛔ 끄기');
    const rbBtn = h('button', { type: 'button', class: 'btn fx-big fx-rainbow', 'aria-pressed': 'false', onclick: () => once(rbBtn, rainbow) });
    const audiBtn = h('button', { type: 'button', class: 'btn fx-big fx-audi', 'aria-pressed': 'false', onclick: () => once(audiBtn, () => send('AUDI')) });
    const spd = h('input', { type: 'range', min: '0.3', max: '5.0', step: '0.1', value: '1.5', class: 'fx-speed', 'aria-label': '조명 속도(초)' });
    const spdLbl = h('b', { class: 'fx-speed-lbl' }, '1.5초');
    spd.addEventListener('input', () => { spdLbl.textContent = Number(spd.value).toFixed(1) + '초'; });
    spd.addEventListener('change', async () => {
        const v = Number(spd.value);
        const res = await ctx.run('lights.set', { speed: v });
        if (res.ok) ctx.toast('💡 조명 속도 ' + v.toFixed(1) + '초', 'ok');
        else { last = ''; ctx.rerender(); }
    });
    const grid = h('div', { class: 'fx-slots' });
    const slots = DEFAULT_COLORS.map((c, i) => {
        const pick = h('input', { type: 'color', value: c, 'aria-label': (i + 1) + '번 색 고르기' });
        const btn = h('button', { type: 'button', class: 'fx-slot-btn', onclick: () => once(btn, () => send(pick.value)) }, '켜기');
        pick.addEventListener('change', async () => {
            const res = await ctx.run('lights.slot', { index: i, color: pick.value });
            if (res.ok) ctx.toast(`🎨 ${i + 1}번 칸을 ${pick.value} 로 바꿨어요 — [켜기] 를 누르면 방송판에 나가요`, 'ok');
            else { last = ''; ctx.rerender(); }
        });
        const cell = h('div', { class: 'fx-slot' }, pick, btn);
        grid.append(cell);
        return { pick, btn, cell };
    });
    const tierList = h('ul', { class: 'fx-tiers' }, TIERS.map(([a, t]) => h('li', null, h('b', null, a), h('span', null, t))));

    el.classList.add('ops', 'ops-fx');
    el.append(
        now,
        h('section', { class: 'ops-blk' }, blockHead('켜고 끄기', '시그니처가 나오는 동안만 방송판에 켜져요'),
            h('div', { class: 'fx-main' }, offBtn, rbBtn, audiBtn)),
        h('section', { class: 'ops-blk' }, blockHead('속도', '네온이 한 바퀴 도는 빠르기 · 아우디 LED 빠르기 — 작을수록 빨라요'),
            h('div', { class: 'ops-row fx-speed-row' }, h('span', null, '빠르게'), spd, h('span', null, '느리게'), spdLbl)),
        h('section', { class: 'ops-blk' }, blockHead('단색 9칸', '칸 색을 골라 두고 [켜기] — 시그니처 사진이 있으면 그 사진 색이 먼저예요'), grid),
        h('section', { class: 'ops-blk' }, blockHead('금액마다 움직임', '색이 아니라 움직임이 금액에 따라 저절로 바뀌어요'), tierList),
    );

    async function send(color) {
        const res = await ctx.run('lights.color', { color });
        if (!res.ok) return;
        const L = res.lights || {};
        if (color === 'OFF') ctx.toast('💡 조명을 껐어요 (네온 · 아우디)', 'info');
        else if (color === 'AUDI') ctx.toast(L.audi ? '🚗 아우디 라이트 켰어요' : '🚗 아우디 라이트 껐어요', L.audi ? 'ok' : 'info');
        else if (color === 'RAINBOW') ctx.toast('🌈 무지개 조명 — 시그니처가 나올 때 켜져요', 'ok');
        else ctx.toast('🎨 조명 ' + color + ' — 시그니처가 나올 때 켜져요', 'ok');
    }

    async function rainbow() {
        const L = ctx.slices.lights || {};
        if (L.color !== 'RAINBOW') return send('RAINBOW');
        const res = await ctx.run('lights.set', { color: 'OFF' });      // 무지개만 끈다(아우디는 그대로)
        if (res.ok) ctx.toast('🌈 무지개를 껐어요', 'info');
    }

    let last = '';
    function render(slices) {
        const L = slices.lights || { color: 'OFF', audi: false, speed: 1.5, colors: DEFAULT_COLORS };
        const sig = sigOf(L.color, L.audi, L.speed, L.colors, !!(slices.session || {}).live);
        if (sig === last) return;
        last = sig;
        const c = String(L.color || 'OFF');
        const neon = c === 'OFF' ? '꺼짐' : (c === 'RAINBOW' ? '🌈 무지개' : null);
        fill(now, '지금 조명 — 네온 ',
            neon ? h('b', null, neon) : h('b', null, h('i', { class: 'fx-dot', style: 'background:' + (isHex(c) ? c : '#888') }), ' ' + c),
            ' · 아우디 ', h('b', null, L.audi ? '켜짐' : '꺼짐'),
            h('span', { class: 'ops-dim' }, (slices.session || {}).live ? ' — 시그니처가 나올 때 켜져요' : ' — 방송 중 · 시그니처가 나올 때 켜져요'));
        now.classList.toggle('off', c === 'OFF' && !L.audi);
        const rb = c === 'RAINBOW';
        rbBtn.textContent = rb ? '🌈 무지개 끄기' : '🌈 무지개 (ON)!';
        rbBtn.classList.toggle('on', rb);
        rbBtn.setAttribute('aria-pressed', String(rb));
        audiBtn.textContent = L.audi ? '🚗 아우디 라이트 켜짐 · 끄기' : '🚗 아우디 라이트';
        audiBtn.classList.toggle('on', !!L.audi);
        audiBtn.setAttribute('aria-pressed', String(!!L.audi));
        const sp = Number(L.speed) || 1.5;
        if (document.activeElement !== spd) { spd.value = String(sp); spdLbl.textContent = sp.toFixed(1) + '초'; }
        const cols = Array.isArray(L.colors) && L.colors.length ? L.colors : DEFAULT_COLORS;
        slots.forEach((s, i) => {
            const col = isHex(cols[i]) ? cols[i].toLowerCase() : DEFAULT_COLORS[i];
            if (document.activeElement !== s.pick && s.pick.value.toLowerCase() !== col) s.pick.value = col;
            const on = c.toLowerCase() === col;
            s.btn.textContent = on ? '현재 ON' : '켜기';
            s.btn.classList.toggle('on', on);
            s.btn.setAttribute('aria-pressed', String(on));
            // 옛 모습: 켜기 = 그 색 바탕 · 흰 글자 / 현재 ON = 어두운 바탕에 그 색 글자 · 테두리
            s.btn.style.setProperty('--slot', col);
            s.cell.classList.toggle('on', on);
        });
    }
    return { render };
}

export const PANELS = [
    { id: 'fx-lights', label: '조명', icon: '💡', group: 'sigs', mount: mountFx },
];
