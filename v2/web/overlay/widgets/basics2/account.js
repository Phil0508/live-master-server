/* 🏦 계좌 — account 조각(bank · acc_num · name). 옛 #account-container / .acc-box-v2 그대로(높이 48 한 줄).
   자리(옛 syncAccountPos):
   - 평소엔 점수판 바로 아래(오른쪽 42 · 판 아래끝 + 8 — layers 표의 below:'ranking').
   - 게임판이 점수판 자리를 쓰는 동안(퇴근빵 · 지옥탈출 · 주사위 · 룰렛 · 슬롯 · 시그뒤집기 · 번외 판)은 머리 줄(6,115)로 올라간다.
     퇴근빵 · 지옥탈출은 10-17 부터 무대가 아니다 — 판이 실제로 떠 있는지(race_view.js)로 본다(옛 75644ae: 지옥 판이 계좌 띠 밑으로 삐져나옴).
     실측해 보니 어느 게임에서도 안 겹치는 띠는 머리 줄(115~163) 뿐이었다.
   → 칸이 둘(layer.place 'board' · 'head')이고 같은 위젯이 붙는다. 지금 자리에 맞는 쪽만 보인다.
   - 은행 · 번호가 둘 다 비면 안 보인다. 방송 중에만(liveOnly) · 고정 자리 스위치 [계좌](hud.account).
   - 테마를 입어도 계좌는 기본 모습(금색 유리판) — 돈이 가는 곳이라 한눈에 읽혀야 한다(대표님 2026-09-22).
   - 🏦 은행 옷(10-19 대표님 시안 C): 은행 이름에 '기업' · 'IBK' 가 들어 있으면 bank-ibk — 왼쪽 칸에 기업은행 마크(vendor/bank/ibk-symbol.png),
     은행 이름 · 테두리 빛만 기업은행 파랑. 판은 그대로 어두운 유리. 다른 은행이면 원래 금색으로 저절로 돌아간다.
   - 고액후원 영상이 떠 있는 동안 계좌가 영상 앞으로 나오면 안 된다(옛 acct-video-on, 10-05) — v2 에서는 층 표에서
     영상 칸(z 23)이 계좌 칸(z 14)보다 위라 따로 할 일이 없다.
   - 안 보일 때는 칸이 자리를 안 차지한다(게이지 금액 딱지가 비킬 판으로 안 센다). */

import { raceAway } from '../games/race_view.js';

// 점수판 자리를 쓰는 무대 — 이 무대면 계좌는 머리 줄, 안내 전광판은 오른쪽으로 물러난다(notice.js 도 accountAway 를 본다)
export const AWAY_STAGES = ['dicegame', 'roulette', 'slot', 'siggame'];
// 이 조각이 바뀌면 다시 본다
export const AWAY_SLICES = ['show', 'players', 'hell', 'home'];

/** 계좌가 머리 줄로 올라가 있나 — 무대(AWAY_STAGES) · 번외 판 · 퇴근빵/지옥탈출 판이 떠 있을 때 */
export function accountAway(lm) {
    const sh = lm.get('show') || {};
    return AWAY_STAGES.includes(sh.stage) || !!(lm.get('players') || {}).extra_active || raceAway(k => lm.get(k));
}

/** 은행 이름 → 은행 옷 이름('' 이면 기본 금색) */
export function bankSkin(bank) {
    const b = String(bank || '').replace(/\s+/g, '');
    return /기업은행|^기업$|IBK/i.test(b) ? 'ibk' : '';
}

export function mount(root, lm, opts) {
    const place = (opts.layer && opts.layer.place) || 'board';
    root.classList.add('b2-acc');
    root.dataset.anchor = (opts.layer && opts.layer.anchor) || 'tl';
    root.innerHTML = '<div class="acc-box-v2 gone">'
        + '<span class="acc-ico">🏦</span>'
        + '<span class="acc-who"><span class="acc-bank"></span><span class="acc-holder"></span></span>'
        + '<span class="acc-num-v2"></span></div>';
    const box = root.firstElementChild;
    const bankEl = root.querySelector('.acc-bank');
    const nameEl = root.querySelector('.acc-holder');
    const numEl = root.querySelector('.acc-num-v2');

    function render() {
        const a = lm.get('account') || {};
        const has = !!(a.bank || a.acc_num);
        const away = accountAway(lm);
        const mine = (place === 'head') === away;
        bankEl.textContent = a.bank || '';
        box.classList.toggle('bank-ibk', bankSkin(a.bank) === 'ibk');
        numEl.textContent = a.acc_num || '';
        nameEl.textContent = a.name || '';
        const gone = !(has && mine);
        if (box.classList.contains('gone') !== gone) {
            box.classList.toggle('gone', gone);
            opts.stage.layoutChanged();
        }
    }
    ['account', ...AWAY_SLICES].forEach(k => lm.on(k, render));
}
