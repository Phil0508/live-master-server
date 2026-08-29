/* 🎡 룰렛 원판이 방송 내내 도는가 — 상시 부담 검사.
 *
 * overlay.html 의 RouletteWidget 를 통째로 꺼내 가짜 캔버스 위에서 돌린다.
 * requestAnimationFrame 을 세어 '멈춘 뒤에도 계속 그리는가' 를 잰다.
 *
 * 왜 이걸 재는가: 연출은 가끔 터지지만 이 루프는 켜지면 안 꺼진다.
 * 3~4시간 방송에서 상시로 깔리는 부담은 연출보다 이쪽이 크다.
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
    return () => { drawCount++; };
  },
  set() { return true; },
});
const canvasStub = { width: 500, height: 500, getContext: () => ctxStub, style: {},
  classList: { add() {}, remove() {}, contains() { return false; } },
  innerText: '', textContent: '', appendChild() {}, remove() {} };
global.document = {
  getElementById: () => canvasStub,
  querySelector: () => canvasStub,
  createElement: () => canvasStub,
};
global.performance = { now: () => now };
global.requestAnimationFrame = function (fn) { rafCount++; queue.push(fn); return queue.length; };
global.cancelAnimationFrame = function () {};
global.fetch = function () { return { catch: function () {} }; };
global.confetti = undefined;
// render() 가 테두리 색을 여기서 읽는다
global.globalData = { theme: 'gold', roulette_enabled: true };

const R = eval('(' + objSrc + ')');

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
tick(4);                                   // 첫 그리기가 지나가게
const idleBefore = rafCount, drawBefore = drawCount;
const ran = tick(300);                     // 5초어치
chk('가만히 두면 스스로 잠든다', rafCount - idleBefore <= 2,
    '5초 동안 프레임 ' + (rafCount - idleBefore) + '번 (예전엔 300번)');
chk('잠든 동안에는 아무것도 안 그린다', drawCount - drawBefore === 0,
    (drawCount - drawBefore) + '번 그림');
chk('예약이 실제로 끊긴다', R.animationFrameId === null || R.animationFrameId === undefined,
    R.animationFrameId);

console.log();
hr('② 돌릴 때 — 제대로 도는가');
R.updateRoster([{ name: 'A' }, { name: 'B' }, { name: 'C' }], null);
tick(3);
const spinFrom = rafCount;
R.launch();
const spun = tick(60);                     // 1초어치
chk('돌리면 매 프레임 이어진다', rafCount - spinFrom >= 50,
    '1초에 ' + (rafCount - spinFrom) + '프레임');
chk('도는 동안 원판을 그린다', drawCount > drawBefore);

console.log();
hr('③ 멈춘 뒤 — 다시 잠드는가');
R.stop(-1);
tick(400);                                 // 넉넉히 흘려 멈추게
const restFrom = rafCount, restDraw = drawCount;
const after = tick(300);                   // 다시 5초
chk('멈추면 다시 잠든다', rafCount - restFrom <= 2,
    '5초 동안 프레임 ' + (rafCount - restFrom) + '번');
chk("'멈추는 중' 표시가 지워진다", !R.stopping, R.stopping);
chk('잠든 뒤에는 안 그린다', drawCount - restDraw === 0, (drawCount - restDraw) + '번');

console.log();
hr('④ 다시 깨우면 도는가');
const wakeFrom = rafCount;
R.updateRoster([{ name: 'A' }, { name: 'B' }], null);
tick(3);
chk('명단이 바뀌면 한 번 다시 그린다', rafCount - wakeFrom >= 1, rafCount - wakeFrom);
const sleep2 = rafCount;
tick(120);
chk('그리고 다시 잠든다', rafCount - sleep2 <= 2, rafCount - sleep2);

console.log();
hr('통과 ' + OK.length + ' · 실패 ' + BAD.length);
BAD.forEach(function (n) { console.log('   [실패] ' + n); });
console.log('='.repeat(74));
process.exit(0);
