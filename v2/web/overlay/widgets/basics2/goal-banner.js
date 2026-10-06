/* 🎯 목표 100% 달성 축하 — popup 조각의 goal {at, target}. 조종실 [목표 달성 연출]을 눌러야 나간다(옛 goal_celebration).
   - 안전지대 한가운데(540,470)에 금색 알약 '🎉 목표 달성!' 이 튀어나왔다가 2.6초 뒤 들어간다(옛 triggerGoalCelebrationEffect). 소리 'goal'.
   - 새 at 일 때만 · 붙은 직후 통째로 받은 것은 30초 안의 것만(다시 붙었을 때 지난 축하가 또 뜨지 않게).
   - 옛 #ui-layer 안에 있었다 — 시그니처가 도는 동안 · 시작/끝 화면 동안은 가려진다.
   ⚠️ 옛 것은 같은 순간 게이지 막대도 세 번 번쩍였다(goal-flash) — 막대는 gauge 위젯의 것이라 여기서는 안 만진다. */
import { restartClass } from '../../util.js';
import { sfxInit, playSfx } from './sfx.js';

const HOLD_MS = 2600;

export function mount(root, lm, opts) {
    sfxInit(opts);
    root.innerHTML = '<div class="goal-banner">🎉 목표 달성!</div>';
    const el = root.firstElementChild;
    let seen, timer = null;

    lm.on('popup', pop => {
        const g = pop && pop.goal;
        if (!g || !g.at) return;
        if (g.at === seen) return;
        seen = g.at;
        if (!opts.isFresh(g.at)) return;
        playSfx('goal');
        restartClass(el, 'show');
        clearTimeout(timer);
        timer = setTimeout(() => el.classList.remove('show'), HOLD_MS);
    });
}
