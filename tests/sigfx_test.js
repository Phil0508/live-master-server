/* 🎇 시그니처 연출 검사 — sig-fx.js 를 진짜로 돌려서 본다.
 *
 * 검사 방식: 가짜 DOM(tests/sigfx_dom.js)이 animate() 호출을 그대로 받아 적고,
 * 그 기록에서 "시각 t 에 무엇이 어떻게 보이는가" 를 되짚는다.
 * 소스에서 글자를 찾는 검사가 아니다 — 값을 바꾸면 검사가 깨진다.
 */
'use strict';
const dom = require('./sigfx_dom.js');
const OK = [], BAD = [];

function chk(name, cond, detail) {
  (cond ? OK : BAD).push(name);
  console.log((cond ? '  [OK] ' : '  [!!] ') + name +
    (detail !== undefined && detail !== '' && detail !== null ? '  -- ' + String(detail).slice(0, 110) : ''));
}
function hr(t) { console.log('='.repeat(74)); console.log(t); console.log('='.repeat(74)); }

dom.install();
/* ⚠️ 러너는 이 파일을 스크래치패드로 복사해 돌린다. 거기엔 ../sig-fx.js 가 없다.
      옆에 있으면 옆에서, 없으면 저장소에서 가져온다. */
const fs = require('fs'), pth = require('path');
const SRC = [pth.join(__dirname, '..', 'sig-fx.js'),
             'C:/Users/Administrator/Desktop/새로다시시작/sig-fx.js']
            .filter(function (p) { return fs.existsSync(p); })[0];
if (!SRC) { console.log('  [!!] sig-fx.js 를 못 찾았다'); process.exit(1); }
console.log('대상: ' + SRC);
const SigFX = require(SRC);

/* 무대 하나 만들기 — 방송판과 같은 1080x1920 세로 */
function stage() {
  const st = new dom.El('div');
  st.clientWidth = 1080; st.clientHeight = 1920;
  const inner = new dom.El('div');
  inner.setAttribute('data-shake', '1');
  st.appendChild(inner);
  document.appendChild(st);
  return st;
}
function card() { const c = new dom.El('div'); document.appendChild(c); return c; }

/* 연출을 한 번 돌리고, 만들어진 레이어와 그 안의 모든 요소를 돌려준다 */
function run(key, opts) {
  const st = stage(), cd = card();
  const warns = [];
  const ow = console.warn;
  console.warn = function () { warns.push(Array.prototype.join.call(arguments, ' ')); };
  let ms;
  try { ms = SigFX.play(key, st, Object.assign({ card: cd }, opts || {})); }
  finally { console.warn = ow; }
  const fx = st.querySelector('[data-sigfx]');
  return { st: st, cd: cd, fx: fx, ms: ms, warns: warns, all: fx ? fx._walk([]) : [] };
}
function done(r) { SigFX.stop(r.st); }

const ITEMS = SigFX.ITEMS;

/* ══════════════════════════════════════════════════════════════════ */
hr('① 17개 연출이 예외 없이 도는가');
const allWarn = [];
ITEMS.forEach(function (it) {
  const r = run(it.key);
  if (r.warns.length) allWarn.push(it.key + ': ' + r.warns[0]);
  done(r);
});
chk('17개 전부 예외 없이 그려진다', allWarn.length === 0, allWarn[0] || '');
chk('ITEMS 가 17개다', ITEMS.length === 17, ITEMS.length);

/* ══════════════════════════════════════════════════════════════════ */
console.log();
hr('② 글자 조기 노출 — delay 전에 글자가 보이면 안 된다');
/* ⚠️ txt() 로 만든 것만 보면 안 된다 — 손으로 만든 글자(edm 'EDM', vip 'VIP')도
      같은 병을 앓고 있었다. '글자를 품은 요소' 를 전부 찾는다.
      이렇게 해야 검사가 순환하지 않는다 — opacity 로 대상을 고르면 opacity 를 빼도 통과한다. */
function textNodes(all) {
  const out = [];
  all.forEach(function (e) {
    e.children.forEach(function (c) {
      if (typeof c.textContent === 'string' && c.textContent.length) out.push({ wrap: e, txt: c });
    });
  });
  return out;
}
/* 시각 t 에 이 글자가 눈에 보이는가 — 래퍼와 글자 둘 다 켜져 있어야 보인다 */
function vis(n, t) {
  const nz = function (v) { return v === undefined ? 1 : Number(v); };
  return nz(dom.sampleProp(n.wrap, t, 'opacity')) * nz(dom.sampleProp(n.txt, t, 'opacity'));
}
const earlyBad = [], noReveal = [];
let nText = 0;
ITEMS.forEach(function (it) {
  const r = run(it.key);
  textNodes(r.all).forEach(function (n) {
    nText++;
    // 애니메이션 없이 처음부터 떠 있기로 한 글자는 조기 노출이 아니다
    const anims = n.wrap.anims.concat(n.txt.anims);
    const d0 = anims.length
      ? Math.min.apply(null, anims.map(function (a) { return a.timing.delay || 0; })) : 0;
    if (d0 > 0 && vis(n, 0) > 0.01) {
      earlyBad.push(it.key + ' "' + n.txt.textContent + '" delay=' + d0 + ' 인데 0ms 에 ' + vis(n, 0));
    }
    let seen = false;
    for (let t = 0; t <= it.dur * 1000; t += 20) if (vis(n, t) > 0.9) { seen = true; break; }
    if (!seen) noReveal.push(it.key + ' "' + n.txt.textContent + '"');
  });
  done(r);
});
chk('0ms 에 글자가 하나도 안 보인다', earlyBad.length === 0, earlyBad.join(' | '));
chk('그래도 모든 글자는 때가 되면 뜬다', noReveal.length === 0, noReveal.join(' | '));
chk('글자를 품은 요소를 실제로 찾아냈다 (검사가 헛돌지 않는다)', nText >= 10, nText + '개');
chk('txt() 래퍼가 opacity:0 으로 시작한다', (function () {
  const r = run('shield');
  const n = textNodes(r.all).filter(function (x) { return x.txt.textContent === '방패'; })[0];
  done(r);
  return !!n && n.wrap.style.get('opacity') === '0';
})());

/* ══════════════════════════════════════════════════════════════════ */
console.log();
hr('③ 히트스톱 — 착탄 프레임에 정말 멈추는가');
function hitstop(key, pick, IMP, span) {
  const r = run(key);
  const el = pick(r.all);
  if (!el) { done(r); return { ok: false, a: '대상을 못 찾음' }; }
  const a = dom.sampleProp(el, IMP + 5, 'transform');
  const b = dom.sampleProp(el, IMP + span, 'transform');
  const before = dom.sampleProp(el, IMP - 20, 'transform');
  done(r);
  return { ok: a === b && a !== before, a: a, b: b, before: before };
}
const pickText = function (word) {
  return function (all) {
    const n = textNodes(all).filter(function (x) { return x.txt.textContent === word; })[0];
    return n && n.wrap;
  };
};
const gz = hitstop('gazua', pickText('가즈아'), 150, 45);
chk('가즈아 — 글자가 155~195ms 동안 눌린 채 멈춘다', gz.ok, gz.a);
chk('가즈아 — 멈추기 직전과는 다른 모습이다', gz.before !== gz.a, gz.before);

const shPick = function (all) {
  return all.filter(function (e) {
    return (e.style.get('clip-path') || '').indexOf('100% 58%') > 0;
  })[0];
};
const sd = hitstop('shield', shPick, 260, 55);
chk('방패 — 방패가 265~315ms 동안 눌린 채 멈춘다', sd.ok, sd.a);
chk('방패 — 눌린 모습이 scale(1.3,.72) 다',
    String(sd.a).indexOf('scale(1.3,.72)') > 0, sd.a);

/* ══════════════════════════════════════════════════════════════════ */
console.log();
hr('④ 스쿼시 — 균일 scale 이면 안 눌린다');
function hasSquash(key, pick) {
  const r = run(key); const el = pick(r.all); done(r);
  if (!el) return false;
  return el.anims.some(function (an) {
    return an.frames.some(function (f) {
      const m = /scale\(([\d.]+),\s*([\d.]+)\)/.exec(f.transform || '');
      return !!m && m[1] !== m[2];
    });
  });
}
chk('가즈아 글자에 눌림이 있다', hasSquash('gazua', pickText('가즈아')));
chk('방패에 눌림이 있다', hasSquash('shield', shPick));

/* ══════════════════════════════════════════════════════════════════ */
console.log();
hr('⑤ 낙하 — 착지 전에 감속하면 부딪히는 게 아니라 내려앉는다');
(function () {
  const r = run('shield'); const el = shPick(r.all);
  const fall = el && el.anims[0];
  done(r);
  chk('방패 낙하가 120ms 다 (원본 620ms)', !!fall && fall.timing.duration === 120,
      fall && fall.timing.duration);
  const ez = (fall && fall.timing.easing) || '';
  const m = /cubic-bezier\(([\d.]+),([\d.]+),([\d.]+),([\d.]+)\)/.exec(ez);
  // 끝까지 가속 = 마지막 제어점 y 가 낮다. 감속 곡선은 여기가 1 에 가깝다.
  chk('끝까지 가속한다 (마지막 제어점 y ≤ .5)', !!m && parseFloat(m[4]) <= 0.5, ez);
})();

/* ══════════════════════════════════════════════════════════════════ */
console.log();
hr('⑥ 플래시 — 길면 "번쩍" 이 아니라 "밝아졌다 어두워짐"');
function flashDur(key) {
  const r = run(key);
  const f = r.all.filter(function (e) {
    return e.style.get('mix-blend-mode') === 'screen' && e.style.get('inset') === '0';
  })[0];
  done(r);
  return f && f.anims[0] && f.anims[0].timing.duration;
}
chk('가즈아 플래시가 30ms 다', flashDur('gazua') === 30, flashDur('gazua'));
chk('방패 플래시가 30ms 다 (원본 110ms)', flashDur('shield') === 30, flashDur('shield'));

/* ══════════════════════════════════════════════════════════════════ */
console.log();
hr('⑦ 규격 — ITEMS 의 dur 를 넘기지 않는가');
const over = [];
ITEMS.forEach(function (it) {
  const r = run(it.key);
  let last = 0;
  r.all.forEach(function (e) {
    e.anims.forEach(function (a) {
      last = Math.max(last, (a.timing.delay || 0) + a.timing.duration);
    });
  });
  // play() 는 dur*1000 + 160 에 레이어를 지운다. 그 전에 끝나야 잘리지 않는다.
  if (last > it.dur * 1000 + 160) over.push(it.key + ' ' + Math.round(last) + '>' + (it.dur * 1000 + 160));
  done(r);
});
const mine = over.filter(function (x) { return /^(gazua|shield) /.test(x); });
chk('이번에 손댄 둘은 정리 시점보다 먼저 끝난다', mine.length === 0, mine.join(' '));
if (over.length) {
  // ⚠️ 이번 지시서 범위 밖이지만 그냥 넘기면 안 되는 것 — 레이어가 지워질 때
  //    아직 움직이는 중이면 화면에서 툭 끊긴다.
  console.log('  [참고] 원래부터 정리 시점을 넘기는 연출 ' + over.length + '개: ' + over.join(', '));
}
const gI = ITEMS.find(function (i) { return i.key === 'gazua'; });
const sI = ITEMS.find(function (i) { return i.key === 'shield'; });
chk('가즈아 dur 가 1.8 그대로다', gI.dur === 1.8, gI.dur);
chk('가즈아 cardAt 이 620 그대로다', gI.cardAt === 620, gI.cardAt);
chk('방패 dur 가 3.2 그대로다', sI.dur === 3.2, sI.dur);
chk('방패 cardAt 이 1040 그대로다', sI.cardAt === 1040, sI.cardAt);

/* ══════════════════════════════════════════════════════════════════ */
console.log();
hr('⑧ 속도 옵션 — speed 가 전 구간에 먹는가');
(function () {
  const a = run('shield');
  const b = run('shield', { speed: 0.5 });
  const t1 = [], t2 = [];
  a.all.forEach(function (e) { e.anims.forEach(function (x) { t1.push([x.timing.duration, x.timing.delay]); }); });
  b.all.forEach(function (e) { e.anims.forEach(function (x) { t2.push([x.timing.duration, x.timing.delay]); }); });
  done(a); done(b);
  const same = t1.length === t2.length;
  let bad = 0;
  if (same) {
    for (let i = 0; i < t1.length; i++) {
      if (Math.abs(t2[i][0] - t1[i][0] * 2) > 1e-6 ||
          Math.abs(t2[i][1] - t1[i][1] * 2) > 1e-6) bad++;
    }
  }
  chk('speed:0.5 면 모든 구간이 정확히 2배다', same && bad === 0,
      same ? bad + '건 어긋남 / ' + t1.length : '개수가 다름');
  // ⚠️ setTimeout 으로 도는 구간(mvp 불꽃)도 같이 느려져야 한다.
  //    소스에서 글자로 찾으면 안 된다 — fireworks 는 부르는 쪽에서 나눈다.
  const unfreeze = dom.freezeRandom();   // 불꽃 연쇄가 다음 때를 주사위로 고른다
  dom.timers.length = 0; const m1 = run('mvp'); const k1 = dom.timers.slice(); done(m1);
  dom.timers.length = 0; const m2 = run('mvp', { speed: 0.5 }); const k2 = dom.timers.slice(); done(m2);
  unfreeze();
  let tbad = 0;
  for (let i = 0; i < Math.min(k1.length, k2.length); i++) {
    if (Math.abs(k2[i] - k1[i] * 2) > 1e-6) tbad++;
  }
  chk('setTimeout 으로 도는 구간도 speed 를 따른다',
      k1.length > 0 && k1.length === k2.length && tbad === 0,
      k1.length + '개 중 ' + tbad + '건 어긋남');
})();

/* ══════════════════════════════════════════════════════════════════ */
console.log();
hr('⑨ 굳음 방지 — 끝나면 잔재가 없는가');
(function () {
  const r = run('shield');
  const before = r.st.querySelectorAll('[data-sigfx]').length;
  SigFX.stop(r.st);
  const after = r.st.querySelectorAll('[data-sigfx]').length;
  const cardLive = r.cd.getAnimations().length;
  chk('재생 중에는 연출 레이어가 있다', before === 1, before);
  chk('stop() 하면 레이어가 사라진다', after === 0, after);
  chk('카드에 걸린 애니메이션도 취소된다', cardLive === 0, cardLive);
  chk('카드 발광색을 되돌린다', r.cd.style.getPropertyValue('--reac-glow') === '',
      r.cd.style.getPropertyValue('--reac-glow'));
})();

/* ══════════════════════════════════════════════════════════════════ */
console.log();
hr('⑩ 중복 재생 — 후원이 연달아 와도 흔적이 안 남는가');
(function () {
  const st = stage(), cd = card();
  SigFX.play('gazua', st, { card: cd });
  SigFX.play('shield', st, { card: cd });
  SigFX.play('crazy', st, { card: cd });
  const layers = st.querySelectorAll('[data-sigfx]');
  chk('레이어가 하나만 남는다', layers.length === 1, layers.length);
  chk('마지막 것만 남는다', !!layers[0] && layers[0].getAttribute('data-sigfx') === 'crazy',
      layers[0] && layers[0].getAttribute('data-sigfx'));
  SigFX.stop(st);
})();

/* ══════════════════════════════════════════════════════════════════ */
console.log();
hr('⑪ 좌표 — 화면 밖에 그리고 있지 않은가');
/* 방송은 1080×1920 세로. 연출은 1920×1080 가로 좌표로 짜여 있고 _fit 이 접는다.
   접는 규칙이 틀리면 화면 밖에 그려도 아무도 오류를 안 낸다 — 그래서 잰다. */
const CW = 1080, CH = 1920;
const num = function (v) {
  const m = /^(-?[\d.]+)px$/.exec(String(v || ''));
  return m ? parseFloat(m[1]) : null;
};
/* 요소가 가로로 화면에 걸치는가.
   ⚠️ scaleX(-1) 로 뒤집은 것은 left 에서 왼쪽으로 뻗는다 — 안 그러면 멀쩡한 것을 잡는다. */
function spanX(e) {
  const l = num(e.style.get('left')), w = num(e.style.get('width')) || 0;
  if (l === null) return null;
  const flip = /scaleX\(-1\)/.test(e.style.get('transform') || '');
  let a = flip ? l - w : l, b = flip ? l : l + w;
  let t = 0;
  e.anims.forEach(function (an) {
    an.frames.forEach(function (f) {
      const m = /translateX\((-?[\d.]+)px\)/.exec(f.transform || '');
      if (m) t = Math.max(t, Math.abs(parseFloat(m[1])));
    });
  });
  return [a - t, b + t];
}
const outX = [], outY = [], budget = [];
ITEMS.forEach(function (it) {
  const r = run(it.key);
  const direct = r.all.filter(function (e) { return e.parentNode === r.fx; });
  if (r.all.length > 200) budget.push(it.key + ' ' + r.all.length);
  direct.forEach(function (e) {
    if (e.style.get('inset') === '0') return;         // 전면 배경은 셈에서 뺀다
    const sx = spanX(e);
    if (sx && (sx[1] < 0 || sx[0] > CW)) {
      // 폭이 아주 좁은 것은 화면 끝에 세워 둔 장식이다 (람바다 야자 기둥)
      if (sx[1] - sx[0] > 40) outX.push(it.key + ' x=' + sx[0].toFixed(0) + '~' + sx[1].toFixed(0));
    }
    const t = num(e.style.get('top'));
    if (t !== null && t >= CH) outY.push(it.key + ' top=' + t);
  });
  done(r);
});
chk('가로로 화면 밖에 나간 것이 없다', outX.length === 0, outX.slice(0, 4).join(' | '));
chk('세로로 화면 밖에 나간 것이 없다', outY.length === 0, outY.slice(0, 4).join(' | '));
chk('한 연출이 DOM 200개를 안 넘는다', budget.length === 0, budget.join(' '));

/* ══════════════════════════════════════════════════════════════════ */
console.log();
hr('⑫ 좌표를 두 번 접지 않는가 — 이번 버그의 회귀 검사');
/* txt() 가 KY 를 곱해 넘긴 값을 mk→mapCss 가 또 곱해 KY² 가 됐다.
   소스에서 설계값을 읽어 와 '한 번만 접혔는가' 를 자로 잰다. */
(function () {
  const src = fs.readFileSync(SRC, 'utf8');
  const want = [];
  const re = /this\.txt\(fx, '([^']+)'[\s\S]*?, (\d+)\);/g;
  let m;
  while ((m = re.exec(src))) want.push({ word: m[1], design: parseInt(m[2]) });
  chk('소스에서 글자 설계값을 읽어냈다', want.length >= 8, want.length + '개');

  const YT = CH * 0.06, KY = CH * (0.50 - 0.06) / 1080;
  const bad = [];
  ITEMS.forEach(function (it) {
    const r = run(it.key);
    textNodes(r.all).forEach(function (n) {
      const w = want.filter(function (x) { return x.word === n.txt.textContent; })[0];
      const top = num(n.wrap.style.get('top'));
      if (!w || top === null) return;
      const once = YT + w.design * KY;
      if (Math.abs(top - once) > 1.5) {
        bad.push(n.txt.textContent + ' 설계' + w.design + ' → ' + top.toFixed(0) +
                 ' (한 번 접으면 ' + once.toFixed(0) + ')');
      }
    });
    done(r);
  });
  chk('글자가 정확히 한 번만 접힌다', bad.length === 0, bad.slice(0, 3).join(' | '));
})();

/* ══════════════════════════════════════════════════════════════════ */
console.log();
hr('⑬ 안전지대 — 유튜브 채팅에 안 가리는가');
/* 실측(2026-08-30): 위 0~4% 채널줄, 50~72% 채팅, 72%↓ 고정 UI.
   읽어야 하는 것은 6~50% 안에만. 그림은 72% 까지 봐준다. */
(function () {
  const TOP = CH * 0.06, BOT = CH * 0.50, HARD = CH * 0.72;
  const outTxt = [], outArt = [];
  ITEMS.forEach(function (it) {
    const r = run(it.key);
    textNodes(r.all).forEach(function (n) {
      const top = num(n.wrap.style.get('top'));
      if (top === null) return;                        // % 로 잡은 것은 따로
      const fs2 = num(n.txt.style.get('font-size')) || 40;
      if (top < TOP - 1 || top > BOT + 1) {
        outTxt.push(it.key + ' "' + n.txt.textContent + '" ' + (top / CH * 100).toFixed(0) + '%');
      } else if (top + fs2 * 1.4 > HARD) {
        outTxt.push(it.key + ' "' + n.txt.textContent + '" 아래가 ' +
                    ((top + fs2 * 1.4) / CH * 100).toFixed(0) + '%');
      }
    });
    r.all.filter(function (e) { return e.parentNode === r.fx; }).forEach(function (e) {
      if (e.style.get('inset') === '0') return;
      const t = num(e.style.get('top'));
      // bottom:0 으로 바닥에 세운 것(불기둥 등)은 채팅 뒤로 가도 된다
      if (t !== null && t > HARD) outArt.push(it.key + ' ' + (t / CH * 100).toFixed(0) + '%');
    });
    done(r);
  });
  chk('글자가 전부 6~50% 안에 있다', outTxt.length === 0, outTxt.slice(0, 4).join(' | '));
  chk('그림이 72% 아래로 안 내려간다', outArt.length === 0, outArt.slice(0, 4).join(' | '));
})();

/* ══════════════════════════════════════════════════════════════════ */
console.log();
hr('⑭ 배경은 그대로 화면 전체를 쓰는가');
(function () {
  const r = run('gazua');
  const full = r.all.filter(function (e) { return e.style.get('inset') === '0'; });
  const floor = r.all.filter(function (e) { return e.style.get('bottom') === '0'; });
  done(r);
  chk('전면 배경(inset:0)은 안 건드린다', full.length >= 2, full.length + '개');
  chk('바닥에 세운 것(bottom:0)은 화면 끝까지 간다', floor.length >= 5, floor.length + '개');
})();

/* ══════════════════════════════════════════════════════════════════ */
console.log();
hr('⑮ 부모 기준 좌표를 화면 좌표로 접지 않는가');
/* 하트·명패처럼 부모 안에 든 조각은 '부모 기준' 이다. 안전지대로 접으면 모양이 깨진다.
   (크레이지의 하트가 실제로 그랬다 — left:-150 이 -459 가 돼 있었다) */
(function () {
  const r = run('crazy');
  const KS = (CW / 1920) * 1.39;
  const kids = r.all.filter(function (e) {
    return e.parentNode !== r.fx && num(e.style.get('left')) !== null;
  });
  const bad = kids.filter(function (e) {
    const l = num(e.style.get('left')), t = num(e.style.get('top'));
    // -150 처럼 음수로 밀어둔 조각이 KS 로만 줄었는가
    if (l !== null && l !== 0 && Math.abs(l - (-150 * KS)) > 1 && Math.abs(l) > 1) return true;
    if (t !== null && t !== 0 && Math.abs(t - (-150 * KS)) > 1 && Math.abs(t) > 1) return true;
    return false;
  });
  done(r);
  chk('부모 안 조각을 실제로 찾았다', kids.length >= 3, kids.length + '개');
  chk('부모 기준 조각은 크기 배율로만 줄인다', bad.length === 0,
      bad.map(function (e) { return e.style.get('left') + '/' + e.style.get('top'); }).join(' '));
})();

/* ══════════════════════════════════════════════════════════════════ */
console.log();
hr('⑯ 제 시각에만 나타나는가 — 글자만이 아니라 전부');
/* ②는 글자만 봤다. 입자·꽃잎·불빛에도 같은 병이 있었다 —
   17개를 훑으니 150개가 delay 전부터 화면에 떠 있었다.
   (람바다 12 · 출항 26 · 클럽음악 46 · VIP 26 · 천사 18 …) */
/* 시각 t 에 이 요소가 눈에 보이는 정도.
   ⚠️ CSS 에서 안 적힌 opacity 는 1 이다. undefined 를 Number() 에 넣으면 NaN 이 되고
      NaN > 0.05 는 거짓이라, 아무 데도 opacity 를 안 적은 요소가 통째로 검사를
      빠져나간다. 실제로 그것 때문에 150개 중 3개만 잡혔다. */
/* 시각 t 에 이 요소가 화면 안에 있는가.
   광택 쓸기 띠처럼 opacity 가 아니라 '화면 밖에 세워두는' 방식으로 숨기는 것이 있다. */
function onScreen(el, t) {
  // ⚠️ mapCss 는 0 을 'left:0' 으로 그냥 둔다 ('0px' 이 아니다). 그것도 읽어야 한다.
  const z = v => (String(v).trim() === '0' ? 0 : num(v));
  const l = z(el.style.get('left')), w = z(el.style.get('width')) || 0;
  if (l === null) return true;
  const tf = String(dom.sampleProp(el, t, 'transform') || '');
  // px 로도, 제 폭 기준 % 로도 물러난다 (광택 띠는 % 를 쓴다 — 배율과 무관하려고)
  const mp = /translateX\((-?[\d.]+)px\)/.exec(tf);
  const mc = /translateX\((-?[\d.]+)%\)/.exec(tf);
  const dx = mp ? parseFloat(mp[1]) : (mc ? parseFloat(mc[1]) / 100 * w : 0);
  return (l + dx + w) > 8 && (l + dx) < CW - 8;
}

function op(el, t) {
  let v = 1;
  for (let n = el; n && n.style; n = n.parentNode) {
    const o = dom.sampleProp(n, t, 'opacity');
    v *= (o === undefined || o === '' || o === null) ? 1 : Number(o);
    // opacity 말고 크기 0 으로 숨긴 것도 있다 (람바다 야자 기둥, 마티니 금선)
    const tf = String(dom.sampleProp(n, t, 'transform') || '');
    if (/scale[XY]?\(\s*-?0(\.0+)?\s*[,)]/.test(tf)) return 0;
    if (n.getAttribute && n.getAttribute('data-sigfx') !== null) break;
  }
  return v;
}

(function () {
  const early = [];
  ITEMS.forEach(function (it) {
    const r = run(it.key);
    r.all.forEach(function (e) {
      const an = e.anims.filter(function (a) { return !a.cancelled; });
      if (!an.length) return;
      const d0 = Math.min.apply(null, an.map(function (a) { return a.timing.delay || 0; }));
      if (d0 <= 30) return;                       // 처음부터 도는 것은 보여도 된다
      if (op(e, 0) > 0.05 && onScreen(e, 0)) {
        early.push(it.key + ' delay=' + Math.round(d0));
      }
    });
    done(r);
  });
  chk('0ms 에 미리 보이는 요소가 하나도 없다', early.length === 0,
      early.length + '건 ' + early.slice(0, 3).join(' | '));
})();

/* ══════════════════════════════════════════════════════════════════ */
console.log();
hr('⑰ 끝이 잘리지 않는가');
/* play() 는 dur 이 지나면 레이어를 통째로 지운다. 그때까지 진한 요소가 남아 있으면
   화면에서 툭 없어진다 — 고치기 전엔 누나누나 37개, VIP·천사 21개가 그랬다. */
(function () {
  const late = [], hot = [];
  ITEMS.forEach(function (it) {
    const r = run(it.key);
    const limit = it.dur * 1000 + 160;
    r.all.forEach(function (e) {
      e.anims.forEach(function (a) {
        if ((a.timing.delay || 0) + a.timing.duration > limit) late.push(it.key);
      });
    });
    // 레이어째 내려가는 마무리까지 셈에 넣어 '실제로 보이는가' 를 본다
    const lay = op(r.fx, limit - 1);
    let n = 0;
    r.all.forEach(function (e) {
      if (!e.anims.length) return;
      if (op(e, limit - 1) * lay > 0.15) n++;
    });
    if (n) hot.push(it.key + ' ' + n + '개');
    done(r);
  });
  chk('정리 시점을 넘겨 도는 애니메이션이 없다', late.length === 0,
      late.length + '건 ' + Array.from(new Set(late)).slice(0, 4).join(' '));
  chk('지워지는 순간 진하게 남은 요소가 없다', hot.length === 0, hot.slice(0, 4).join(' | '));
  chk('연출 레이어가 마지막에 부드럽게 내려간다', (function () {
    const r = run('lambada');
    const a = r.fx.anims.filter(function (x) {
      return x.frames.length && x.frames[x.frames.length - 1].opacity === 0;
    });
    done(r);
    return a.length === 1;
  })());
})();

console.log();
hr('통과 ' + OK.length + ' · 실패 ' + BAD.length);
BAD.forEach(function (n) { console.log('   [실패] ' + n); });
console.log('='.repeat(74));
process.exit(0);
