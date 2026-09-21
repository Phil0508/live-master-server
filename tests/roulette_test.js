/* 🎡 룰렛 원판 — 상시 부담 + 제대로 서는가.
 *
 * overlay.html 의 RouletteWidget 를 통째로 꺼내 가짜 캔버스 위에서 돌린다.
 * requestAnimationFrame 을 세어 '멈춘 뒤에도 계속 도는가' 를 잰다.
 *
 * 왜 이걸 재는가: 연출은 가끔 터지지만 이 루프는 켜지면 안 꺼진다.
 * 3~4시간 방송에서 상시로 깔리는 부담은 연출보다 이쪽이 크다.
 *
 * 2026-09-21 귀여운 금테 판으로 바꾸면서 더 본다:
 *   · 원판은 칸이 바뀔 때만 그린다 — 도는 동안에는 캔버스를 돌리기만 한다
 *   · 조종실이 정한 칸에 정확히 선다
 *   · 창이 여러 개여도(같은 정지 시각) 모두 같은 칸에 선다
 *   · 정지를 누르고 5초 안에 선다 (원본 룰렛과 같은 느낌)
 */
'use strict';
const fs = require('fs');
const path = require('path');

const OK = [], BAD = [];
function chk(name, cond, detail) {
  (cond ? OK : BAD).push(name);
  console.log((cond ? '  [OK] ' : '  [!!] ') + name +
    (detail !== undefined && detail !== '' ? '  -- ' + String(detail).slice(0, 110) : ''));
}
function hr(t) { console.log('='.repeat(74)); console.log(t); console.log('='.repeat(74)); }

const SRC = [path.join(__dirname, '..', 'overlay.html'),
             'C:/Users/Administrator/Desktop/새로다시시작/overlay.html']
            .filter(function (p) { return fs.existsSync(p); })[0];
if (!SRC) { console.log('  [!!] overlay.html 을 못 찾았다'); process.exit(1); }
const html = fs.readFileSync(SRC, 'utf8');

/* ── RouletteWidget 객체만 잘라낸다 (괄호 짝을 세어서) ── */
const at = html.indexOf('const RouletteWidget = {');
if (at < 0) { console.log('  [!!] RouletteWidget 을 못 찾았다'); process.exit(1); }
let i = html.indexOf('{', at), depth = 0, end = -1;
for (let j = i; j < html.length; j++) {
  const c = html[j];
  if (c === '{') depth++;
  else if (c === '}') { depth--; if (depth === 0) { end = j; break; } }
}
const objSrc = html.slice(i, end + 1);

/* ── 가짜 캔버스·시계 ── */
let rafCount = 0, drawCount = 0, now = 0;
const queue = [];
const ctxStub = new Proxy({}, {
  get(t, p) {
    if (p === 'canvas') return {};
    if (p === 'measureText') return () => ({ width: 10 });
    if (p === 'createRadialGradient' || p === 'createLinearGradient') return () => ({ addColorStop() {} });
    return () => { drawCount++; };
  },
  set() { return true; },
});
function el() {
  return { width: 500, height: 500, getContext: () => ctxStub,
    style: { setProperty() {} }, childElementCount: 0,
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    innerText: '', textContent: '', appendChild() { this.childElementCount++; }, setAttribute() {}, remove() {},
    get offsetWidth() { return 1; } };
}
const els = {};
global.document = {
  getElementById: (id) => (els[id] = els[id] || el()),
  querySelector: () => el(),
  createElement: () => el(),
  createElementNS: () => el(),
  fonts: { load: () => ({ then: () => ({ catch() {} }) }) },
};
global.window = { sfxEnabled: false };
global.performance = { now: () => now };
global.requestAnimationFrame = function (fn) { rafCount++; queue.push(fn); return queue.length; };
global.cancelAnimationFrame = function () {};
let reported = [];
global.fetch = function (u, o) { reported.push(JSON.parse(o.body).name); return { catch: function () {} }; };
global.confetti = undefined;
global.setTimeout = function () { return 0; };
global.clearTimeout = function () {};
global.globalData = { roulette_enabled: true };

function make() { return eval('(' + objSrc + ')'); }
const R = make();

/* 프레임을 n 번 흘린다 (한 프레임 16ms) */
function tick(n) {
  for (let k = 0; k < n; k++) {
    now += 16;
    const batch = queue.splice(0, queue.length);
    if (!batch.length) return k;          // 아무도 다음 프레임을 안 부르면 잠든 것
    // ⚠️ 예외를 삼키면 '루프가 잠들었다' 와 '루프가 터졌다' 를 못 가린다
    batch.forEach(function (fn) {
      try { fn(now); }
      catch (e) { if (!tick.err) { tick.err = e; console.log('   [예외] ' + e.message); } }
    });
  }
  return n;
}

hr('① 켜자마자 — 원판이 서 있을 때');
R.init();
tick(4);
const idleBefore = rafCount, drawBefore = drawCount;
tick(300);                                 // 5초어치
chk('가만히 두면 프레임을 안 돌린다', rafCount - idleBefore <= 1,
    '5초 동안 프레임 ' + (rafCount - idleBefore) + '번 (예전엔 300번)');
chk('서 있는 동안에는 아무것도 안 그린다', drawCount - drawBefore === 0, (drawCount - drawBefore) + '번 그림');

console.log();
hr('② 돌릴 때 — 원판은 다시 안 그리고 돌리기만 한다');
R.updateRoster([{ name: 'A' }, { name: 'B' }, { name: 'C' }], null);
chk('명단이 바뀌면 그 자리에서 한 번 그린다', drawCount > drawBefore);
const spinFrom = rafCount, spinDraw = drawCount;
R.launch();
tick(60);                                  // 1초어치
chk('돌리면 매 프레임 이어진다', rafCount - spinFrom >= 50, '1초에 ' + (rafCount - spinFrom) + '프레임');
chk('도는 동안 칸을 다시 그리지 않는다 (캔버스를 돌리기만)', drawCount === spinDraw, (drawCount - spinDraw) + '번 그림');
chk('실제로 돈다', R.rotation > 300, R.rotation);
const r1 = R.rotation; tick(1);
chk('최고 속도는 초당 2바퀴를 안 넘는다', R.rotation - r1 < 720 * 0.016 + 0.01, (R.rotation - r1).toFixed(2));

console.log();
hr('③ 정지 — 정한 칸에, 5초 안에 선다');
reported = [];
const stopAt = now;
R.stop(1, 1726900000123);                  // B 칸으로
tick(400);
const took = (now - stopAt) / 1000;
chk('정지 누르고 5초 안에 선다', !R.isRolling && took < 5, '서기까지 ' + took.toFixed(2) + '초');
chk('정한 칸(B)에 섰다', R.current === 'B', R.current);
chk('당첨을 한 번만 보고한다', reported.length === 1 && reported[0] === 'B', JSON.stringify(reported));
chk("'멈추는 중' 표시가 지워진다", !R.stopping, R.stopping);
chk('각도를 0~360 으로 되돌려 둔다', R.rotation >= 0 && R.rotation < 360, R.rotation);
const restFrom = rafCount, restDraw = drawCount;
tick(300);
chk('멈추면 프레임을 안 돌린다', rafCount - restFrom <= 1, '5초 동안 프레임 ' + (rafCount - restFrom) + '번');
chk('선 뒤에는 안 그린다', drawCount - restDraw === 0, (drawCount - restDraw) + '번');

console.log();
hr('④ 창이 둘이어도 같은 칸 — 정지 시각이 씨앗');
const names = ['얼음물', '애교', '팔굽혀펴기 20개', '노래 한 소절', '꽝', '벌칙 면제'].map(n => ({ name: n }));
function runOne(spinFrames, seed) {
  const W = make(); W.init(); W.updateRoster(names, 'equal');
  W.launch(); tick(spinFrames);
  W.stop(-1, seed); tick(500);
  return W.current;
}
const same = [];
for (const seed of [111, 222222, 1726900000999, 1726912345678]) {
  const a = runOne(37, seed), b = runOne(83, seed);    // 서로 다른 순간에 정지를 받는다
  same.push(a === b ? 'OK' : (a + '≠' + b));
}
chk('다른 창 · 다른 순간이어도 같은 칸에 선다', same.every(x => x === 'OK'), same.join(' '));
const seen = new Set();
for (let s = 1; s <= 60; s++) seen.add(runOne(10, s * 7919));
chk('무작위일 때 여러 칸이 고루 나온다', seen.size >= 5, [...seen].join(','));

console.log();
hr('⑤ 초기화');
R.launch(); tick(20); R.reset();
const rs = rafCount; tick(60);
chk('초기화하면 서고 프레임도 멈춘다', !R.isRolling && R.rotation === 0 && rafCount - rs <= 1, rafCount - rs);

console.log();
hr('통과 ' + OK.length + ' · 실패 ' + BAD.length);
BAD.forEach(function (n) { console.log('   [실패] ' + n); });
console.log('='.repeat(74));
process.exit(BAD.length ? 1 : 0);
