/* 👑 조종실 후원 연출 — cast.fx {id, kinds, name, amount, message, at} · cast.fx_clear {id, at}.
   옛 overlay.html opFxFire · opFxClear · #op-fx-*(후원 콘솔 '이펙트' 탭, features/effects.py) 를 그대로 옮겼다.
   시그니처 대기줄 · 게이지와 따로 도는 연출이라 시그니처가 나오는 중에 쏴도 서로 끊지 않는다.

   연출(kinds) — 여러 개를 같이 쏠 수 있다. 겹쳐 쏘면 앞의 것을 걷고 새로 시작한다.
     flash   화면 번쩍(0.22초) + 금빛 테두리가 6초 숨 쉰다
     banner  화면 가운데(위 42%) 큰 이름(150px) + 아랫줄 '금액원 · 문구' — 6초. 이름이 없으면 '감사합니다', 0원이면 금액은 안 쓴다
     ticker  맨 위 띠(92px)에 문구가 오른쪽 밖에서 왼쪽 밖으로 12초 동안 한 번 흐른다. 문구가 없으면 'OO님 후원 감사합니다!'
     card    화면 전체를 덮는 인수 카드(DONATION · 이름 · 금액 · 문구) — 3.2초(길면 답답하다)
     shock   가운데서 빛 고리 셋이 퍼진다(1.4초) + 화면 흔들림(0.5초 — 칸이 아니라 캔버스를 흔든다: stage 모드 'opfx-shake')
     glitch  네온 글리치 — 이름(없으면 문구 · DONATION)이 갈라지며 어긋난다(1.7초 — 짧아야 멋있다)
     warn    비상 경보 — 붉은 사선 띠 · ⚠ WARNING ⚠ · 아랫줄(문구 또는 '이름 · 금액원', 없으면 '고액 후원 감지') — 4초
   안의 겹침 순서는 옛 z 차례 그대로 그리는 순서로: 번쩍 < 테두리 < 배너 < 전광판 < 충격파 < 글리치 < 카드 < 경보.
   다른 위젯(예: 시그니처 전용 연출의 계엄령 경보)이 쓸 수 있게 무대에 'opfx' {fire, clear, clearWarn} 를 내놓는다.
   모양은 css/cast.css(옛 #op-fx-* CSS — fixed 대신 칸 안 absolute). */
import { watchCast } from './fresh.js';
import { formatNum } from '../../util.js';

export const MS = { card: 3200, glitch: 1700, warn: 4000, banner: 6000, edge: 6000, ticker: 12000, flash: 220, shock: 1400, shake: 600 };
const W = 1080;

/* ── 글자(옛 opFxFire 와 같은 셈 — 검사가 node 로 부른다) ── */
const won = a => formatNum(a) + '원';
export function texts(d) {
    const name = String((d && d.name) || '').trim();
    const amount = parseInt(d && d.amount, 10) || 0;
    const msg = String((d && d.message) || '').trim();
    const sub = [];
    if (amount > 0) sub.push(won(amount));
    if (msg) sub.push(msg);
    const warn = [];
    if (name) warn.push(name);
    if (amount > 0) warn.push(won(amount));
    return {
        bannerName: name || '감사합니다',
        bannerSub: sub.join('  ·  '),
        cardName: name || '감사합니다',
        cardAmount: amount > 0 ? won(amount) : '',
        cardMsg: msg,
        glitch: name || msg || 'DONATION',
        warnSub: msg || warn.join('  ·  ') || '고액 후원 감지',
        ticker: msg || ((name ? name + '님 ' : '') + '후원 감사합니다!'),
    };
}

function el(tag, cls, kids) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    (kids || []).forEach(k => e.appendChild(k));
    return e;
}

export function mount(root, lm, opts) {
    root.classList.add('cast-fx');
    root.setAttribute('aria-hidden', 'true');
    const flash = el('div', 'opfx-flash');
    const edge = el('div', 'opfx-edge');
    const bName = el('div', 'opfx-banner-name'), bSub = el('div', 'opfx-banner-sub');
    const banner = el('div', 'opfx-banner', [bName, bSub]);
    const tText = el('span', 'opfx-ticker-text');
    const track = el('div', 'opfx-ticker-track', [tText]);
    const ticker = el('div', 'opfx-ticker', [track]);
    const shock = el('div', 'opfx-shock', [el('span'), el('span'), el('span')]);
    const gText = el('div', 'opfx-glitch-text');
    const glitch = el('div', 'opfx-glitch', [gText]);
    const label = el('div', 'op-card-label'); label.textContent = 'DONATION';
    const cName = el('div', 'op-card-name'), cAmt = el('div', 'op-card-amount'), cMsg = el('div', 'op-card-msg');
    const card = el('div', 'opfx-card', [el('div', 'op-card-box', [label, cName, cAmt, cMsg])]);
    const wTitle = el('div', 'op-warn-title'); wTitle.textContent = '⚠ WARNING ⚠';
    const wSub = el('div', 'op-warn-sub');
    const warn = el('div', 'opfx-warn', [el('div', 'op-warn-bar top'), el('div', 'op-warn-body', [wTitle, wSub]), el('div', 'op-warn-bar bottom')]);
    [flash, edge, banner, ticker, shock, glitch, card, warn].forEach(x => root.appendChild(x));   // 그리는 순서 = 겹침 순서

    let timers = [];
    const later = (fn, ms) => timers.push(setTimeout(fn, ms));
    const restart = x => { x.classList.remove('on'); void x.offsetWidth; x.classList.add('on'); };

    function shake() {
        // 캔버스(방송 내용물)를 흔든다 — 칸 바깥은 직접 안 만지고 무대 모드로(옛 #master-container.op-shake)
        opts.stage.setMode('opfx-shake', false);
        requestAnimationFrame(() => opts.stage.setMode('opfx-shake', true));
        later(() => opts.stage.setMode('opfx-shake', false), MS.shake);
    }

    function clear() {
        timers.forEach(t => clearTimeout(t));
        timers = [];
        [flash, edge, banner, ticker, card, shock, glitch, warn].forEach(x => x.classList.remove('on'));
        opts.stage.setMode('opfx-shake', false);
        track.style.transition = 'none';
        track.style.transform = 'translateX(0)';
    }

    function fire(d) {
        const kinds = Array.isArray(d && d.kinds) ? d.kinds : [];
        const t = texts(d);
        clear();                                        // 겹쳐 쏘면 이전 것을 정리하고 새로 시작
        const has = k => kinds.indexOf(k) !== -1;
        if (has('flash')) {
            flash.classList.add('on'); later(() => flash.classList.remove('on'), MS.flash);
            edge.classList.add('on'); later(() => edge.classList.remove('on'), MS.edge);
        }
        if (has('banner')) {
            bName.textContent = t.bannerName;
            bSub.textContent = t.bannerSub;
            bSub.style.display = t.bannerSub ? 'block' : 'none';
            banner.classList.add('on'); later(() => banner.classList.remove('on'), MS.banner);
        }
        if (has('card')) {
            cName.textContent = t.cardName;
            cAmt.textContent = t.cardAmount; cAmt.style.display = t.cardAmount ? 'block' : 'none';
            cMsg.textContent = t.cardMsg; cMsg.style.display = t.cardMsg ? 'block' : 'none';
            card.classList.add('on'); later(() => card.classList.remove('on'), MS.card);
        }
        if (has('shock')) {
            restart(shock); later(() => shock.classList.remove('on'), MS.shock);
            shake();
        }
        if (has('glitch')) {
            gText.textContent = t.glitch;
            gText.setAttribute('data-txt', t.glitch);   // 겹쳐 그리는 두 겹이 같은 글자를 써야 한다
            restart(glitch); later(() => glitch.classList.remove('on'), MS.glitch);
        }
        if (has('warn')) {
            wSub.textContent = t.warnSub;
            warn.classList.add('on'); later(() => warn.classList.remove('on'), MS.warn);
        }
        if (has('ticker')) {
            tText.textContent = t.ticker;
            ticker.classList.add('on');
            // 오른쪽 밖 → 왼쪽 밖으로 한 번 흘려보낸다(다음 그림에서 시작해야 transition 이 먹는다)
            track.style.transition = 'none';
            track.style.transform = 'translateX(' + W + 'px)';
            requestAnimationFrame(() => requestAnimationFrame(() => {
                track.style.transition = 'transform ' + MS.ticker + 'ms linear';
                track.style.transform = 'translateX(' + (-track.offsetWidth) + 'px)';
            }));
            later(() => ticker.classList.remove('on'), MS.ticker);
        }
    }

    opts.stage.provide('opfx', { fire, clear, clearWarn: () => warn.classList.remove('on') });
    watchCast(lm, opts, 'fx', fire);
    watchCast(lm, opts, 'fx_clear', clear);
}
