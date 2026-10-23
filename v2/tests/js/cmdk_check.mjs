// 🔎 Ctrl+K 찾기(10-24 "모든걸 검색") — 맞추기 · 줄 세우기 · 색인을 node 로 화면 없이 돌린다(v2/tests/test_cmdk_search.py 가 부른다).
// 실물 파일을 그대로 부른다(베끼지 않는다). 답: 줄마다 'OK 이름' · 'BAD 이름 -- 까닭', 끝에 'DONE n'
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

const here = path.dirname(fileURLToPath(import.meta.url));
const ctl = path.resolve(here, '..', '..', 'web', 'controller');
const js = path.join(ctl, 'js');
const load = p => import(pathToFileURL(path.join(js, p)).href);

const CORE = await load('cmdkcore.js');
const IDX = await load('cmdkindex.js');
const CMDK = await load('cmdk.js');
const CMDS = await load('panels/ai/commands.js');

let n = 0;
function chk(name, cond, detail) {
    n++;
    console.log((cond ? 'OK ' : 'BAD ') + name + (cond ? '' : ' -- ' + JSON.stringify(detail === undefined ? null : detail).slice(0, 600)));
}
const brief = s => (s || []).map(x => `${x.group}/${x.kind}:${x.label}`);

// ── 글자 맞추기(cmdkcore) ──
const { norm, cho, hit, wonOf, looseIndex, scoreEntry } = CORE;
chk('norm: 띄어쓰기 · 이모지 · 대소문자 · 문장부호 무시', norm('🖼 방송 테두리') === '방송테두리' && norm('BGM 다음 곡') === 'bgm다음곡' && norm('이름 · 종잣돈') === '이름종잣돈');
chk('norm: + · - 는 남긴다(+1분 ≠ -1분) · 긴 줄표는 -', norm('+1분') === '+1분' && norm('−1분') === '-1분' && norm('+1분') !== norm('-1분'));
chk('초성', cho('밍밍 5') === 'ㅁㅁ 5' && cho('BGM') === 'BGM');
chk('점수: 똑같음 > 앞이 같음 > 들어 있음', hit('방송테두리', '방송테두리') === 100 && hit('방송테두리', '방송') === 82 && hit('방송테두리', '테두리') === 58
    && hit('방송테두리', '테두리') < hit('방송테두리', '방송'));
chk('초성: ㅁㅁ → 밍밍(거의 똑같음) · ㅂㅅㅌㄷㄹ → 방송테두리', hit('밍밍', 'ㅁㅁ') === 78 && hit('방송테두리', 'ㅂㅅㅌㄷㄹ') === 78 && hit('예지랑', 'ㅈㄹ') > 0);
chk('초성 · 글자 섞기: 밍ㅁ → 밍밍', hit('밍밍', '밍ㅁ') > 0);
chk('치는 중인 마지막 글자: 미 → 밍밍 · 밍 → 미안 · 대바 → 대박', hit('밍밍', '미') > 0 && looseIndex('미안', '밍') === 0 && hit('대박', '대바') > 0);
chk('마지막 글자가 아니면 받침 없는 글자로 안 맞춘다(미밍 ≠ 밍밍)', hit('밍밍', '미밍') === 0);
chk('안 맞으면 0', hit('방송테두리', '모금함') === 0 && hit('', 'a') === 0 && hit('a', '') === 0);
chk('금액 읽기', wonOf('5만') === 50000 && wonOf('5만원') === 50000 && wonOf('50,000원') === 50000 && wonOf('₩50000') === 50000
    && wonOf('1.5만') === 15000 && wonOf('5만5천') === 55000 && wonOf('3천') === 3000 && wonOf('안녕') === 0 && wonOf('12') === 0, [wonOf('5만5천')]);
chk('다른 말(kw)은 이름보다 조금 낮게 — 똑같은 다른 말(80)도 이름 앞이 같은 것(82)보다 아래', scoreEntry({ title: '🔑 은행 확장 연결', kw: '계좌열쇠' }, '계좌 열쇠') === 80 && scoreEntry({ title: '계좌 열쇠' }, '계좌 열쇠') === 100);
chk('설명(sub)에만 있으면 30', scoreEntry({ title: '모금함', sub: '모금함 켜기 · 금액 · 깃발 자리' }, '깃발') === 30);
chk('여러 낱말: 낱말마다 어딘가에 있으면 40', scoreEntry({ title: '방송판 깃발 자리', sub: '모금함' }, '모금함 깃발') === 40
    && scoreEntry({ title: '방송판 깃발 자리', sub: '모금함' }, '모금함 노래방') === 0);

// ── 찾을 거리 — 실제 색인(cmdkindex.js) + 가짜 조각 ──
const names = ['밍밍', '예지랑', '쏘랑'];
const tabs = [
    { id: 'home', label: '랭킹', short: '랭킹', icon: '🏆' },
    { id: 'roulette', label: '룰렛', icon: '🎡', group: '왼쪽 줄' }, { id: 'bgm', label: 'BGM', icon: '🎵' },
    { id: 'match', label: '대결', icon: '⚔️' }, { id: 'clip', label: '클립', icon: '✂️' },
    { id: 'ledger', label: '장부', icon: '📒', desc: '이번 방송 후원 · 점수 기록', group: '기록' },
    { id: 'ops-notice', label: '공지', icon: '📣', desc: '방송판 아래로 흐르는 안내', group: '방송 화면' },
    { id: 'ops-fundjar', label: '모금함', icon: '🏺', desc: '모금함 켜기 · 금액 · 깃발 자리', group: '방송 화면', locked: true },
    { id: 'ops-stage', label: '무대', icon: '📺', desc: '방송판에 띄울 것 · 순서표', group: '방송 화면' },
    { id: '@bank', act: '@bank', label: '은행 확장', icon: '🏦', desc: '계좌 입금 확장 · 폰 앱 상태', group: '시스템' },
];
const tabLabel = Object.fromEntries(tabs.map(t => [t.id, t.label]));
const spots = IDX.SPOTS.map(([tab, title, kw, find]) => ({ key: tab + '|' + title, tab, title, kw, find,
    where: (IDX.PLACE[tab] || [])[1] || `${tabLabel[tab] || tab} 탭`, sub: tabLabel[tab] || '' }));
const more = {
    spots,
    donors: [{ title: '별빛', pid: 'p1', info: '💛밍밍 전담 · 23회' }, { title: '별사탕', pid: '' }, { title: '구름빵', pid: 'p3' }],
    sigs: [{ title: '사쿠란보', kw: '1', id: 1, amount: 10300 }, { title: '대박', kw: '3', id: 3, amount: 50000 }, { title: '제로투 댄스', kw: '105', id: 105, amount: 600000 }],
    pending: [{ id: 'd9', title: '구름빵', sub: '밍밍 화이팅', amount: 30000 }],
    ledger: [{ id: 'don_1', title: '하늘', sub: '오늘도 화이팅 응원해요', amount: 20000, time: '20:31:00' }],
    notices: [{ title: '계좌로 보내실 때 *닉네임+플레이어* 를 적어 주세요', i: 0 }],
    roulette: [{ title: '벌칙 노래 한 곡', i: 0 }, { title: '애교', i: 1 }],
};
const S = q => CMDK.suggest(q, names, tabs, more);
const top = q => S(q)[0] || {};

let s = S('방송 테두리');
chk("'방송 테두리' → 무대 탭 🖼 방송 테두리 스위치가 맨 위", s[0].kind === 'spot' && s[0].spot.tab === 'ops-stage' && s[0].spot.find === '방송 테두리', brief(s));
chk("'테마' → 무대 탭 테마 블록", top('테마').kind === 'spot' && top('테마').spot.find === '테마' && top('테마').spot.tab === 'ops-stage', brief(S('테마')));
chk("'할로윈' → 🎃 할로윈 테마", top('할로윈').label === '🎃 할로윈 테마', brief(S('할로윈')));
chk("'효과음' → 🔊 효과음", top('효과음').label === '🔊 효과음', brief(S('효과음')));
chk("'용 연출' · '용' → 🐉 용 연출(이펙트 탭)", top('용 연출').label === '🐉 용 연출' && S('용').some(x => x.label === '🐉 용 연출') && top('용 연출').spot.tab === 'ops-opfx', brief(S('용')));
chk("'계좌 열쇠' → 🔑 은행 확장 연결 · 계좌 열쇠(후원 콘솔)", top('계좌 열쇠').spot && top('계좌 열쇠').spot.tab === 'ops-console', brief(S('계좌 열쇠')));
chk("'시그니처 최저선' · '최저선' → 시그니처 관리", top('최저선').spot && top('최저선').spot.tab === 'sig-admin' && top('시그니처 최저선').spot.tab === 'sig-admin', brief(S('최저선')));
chk("'공지' → 공지 탭이 맨 위 · 설정에도 공지 줄들", top('공지').kind === 'tab' && top('공지').text === 'ops-notice' && S('공지').some(x => x.kind === 'spot' && x.spot.tab === 'ops-notice'), brief(S('공지')));
chk("'모금함' — 잠긴 탭은 그대로 보이되(방송을 시작하면 열려요) 맨 위 120 은 아니다", (() => {
    const t = S('모금함').find(x => x.kind === 'tab' && x.text === 'ops-fundjar');
    return t && t.locked && t.score === 100 && /방송을 시작하면/.test(t.sub);
})(), brief(S('모금함')));
chk("'ㅂㅅㅌㄷㄹ'(초성) → 🖼 방송 테두리", top('ㅂㅅㅌㄷㄹ').label === '🖼 방송 테두리', brief(S('ㅂㅅㅌㄷㄹ')));
chk("'ㅁㅁ'(초성) → 밍밍 이름 채우기가 맨 위", top('ㅁㅁ').kind === 'fill' && top('ㅁㅁ').text === '밍밍 ', brief(S('ㅁㅁ')));
chk("'ㅁㅁ 5' → 밍밍 +5점 바로", top('ㅁㅁ 5').kind === 'run' && top('ㅁㅁ 5').text === '밍밍 5', brief(S('ㅁㅁ 5')));
chk("'미'(치는 중) → 밍밍 채우기도 나온다", S('미').some(x => x.kind === 'fill' && x.text === '밍밍 '), brief(S('미')));
chk("'별빛' → 후원자 카드(pid)", top('별빛').kind === 'donor' && top('별빛').pid === 'p1' && /전담/.test(top('별빛').sub), brief(S('별빛')));
chk("'별' → 후원자 둘(앞이 같음) · 카드 없는 사람은 '장부에서'", S('별').filter(x => x.kind === 'donor').length === 2
    && S('별').find(x => x.text === '별사탕').hint === '장부에서', brief(S('별')));
chk("'사쿠' → 시그니처 사쿠란보", top('사쿠').kind === 'sig' && top('사쿠').text === '1', brief(S('사쿠')));
chk("'5만' → 50,000원 시그니처(대박)", S('5만').some(x => x.kind === 'sig' && x.text === '3' && x.score >= 96), brief(S('5만')));
chk("'105'(번호) → 제로투 댄스", S('105').some(x => x.kind === 'sig' && x.text === '105'), brief(S('105')));
chk("'구름빵' → 대기함 카드 · 후원자 둘 다", S('구름빵').some(x => x.kind === 'pend' && x.text === 'd9') && S('구름빵').some(x => x.kind === 'donor'), brief(S('구름빵')));
chk("'3만' → 대기함 30,000원", S('3만').some(x => x.kind === 'pend'), brief(S('3만')));
chk("'화이팅'(메시지) → 대기함 · 장부 줄", S('화이팅').some(x => x.kind === 'pend') && S('화이팅').some(x => x.kind === 'ledger' && x.name === '하늘' && x.time === '20:31:00'), brief(S('화이팅')));
chk("'닉네임' → 공지 줄", S('닉네임').some(x => x.kind === 'notice' && x.text === '0'), brief(S('닉네임')));
chk("'벌칙' → 룰렛 칸(적어 둔 칸 · 룰렛 직접 입력 칸 둘 다)", S('벌칙').some(x => x.kind === 'roul' && x.text === '벌칙 노래 한 곡') && S('벌칙').every(x => x.group === 'ask' || (x.spot || {}).tab === 'roulette' || x.kind === 'roul'), brief(S('벌칙')));
chk("'은행' → 은행 확장 타일(탭이 아닌 것)도", S('은행').some(x => x.kind === 'act' && x.text === '@bank'), brief(S('은행')));
chk("'깃발' → 모금함 깃발 자리", S('깃발').some(x => x.kind === 'spot' && x.spot.tab === 'ops-fundjar'), brief(S('깃발')));
chk("'점수판' → 랭킹 첫 화면 점수판(#scores)", S('점수판').some(x => x.kind === 'spot' && x.spot.find === '#scores'), brief(S('점수판')));
chk("'대기함' → 오른쪽 칸 대기함", S('대기함').some(x => x.kind === 'spot' && x.spot.find === '#pending'), brief(S('대기함')));

// ── 명령은 예전 그대로 ──
chk("'룰렛' → 탭이 맨 위(돌리기는 '룰렛 돌려')", top('룰렛').kind === 'tab' && top('룰렛').text === 'roulette' && S('룰렛').some(x => x.kind === 'run' && x.text === '룰렛 돌려'));
chk("'대결' · '클립' → 탭 이름 그대로면 탭(예전처럼)", top('대결').kind === 'tab' && top('클립').kind === 'tab');
chk("'룰렛 돌려' → 명령", top('룰렛 돌려').kind === 'run' && top('룰렛 돌려').text === '룰렛 돌려');
chk("'스킵' · '건너뛰기' → 명령 꼴이라 '바로 하기' 가 설정보다 위", top('스킵').kind === 'run' && top('스킵').text === '스킵'
    && top('건너뛰기').kind === 'run' && top('건너뛰기').text === '건너뛰기' && S('건너뛰기').some(x => x.kind === 'spot'), brief(S('건너뛰기')));
chk("'다음' → 순서표 다음(명령) · BGM 다음 곡은 아래", top('다음').kind === 'run' && top('다음').text === '다음' && S('다음').some(x => x.kind === 'local'), brief(S('다음')));
chk("'밍밍한테 3점 줘' → 명령 그대로", top('밍밍한테 3점 줘').kind === 'run' && top('밍밍한테 3점 줘').text === '밍밍한테 3점 줘');
chk("'+1분' · '-30초' → 명령", top('+1분').text === '+1분' && top('-30초').kind === 'run' && top('-30초').text === '-30초');
chk("'올클' → 명령(올클리어)", top('올클').kind === 'run' && top('올클').text === '올클', brief(S('올클')));
chk('isCommandForm: 선수 이름이 아니면 점수 명령 아님', CMDS.isCommandForm('밍 5', names) && !CMDS.isCommandForm('하늘 5', names) && !CMDS.isCommandForm('테마', names)
    && CMDS.isCommandForm('대결 시작', names) && CMDS.isCommandForm('클립 저장', names) && CMDS.isCommandForm('1분 추가', names) && !CMDS.isCommandForm('', names));
s = S('공지 바꿔: 오늘은 7시까지');
chk("모르는 긴 말 → '그대로 하기' 만(서버 · AI 에게)", s.length === 1 && s[0].group === 'ask' && s[0].text === '공지 바꿔: 오늘은 7시까지', brief(s));
chk("'아무말' → '그대로 하기' 하나", S('아무말').length === 1 && S('아무말')[0].kind === 'run');

// ── 묶음 · 줄 세우기 ──
function contiguous(list) {
    const seen = new Set();
    let prev = null;
    for (const it of list) {
        if (it.group !== prev) { if (seen.has(it.group)) return false; seen.add(it.group); prev = it.group; }
    }
    return true;
}
const broad = ['공지', '모금', '알림', '밍', '별', '화이팅', 'ㅁ', '시그', '무대', '계좌', '5만', '테'];
chk('같은 묶음은 붙어 있다(머리 하나)', broad.every(q => contiguous(S(q))), broad.filter(q => !contiguous(S(q))));
chk("'그대로 하기' 는 늘 맨 끝 · 하나", broad.every(q => { const a = S(q); const k = a.filter(x => x.group === 'ask'); return k.length <= 1 && (!k.length || a[a.length - 1] === k[0]); }));
chk('묶음마다 몇 개까지만(설정 6 · 탭 5 · 후원자 5 …)', broad.every(q => {
    const c = {};
    S(q).forEach(x => { c[x.group] = (c[x.group] || 0) + 1; });
    return (c.spot || 0) <= 6 && (c.tab || 0) <= 5 && (c.donor || 0) <= 5 && (c.cmd || 0) <= 4;
}));
chk('묶음 안은 점수 순', broad.every(q => { const a = S(q); return a.every((x, i) => i === 0 || a[i - 1].group !== x.group || a[i - 1].score >= x.score); }));
s = S('알림');
const iPrefix = s.findIndex(x => x.label === '알림 (후원 팝업 · 1등 탈환 · 시그 제목)');
const iContains = s.findIndex(x => x.label === '🔔 AI 먼저 알림');
chk("'알림' — 앞이 같은 것이 들어 있는 것보다 위", iPrefix >= 0 && (iContains < 0 || iPrefix < iContains), brief(s));
chk('빈칸이면 예시 5개(머리 없이)', CMDK.suggest('', names, tabs, more).length === 5);
chk('3개만 넘겨도(옛 부르기) 된다', CMDK.suggest('룰렛', names, tabs)[0].kind === 'tab');

// ── 빠르기 — 후원자 6,000명 · 글자마다 ──
const many = Array.from({ length: 6000 }, (_, i) => ({ title: '후원자' + i + (i % 7 ? '별' : '달'), pid: 'p' + i }));
const big = Object.assign({}, more, { donors: many });
CMDK.suggest('후원', names, tabs, big);                     // 첫 번은 바꾼 글자를 만든다
let t0 = performance.now();
for (const q of ['ㅎ', '후', '후원', '후원자1', '별', '달빛', 'ㅎㅇㅈ']) CMDK.suggest(q, names, tabs, big);
const per = (performance.now() - t0) / 7;
chk(`빠르기: 6,000명에서 한 번 찾기 ${per.toFixed(1)}ms (120ms 아래)`, per < 120, per);

// ── 색인(cmdkindex.js)이 실물과 맞는가 ──
function walk(dir) {
    return fs.readdirSync(dir, { withFileTypes: true }).flatMap(d => d.isDirectory() ? walk(path.join(dir, d.name)) : [path.join(dir, d.name)]);
}
const srcFiles = walk(js).filter(f => f.endsWith('.js') && !/cmdk(index|core)?\.js$/.test(f));
const SRC = srcFiles.map(f => fs.readFileSync(f, 'utf8')).join('\n') + fs.readFileSync(path.join(ctl, 'index.html'), 'utf8');
// 탭 id — 탭 목록 파일들에서
const panelIds = new Set();
for (const f of ['games.js', 'tools_ops.js', 'tools_records.js', 'tools_more.js', 'tools_sig.js', 'tools_fx.js', 'tools_ai.js', 'tools_auto.js', 'frame.js', 'settings_menu.js']) {
    for (const m of fs.readFileSync(path.join(js, 'panels', f), 'utf8').matchAll(/\{\s*id:\s*'([a-z0-9-]+)'/g)) panelIds.add(m[1]);
}
const badTab = IDX.SPOTS.filter(([tab]) => !panelIds.has(tab) && !IDX.PLACE[tab]).map(x => x[0] + ' ' + x[1]);
chk('색인: 탭 id 가 다 있다', badTab.length === 0 && panelIds.size > 30, badTab);
const missing = [];
for (const [tab, title, , find] of IDX.SPOTS) {
    if (find.startsWith('#')) {
        const id = find.slice(1);
        if (!SRC.includes(`id: '${id}'`) && !SRC.includes(`id="${id}"`)) missing.push(tab + ' ' + find);
    } else if (find.startsWith('.')) {
        if (!SRC.includes(find.slice(1))) missing.push(tab + ' ' + find);
    } else if (!SRC.includes(find)) missing.push(tab + ' ' + title + ' → ' + find);
}
chk('색인: 찾을 글자 · id · class 가 실제 코드에 있다(글자를 바꿨으면 cmdkindex.js 도)', missing.length === 0, missing);
const titles = IDX.SPOTS.map(x => x[0] + '|' + x[1]);
chk('색인: 같은 이름이 두 번 없다', new Set(titles).size === titles.length, titles.filter((t, i) => titles.indexOf(t) !== i));
// 블록 제목(blockHead)을 새로 만들면 색인에도 한 줄 — 안 연 탭에서도 찾게
const heads = [];
for (const f of walk(path.join(js, 'panels'))) {
    for (const m of fs.readFileSync(f, 'utf8').matchAll(/blockHead\(\s*'([^']+)'/g)) heads.push([path.basename(f), m[1]]);
}
const finds = IDX.SPOTS.filter(x => !/^[#.]/.test(x[3])).map(x => norm(x[3]));
const uncovered = heads.filter(([, t]) => !finds.some(f => f && norm(t).includes(f)));
chk(`색인: 블록 제목 ${heads.length}개가 다 찾힌다`, heads.length >= 30 && uncovered.length === 0, uncovered);

console.log('DONE ' + n);
process.exit(0);           // 다른 모듈의 시계(setInterval)가 node 를 붙잡지 않게
