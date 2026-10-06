/* 층 표 묶음 — 공지 · 계좌 · 시작/끝 화면 · 축하 · 퇴근 연출 · 계좌 영상 · 노래방 · 모금함.
   layers.js 와 같은 모양의 칸 목록. layers.js 가 이 목록을 이어 붙인다(이 파일만 고치면 된다).

   층(z) — layers.js 의 순서(판 10~ < 게이지 20 < 알림 30~ < 후원 카드 40~ < 시그니처 50)를 지킨다:
     13~15  판 무리       모금함 · 계좌 · 안내 전광판(옛 머리 줄 #headrow — 판 맨 위였다)
     22     시작/끝 화면  판 · 게이지보다 위, 알림 · 후원 카드 · 시그니처보다 아래(옛 87000 — '기다리는 동안 들어온 후원도 알림은 떠야 한다')
     23     계좌 영상     시작/끝 화면 · 판(계좌 줄 포함)보다 위 → 계좌가 영상 앞으로 튀어나오지 않는다(옛 acct-video-on, 10-05).
                          시그니처 · 후원 카드는 영상 위(옛 88000 < 90000 < 100005)
     24     노래방        영상보다 위(옛 90000 > 88000)
     32~33  목표 달성 · 퇴근 — 알림 무리. ⚠️ 옛 것은 후원 카드보다 위였다(100050 · 999999) — 표의 약속(알림 < 후원 카드)을 따랐다
   옛 기본 자리 출처: overlay.html 의 컨테이너 style · tests/acct_video_layer_test.py 의 운영 배치(계좌 영상 0,380 · 0.84). */
export const LAYERS = [
    // 🏺 모금함 깃발 — 옛 #fundjar-container 40,167(점수판 왼쪽 빈자리, 깃발 108×262). 보이기는 위젯이 정한다(hud.fundjar 또는 fundjar.enabled).
    { id: 'fundjar',     widget: 'basics2/fundjar',      z: 13, x: 40,   y: 167, liveOnly: true },
    // 🏦 계좌(평소) — 점수판 바로 아래, 오른쪽 끝 1038(점수판과 같이). 점수판 키가 바뀌면 따라간다(옛 syncAccountPos).
    //    y 는 점수판을 못 잴 때 값. 후원 순위(donorRank gap 64)가 이 줄(48) + 사이 8 을 비워 두고 붙는다.
    { id: 'account',     widget: 'basics2/account',      z: 14, x: 1038, y: 331, anchor: 'tr', below: 'ranking', gap: 8, place: 'board',
      liveOnly: true, hud: 'account', hudDefault: true, hideInReaction: true, solid: true },
    // 🏦 계좌(머리 줄) — 게임판이 점수판 자리를 쓰는 동안(퇴근빵 · 주사위 · 룰렛 · 슬롯 · 시그뒤집기 · 번외 판) 6,115 로 올라온다.
    { id: 'accountHead', widget: 'basics2/account',      z: 14, x: 6,    y: 115, place: 'head',
      liveOnly: true, hud: 'account', hudDefault: true, hideInReaction: true, solid: true },
    // 📣 안내 전광판 — 머리 줄(6,115 · 폭 1068 · 높이 48). 계좌가 머리 줄에 오면 654 · 폭 388 로 물러난다(위젯 안에서).
    //    방송 전에도 흐른다(옛 noticeUpdate 는 '방송 꺼짐 return' 앞). 띠가 올라와 있을 때만 판으로 센다.
    { id: 'notice',      widget: 'basics2/notice',       z: 15, x: 6,    y: 115, hud: 'notice', hudDefault: false, hideInReaction: true, solid: true },

    // 🎬 시작 전 · 끝 화면 — 캔버스 전체(불투명). 방송 전에도 뜬다.
    { id: 'stageScreen', widget: 'basics2/stage-screen', z: 22, x: 0,    y: 0,   w: 1080, h: 1920 },
    // 🎞️ 계좌 고액후원 영상 — 1280×720 상자를 0.84 배(1075×605)로 가운데(운영 배치 0,380 · 0.84). 방송 전에도 튼다.
    { id: 'acctVideo',   widget: 'basics2/acct-video',   z: 23, x: 2,    y: 380, w: 1280, h: 720, scale: 0.84 },
    // 🎤 노래방 — 옛 #karaoke-container 40,560 · 1000×563.
    { id: 'karaoke',     widget: 'basics2/karaoke',      z: 24, x: 40,   y: 560, w: 1000, h: 563 },

    // 🎯 목표 달성 — 안전지대 한가운데(옛 .goal-banner 540,470). 옛 #ui-layer 안 → 시그니처 중엔 가린다.
    { id: 'goalBanner',  widget: 'basics2/goal-banner',  z: 32, x: 540,  y: 470, anchor: 'cc', hideInReaction: true },
    // 🏃 퇴근 · 지옥 탈출 — 화면 위 1/5(옛 top 20vh = 384), 가운데.
    { id: 'offwork',     widget: 'basics2/offwork',      z: 33, x: 540,  y: 384, anchor: 'tc' },
];
