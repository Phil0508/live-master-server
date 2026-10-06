/* 🗂️ 방송판 층 표 — 위젯의 자리 · 크기 · 위아래 순서는 **여기 한 곳**에서만 정한다.

   ⚠️ 왜 표 하나인가: 옛 방송판(overlay.html 1만 1천 줄)은 z-index 가 HTML · CSS · JS 곳곳에 흩어져 있었다.
      10-06 닫는 </div> 하나가 판 6개를 후원 팝업 위로 올렸다 — 어디서 순서가 정해지는지 아무도 몰랐다.
      v2 에서는 overlay.css 에 z-index 를 쓰지 않는다. main.js 가 이 표의 z 만 칸에 넣는다.

   캔버스 = 1080 × 1920(세로 방송). 좌표는 전부 이 캔버스 기준 px.
   칸마다:
     id        칸 이름(겹치면 안 된다)
     widget    widgets/<widget>.js — mount(root, lm, opts) 를 내보낸다
     z         층 번호. 클수록 위. ⚠️ 후원 알림 · 시그니처 > 점수 팝업 > 게이지 > 판 — 이 순서를 지킬 것
     x, y      자리. anchor 가 어느 점을 그 자리에 둘지 정한다
     anchor    'tl'(왼쪽 위, 기본) · 'tr'(오른쪽 위 — 판이 넓어지면 왼쪽으로 자란다) · 'tc'(위 가운데) · 'cc'(한가운데)
     scale     배율(기본 1)
     w, h      칸 크기를 못 박을 때만(없으면 내용만큼)
     liveOnly  방송 중(session.live)에만 보인다 — 옛 handleData 의 '방송 꺼짐이면 판 숨김' 과 같다
     hud       조종실 '고정 자리' 스위치 이름(show.hud.<이름>). hudDefault 는 show 조각이 없을 때 값(옛 show.py HUD_DEFAULT)
     hideInReaction  시그니처가 도는 동안 숨긴다(옛 body.reaction-mode 가 #ui-layer 를 숨기던 것)
     below, gap  다른 칸 바로 아래에 붙는다(그 칸의 아래끝 + gap). 사람 수가 바뀌어 기준 칸 높이가 바뀌면 따라 움직인다
     solid     '자리를 차지하는 판' — 게이지 금액 딱지가 이 판들과 겹치면 위나 아래 빈자리로 비킨다(옛 placeGoalTip)
     debugOnly ?debug=1 일 때만 만든다

   옛 기본 자리 출처: overlay.html 의 컨테이너 style · admin.html 편집기 기본값 · layout.json(점수 팝업 · 1등 탈환).
*/
import { LAYERS as BASICS2 } from './groups/basics2.js';
import { LAYERS as GAMES_A } from './groups/games_a.js';
import { LAYERS as GAMES_B } from './groups/games_b.js';
import { LAYERS as FX } from './groups/fx.js';          // 💡 조명(네온 · 아우디) · ✨ 테마 입자 · 🌕 보름달

export const CANVAS = { w: 1080, h: 1920 };

const BASE = [
    // ── 판(정보 위젯) ─────────────────────────────────────────
    // 🏆 점수판 — 오른쪽 끝에서 42px(오른쪽 끝 1038 = 목표 막대 1046 바로 앞), 위 167. 왼쪽으로 자란다.
    { id: 'ranking',   widget: 'ranking',     z: 10, x: 1038, y: 167, anchor: 'tr', liveOnly: true, hud: 'ranking',    hudDefault: true,  hideInReaction: true, solid: true },
    // 💥 한 방 최고 후원 — 옛 기본 40,400(폭 340)
    { id: 'best',      widget: 'best',        z: 11, x: 40,   y: 400,               liveOnly: true, hud: 'best',       hudDefault: false, solid: true },
    // 🏅 후원 순위 — x 658(폭 380 → 오른쪽 끝 1038). 위아래는 점수판을 따라간다(옛 syncAccountPos):
    //    점수판 아래끝 + 8 + 계좌 줄(48) + 8 = gap 64. 점수판이 2줄이면 올라오고 5줄이면 내려간다. y 는 점수판을 못 잴 때 값.
    { id: 'donorRank', widget: 'donor-rank',  z: 12, x: 658,  y: 387, below: 'ranking', gap: 64, liveOnly: true, hud: 'donor_rank', hudDefault: false, solid: true },
    // 📊 시그 집계 — 옛 자리(800, 315) · 판과 같은 높이(옛 100000). 게임판이 떠도 안 비킨다(옛 game-on 규칙에 없었다).
    { id: 'sigTally',  widget: 'sig-tally',   z: 12, x: 800,  y: 315,               liveOnly: true, hud: 'sig_tally',  hudDefault: false, solid: true },
    // 💰 목표 게이지 — 오른쪽 끝 세로 막대(1046~1076 / 115~954). 판보다 위(옛 100040 > 게임판 100000).
    { id: 'gauge',     widget: 'gauge',       z: 20, x: 1046, y: 115,               liveOnly: true, hud: 'gauge',      hudDefault: true,  hideInReaction: true },

    // ── 알림 ────────────────────────────────────────────────
    // 🔔 점수 팝업('하율 후원 +5') · 👑 1등 탈환 — 가운데 정렬(옛 layout.json 342,536 · 328,639 의 알약 가운데)
    { id: 'scorePopup', widget: 'score-popup', z: 30, x: 540, y: 536, anchor: 'tc' },
    { id: 'takeover',   widget: 'takeover',    z: 31, x: 540, y: 639, anchor: 'tc', hideInReaction: true },
    // 🎁 후원 카드 — 화면 한가운데(옛 #toon-popup-container 50%/50%)
    { id: 'donation',   widget: 'donation',    z: 40, x: 540, y: 960, anchor: 'cc' },
    // 💬 소액 후원 띠 — 맨 위 한 줄, 폭 전체(옛 #small-don)
    { id: 'smallDon',   widget: 'small-don',   z: 41, x: 0,   y: 0,   w: 1080 },

    // ── 시그니처 ─────────────────────────────────────────────
    // 🎵 시그니처 카드 · 'OO업' 배너 — 캔버스 전체를 덮는 칸(안에서 가운데 → 2.5초 뒤 왼쪽 180,600 으로 작게).
    //    옛 순서 그대로 후원 카드(100005) · 소액 띠(100006)보다 위(100010 · 배너 100015).
    { id: 'signature',  widget: 'signature',   z: 50, x: 0,   y: 0,   w: 1080, h: 1920 },

    // ── 점검용 ──────────────────────────────────────────────
    { id: 'connection', widget: 'connection',  z: 90, x: 8,   y: 8,   debugOnly: true },
];

// 묶음마다 따로 고친다(여러 사람이 한 파일을 같이 고치다 꼬이지 않게). 같은 id 가 있으면 뒤에 온 것이 이긴다.
export const LAYERS = (() => {
    const all = [...BASE, ...BASICS2, ...GAMES_A, ...GAMES_B, ...FX];
    const seen = new Map();
    all.forEach(L => seen.set(L.id, L));
    return [...seen.values()];
})();
