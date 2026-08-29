/* 가짜 DOM — sig-fx.js 를 node 에서 진짜로 돌리기 위한 최소한의 것.
 *
 * 왜 이렇게까지 하는가: 연출 검사를 '소스에 이 글자가 있나' 로 하면 값을 바꿔도
 * 검사가 통과한다. animate() 호출을 그대로 받아 적으면 "언제 무엇이 어떻게
 * 움직이는가" 를 실제 코드에서 캐낼 수 있다 — 히트스톱이 정말 정지인지,
 * speed 가 전 구간에 먹는지 같은 걸 값으로 따질 수 있다.
 *
 * animate() 는 실행하지 않고 기록만 한다. 그래서 시각 t 의 모습은
 * sampleTransform() 이 직접 계산한다(합성 순서 = 만든 순서, 뒤엣것이 이긴다).
 */
'use strict';

let SEQ = 0;

function parseCss(text) {
  const o = {};
  String(text || '').split(';').forEach(kv => {
    const i = kv.indexOf(':');
    if (i > 0) o[kv.slice(0, i).trim()] = kv.slice(i + 1).trim();
  });
  return o;
}

class Style {
  constructor() { this._m = {}; }
  get cssText() {
    return Object.keys(this._m).map(k => k + ':' + this._m[k]).join(';');
  }
  set cssText(v) { this._m = parseCss(v); }
  setProperty(k, v) { this._m[k] = v; }
  removeProperty(k) { delete this._m[k]; }
  getPropertyValue(k) { return this._m[k] || ''; }
  get(k) { return this._m[k]; }
}
/* 엔진이 el.style.opacity 로 직접 읽고 쓴다 (delay 앞 구간을 숨길 때).
   cssText 로만 다루면 그 코드가 헛돌아 검사가 거짓 통과한다. */
['opacity', 'transform'].forEach(function (p) {
  Object.defineProperty(Style.prototype, p, {
    get() { return this._m[p] || ''; },
    set(v) { this._m[p] = String(v); },
  });
});

class Anim {
  constructor(el, frames, timing) {
    this.el = el; this.frames = frames; this.timing = timing;
    this.seq = SEQ++; this.cancelled = false;
  }
  cancel() { this.cancelled = true; }
  commitStyles() {}
}

class El {
  constructor(tag) {
    this.tagName = (tag || 'div').toUpperCase();
    this.style = new Style();
    this.children = []; this.parentNode = null;
    this.attrs = {}; this.anims = [];
    this.clientWidth = 0; this.clientHeight = 0;
  }
  appendChild(c) { c.parentNode = this; this.children.push(c); return c; }
  remove() {
    if (this.parentNode) {
      const i = this.parentNode.children.indexOf(this);
      if (i >= 0) this.parentNode.children.splice(i, 1);
      this.parentNode = null;
    }
  }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return this.attrs[k] != null ? this.attrs[k] : null; }
  animate(frames, timing) { const a = new Anim(this, frames, timing); this.anims.push(a); return a; }
  getAnimations() { return this.anims.filter(a => !a.cancelled); }
  getContext() {
    return new Proxy({}, { get: (t, p) => (p === 'canvas' ? this : () => {}) });
  }
  get firstElementChild() { return this.children[0] || null; }
  contains(el) {
    if (el === this) return true;
    return this.children.some(c => c.contains(el));
  }
  _walk(out) { this.children.forEach(c => { out.push(c); c._walk(out); }); return out; }
  _match(sel, direct) {
    // ':scope > [data-x]' / '[data-x]' 만 쓴다
    const scoped = sel.indexOf(':scope >') === 0;
    const attr = (sel.match(/\[([\w-]+)\]/) || [])[1];
    const pool = (scoped || direct) ? this.children : this._walk([]);
    return pool.filter(e => attr ? e.attrs[attr] != null : false);
  }
  querySelector(sel) { return this._match(sel)[0] || null; }
  querySelectorAll(sel) { return this._match(sel); }
}

/* setTimeout 도 받아 적는다 — 터뜨리지는 않는다.
   ⚠️ 진짜로 돌게 두면 fireworks 의 연쇄가 무한히 스스로를 예약한다. */
const timers = [];
function install() {
  const doc = new El('body');
  doc.createElement = t => new El(t);
  doc.getElementById = () => null;
  doc.contains = el => doc.contains_(el);
  doc.contains_ = el => El.prototype.contains.call(doc, el);
  global.document = doc;
  global.requestAnimationFrame = () => 0;
  timers.length = 0;
  global.setTimeout = (fn, ms) => { timers.push(ms); return timers.length; };
  global.clearTimeout = () => {};
  return doc;
}

/* ── 시각 t(ms) 에 el 의 transform / opacity 가 무엇인가 ──
   WAAPI 의 합성 순서를 그대로 흉내낸다:
     · delay 전(before)에는 fill:'forwards' 가 안 걸린다 → 그 애니메이션은 없는 셈
     · active 중이면 프레임 사이를 선형 보간… 은 하지 않는다. 우리가 알고 싶은 건
       '두 시점의 값이 같은가' 라서, 이징 곡선까지 흉내 낼 필요가 없다.
       대신 offset 구간을 찾아 '그 구간의 시작 프레임 → 끝 프레임' 을 돌려준다.
     · 끝난 뒤에는 마지막 프레임이 남는다(forwards)
     · 나중에 만든 것이 이긴다 */
function sampleProp(el, t, prop, speed) {
  speed = speed || 1;
  let best = null;
  el.anims.filter(a => !a.cancelled).forEach(a => {
    const d = (a.timing.delay || 0), dur = a.timing.duration;
    if (t < d) return;                       // before — fill 안 걸림
    const frames = a.frames.filter(f => f[prop] !== undefined);
    if (!frames.length) return;
    let v;
    if (t >= d + dur) v = frames[frames.length - 1][prop];
    else {
      const p = dur > 0 ? (t - d) / dur : 1;
      // offset 이 없는 프레임은 균등 분배된 것으로 본다
      const n = a.frames.length - 1;
      const off = a.frames.map((f, i) => f.offset != null ? f.offset : i / n);
      let k = 0;
      for (let i = 0; i < a.frames.length; i++) if (off[i] <= p) k = i;
      // prop 을 가진 가장 가까운 앞 프레임
      let j = k;
      while (j >= 0 && a.frames[j][prop] === undefined) j--;
      v = j >= 0 ? a.frames[j][prop] : frames[0][prop];
      // 구간 끝에 정확히 닿았으면 그 프레임 값
      if (a.frames[k][prop] !== undefined && Math.abs(off[k] - p) < 1e-9) v = a.frames[k][prop];
      // 숫자면 다음 프레임까지 선형으로 이어 읽는다 (이징 곡선은 흉내 안 낸다)
      let n2 = j + 1;
      while (n2 < a.frames.length && a.frames[n2][prop] === undefined) n2++;
      if (j >= 0 && n2 < a.frames.length && typeof v === 'number' &&
          typeof a.frames[n2][prop] === 'number' && off[n2] > off[j]) {
        const r = Math.min(1, Math.max(0, (p - off[j]) / (off[n2] - off[j])));
        v = v + (a.frames[n2][prop] - v) * r;
      }
    }
    if (!best || a.seq > best.seq) best = { seq: a.seq, v: v };
  });
  return best ? best.v : el.style.get(prop);
}

/* 두 번 돌려 견줄 때만 쓴다 — 무작위가 섞이면 속도 문제인지 주사위 문제인지 못 가린다 */
function freezeRandom(v) {
  const orig = Math.random;
  Math.random = () => (v === undefined ? 0.5 : v);
  return () => { Math.random = orig; };
}

module.exports = { install, El, sampleProp, timers, freezeRandom };
