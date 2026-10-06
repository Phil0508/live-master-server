/* 💬 소액 후원 띠 — 방송판 맨 위 반투명 한 줄(옛 #small-don, 대표님 2026-09-29 A안). popup 조각의 donation.
   - 화면에만(display_only) 후원이거나 0원 초과 1만 원 미만이면 가운데 카드 대신 여기('OO님이 N원 후원했습니다!').
   - 여러 건이 몰리면 줄을 서되 밀린 만큼 짧게: 4건 이상 남으면 2초 · 2건 이상 3초 · 아니면 5초. 아무도 건너뛰지 않는다.
   - 띠는 시그니처를 붙잡지 않는다(카드처럼 기다리게 하지 않는다 — 옛 것과 같다).
   - 조종실 알림 스위치 [1천~9천 알림](show.alerts.small)을 끄면 아무것도 안 띄운다(카드로 되돌리지도 않는다). */
import { formatNum, classifyDonation } from '../util.js';

export function mount(root, lm, opts) {
    root.innerHTML = '<div class="small-don">'
        + '<div class="sd-line"><span class="sd-hl sd-name"></span>님이 <span class="sd-hl sd-amt"></span>원 후원했습니다!</div>'
        + '<div class="sd-msg"></div></div>';
    const bar = root.firstElementChild;
    const nameEl = root.querySelector('.sd-name');
    const amtEl = root.querySelector('.sd-amt');
    const msgEl = root.querySelector('.sd-msg');
    const queue = [];
    let busy = false;
    let seen;

    function next() {
        if (!queue.length) { busy = false; return; }
        busy = true;
        const d = queue.shift();
        try {
            nameEl.textContent = d.name || '익명';
            amtEl.textContent = formatNum(d.amount);
            const msg = String(d.message || '').trim();
            msgEl.textContent = msg;
            msgEl.style.display = msg ? '' : 'none';
            bar.classList.remove('show');
            void bar.offsetWidth;
            bar.classList.add('show');
        } catch (e) { console.error('[소액 띠] 그리기 실패 — 다음으로 넘어간다:', e); }
        const left = queue.length;
        const hold = left >= 4 ? 2000 : (left >= 2 ? 3000 : 5000);
        setTimeout(() => { bar.classList.remove('show'); setTimeout(next, 500); }, hold);
    }

    lm.on('popup', (pop, slices) => {
        const d = pop && pop.donation;
        if (!d) return;
        const key = d.id || String(d.at);
        if (key === seen) return;
        seen = key;
        if (!opts.isFresh(d.at)) return;
        if (!((slices.session || {}).live)) return;
        if (classifyDonation(d, slices.queue) !== 'small') return;
        if (!opts.stage.alertOn('small')) return;
        queue.push(d);
        if (!busy) next();
    });
}
