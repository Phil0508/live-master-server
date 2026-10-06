/* 🎰 시그니처 슬롯머신 — slot 조각 {round, phase, spin_at, ends_at, winner{id,title,amount,image_url}, reel[], seed}.
   **당첨은 서버가 정한다.** 방송판은 릴 셋을 돌려 winner 칸에 세우기만 한다(옛 handleSlotSpinOverlay 의 모습 · 박자 그대로).

   서버 화면 약속(v2/server/domain/slot.py)
     1. round 가 바뀌고 phase=spinning → 판을 띄우고 릴 셋을 reel 카드로 채운다(seed 로 뽑은 순서 — 창마다 같게).
        각 릴 맨 끝 칸 = winner. 0.1초 뒤 0.25초 간격으로 1.5 · 1.9 · 2.3초 동안 세우고, 3.2초 뒤 '[제목] 당첨!!' · 폭죽.
        카드 높이 120px 고정 — 서는 좌표(15칸 × 120)가 그 숫자에 묶여 있다.
     2. ends_at(= spin_at + 4초)에 slot.done{round} — 로그인 없이(?monitor=1 은 안 보낸다 · 서버도 스스로 닫는다).
        무대(stage)가 slot 이 아니게 되면 판을 내린다.
     3. 당첨 시그니처 소리는 여기서 틀지 않는다 — 대기줄(queue)이 play_after(=ends_at) 뒤에 평소처럼 튼다(두 번 나지 않게).
     4. 늦게 붙은 창: 박자는 **서버 시각**(spin_at)에 맞춘다 — 도는 중간에 붙으면 릴을 그만큼 앞으로 당겨(음수 지연) 그리고,
        ends_at 이 지났으면 돌리지 않고 당첨 칸을 바로 보여 준다.
     ⚠️ winner 는 [돌리기] 순간 공개 조각에 실린다 — 제목 글자는 3.2초 전에 띄우지 않는다. */
import { serverNow, rng, boom, esc, screenCovered } from './slot-roulette-kit.js';

const CARD_H = 120;          // ⚠️ .slot-reel 높이 · 카드 높이와 같아야 한다(당첨 칸에 정확히 서게)
const REPEAT = 15;           // 당첨 칸 앞에 까는 카드 수(옛 repeatCount)
const START_MS = 100;        // 판이 뜬 뒤 첫 릴이 출발하기까지
const GAP_MS = 250;          // 릴 사이 출발 간격
const SPIN_MS = [1500, 1900, 2300];
const WIN_MS = 3300;         // 0.1 + 3.2초 — '당첨!!' 글자 · 폭죽
const EASE = 'cubic-bezier(0.1, 0.9, 0.2, 1.0)';

export function mount(root, lm, opts) {
    root.innerHTML = '<div class="slot-wrap gm-board"><div class="slot-card">'
        + '<h1 class="slot-ttl">🎰 시그니처 슬롯머신</h1>'
        + '<div class="slot-reels">'
        + '<div class="slot-reel"><div class="slot-strip"></div></div>'
        + '<div class="slot-reel"><div class="slot-strip"></div></div>'
        + '<div class="slot-reel"><div class="slot-strip"></div></div>'
        + '</div><div class="slot-win">대기 중...</div></div></div>';
    const board = root.firstElementChild;
    const strips = [...root.querySelectorAll('.slot-strip')];
    const winEl = root.querySelector('.slot-win');
    let seen = null;              // 마지막으로 본 판 번호(처음 통째에서도 기억만 하지 않고 그 판을 그린다 — 늦게 붙은 창)
    let timers = [];
    let doneSent = 0;

    const clear = () => { timers.forEach(clearTimeout); timers = []; };
    const later = (ms, fn) => { timers.push(setTimeout(fn, Math.max(0, ms))); };

    function card(item, isWinner) {
        const t = String((item && item.title) || '시그니처');
        const amt = (Number(item && item.amount) || 0).toLocaleString();
        const img = String((item && item.image_url) || '');
        return '<div class="slot-cardi' + (isWinner ? ' win' : '') + '">'
            + (img ? '<img src="' + esc(img) + '" alt="" onerror="this.remove()">' : '')
            + '<div class="slot-cap"><div class="slot-cap-t">' + esc(t) + '</div><div class="slot-cap-a">' + amt + '원</div></div></div>';
    }

    /* 무대가 slot 일 때만 보인다(옛 handleData 의 slot-container 스위치). 판이 떠 있는 동안은 'slot-game' 표시를 켠다 —
       games_a.css 가 그걸 보고 후원 순위 · 최고 후원 · 게이지 딱지를 비킨다(옛 body.game-on). */
    function visible() {
        const on = (lm.get('show') || {}).stage === 'slot';
        board.classList.toggle('on', on && !screenCovered(lm));
        opts.stage.setMode('slot-game', on);
    }

    function sendDone(round) {
        if (opts.monitor || doneSent === round) return;
        doneSent = round;
        lm.cmd('slot.done', { round }).catch(() => {});
    }

    function spin(s) {
        clear();
        const w = s.winner || {};
        const title = w.title || (w.amount ? (Number(w.amount).toLocaleString() + '원') : '시그니처');
        const pool = (Array.isArray(s.reel) && s.reel.length) ? s.reel : [w];
        const r = rng(Number(s.seed) || Number(s.round) || 1);
        const elapsed = serverNow() - (Number(s.spin_at) || serverNow());
        const finalY = -(REPEAT * CARD_H);

        strips.forEach((strip, idx) => {
            let html = '';
            for (let i = 0; i < REPEAT; i++) html += card(pool[Math.floor(r() * pool.length)], false);
            html += card(w, true);
            strip.innerHTML = html;
            strip.style.transition = 'none';
            strip.style.transform = 'translateY(0px)';
        });
        void board.offsetWidth;          // 처음 자리(0)를 먼저 그려 둬야 미끄러진다

        strips.forEach((strip, idx) => {
            const t0 = START_MS + idx * GAP_MS, dur = SPIN_MS[idx];
            const into = elapsed - t0;   // 이 릴이 출발한 지 몇 ms(음수면 아직)
            if (into >= dur) {
                strip.style.transition = 'none';
            } else {
                // 늦게 붙은 창은 음수 지연으로 '그만큼 전에 출발한' 모습부터 — 창마다 같은 순간에 선다
                strip.style.transition = 'transform ' + dur + 'ms ' + EASE + ' ' + (-into) + 'ms';
            }
            strip.style.transform = 'translateY(' + finalY + 'px)';
        });

        if (elapsed >= WIN_MS) {
            winEl.textContent = '🎊 [' + title + '] 당첨!! 🎊';
        } else {
            winEl.textContent = '🎰 슬롯머신 돌리는 중...';
            later(WIN_MS - elapsed, () => {
                winEl.textContent = '🎊 [' + title + '] 당첨!! 🎊';
                if (board.classList.contains('on')) boom({ particleCount: 80, spread: 70, origin: { y: 0.4 } });
            });
        }
        const endIn = (Number(s.ends_at) || 0) - serverNow();
        later(endIn, () => { sendDone(Number(s.round)); });
    }

    function render(s) {
        s = s || {};
        const rnd = Number(s.round) || 0;
        if (rnd !== seen) {
            seen = rnd;
            if (s.phase === 'spinning' && s.winner) {
                // ends_at 이 한참 지난 판(아무도 done 을 못 보냈다)도 당첨 칸을 바로 보여 준다 — 무대가 slot 일 때만 보인다
                spin(s);
            }
        }
        visible();
    }

    lm.on('slot', render);
    lm.on('show', visible);
    lm.on('screen', visible);
}
