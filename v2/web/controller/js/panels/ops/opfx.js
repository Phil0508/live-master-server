/* ✨ 이펙트 — 옛 후원 콘솔(manual_send.html) '이펙트' 탭 · 조종실 후원 연출. 서버는 cast.py(cast 조각).
   사장님께 후원한 분을 위한 연출 — 이름 · 금액 · 문구를 적고 쏠 연출을 골라 [연출 쏘기] → cast.fx {kinds, name, amount, message}.
   [걷기] → cast.fx_clear — 잘못 눌렀을 때 바로 걷는다.
   기본으로 골라 둔 것(옛 것과 같다): 큰 배너 · 번쩍 + 테두리 빛 · 전광판 문구. 화려한 것(화면을 크게 덮는다): 카드 · 충격파 · 글리치 · 경보.
   시그니처 재생과 따로 도는 연출이라 시그니처가 나오는 중에 쏴도 서로 끊기지 않는다. 장부 · 점수는 안 바뀐다. */
import { h, once, blockHead, parseWon, onEnter, num } from './common.js';

const BASIC = [['banner', '화면 가운데 ', '큰 배너', true], ['flash', '화면 ', '번쩍 + 테두리 빛', true], ['ticker', '', '전광판에 흐르는 문구', true]];
const FANCY = [['card', '🃏 ', '화면 전체 인수 카드', false], ['shock', '💥 ', '충격파 + 화면 흔들림', false],
    ['glitch', '⚡ ', '네온 글리치', false], ['warn', '🚨 ', '비상 경보 (붉은색)', false]];
const NAMES = { banner: '배너', flash: '번쩍', ticker: '전광판', card: '전체화면 카드', shock: '충격파', glitch: '글리치', warn: '비상경보' };

export function mountOpFx(el, ctx) {
    const nameIn = h('input', { type: 'text', maxlength: '40', autocomplete: 'off', placeholder: '예) 홍길동', 'aria-label': '후원자 이름' });
    const amtIn = h('input', { type: 'text', inputmode: 'numeric', autocomplete: 'off', placeholder: '30,000', 'aria-label': '금액(원, 선택)' });
    const msgIn = h('input', { type: 'text', maxlength: '120', autocomplete: 'off', placeholder: "비우면 '○○님 후원 감사합니다!'", 'aria-label': '문구(선택)' });
    const boxes = {};
    const chk = ([k, pre, b, on]) => {
        const c = h('input', { type: 'checkbox' });
        c.checked = on;
        boxes[k] = c;
        return h('label', { class: 'fx-chk' }, c, h('span', null, pre, h('b', null, b)));
    };
    const fire = h('button', { type: 'button', class: 'btn pri big fx-fire' }, '✨ 연출 쏘기');
    const clear = h('button', { type: 'button', class: 'btn danger fx-clear' }, '걷기');
    const out = h('p', { class: 'ops-hint fx-out', 'aria-live': 'polite' });

    el.classList.add('ops', 'ops-opfx');
    el.append(h('section', { class: 'ops-blk' },
        blockHead('👑 조종실 후원 연출', '사장님께 후원해 주신 분을 위한 연출 — 적고 [연출 쏘기] 를 누르면 방송 화면에 나가요'),
        h('p', { class: 'ops-note gold' }, '시그니처 재생과 따로 도는 연출이라, 시그니처가 나오는 중에 쏴도 서로 끊기지 않아요. 장부 · 점수는 안 바뀌어요.'),
        h('label', { class: 'ops-field' }, h('span', null, '후원자 이름'), nameIn),
        h('label', { class: 'ops-field' }, h('span', null, '금액 (원, 선택 — 비우면 안 나와요)'), amtIn),
        h('label', { class: 'ops-field' }, h('span', null, '문구 (선택 — 전광판에 흘러요)'), msgIn),
        h('div', { class: 'ops-sub fx-sub' }, '쏠 연출 고르기'),
        h('div', { class: 'fx-chks' }, BASIC.map(chk)),
        h('div', { class: 'ops-sub fx-sub' }, '화려한 연출 (화면을 크게 덮어요)'),
        h('div', { class: 'fx-chks' }, FANCY.map(chk)),
        h('div', { class: 'ops-row fx-btns' }, fire, clear),
        out));

    amtIn.addEventListener('blur', () => { const v = parseWon(amtIn.value); if (v != null && v > 0) amtIn.value = num(v); });

    async function shoot() {
        const kinds = [...BASIC, ...FANCY].map(x => x[0]).filter(k => boxes[k].checked);
        if (!kinds.length) { out.className = 'ops-hint fx-out bad'; out.textContent = '연출을 하나 이상 골라 주세요.'; return; }
        const raw = amtIn.value.trim();
        const amount = raw ? parseWon(raw) : 0;
        if (amount == null) { out.className = 'ops-hint fx-out bad'; out.textContent = '금액은 원 단위 숫자로 적어 주세요(비워도 돼요).'; amtIn.focus(); return; }
        const res = await ctx.run('cast.fx', { kinds, name: nameIn.value.trim(), amount, message: msgIn.value.trim() });
        if (res.ok) {
            out.className = 'ops-hint fx-out good';
            out.textContent = '✨ 연출을 쐈어요 — ' + kinds.map(k => NAMES[k] || k).join(', ');
        } else {
            out.className = 'ops-hint fx-out bad';
            out.textContent = res.error || '쏘지 못했어요';
        }
    }
    async function wipe() {
        const res = await ctx.run('cast.fx_clear', {});
        out.className = 'ops-hint fx-out' + (res.ok ? '' : ' bad');
        out.textContent = res.ok ? '연출을 걷었어요.' : (res.error || '걷지 못했어요');
    }
    fire.addEventListener('click', () => once(fire, shoot));
    clear.addEventListener('click', () => once(clear, wipe));
    [nameIn, amtIn, msgIn].forEach(i => onEnter(i, () => once(fire, shoot)));

    return { render() {} };     // 서버 조각은 안 본다 — 쏘기만 한다
}
