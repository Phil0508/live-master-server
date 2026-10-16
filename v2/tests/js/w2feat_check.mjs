// 🎵 BGM 재생 목록 · 📥 장부 엑셀 · ⌨️ Ctrl+K — 조종실 순수 계산을 node 로 화면 없이 돌린다(v2/tests/test_w2feat.py 가 부른다).
// 실물 파일을 그대로 부른다(베끼지 않는다 — 검사 도구는 실물과 같아야 한다). 답: 줄마다 'OK 이름' · 'BAD 이름 -- 까닭', 끝에 'DONE n'
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const js = path.resolve(here, '..', '..', 'web', 'controller', 'js');
const load = p => import(pathToFileURL(path.join(js, p)).href);

const BGM = await load('panels/records/bgm.js');
const CSV = await load('panels/records/csv.js');
const CMDK = await load('cmdk.js');
const MON = await load('panels/more/monthly.js');

let n = 0;
function chk(name, cond, detail) {
    n++;
    console.log((cond ? 'OK ' : 'BAD ') + name + (cond ? '' : ' -- ' + JSON.stringify(detail === undefined ? null : detail)));
}
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// ── 🔁 다음 곡 셈(nextIndex) — 곡이 끝났을 때(ENDED) ──
chk('전체 반복: 다음 · 마지막 → 처음', eq([0, 1, 2].map(i => BGM.nextIndex('all', i, 3)), [1, 2, 0]));
chk('한 곡 반복: 같은 곡', eq([0, 1, 2].map(i => BGM.nextIndex('one', i, 3)), [0, 1, 2]));
chk('반복 끔: 마지막에서 멈춤(-1)', eq([0, 1, 2].map(i => BGM.nextIndex('off', i, 3)), [1, 2, -1]));
chk('전체 반복 · 한 곡뿐: 그 곡을 계속', BGM.nextIndex('all', 0, 1) === 0);
chk('반복 끔 · 한 곡뿐: 끝', BGM.nextIndex('off', 0, 1) === -1);
chk('곡 없음: -1', BGM.nextIndex('all', 0, 0) === -1 && BGM.nextIndex('one', 3, 0) === -1);
// [다음] 을 손으로 누르면 모드와 상관없이 다음(끝이면 처음)
chk('손으로 다음: 한 곡 반복이어도 다음 곡', BGM.nextIndex('one', 0, 3, true) === 1);
chk('손으로 다음: 반복 끔 마지막 → 처음', BGM.nextIndex('off', 2, 3, true) === 0);
chk('번호가 범위 밖이면 끝으로 붙인다', BGM.nextIndex('all', 9, 3) === 0 && BGM.nextIndex('all', -4, 3) === 1);
// 못 트는 곡 건너뛰기(skipIndex) — 한 곡 반복이어도 다음 곡(같은 막힌 곡을 다시 부르지 않게, 검토 10-17)
chk('건너뛰기: 한 곡 반복 → 다음 곡 · 끝이면 처음', eq([0, 1, 2].map(i => BGM.skipIndex('one', i, 3)), [1, 2, 0]));
chk('건너뛰기: 반복 끔 마지막 → 멈춤 · 전체 반복 → 처음', BGM.skipIndex('off', 2, 3) === -1 && BGM.skipIndex('all', 2, 3) === 0);
// 나오던 곡을 뺀 뒤(goneIndex) — 그 자리 곡 · 마지막 곡을 뺐으면 반복 규칙(검토 10-17: 바로 앞 곡이 다시 나왔다)
chk('뺀 뒤: 그 자리에 온 곡', BGM.goneIndex('all', 1, 3) === 1 && BGM.goneIndex('off', 1, 3) === 1 && BGM.goneIndex('one', 0, 2) === 0);
chk('뺀 뒤: 마지막 곡을 뺐다 → 전체 · 한 곡 반복은 처음, 반복 끔은 멈춤', BGM.goneIndex('all', 2, 2) === 0 && BGM.goneIndex('one', 2, 2) === 0 && BGM.goneIndex('off', 2, 2) === -1);
chk('뺀 뒤: 손으로 [다음] 은 끝이어도 처음 · 곡 없으면 -1', BGM.goneIndex('off', 2, 2, true) === 0 && BGM.goneIndex('all', 0, 0) === -1);
chk('이전 곡: 처음에서 → 맨 끝', eq([0, 1, 2].map(i => BGM.prevIndex(i, 3)), [2, 0, 1]) && BGM.prevIndex(0, 0) === -1);

// ── 목록에 넣기(addTo) — 200곡 끝 · 같은 곡 두 번 안 넣음 · 이상한 번호 거름 ──
let r = BGM.addTo([], ['aaaaaaaaaaa', 'bbbbbbbbbbb', 'aaaaaaaaaaa', 'nope', ''], 200);
chk('넣기: 2곡 · 첫 새 곡 0 · 겹침 0번', r.added === 2 && r.firstNew === 0 && r.dup === 0 && r.list.length === 2, r);
const ids = Array.from({ length: 230 }, (_, i) => 'v' + String(i).padStart(10, '0'));
r = BGM.addTo([], ids, BGM.LIST_MAX);
chk('넣기: 최대 200곡 · 넘친 30곡은 뺀다', BGM.LIST_MAX === 200 && r.list.length === 200 && r.added === 200 && r.over === 30, { len: r.list.length, over: r.over });
r = BGM.addTo(r.list, ['zzzzzzzzzzz'], 200);
chk('넣기: 가득 차면 0곡', r.added === 0 && r.over === 1 && r.list.length === 200);

// ── 주소 읽기 ──
chk('영상 주소 꼴', ['https://www.youtube.com/watch?v=dQw4w9WgXcQ', 'https://youtu.be/dQw4w9WgXcQ?t=3', 'dQw4w9WgXcQ',
    'https://www.youtube.com/shorts/dQw4w9WgXcQ', 'https://www.youtube.com/watch?list=PLx&v=dQw4w9WgXcQ'].every(u => BGM.videoId(u) === 'dQw4w9WgXcQ'));
chk('재생목록 주소 → list 번호', BGM.listId('https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf') === 'PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf'
    && BGM.videoId('https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf') === null);
chk('엉뚱한 글은 없음', BGM.videoId('안녕하세요') === null && BGM.listId('https://example.com/?x=1') === null);
chk('시간 글자 1:42 / 1:02:03', BGM.fmt(102) === '1:42' && BGM.fmt(3723) === '1:02:03' && BGM.fmt(0) === '0:00');

// ── 📥 엑셀(CSV) ──
chk('csvCell 은 월별 순위 것 그대로(= + - @ 앞에 \')', MON.csvCell('=1+1') === '"\'=1+1"' && MON.csvCell('@x') === '"\'@x"' && MON.csvCell('보통') === '"보통"');
chk('한국 시각: 2026-10-07 11:30:05 UTC → 20:30:05', CSV.kst(Date.UTC(2026, 9, 7, 11, 30, 5) / 1000) === '2026-10-07 20:30:05', CSV.kst(Date.UTC(2026, 9, 7, 11, 30, 5) / 1000));
chk('한국 시각: ms 도 · 0 은 빈칸', CSV.kst(Date.UTC(2026, 9, 7, 15, 0, 0)) === '2026-10-08 00:00:00' && CSV.kst(0) === '');
chk('회차 글자', CSV.sessionStamp('20261007-2030-ab12') === '2026-10-07 20:30' && CSV.sessionStamp('') === '방송 밖');
const at = Date.UTC(2026, 9, 7, 11, 31, 0) / 1000;
let t = CSV.donationsCsv([
    { id: 'd2', at: at + 60, name: '구름빵', amount: 20000, message: '', status: 'pending', player: null, source: 'toonation', session: '20261007-2030-ab12' },
    { id: 'd1', at, name: '=HYPERLINK("http://x")', amount: 50000, message: '+밍밍 "화이팅"\n둘째 줄', status: 'assigned', player: '밍밍', source: 'manual', session: '20261007-2030-ab12' },
]);
const lines = t.split('\r\n');
chk('후원 CSV: BOM 으로 시작 · 줄 끝 \\r\\n', t.charCodeAt(0) === 0xfeff && t.endsWith('\r\n'));
chk('후원 CSV: 머리줄', lines[0] === '\ufeff"회차","시각(한국)","후원자","금액","메시지","상태","받은 선수","경로"', lines[0]);
chk('후원 CSV: 오래된 것이 위 · 한국 시각 · 금액은 숫자', lines[1].startsWith('"2026-10-07 20:30","2026-10-07 20:31:00",') && lines[1].includes(',50000,'), lines[1]);
chk('후원 CSV: = 로 시작하는 이름 앞에 \' (수식 막기)', lines[1].includes('"\'=HYPERLINK(""http://x"")"'), lines[1]);
chk('후원 CSV: + 로 시작하는 메시지도 막고 따옴표는 두 겹', lines[1].includes('"\'+밍밍 ""화이팅""\n둘째 줄"'), lines[1]);
chk('후원 CSV: 상태 · 받은 선수 · 경로 한국말', lines[1].includes('"배정","밍밍","손으로 넣음"') && t.includes('"대기","","투네이션"'));
t = CSV.scoresCsv([
    { id: 7, at: at + 5, player: '밍밍', field: 'contribution', list: 'list', delta: 5, reason: '', ref: 'don_d1', undone: 0, session: '20261007-2030-ab12' },
    { id: 6, at, player: '-빼기', field: 'score', list: 'extra', delta: -3, reason: '@잘못', ref: '', undone: 1, session: '20261007-2030-ab12' },
]);
const sl = t.split('\r\n');
chk('점수 CSV: 머리줄', sl[0] === '\ufeff"회차","시각(한국)","선수","판","항목","변화","까닭","후원 묶음","되돌림"', sl[0]);
chk('점수 CSV: 음수 변화는 숫자 그대로 · 이름 · 까닭은 수식 막기 · 되돌림 표시', sl[1].includes('"\'-빼기","번외","점수",-3,"\'@잘못","","되돌림"'), sl[1]);
chk('점수 CSV: 기여도 줄', sl[2].includes('"밍밍","본판","기여도",5,"","don_d1",""'), sl[2]);
chk('파일 이름: 못 쓰는 글자 빼기', CSV.fileName('후원내역_2026-10-07 20:30') === '후원내역_2026-10-07_2030.csv');

// ── ⌨️ Ctrl+K 고를 거리 ──
const names = ['밍밍', '예지랑', '쏘랑'];
const tabs = [{ id: 'roulette', label: '룰렛', short: '' }, { id: 'bgm', label: 'BGM', short: '' }, { id: 'ledger', label: '장부', short: '' }];
let s = CMDK.suggest('밍 5', names, tabs);
chk("Ctrl+K: '밍 5' → '밍밍 5' 바로 하기", s[0] && s[0].kind === 'run' && s[0].text === '밍밍 5', s);
s = CMDK.suggest('랑', names, tabs);
chk("Ctrl+K: '랑' → 예지랑 · 쏘랑 이름 채우기", s.filter(x => x.kind === 'fill').map(x => x.text).join('|') === '예지랑 |쏘랑 ', s);
s = CMDK.suggest('룰렛', names, tabs);
chk("Ctrl+K: '룰렛' → 맨 위는 룰렛 탭 열기, 돌리기는 그 아래", s[0].kind === 'tab' && s[0].text === 'roulette' && s.some(x => x.kind === 'run' && x.text === '룰렛 돌려'), s);
s = CMDK.suggest('bgm', names, tabs);
chk("Ctrl+K: 'bgm' → BGM 탭 · BGM 다음 곡", s[0].kind === 'tab' && s.some(x => x.kind === 'local' && x.text === 'BGM 다음 곡'), s);
s = CMDK.suggest('+1분', names, tabs);
chk("Ctrl+K: '+1분' 은 명령", s[0].kind === 'run' && s[0].text === '+1분', s);
s = CMDK.suggest('아무말', names, tabs);
chk("Ctrl+K: 모르는 말은 '그대로 하기' 하나", s.length === 1 && s[0].kind === 'run' && s[0].text === '아무말', s);
chk('Ctrl+K: 빈칸이면 예시', CMDK.suggest('', names, tabs).length === 5);

console.log('DONE ' + n);
process.exit(0);           // 다른 모듈의 시계(setInterval)가 node 를 붙잡지 않게
