// 🏦 bank-watch(엔젤 입금확인) — 표 읽는 규칙 검사. content.js 의 순수 도구를 그대로 부른다.
// 실행: node tests/bankwatch_test.js
const path = require('path');
const ROOT = process.env.LM_PROJECT_ROOT || path.join(__dirname, '..');
const W = require(path.join(ROOT, 'bank-watch', 'content.js'));
let ok = 0, bad = 0;
function chk(name, cond, detail) {
  if (cond) { ok++; console.log('  [OK] ' + name); }
  else { bad++; console.log('  [!!] ' + name + (detail !== undefined ? '  -- ' + JSON.stringify(detail).slice(0, 200) : '')); }
}

console.log('① 금액 읽기');
chk('"12,000" → 12000', W.toWon('12,000') === 12000);
chk('"+1,000원" → 1000', W.toWon('+1,000원') === 1000);
chk('빈칸 · "-" → 0', W.toWon('') === 0 && W.toWon('-') === 0 && W.toWon(null) === 0);

console.log('② 칸 제목으로 칸 찾기');
let m = W.colMap(['거래일시', '출금(원)', '입금(원)', '잔액(원)', '거래내용', '상대계좌예금주명', '거래구분']);
chk('입금 · 출금 · 잔액 · 날짜 칸', m.dep === 2 && m.wd === 1 && m.bal === 3 && m.date === 0, m);
chk('이름/내용 칸 둘(거래내용 · 예금주명)', JSON.stringify(m.memo) === '[4,5]', m.memo);
chk('구분 칸', m.kind === 6 && m.ok);
m = W.colMap(['거래일자', '거래시간', '찾으신금액', '맡기신금액', '거래후잔액', '기재내용', '입금자명']);
chk('옛 말투(찾으신 · 맡기신) · 날짜/시간 따로', m.wd === 2 && m.dep === 3 && m.bal === 4 && m.date === 0 && m.time === 1, m);
chk("'입금자명' 은 금액 칸이 아니라 이름 칸", m.memo.indexOf(6) >= 0 && m.dep === 3, m);
m = W.colMap(['거래일시', '구분', '거래금액', '잔액', '내용']);
chk('금액 하나 + 구분(입금/출금) 모양도 읽는다', m.ok && m.amt === 2 && m.kind === 1 && m.dep === -1, m);
chk('엉뚱한 표(금액 칸 없음)는 거래내역으로 안 본다', !W.colMap(['번호', '제목', '등록일']).ok);

console.log('③ 머리줄 칸 합치기');
const labels = W.gridLabels([
  [{ text: '거래일시', rowspan: 2 }, { text: '금액', colspan: 2 }, { text: '잔액', rowspan: 2 }, { text: '내용', rowspan: 2 }],
  [{ text: '출금' }, { text: '입금' }],
]);
chk('두 줄 머리 → 칸마다 하나의 제목', JSON.stringify(labels) === JSON.stringify(['거래일시', '금액 출금', '금액 입금', '잔액', '내용']), labels);
m = W.colMap(labels);
chk('합친 제목으로도 입금 · 출금을 가린다', m.dep === 2 && m.wd === 1, m);

console.log('④ 줄 읽기');
m = W.colMap(['거래일시', '출금(원)', '입금(원)', '잔액(원)', '거래내용', '상대계좌예금주명', '거래구분']);
let r = W.rowFrom(['2026.10.12 14:00:02', '', '1,000', '501,000', '테스트/안녕', '홍길동', '타행이체'], m);
chk('입금 1,000 · 메모 둘 · 시각', r.dep === 1000 && r.wd === 0 && r.memo.join('|') === '테스트/안녕|홍길동' && r.when === '2026.10.12 14:00:02', r);
r = W.rowFrom(['2026.10.12 14:00:03', '8,000', '', '493,000', '배달앱', '', '체크카드'], m);
chk('출금 줄은 입금 0', r.dep === 0 && r.wd === 8000, r);
const m2 = W.colMap(['거래일시', '구분', '거래금액', '잔액', '내용']);
chk('구분이 입금이면 거래금액이 입금', W.rowFrom(['2026.10.12 14:00', '입금', '5,000', '10,000', '김씨'], m2).dep === 5000);
chk('구분이 출금이면 입금 0', W.rowFrom(['2026.10.12 14:00', '출금', '5,000', '5,000', '마트'], m2).dep === 0);

console.log('⑤ 새 줄 고르기');
const mk = (cells) => W.keyRows(cells.map((c) => W.rowFrom(c, m)));
const base = mk([
  ['2026.10.12 09:10:11', '', '30,000', '530,000', '김예전', '김예전', '타행이체'],
  ['2026.10.12 08:01:02', '12,000', '', '500,000', '편의점', '', '체크카드'],
]);
let j = W.judge(base, {}, false);
chk('처음엔 기준만 잡고 아무것도 안 알린다(예전 입금이 쏟아지지 않게)', j.baseline === true && j.fresh.length === 0);
const seen = {}; base.forEach((x) => { seen[x.key] = 1; });
const next = mk([
  ['2026.10.12 14:00:02', '', '1,000', '531,000', '테스트/안녕', '홍길동', '타행이체'],
  ['2026.10.12 09:10:11', '', '30,000', '530,000', '김예전', '김예전', '타행이체'],
  ['2026.10.12 08:01:02', '12,000', '', '500,000', '편의점', '', '체크카드'],
]);
j = W.judge(next, seen, true);
chk('새로 생긴 한 줄만 고른다', j.fresh.length === 1 && j.fresh[0].dep === 1000, j);
const dup = mk([
  ['2026.10.12 14:00', '', '1,000', '', '홍길동', '', '이체'],
  ['2026.10.12 14:00', '', '1,000', '', '홍길동', '', '이체'],
]);
chk('잔액 칸이 없어 글자가 똑같은 두 줄도 서로 다른 줄로 센다', dup[0].key !== dup[1].key, dup.map((x) => x.key));
const other = mk([1, 2, 3, 4].map((i) => ['2026.09.0' + i + ' 10:00', '', '9,000', String(i), '딴계좌' + i, '', '이체']));
j = W.judge(other, seen, true);
chk('아는 줄이 하나도 없는 표(다른 계좌 · 기간)는 기준을 새로 잡고 안 알린다', j.rebase === true && j.fresh.length === 0, j);

console.log('⑥ 정렬');
chk('최근순이면 통과', W.newestFirst(next));
chk('오래된 순이면 알아챈다', !W.newestFirst(next.slice().reverse()));

console.log('\n통과 ' + ok + ' · 실패 ' + bad);
process.exit(bad ? 1 : 0);
