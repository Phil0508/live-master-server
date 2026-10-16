/* 💬 화면에 한마디 · ⬆ UP 자막 — 오른쪽 칸 맨 위 얇은 두 줄(시안 B 10-17: #say-slot). 서버는 cast.py(cast 조각).
   💬 한마디: 쓰고 Enter → cast.say {text} → 방송판 한가운데 1초(궁서 · 흰 글씨 · 검은 테두리). 옛 controller.html #rail-say(10-07).
   ⬆ UP 자막: 쓰고 Enter 또는 [발사] → cast.up {text} → 방송판 가운데 금색 큰 글씨 2초(방송 중일 때만 보인다).
              옛 조종실 랭킹 탭 '#in-up-text' · 폰 '📢 전광판' 을 이 한 곳으로 모았다.
   ⚠️ 한글 조합 중 Enter(isComposing · 229)는 건너뛴다 — 마지막 글자가 두 번 · 덜 들어간다.
   ⚠️ 보내자마자 칸을 비운다(연달아 쓰기 쉽게). 실패하면 쓴 글을 칸에 되돌린다(옛 saySend 그대로).
   폰(900px 아래)에서는 대기함 · 점수판 · 되돌리기 다음에 온다(controller.css 의 order — css/tools_cast.css). */
import { h } from './util.js';

const SAY_MAX = 60, UP_MAX = 60;       // 서버 cast.SAY_MAX · UP_MAX

export function mountCastBox(ctx) {
    const rail = document.getElementById('say-slot');
    if (!rail) return null;
    const sayIn = h('input', { type: 'text', maxlength: String(SAY_MAX), placeholder: '화면에 한마디 — 쓰고 Enter', autocomplete: 'off',
        enterkeyhint: 'send', 'aria-label': '방송 화면에 잠깐 띄울 글' });
    const upIn = h('input', { type: 'text', maxlength: String(UP_MAX), placeholder: 'UP 자막 — Enter 발사', autocomplete: 'off',
        enterkeyhint: 'send', 'aria-label': 'UP 자막(방송판 가운데 금색 큰 글씨 2초)' });
    const upBtn = h('button', { type: 'button', class: 'btn sm cb-fire', title: '방송판 가운데 금색 큰 글씨로 2초(방송 중일 때)' }, '발사');
    const log = h('div', { class: 'cb-log', 'aria-live': 'polite' });
    const box = h('section', { class: 'sec cast-sec', id: 'castbox', 'aria-label': '화면에 한마디 · UP 자막' },
        h('div', { class: 'cb-row' }, h('span', { class: 'cb-ico', 'aria-hidden': 'true' }, '💬'), sayIn),
        h('div', { class: 'cb-row' }, h('span', { class: 'cb-ico', 'aria-hidden': 'true' }, '⬆'), upIn, upBtn),
        log);
    rail.append(box);

    async function send(input, type, okText) {
        const text = (input.value || '').trim();
        if (!text) { if (type === 'cast.up') ctx.toast('화면에 띄울 문구를 먼저 입력해 주세요', 'err'); return; }
        input.value = '';
        const res = await ctx.run(type, { text }, { quiet: true });
        if (res.ok) {
            log.classList.remove('err');
            const row = res[type === 'cast.say' ? 'say' : 'up'] || {};
            log.textContent = '✓ ' + okText + ' · ' + (row.text || text);
        } else {
            log.classList.add('err');
            log.textContent = '⚠ ' + (res.error || '못 띄웠어요') + ' — 다시 Enter';
            if (!input.value) input.value = text;
        }
    }
    const onEnter = (input, fn) => input.addEventListener('keydown', e => {
        if (e.key !== 'Enter' || e.isComposing || e.keyCode === 229) return;
        e.preventDefault();
        fn();
    });
    onEnter(sayIn, () => send(sayIn, 'cast.say', '띄웠어요'));
    onEnter(upIn, () => send(upIn, 'cast.up', 'UP 자막을 쐈어요'));
    upBtn.addEventListener('click', () => send(upIn, 'cast.up', 'UP 자막을 쐈어요'));
    return { el: box };
}
