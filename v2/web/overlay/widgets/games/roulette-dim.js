/* 🎡 룰렛 뒤 어둡게 — 옛 #roulette-overlay-backdrop(화면 전체 검정 75%, 룰렛판 바로 밑).
   룰렛 위젯이 판을 띄우는 동안(선 자리 4초 포함) 켜는 'roulette-game' 표시(#canvas.roulette-game-mode)를 보고
   games_a.css 가 켜고 끈다 — 이 위젯은 칸 하나만 깐다(남의 판 속은 안 본다).
   층: 판(점수판 · 후원 순위)보다 위, 게이지 · 알림보다 아래(옛 99999 — 게이지 100040 · 후원 팝업 100005 보다 아래). */
export function mount(root) {
    root.innerHTML = '<div class="rw-dim"></div>';
}
