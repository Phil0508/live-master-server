/*
 * 🎆 시그니처 연출 — 빛·입자·연기 레이어 (WebGL2)
 *
 * ══ 왜 이게 필요했나 ══
 *   연출이 "PPT 같다" 는 말을 들었다. 맞는 말이었다. 이유는 다섯이다.
 *     ① 전부 div 다 — 네모·원이 A 에서 B 로 미끄러진다
 *     ② 곧게 간다 — CSS 이징은 매끄럽지만 규칙적이라 자연에 없는 움직임이다
 *     ③ 끝이 보인다 — 조각마다 경계가 딱 있다
 *     ④ 조각들이 따로 논다 — 한 카메라로 찍힌 느낌이 없다
 *     ⑤ 화면이 비어 있다 — 대부분의 시간에 아무것도 안 흐른다
 *
 *   게임 연출(오버워치·롤)이 예뻐 보이는 건 화면에 **늘 연속된 매질**이 흐르고,
 *   빛이 진짜 빛처럼 번지고, 모든 게 한 렌즈를 통과하기 때문이다.
 *   그래서 이 레이어는 조각을 그리는 도구가 아니라 **매질을 만드는 도구**다.
 *
 * ══ 그리는 순서 (뒤에서 앞으로) ══
 *   1. 매질   연기·에너지 구름 + 빛 덩어리   ← 화면을 채운다 (③⑤ 를 없앤다)
 *   2. 입자   불티·반짝임·먼지              ← 소용돌이로 휘감긴다 (② 를 없앤다)
 *   3. 빛     밝은 데를 뽑아 3단계로 번짐
 *   4. 렌즈   충격파 왜곡 · 색수차 · 그레인   ← 전부를 한 장으로 묶는다 (④)
 *
 * ══ 쓰는 법 ══
 *   SigGL.attach(레이어, 폭, 높이)
 *   SigGL.smoke(x, y, {...})   연기·에너지 구름
 *   SigGL.glow (x, y, {...})   부드러운 빛 덩어리
 *   SigGL.shock(x, y, {...})   충격파 — 화면이 일그러진다
 *   SigGL.burst(x, y, {...})   입자
 *   SigGL.detach()             ← 반드시
 *
 *   좌표는 화면 픽셀(0~폭, 0~높이). 설계 좌표(1920×1080)는 부르는 쪽에서
 *   SigFX._x() / _y() 로 옮겨 넘긴다.
 *
 * ══ 못 쓰는 자리에서 ══
 *   attach() 가 false 를 준다. 부르는 쪽은 예전 방식으로 넘어가면 된다.
 *   방송이 멈추면 안 된다.
 *
 * ⚠️ 스스로 멈춘다. 살아 있는 것이 없으면 rAF 루프를 끊는다. 캔버스가 화면에서
 *    떨어져도 멈춘다 — parentNode 가 아니라 document.contains 로 본다.
 */
(function (global) {
'use strict';

const MAX_SMOKE = 6, MAX_GLOW = 8, MAX_SHOCK = 4;
const CAP = 160000;                 // 동시에 담아둘 수 있는 입자 수
const FIELD_DIV = 4;                // 매질은 1/4 크기로 그린다 (아래 설명)

/* ══════════════════════════════════════════════════════════════════
   입자 — 위치를 셰이더가 푼다
   자바스크립트가 입자마다 좌표를 고쳐 쓰면 20만 개는 어림도 없다.
   '태어난 시각 + 처음 속도 + 받는 힘' 만 한 번 올리고 매 프레임 시각만 바꾼다.
     p = p0 + v·t·저항 + ½·g·t² + 소용돌이(t)
   ══════════════════════════════════════════════════════════════════ */
const VS = `#version 300 es
layout(location=0) in vec4 a_p0v;    // xy: 태어난 자리, zw: 처음 속도
layout(location=1) in vec4 a_meta;   // x: 태어난 시각, y: 수명, z: 크기, w: 씨앗
layout(location=2) in vec4 a_col;    // rgb: 색, w: 종류(0 불티 1 반짝임 2 먼지)
layout(location=3) in vec4 a_dyn;    // x: 중력, y: 저항, z: 커짐, w: 소용돌이
uniform float u_t, u_dpr, u_gen;
uniform vec2  u_res;
out vec3  v_col;
out float v_life, v_kind, v_seed;

/* 회전장 — 입자가 곧게 안 가고 공기에 휘감기게 한다.
   진짜 난류를 풀 필요는 없다. 사인 두 개를 어긋나게 겹치면 눈에는 충분하다.
   ⚠️ 이게 'PPT 같다' 를 푸는 가장 싼 한 수다. 포물선으로 곧게 가는 것이
      물리적으로는 맞아도, 보는 사람에게는 '계산된 것' 으로 읽힌다. */
vec2 curl(vec2 p, float t){
  float a = sin(p.x * 0.0105 + t * 0.70) + sin(p.y * 0.0132 - t * 0.53);
  float b = cos(p.y * 0.0098 - t * 0.61) + cos(p.x * 0.0121 + t * 0.44);
  return vec2(b, -a);
}

void main(){
  float age  = u_t - a_meta.x;
  float life = 1.0 - age / max(a_meta.y, 0.001);
  if (life <= 0.0 || age < 0.0 || a_meta.x < u_gen) {   // 죽었거나 지난 세대
    gl_Position = vec4(2.0, 2.0, 0.0, 1.0);
    gl_PointSize = 0.0;
    return;
  }
  v_col = a_col.rgb; v_life = life; v_kind = a_col.w; v_seed = a_meta.w;

  float drag = max(1.0 - a_dyn.y * age, 0.30);
  vec2  p = a_p0v.xy + a_p0v.zw * age * drag + vec2(0.0, a_dyn.x) * age * age * 0.5;
  // 나이를 먹을수록 더 휘감긴다. 씨앗을 섞어 입자마다 다른 흐름을 탄다.
  if (a_dyn.w > 0.0) p += curl(p + a_meta.w * 620.0, u_t * 0.6) * a_dyn.w * age;

  vec2 ndc = (p / u_res) * 2.0 - 1.0;
  gl_Position = vec4(ndc.x, -ndc.y, 0.0, 1.0);
  float grow = 1.0 + a_dyn.z * (1.0 - life);
  gl_PointSize = a_meta.z * u_dpr * grow * (a_dyn.z > 0.0 ? 1.0 : (0.35 + 0.65 * life));
}`;

const FS = `#version 300 es
precision highp float;
in vec3  v_col;
in float v_life, v_kind, v_seed;
uniform float u_t;
out vec4 o;
void main(){
  vec2  d = gl_PointCoord - 0.5;
  float r = dot(d, d) * 4.0;
  if (r > 1.0) discard;
  float soft = pow(1.0 - r, 1.6);
  float k = clamp(v_life, 0.0, 1.0);
  vec3  c = v_col;
  float a;
  if (v_kind < 0.5) {
    // 불티 — 갓 터진 것은 흰빛, 식으면서 제 색, 끝에는 어둡게
    c = mix(v_col * 0.34, v_col, smoothstep(0.0, 0.55, k));
    c = mix(c, vec3(1.0, 0.97, 0.90), smoothstep(0.72, 1.0, k));
    a = soft * pow(k, 0.55);
  } else if (v_kind < 1.5) {
    // 반짝임 — 금가루가 빛을 되쏘듯 깜빡인다
    float tw = 0.45 + 0.55 * abs(sin(v_seed * 43.0 + u_t * (5.0 + v_seed * 9.0)));
    a = soft * pow(k, 0.4) * tw;
    c = v_col * (0.8 + 0.5 * tw);
  } else {
    // 먼지 — 옅고 넓게
    a = soft * 0.22 * pow(k, 1.4);
  }
  // ⚠️ 미리 곱해진 알파로 낸다. 방송 화면 위에 얹히는 레이어라
  //    이래야 '가리지 않고 빛만 더해지는' 그림이 된다.
  o = vec4(c * a, a);
}`;

const QUAD_VS = `#version 300 es
layout(location=0) in vec2 a; out vec2 uv;
void main(){ uv = a * 0.5 + 0.5; gl_Position = vec4(a, 0.0, 1.0); }`;

/* ══════════════════════════════════════════════════════════════════
   매질 — 연기·에너지 구름 + 빛 덩어리
   이게 'PPT 같다' 를 푸는 가장 큰 한 수다. 경계가 없는 것이 화면에 흐르면
   조각들이 그 안에 잠겨 더는 조각으로 안 보인다.

   ⚠️ 1/4 크기로 그린다. 연기는 원래 흐릿한 것이라 눈에 차이가 없는데
      비용은 16분의 1 이다. 픽셀마다 노이즈를 수십 번 뽑는 셰이더라
      전체 크기로 하면 이것만으로 예산을 다 쓴다.
   ══════════════════════════════════════════════════════════════════ */
const FIELD_FS = `#version 300 es
precision highp float;
in vec2 uv; out vec4 o;
uniform float u_t;
uniform vec2  u_res;
uniform int   u_ns, u_ng;
uniform vec4  u_s0[${MAX_SMOKE}];   // x,y,반지름,태어난시각
uniform vec4  u_s1[${MAX_SMOKE}];   // 수명,짙기,떠오름,휘감김
uniform vec4  u_s2[${MAX_SMOKE}];   // rgb,씨앗
uniform vec4  u_g0[${MAX_GLOW}];    // x,y,반지름,태어난시각
uniform vec4  u_g1[${MAX_GLOW}];    // 수명,세기,가장자리,0
uniform vec4  u_g2[${MAX_GLOW}];    // rgb,0

float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float vnoise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);                 // 부드럽게 잇는다
  return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x),
             mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
}
/* 옥타브를 겹쳐 큰 덩어리 + 중간 결 + 잔 알갱이를 한꺼번에 만든다.
   자연에 있는 것은 모든 크기에서 무늬가 있다 — 한 크기만 있으면 가짜로 보인다. */
float fbm(vec2 p){
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 4; i++){ v += a * vnoise(p); p *= 2.03; a *= 0.5; }
  return v;
}

void main(){
  /* ⚠️ y 를 뒤집는다. OpenGL 의 uv 는 아래가 0 인데 입자는 '화면 좌표(위가 0)'
        로 그린다. 안 뒤집으면 착탄점 위쪽에 있어야 할 빛이 아래쪽에 가 있다. */
  vec2 px = vec2(uv.x, 1.0 - uv.y) * u_res;
  vec3 acc = vec3(0.0);
  float aAcc = 0.0;

  // ── 연기·에너지 구름 ──
  for (int i = 0; i < ${MAX_SMOKE}; i++){
    if (i >= u_ns) break;
    float born = u_s0[i].w, life = u_s1[i].x;
    float age = u_t - born;
    if (age < 0.0 || age > life) continue;
    float k = age / life;
    vec2  c = u_s0[i].xy;
    float R = u_s0[i].z * (0.55 + 0.75 * k);          // 시간이 갈수록 부푼다
    float d = length(px - c) / R;
    if (d > 1.25) continue;

    float rise = u_s1[i].z, swirl = u_s1[i].w, dens = u_s1[i].y;
    vec2 q = (px - c) * 0.0042 + vec2(0.0, -rise * age * 0.0016) + u_s2[i].w * 17.0;
    // 도메인 왜곡 — 좌표 자체를 다른 노이즈로 민다. 이게 있어야 뭉게뭉게해진다.
    q += swirl * (vec2(fbm(q + 3.1), fbm(q + 7.7)) - 0.5) * 1.6;
    float n = fbm(q * 1.7);
    n = smoothstep(0.30, 0.92, n);                     // 결을 또렷하게

    float edge = smoothstep(1.25, 0.10, d);            // 가장자리는 흐리게 사라진다
    float fade = sin(clamp(k, 0.0, 1.0) * 3.14159);    // 피었다 진다
    float m = n * edge * fade * dens;
    acc  += u_s2[i].rgb * m;
    aAcc += m * 0.55;
  }

  // ── 빛 덩어리 ── 경계 없는 빛. 연기 속에서 빛나는 것처럼 보인다.
  for (int i = 0; i < ${MAX_GLOW}; i++){
    if (i >= u_ng) break;
    float born = u_g0[i].w, life = u_g1[i].x;
    float age = u_t - born;
    if (age < 0.0 || age > life) continue;
    float k = age / life;
    float R = u_g0[i].z * (0.7 + 0.9 * k);
    float d = length(px - u_g0[i].xy) / R;
    if (d > 1.0) continue;
    float fall = pow(1.0 - d, u_g1[i].z);
    float m = fall * u_g1[i].y * sin(clamp(k, 0.0, 1.0) * 3.14159);
    acc  += u_g2[i].rgb * m;
    aAcc += m * 0.7;
  }

  o = vec4(acc, clamp(aAcc, 0.0, 1.0));
}`;

/* 밝은 데만 뽑는다 — 빛이 '넘치는' 느낌은 여기서 나온다 */
const BRIGHT_FS = `#version 300 es
precision highp float; in vec2 uv; out vec4 o; uniform sampler2D u_src;
void main(){
  vec3 c = texture(u_src, uv).rgb;
  float b = max(c.r, max(c.g, c.b));
  o = vec4(c * smoothstep(0.38, 0.95, b), 1.0);
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

/* ══ 렌즈 ══ 충격파 왜곡 · 색수차 · 그레인.
   조각들이 따로 노는 것이 'PPT 같다' 의 절반이다. 전부를 같은 렌즈에 통과시키면
   서로 다른 것들이 한 카메라로 찍힌 것처럼 묶인다. */
const COMP_FS = `#version 300 es
precision highp float; in vec2 uv; out vec4 o;
uniform sampler2D u_scene, u_b1, u_b2, u_b3;
uniform float u_amt, u_grain, u_chrom, u_t;
uniform vec2  u_res;
uniform int   u_nk;
uniform vec4  u_k0[${MAX_SHOCK}];   // x,y,태어난시각,수명
uniform vec4  u_k1[${MAX_SHOCK}];   // 시작반지름,끝반지름,세기,두께

vec3 bloomAt(vec2 c){
  return texture(u_b1, c).rgb * 0.50
       + texture(u_b2, c).rgb * 0.34
       + texture(u_b3, c).rgb * 0.26;
}

void main(){
  vec2 st = uv;

  /* 충격파 — 고리가 지나간 자리가 일그러진다.
     ⚠️ 방송 화면은 못 건드린다(투명 레이어라 뒤 영상에 접근할 수 없다).
        우리 레이어 안의 빛·연기만 휜다 — 그래도 '힘이 지나갔다' 는 읽힌다. */
  for (int i = 0; i < ${MAX_SHOCK}; i++){
    if (i >= u_nk) break;
    float age = u_t - u_k0[i].z, life = u_k0[i].w;
    if (age < 0.0 || age > life) continue;
    float k = age / life;
    // ⚠️ 매질과 같은 좌표계(위가 0)로 맞춘다
    vec2  d = vec2(uv.x, 1.0 - uv.y) * u_res - u_k0[i].xy;
    float dist = length(d);
    float R = mix(u_k1[i].x, u_k1[i].y, k);
    float band = 1.0 - smoothstep(0.0, u_k1[i].w, abs(dist - R));
    if (band <= 0.0) continue;
    // 밀어내는 방향도 y 를 되돌려 uv 공간으로 옮긴다
    vec2 dir = normalize(d + 1e-4);
    st += vec2(dir.x, -dir.y) * band * u_k1[i].z * (1.0 - k) / u_res;
  }

  vec4 sc = texture(u_scene, st);

  /* 색수차 — 렌즈가 색마다 다른 각도로 꺾는다. 가장자리로 갈수록 커진다.
     아주 조금만 준다. 많이 주면 고장난 화면처럼 보인다. */
  vec3 bl;
  if (u_chrom > 0.0) {
    vec2 d = (st - 0.5) * u_chrom;
    bl = vec3(bloomAt(st + d).r, bloomAt(st).g, bloomAt(st - d).b);
  } else {
    bl = bloomAt(st);
  }
  vec3 add = bl * u_amt;

  /* 필름 그레인 — 화면 전체에 같은 결을 덮어 조각들을 한 그림으로 묶는다.
     ⚠️ 방송 위에 얹히는 레이어라 어둡게 까는 그레인은 못 쓴다 — 밝기만 흔든다. */
  if (u_grain > 0.0) {
    float n = fract(sin(dot(uv * u_res + u_t * 91.7, vec2(12.9898, 78.233))) * 43758.5453);
    add *= 1.0 + (n - 0.5) * u_grain;
    sc.rgb *= 1.0 + (n - 0.5) * u_grain * 0.6;
  }

  float a = clamp(sc.a + max(add.r, max(add.g, add.b)) * 0.85, 0.0, 1.0);
  o = vec4(sc.rgb + add, a);
}`;

/* 매질을 무대에 올릴 때 쓰는 '그대로 그리기' */
const COPY_FS = `#version 300 es
precision highp float; in vec2 uv; out vec4 o; uniform sampler2D u_src;
void main(){ o = texture(u_src, uv); }`;

/* 잔상 — 지우는 대신 곱해서 옅게. dst = dst × k */
const FADE_FS = `#version 300 es
precision highp float; out vec4 o; uniform float u_k;
void main(){ o = vec4(u_k, u_k, u_k, u_k); }`;


/* ══════════════════════════════════════════════════════════════════
   스프라이트 — 글자·형상을 GL 안으로
   매질만 깔아서는 'PPT 같다' 가 안 없어진다. 주인공이 여전히 CSS div 로
   화면 위에 따로 떠 있기 때문이다. 같은 빛·그레인·왜곡을 먹어야 한 장이 된다.
   ══════════════════════════════════════════════════════════════════ */
const SPR_VS = `#version 300 es
layout(location=0) in vec2 a;
uniform vec4 u_rect;    // x, y, w, h  (화면 픽셀, 왼위 기준)
uniform vec2 u_res;
uniform float u_rot;
out vec2 uv;
void main(){
  uv = a * 0.5 + 0.5;
  vec2 hf = u_rect.zw * 0.5;   // ⚠️ 'half' 는 GLSL 예약어라 못 쓴다
  vec2 p = a * hf;                                     // 가운데 기준
  float c = cos(u_rot), s = sin(u_rot);
  p = vec2(p.x * c - p.y * s, p.x * s + p.y * c);
  p += u_rect.xy + hf;
  vec2 ndc = (p / u_res) * 2.0 - 1.0;
  gl_Position = vec4(ndc.x, -ndc.y, 0.0, 1.0);
}`;

const SPR_FS = `#version 300 es
precision highp float;
in vec2 uv; out vec4 o;
uniform sampler2D u_tex;
uniform float u_t, u_alpha, u_dis, u_burn, u_rim, u_warp, u_sheen;
uniform vec3  u_rimCol, u_burnCol;

float hash(vec2 p){ return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
float vnoise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  vec2 u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash(i), hash(i + vec2(1,0)), u.x),
             mix(hash(i + vec2(0,1)), hash(i + vec2(1,1)), u.x), u.y);
}
float fbm(vec2 p){
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 3; i++){ v += a * vnoise(p); p *= 2.07; a *= 0.5; }
  return v;
}

void main(){
  vec2 st = uv;
  // 열 일렁임 — 공기가 뜨거우면 그 너머가 흔들린다
  if (u_warp > 0.0) {
    st += (vec2(fbm(uv * 7.0 + u_t * 1.3), fbm(uv * 7.0 - u_t * 1.1)) - 0.5) * u_warp;
  }
  vec4 tx = texture(u_tex, st);
  if (tx.a < 0.003) discard;

  float a = tx.a * u_alpha;
  vec3  c = tx.rgb;

  /* 디졸브 — 노이즈 문턱으로 타들어간다.
     ⚠️ 이게 '켜졌다/꺼졌다' 를 '타올랐다/재가 됐다' 로 바꾼다.
        경계에 뜨거운 테를 붙이는 게 핵심이다. 없으면 그냥 지워지는 것처럼 보인다. */
  if (u_dis > 0.0) {
    float n = fbm(uv * 5.5 + 11.3);
    float edge = n - (u_dis * 1.16 - 0.08);
    if (edge < 0.0) discard;
    if (u_burn > 0.0) {
      float hot = 1.0 - smoothstep(0.0, u_burn, edge);   // 문턱 바로 위가 탄다
      c = mix(c, u_burnCol, hot);
      a = min(1.0, a + hot * 0.85);
    }
  }

  /* 림라이트 — 알파 기울기로 테두리를 뽑는다. 요소가 장면 안에서 빛을 받는다. */
  if (u_rim > 0.0) {
    vec2 e = vec2(1.6) / vec2(textureSize(u_tex, 0));
    float g = abs(texture(u_tex, st + vec2(e.x, 0.0)).a - texture(u_tex, st - vec2(e.x, 0.0)).a)
            + abs(texture(u_tex, st + vec2(0.0, e.y)).a - texture(u_tex, st - vec2(0.0, e.y)).a);
    c += u_rimCol * g * u_rim;
    a = min(1.0, a + g * u_rim * 0.5);
  }

  /* 광택 쓸기 — 금속이 금속으로 보이는 건 결이 흐르기 때문이다 */
  if (u_sheen > 0.0) {
    float band = smoothstep(0.14, 0.0, abs(fract(uv.x * 0.9 - u_t * 0.55) - 0.5) - 0.36);
    c += vec3(1.0, 0.95, 0.82) * band * u_sheen;
  }

  o = vec4(c * a, a);     // 미리 곱해진 알파
}`;

const HEX = /^#?([0-9a-f]{6})$/i;
function toRGB(c) {
  if (Array.isArray(c)) return c;
  const m = HEX.exec(String(c || ''));
  if (!m) return [1.0, 0.78, 0.28];                  // 기본은 금색
  const n = parseInt(m[1], 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
}
const KIND = { ember: 0, glint: 1, dust: 2, smoke: 2 };
const rnd = (a, b) => a + Math.random() * (b - a);

class SigGLEngine {
  constructor() {
    this.ok = false;        // 이 브라우저에서 쓸 수 있나
    this.on = false;        // 지금 붙어 있나
    this.why = '';
    this.bloom = 1.15;      // 빛 번짐 세기 (0 이면 끔)
    this.trail = 0;         // 잔상 (0 없음 ~ 0.9 길게)
    this.grain = 0.22;      // 필름 그레인 — 조각들을 한 그림으로 묶는다
    this.chrom = 0.0035;    // 색수차 — 렌즈 흉내. 많으면 고장나 보인다
    this._raf = null;
    this._until = -1;       // 마지막 것이 죽는 시각(초). 그때 루프를 끊는다
    this.smokes = []; this.glows = []; this.shocks = []; this.sprites = [];
    this._texCache = new Map();     // 같은 그림을 두 번 올리지 않는다
  }

  /* ── 붙이기 ── 못 쓰면 false. 부르는 쪽이 예전 방식으로 넘어가야 한다. */
  attach(parentEl, w, h, opt) {
    if (!parentEl || !w || !h) return false;
    opt = opt || {};
    this.bloom = opt.bloom != null ? opt.bloom : 1.15;
    this.trail = opt.trail != null ? opt.trail : 0;
    this.grain = opt.grain != null ? opt.grain : 0.22;
    this.chrom = opt.chrom != null ? opt.chrom : 0.0035;
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
      this.cv.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;pointer-events:none;';
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

  /* ⚠️ 입자를 실제로 지우지 않는다. 16만 개 × 64바이트 = 10MB 를 다시 올리는
        일이라 연출이 시작·끝날 때마다 멈칫한다. '이 시각 이전 것은 없는 셈' 이라고
        셰이더에 알려주기만 하면 된다 — 공짜다. */
  clear() {
    if (!this.ok) return;
    this._gen = this._now();
    this.head = 0;
    this._until = -1;
    this.smokes.length = 0; this.glows.length = 0; this.shocks.length = 0;
    this.sprites.length = 0;
    if (this.gl && this.rt) {
      const gl = this.gl;
      [this.rt.scene, this.rt.field].concat(this.rt.b, this.rt.tmp).forEach(r => {
        gl.bindFramebuffer(gl.FRAMEBUFFER, r.f);
        gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
      });
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
    }
  }

  /* ══ 연기·에너지 구름 ══
     경계가 없는 것이 화면에 흐르면 조각들이 그 안에 잠겨 조각으로 안 보인다.
       r 반지름 · life 초 · color · density 짙기 · rise 떠오르는 속도
       swirl 휘감기는 정도 · delay 초 뒤에 피어남                          */
  smoke(x, y, opt) {
    if (!this.ok || !this.on) return;
    opt = opt || {};
    const born = this._now() + (opt.delay || 0);
    const life = opt.life != null ? opt.life : 2.2;
    // ⚠️ 자리가 꽉 차면 제일 먼저 태어난 것을 밀어낸다. 안 그러면 새 연기가 안 보인다.
    if (this.smokes.length >= MAX_SMOKE) this.smokes.shift();
    this.smokes.push({
      x, y, r: opt.r != null ? opt.r : 420, born, life,
      density: opt.density != null ? opt.density : 0.55,
      rise: opt.rise != null ? opt.rise : 160,
      swirl: opt.swirl != null ? opt.swirl : 1.0,
      col: toRGB(opt.color), seed: Math.random()
    });
    this._mark(born + life); this._wake();
  }

  /* ══ 빛 덩어리 ══ 경계 없는 빛. 연기 속에서 빛나는 것처럼 보인다. */
  glow(x, y, opt) {
    if (!this.ok || !this.on) return;
    opt = opt || {};
    const born = this._now() + (opt.delay || 0);
    const life = opt.life != null ? opt.life : 0.9;
    if (this.glows.length >= MAX_GLOW) this.glows.shift();
    this.glows.push({
      x, y, r: opt.r != null ? opt.r : 300, born, life,
      power: opt.power != null ? opt.power : 1.0,
      falloff: opt.falloff != null ? opt.falloff : 2.4,
      col: toRGB(opt.color)
    });
    this._mark(born + life); this._wake();
  }

  /* ══ 충격파 ══ 고리가 지나간 자리가 일그러진다.
     ⚠️ 방송 화면은 못 건드린다(투명 레이어라 뒤 영상에 접근할 수 없다).
        우리 레이어 안의 빛·연기만 휜다 — 그래도 '힘이 지나갔다' 는 읽힌다. */
  shock(x, y, opt) {
    if (!this.ok || !this.on) return;
    opt = opt || {};
    const born = this._now() + (opt.delay || 0);
    const life = opt.life != null ? opt.life : 0.55;
    if (this.shocks.length >= MAX_SHOCK) this.shocks.shift();
    this.shocks.push({
      x, y, born, life,
      r0: opt.r0 != null ? opt.r0 : 20,
      r1: opt.r1 != null ? opt.r1 : 900,
      power: opt.power != null ? opt.power : 26,
      width: opt.width != null ? opt.width : 90
    });
    this._mark(born + life); this._wake();
  }

  /* ══ 입자 ══
     n 개수 · speed [최소,최대] · life 초 · size · color · kind
     gravity · drag · dir 중심방향 · spread 각도폭
     jitter 태어나는 시각을 흩는 폭 · radius 태어나는 자리를 흩는 반지름
     turb 소용돌이 세기 · grow 커지는 정도 · delay
     ⚠️ jitter·radius 가 0 이면 수천 개가 한 점·한 순간에 겹쳐 딱딱한 흰 원반이
        된다. 실제 화약도 순간이 아니라 짧은 시간 동안 터진다. */
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
    const turb = opt.turb != null ? opt.turb : 0;
    const dir = opt.dir != null ? opt.dir : 0;
    const spread = opt.spread != null ? opt.spread : Math.PI * 2;
    const born0 = this._now() + (opt.delay || 0);
    const jit = opt.jitter || 0, rad = opt.radius || 0;

    const from = this.head;
    for (let i = 0; i < n; i++) {
      const k = (from + i) % this.cap, k4 = k * 4;
      const a = dir + (Math.random() - 0.5) * spread;
      // 0.55 승이 불꽃처럼 가운데가 찬다 (제곱근이면 안쪽이 빈다)
      const v = sp[0] + Math.pow(Math.random(), 0.55) * (sp[1] - sp[0]);
      const life = rnd(lf[0], lf[1]);
      const born = born0 + Math.random() * jit;
      const ra = Math.random() * Math.PI * 2, rr = Math.random() * rad;
      this.p0v[k4] = x + Math.cos(ra) * rr;
      this.p0v[k4 + 1] = y + Math.sin(ra) * rr;
      this.p0v[k4 + 2] = Math.cos(a) * v; this.p0v[k4 + 3] = Math.sin(a) * v;
      this.meta[k4] = born; this.meta[k4 + 1] = life;
      this.meta[k4 + 2] = rnd(sz[0], sz[1]); this.meta[k4 + 3] = Math.random();
      this.col[k4] = col[0]; this.col[k4 + 1] = col[1];
      this.col[k4 + 2] = col[2]; this.col[k4 + 3] = kind;
      this.dyn[k4] = grav; this.dyn[k4 + 1] = drag;
      this.dyn[k4 + 2] = grow; this.dyn[k4 + 3] = turb;
      this._mark(born + life);
    }
    this.head = (from + n) % this.cap;
    this._upload(from, n);
    this._wake();
    return n;
  }


  /* ══ 스프라이트 ══ 글자·형상을 GL 안으로 들여온다.
     src   : 캔버스나 이미지 (그려둔 글자·도형)
     x,y,w,h : 화면 픽셀, 왼위 기준
     life  : 초 · delay : 초 뒤에
     in_   : 나타나는 시간(초) — 그 동안 타들어오듯 생긴다
     out_  : 사라지는 시간(초) — 그 동안 재가 되듯 없어진다
     rim/rimColor : 테두리 빛 · sheen : 광택 쓸기 · warp : 열 일렁임
     from/to : {x,y,scale,rot,alpha} 사이를 움직인다 (ease: 'out'|'back'|'in')
     ⚠️ 요소가 '켜졌다/꺼졌다' 가 아니라 '타올랐다/재가 됐다' 로 보여야
        게임 연출처럼 읽힌다. 그게 in_/out_ 가 하는 일이다. */
  sprite(src, o) {
    if (!this.ok || !this.on || !src) return null;
    o = o || {};
    const tex = this._tex2d(src);
    if (!tex) return null;
    const born = this._now() + (o.delay || 0);
    const life = o.life != null ? o.life : 1.2;
    const e = {
      tex, born, life,
      x: o.x || 0, y: o.y || 0, w: o.w || 100, h: o.h || 100,
      from: o.from || null, to: o.to || null, ease: o.ease || 'out',
      inT: o.in_ != null ? o.in_ : 0.34,
      outT: o.out_ != null ? o.out_ : 0.30,
      rim: o.rim != null ? o.rim : 0.9,
      rimCol: toRGB(o.rimColor || '#ffe6a8'),
      burnCol: toRGB(o.burnColor || '#ffd070'),
      burn: o.burn != null ? o.burn : 0.16,
      sheen: o.sheen != null ? o.sheen : 0.0,
      warp: o.warp != null ? o.warp : 0.0,
      alpha: o.alpha != null ? o.alpha : 1
    };
    this.sprites.push(e);
    this._mark(born + life); this._wake();
    return e;
  }

  /* ══ 부서짐 ══ 그림의 픽셀을 훑어 그 자리에서 입자를 뿜는다.
     글자가 '사라지는' 게 아니라 '가루가 된다'. 이 한 수가 값어치를 만든다.
     ⚠️ 픽셀을 CPU 로 훑으므로 촘촘히 보면 안 된다. step 으로 건너뛴다
        (4px 간격이면 1080×300 글자에서 2만 점쯤 — 충분하다). */
  shatter(src, x, y, w, h, o) {
    if (!this.ok || !this.on || !src) return 0;
    o = o || {};
    const px = this._pixels(src);
    if (!px) return 0;
    const step = Math.max(2, o.step || 4);
    const col = o.color ? toRGB(o.color) : null;
    const born = this._now() + (o.delay || 0);
    const life = o.life || [0.7, 1.7];
    const up = o.up != null ? o.up : 260;
    const spread = o.spread != null ? o.spread : 220;
    const grav = o.gravity != null ? o.gravity : 520;
    let n = 0;
    for (let py = 0; py < px.h; py += step) {
      for (let pxx = 0; pxx < px.w; pxx += step) {
        const i = (py * px.w + pxx) * 4;
        if (px.d[i + 3] < 70) continue;               // 비어 있는 자리는 건너뛴다
        const k = (this.head + n) % this.cap, k4 = k * 4;
        const sx = x + (pxx / px.w) * w;
        const sy = y + (py / px.h) * h;
        this.p0v[k4] = sx; this.p0v[k4 + 1] = sy;
        this.p0v[k4 + 2] = (Math.random() - 0.5) * spread;
        this.p0v[k4 + 3] = -up * (0.35 + Math.random() * 0.9);
        this.meta[k4] = born + Math.random() * (o.jitter || 0.12);
        this.meta[k4 + 1] = life[0] + Math.random() * (life[1] - life[0]);
        this.meta[k4 + 2] = (o.size || 2.6) * (0.6 + Math.random() * 0.9);
        this.meta[k4 + 3] = Math.random();
        const c = col || [px.d[i] / 255, px.d[i + 1] / 255, px.d[i + 2] / 255];
        this.col[k4] = c[0]; this.col[k4 + 1] = c[1];
        this.col[k4 + 2] = c[2]; this.col[k4 + 3] = 1;   // 반짝임으로 — 가루가 빛을 되쏜다
        this.dyn[k4] = grav; this.dyn[k4 + 1] = 0.5;
        this.dyn[k4 + 2] = 0; this.dyn[k4 + 3] = 30;
        n++;
        if (n >= this.cap) break;
      }
      if (n >= this.cap) break;
    }
    const from = this.head;
    this.head = (from + n) % this.cap;
    if (n) { this._upload(from, n); this._mark(born + life[1] + (o.jitter || 0.12)); this._wake(); }
    return n;
  }

  /* 같은 그림을 두 번 올리지 않는다 */
  _tex2d(src) {
    if (this._texCache.has(src)) return this._texCache.get(src);
    const gl = this.gl;
    const t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    try { gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, src); }
    catch (e) { return null; }
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    const e = { t, w: src.width, h: src.height };
    this._texCache.set(src, e);
    return e;
  }

  _pixels(src) {
    if (!src.getContext) return null;
    try {
      const c = src.getContext('2d');
      const d = c.getImageData(0, 0, src.width, src.height).data;
      return { d, w: src.width, h: src.height };
    } catch (e) { return null; }
  }

  /* ══════════ 아래는 속 ══════════ */

  _now() { return ((global.performance || Date).now() - this.t0) / 1000; }
  _mark(t) { if (t > this._until) this._until = t; }

  _init() {
    if (this.ok) return true;
    if (this._tried) return false;
    this._tried = true;
    const doc = global.document;
    const cv = doc && doc.createElement ? doc.createElement('canvas') : null;
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
      this.pField = this._link(QUAD_VS, FIELD_FS);
      this.pBright = this._link(QUAD_VS, BRIGHT_FS);
      this.pBlur = this._link(QUAD_VS, BLUR_FS);
      this.pComp = this._link(QUAD_VS, COMP_FS);
      this.pCopy = this._link(QUAD_VS, COPY_FS);
      this.pFade = this._link(QUAD_VS, FADE_FS);
      this.pSpr = this._link(SPR_VS, SPR_FS);
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
    this._u = {                          // 셰이더로 넘길 자리 (매 프레임 새로 안 만든다)
      s0: new Float32Array(MAX_SMOKE * 4), s1: new Float32Array(MAX_SMOKE * 4),
      s2: new Float32Array(MAX_SMOKE * 4),
      g0: new Float32Array(MAX_GLOW * 4), g1: new Float32Array(MAX_GLOW * 4),
      g2: new Float32Array(MAX_GLOW * 4),
      k0: new Float32Array(MAX_SHOCK * 4), k1: new Float32Array(MAX_SHOCK * 4)
    };
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

  /* 쓴 자리만 올린다. 매번 전체(10MB)를 올리면 그게 병목이다. */
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
    if (this.rt) [this.rt.scene, this.rt.field].concat(this.rt.b, this.rt.tmp)
      .forEach(r => { gl.deleteTexture(r.t); gl.deleteFramebuffer(r.f); });
    this.rt = {
      scene: this._tex(w, h),
      // ⚠️ 매질은 1/4 크기로 그린다. 연기는 원래 흐릿한 것이라 눈에 차이가 없는데
      //    비용은 16분의 1 이다. 픽셀마다 노이즈를 수십 번 뽑는 셰이더라
      //    전체 크기로 하면 이것만으로 예산을 다 쓴다.
      field: this._tex(Math.ceil(w / FIELD_DIV), Math.ceil(h / FIELD_DIV)),
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

  /* 살아 있는 것만 남기고 셰이더로 넘길 자리에 채워 넣는다 */
  _packField(t) {
    const u = this._u;
    const S = this.smokes = this.smokes.filter(s => t <= s.born + s.life);
    const G = this.glows = this.glows.filter(g => t <= g.born + g.life);
    for (let i = 0; i < S.length; i++) {
      const s = S[i], j = i * 4;
      u.s0[j] = s.x * this.DPR; u.s0[j + 1] = s.y * this.DPR;
      u.s0[j + 2] = s.r * this.DPR; u.s0[j + 3] = s.born;
      u.s1[j] = s.life; u.s1[j + 1] = s.density; u.s1[j + 2] = s.rise; u.s1[j + 3] = s.swirl;
      u.s2[j] = s.col[0]; u.s2[j + 1] = s.col[1]; u.s2[j + 2] = s.col[2]; u.s2[j + 3] = s.seed;
    }
    for (let i = 0; i < G.length; i++) {
      const g = G[i], j = i * 4;
      u.g0[j] = g.x * this.DPR; u.g0[j + 1] = g.y * this.DPR;
      u.g0[j + 2] = g.r * this.DPR; u.g0[j + 3] = g.born;
      u.g1[j] = g.life; u.g1[j + 1] = g.power; u.g1[j + 2] = g.falloff; u.g1[j + 3] = 0;
      u.g2[j] = g.col[0]; u.g2[j + 1] = g.col[1]; u.g2[j + 2] = g.col[2]; u.g2[j + 3] = 0;
    }
    return { ns: S.length, ng: G.length };
  }

  _packShock(t) {
    const u = this._u;
    const K = this.shocks = this.shocks.filter(k => t <= k.born + k.life);
    for (let i = 0; i < K.length; i++) {
      const k = K[i], j = i * 4;
      u.k0[j] = k.x * this.DPR; u.k0[j + 1] = k.y * this.DPR;
      u.k0[j + 2] = k.born; u.k0[j + 3] = k.life;
      u.k1[j] = k.r0 * this.DPR; u.k1[j + 1] = k.r1 * this.DPR;
      u.k1[j + 2] = k.power * this.DPR; u.k1[j + 3] = k.width * this.DPR;
    }
    return K.length;
  }


  /* 요소는 '켜졌다/꺼졌다' 가 아니라 '타올랐다/재가 됐다' 여야 한다.
     그래서 나타날 때·사라질 때 디졸브 값을 반대 방향으로 굴린다. */
  _drawSprites(t, target) {
    const gl = this.gl, U = (p, n) => gl.getUniformLocation(p, n);
    const L = this.sprites = this.sprites.filter(e => t <= e.born + e.life);
    if (!L.length) return;
    gl.bindFramebuffer(gl.FRAMEBUFFER, target ? target.f : null);
    gl.viewport(0, 0, this.cv.width, this.cv.height);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA);   // 미리 곱해진 알파 위에 얹기
    gl.useProgram(this.pSpr);
    gl.bindVertexArray(this.quadVao);

    for (const e of L) {
      const age = t - e.born;
      if (age < 0) continue;
      const k = age / e.life;
      let dis = 0;
      if (age < e.inT) dis = 1 - age / e.inT;                       // 타올라 나타난다
      else if (age > e.life - e.outT) dis = (age - (e.life - e.outT)) / e.outT;  // 재가 된다
      dis = Math.max(0, Math.min(1, dis));

      // from -> to 사이를 굴린다
      let x = e.x, y = e.y, sc = 1, rot = 0, al = e.alpha;
      if (e.from && e.to) {
        const p = this._ease(Math.min(1, k / Math.max(0.001, e.moveK || 0.42)), e.ease);
        const F = e.from, T = e.to;
        x = (F.x != null ? F.x : e.x) + ((T.x != null ? T.x : e.x) - (F.x != null ? F.x : e.x)) * p;
        y = (F.y != null ? F.y : e.y) + ((T.y != null ? T.y : e.y) - (F.y != null ? F.y : e.y)) * p;
        sc = (F.scale != null ? F.scale : 1) + ((T.scale != null ? T.scale : 1) - (F.scale != null ? F.scale : 1)) * p;
        rot = (F.rot != null ? F.rot : 0) + ((T.rot != null ? T.rot : 0) - (F.rot != null ? F.rot : 0)) * p;
        al *= (F.alpha != null ? F.alpha : 1) + ((T.alpha != null ? T.alpha : 1) - (F.alpha != null ? F.alpha : 1)) * p;
      }
      const w = e.w * sc, h = e.h * sc;
      const cx = x + e.w * 0.5, cy = y + e.h * 0.5;

      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, e.tex.t);
      gl.uniform1i(U(this.pSpr, 'u_tex'), 0);
      gl.uniform4f(U(this.pSpr, 'u_rect'), (cx - w * 0.5) * this.DPR, (cy - h * 0.5) * this.DPR,
                   w * this.DPR, h * this.DPR);
      gl.uniform2f(U(this.pSpr, 'u_res'), this.cv.width, this.cv.height);
      gl.uniform1f(U(this.pSpr, 'u_rot'), rot);
      gl.uniform1f(U(this.pSpr, 'u_t'), t);
      gl.uniform1f(U(this.pSpr, 'u_alpha'), al);
      gl.uniform1f(U(this.pSpr, 'u_dis'), dis);
      gl.uniform1f(U(this.pSpr, 'u_burn'), e.burn);
      gl.uniform1f(U(this.pSpr, 'u_rim'), e.rim);
      gl.uniform1f(U(this.pSpr, 'u_warp'), e.warp);
      gl.uniform1f(U(this.pSpr, 'u_sheen'), e.sheen);
      gl.uniform3f(U(this.pSpr, 'u_rimCol'), e.rimCol[0], e.rimCol[1], e.rimCol[2]);
      gl.uniform3f(U(this.pSpr, 'u_burnCol'), e.burnCol[0], e.burnCol[1], e.burnCol[2]);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }
    gl.bindVertexArray(null);
    gl.blendFunc(gl.ONE, gl.ONE);
  }

  /* 움직임의 결. 'back' 은 목표를 살짝 지나쳤다 돌아온다 —
     이게 있어야 '툭 놓였다' 가 아니라 '내리꽂혔다' 로 읽힌다. */
  _ease(p, kind) {
    p = Math.max(0, Math.min(1, p));
    if (kind === 'in') return p * p * p;
    if (kind === 'back') {
      const c = 1.9;
      const q = p - 1;
      return 1 + (c + 1) * q * q * q + c * q * q;
    }
    const q = 1 - p;
    return 1 - q * q * q;                      // out
  }

  _draw(t) {
    const gl = this.gl, rt = this.rt, U = (p, n) => gl.getUniformLocation(p, n);
    const useBloom = this.bloom > 0;
    gl.disable(gl.DEPTH_TEST);

    // ── 1. 매질 (1/4 크기) ──
    const cnt = this._packField(t);
    if (cnt.ns || cnt.ng) {
      gl.disable(gl.BLEND);
      this._blit(this.pField, rt.field, null, p => {
        gl.uniform1f(U(p, 'u_t'), t);
        gl.uniform2f(U(p, 'u_res'), this.cv.width, this.cv.height);
        gl.uniform1i(U(p, 'u_ns'), cnt.ns);
        gl.uniform1i(U(p, 'u_ng'), cnt.ng);
        gl.uniform4fv(U(p, 'u_s0'), this._u.s0); gl.uniform4fv(U(p, 'u_s1'), this._u.s1);
        gl.uniform4fv(U(p, 'u_s2'), this._u.s2);
        gl.uniform4fv(U(p, 'u_g0'), this._u.g0); gl.uniform4fv(U(p, 'u_g1'), this._u.g1);
        gl.uniform4fv(U(p, 'u_g2'), this._u.g2);
      });
    }

    // ── 2. 무대: 지우기(또는 잔상) → 매질 올리기 → 입자 ──
    const target = useBloom ? rt.scene : null;
    if (this.trail > 0) {
      // 지우는 대신 곱해서 옅게 — 빠른 것이 흐르는 자국을 남긴다
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ZERO, gl.SRC_COLOR);
      this._blit(this.pFade, target, null, p => gl.uniform1f(U(p, 'u_k'), this.trail));
    } else {
      gl.bindFramebuffer(gl.FRAMEBUFFER, target ? target.f : null);
      gl.viewport(0, 0, this.cv.width, this.cv.height);
      gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
    }

    if (cnt.ns || cnt.ng) {
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE);                 // 미리 곱해진 알파끼리 더한다
      this._blit(this.pCopy, target, [['u_src', rt.field]]);
    }

    gl.bindFramebuffer(gl.FRAMEBUFFER, target ? target.f : null);
    gl.viewport(0, 0, this.cv.width, this.cv.height);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE);
    gl.useProgram(this.pDraw);
    gl.uniform1f(U(this.pDraw, 'u_t'), t);
    gl.uniform2f(U(this.pDraw, 'u_res'), this.W, this.H);
    gl.uniform1f(U(this.pDraw, 'u_dpr'), this.DPR);
    gl.uniform1f(U(this.pDraw, 'u_gen'), this._gen || 0);
    gl.bindVertexArray(this.vao);
    gl.drawArrays(gl.POINTS, 0, this.cap);
    gl.bindVertexArray(null);

    // ── 2-b. 스프라이트 (글자·형상) — 입자 위, 빛 번짐 앞 ──
    //   여기서 그려야 같은 빛·그레인·왜곡을 먹는다. 이게 '한 장의 그림' 을 만든다.
    this._drawSprites(t, target);

    if (!useBloom) { gl.disable(gl.BLEND); return; }

    // ── 3. 빛 번짐 ──
    gl.disable(gl.BLEND);
    this._blit(this.pBright, rt.b[0], [['u_src', rt.scene]]);
    for (let i = 0; i < 3; i++) {
      if (i) this._blit(this.pBlur, rt.b[i], [['u_src', rt.b[i - 1]]],
                        p => gl.uniform2f(U(p, 'u_dir'), 0, 0));
      this._blit(this.pBlur, rt.tmp[i], [['u_src', rt.b[i]]],
                 p => gl.uniform2f(U(p, 'u_dir'), 1, 0));
      this._blit(this.pBlur, rt.b[i], [['u_src', rt.tmp[i]]],
                 p => gl.uniform2f(U(p, 'u_dir'), 0, 1));
    }

    // ── 4. 렌즈 ──
    const nk = this._packShock(t);
    this._blit(this.pComp, null,
      [['u_scene', rt.scene], ['u_b1', rt.b[0]], ['u_b2', rt.b[1]], ['u_b3', rt.b[2]]],
      p => {
        gl.uniform1f(U(p, 'u_amt'), this.bloom);
        gl.uniform1f(U(p, 'u_grain'), this.grain);
        gl.uniform1f(U(p, 'u_chrom'), this.chrom);
        gl.uniform1f(U(p, 'u_t'), t);
        gl.uniform2f(U(p, 'u_res'), this.cv.width, this.cv.height);
        gl.uniform1i(U(p, 'u_nk'), nk);
        gl.uniform4fv(U(p, 'u_k0'), this._u.k0);
        gl.uniform4fv(U(p, 'u_k1'), this._u.k1);
      });
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
  // 남은 것이 없으면 여기서 끊는다 — 방송 내내 도는 루프를 만들지 않는다
  if (t > SigGL._until + 0.05) return;
  SigGL._raf = requestAnimationFrame(SigGL._tick);
};

if (typeof module !== 'undefined' && module.exports) module.exports = SigGL;
global.SigGL = SigGL;
})(typeof window !== 'undefined' ? window : this);
