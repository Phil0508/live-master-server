/* 🧩 퀴즈판 — quiz 조각 {tiles[{c, s}], revealed}. 네모칸만(대표님 10-06 "그냥 네모칸만" — 바탕 · 제목 · 남은 초 · 정답자 없음).
   옛 qzUpdate 를 옮겼다.
   - 무대(show.stage)가 'quiz' 이고 칸이 있을 때만 보인다. 시그니처가 도는 동안(hideInReaction) · 시작/끝 화면 동안은 숨는다.
   - 칸 상태 s: q 초성 · g 처음부터 보여 준 글자 · b 빈칸 · h 힌트로 연 글자 · o 정답 공개.
     정답 글자는 열린 칸(g · h · o)에만 실려 온다 — 서버가 방송판으로 정답을 안 보낸다(quiz_ops 는 비공개 조각).
   - 바뀐 칸만 뒤집는다(pop). 같은 문제에서 칸이 열린 것이면 그 칸만, 새 문제(칸 수가 다름)면 통째로.
   - 칸 크기: 120 칸 여덟 개(+ 사이 14)가 폭 1080 에 딱 맞는다. 아홉 칸부터는 줄인다(--qz-s, 최소 48). */
import { screenCovered } from './slot-roulette-kit.js';

const STATES = ['q', 'g', 'b', 'h', 'o'];

export function mount(root, lm) {
    root.innerHTML = '<div class="qz-box" aria-hidden="true"></div>';
    const box = root.firstElementChild;
    let sig = '';

    function visible() {
        const q = lm.get('quiz') || {};
        const tiles = Array.isArray(q.tiles) ? q.tiles : [];
        const st = (lm.get('show') || {}).stage;
        box.classList.toggle('on', st === 'quiz' && tiles.length > 0 && !screenCovered(lm));
    }

    function render(q) {
        q = q || {};
        const tiles = Array.isArray(q.tiles) ? q.tiles : [];
        visible();
        const now = JSON.stringify(tiles);
        if (now === sig) return;
        let prev = [];
        try { prev = sig ? JSON.parse(sig) : []; } catch (e) { prev = []; }
        sig = now;
        const same = prev.length === tiles.length;
        const n = tiles.length;
        box.style.setProperty('--qz-s', Math.max(48, Math.min(120, Math.floor((1064 - 14 * Math.max(0, n - 1)) / Math.max(1, n)))) + 'px');
        box.textContent = '';
        tiles.forEach((t, i) => {
            const el = document.createElement('div');
            const st = STATES.includes(t && t.s) ? t.s : 'b';
            el.className = 'qz-tile s-' + st;
            el.textContent = st === 'b' ? '' : String((t && t.c) || '').slice(0, 1);
            if (!same || !prev[i] || prev[i].s !== st || prev[i].c !== (t && t.c)) el.classList.add('pop');
            box.appendChild(el);
        });
    }

    lm.on('quiz', render);
    lm.on('show', visible);
    lm.on('screen', visible);
}
