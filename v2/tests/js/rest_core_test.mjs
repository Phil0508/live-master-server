// ☕ 휴식 모드 계산(v2/web/controller/js/restcore.js) — node 로 화면 없이 돌린다.
// 부르는 법: node rest_core_test.mjs <restcore.mjs 경로>   (v2/tests/test_rest_mode.py 가 .mjs 로 복사해 넘긴다)
// 답: 줄마다 'OK 이름' · 'BAD 이름 -- 까닭', 끝에 'DONE n'
import { pathToFileURL } from 'node:url';

const M = await import(pathToFileURL(process.argv[2]).href);
let n = 0;
function chk(name, cond, detail) {
    n++;
    console.log((cond ? 'OK ' : 'BAD ') + name + (cond ? '' : ' -- ' + JSON.stringify(detail === undefined ? null : detail)));
}
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// ── 기억(localStorage) — 못 읽으면 끔 ──
const mem = () => { const m = {}; return { getItem: k => (k in m ? m[k] : null), setItem: (k, v) => { m[k] = String(v); } }; };
const boom = { getItem() { throw new Error('막힘'); }, setItem() { throw new Error('막힘'); } };
let s = mem();
chk('처음엔 끔', M.readRest(s) === false);
chk('켬 기억', M.writeRest(s, true) === true && M.readRest(s) === true);
chk('끔 기억', M.writeRest(s, false) === true && M.readRest(s) === false);
chk('막힌 저장소 — 읽기는 끔 · 쓰기는 false(던지지 않음)', M.readRest(boom) === false && M.writeRest(boom, true) === false);
chk('저장소 없음 — 끔', M.readRest(null) === false && M.readRest(undefined) === false);

// ── 카드 줄 — 실명은 안 쓴다 ──
let l = M.bankLine({ id: 'b1', amount: 30000, name: '영원', holder: '김진짜', how: 'known', message: '밍밍화이팅' });
chk('입금 줄: 금액 · 추정 닉네임', l.title === '🏦 계좌 입금 30,000원 · 영원(추정)' && l.kind === 'bank' && l.id === 'bank:b1', l);
chk('입금 줄: 실명(holder) · 메시지 안 씀', !JSON.stringify(l).includes('김진짜') && !JSON.stringify(l).includes('밍밍화이팅'), l);
l = M.bankLine({ id: 'b2', amount: 50000, name: '홍길동', holder: '홍길동', how: 'no_memo' });
chk('메모 없이 보냄(이름 = 예금주) → 이름 빼고 금액만', l.title === '🏦 계좌 입금 50,000원' && !JSON.stringify(l).includes('홍길동'), l);
l = M.bankLine({ id: 'b3', amount: 10000, name: '김철수', holder: '', how: 'name_only' });
chk('이름만(실명일 수 있음) → 이름 뺌', l.title === '🏦 계좌 입금 10,000원', l);
l = M.bankLine({ id: 'b4', amount: 10000, name: '김 철수', holder: '김철수', how: 'first' });
chk('이름이 예금주와 같으면(띄어쓰기 달라도) 뺌', l.title === '🏦 계좌 입금 10,000원', l);
chk('금액 없음 → 0원', M.bankLine({ id: 'x' }).title === '🏦 계좌 입금 0원');
l = M.holdLine({ id: 'p9', name: '영원', amount: 1004, auto: { hold: ['금액이 애매해요(1,004원)'] } });
chk('보류 줄: 닉네임 · 금액 · 까닭', l.title === '🙋 확인할 후원 · 영원 1,004원' && l.sub === '보류 까닭: 금액이 애매해요(1,004원)' && l.id === 'hold:p9', l);
chk('보류 줄: 이름 없으면 익명', M.holdLine({ id: 'p1', amount: 5000 }).title === '🙋 확인할 후원 · 익명 5,000원');

// ── 새 입금 고르기 ──
let r = M.bankTrack(null, { new: 2, newest: { id: 'a', at: 100, amount: 1000, name: '가' } });
chk('처음 읽을 땐 알리지 않음', r.add === 0 && r.line === null && r.st.at === 100 && r.st.n === 2, r);
let t = M.bankTrack(r.st, { new: 2, newest: { id: 'a', at: 100 } });
chk('같은 카드면 조용', t.add === 0, t);
t = M.bankTrack(t.st, { new: 3, newest: { id: 'b', at: 120, amount: 30000, name: '영원', how: 'known' } });
chk('새 카드 → 1건', t.add === 1 && t.line.title === '🏦 계좌 입금 30,000원 · 영원(추정)', t);
let t2 = M.bankTrack(t.st, { new: 2, newest: { id: 'a', at: 100 } });
chk('맨 위 카드를 처리해 밑 카드가 올라와도 새 입금 아님', t2.add === 0, t2);
t2 = M.bankTrack(t2.st, { new: 5, newest: { id: 'd', at: 200, amount: 1000 } });
chk('한 번에 여러 건(미처리 2 → 5) → 3건', t2.add === 3, t2);
t2 = M.bankTrack(t2.st, { new: 1, newest: { id: 'e', at: 300, amount: 1000 } });
chk('처리하면서 새로 와 미처리가 줄어도 최소 1건', t2.add === 1, t2);
t2 = M.bankTrack(t2.st, { new: 0, newest: null });
chk('미처리 0 → 조용', t2.add === 0 && t2.st.at === 300, t2);
t2 = M.bankTrack(t2.st, { new: 1, newest: { id: 'c', at: 110 } });
chk('숨긴 것을 되살림(예전 시각) → 새 입금 아님', t2.add === 0, t2);
r = M.bankTrack(null, { new: 0, newest: null });
t = M.bankTrack(r.st, { new: 1, newest: { id: 'z', at: 50, amount: 2000 } });
chk('빈 상태에서 첫 입금 → 1건', t.add === 1, t);

// ── 새 보류 고르기 ──
let h = M.holdTrack(null, [{ id: 'p1' }]);
chk('처음 본 보류는 알리지 않음', h.fresh.length === 0 && eq(h.seen, ['p1']), h);
h = M.holdTrack(h.seen, [{ id: 'p1' }, { id: 'p2' }]);
chk('새 보류 하나', h.fresh.length === 1 && h.fresh[0].id === 'p2', h);
h = M.holdTrack(h.seen, [{ id: 'p2' }]);
chk('처리돼 빠지면 조용', h.fresh.length === 0 && eq(h.seen, ['p2']), h);
h = M.holdTrack(h.seen, [{ id: 'p2' }, { id: 'p1' }]);
chk('빠졌던 번호가 다시 보류 → 다시 알림', h.fresh.length === 1 && h.fresh[0].id === 'p1', h);

// ── 쌓기 · 글자 ──
let a = M.emptyAlert();
chk('빈 알림 — 탭 제목 그대로', M.titleText(a, '조종실', true) === '조종실');
a = M.pushAlert(a, M.bankLine({ id: 'b1', amount: 30000, name: '영원', how: 'known' }), 1);
chk('입금 1건 탭 제목(켬)', M.titleText(a, '조종실 · 라이브 마스터', true) === '🔔 입금 1건 · 조종실 · 라이브 마스터', M.titleText(a, '조종실 · 라이브 마스터', true));
chk('입금 1건 탭 제목(번갈아 — 원래)', M.titleText(a, '조종실', false) === '조종실');
let v = M.cardView(a);
chk('카드 한 건: 큰 글자 · 줄 없음', v.title === '🏦 계좌 입금 30,000원 · 영원(추정)' && v.head === '🔔 새 알림' && v.rest.length === 0 && v.left === 0, v);
a = M.pushAlert(a, M.bankLine({ id: 'b2', amount: 10000, name: '밍밍', how: 'known' }), 2);
a = M.pushAlert(a, M.holdLine({ id: 'p1', name: '별', amount: 1004, auto: { hold: ['애매'] } }), 1);
chk('건수 누적: 입금 3 · 보류 1', a.bank === 3 && a.hold === 1, a);
chk('탭 제목 두 가지', M.titleText(a, 'X', true) === '🔔 입금 3건 · 확인할 후원 1건 · X');
v = M.cardView(a);
chk('카드 여러 건: 가장 최근이 크게 · 나머지 줄', v.title.startsWith('🙋 확인할 후원 · 별') && v.rest.length === 2 && v.head === '🔔 새 알림 4건 — 입금 3건 · 확인할 후원 1건', v);
a = M.pushAlert(a, M.bankLine({ id: 'b2', amount: 10000, name: '밍밍', how: 'known' }), 1);
chk('같은 입금이 또 오면 줄은 하나(맨 앞으로) · 건수는 쌓임', a.lines.length === 3 && a.lines[0].id === 'bank:b2' && a.bank === 4, a);
for (let i = 0; i < 8; i++) a = M.pushAlert(a, M.bankLine({ id: 'm' + i, amount: 1000 }), 1);
v = M.cardView(a);
chk('줄이 많으면 4줄 + 외 N건', v.rest.length === M.MAX_LINES - 1 && v.left === a.lines.length - 1 - (M.MAX_LINES - 1), v);

console.log('DONE ' + n);
