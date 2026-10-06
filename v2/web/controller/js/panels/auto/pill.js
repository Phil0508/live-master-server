/* 🤖 머리줄 자동 진행 표시 — 끔이 아닐 때만 '🤖 그림자' · '🤖 켬'. 누르면 자동 진행 탭을 연다.
   켬은 돈이 걸려 있어 눈에 띄게(초록 테두리 + 점) — 켜져 있는 걸 모르는 상태가 가장 위험하다(옛 🚗 오토파일럿 교훈).
   폰에서도 숨기지 않는다(💰 칸과 다르다). */
import { h, openAutoTab } from './common.js';

export function mountAutoPill(before) {
    const t = h('span', { class: 't' });
    const el = h('button', { type: 'button', class: 'pill au-pill', hidden: true, onclick: () => openAutoTab() },
        h('i', { 'aria-hidden': 'true' }), t);
    if (before && before.parentNode) before.parentNode.insertBefore(el, before);
    let last = '';
    return {
        render(slices, view) {
            const mode = ((slices || {}).autopilot || {}).mode || 'off';
            const want = view === 'live' && mode !== 'off' ? mode : '';
            if (want === last) return;
            last = want;
            el.hidden = !want;
            el.dataset.mode = want;
            t.textContent = want === 'on' ? '🤖 자동 켬' : '👀 그림자';
            el.title = want === 'on'
                ? '자동 진행 켬 — 확실한 후원은 기계가 바로 줘요. 눌러서 자동 진행 탭 열기'
                : "자동 진행 그림자 — 기계는 '했을 일' 만 적어요. 눌러서 자동 진행 탭 열기";
        },
    };
}
