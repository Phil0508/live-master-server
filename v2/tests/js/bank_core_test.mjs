// 🏦 조종실 계좌 입금 계산(v2/web/controller/js/bankcore.js) — node 로 화면 없이 돌린다.
// 부르는 법: node bank_core_test.mjs <bankcore.mjs 경로>   (v2/tests/test_bank_js.py 가 .mjs 로 복사해 넘긴다)
// 답: 줄마다 'OK 이름' · 'BAD 이름 -- 까닭', 끝에 'DONE n'
import { pathToFileURL } from 'node:url';

const M = await import(pathToFileURL(process.argv[2]).href);
let n = 0;
function chk(name, cond, detail) {
    n++;
    console.log((cond ? 'OK ' : 'BAD ') + name + (cond ? '' : ' -- ' + JSON.stringify(detail === undefined ? null : detail)));
}
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// ── 시각 글자 ──
chk('방금 · 초 · 분 · 시간', eq([0, 9, 10, 59, 60, 3599, 3600, 7300].map(M.bankAgo), ['방금', '방금', '10초 전', '59초 전', '1분 전', '59분 전', '1시간 전', '2시간 전']));
chk('은행 시각 → HH:MM', M.bankClock({ when: '2026.10.14 19:01:02' }) === '19:01' && M.bankClock({ when: '9:05' }) === '09:05' && M.bankClock({}) === '');

// ── 카드 ──
const now = 1760000000;
let v = M.cardView({ id: 'b1', amount: 50000, when: '2026.10.14 19:01:02', at: now - 125, memo: '영원밍밍화이팅', holder: '김진짜', name: '영원',
    message: '밍밍화이팅', how: 'known', sure: true, target: '밍밍', target_why: "메시지에 '밍밍' 이 있음", ai: 'done', source: 'web' }, now);
chk('카드: 금액 · 시각 · 몇 분 전', v.amount === 50000 && v.clock === '19:01' && v.ago === '2분 전' && !v.phone, v);
chk('카드: 예상 딱지 → 밍밍 ＋? 예상 (까닭은 마우스 글)', v.target && v.target.text === '→ 밍밍 ＋? 예상' && v.target.title.includes('밍밍'), v.target);
chk('카드: 메모 원문 · 예금주(닉네임과 다를 때만)', v.raw === '메모 원문: 영원밍밍화이팅 · 예금주 김진짜', v.raw);
chk('카드: 나눈 방법 딱지', v.how && v.how.text === '✓ 예전 닉네임' && v.how.cls === 'ok');
v = M.cardView({ id: 'b2', amount: 30000, at: now, memo: '홍길동', holder: '홍길동', name: '홍길동', message: '', how: 'no_memo', ai: 'pending', source: 'phone' }, now);
chk('카드: 메시지 없으면 예상 중… 도 안 띄운다 · 예금주가 이름과 같으면 안 적는다 · 폰', v.target === null && v.raw === '메모 원문: 홍길동' && v.phone, v);
v = M.cardView({ id: 'b3', amount: 1, at: now, memo: '테스트 안녕', name: '테스트', message: '안녕', how: 'first', ai: 'pending' }, now);
chk('카드: 예상이 아직이면 예상 중…', v.target && v.target.text === '예상 중…' && v.how.cls === 'warn');
chk('카드: 모르는 how 는 딱지 없음', M.cardView({ how: 'zzz', at: now }, now).how === null);
// 📚 10-17 새 순서의 까닭 딱지 — 배운 짝 · 지난 기록은 초록(믿어도 됨), 선수 이름 떼기는 노랑(확인)
v = M.cardView({ id: 'b4', amount: 20000, at: now, memo: '고마워요', holder: '김가짜', name: '달토끼', message: '고마워요', how: 'learned', sure: true, ai: 'done' }, now);
chk('카드: 배운 짝 딱지', v.how && v.how.text === '✓ 배운 짝' && v.how.cls === 'ok', v.how);
v = M.cardView({ id: 'b5', amount: 20000, at: now, memo: '하루밍밍화이팅', name: '하루', message: '화이팅', how: 'known_name', sure: true,
    target: '밍밍', target_why: '메모에 선수 이름', ai: 'done' }, now);
chk('카드: 지난 기록 딱지 · 메모의 선수 → 예상', v.how.text === '✓ 지난 기록' && v.how.cls === 'ok' && v.target.text === '→ 밍밍 ＋? 예상'
    && v.target.title === '메모에 선수 이름', v);
v = M.cardView({ id: 'b6', amount: 20000, at: now, memo: '달별밍밍화이팅', name: '달별', message: '화이팅', how: 'player_strip', target: '밍밍', ai: 'done' }, now);
chk('카드: 선수 이름 떼기 딱지는 확인(노랑)', v.how.cls === 'warn' && v.how.text.includes('선수 이름'), v.how);

// ── 후원 콘솔 머리 연결 칩 ──
chk('연결 칩: 열쇠 없음', M.linkChip({ key_set: false, link: {} }).text.startsWith('은행 확장 연결 전'));
chk('연결 칩: 소식 없음', M.linkChip({ key_set: true, link: {} }).text === '은행 확장 소식 없음');
let c = M.linkChip({ key_set: true, link: { web: { age_sec: 200, note: '' }, phone: { age_sec: 12, note: '폰 알림 켬' } } });
chk('연결 칩: 더 최근 쪽(폰) · 메모', c.cls === 'ok' && c.text === '은행 확장 연결됨 · 12초 전 · 폰 알림 켬', c);
c = M.linkChip({ key_set: true, link: { web: { age_sec: 95, note: '' } } });
chk('연결 칩: 90초 넘으면 끊김(노랑)', c.cls === 'stale' && c.text === '은행 확장 소식 끊김 · 마지막 1분 전', c);

// ── 🪞 거울 판단 · 머리줄 칩 · 띠 ──
const ms = 1760000000000;
const ext = (age, state, extra) => Object.assign({ key_set: true, new: 2, link: { web: { age_sec: age, note: '', state } } }, extra || {});
let j = M.judgeExt(null, ms);
chk('판단: 읽기 전 = 연결 전(칩 숨김)', j.k === 'none' && M.chipView(j, 0).hidden);
j = M.judgeExt({ key_set: true, link: {} }, ms);
chk('판단: 확장 소식 없음 = 칩 숨김', j.k === 'none' && M.chipView(j, 3).hidden);
j = M.judgeExt(ext(4 * 3600, { enabled: true }), ms);
chk('판단: 3시간 넘게 조용 = 꺼짐(칩 숨김 · 띠 없음)', j.k === 'off' && M.chipView(j, 1).hidden && M.deadBand(j) === null);
j = M.judgeExt(ext(120, { enabled: true, cls: 'ok' }), ms);
chk('판단: 신호 90초 넘게 없음 = 끊김 · 빨간 띠', j.k === 'dead' && j.dead && M.extLevel(j) === 'bad' && M.deadBand(j).t === '⚠ 은행 확장 끊김 · 신호 없음 2분 — 계좌 입금을 못 받고 있어요', M.deadBand(j));
const cv = M.chipView(j, 3);
chk('칩: 끊김은 색으로만 — 숫자를 안 붙인다', !cv.hidden && cv.lv === 'bad' && cv.text === '계좌' && cv.title.includes('미처리 3건'), cv);
j = M.judgeExt(ext(10, { enabled: true, dead: true, status: '은행 로그아웃됨', lastOkAt: new Date(2026, 9, 14, 18, 5).getTime() }), ms);
chk('판단: 확장이 스스로 끊김(로그아웃) 보고', j.k === 'dead' && j.t1 === '은행 로그아웃됨' && j.t2.endsWith('마지막 정상 18:05'), j);
j = M.judgeExt(ext(10, { enabled: false, status: '' }), ms);
chk('판단: 자동 조회 꺼짐 = 회색 점', j.k === 'idle' && M.extLevel(j) === 'none' && !M.chipView(j, 0).hidden && j.t1 === '자동 조회 꺼짐');
j = M.judgeExt(ext(10, { enabled: true, cls: 'warn', status: '표를 못 찾음' }), ms);
chk('판단: 확장이 노랑으로 보고 = 주의', j.k === 'warn' && M.chipView(j, 0).lv === 'warn');
j = M.judgeExt(ext(12, { enabled: true, cls: 'ok', status: '자동 조회 중', clicks: 7, startedAt: ms - 75 * 60000 }), ms);
chk('판단: 정상 = 초록 · 조회 수 · 켜 둔 지', j.k === 'ok' && j.t2 === '신호 12초 전 · 조회 7번 · 켜 둔 지 1시간 15분', j);
chk('칩: 미처리 수를 붙인다', M.chipView(j, 2).text === '계좌 2' && M.chipView(j, 0).text === '계좌');

// 초록 띠
const nb = M.newBand({ amount: 50000, name: '영원', message: '밍밍화이팅' }, 3);
chk('초록 띠 글자', nb.t === '🏦 계좌 입금 50,000원 · 영원 「밍밍화이팅」' && nb.s === '미처리 3건 · 후원 콘솔에서 [채우기] → 송출', nb);
chk('초록 띠: 닉네임 없으면 예금주', M.newBand({ amount: 1000, name: '', holder: '김진짜' }, 1).t === '🏦 계좌 입금 1,000원 · 김진짜');
let k = M.newestCheck(null, 'b1');
chk('새 입금: 처음 읽을 땐 띄우지 않는다', k.known === 'b1' && !k.show);
k = M.newestCheck(k.known, 'b1');
chk('새 입금: 그대로면 안 띄운다', !k.show);
k = M.newestCheck(k.known, 'b2');
chk('새 입금: 가장 새 카드가 바뀌면 띄운다', k.show && k.known === 'b2');
k = M.newestCheck(k.known, undefined);
chk('새 입금: 다 처리해 비면 조용히', !k.show && k.known === 'b2');
k = M.newestCheck(null, undefined);
chk('새 입금: 처음부터 비어 있으면 그다음 첫 카드는 띄운다', !k.show && M.newestCheck(k.known, 'b9').show);

// 명령 · 기다림 · 경고
chk('명령: 켜기/끄기는 지금과 반대로', eq(M.extCmdBody('enable', null, { enabled: true }), { t: 'enable', source: 'web', on: false })
    && eq(M.extCmdBody('enable', null, {}), { t: 'enable', source: 'web', on: true }));
chk('명령: 간격은 숫자로', eq(M.extCmdBody('interval', '60', {}), { t: 'interval', source: 'web', sec: 60 }));
chk('기다리는 명령 글자', M.pendingText([{ t: 'enable' }, { t: 'press' }]) === '보낸 명령 기다리는 중: 켜기/끄기 · 지금 조회 — 확장이 25초 안에 받아요' && M.pendingText([]) === '');
chk('거울 경고: 날짜 칸 · 표 못 읽음', M.extWarns({ dateOk: false, rows: 0, diag: '표3 · 20칸' }, true).length === 2 && M.extWarns({ dateOk: true, rows: 8 }, true).length === 0);

// ── [채우기] → [송출] — '장부 기록' 체크를 원래대로 (옛 50878d1 사고) ──
let P = M.makePick();
let ledger = false;                                  // 재생만(장부 안 넣음)으로 쓰던 중
const set = r => { if (r !== null && r !== undefined) ledger = r; };
set(P.fill({ id: 'b1', amount: 50000 }, ledger));
chk('채우기: 장부 체크를 켠다', ledger === true && P.get().id === 'b1' && P.get().prevLedger === false);
set(P.release());                                    // 송출 끝
chk('송출 뒤: 장부 체크가 채우기 전(꺼짐)으로 — 다음 재생만 송출이 진짜 후원으로 안 들어간다', ledger === false && P.get() === null);
set(P.fill({ id: 'b1', amount: 50000 }, ledger));
set(P.fill({ id: 'b2', amount: 30000 }, ledger));   // 다른 카드로 다시 채움 — 그때 장부는 이미 켜져 있다
chk('두 번 채워도 처음 상태(꺼짐)를 기억한다', P.get().id === 'b2' && P.get().prevLedger === false && ledger === true);
set(P.releaseIf('b9'));
chk('다른 카드를 숨기면 그대로', ledger === true && P.get().id === 'b2');
set(P.releaseIf('b2'));
chk('채운 카드를 숨기면 되돌린다', ledger === false && P.get() === null);
set(P.fill({ id: 'b3', amount: 1000 }, ledger));
set(P.releaseIfGone(['b3', 'b4']));
chk('목록에 아직 있으면 그대로', ledger === true && P.get().id === 'b3');
set(P.releaseIfGone(['b4']));
chk('다른 화면에서 송출 · 숨김 — 목록에서 사라지면 되돌린다', ledger === false && P.get() === null);
ledger = true;                                       // 처음부터 장부에 넣던 중
set(P.fill({ id: 'b5', amount: 1000 }, ledger));
set(P.release());
chk('처음부터 켜 두었으면 켜진 채로', ledger === true);
chk('놓을 게 없으면 손대지 않는다(null)', P.release() === null && P.releaseIf('x') === null && P.releaseIfGone([]) === null);

// ── 송출 이름 · 장부 번호 · 탭 배지 ──
chk('송출 이름: 채웠는데 비우면 익명, 아니면 수동송출', M.sendName('  ', { id: 'b1' }) === '익명' && M.sendName('', null) === '수동송출' && M.sendName(' 영원 ', { id: 'b1' }) === '영원');
chk('장부 번호: 계좌 입금은 manual_bank_<입금번호> — 두 번 눌러도 장부엔 한 번', M.txBase({ id: 'b1a2' }, 123) === 'manual_bank_b1a2' && M.txBase(null, 123) === 'manual_123');
chk('탭 배지: 아직 안 쓴 입금 수', M.bankBadge({ bank: { new: 3 } }) === '🏦 3' && M.bankBadge({ bank: { new: 0 } }) === '' && M.bankBadge({}) === '');

console.log('DONE ' + n);
