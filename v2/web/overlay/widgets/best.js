/* 💥 한 방 최고 후원 — tallies 조각의 best {name, amount, at, member}.
   - 금액(원은 작게) · 보낸 분. 받은 멤버(member)는 화면에 안 띄운다(대표님 2026-09-18 — 끝 화면만 쓴다).
   - 이름이 길면 판을 넓히지 않고 글씨를 줄인다(38 → 32 → 27px, 그 뒤는 …). 금액이 길어도 줄인다(58 → 48 → 40px).
   - 기록이 **바뀌는 순간**(at 이 달라짐)에만 '최고 기록 갱신!' — 처음 그림에서는 기억만 한다(OBS 를 켤 때마다 뜨지 않게). */
import { formatNum, restartClass } from '../util.js';

export function mount(root, lm, opts) {
    root.innerHTML = '<div class="best-wrap"><div class="best-board">'
        + '<div class="best-head">💥 한 방 최고 후원</div>'
        + '<div class="best-amt-row"><span class="best-amt">0</span><span class="best-won">원</span></div>'
        + '<div class="best-name">-</div>'
        + '</div><div class="best-flash">💥 최고 기록 갱신!</div></div>';
    const board = root.querySelector('.best-board');
    const flash = root.querySelector('.best-flash');
    const amtEl = root.querySelector('.best-amt');
    const nameEl = root.querySelector('.best-name');
    let seenAt = null;

    lm.on('tallies', t => {
        const b = (t && t.best) || {};
        const amt = Number(b.amount) || 0;
        const nm = amt ? (b.name || '익명') : '아직 없음';
        nameEl.textContent = nm;
        nameEl.style.setProperty('--best-name-size', nm.length <= 8 ? '38px' : (nm.length <= 11 ? '32px' : '27px'));
        const txt = formatNum(amt);
        amtEl.textContent = txt;
        amtEl.style.setProperty('--best-amt-size', txt.length <= 7 ? '58px' : (txt.length <= 9 ? '48px' : '40px'));
        const at = Number(b.at) || 0;
        if (seenAt !== null && at && at !== seenAt && opts.stage.isOn(opts.layer.id)) {
            restartClass(board, 'best-pop');
            restartClass(flash, 'show');
            try { const fx = opts.stage.use('fx'); if (fx) fx.burst(root, 'best'); } catch (e) {}   // ✨ 테마 입자(widgets/fx/burst.js)
        }
        seenAt = at;
    });
}
