/* 층 표 묶음 — 퀴즈 · 핀볼 · 룰렛 · 슬롯.
   layers.js 와 같은 모양의 칸 목록. layers.js 가 이 목록을 이어 붙인다(이 파일만 고치면 된다).

   층(z) — layers.js 의 순서 규칙(후원 알림 · 시그니처 > 점수 팝업 > 게이지 > 판)을 지킨다:
     판(점수판 10 · 최고 후원 11 · 후원 순위 12) < 룰렛 뒤 어둡게 14 < 게임판 15 < 룰렛 16 < '이름 당첨!' 17 < 게이지 20 < 알림 30~
     옛 순서와 같다: 게임판 100000 · 룰렛 뒤 어둡게 99999 · 룰렛 100001 · 당첨 글씨 100002 · 게이지 100040 · 후원 팝업 100005.
     ⚠️ 무대(show.stage)에는 판이 하나만 오른다 — 게임판끼리 같은 층이어도 겹치지 않는다. 룰렛만 다 선 뒤 4초 더 남아
        돌아간 무대(예: 주사위판) 위에 떠 있어야 해서 한 층 위(16)다.
   보이기: 각 위젯이 무대를 보고 판 안에서 켜고 끈다(.gm-board.on). 칸 자체는 늘 있다(편집기 자리 · 폭죽 자리 재기).
     liveOnly — 룰렛만(옛 방송판도 방송 꺼짐이면 룰렛 칸을 display:none 했다). 퀴즈 · 핀볼 · 슬롯은 방송 전에도 뜬다(옛 것과 같다).
     hideInReaction — 퀴즈 · 핀볼(옛 body.reaction-mode 목록). 룰렛 · 슬롯은 시그니처가 돌아도 남는다(옛 것과 같다 —
       슬롯 당첨 시그는 릴이 선 뒤에 나온다).
   옛 기본 자리: overlay.html 의 컨테이너 style(퀴즈 0,700 폭 1080 · 핀볼 50,300 · 슬롯 191,452 · 룰렛 234,311 × 0.87). */
export const LAYERS = [
    // 🎡 룰렛 뒤 화면 전체를 75% 어둡게(옛 #roulette-overlay-backdrop) — 룰렛이 떠 있을 때만(#canvas.roulette-game-mode)
    { id: 'rouletteDim', widget: 'games/roulette-dim', z: 14, x: 0,   y: 0,   w: 1080, h: 1920, liveOnly: true },
    // 🧩 퀴즈 네모칸 — 폭 전체에 가운데 정렬(칸 120 × 여덟 = 1064)
    { id: 'quiz',        widget: 'games/quiz',        z: 15, x: 0,   y: 700, w: 1080, hideInReaction: true },
    // 🎱 구슬 핀볼 — 980 × 840 캔버스
    { id: 'pinball',     widget: 'games/pinball',     z: 15, x: 50,  y: 300, hideInReaction: true },
    // 🎰 슬롯머신 — 660 × 360(릴 창 170 × 120 은 서는 좌표와 묶여 있다)
    { id: 'slot',        widget: 'games/slot',        z: 15, x: 191, y: 452 },
    // 🎡 룰렛 — 660 × 740 판을 0.87 배(574 × 644 → 311~955). 게임 자리에 맞춘 값이라 배율은 이 표에서만 바꾼다
    { id: 'roulette',    widget: 'games/roulette',    z: 16, x: 234, y: 311, scale: 0.87, liveOnly: true },
    // 🎡 '이름 당첨!' — 화면 가운데(옛 .time-up-message: 위 45% = 864)
    { id: 'rouletteWin', widget: 'games/roulette-win', z: 17, x: 540, y: 864, anchor: 'cc', liveOnly: true },
];
