/* ☕ 상태 줄 휴식 표시 — 휴식(서버 자동 진행 '켬')일 때만 '☕ 휴식 중'. 누르면 학습 · 휴식 탭을 연다.
   10-22 대표님 정리: 평소(📚 학습)는 따로 표시하지 않는다 — 기계가 점수를 넣는 휴식만 눈에 띄게.
   시안 B(10-17): 다른 상태처럼 테두리 없는 점 + 글자(.st) — 단, 켬은 초록 테두리를 남긴다(controller.css #hdr .au-pill).
   켜져 있는 걸 모르는 상태가 가장 위험하다(옛 🚗 오토파일럿 교훈).
   폰에서도 숨기지 않는다(💰 칸과 다르다). */
import { h, openAutoTab } from './common.js';

export function mountAutoPill(host) {
    const t = h('span', { class: 't' });
    const el = h('button', { type: 'button', class: 'st au-pill', hidden: true, onclick: () => openAutoTab() },
        h('i', { class: 'dot', 'aria-hidden': 'true' }), t);
    if (host) host.append(el);
    let last = '';
    return {
        render(slices, view) {
            const mode = ((slices || {}).autopilot || {}).mode || 'off';
            const want = view === 'live' && mode === 'on' ? mode : '';
            if (want === last) return;
            last = want;
            el.hidden = !want;
            el.dataset.mode = want;
            t.textContent = '☕ 휴식 중';
            el.title = '휴식 중 — 확실한 투네 후원은 기계가 바로 점수를 넣어요. 애매한 것 · 계좌 입금은 초록 알림. 눌러서 학습 · 휴식 탭 열기';
        },
    };
}
