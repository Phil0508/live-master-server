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

console.log('⑦ 방송 서버로 보낼 모양(0.2)');
const L = ['거래일시', '출금(원)', '입금(원)', '잔액(원)', '거래내용', '상대계좌예금주명', '거래구분'];
const p = W.depPayload(j.fresh[0] || next[0], L, m);
chk('번호(ref) = 줄 지문 + 시각 + 금액(지문이 드물게 겹쳐도 다른 입금은 다른 번호)',
  p.ref === next[0].key + '@2026.10.12 14:00:02@1000' && p.amount === 1000 && p.when === '2026.10.12 14:00:02', p);
chk('이름/내용 칸은 [머리글, 값] — 서버가 메모 칸과 예금주 칸을 가른다',
  JSON.stringify(p.fields) === JSON.stringify([['거래내용', '테스트/안녕'], ['상대계좌예금주명', '홍길동']]), p.fields);
const e = W.depPayload(W.keyRows([W.rowFrom(['2026.10.12 15:00', '', '5,000', '1', '구름빵', '', '타행'], m)])[0], L, m);
chk('빈 칸은 안 보낸다(예금주 칸이 비었으면 메모 칸만)', JSON.stringify(e.fields) === JSON.stringify([['거래내용', '구름빵']]), e.fields);
chk('표 한 줄 전체(잔액 · 출금 칸 등)는 보내지 않는다', Object.keys(p).sort().join(',') === 'amount,fields,ref,when', Object.keys(p));

console.log('⑦-2 실제 표 (10-14 기업 인터넷뱅킹 kiup.ibk.co.kr 거래내역조회)');
{
  const KL = W.gridLabels([[{ text: '' }, { text: '' }, { text: '거래일시' }, { text: '출금' }, { text: '입금' }, { text: '거래후 잔액' }, { text: '거래내용' }, { text: '상대계좌번호' }, { text: '상대은행' }]]);
  const km = W.colMap(KL);
  chk('칸 찾기: 입금 · 출금 · 잔액 · 일시 · 거래내용', km.ok && KL[km.dep] === '입금' && KL[km.wd] === '출금' && KL[km.bal] === '거래후 잔액' && KL[km.date] === '거래일시' && km.memo.map((i) => KL[i])[0] === '거래내용', km);
  const rows = W.keyRows([
    ['1', '', '2026-10-14 16:34:54', '0', '1', '37,449,258', '스트밍밍플러', '', '하나은행'],
    ['2', '', '2026-10-14 15:08:56', '12,300', '0', '37,449,257', '카카오T일반택시(법인', '5298038078885977', ''],
    ['3', '', '2026-10-14 14:39:07', '0', '11,800', '37,461,557', '카카오T택시_가승인', '', ''],
    ['4', '', '2026-10-14 14:38:57', '11,800', '0', '37,449,757', '카카오T택시_가승인', '5298038078885977', ''],
    ['5', '', '2026-10-14 09:32:38', '1,990', '0', '37,461,557', '배민클럽_우아한형제', '5298038078885977', ''],
  ].map((c) => W.rowFrom(c, km)));
  const deps = rows.filter((r) => r.dep > 0 && !W.isRefund(r, rows));
  chk('입금은 스트밍밍플러 1원 하나만(카드 가승인 취소 11,800 은 뺀다)', deps.length === 1 && deps[0].dep === 1 && deps[0].memo[0] === '스트밍밍플러', deps.map((r) => r.dep + ' ' + r.memo[0]));
  const kp = W.depPayload(deps[0], KL, km);
  chk('보내는 칸: 거래내용 · 상대은행 (빈 상대계좌번호는 안 보냄)', JSON.stringify(kp.fields) === JSON.stringify([['거래내용', '스트밍밍플러'], ['상대은행', '하나은행']]), kp.fields);
  chk('같은 내용 · 같은 금액 출금이 있으면 환불로 본다', W.isRefund({ dep: 5000, memo: ['편의점'] }, [{ wd: 5000, memo: ['편의점'] }]));
  chk('금액이 다르면 후원으로 둔다', !W.isRefund({ dep: 5000, memo: ['편의점'] }, [{ wd: 4000, memo: ['편의점'] }]));
  chk('보통 후원 메모는 환불이 아니다', !W.isRefund({ dep: 10000, memo: ['영원 밍밍 화이팅'] }, rows));

  // 새 입금이 오면 맨 앞 번호 칸이 하나씩 밀린다 — 그래도 옛 줄은 '본 줄' 이어야 한다(10-14 1원을 놓친 원인)
  const seen0 = {}; rows.forEach((r) => { seen0[r.key] = 1; });
  const after = W.keyRows([
    ['1', '', '2026-10-14 16:58:10', '0', '1', '37,449,259', '스트밍밍플러', '', '하나은행'],
    ['2', '', '2026-10-14 16:34:54', '0', '1', '37,449,258', '스트밍밍플러', '', '하나은행'],
    ['3', '', '2026-10-14 15:08:56', '12,300', '0', '37,449,257', '카카오T일반택시(법인', '5298038078885977', ''],
    ['4', '', '2026-10-14 14:39:07', '0', '11,800', '37,461,557', '카카오T택시_가승인', '', ''],
    ['5', '', '2026-10-14 14:38:57', '11,800', '0', '37,449,757', '카카오T택시_가승인', '5298038078885977', ''],
    ['6', '', '2026-10-14 09:32:38', '1,990', '0', '37,461,557', '배민클럽_우아한형제', '5298038078885977', ''],
  ].map((c) => W.rowFrom(c, km)));
  const ja = W.judge(after, seen0, true);
  chk('번호가 밀려도 표를 갈아엎지 않는다(기준 새로 잡기 X)', !ja.rebase && !ja.baseline, ja);
  chk('번호가 밀려도 새 줄은 새 1원 하나뿐', (ja.fresh || []).length === 1 && ja.fresh[0].when === '2026-10-14 16:58:10' && ja.fresh[0].dep === 1, (ja.fresh || []).map((r) => r.when));
}

console.log('⑧ 확장 배경 — 보낼 곳 제한 · 대기줄');
const B = require(path.join(ROOT, 'bank-watch', 'background.js'));
chk('방송 서버(엔젤컴퍼니.메인.한국)로는 보낸다', B.allowed('https://xn--9i1b547a0ublxlz4f.xn--h32bi4v.xn--3e0b707e'));
chk('방송 주소가 맞다(idna 로 만든 값)', B.PROD === 'https://' + require('url').domainToASCII('엔젤컴퍼니.메인.한국'), B.PROD);
chk('내 PC 시험 서버로는 보낸다', B.allowed('http://127.0.0.1:5289') && B.allowed('http://localhost:5000'));
chk('다른 주소로는 안 보낸다', !B.allowed('https://evil.example') && !B.allowed('http://10.0.0.5:5000') && !B.allowed('https://127.0.0.1.evil.com') && !B.allowed('javascript:alert(1)') && !B.allowed(''));
chk('방송 서버도 https 만', !B.allowed('http://xn--9i1b547a0ublxlz4f.xn--h32bi4v.xn--3e0b707e'));
let q = B.mergeQueue([{ ref: 'a' }], [{ ref: 'a' }, { ref: 'b' }, null, { amount: 1 }]);
chk('대기줄: 같은 입금은 한 번 · ref 없는 것은 버린다', q.map((x) => x.ref).join(',') === 'a,b', q);
q = B.mergeQueue([], Array.from({ length: 250 }, (_, i) => ({ ref: 'r' + i })));
chk('대기줄은 200건까지(최근 것을 남긴다)', q.length === 200 && q[0].ref === 'r50' && q[199].ref === 'r249');
const MAN = require(path.join(ROOT, 'bank-watch', 'manifest.json'));
chk('manifest 의 보낼 곳(host_permissions)과 배경의 제한이 같다',
  JSON.stringify(MAN.host_permissions) === JSON.stringify([B.PROD + '/*', 'http://127.0.0.1/*', 'http://localhost/*']), MAN.host_permissions);

console.log('\n통과 ' + ok + ' · 실패 ' + bad);
process.exit(bad ? 1 : 0);
