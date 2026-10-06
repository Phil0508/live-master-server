/* 🔥 대결 불꽃 테두리 — 캔버스 가장자리를 붉게 태우는 막(옛 .fire-vignette · body.match-fire-on · match-fever-on).
   - 수동 불꽃: match.fire 이고 무대가 match 일 때.
   - 피버: 대결이 열려 있고(active) 타이머가 돌고 있고 남은 시간이 0 초과 60초 이하일 때(옛 updateMatchTimer).
   - 맨 아래 층(칸 표 z 가 가장 작다) — 판 · 알림을 덮지 않고 가장자리만 물들인다(옛 z 5).
   - 시작 · 끝 화면이면 끈다. 시그니처 중에도 남는다(옛 것도 리액션 가리개 목록에 없었다 — 대결 시계는 서버가 얼린다). */
import { startClock, serverNow, coverOn } from './dice_kit.js';

export function mount(root, lm) {
    startClock();
    root.innerHTML = '<div class="fire-vignette"></div>';
    const v = root.firstElementChild;
    function paint() {
        const m = lm.get('match') || {};
        const stageMatch = (lm.get('show') || {}).stage === 'match';
        const t = m.timer || {};
        const left = t.running ? (Number(t.end_ms) || 0) - serverNow() : 0;
        const fever = !!m.active && !!t.running && left > 0 && Math.ceil(left / 1000) <= 60;
        const on = !coverOn(lm) && ((stageMatch && !!m.fire) || fever);
        v.classList.toggle('on', on);
    }
    lm.on('match', paint);
    lm.on('show', paint);
    lm.on('screen', paint);
    setInterval(paint, 250);
}
