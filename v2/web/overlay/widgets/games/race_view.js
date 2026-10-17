/* 🏃🔥 퇴근빵 · 지옥탈출 — 지금 방송판에 어느 판을 어떤 모양으로 둘지. 서버 조각만 보고 정한다(화면은 안 만진다 → node 로 검사).

   10-17(w2races) — 두 판은 무대(show.stage, 한 번에 하나)가 아니라 **늘 붙는 칸**이다. 다른 게임을 켜도 안 꺼진다.
   kind   'hell' | 'home' | null
          지옥 = hell.on 이고 hell.shown(값이 없는 옛 저장본은 보임) · 퇴근 = home.on. 둘 다 켜져 있으면 지옥이 먼저(대표님 10-17)
          — 퇴근빵은 숨기만 하고 셈 · 카드는 서버에서 계속 돈다.
   shape  'big'  점수판 자리 큰 판(지금 모습) — 무대가 비었거나 대결 · 룰렛 · 슬롯 · 퀴즈일 때
                 (룰렛 · 슬롯은 몇 초 동안 위에 덮인다 — 층이 판(13) < 게임판(15)이라 게임판이 늘 위)
          'thin' 얇은 판(제목 + 한 사람씩 5초마다 도는 한 줄, 167~290) — 시그뒤집기(340~) · 핀볼(300~) 이 같은 자리 아래를 쓸 때,
                 지옥탈출: 퀴즈 중 9명 이상(큰 판 아래끝이 퀴즈 네모칸 700 에 닿는다) · 대결 중엔 몇 명이든 큰 판
                 퇴근빵: 퀴즈 · 대결이 같이 뜰 때 큰 판 아래끝(homeBottom)이 그 판 위끝에 닿으면 — GOAL 줄이 하나 더 있어 지옥보다 길다
                 (10-17 연습 서버에서 잼: 6명 695 · 7명 755 · 8명 815 → 퀴즈(700)는 7명부터, 대결(795)은 8명부터 얇은 판)
          null   숨김 — 주사위판 동안(주사위판 + 점수 띠가 안전지대를 거의 다 쓴다 · 대표님 10-17 '숨긴다')
   시그니처가 나오는 동안 숨는 것은 층 표(hideInReaction)가, 시작 · 끝 화면은 위젯(coverOn)이 맡는다. */

export const HIDE_STAGES = ['dicegame'];
export const THIN_STAGES = ['siggame', 'pinball'];
export const QUIZ_BIG_MAX = 8;            // 지옥탈출만 — 퀴즈 중 이 수까지 큰 판

// 🏃 퇴근빵 큰 판 높이 — 제목 · 테두리 · GOAL 줄 168 + 한 사람 60(.home-race-row). 연습 서버에서 잰 값(위 주석)
//    ⚠️ 기본 테마 값이다. 테마는 제목 글꼴 · 테두리가 달라 머리가 168~179(10-17 테마 16벌 실측 — 아케이드 · 로즈가 179), 한 사람 60 은 같다.
//       그래서 테마 판은 아래끝이 최대 11px 더 내려온다 — 대결(795)은 7명 766 이라 괜찮고, 퀴즈(700)는 6명 706 으로 네모칸이 판 아래 테두리만 살짝 덮는다(GOAL 줄은 안 가린다).
export const HOME_HEAD = 168, HOME_ROW = 60;
// 퇴근빵과 같이 뜨는 아래 게임판 — 무대 이름 → 칸 id · 기본 위끝(groups/games_a.js 퀴즈 y700 · games_b.js 대결판 y795)
export const BELOW = { quiz: { id: 'quiz', y: 700 }, match: { id: 'match', y: 795 } };
const HOME = { id: 'homeRace', y: 167 };

// 칸 자리 — 편집기에서 옮겼으면(layout 조각) 그 자리 · 배율, 아니면 표의 기본 자리
function cellAt(get, L) {
    const o = ((get('layout') || {}).widgets || {})[L.id] || {};
    const num = v => typeof v === 'number' && isFinite(v);
    return { y: num(o.y) ? o.y : L.y, scale: num(o.scale) && o.scale > 0 ? o.scale : 1 };
}

/** 퇴근빵 큰 판의 아래끝(px) — rows 사람. top · scale 은 칸 자리(기본 167 · 1) */
export function homeBottom(rows, top = HOME.y, scale = 1) {
    return top + (HOME_HEAD + HOME_ROW * rows) * scale;
}

/** 퇴근빵 큰 판이 같이 뜬 게임판(퀴즈 · 대결)에 닿나 — 닿으면 얇은 판으로 */
export function homeHitsBelow(get, st, rows) {
    const B = BELOW[st];
    if (!B) return false;
    const h = cellAt(get, HOME), b = cellAt(get, B);
    return homeBottom(rows, h.y, h.scale) > b.y;             // 6명 695 < 퀴즈 700 — 판 그림자만 살짝 걸친다
}

/** get(조각 이름) → 조각. 돌려받는 값: { kind, shape, rows } — rows = 판에 오를 사람 수 */
export function raceView(get) {
    const players = get('players') || {};
    const list = Array.isArray(players.list) ? players.list : [];
    const names = new Set(list.map(b => b && b.name));
    const hell = get('hell') || {};
    const home = get('home') || {};
    let kind = null, rows = 0;
    if (hell.on && hell.shown !== false) {
        rows = Object.keys(hell.goals || {}).filter(n => names.has(n)).length;
        if (rows) kind = 'hell';
    }
    if (!kind && home.on && list.length) { kind = 'home'; rows = list.length; }
    if (!kind) return { kind: null, shape: null, rows: 0 };
    const st = (get('show') || {}).stage;
    let shape = 'big';
    if (HIDE_STAGES.includes(st)) shape = null;
    else if (THIN_STAGES.includes(st)) shape = 'thin';
    else if (kind === 'hell' && st === 'quiz' && rows > QUIZ_BIG_MAX) shape = 'thin';
    else if (kind === 'home' && homeHitsBelow(get, st, rows)) shape = 'thin';
    return { kind, shape, rows };
}

/** 점수판 자리를 지금 퇴근빵 · 지옥탈출 판이 쓰고 있나(계좌 · 안내 전광판이 머리 줄로 비킨다) */
export function raceAway(get) {
    return !!raceView(get).shape;
}
