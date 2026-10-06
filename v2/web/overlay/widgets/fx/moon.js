/* 🌕 추석 보름달 — 추석 테마에서 큰 후원(3만 원 이상) · 최고 기록 갱신 · 핀볼 우승 때 후원 알림 뒤에서 떠오른다(옛 #theme-moon).
   달 그림은 추석 테마의 --crown(달토끼). 부르는 것은 테마 입자(burst.js)뿐 — stage.use('themeMoon').rise(). */
export function mount(root, lm, opts) {
    root.innerHTML = '<div class="theme-moon" aria-hidden="true"></div>';
    const moon = root.firstElementChild;
    opts.stage.provide('themeMoon', {
        rise() {
            moon.classList.remove('rise');
            void moon.offsetWidth;          // 연달아 와도 처음부터 다시 떠오른다
            moon.classList.add('rise');
        },
    });
}
