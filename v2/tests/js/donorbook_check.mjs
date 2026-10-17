// 📇 후원자 장부 — 조종실 js/donorcore.js(딱지 글자 · 목록 거르기 · 막대)를 node 로 화면 없이 부른다(v2/tests/test_donorbook_ui.py 가 부른다).
// 실물 파일을 그대로 부른다. 답: 줄마다 'OK 이름' · 'BAD 이름 -- 까닭', 끝에 'DONE n'
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const js = path.resolve(here, '..', '..', 'web', 'controller', 'js');
const D = await import(pathToFileURL(path.join(js, 'donorcore.js')).href);

let n = 0;
function chk(name, cond, detail) {
    n++;
    console.log((cond ? 'OK ' : 'BAD ') + name + (cond ? '' : ' -- ' + JSON.stringify(detail === undefined ? null : detail)));
}
const txt = c => (c ? c.text : null);

// ── 이름 맞추기(서버 rules.norm_donor 와 같게) ──
chk('norm: 앞뒤 빈칸 · 겹친 빈칸', D.normDonor('  영원   왕자 ') === '영원 왕자');
chk('norm: 끝의 님 떼기', D.normDonor('영원님') === '영원' && D.normDonor('영원 님') === '영원');
chk('norm: 빈 것은 익명', D.normDonor('') === '익명' && D.normDonor(null) === '익명' && D.normDonor('님') === '익명');

const tags = {
    '영원': { pid: 'p_aaaaaaaaaa', tag: 'main', player: '밍밍', n: 23, share: 0.957, club: '밍밍' },
    '쏘랑왕자님': { pid: 'p_b', tag: 'lean', player: '쏘랑', n: 8, share: 0.75, club: '' },
    '여기저기': { pid: 'p_c', tag: 'multi', player: '예지랑', n: 12, share: 0.4, club: '앙앙' },
    '새손님': { pid: 'p_d', tag: 'new', player: '밍밍', n: 1, share: 1 },
    '고정씨': { pid: 'p_e', tag: 'pin', player: '복자', n: 4, share: 0.5 },
    '익명': { pid: 'p_anon', tag: 'main', player: '밍밍', n: 99, share: 1 },
};

// ── 조각에서 찾기 ──
chk('tagFor: 그대로', D.tagFor(tags, '영원').pid === 'p_aaaaaaaaaa');
chk('tagFor: 님 · 빈칸 붙어도 같은 사람', D.tagFor(tags, ' 영원님 ').pid === 'p_aaaaaaaaaa');
chk('tagFor: 조각이 없으면 null', D.tagFor(undefined, '영원') === null && D.tagFor(null, '영원') === null);
chk('tagFor: 이름이 없거나 익명이면 null(조각에 익명 칸이 있어도)', D.tagFor(tags, '') === null && D.tagFor(tags, null) === null && D.tagFor(tags, '익명') === null && D.tagFor(tags, 'Anonymous') === null);
chk('tagFor: 모르는 이름은 null', D.tagFor(tags, '처음보는') === null);

// ── 딱지 글자 ──
chk('전담: 💛밍밍 전담 · 23회', txt(D.chipText(tags['영원'])) === '💛밍밍 전담 · 23회', D.chipText(tags['영원']));
chk('전담 title 에 비율', /밍밍 96%/.test(D.chipText(tags['영원']).title), D.chipText(tags['영원']).title);
chk('주력: 🧡쏘랑 주력 · 8회', txt(D.chipText(tags['쏘랑왕자님'])) === '🧡쏘랑 주력 · 8회');
chk('여러 멤버: 🌈 여러 멤버 · 12회', txt(D.chipText(tags['여기저기'])) === '🌈 여러 멤버 · 12회');
chk('새 얼굴: 🌱 새 얼굴(선수 · 횟수 안 씀)', txt(D.chipText(tags['새손님'])) === '🌱 새 얼굴');
chk('고정: 📌복자 고정', txt(D.chipText(tags['고정씨'])) === '📌복자 고정');
chk('딱지 class', D.chipText(tags['영원']).cls === 'dn-tag t-main' && D.chipText(tags['고정씨']).cls === 'dn-tag t-pin');
chk('모르는 딱지 · 빈 것은 null', D.chipText({ tag: 'boss' }) === null && D.chipText(null) === null && D.chipText({}) === null);
chk('전담인데 선수가 비면 그리지 않음', D.chipText({ tag: 'main', player: '', n: 9, share: 1 }) === null);
chk('횟수 이상한 값은 0 으로', txt(D.chipText({ tag: 'multi', n: 'x' })) === '🌈 여러 멤버');

// ── 팬클럽 딱지 ──
chk('팬클럽: 전담과 같은 선수면 안 붙임', D.clubText(tags['영원']) === null);
chk('팬클럽: 다른 선수면 🏷️앙앙 팬클럽', txt(D.clubText(tags['여기저기'])) === '🏷️앙앙 팬클럽');
chk('팬클럽: 없으면 null', D.clubText(tags['쏘랑왕자님']) === null && D.clubText(null) === null);
chk('chipsFor: 딱지 + 팬클럽 두 개', D.chipsFor(tags, '여기저기').map(c => c.text).join('|') === '🌈 여러 멤버 · 12회|🏷️앙앙 팬클럽');
chk('chipsFor: 없는 이름은 빈 배열', Array.isArray(D.chipsFor(tags, '없음')) && D.chipsFor(tags, '없음').length === 0);
chk('chipsFor: 조각 없으면 빈 배열', D.chipsFor(undefined, '영원').length === 0);
chk('tagSig: 딱지가 바뀌면 달라진다', D.tagSig(tags, '영원') !== D.tagSig({ '영원': { ...tags['영원'], n: 24 } }, '영원') && D.tagSig(tags, '없음') === '');

// ── 목록 거르기 ──
const persons = [
    { pid: 'p1', label: '영원', tag: 'main', player: '밍밍', n: 23, share: 0.96, club: '밍밍', total_won: 900000, last_at: 300, names: ['영원', '존잘영원', '밍플단영트트'], sugg: 1 },
    { pid: 'p2', label: '쏘랑왕자님', tag: 'lean', player: '쏘랑', n: 8, total_won: 120000, last_at: 500, names: [{ name: '쏘랑왕자님', n: 8 }], dormant: true },
    { pid: 'p3', label: '여기저기', tag: 'multi', player: '예지랑', n: 12, total_won: 300000, last_at: 100, names: ['여기저기'] },
    { pid: 'p4', label: '새손님', tag: 'new', n: 1, total_won: 10000, last_at: 900, names: ['새손님'] },
    { pid: 'p5', label: '1111', tag: 'new', n: 2, total_won: 20000, last_at: 950, names: ['1111'], test: 1 },
    { pid: 'p6', label: '고정씨', tag: 'pin', pin: '복자', player: '복자', n: 4, total_won: 40000, last_at: 400, names: ['고정씨'] },
];
const ids = list => list.map(p => p.pid).join(',');
chk('전체: 시험 이름은 빼고 최근 온 순', ids(D.filterPersons(persons)) === 'p4,p2,p6,p1,p3', ids(D.filterPersons(persons)));
chk('💛 전담만', ids(D.filterPersons(persons, { filter: 'main' })) === 'p1');
chk('🌱 새 얼굴 — 시험 이름 1111 은 안 나온다', ids(D.filterPersons(persons, { filter: 'new' })) === 'p4');
chk('🧪 시험 이름에서만 1111', ids(D.filterPersons(persons, { filter: 'test' })) === 'p5');
chk('📌 고정', ids(D.filterPersons(persons, { filter: 'pin' })) === 'p6');
chk('🏷️ 팬클럽', ids(D.filterPersons(persons, { filter: 'club' })) === 'p1');
chk('🔗 묶을까?', ids(D.filterPersons(persons, { filter: 'sugg' })) === 'p1');
chk('💤 쉬는 중', ids(D.filterPersons(persons, { filter: 'dormant' })) === 'p2');
chk('찾기: 예전 닉네임으로(존잘)', ids(D.filterPersons(persons, { q: '존잘' })) === 'p1');
chk('찾기: 빈칸 · 대소문자 무시', ids(D.filterPersons(persons, { q: ' 밍플 단 ' })) === 'p1');
chk('찾기: 이름 칸이 {name} 모양이어도', ids(D.filterPersons(persons, { q: '왕자' })) === 'p2');
chk('찾기: 선수 이름으로', ids(D.filterPersons(persons, { q: '예지랑' })) === 'p3');
chk('찾기 + 거르기 같이', ids(D.filterPersons(persons, { filter: 'lean', q: '영원' })) === '');
chk('많이 준 순', ids(D.filterPersons(persons, { sort: 'won' })) === 'p1,p3,p2,p6,p4');
chk('자주 온 순', ids(D.filterPersons(persons, { sort: 'n' })) === 'p1,p3,p2,p6,p4');
chk('원본 배열은 그대로', ids(persons) === 'p1,p2,p3,p4,p5,p6');
chk('배열이 아니면 빈 목록', D.filterPersons(null).length === 0 && D.filterPersons({}).length === 0);
const c = D.filterCounts(persons);
chk('거르기 숫자', c.all === 5 && c.main === 1 && c.lean === 1 && c.multi === 1 && c.new === 1 && c.pin === 1 && c.club === 1 && c.sugg === 1 && c.dormant === 1 && c.test === 1, c);
chk('거르기 단추마다 숫자 칸이 있다', D.FILTERS.every(([k]) => k in c));

// ── 카드 ──
const bars = D.playerBars({ '밍밍': 20, '앙앙': 3, '예지랑': 0, '복자': 'x' });
chk('막대: 많은 순 · 0 은 뺀다', bars.map(b => b.name).join(',') === '밍밍,앙앙', bars);
chk('막대: 비율 · 폭', bars[0].pct === 87 && bars[1].pct === 13 && bars[0].w === 100 && bars[1].w === 15, bars);
chk('막대: 없으면 빈 배열', D.playerBars(null).length === 0 && D.playerBars({}).length === 0);
chk('받은 사람: player 글자', D.recentTo({ player: '밍밍' }) === '밍밍');
chk('받은 사람: players 배열', D.recentTo({ players: ['밍밍', '앙앙'] }) === '밍밍 · 앙앙');
chk('받은 사람: 없으면 빈 글자', D.recentTo({}) === '' && D.recentTo(null) === '');
const now = new Date(2026, 9, 17, 21, 0).getTime();
chk('마지막: 오늘(초 단위도 받는다)', D.relDay(new Date(2026, 9, 17, 0, 5).getTime() / 1000, now) === '오늘');
chk('마지막: 어제', D.relDay(new Date(2026, 9, 16, 23, 59).getTime(), now) === '어제');
chk('마지막: 5일 전', D.relDay(new Date(2026, 9, 12, 12).getTime(), now) === '5일 전');
chk('마지막: 달 전', D.relDay(new Date(2026, 6, 10).getTime(), now) === '3달 전', D.relDay(new Date(2026, 6, 10).getTime(), now));
chk('마지막: 1년 넘게', D.relDay(new Date(2025, 5, 1).getTime(), now) === '1년 넘게');
chk('마지막: 없으면 빈 글자', D.relDay(0, now) === '' && D.relDay(null, now) === '');
chk('날짜 글자', D.ymd(new Date(2026, 9, 7, 20, 30).getTime() / 1000) === '2026.10.07');

// ── 팬클럽 사전 ──
const clubs = { '밍플단': { player: '밍밍', confirmed: true }, '앙플단': { player: '앙앙', confirmed: true }, '7싸단': { player: '제이양', confirmed: false }, '잔단': { player: '', confirmed: false } };
const rows = D.clubRows(clubs);
chk('사전: 추정이 위', rows.slice(0, 2).every(r => !r.confirmed) && rows.slice(2).every(r => r.confirmed), rows);
chk('사전: 확인 기다림 수(선수 짐작이 있는 추정만)', D.clubGuessCount(clubs) === 1);
chk('사전: 조각 없으면 빈 배열', D.clubRows(undefined).length === 0 && D.clubGuessCount(null) === 0);

// ── 그 밖 ──
chk('📌 고정: 서버가 안 알려 주면 보인다', D.pinOn({}) === true && D.pinOn(null) === true);
chk('📌 고정: pin_on:false 면 숨긴다', D.pinOn({ pin_on: false }) === false && D.pinOn({ pin_off: true }) === false && D.pinOn({ pin_on: true }) === true);
chk('제안 목록 모양', D.suggestList([{ id: 1 }]).length === 1 && D.suggestList({ suggest: [{}, {}] }).length === 2 && D.suggestList({ rows: [{}] }).length === 1 && D.suggestList(null).length === 0);
chk('제안 까닭 글자', D.whyText('key') === '투네이션 번호표가 같아요' && D.whyText('name') === '닉네임이 비슷해요' && D.whyText('bank') === '계좌 입금 짝이에요');

console.log('DONE ' + n);
