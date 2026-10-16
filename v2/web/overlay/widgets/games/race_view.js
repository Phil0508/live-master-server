/* 🏃🔥 퇴근빵 · 지옥탈출 — 지금 방송판에 어느 판을 어떤 모양으로 둘지. 서버 조각만 보고 정한다(화면은 안 만진다 → node 로 검사).

   10-17(w2races) — 두 판은 무대(show.stage, 한 번에 하나)가 아니라 **늘 붙는 칸**이다. 다른 게임을 켜도 안 꺼진다.
   kind   'hell' | 'home' | null
          지옥 = hell.on 이고 hell.shown(값이 없는 옛 저장본은 보임) · 퇴근 = home.on. 둘 다 켜져 있으면 지옥이 먼저(대표님 10-17)
          — 퇴근빵은 숨기만 하고 셈 · 카드는 서버에서 계속 돈다.
   shape  'big'  점수판 자리 큰 판(지금 모습) — 무대가 비었거나 대결 · 룰렛 · 슬롯 · 퀴즈일 때
                 (룰렛 · 슬롯은 몇 초 동안 위에 덮인다 — 층이 판(13) < 게임판(15)이라 게임판이 늘 위)
          'thin' 얇은 판(제목 + 한 사람씩 5초마다 도는 한 줄, 167~290) — 시그뒤집기(340~) · 핀볼(300~) 이 같은 자리 아래를 쓸 때,
                 퀴즈 중 9명 이상(큰 판 아래끝이 퀴즈 네모칸 700 에 닿는다)
          null   숨김 — 주사위판 동안(주사위판 + 점수 띠가 안전지대를 거의 다 쓴다 · 대표님 10-17 '숨긴다')
   시그니처가 나오는 동안 숨는 것은 층 표(hideInReaction)가, 시작 · 끝 화면은 위젯(coverOn)이 맡는다. */

export const HIDE_STAGES = ['dicegame'];
export const THIN_STAGES = ['siggame', 'pinball'];
export const QUIZ_BIG_MAX = 8;

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
    else if (THIN_STAGES.includes(st) || (st === 'quiz' && rows > QUIZ_BIG_MAX)) shape = 'thin';
    return { kind, shape, rows };
}

/** 점수판 자리를 지금 퇴근빵 · 지옥탈출 판이 쓰고 있나(계좌 · 안내 전광판이 머리 줄로 비킨다) */
export function raceAway(get) {
    return !!raceView(get).shape;
}
