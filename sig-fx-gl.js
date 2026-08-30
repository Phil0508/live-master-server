/*
 * 🎆 시그니처 연출 — 빛·입자 레이어 (WebGL2)
 *
 * 왜 만들었나
 *   지금 연출은 DOM 조각 + CSS 로 되어 있다. 조각 하나가 곧 DOM 요소 하나라
 *   1,400개쯤에서 9fps 로 무너진다. 그래서 "몇 개까지 쓸까" 를 늘 아껴야 했다.
 *   같은 것을 WebGL 로 그리면 20만 개를 한 프레임 0.8ms 에 그린다 —
 *   60fps 예산 16.7ms 의 5% 다. (2026-08-31 RTX 3070 Ti 실측)
 *
 * 쓰는 법
 *   SigGL.attach(레이어, 폭, 높이)          // 연출 시작할 때
 *   SigGL.burst(x, y, { ... })              // 아무 때나, 몇 번이든
 *   SigGL.detach()                          // 연출 끝날 때 (반드시)
 *
 *   좌표는 화면 픽셀이다(0~폭, 0~높이). 설계 좌표(1920×1080)를 쓰려면
 *   부르는 쪽에서 SigFX._x() / _y() 로 옮겨서 넘긴다.
 *
 * 없으면 어떻게 되나
 *   WebGL2 를 못 쓰는 자리(하드웨어 가속 꺼진 OBS 등)에서는 attach() 가 false 를
 *   돌려준다. 부르는 쪽은 예전 방식으로 넘어가면 된다. 방송이 멈추면 안 된다.
 *
 * ⚠️ 스스로 멈춘다
 *   살아 있는 입자가 없으면 rAF 루프를 끊는다. 예전에 룰렛이 방송 내내 60fps 로
 *   돌던 사고가 있었다. 그리고 캔버스가 화면에서 떨어지면(연출 레이어가 통째로
 *   지워지면) 그것도 알아채고 멈춘다 — parentNode 로 보면 안 되고
 *   document.contains 로 봐야 한다.
 */
(function (global) {
'use strict';

/* ── 입자 하나가 GPU 로 가는 것 (vec4 넷 = 64바이트) ──
   위치를 자바스크립트가 매 프레임 고쳐 쓰면 20만 개는 어림도 없다.
   '태어난 시각 + 처음 속도 + 받는 힘' 만 한 번 올리고, 매 프레임 시각만
   바꿔 넣는다. 나머지는 정점 셰이더가 푼다.
     p = p0 + v·t·저항 + ½·g·t²                                            */
const VS = `#version 300 es
layout(location=0) in vec4 a_p0v;    // xy: 태어난 자리, zw: 처음 속도
layout(location=1) in vec4 a_meta;   // x: 태어난 시각, y: 수명, z: 크기, w: 씨앗
layout(location=2) in vec4 a_col;    // rgb: 색, w: 종류(0 불티 1 반짝임 2 연기)
layout(location=3) in vec4 a_dyn;    // x: 중력, y: 저항, z: 커지는 정도, w: 여분
uniform float u_t;
uniform vec2  u_res;
uniform float u_dpr;
uniform float u_gen;   // 이 시각 이전에 태어난 것은 없는 셈 친다 (지우기를 공짜로)
out vec3  v_col;
out float v_life;
out float v_kind;
out float v_seed;
void main(){
  float age  = u_t - a_meta.x;
  float life = 1.0 - age / max(a_meta.y, 0.001);
  if (life <= 0.0 || age < 0.0 || a_meta.x < u_gen) {   // 죽었거나 지난 세대
    gl_Position = vec4(2.0, 2.0, 0.0, 1.0);   // 화면 밖으로 던진다
    gl_PointSize = 0.0;
    return;
  }
  v_col = a_col.rgb; v_life = life; v_kind = a_col.w; v_seed = a_meta.w;

  float drag = max(1.0 - a_dyn.y * age, 0.30);
  vec2  p = a_p0v.xy + a_p0v.zw * age * drag + vec2(0.0, a_dyn.x) * age * age * 0.5;
  vec2  ndc = (p / u_res) * 2.0 - 1.0;
  gl_Position = vec4(ndc.x, -ndc.y, 0.0, 1.0);

  // 연기는 커지면서 옅어지고, 불티·반짝임은 식으면서 작아진다
  float grow = 1.0 + a_dyn.z * (1.0 - life);
  gl_PointSize = a_meta.z * u_dpr * grow * (a_dyn.z > 0.0 ? 1.0 : (0.35 + 0.65 * life));
}`;

const FS = `#version 300 es
precision highp float;
in vec3  v_col;
in float v_life;
in float v_kind;
in float v_seed;
uniform float u_t;
out vec4 o;
void main(){
  vec2  d = gl_PointCoord - 0.5;
  float r = dot(d, d) * 4.0;
  if (r > 1.0) discard;
  float soft = pow(1.0 - r, 1.6);          // 가장자리가 부드러운 점
  float k = clamp(v_life, 0.0, 1.0);
  vec3  c = v_col;
  float a;

  if (v_kind < 0.5) {
    // 불티 — 갓 터진 것은 흰빛, 식으면서 제 색, 끝에는 어둡게
    vec3 hot  = vec3(1.0, 0.97, 0.90);
    vec3 cool = v_col * 0.34;
    c = mix(cool, v_col, smoothstep(0.0, 0.55, k));
    c = mix(c, hot, smoothstep(0.72, 1.0, k));
    a = soft * pow(k, 0.55);
  } else if (v_kind < 1.5) {
    // 반짝임 — 색은 그대로, 깜빡인다 (금가루가 빛을 되쏘는 느낌)
    float tw = 0.45 + 0.55 * abs(sin(v_seed * 43.0 + u_t * (5.0 + v_seed * 9.0)));
    a = soft * pow(k, 0.4) * tw;
    c = v_col * (0.8 + 0.5 * tw);
  } else {
    // 연기 — 옅고 넓게, 빨리 사라진다
    a = soft * 0.22 * pow(k, 1.4);
  }
  // ⚠️ 미리 곱해진 알파(premultiplied)로 낸다. 방송 화면 위에 얹히는 레이어라
  //    이래야 '가리지 않고 빛만 더해지는' 그림이 된다.
  o = vec4(c * a, a);
}`;

const QUAD_VS = `#version 300 es
layout(location=0) in vec2 a; out vec2 uv;
void main(){ uv = a * 0.5 + 0.5; gl_Position = vec4(a, 0.0, 1.0); }`;

/* 밝은 데만 뽑는다 — 이게 있어야 빛이 '넘치는' 느낌이 난다 */
const BRIGHT_FS = `#version 300 es
precision highp float; in vec2 uv; out vec4 o; uniform sampler2D u_src;
void main(){
  vec3 c = texture(u_src, uv).rgb;
  float b = max(c.r, max(c.g, c.b));
  o = vec4(c * smoothstep(0.40, 0.95, b), 1.0);
}`;

/* 가로·세로를 따로 흐린다(분리 가능 가우시안) — 한 번에 하면 비용이 제곱으로 뛴다 */
const BLUR_FS = `#version 300 es
precision highp float; in vec2 uv; out vec4 o;
uniform sampler2D u_src; uniform vec2 u_dir;
void main(){
  vec2 t = u_dir / vec2(textureSize(u_src, 0));
  vec3 s = texture(u_src, uv).rgb * 0.227;
  s += (texture(u_src, uv + t * 1.385).rgb + texture(u_src, uv - t * 1.385).rgb) * 0.316;
  s += (texture(u_src, uv + t * 3.231).rgb + texture(u_src, uv - t * 3.231).rgb) * 0.070;
  o = vec4(s, 1.0);
}`;

const COMP_FS = `#version 300 es
precision highp float; in vec2 uv; out vec4 o;
uniform sampler2D u_scene, u_b1, u_b2, u_b3;
uniform float u_amt;
void main(){
  vec4 sc = texture(u_scene, uv);
  vec3 bl = texture(u_b1, uv).rgb * 0.50
          + texture(u_b2, uv).rgb * 0.34
          + texture(u_b3, uv).rgb * 0.26;
  vec3 add = bl * u_amt;
  // 번진 빛도 방송 화면 위로 보이게 알파를 같이 올린다 (미리 곱해진 알파)
  float a = clamp(sc.a + max(add.r, max(add.g, add.b)) * 0.85, 0.0, 1.0);
  o = vec4(sc.rgb + add, a);
}`;

/* 잔상 — 지우는 대신 곱해서 옅게 만든다. dst = dst × k */
const FADE_FS = `#version 300 es
precision highp float; out vec4 o; uniform float u_k;
void main(){ o = vec4(u_k, u_k, u_k, u_k); }`;

const CAP = 160000;          // 동시에 담아둘 수 있는 입자 수
const HEX = /^#?([0-9a-f]{6})$/i;

function toRGB(c) {
  if (Array.isArray(c)) return c;
  const m = HEX.exec(String(c || ''));
  if (!m) return [1.0, 0.78, 0.28];                  // 기본은 금색
  const n = parseInt(m[1], 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}
const KIND = { ember: 0, glint: 1, smoke: 2 };
const rnd = (a, b) => a + Math.random() * (b - a);

class SigGLEngine {
  constructor() {
    this.ok = false;        // 이 브라우저에서 쓸 수 있나
    this.on = false;        // 지금 붙어 있나
    this.why = '';
    this.bloom = 1.15;      // 빛 번짐 세기 (0 이면 끔)
    this.trail = 0;         // 잔상 (0 없음 ~ 0.9 길게)
    this._raf = null;
    this._until = -1;       // 마지막 입자가 죽는 시각(초). 그때 루프를 끊는다
  }

  /* ── 붙이기 ──
     parentEl 안에 캔버스를 만들어 넣는다. 못 쓰면 false — 부르는 쪽이 예전
     방식으로 넘어가야 한다. 방송이 멈추면 안 된다. */
  attach(parentEl, w, h, opt) {
    if (!parentEl || !w || !h) return false;
    opt = opt || {};
    this.bloom = opt.bloom != null ? opt.bloom : 1.15;
    this.trail = opt.trail != null ? opt.trail : 0;
    try {
      if (!this._init()) return false;
      this.W = Math.round(w); this.H = Math.round(h);
      this.DPR = Math.min(global.devicePixelRatio || 1, 2);
      const cw = Math.max(1, Math.round(this.W * this.DPR));
      const ch = Math.max(1, Math.round(this.H * this.DPR));
      if (this.cv.width !== cw || this.cv.height !== ch) {
        this.cv.width = cw; this.cv.height = ch;
        this._targets();
      }
      this.cv.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;' +
                              'pointer-events:none;';
      parentEl.appendChild(this.cv);
      this.on = true;
      this.clear();
      return true;
    } catch (e) {
      this.why = String((e && e.message) || e);
      this.ok = false;
      return false;
    }
  }

  /* ── 떼기 ── 연출이 끝나면 반드시 부른다. 안 부르면 루프가 남는다. */
  detach() {
    this.on = false;
    if (this._raf) { cancelAnimationFrame(this._raf); this._raf = null; }
    if (this.cv && this.cv.parentNode) this.cv.parentNode.removeChild(this.cv);
    this.clear();
  }

  /* ⚠️ 입자를 실제로 지우지 않는다. 16만 개 × 64바이트 = 10MB 를 GPU 에 다시
        올리는 일이라 연출이 시작·끝날 때마다 멈칫한다. '이 시각 이전 것은 없는
        셈' 이라고 셰이더에 알려주기만 하면 된다 — 공짜다. */
  clear() {
    if (!this.ok) return;
    this._gen = this._now();
    this.head = 0;
    this._until = -1;
    if (this.gl && this.rt) {
      const gl = this.gl;
      [this.rt.scene].concat(this.rt.b, this.rt.tmp).forEach(r => {
        gl.bindFramebuffer(gl.FRAMEBUFFER, r.f);
        gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
      });
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
    }
  }

  /* ── 쏘기 ──
     x, y : 화면 픽셀 (0~폭, 0~높이)
     opt  : n 개수 · speed [최소,최대] · life 초 [최소,최대] · size [최소,최대]
            color '#rrggbb' 또는 [r,g,b] · kind 'ember'|'glint'|'smoke'
            gravity 아래로 당기는 힘 · drag 공기 저항
            dir 중심 방향(라디안) · spread 퍼지는 각도 폭(라디안)
            grow 커지는 정도(연기용) · delay 초 뒤에 터짐
            jitter 태어나는 시각을 흩는 폭(초) · radius 태어나는 자리를 흩는 반지름
     ⚠️ jitter·radius 가 0 이면 수천 개가 한 점·한 순간에 겹쳐 딱딱한 흰 원반이
        된다. 실제 화약도 순간이 아니라 짧은 시간 동안 터진다.                */
  burst(x, y, opt) {
    if (!this.ok || !this.on) return 0;
    opt = opt || {};
    const n = Math.max(1, Math.min(opt.n || 3000, this.cap));
    const sp = opt.speed || [120, 1000];
    const lf = opt.life  || [0.9, 2.4];
    const sz = opt.size  || [1.6, 4.8];
    const col = toRGB(opt.color);
    const kind = KIND[opt.kind] != null ? KIND[opt.kind] : 0;
    const grav = opt.gravity != null ? opt.gravity : 620;
    const drag = opt.drag != null ? opt.drag : 0.22;
    const grow = opt.grow != null ? opt.grow : (kind === 2 ? 2.2 : 0);
    const dir = opt.dir != null ? opt.dir : 0;
    const spread = opt.spread != null ? opt.spread : Math.PI * 2;
    const born0 = this._now() + (opt.delay || 0);
    const jit = opt.jitter || 0;
    const rad = opt.radius || 0;

    const from = this.head;
    for (let i = 0; i < n; i++) {
      const k = (from + i) % this.cap;
      const a = dir + (Math.random() - 0.5) * spread;
      const born = born0 + Math.random() * jit;
      const ra = Math.random() * Math.PI * 2, rr = Math.random() * rad;
      // 제곱근을 쓰면 안쪽이 비어 보인다 — 0.55 승이 불꽃처럼 가운데가 찬다
      const v = sp[0] + Math.pow(Math.random(), 0.55) * (sp[1] - sp[0]);
      const life = rnd(lf[0], lf[1]);
      const k4 = k * 4;
      this.p0v[k4] = x + Math.cos(ra) * rr;
      this.p0v[k4 + 1] = y + Math.sin(ra) * rr;
      this.p0v[k4 + 2] = Math.cos(a) * v; this.p0v[k4 + 3] = Math.sin(a) * v;
      this.meta[k4] = born; this.meta[k4 + 1] = life;
      this.meta[k4 + 2] = rnd(sz[0], sz[1]); this.meta[k4 + 3] = Math.random();
      this.col[k4] = col[0]; this.col[k4 + 1] = col[1];
      this.col[k4 + 2] = col[2]; this.col[k4 + 3] = kind;
      this.dyn[k4] = grav; this.dyn[k4 + 1] = drag;
      this.dyn[k4 + 2] = grow; this.dyn[k4 + 3] = 0;
      const dies = born + life;
      if (dies > this._until) this._until = dies;
    }
    this.head = (from + n) % this.cap;
    this._upload(from, n);
    this._wake();
    return n;
  }

  /* 고리 모양으로 퍼지는 충격파 */
  ring(x, y, opt) {
    opt = opt || {};
    return this.burst(x, y, Object.assign({
      n: 2200, speed: [opt.r || 700, (opt.r || 700) * 1.12],
      life: [0.5, 0.8], size: [2.0, 4.0], gravity: 60, drag: 1.6
    }, opt, { spread: Math.PI * 2 }));
  }

  /* ══════════ 아래는 속 ══════════ */

  _now() { return ((global.performance || Date).now() - this.t0) / 1000; }

  _init() {
    if (this.ok) return true;
    if (this._tried) return false;
    this._tried = true;
    const cv = (global.document || {}).createElement
      ? global.document.createElement('canvas') : null;
    if (!cv) { this.why = 'document 없음'; return false; }
    let gl = null;
    try {
      gl = cv.getContext('webgl2', {
        alpha: true, premultipliedAlpha: true, antialias: false,
        depth: false, stencil: false, preserveDrawingBuffer: false,
        powerPreference: 'high-performance'
      });
    } catch (e) { this.why = String((e && e.message) || e); }
    if (!gl) { this.why = this.why || 'WebGL2 를 못 연다'; return false; }
    this.cv = cv; this.gl = gl;
    // ⚠️ 시계는 여기서 한 번만 잡는다. attach 마다 되감으면 이미 올라가 있는
    //    입자들의 '태어난 시각' 이 미래가 되어 영영 안 나온다.
    this.t0 = (global.performance || Date).now();
    this._gen = 0;
    this.halfFloat = !!gl.getExtension('EXT_color_buffer_float');

    try {
      this.pDraw = this._link(VS, FS);
      this.pBright = this._link(QUAD_VS, BRIGHT_FS);
      this.pBlur = this._link(QUAD_VS, BLUR_FS);
      this.pComp = this._link(QUAD_VS, COMP_FS);
      this.pFade = this._link(QUAD_VS, FADE_FS);
    } catch (e) { this.why = '셰이더 오류: ' + e.message; return false; }

    this.quadVao = gl.createVertexArray();
    gl.bindVertexArray(this.quadVao);
    const qb = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, qb);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
    gl.bindVertexArray(null);

    this._alloc(CAP);
    this.ok = true;
    return true;
  }

  _link(vs, fs) {
    const gl = this.gl;
    const c = (t, src) => {
      const s = gl.createShader(t); gl.shaderSource(s, src); gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s));
      return s;
    };
    const p = gl.createProgram();
    gl.attachShader(p, c(gl.VERTEX_SHADER, vs));
    gl.attachShader(p, c(gl.FRAGMENT_SHADER, fs));
    gl.linkProgram(p);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
    return p;
  }

  _alloc(cap) {
    const gl = this.gl;
    this.cap = cap; this.head = 0;
    this.p0v = new Float32Array(cap * 4);
    this.meta = new Float32Array(cap * 4);
    this.col = new Float32Array(cap * 4);
    this.dyn = new Float32Array(cap * 4);
    this.meta.fill(-1e9);                     // 다 죽은 상태로 시작
    this.vao = gl.createVertexArray();
    gl.bindVertexArray(this.vao);
    const mk = (loc, arr) => {
      const b = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, b);
      gl.bufferData(gl.ARRAY_BUFFER, arr, gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(loc);
      gl.vertexAttribPointer(loc, 4, gl.FLOAT, false, 0, 0);
      return b;
    };
    this.bP = mk(0, this.p0v); this.bM = mk(1, this.meta);
    this.bC = mk(2, this.col);  this.bD = mk(3, this.dyn);
    gl.bindVertexArray(null);
  }

  /* 쓴 자리만 올린다. 매번 전체(160,000 × 64바이트 = 10MB)를 올리면 그게 병목이다. */
  _upload(from, n) {
    const gl = this.gl, cap = this.cap;
    const put = (buf, arr) => {
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      if (from + n <= cap) {
        gl.bufferSubData(gl.ARRAY_BUFFER, from * 16, arr, from * 4, n * 4);
      } else {                                  // 고리 끝을 넘으면 두 번에 나눠 올린다
        const first = cap - from;
        gl.bufferSubData(gl.ARRAY_BUFFER, from * 16, arr, from * 4, first * 4);
        gl.bufferSubData(gl.ARRAY_BUFFER, 0, arr, 0, (n - first) * 4);
      }
    };
    put(this.bP, this.p0v); put(this.bM, this.meta);
    put(this.bC, this.col);  put(this.bD, this.dyn);
  }

  _tex(w, h) {
    const gl = this.gl;
    w = Math.max(1, w); h = Math.max(1, h);
    const t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    const ifmt = this.halfFloat ? gl.RGBA16F : gl.RGBA8;
    const type = this.halfFloat ? gl.HALF_FLOAT : gl.UNSIGNED_BYTE;
    gl.texImage2D(gl.TEXTURE_2D, 0, ifmt, w, h, 0, gl.RGBA, type, null);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    const f = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, f);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    return { t, f, w, h };
  }

  _targets() {
    const gl = this.gl, w = this.cv.width, h = this.cv.height;
    if (this.rt) [this.rt.scene].concat(this.rt.b, this.rt.tmp).forEach(r => {
      gl.deleteTexture(r.t); gl.deleteFramebuffer(r.f);
    });
    // 빛 번짐은 절반 크기부터 — 눈에 차이가 없고 비용은 4분의 1이다
    this.rt = {
      scene: this._tex(w, h),
      b: [this._tex(w >> 1, h >> 1), this._tex(w >> 2, h >> 2), this._tex(w >> 3, h >> 3)],
      tmp: [this._tex(w >> 1, h >> 1), this._tex(w >> 2, h >> 2), this._tex(w >> 3, h >> 3)]
    };
  }

  _blit(prog, dst, binds, setU) {
    const gl = this.gl;
    gl.bindFramebuffer(gl.FRAMEBUFFER, dst ? dst.f : null);
    gl.viewport(0, 0, dst ? dst.w : this.cv.width, dst ? dst.h : this.cv.height);
    gl.useProgram(prog);
    (binds || []).forEach((pair, i) => {
      gl.activeTexture(gl.TEXTURE0 + i);
      gl.bindTexture(gl.TEXTURE_2D, pair[1].t);
      gl.uniform1i(gl.getUniformLocation(prog, pair[0]), i);
    });
    if (setU) setU(prog);
    gl.bindVertexArray(this.quadVao);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    gl.bindVertexArray(null);
  }

  _wake() {
    if (this._raf || !this.on) return;
    this._raf = requestAnimationFrame(this._tick);
  }

  _draw(t) {
    const gl = this.gl, rt = this.rt;
    const useBloom = this.bloom > 0;
    gl.disable(gl.DEPTH_TEST);
    gl.bindFramebuffer(gl.FRAMEBUFFER, useBloom ? rt.scene.f : null);
    gl.viewport(0, 0, this.cv.width, this.cv.height);

    if (this.trail > 0) {
      // 지우는 대신 곱해서 옅게 — 빠른 것이 흐르는 자국을 남긴다
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ZERO, gl.SRC_COLOR);
      this._blit(this.pFade, useBloom ? rt.scene : null, null,
                 p => gl.uniform1f(gl.getUniformLocation(p, 'u_k'), this.trail));
      gl.bindFramebuffer(gl.FRAMEBUFFER, useBloom ? rt.scene.f : null);
      gl.viewport(0, 0, this.cv.width, this.cv.height);
    } else {
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
    }

    // 미리 곱해진 알파끼리 더한다 — 겹칠수록 밝아진다
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.useProgram(this.pDraw);
    gl.uniform1f(gl.getUniformLocation(this.pDraw, 'u_t'), t);
    gl.uniform2f(gl.getUniformLocation(this.pDraw, 'u_res'), this.W, this.H);
    gl.uniform1f(gl.getUniformLocation(this.pDraw, 'u_dpr'), this.DPR);
    gl.uniform1f(gl.getUniformLocation(this.pDraw, 'u_gen'), this._gen || 0);
    gl.bindVertexArray(this.vao);
    gl.drawArrays(gl.POINTS, 0, this.cap);
    gl.bindVertexArray(null);

    if (!useBloom) { gl.disable(gl.BLEND); return; }

    gl.disable(gl.BLEND);
    this._blit(this.pBright, rt.b[0], [['u_src', rt.scene]]);
    for (let i = 0; i < 3; i++) {
      if (i) this._blit(this.pBlur, rt.b[i], [['u_src', rt.b[i - 1]]],
                        p => gl.uniform2f(gl.getUniformLocation(p, 'u_dir'), 0, 0));
      this._blit(this.pBlur, rt.tmp[i], [['u_src', rt.b[i]]],
                 p => gl.uniform2f(gl.getUniformLocation(p, 'u_dir'), 1, 0));
      this._blit(this.pBlur, rt.b[i], [['u_src', rt.tmp[i]]],
                 p => gl.uniform2f(gl.getUniformLocation(p, 'u_dir'), 0, 1));
    }
    this._blit(this.pComp, null,
      [['u_scene', rt.scene], ['u_b1', rt.b[0]], ['u_b2', rt.b[1]], ['u_b3', rt.b[2]]],
      p => gl.uniform1f(gl.getUniformLocation(p, 'u_amt'), this.bloom));
  }
}

const SigGL = new SigGLEngine();
/* ⚠️ rAF 는 this 를 안 넘겨준다. 그래서 이 함수는 this 를 안 쓰고
      바깥의 SigGL 을 직접 본다. */
SigGL._tick = function () {
  SigGL._raf = null;
  if (!SigGL.on || !SigGL.ok) return;
  /* ⚠️ '아직 살아 있나' 를 parentNode 로 보면 안 된다. 연출 레이어를 통째로 떼도
        캔버스의 부모는 여전히 그 레이어라서 참으로 남는다. 예전에 그것 때문에
        화면에 붙어 있지도 않은 캔버스에 계속 그리는 루프가 돌았다. */
  if (!global.document || !global.document.contains(SigGL.cv)) { SigGL.on = false; return; }
  const t = SigGL._now();
  try { SigGL._draw(t); } catch (e) { SigGL.on = false; return; }
  // 남은 입자가 없으면 여기서 끊는다 — 방송 내내 도는 루프를 만들지 않는다
  if (t > SigGL._until + 0.05) return;
  SigGL._raf = requestAnimationFrame(SigGL._tick);
};

if (typeof module !== 'undefined' && module.exports) module.exports = SigGL;
global.SigGL = SigGL;
})(typeof window !== 'undefined' ? window : this);
