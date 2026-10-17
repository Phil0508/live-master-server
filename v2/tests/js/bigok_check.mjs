// 🛡️ 큰 금액은 한 번 더 확인 — 조종실 js/bigok.js 를 node 로 화면 없이 부른다(v2/tests/test_bigok.py 가 부른다).
// 실물 파일을 그대로 부른다. 답: 줄마다 'OK 이름' · 'BAD 이름 -- 까닭', 끝에 'DONE n'
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';
import fs from 'node:fs';

const here = path.dirname(fileURLToPath(import.meta.url));
const js = path.resolve(here, '..', '..', 'web', 'controller', 'js');
const B = await import(pathToFileURL(path.join(js, 'bigok.js')).href);

let n = 0;
function chk(name, cond, detail) {
    n++;
    console.log((cond ? 'OK ' : 'BAD ') + name + (cond ? '' : ' -- ' + JSON.stringify(detail === undefined ? null : detail)));
}

const pend = [
    { id: 'p1', name: '영원', amount: 500000, message: '밍밍 화이팅' },
    { id: 'p2', name: '작은손', amount: 199999 },
    { id: 'p3', name: '딱이십', amount: 200000 },
    { id: 'p4', name: '기여', kind: 'contrib', amount: 0, contrib: 25 },
    { id: 'p5', name: '기여작게', kind: 'contrib', amount: 0, contrib: 5 },
    { id: 'off', type: 'off_work', name: '퇴근', amount: 0 },
];
const S = bigok => ({ pending: pend, bigok });
const def = S({ won: 200000, pts: 20 });

// ── 기준 ──
chk('기본값: 조각이 없으면 20만 원 · 20점', JSON.stringify(B.limits({})) === '{"won":200000,"pts":20}');
chk('조각 값 그대로 · 음수는 0', JSON.stringify(B.limits({ bigok: { won: 50000, pts: -3 } })) === '{"won":50000,"pts":0}');

// ── 대기함 배정 ──
let x = B.needFor(def, 'pending.assign', { id: 'p1', name: '밍밍' });
chk('50만 원 → 묻는다 · 밍밍 50점', x && x.kind === 'don' && x.who === '영원' && x.amount === 500000 && x.rows.length === 1 && x.rows[0].name === '밍밍' && x.rows[0].pts === 50, x);
chk('제목: 영원 500,000원 → 밍밍에게 50점 줄까요?', B.titleOf([x]) === '영원 500,000원 → 밍밍에게 50점 줄까요?', B.titleOf([x]));
chk('199,999원 → 바로(안 묻는다)', B.needFor(def, 'pending.assign', { id: 'p2', name: '밍밍' }) === null);
chk('딱 200,000원 → 묻는다(이상)', !!B.needFor(def, 'pending.assign', { id: 'p3', name: '밍밍' }));
x = B.needFor(def, 'pending.assign', { id: 'p1', names: ['밍밍', '하율', '예지'] });
chk('나눠 주기 3명: 누구에게 몇 점 다(17 · 17 · 16)', x && x.rows.map(r => r.name + r.pts).join(',') === '밍밍17,하율17,예지16', x);
chk('나눠 주기 제목: 3명에게 나눠 줄까요?', B.titleOf([x]) === '영원 500,000원 → 3명에게 나눠 줄까요?', B.titleOf([x]));
chk('오토파일럿(via ap)은 안 묻는다', B.needFor(def, 'pending.assign', { id: 'p1', name: '밍밍', via: 'ap' }) === null);
chk('없는 후원 · 퇴근 카드는 안 묻는다', B.needFor(def, 'pending.assign', { id: 'nope', name: '밍밍' }) === null && B.needFor(def, 'pending.assign', { id: 'off', name: '밍밍' }) === null);
chk('기준 0 = 끔', B.needFor(S({ won: 0, pts: 20 }), 'pending.assign', { id: 'p1', name: '밍밍' }) === null);
chk('기준을 5만 원으로 낮추면 199,999원도 묻는다', !!B.needFor(S({ won: 50000, pts: 20 }), 'pending.assign', { id: 'p2', name: '밍밍' }));
x = B.needFor(def, 'pending.assign', { id: 'p4', name: '밍밍' });
chk('기여도 카드 25 ≥ 20 → 묻는다(기여도로)', x && x.kind === 'contrib' && x.rows[0].contrib === 25 && x.rows[0].pts === 0, x);
chk('기여도 카드 5 → 바로', B.needFor(def, 'pending.assign', { id: 'p5', name: '밍밍' }) === null);

// ── 손 점수 ──
chk('손 점수 19 → 바로', B.needFor(def, 'score.add', { name: '밍밍', delta: 19 }) === null);
x = B.needFor(def, 'score.add', { name: '밍밍', delta: 20, list: 'list' });
chk('손 점수 20 → 묻는다', x && x.kind === 'hand' && x.rows[0].pts === 20, x);
chk('손 점수 제목: 밍밍 +20점 — 줄까요?', x && B.titleOf([x]) === '밍밍 +20점 — 줄까요?', x && B.titleOf([x]));
x = B.needFor(def, 'score.add', { name: '밍밍', delta: -30 });
chk('빼기 −30 도 묻는다 · 뺄까요?', x && B.titleOf([x]) === '밍밍 −30점 — 뺄까요?', x && B.titleOf([x]));
x = B.needFor(def, 'score.add', { target: 'bottom', delta: 50 });
chk('운영비 50 → 묻는다(이름 운영비)', x && x.rows[0].name === '운영비', x);
chk('기여도만 고치기 25 → 묻는다', !!B.needFor(def, 'score.add', { name: '밍밍', delta: 0, contrib: 25 }));
chk('기여도만 고치기 3 → 바로', B.needFor(def, 'score.add', { name: '밍밍', delta: 0, contrib: 3 }) === null);
chk('번외 판 표시', (B.needFor(def, 'score.add', { name: '밍밍', delta: 30, list: 'extra' }) || {}).extra === true);
chk('손 점수 기준 0 = 끔', B.needFor(S({ won: 200000, pts: 0 }), 'score.add', { name: '밍밍', delta: 99 }) === null);
chk('다른 명령은 상관없음', B.needFor(def, 'goal.set', { target: 999999 }) === null && B.needFor(def, 'pending.ignore', { id: 'p1' }) === null);
chk('여러 건 제목', B.titleOf([B.needFor(def, 'pending.assign', { id: 'p1', name: '밍밍' }), B.needFor(def, 'score.add', { name: '하율', delta: 30 })]) === '큰 점수 2건 — 모두 줄까요?');

// ── guardRun — [취소]면 명령이 안 간다 · [주기]면 간다 ──
async function trial(answer, type, data, opts, sl = def) {
    const sent = [], asked = [], cancelled = [];
    const run = async (t, d, o) => { sent.push([t, d, o]); return { ok: true }; };
    const g = B.guardRun(run, () => sl, async needs => { asked.push(needs); return answer; }, need => cancelled.push(need));
    const res = await g(type, data, opts);
    return { res, sent, asked, cancelled };
}
let t = await trial(false, 'pending.assign', { id: 'p1', name: '밍밍' });
chk('[취소] → 명령 안 감 · cancelled', t.sent.length === 0 && t.asked.length === 1 && t.res.ok === false && t.res.cancelled === true && t.cancelled.length === 1, t);
t = await trial(true, 'pending.assign', { id: 'p1', name: '밍밍' });
chk('[주기] → 명령 감(한 번)', t.sent.length === 1 && t.sent[0][0] === 'pending.assign' && t.asked.length === 1 && t.res.ok === true, t);
t = await trial(false, 'pending.assign', { id: 'p2', name: '밍밍' });
chk('기준 미만 → 묻지 않고 바로 감', t.sent.length === 1 && t.asked.length === 0, t);
t = await trial(false, 'pending.assign', { id: 'p1', name: '밍밍' }, { bigOk: true });
chk('이미 물어본 길(bigOk) → 다시 안 묻는다', t.sent.length === 1 && t.asked.length === 0 && t.sent[0][2].bigOk === true, t);
t = await trial(false, 'pending.assign', { id: 'p1', name: '밍밍', via: 'ap' }, { quiet: true });
chk('오토파일럿 → 안 묻고 감', t.sent.length === 1 && t.asked.length === 0, t);
t = await trial(false, 'score.add', { name: '밍밍', delta: 30 });
chk('손 점수 30 [취소] → 안 감', t.sent.length === 0 && t.asked.length === 1, t);
t = await trial(true, 'score.add', { name: '밍밍', delta: 30 }, { quiet: true });
chk('손 점수 30 [주기] → 감 · opts 그대로', t.sent.length === 1 && t.sent[0][2].quiet === true, t);
t = await trial(false, 'score.add', { name: '밍밍', delta: 5 });
chk('손 점수 5 → 바로', t.sent.length === 1 && t.asked.length === 0, t);
t = await trial(false, 'roulette.spin', {});
chk('점수 아닌 명령 → 바로', t.sent.length === 1 && t.asked.length === 0, t);
{   // 기준을 읽다가 넘어져도 명령은 막히지 않는다(조종실이 멈추면 안 된다)
    const sent = [];
    const g = B.guardRun(async a => { sent.push(a); return { ok: true }; }, () => { throw new Error('x'); }, async () => false);
    await g('score.add', { name: '밍밍', delta: 99 });
    chk('기준을 못 읽으면 그냥 보낸다', sent.length === 1);
}

// ── 글자 · 파일 약속 ──
const strip = s => s.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:'"])\/\/[^\n]*/g, '$1');
const src = strip(fs.readFileSync(path.join(js, 'bigok.js'), 'utf8'));
chk('bigok.js 에 confirm( · alert( · 소리 · innerHTML 없음', !/(^|[^.\w])confirm\(|window\.confirm|\balert\(|new Audio|\.play\(|innerHTML/.test(src));
const cards = fs.readFileSync(path.join(js, 'panels', 'ai', 'cards.js'), 'utf8');
chk('AI 카드 묶음은 한 상자로 묻고 bigOk 로 보낸다', /askBig\(ctx, bigs\)/.test(cards) && /runCard\(ctx, c, \{ bigOk: true \}\)/.test(cards));
chk('설정 글: 꺼짐 · 켬', B.stateText({ won: 0, pts: 0 }).includes('꺼져') && B.stateText({ won: 200000, pts: 20 }) === '지금: 후원 200,000원 이상 · 손 점수 20점 이상이면 한 번 더 물어요', B.stateText({ won: 200000, pts: 20 }));

console.log('DONE ' + n);
