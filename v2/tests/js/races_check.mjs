// 🏃🔥 퇴근빵 · 지옥탈출 방송판 규칙 — node 로 순수 함수 · 층 표만 본다(화면 없이). v2/tests/test_races.py 가 부른다.
// 하나라도 틀리면 throw → 종료 코드 1. 끝까지 오면 'ok' 와 본 개수를 찍는다.
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const web = path.resolve(here, '..', '..', 'web', 'overlay');
const imp = rel => import(new URL('file://' + path.join(web, rel).replace(/\\/g, '/')).href);

const V = await imp('widgets/games/race_view.js');
const A = await imp('widgets/basics2/account.js');
const L = await imp('layers.js');

let n = 0;
function eq(a, b, what) {
    n++;
    const x = JSON.stringify(a), y = JSON.stringify(b);
    if (x !== y) throw new Error(what + ' — 기대 ' + y + ' · 실제 ' + x);
}

const players = { list: [{ name: '하율', score: 9 }, { name: '서아', score: 3 }, { name: '채원', score: 0 }] };
const hellOn = { on: true, shown: true, goals: { 하율: 50, 서아: 40, 채원: 30 }, base: {} };
const S = (o) => k => Object.assign({ players, show: { stage: null }, hell: {}, home: {} }, o)[k];
const view = o => { const v = V.raceView(S(o)); return [v.kind, v.shape]; };

// 1) 무엇이 보이나 — 무대가 아니라 스위치
eq(view({}), [null, null], '둘 다 꺼짐');
eq(view({ home: { on: true } }), ['home', 'big'], '퇴근빵 켜짐 → 큰 판');
eq(view({ hell: hellOn }), ['hell', 'big'], '지옥 진행 · 보임');
eq(view({ hell: Object.assign({}, hellOn, { shown: false }) }), [null, null], '지옥 숨김');
eq(view({ hell: Object.assign({}, hellOn, { shown: undefined }) }), ['hell', 'big'], 'shown 이 없는 옛 저장본은 보임');
eq(view({ hell: Object.assign({}, hellOn, { on: false }) }), [null, null], '끝낸 지옥은 안 보임');
eq(view({ hell: hellOn, home: { on: true } }), ['hell', 'big'], '둘 다 켜지면 지옥이 먼저(대표님 10-17)');
eq(view({ hell: Object.assign({}, hellOn, { shown: false }), home: { on: true } }), ['home', 'big'], '지옥을 숨기면 퇴근빵이 보인다');
eq(view({ home: { on: true }, players: { list: [] } }), [null, null], '선수가 없으면 안 보임');

// 2) 무대에 무엇이 오든 안 꺼진다 — 모양만 바뀐다
for (const st of ['match', 'roulette', 'slot', 'quiz', null]) eq(view({ hell: hellOn, show: { stage: st } }), ['hell', 'big'], st + ' 무대 → 큰 판');
for (const st of ['siggame', 'pinball']) eq(view({ hell: hellOn, show: { stage: st } }), ['hell', 'thin'], st + ' 무대 → 얇은 판');
eq(view({ home: { on: true }, show: { stage: 'dicegame' } }), ['home', null], '주사위판 동안은 숨김(대표님 10-17)');
const nine = { list: Array.from({ length: 9 }, (_, i) => ({ name: 'p' + i, score: 0 })) };
eq(view({ home: { on: true }, players: nine, show: { stage: 'quiz' } }), ['home', 'thin'], '퀴즈 + 9명 → 얇은 판(네모칸 700 에 안 닿게)');
eq(view({ home: { on: true }, players: nine, show: { stage: null } }), ['home', 'big'], '퀴즈가 아니면 9명도 큰 판');

// 2-1) 퇴근빵은 GOAL 줄만큼 길다 — 퀴즈(700) · 대결판(795) 위끝에 닿으면 얇은 판(10-17 연습 서버에서 잰 아래끝 6명 695 · 7명 755 · 8명 815)
const many = k => ({ list: Array.from({ length: k }, (_, i) => ({ name: 'p' + i, score: 0 })) });
const hellOf = k => ({ on: true, shown: true, goals: Object.fromEntries(Array.from({ length: k }, (_, i) => ['p' + i, 10])), base: {} });
eq([6, 7, 8].map(k => V.homeBottom(k)), [695, 755, 815], '퇴근빵 큰 판 아래끝(잰 값)');
for (const [k, st, want] of [[6, 'quiz', 'big'], [7, 'quiz', 'thin'], [8, 'quiz', 'thin'], [10, 'quiz', 'thin'],
                             [6, 'match', 'big'], [7, 'match', 'big'], [8, 'match', 'thin'], [10, 'match', 'thin'],
                             [10, null, 'big'], [10, 'roulette', 'big'], [10, 'slot', 'big']]) {
    eq(view({ home: { on: true }, players: many(k), show: { stage: st } }), ['home', want], '퇴근빵 ' + k + '명 + ' + st);
}
// 지옥탈출은 그대로 — 퀴즈 중 8명까지 큰 판, 대결 중엔 몇 명이든 큰 판
for (const [k, st, want] of [[8, 'quiz', 'big'], [9, 'quiz', 'thin'], [10, 'match', 'big']]) {
    eq(view({ hell: hellOf(k), players: many(k), show: { stage: st } }), ['hell', want], '지옥 ' + k + '명 + ' + st);
}
// 편집기에서 옮긴 자리를 따른다 — 퀴즈를 아래(900)로 내리면 8명도 큰 판 · 퇴근빵을 0.8배로 줄이면 7명 + 퀴즈도 큰 판
eq(view({ home: { on: true }, players: many(8), show: { stage: 'quiz' }, layout: { widgets: { quiz: { y: 900 } } } }), ['home', 'big'], '퀴즈를 내리면 큰 판');
eq(view({ home: { on: true }, players: many(7), show: { stage: 'quiz' }, layout: { widgets: { homeRace: { scale: 0.8 } } } }), ['home', 'big'], '퇴근빵을 줄이면 큰 판');
eq(view({ home: { on: true }, players: many(6), show: { stage: 'match' }, layout: { widgets: { match: { y: 600 } } } }), ['home', 'thin'], '대결판을 올리면 6명도 얇은 판');
// 기본 위끝이 층 표와 같은지(표를 고치면 여기 숫자도)
const byId = Object.fromEntries(L.LAYERS.map(x => [x.id, x]));
eq([byId.quiz.y, byId.match.y, byId.homeRace.y], [V.BELOW.quiz.y, V.BELOW.match.y, 167], '퀴즈 · 대결 · 퇴근빵 기본 자리 = 층 표');

// 3) 계좌 · 안내 전광판이 비키는 조건 — 지옥 판이 떠 있어도 비킨다(옛 75644ae 의 겹침)
eq(A.AWAY_STAGES.includes('home_race') || A.AWAY_STAGES.includes('hell'), false, '무대 목록에 옛 이름이 없다');
const lm = o => ({ get: S(o) });
eq(A.accountAway(lm({ hell: hellOn })), true, '지옥 판이 뜨면 계좌는 머리 줄');
eq(A.accountAway(lm({ home: { on: true } })), true, '퇴근빵 판이 뜨면 계좌는 머리 줄');
eq(A.accountAway(lm({ hell: Object.assign({}, hellOn, { shown: false }) })), false, '숨긴 지옥이면 제자리');
eq(A.accountAway(lm({ show: { stage: 'dicegame' } })), true, '주사위 무대는 그대로 머리 줄');
eq(A.AWAY_SLICES.includes('hell') && A.AWAY_SLICES.includes('home'), true, '지옥 · 퇴근이 바뀌어도 다시 본다');

// 4) 층 — 늘 붙는 판(13)은 게임판(15) · 룰렛 어둡게(14)보다 아래, 후원 순위(12)보다 위
const by = Object.fromEntries(L.LAYERS.map(x => [x.id, x]));
for (const id of ['homeRace', 'hell']) {
    eq(by[id].z, 13, id + ' 층 13');
    for (const g of ['match', 'siggame', 'dicegame', 'dgscore']) eq(by[id].z < by[g].z, true, id + ' 이(가) ' + g + ' 보다 아래');
    eq(by[id].hideInReaction, true, id + ' 시그니처 동안 숨김(대표님 10-17 지금처럼)');
    eq(by[id].liveOnly, true, id + ' 방송 중에만');
}
if (by.donorRank) eq(by.donorRank.z < by.hell.z, true, '후원 순위는 지옥 판 아래');

console.log('ok', n);
