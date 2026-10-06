/* 🏷️ 위젯 이름표 — 대표님이 옛 편집기(admin.html widgetNames)에서 보던 이름 그대로.
   v2 의 칸 이름(layers.js id)은 낙타 모양(donorRank)이라 옛 이름(donor-rank · acct_video)과 글자가 다르다 →
   id 그대로 · 대시 모양 · 밑줄 모양 순서로 찾는다. 표에 없는 칸은 id 를 그대로 보여 준다(새 위젯이 생겨도 목록에는 뜬다). */

// 옛 admin.html 의 widgetNames — 손대지 말고 옮겨 적은 것
const OLD = {
    'ranking': '🏆 랭킹판', 'dgscore': '🎲 주사위 점수 띠', 'gauge': '🔥 목표 게이지', 'account': '🏦 계좌 정보',
    'match': '⚔️ 대결 보드', 'home-race': '🏃 퇴근빵', 'popup': '🔔 점수 팝업', 'takeover': '👑 1등 탈환 팝업',
    'roulette': '🎡 행운의 룰렛', 'slot': '🎰 시그니처 슬롯머신', 'sig-tally': '📊 오늘의 시그니처', 'donor-rank': '🏅 후원 순위',
    'best': '💥 한 방 최고 후원', 'fundjar': '🏺 모금함', 'pinball': '🎱 구슬 핀볼', 'karaoke': '🎤 노래방 영상',
    'acct_video': '🎬 고액후원 영상', 'siggame': '🃏 시그 뒤집기', 'dicegame': '🎲 주사위판', 'notice': '📣 안내 전광판',
};

// v2 에서 새로 생겼거나 이름이 바뀐 칸
const V2 = {
    'scorePopup': '🔔 점수 팝업',
    'donation': '🔔 후원 팝업',
    'smallDon': '💬 소액 후원 띠',
    'signature': '🎵 시그니처 카드',
    'connection': '📶 연결 표시',
    'quiz': '🧩 퀴즈판',
    'hell': '🔥 지옥탈출',
    'homeRace': '🏃 퇴근빵',
    'home': '🏃 퇴근빵',
    'screen': '🎬 시작 · 끝 화면',
    'stageScreen': '🎬 시작 · 끝 화면',
    'accountHead': '🏦 계좌 정보(머리 줄)',
    'celebrate': '🎯 목표 달성',
    'goalBanner': '🎯 목표 달성',
    'offwork': '🏃 퇴근 · 지옥 탈출',
    'rouletteDim': '🎡 룰렛 뒤 어둡게',
    'rouletteWin': '🎡 룰렛 당첨 글씨',
    'matchFire': '⚔️ 대결 불꽃(바탕)',
    'matchFx': '⚔️ 대결 연출',
    'acctVideo': '🎬 고액후원 영상',
    'sigTally': '📊 오늘의 시그니처',
    'dgScore': '🎲 주사위 점수 띠',
    'diceGame': '🎲 주사위판',
    'sigGame': '🃏 시그 뒤집기',
    // 💡 조명 · ✨ 테마 연출(groups/fx.js) — 화면 전체 칸이라 끌어 옮길 일은 없다(목록에 이름만)
    'fxNeon': '🌈 조명 네온 테두리',
    'fxAudi': '🚗 아우디 LED',
    'fxBurst': '✨ 테마 입자',
    'fxMoon': '🌕 추석 보름달',
};

const kebab = s => s.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase();
const snake = s => s.replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase();

export function nameOf(id) {
    id = String(id || '');
    return V2[id] || OLD[id] || OLD[kebab(id)] || OLD[snake(id)] || OLD[id.toLowerCase()] || id;
}

// 기준점 — x · y 가 위젯의 어느 점인가(layers.js anchor 와 같은 뜻)
export const ANCHOR_TEXT = {
    tl: '왼쪽 위 모서리',
    tr: '오른쪽 위 모서리 — 판이 넓어지면 왼쪽으로 자란다',
    tc: '위 가운데',
    cc: '한가운데',
};
