/* 🔔 점수 팝업 — popup 조각의 score {name, diff, at}. '하율 후원 +5' 알약이 2초(옛 것과 같다).
   - 새 at 일 때만 · 점수가 올랐을 때만(diff > 0) · 방송 중일 때만 · 붙은 직후 통째로 받은 것은 30초 안의 것만.
   - 조종실 알림 스위치 [후원 팝업](show.alerts.popup)을 따른다(옛 것도 같은 스위치였다). */
import { formatNum, restartClass } from '../util.js';

const HOLD_MS = 2000;

export function mount(root, lm, opts) {
    root.innerHTML = '<div class="center-popup-content"><span class="popup-text"></span><span class="popup-score"></span></div>';
    const pill = root.firstElementChild;
    const textEl = root.querySelector('.popup-text');
    const scoreEl = root.querySelector('.popup-score');
    let seen, timer = null;

    lm.on('popup', (pop, slices) => {
        const s = pop && pop.score;
        if (!s) return;
        if (s.at === seen) return;
        seen = s.at;
        if (!opts.isFresh(s.at)) return;
        if (!((slices.session || {}).live)) return;
        if (!opts.stage.alertOn('popup')) return;
        if (!(Number(s.diff) > 0)) return;
        textEl.textContent = (s.name || '') + ' 후원 ';
        scoreEl.textContent = '+' + formatNum(s.diff);
        restartClass(pill, 'show');
        clearTimeout(timer);
        timer = setTimeout(() => pill.classList.remove('show'), HOLD_MS);
    });
}
