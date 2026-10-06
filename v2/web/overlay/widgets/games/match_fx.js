/* 💥 대결 '시간 종료!' — 캔버스 전체 칸. 대결판(match)이 무대의 'matchFx'.boom(x, y) 로 부른다(판끼리 화면을 안 만진다).
   - 가운데(위 45%)에 '시간 종료!' 큰 글씨 3초(옛 #time-up-message-layer).
   - 타이머 자리에서 꽃가루 150개(옛 confetti 150 · spread 100 · 빨강 · 주황 · 노랑). 꽃가루 그림은 우리 서버의
     /vendor/confetti.browser.min.js(canvas-confetti 1.9.3, 옛 방송판과 같은 파일)를 처음 쓸 때 한 번 받는다.
     이 칸 안의 캔버스에만 그린다 — 후원 알림 · 시그니처(더 위 층)를 덮지 않는다. 못 받으면 꽃가루만 빠진다. */
const CONFETTI_SRC = '/vendor/confetti.browser.min.js';
let libP = null;

function loadConfetti() {
    if (typeof window.confetti === 'function') return Promise.resolve(window.confetti);
    if (libP) return libP;
    libP = new Promise(resolve => {
        const s = document.createElement('script');
        s.src = CONFETTI_SRC;
        s.async = true;
        s.onload = () => resolve(typeof window.confetti === 'function' ? window.confetti : null);
        s.onerror = () => resolve(null);
        document.head.appendChild(s);
    });
    return libP;
}

export function mount(root, lm, opts) {
    // ⚠️ 평소에는 칸을 비워 둔다 — 글씨를 미리 깔아 두면 생김새(CSS)가 늦게 붙거나 못 붙은 창에서 '시간 종료!' 가
    //    왼쪽 위에 그대로 비쳤다(10-07 다른 검사에서 잡힘). 터질 때 만들고, 끝나면 걷는다.
    root.textContent = '';
    let cv = null, shoot = null, msg = null, hideT = null;

    opts.stage.provide('matchFx', {
        /* x, y = 캔버스(1080×1920) 좌표 — 꽃가루가 터지는 자리(타이머 가운데) */
        boom(x, y) {
            clearTimeout(hideT);
            if (msg) msg.remove();
            msg = document.createElement('div');
            msg.className = 'time-up-message';
            msg.textContent = '시간 종료!';
            root.appendChild(msg);
            void msg.offsetWidth;
            msg.classList.add('show');
            const mine = msg;
            hideT = setTimeout(() => {
                mine.classList.remove('show');
                setTimeout(() => { mine.remove(); if (msg === mine) msg = null; }, 500);   // 사라지는 0.4초 뒤 걷는다
            }, 3000);
            loadConfetti().then(lib => {
                if (!lib) return;
                try {
                    if (!cv) {
                        cv = document.createElement('canvas');
                        cv.className = 'mfx-canvas';
                        root.insertBefore(cv, root.firstChild);          // 글씨보다 아래
                    }
                    if (!shoot) shoot = lib.create(cv, { resize: true, useWorker: false });
                    shoot({ particleCount: 150, spread: 100, startVelocity: 40,
                            origin: { x: Math.max(0, Math.min(1, (x || 540) / 1080)), y: Math.max(0, Math.min(1, (y || 864) / 1920)) },
                            colors: ['#ff0000', '#ff5500', '#ffff00'] });
                } catch (e) { /* 꽃가루는 없어도 방송은 계속된다 */ }
            });
        },
    });
}
