/* 👑 1등 탈환 — popup 조각의 takeover {name, at}. 'OO 1등 탈환! 👑' 금테 알약이 2.5초(옛 것과 같다).
   - 새 at 일 때만 · 방송 중일 때만 · 붙은 직후 통째로 받은 것은 30초 안의 것만 · 스위치 [1등 탈환](show.alerts.takeover).
   - 시그니처가 도는 동안은 칸이 가려진다(layers.js hideInReaction — 옛 #ui-layer 안에 있었다). */
import { restartClass } from '../util.js';

const HOLD_MS = 2500;

export function mount(root, lm, opts) {
    root.innerHTML = '<div class="takeover-popup-content"><span class="takeover-text"></span></div>';
    const pill = root.firstElementChild;
    const textEl = root.querySelector('.takeover-text');
    let seen, timer = null;

    lm.on('popup', (pop, slices) => {
        const t = pop && pop.takeover;
        if (!t) return;
        if (t.at === seen) return;
        seen = t.at;
        if (!opts.isFresh(t.at)) return;
        if (!((slices.session || {}).live)) return;
        if (!opts.stage.alertOn('takeover')) return;
        textEl.textContent = (t.name || '') + ' 1등 탈환! 👑';
        restartClass(pill, 'show');
        clearTimeout(timer);
        timer = setTimeout(() => pill.classList.remove('show'), HOLD_MS);
    });
}
