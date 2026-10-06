/* 💡 아우디 LED — 화면 아래 양쪽 끝 LED 8개씩이 차례로 하얗게 켜지며 빛기둥이 솟는다(옛 overlay.html #audi-overlay 그대로).
   켜지는 때: 방송 중 · 시그니처가 나오는 동안 · 조종실 [아우디 라이트] 가 켜져 있을 때(lights.audi).
   속도: --audi-speed = 조명 속도 × 0.56초(옛 계산 그대로 — 기본 1.5초 → 0.84초).
   켜기: hide 를 떼고 → 한 번 그린 뒤(reflow) active — 애니메이션이 처음부터 돈다. 끄기: active 를 떼고 hide(0.4초에 걸쳐 사라짐). */
import { lightsOf, speedOf, reactionLive, watch } from './kit.js';

export function mount(root, lm, opts) {
    let html = '<div class="audi-layer">';
    ['left', 'right'].forEach(side => {
        html += '<div class="audi-container ' + side + '">';
        for (let i = 0; i < 8; i++) html += '<div class="audi-led" style="--idx: ' + i + '"></div>';
        html += '</div>';
    });
    root.innerHTML = html + '</div>';
    const el = root.firstElementChild;

    function render() {
        const L = lightsOf(lm);
        el.style.setProperty('--audi-speed', (speedOf(L) * 0.56) + 's');
        const show = !!L.audi && reactionLive(lm, opts.stage);
        if (show) {
            if (!el.classList.contains('active')) {
                el.classList.remove('hide');
                void el.offsetWidth;
                el.classList.add('active');
            }
        } else if (el.classList.contains('active')) {
            el.classList.remove('active');
            el.classList.add('hide');
        }
    }
    watch(lm, opts.stage, render);
}
