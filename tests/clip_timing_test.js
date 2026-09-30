/* ✂️ 쇼츠 클립 — 누른 순간 앞 90초 + 뒤 90초가 담기는 때에 저장하는가.
 *
 * 대표님(2026-09-30): "영상클립 누르는 순간기준 전 90초~ 후 90초 까지 저장으로 바꿔줘"
 *
 * OBS 리플레이 버퍼는 '저장한 순간까지의 N초' 만 떨군다. 그래서 순간에서 90초 뒤에 저장해야
 * 버퍼 180초 = 앞 90초 + 뒤 90초가 된다. overlay.html 의 클립 코드를 통째로 꺼내
 * 가짜 OBS · 가짜 시계 위에서 돌려 '언제 저장하나' 를 잰다(베낀 흉내가 아니라 실제 함수를 부른다).
 *
 *   · 누르고 90초 뒤에 한 번 저장 — 그 전엔 저장 안 한다
 *   · 30초 안에 붙은 두 순간은 파일 하나(뒤 순간 +90초) · 먼 순간은 따로
 *   · 기다리는 사이 방송판이 새로고침돼도 되살려 저장한다 · 너무 오래된 것은 버린다
 *   · 권한이 낮거나 OBS 밖이면 아무 일도 안 한다
 *   · 저장이 확인되면 무엇을 저장했나(열쇠)를 서버에 알린다
 */
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const OK = [], BAD = [];
function chk(name, cond, detail) {
  (cond ? OK : BAD).push(name);
  console.log((cond ? '  [OK] ' : '  [!!] ') + name +
    (detail !== undefined && detail !== '' ? '  -- ' + String(detail).slice(0, 120) : ''));
}
function hr(t) { console.log('='.repeat(74)); console.log(t); console.log('='.repeat(74)); }

const SRC = [path.join(__dirname, '..', 'overlay.html'),
             'C:/Users/Administrator/Desktop/새로다시시작/overlay.html']
            .filter(function (p) { return fs.existsSync(p); })[0];
if (!SRC) { console.log('  [!!] overlay.html 을 못 찾았다'); process.exit(1); }
const OV = fs.readFileSync(SRC, 'utf8');
const a = OV.indexOf("/* ✂️ 쇼츠 클립 — 이 방송판이 OBS 의 '리플레이 버퍼 저장' 담당이다");
const b = OV.indexOf('function clipAuto() {', a);
if (a < 0 || b < 0) { console.log('  [!!] 클립 코드를 못 찾았다'); process.exit(1); }
const BLOCK = OV.slice(a, b);

// ── 가짜 시계 · 가짜 OBS · 가짜 저장소 ──
let NOW = 1790000000000;
const STORE = {};   // 방송판(OBS 안) 저장소 — 새로고침해도 남는다
function makePage(level, withObs) {
  const timers = [];
  let seq = 0;
  const saves = [], hellos = [];
  const obs = {
    getControlLevel: function (cb) { cb(level); },
    getStatus: function (cb) { cb({ replaybuffer: true }); },
    startReplayBuffer: function () {},
    saveReplayBuffer: function () { saves.push(NOW); },
  };
  const ctx = {
    window: withObs ? { obsstudio: obs } : {},
    console: { log: function () {} },
    Date: { now: function () { return NOW; } },
    JSON: JSON, Math: Math, Number: Number, String: String, Array: Array, Object: Object,
    setTimeout: function (fn, ms) { const id = ++seq; timers.push({ id: id, at: NOW + Math.max(0, ms || 0), fn: fn }); return id; },
    clearTimeout: function (id) { const i = timers.findIndex(function (t) { return t.id === id; }); if (i >= 0) timers.splice(i, 1); },
    localStorage: { getItem: function (k) { return k in STORE ? STORE[k] : null; }, setItem: function (k, v) { STORE[k] = String(v); } },
    fetch: function (url, opt) { hellos.push(JSON.parse(opt.body)); return { catch: function () {} }; },
  };
  vm.createContext(ctx);
  vm.runInContext(BLOCK + '\n;this.__clip = { CLIP: CLIP, clipSave: clipSave, clipCheck: clipCheck, CLIP_AFTER: CLIP_AFTER };', ctx);
  const api = ctx.__clip;
  // 시간을 ms 만큼 흘린다 — 그 사이 걸린 타이머를 순서대로 부른다
  api.advance = function (ms) {
    const end = NOW + ms;
    for (;;) {
      timers.sort(function (x, y) { return x.at - y.at; });
      const t = timers[0];
      if (!t || t.at > end) break;
      timers.shift();
      NOW = t.at;
      t.fn();
    }
    NOW = end;
  };
  api.saves = saves; api.hellos = hellos;
  return api;
}
const sec = function (s) { return s * 1000; };

hr('① 누르고 90초 뒤에 한 번');
STORE.lm_clip_pend = '[]';
let P = makePage(4, true);
P.clipCheck();
chk('뒤로 기다리는 시간 = 90초', P.CLIP_AFTER === 90000, P.CLIP_AFTER);
let t0 = NOW;
P.clipSave(P.CLIP_AFTER, '조종실', 'c1');
P.advance(sec(89));
chk('89초까지는 저장 안 한다(뒤 90초를 기다린다)', P.saves.length === 0, P.saves.length);
P.advance(sec(2));
chk('90초에 저장 — 버퍼 180초 = 앞 90초 + 뒤 90초', P.saves.length === 1 && P.saves[0] - t0 === 90000, P.saves.map(function (x) { return x - t0; }));
P.advance(sec(5));
const h = P.hellos.filter(function (x) { return x.saved; });
chk('저장 뒤 무엇을 저장했나(열쇠)를 서버에 알린다', h.length === 1 && JSON.stringify(h[0].refs) === '["c1"]', JSON.stringify(h));
chk('기다리던 목록이 비었다(저장소도)', P.CLIP.pend.length === 0 && STORE.lm_clip_pend === '[]', STORE.lm_clip_pend);

hr('② 붙은 순간은 파일 하나 · 먼 순간은 따로');
P = makePage(4, true); P.clipCheck(); t0 = NOW;
P.clipSave(P.CLIP_AFTER, 'a', 'a');
P.advance(sec(20));
P.clipSave(P.CLIP_AFTER, 'b', 'b');           // 20초 뒤 — 붙었다
P.advance(sec(200));
let hs = P.hellos.filter(function (x) { return x.saved; });
chk('20초 안의 두 순간 → 저장 한 번, 뒤 순간 +90초(110초)', P.saves.length === 1 && P.saves[0] - t0 === 110000, P.saves.map(function (x) { return x - t0; }));
chk('열쇠 둘이 그 파일 하나에', hs.length === 1 && JSON.stringify(hs[0].refs) === '["a","b"]', JSON.stringify(hs));
P = makePage(4, true); P.clipCheck(); t0 = NOW;
P.clipSave(P.CLIP_AFTER, 'a', 'a');
P.advance(sec(60));
P.clipSave(P.CLIP_AFTER, 'b', 'b');           // 60초 뒤 — 멀다
P.advance(sec(300));
chk('60초 떨어진 두 순간 → 따로 두 번(90초 · 150초)', P.saves.length === 2 && P.saves[0] - t0 === 90000 && P.saves[1] - t0 === 150000,
    P.saves.map(function (x) { return x - t0; }));
P = makePage(4, true); P.clipCheck(); t0 = NOW;
P.clipSave(P.CLIP_AFTER, 'a', 'a');
P.advance(sec(10));
P.clipSave(P.CLIP_AFTER, 'a', 'a');           // 같은 것을 또
P.advance(sec(200));
hs = P.hellos.filter(function (x) { return x.saved; });
chk('같은 열쇠는 한 번만 적는다', P.saves.length === 1 && JSON.stringify(hs[0].refs) === '["a"]', JSON.stringify(hs));

hr('③ 기다리는 사이 방송판이 새로고침돼도');
STORE.lm_clip_pend = '[]';
P = makePage(4, true); P.clipCheck(); t0 = NOW;
P.clipSave(P.CLIP_AFTER, '조종실', 'r1');
P.advance(sec(30));                            // 30초 뒤 새로고침 — 옛 방송판은 사라진다
let Q = makePage(4, true);
chk('새 방송판은 권한을 확인하기 전엔 아무것도 안 건다', Q.CLIP.pend.length === 0);
Q.clipCheck();
chk('권한 확인 순간 기다리던 저장을 되살린다', Q.CLIP.pend.length === 1 && JSON.stringify(Q.CLIP.pend[0].refs) === '["r1"]', JSON.stringify(Q.CLIP.pend));
Q.advance(sec(100));
chk('원래 시각(90초)에 저장한다', Q.saves.length === 1 && Q.saves[0] - t0 === 90000, Q.saves.map(function (x) { return x - t0; }));
STORE.lm_clip_pend = '[]';
P = makePage(4, true); P.clipCheck(); t0 = NOW;
P.clipSave(P.CLIP_AFTER, '조종실', 'r2');
Q = makePage(4, true);   // 옛 방송판은 곧바로 꺼졌다고 친다(그 타이머는 안 돈다)
NOW = t0 + sec(120);   // 새로고침이 2분 뒤에 끝났다 — 저장 시각(90초)은 30초 지났다
Q.clipCheck(); Q.advance(sec(1));
chk('저장 시각이 지났으면 바로 저장(버퍼 180초 안이라 뒤쪽은 다 있다)', Q.saves.length === 1 && Q.saves[0] - t0 <= sec(121), Q.saves.map(function (x) { return x - t0; }));
STORE.lm_clip_pend = JSON.stringify([{ due: NOW - sec(200), first: NOW - sec(200), refs: ['old'] }]);
Q = makePage(4, true); Q.clipCheck(); Q.advance(sec(10));
chk('저장 시각이 2분 30초 넘게 지난 것은 버린다(버퍼에 거의 없다)', Q.saves.length === 0 && Q.CLIP.pend.length === 0, STORE.lm_clip_pend);
STORE.lm_clip_pend = '{깨진';
Q = makePage(4, true); Q.clipCheck(); Q.advance(sec(1));
chk('저장소가 깨져 있어도 멈추지 않는다', Q.saves.length === 0 && Q.CLIP.level === 4);

hr('④ 권한 · OBS 밖');
STORE.lm_clip_pend = '[]';
P = makePage(3, true); P.clipCheck();
P.clipSave(P.CLIP_AFTER, 'x', 'x'); P.advance(sec(200));
chk('권한이 고급(4)보다 낮으면 저장 안 한다', P.saves.length === 0 && STORE.lm_clip_pend === '[]');
P = makePage(4, false); P.clipCheck();
P.clipSave(P.CLIP_AFTER, 'x', 'x'); P.advance(sec(200));
chk('OBS 밖(미리보기 · 폰)에서는 아무 일도 안 한다', P.saves.length === 0 && P.hellos.length === 0);

hr('⑤ 부르는 곳 — 전부 90초 뒤');
chk('조종실 [✂ 클립]', OV.indexOf("clipSave(CLIP_AFTER + (Number(d.delay_ms) || 0), d.label || '조종실', d.id)") >= 0);
chk('큰 시그', OV.indexOf("clipSave(CLIP_AFTER, (data.donator || '') + ' ' + data.amount, data.id)") >= 0);
chk('시그뒤집기 올클리어', OV.indexOf("clipSave(CLIP_AFTER, '올클리어', 'allclear:' + act.ts)") >= 0);

console.log();
hr('통과 ' + OK.length + ' · 실패 ' + BAD.length);
BAD.forEach(function (n) { console.log('   [실패] ' + n); });
console.log('='.repeat(74));
process.exit(BAD.length ? 1 : 0);
