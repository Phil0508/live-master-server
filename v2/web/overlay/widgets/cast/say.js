/* 💬 화면에 한마디 — cast.say {id, text, at}. 옛 overlay.html #say-layer · sayShow(10-07) 그대로.
   조종실 오른쪽 칸 맨 위에 쓰고 Enter → 방송판 한가운데에 궁서체 흰 글씨(검은 테두리 · 배경 없음)가
   0.35초 스윽 나타나 1초 그대로 있다가 0.45초 스윽 사라진다(1.8초). 새 글이 오면 앞 글은 바로 걷고 새 글만.
   긴 글은 글자를 줄여 한두 줄에 들게 한다(10자 120px · 18자 100 · 30자 80 · 그 위 62).
   ⚠️ 애니메이션이 멈춰 있어도(가려진 창) 2.3초 뒤엔 꼭 걷는다. 글씨 모양은 css/cast.css. */
import { watchCast } from './fresh.js';

export const SAY_DONE_MS = 2300;

export function sayFontPx(text) {
    const n = String(text || '').length;
    return n <= 10 ? 120 : n <= 18 ? 100 : n <= 30 ? 80 : 62;
}

export function mount(root, lm, opts) {
    root.classList.add('cast-say');
    root.setAttribute('aria-hidden', 'true');

    function show(row) {
        const text = String((row && row.text) || '').trim();
        if (!text) return;
        root.replaceChildren();
        const el = document.createElement('div');
        el.className = 'say-text';
        el.textContent = text;
        el.style.fontSize = sayFontPx(text) + 'px';
        const done = () => { if (el.parentNode) el.parentNode.removeChild(el); };
        el.addEventListener('animationend', done);
        setTimeout(done, SAY_DONE_MS);
        root.appendChild(el);
    }
    watchCast(lm, opts, 'say', show);
}
