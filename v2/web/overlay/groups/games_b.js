/* 층 표 묶음 — 주사위 · 시그뒤집기 · 대결 · 지옥탈출/퇴근빵.
   layers.js 와 같은 모양의 칸 목록. layers.js 가 이 목록을 이어 붙인다(이 파일만 고치면 된다).

   층(z) — layers.js 의 순서 규칙(후원 알림 · 시그니처 > 점수 팝업 > 게이지 > 판)을 지킨다:
     대결 불꽃 테두리 1(맨 아래 — 옛 .fire-vignette z 5) < 판(점수판 10 · 최고 후원 11 · 후원 순위 12) <
     게임판 15(games_a 와 같은 층 — 옛 게임판 100000) < '시간 종료!' · 꽃가루 18(옛 100000, 판보다 뒤에 적혀 위) < 게이지 20 < 알림 30~
     ⚠️ 무대(show.stage)에는 판이 하나만 오른다 — 게임판끼리 같은 층이어도 겹치지 않는다.
        주사위판과 점수 띠는 같이 뜬다 — 같은 층이면 표에서 뒤에 적힌 띠가 위(옛 DOM 순서와 같다: '한 바퀴' 배너가 띠 밑으로).
   보이기: 각 위젯이 무대를 보고 판 안에서 켜고 끈다(.gb-wrap.gb-on, 다 숨으면 display:none — 칸 상자가 0 이 되어 게이지 딱지가 안 비킨다).
     시작 · 끝 화면(screen.mode start/end)이면 위젯이 내린다(옛 body.stage-on).
     liveOnly — 대결 · 퇴근빵 · 지옥탈출(옛 handleData 의 '방송 꺼짐이면 숨김' 목록: match · home-race).
       주사위 · 시그뒤집기는 방송 전에도 뜬다(옛 것도 '방송 꺼짐 return' 보다 앞에서 그렸다).
     hideInReaction — 판 전부(옛 body.reaction-mode 목록: siggame · dicegame · dgscore · match · #ui-layer 안의 퇴근빵).
     solid — 판 전부(게이지 금액 딱지가 비킨다). 불꽃 테두리 · '시간 종료!' 는 캔버스 전체 칸이라 solid 가 아니다.
   옛 기본 자리: overlay.html 컨테이너 style · applyLayout —
     대결 288,795 · 시그뒤집기 171,340 폭 700 · 주사위 위 307(가운데로 모은다) · 점수 띠 6,191(= 판 바로 위, 편집기에서 안 옮겼으면 판을 따라간다)
     · 퇴근빵 = 점수판 자리(오른쪽 끝 42 → 1038, 위 167 — 이 동안 점수판은 비킨다). */
export const LAYERS = [
    // 🔥 대결 불꽃 테두리 — 수동 불꽃(무대 match) · 피버(남은 60초)
    { id: 'matchFire', widget: 'games/match_fire', z: 1,  x: 0,    y: 0,   w: 1080, h: 1920, liveOnly: true },
    // 🏃 퇴근빵 · 🔥 지옥탈출 — 점수판 자리(오른쪽 기준, 판 폭 946 이 왼쪽으로 자란다)
    { id: 'homeRace',  widget: 'games/homerace',   z: 15, x: 1038, y: 167, anchor: 'tr', liveOnly: true, hideInReaction: true, solid: true },
    { id: 'hell',      widget: 'games/hell',       z: 15, x: 1038, y: 167, anchor: 'tr', liveOnly: true, hideInReaction: true, solid: true },
    // ⚔️ 대결판 — 게이지 720 + 카드
    { id: 'match',     widget: 'games/match',      z: 15, x: 288,  y: 795,               liveOnly: true, hideInReaction: true, solid: true },
    // 🃏 시그뒤집기 — 판 폭 700(폭은 위젯이 정한다 — 숨었을 때 칸이 0 이 되게)
    { id: 'siggame',   widget: 'games/siggame',    z: 15, x: 171,  y: 340,                               hideInReaction: true, solid: true },
    // 🎲 주사위판 — 위 307, 가운데로 모은다(8×5 판이면 폭 1030 → 25~1055)
    { id: 'dicegame',  widget: 'games/dice',       z: 15, x: 540,  y: 307, anchor: 'tc',                 hideInReaction: true, solid: true },
    // 🎲 주사위 점수 띠 — 판 바로 위(위젯이 판을 따라간다). 편집기에서 옮기면 그 자리
    { id: 'dgscore',   widget: 'games/dicescore',  z: 15, x: 6,    y: 191,                               hideInReaction: true, solid: true },
    // 💥 '시간 종료!' · 꽃가루 — 캔버스 전체(대결판이 부른다)
    { id: 'matchFx',   widget: 'games/match_fx',   z: 18, x: 0,    y: 0,   w: 1080, h: 1920, liveOnly: true },
];
