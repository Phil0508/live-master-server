/* ⬆ UP 자막 — cast.up {id, text, at}. 옛 overlay.html #up-message-layer(.up-message) · gd.up_trigger 그대로.
   조종실에 적고 [발사] → 방송판 가운데(위 40%)에 금색 큰 글씨(110px · 테마 네온 빛 · 검은 그림자)가 튀어 올라 2초 뒤 사라진다.
   연달아 쏘면 처음부터 다시 튄다. 방송 중일 때만(칸이 liveOnly — 옛 것도 '방송 꺼짐 return' 뒤에서 그렸다). 모양은 css/cast.css. */
import { watchCast } from './fresh.js';

export const UP_SHOW_MS = 2000;

export function mount(root, lm, opts) {
    root.classList.add('cast-up');
    const el = document.createElement('div');
    el.className = 'up-message';
    root.appendChild(el);
    let timer = null;

    watchCast(lm, opts, 'up', row => {
        el.textContent = String(row.text || '');
        el.style.transition = 'none';
        el.classList.remove('show');
        void el.offsetWidth;
        el.style.transition = '';
        el.classList.add('show');
        clearTimeout(timer);
        timer = setTimeout(() => el.classList.remove('show'), UP_SHOW_MS);
    });
}
