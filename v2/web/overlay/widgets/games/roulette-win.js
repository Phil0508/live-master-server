/* 🎡 '이름 당첨!' 큰 글씨 — 옛 #roulette-winner-message-layer(.time-up-message: 화면 가운데 · 130px · 4초).
   룰렛 위젯이 다 섰을 때 stage.use('rouletteWin').show(이름, ms) 로 부른다(서버가 정한 이름 — ends_at 전엔 안 부른다).
   층: 룰렛판 위(옛 100002 > 룰렛 100001). */
export function mount(root, lm, opts) {
    root.innerHTML = '<div class="rw-winmsg"></div>';
    const el = root.firstElementChild;
    let timer = 0;
    opts.stage.provide('rouletteWin', {
        show(name, ms) {
            const txt = String(name || '').trim() + ' 당첨!';
            el.textContent = txt;
            // 벌칙 이름은 길다('팔굽혀펴기 20개 당첨!' = 130px 이면 1,400px) — 화면 폭에 맞춰 줄인다(옛 것 그대로)
            el.style.fontSize = Math.max(56, Math.min(130, Math.floor(980 / Math.max(1, txt.length)))) + 'px';
            el.classList.remove('show');
            void el.offsetWidth;
            el.classList.add('show');
            clearTimeout(timer);
            timer = setTimeout(() => el.classList.remove('show'), Math.max(300, Number(ms) || 4000));
        },
        hide() { clearTimeout(timer); el.classList.remove('show'); },
    });
}
