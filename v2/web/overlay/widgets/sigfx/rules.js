/* 🎆 시그니처 전용 연출 · 🚨 계엄령 — 어떤 시그니처에 무엇을 띄우나(화면은 안 만진다 · node 로 검사한다).

   옛 overlay.html 의 SIGFX_BY_AMOUNT · sigFxKey · isMartialLaw · reactionUpText · showReactionTitle 판단 · shrinkWait 를 그대로 옮겼다.
   ⚠️ 후원 금액이 아니라 '시그니처 자신의 값'(sig_amount) 으로 고른다 — 26만 원을 쏴도 30만 원짜리가 걸릴 수 있어서다.
   ⚠️ 계엄령(25만)은 경보를 쓰므로 표에 넣지 않는다. 제목도 같이 보는 이유: sig_amount 가 없는 옛 대기줄 항목. */

export const MARTIAL_LAW_AMOUNT = 250000;
export const MARTIAL_LAW_TITLE = '계엄령';
export const MARTIAL_LAW_MESSAGE = '주의 계엄령 발동';      // 경보 아래 글자(옛 opFxFire({kinds:['warn'], message}))

// 10만 원 이상 시그니처마다 하나씩(연출 이름은 sigfx/sig-fx.js 의 ITEMS key)
export const SIGFX_BY_AMOUNT = {
    100000: 'jinap',   // 🚨 진압해 (2026-09-23 추가)
    100009: 'gazua',   130000: 'lambada', 150000: 'hotel',
    160000: 'crazy',   180000: 'bounce',  200000: 'martini',
    200001: 'pocha',   300000: 'pucha',   350000: 'edm',
    500000: 'sail',    500001: 'shield',  600001: 'slash',
    700000: 'nuna',    800000: 'club',   1000000: 'vip',
    2000000: 'angel', 3000000: 'mvp',
};

export function isMartialLaw(item) {
    if (!item) return false;
    if (item.sig_amount != null) return Number(item.sig_amount) === MARTIAL_LAW_AMOUNT;
    return String(item.title || '').trim() === MARTIAL_LAW_TITLE;
}

export function sigFxKey(item) {
    if (!item || item.sig_amount == null) return null;
    return SIGFX_BY_AMOUNT[Number(item.sig_amount)] || null;
}

/* 시그니처가 시작될 때 가운데에 무엇을 띄우나 — 옛 startPlayback 의 갈래 순서 그대로:
     'warn'    계엄령 — 'OO업' 대신 붉은 경보(이름을 부르지 않는다. 사이렌이 먼저다)
     'fx'      전용 연출이 있다 — 'OO업' 은 안 띄운다(연출마다 자기 글자 '가즈아' · '참격' · 'CLUB OPEN' … 이 있어 겹친다).
               ⚠️ 연출이 못 뜨면(파일을 못 받음 · 실패) 부르는 쪽이 'banner' 로 내려간다(옛 sigFxKey && sigFxPlay)
     'banner'  'OO업' 배너(bannerText 가 빈 글이면 아무것도 안 띄운다) */
export function titlePlan(item) {
    if (isMartialLaw(item)) return 'warn';
    if (sigFxKey(item)) return 'fx';
    return 'banner';
}

/* 'OO업' 배너 글 — 옛 reactionUpText · showReactionTitle 그대로. 빈 글이면 배너를 안 띄운다.
   🎲 주사위 시그(source 'dice')는 후원이 아니다 — 누가 밟았는지만('밍밍 · 시그 칸 도착', 서버가 banner 에 실어 준다). 금액 · '업' 없음.
   🎰 슬롯 당첨(skip_popup)은 시그니처 이름만(접미사 없음). 그 밖에는 bigMin(10만) 이상만 '이름 + 업'. 끝의 '님' 은 뗀다. */
export function bannerText(item, suffix, bigMin) {
    if (!item) return '';
    const dice = item.source === 'dice';
    const slotLike = dice || !!item.skip_popup;
    if (!slotLike && (parseInt(item.amount, 10) || 0) < (Number(bigMin) || 0)) return '';
    let name;
    if (dice) name = String(item.banner || ((item.donator || '') + ' · 시그 칸 도착')).trim();
    else name = String((item.skip_popup ? item.title : item.donator) || '').trim();
    if (name.endsWith('님')) name = name.slice(0, -1);
    if (!name) return '';
    return name + (slotLike ? '' : (typeof suffix === 'string' ? suffix : '업'));
}

/* 배너 색 · 크기 등급에 쓰는 금액 — 주사위는 후원이 아니라 0(옛 showReactionTitle(…, true, 0)) */
export function bannerAmount(item) {
    return item && item.source === 'dice' ? 0 : (parseInt(item && item.amount, 10) || 0);
}

/* 카드를 왼쪽으로 줄이는 때 — 전용 연출이 카드를 붙잡고 있는 동안은 미룬다(옛 shrinkWait).
   그냥 두면 축소 클래스는 붙는데 연출 애니메이션이 이겨 안 움직이다가, 연출이 끝나는 순간 카드가 '툭' 순간이동한다. */
export function shrinkWait(base, busyUntil, now) {
    return Math.max(Number(base) || 0, (Number(busyUntil) || 0) - (Number(now) || 0) + 120);
}
