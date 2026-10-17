// 🚦 가운데 차례 규칙(v2/web/overlay/turns.js) — node 로 순수 함수만 본다. v2/tests/test_ovcard.py 가 부른다.
// 하나라도 틀리면 throw → 종료 코드 1. 끝까지 오면 'ok' 와 본 개수를 찍는다.
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const web = path.resolve(here, '..', '..', 'web', 'overlay');
const T = await import(new URL('file://' + path.join(web, 'turns.js').replace(/\\/g, '/')).href);
const L = await import(new URL('file://' + path.join(web, 'layers.js').replace(/\\/g, '/')).href);

let n = 0;
function eq(a, b, what) {
    n++;
    const A = JSON.stringify(a), B = JSON.stringify(b);
    if (A !== B) throw new Error(what + ' — 기대 ' + B + ' · 실제 ' + A);
}

// ① 후원 카드 ↔ 시그니처 차례
const ct = T.cardTurn;
eq(ct({ busy: true, queued: 3, sigCenter: true, sigWants: true }), 'wait', '카드가 떠 있으면 무엇보다 먼저 기다린다');
eq(ct({ busy: false, queued: 3, sigCenter: true, sigWants: false }), 'center', '시그가 가운데 — 카드가 깔리지 않게 기다린다');
eq(ct({ busy: false, queued: 0, sigCenter: true }), 'center', '줄이 비어도 가운데면 center(손댈 것 없음)');
eq(ct({ busy: false, queued: 2, sigCenter: false, sigWants: true }), 'yield', '시그가 기다리면 새 카드보다 먼저 넘긴다(밀림 방지)');
eq(ct({ busy: false, queued: 0, sigCenter: false, sigWants: true }), 'yield', '줄이 비어도 기다리는 시그에 넘긴다');
eq(ct({ busy: false, queued: 2, sigCenter: false, sigWants: false }), 'show', '시그가 없으면 카드');
eq(ct({ busy: false, queued: 0 }), 'idle', '아무것도 없으면 idle');
eq(ct(null), 'idle', '빈 값');

// 교착이 없다 — '카드가 시그를 기다림(center)' 과 '시그가 카드를 기다림(wants)' 은 같이 참일 수 없다(시그 쪽 정의로 보장).
// 여기서는 규칙 쪽: sigCenter 와 sigWants 가 동시에 와도 center 가 이기고, busy 일 때는 늘 wait(카드는 2.45초 안에 내려간다)
eq(ct({ busy: false, queued: 1, sigCenter: true, sigWants: true }), 'center', '둘 다 와도 center');

// 가운데 붙잡는 시간 = 줄어드는 때 · 배너 · 경보 중 가장 늦은 것
eq(T.centerHoldMs(2500, 0, 0), 2500, '기본 — 줄어드는 때(2.5초)');
eq(T.centerHoldMs(2500, 3500, 0), 3500, "'OO업' 배너 3.5초가 더 길다");
eq(T.centerHoldMs(2500, 4000, 0), 4000, '계엄령 경보 4초');
eq(T.centerHoldMs(8120, 0, 0), 8120, '전용 연출이 줄어들기를 미루면 그만큼');
eq(T.centerHoldMs(NaN, -1, undefined), 0, '이상한 값은 0');

// 시그가 시작할 수 있나(카드 사정 빼고)
eq(T.sigDue({ play_after: 0 }, { paused: false }, 1000, false), true, '바로');
eq(T.sigDue({ play_after: 5000 }, {}, 4999, false), false, 'play_after 전');
eq(T.sigDue({ play_after: 5000 }, {}, 5000, false), true, 'play_after 지남');
eq(T.sigDue({ play_after: 0 }, { paused: true }, 1000, false), false, '멈춤');
eq(T.sigDue({ play_after: 0 }, {}, 1000, true), false, '이미 다 틀고 서버가 빼기를 기다림');
eq(T.sigDue(null, {}, 1000, false), false, '맨 앞 없음');

// ② 다시 붙었을 때 지난 카드
const now = 100000;
const list = [
    { id: 'a', at: now - 40000 },                 // 30초 넘음
    { id: 'b', at: now - 20000 },                 // 이미 봄
    { id: 'c', at: now - 15000, sig: true },      // 시그 걸림
    { id: 'd', at: now - 10000 },
    { id: 'e', at: now - 1000 },
    { id: 'e', at: now - 1000 },                  // 같은 id 두 번
    null, 'x',
];
const r = T.pendingCards(list, new Set(['b']), now, 30000);
eq(r.fresh.map(d => d.id), ['d', 'e'], '안 본 것 · 30초 안 · 시그 아닌 것만 오래된 순');
eq(r.keys, ['a', 'b', 'c', 'd', 'e'], '본 열쇠는 전부(30초 넘은 것 · 시그도 — 다음에 또 안 띄우게)');
eq(T.pendingCards(undefined, null, now, 30000), { fresh: [], keys: [] }, '빈 목록');
eq(T.pendingCards([{ at: now - 5 }], new Set(), now, 30000).fresh.length, 1, 'id 없는 옛 팝업은 at 으로');
eq(T.cardKey({ id: 'don_1', at: 5 }), 'don_1', '열쇠 = id');
eq(T.cardKey({ at: 5 }), '5', 'id 없으면 at');

// ③ 출연진 전광판
const ds = T.sigDispShow;
eq(ds({ id: 'r', play_after: 0 }, {}, 1000, 0), false, '신호 없고 기다리기 시작 전 — 안 뜬다(옛 것은 곧바로 떴다)');
eq(ds({ id: 'r', play_after: 0, started: { replay: 0, at: 1 } }, {}, 1000, 0), true, '방송판이 시작했다 — 뜬다');
eq(ds({ id: 'r', replay: 1, started: { replay: 0, at: 1 } }, {}, 1000, 0), false, '다 틀기 다음 회차 — 앞 회차 신호로는 안 뜬다');
eq(ds({ id: 'r', replay: 1, started: { replay: 1, at: 1 } }, { paused: true }, 1000, 0), true, '이미 시작한 것은 멈춤이어도 끝까지(방송판과 같다)');
eq(ds({ id: 'r', play_after: 0 }, { paused: true }, 999999, 1), false, '멈춤 — 신호 없이 안 뜬다');
eq(ds({ id: 'r', play_after: 50000 }, {}, 40000, 1), false, 'play_after 전(슬롯 · 주사위 결과 미리 안 보임)');
eq(ds({ id: 'r', play_after: 0 }, {}, 1000 + T.STARTED_GRACE_MS - 1, 1000), false, '신호 기다림 한도 전');
eq(ds({ id: 'r', play_after: 0 }, {}, 1000 + T.STARTED_GRACE_MS, 1000), true, '한도가 지나면 신호 없이도(옛 방송판 · 방송판 꺼짐)');
eq(ds(null, {}, 1, 1), false, '맨 앞 없음');

// 층 순서는 그대로 — 카드(40) < 시그니처(50). 가리지 않게 하는 것은 차례 규칙이다(층을 바꾸면 시그 카드가 후원 카드 밑에 깔린다)
const z = id => (L.LAYERS.find(x => x.id === id) || {}).z;
eq(z('donation') < z('signature'), true, '층: 후원 카드 < 시그니처');

console.log('ok ' + n);
