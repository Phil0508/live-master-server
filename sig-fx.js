/*
 * 시그니처 전용 연출 17선 — 엔젤컴퍼니
 * 순수 CSS/JS. 외부 라이브러리·이미지·이모지 없음.
 *
 * 사용법
 *   <div id="stage" style="position:relative;width:1920px;height:1080px;overflow:hidden"></div>
 *   <script src="sig-fx.js"></script>
 *   SigFX.play('gazua', document.getElementById('stage'));
 *
 * play(key, stageEl, opts?)
 *   key     : SigFX.ITEMS 의 key ('gazua' … 'mvp')
 *   stageEl : 1920x1080 기준의 컨테이너 (position:relative / overflow:hidden 필수)
 *   opts.image  : 시그니처 사진 주소. 넘기면 연출 바탕이 그 사진이 된다
 *   opts.colors : 사진에서 뽑은 대표색 배열. 넘기면 빛·테두리·글자 색이 이걸 따른다
 *   opts.card   : 시그니처 카드 요소. 넘기면 연출이 카드 등장 시점까지 맡는다
 *   ⚠️ 세 개 다 없어도 정상 동작한다 (없으면 기본 색·기본 타이밍)
 *   opts    : { speed: 1, impact: 1 }  speed↑ = 빠름, impact = 흔들림·글리치 세기
 *
 * 연출 레이어는 stageEl 안에 z-index:60 으로 잠깐 생겼다 스스로 사라집니다.
 * 화면 흔들림은 stageEl 의 첫 자식(또는 [data-shake] 요소)에 걸립니다 —
 * 흔들 대상이 없으면 흔들림만 생략되고 나머지는 그대로 동작합니다.
 *
 * 폰트: Black Han Sans / Anton / Cormorant Garamond / IBM Plex Sans KR
 *   <link href="https://fonts.googleapis.com/css2?family=Black+Han+Sans&family=Anton&family=Cormorant+Garamond:wght@300&family=IBM+Plex+Sans+KR:wght@400;600;700&display=swap" rel="stylesheet">
 */
(function (global) {
'use strict';

class SigEngine {
  constructor() {
    this.opts = { speed: 1, impact: 1 };
    // ⚠️ null 로 시작해야 한다. undefined 면 첫 재생의 _cleanup() 이
    //    --reac-glow 에 문자열 'undefined' 를 써버려 카드 테두리·발광이 죽는다.
    this._glowPrev = null;
  }

  // ⚠️ 이 두 개가 없으면 dur / this.S 가 NaN 이 되어 animate() 가 통째로 던진다.
  //    (연출 17개가 전부 첫 줄에서 죽는다 — 화면에 아무것도 안 나온다)
  get S() { return this.opts.speed  || 1; }   // 속도 배수 (↑ 빠름)
  get P() { return this.opts.impact || 1; }   // 흔들림·충격 세기

  /* ══ 좌표 옮기기 ══
     이 파일의 연출은 전부 1920x1080 '가로' 를 머릿속에 두고 좌표를 박아 넣었다.
     그런데 이 방송판은 1080x1920 '세로' 다. 가로 그림을 그대로 얹으면 양옆이
     잘려나가고, 축소해 넣으면 위아래가 텅 빈다.
     그래서 그리기 직전에 좌표만 세로 판으로 옮긴다. 연출 코드는 손대지 않는다.

       가로 위치 : 화면 한가운데를 기준으로 접어 넣는다 (x' = W/2 + (x-960)*KS)
       세로 위치 : 화면 높이에 비례해 편다   (y' = y * KY)  → 위는 위, 아래는 아래
       길이·글자 : 한 배율(KS)로만 키우고 줄인다 → 동그란 것이 타원이 되지 않는다

     ⚠️ left:0 / right:0 / top:0 / bottom:0 은 '화면 끝' 을 뜻하므로 건드리지 않는다.
        (0 은 어느 판에서도 0 이다 — inset:0 같은 전면 레이어가 여기 걸린다)
     ⚠️ % 값도 건드리지 않는다. 원래부터 판 크기에 맞춰 도는 값이다. */
  _fit(stageEl) {
    const W = stageEl.clientWidth || 1920, H = stageEl.clientHeight || 1080;
    this.W = W; this.H = H;
    const portrait = H > W;

    /* ⚠️ 유튜브 세로 라이브는 위에 채널줄(0~4%), 아래 절반에 채팅이 깔린다.
       읽어야 하는 것은 그 사이에만 둔다. 실측 근거는 docs/이펙트개편.md.
       기기·앱이 바뀌면 이 두 숫자만 고치면 된다. */
    this.SAFE_TOP = portrait ? 0.06 : 0;
    this.SAFE_BOT = portrait ? 0.50 : 1;

    /* ⚠️ '위치 배율' 과 '크기 배율' 을 갈라놓는다.
       예전에는 하나(KS)로 둘 다 했다. 세로판에서 글자가 작아지지 않게 1.6배를
       올렸는데 그게 가로 위치까지 벌려서, 설계 폭 1920 이 1728 로 펴져 1080 판
       가운데 놓였다(-324~1404). 설계의 가운데 62% 만 화면에 남고 양옆은 잘렸다
       — 부티호텔은 43개 중 35개가 화면 밖이었다. */
    this.KX = W / 1920;                                      // 가로 위치·거리
    this.YT = H * this.SAFE_TOP;                             // 안전지대가 시작하는 곳
    this.KY = H * (this.SAFE_BOT - this.SAFE_TOP) / 1080;    // 세로 위치·거리
    this.KS = this.KX * (portrait ? 1.39 : 1);               // 크기·글자만
  }
  _n(v, k) { return +(parseFloat(v) * k).toFixed(1); }
  // 가로 위치: 설계 폭 1920 을 화면 폭에 그대로 넣는다 (가운데 기준 접기를 없앴다)
  _x(v) { return +(parseFloat(v) * this.KX).toFixed(1); }
  _r(v) { return +(parseFloat(v) * this.KX).toFixed(1); }
  // 세로 위치: 설계 0~1080 을 안전지대 안으로
  _y(v) { return +(this.YT + parseFloat(v) * this.KY).toFixed(1); }
  // 아래에서 잰 위치도 같은 자로 — 안전지대 바닥에서부터 센다
  _b(v) { return +(this.H - this.YT - (1080 - parseFloat(v)) * this.KY).toFixed(1); }
  // 화면(연출 레이어)에 바로 붙은 것인가. 아니면 좌표가 '부모 기준' 이다.
  _stage(p) {
    try { return !!(p && p.getAttribute && p.getAttribute('data-sigfx') !== null); }
    catch (e) { return false; }
  }

  /* rel = 좌표가 '부모 기준' 인가. 화면에 바로 붙은 게 아니면 안전지대로 접으면 안 된다
     — 부모 안에서의 어긋남이라 부모와 같은 배율(크기 배율)로만 줄여야 모양이 산다.
     (크레이지의 하트가 실제로 이것 때문에 찌그러져 있었다) */
  mapCss(css, rel) {
    if (!css || (this.KX === 1 && this.KY === 1 && this.KS === 1 && !this.YT)) return css;
    const X = rel ? (v => this._n(v, this.KS)) : (v => this._x(v));
    const R = rel ? (v => this._n(v, this.KS)) : (v => this._r(v));
    const Y = rel ? (v => this._n(v, this.KS)) : (v => this._y(v));
    const B = rel ? (v => this._n(v, this.KS)) : (v => this._b(v));
    return css
      // 위치 — 0 은 화면 끝이므로 그대로 둔다
      .replace(/(^|[;{\s])left:\s*(-?\d*\.?\d+)px/g,   (m,p,v) => +v === 0 ? m : p + 'left:'   + X(v) + 'px')
      .replace(/(^|[;{\s])right:\s*(-?\d*\.?\d+)px/g,  (m,p,v) => +v === 0 ? m : p + 'right:'  + R(v) + 'px')
      .replace(/(^|[;{\s])top:\s*(-?\d*\.?\d+)px/g,    (m,p,v) => +v === 0 ? m : p + 'top:'    + Y(v) + 'px')
      .replace(/(^|[;{\s])bottom:\s*(-?\d*\.?\d+)px/g, (m,p,v) => +v === 0 ? m : p + 'bottom:' + B(v) + 'px')
      /* % 로 잡은 세로 위치도 같이 접는다.
         ⚠️ 예전에는 % 를 안 건드렸다 — 그때는 설계 0~1080 이 화면 0~100% 로 그대로
            펴져서 50% 가 곧 50% 였기 때문이다. 안전지대로 접으면 더는 같지 않다.
         ⚠️ 0%·100% 밖(음수·초과)은 '일부러 화면을 넘긴 것' 이라 그대로 둔다. */
      .replace(/(^|[;{\s])top:\s*(\d*\.?\d+)%/g, (m,p,v) =>
        (rel || +v <= 0 || +v >= 100) ? m
          : p + 'top:' + (((this.YT + (+v) / 100 * 1080 * this.KY) / this.H) * 100).toFixed(2) + '%')
      .replace(/(^|[;{\s])bottom:\s*(\d*\.?\d+)%/g, (m,p,v) =>
        (rel || +v <= 0 || +v >= 100) ? m
          : p + 'bottom:' + (((this.H - this.YT - (100 - +v) / 100 * 1080 * this.KY) / this.H) * 100).toFixed(2) + '%')
      // 길이·글자 — 한 배율로만
      .replace(/(width|height|font-size|letter-spacing|border-radius|border-width|padding|margin|blur|gap):\s*(-?\d*\.?\d+)px/g,
               (m,p,v) => +v === 0 ? m : p + ':' + this._n(v, this.KS) + 'px')
      .replace(/border:\s*(-?\d*\.?\d+)px/g, (m,v) => 'border:' + this._n(v, this.KS) + 'px')
      .replace(/blur\((-?\d*\.?\d+)px\)/g,  (m,v) => 'blur('   + this._n(v, this.KS) + 'px)')
      // 움직이는 거리는 '위치' 와 같은 자로 재야 한다 (부모 기준이면 부모 배율로)
      .replace(/translateX\((-?\d*\.?\d+)px\)/g, (m,v) => 'translateX(' + this._n(v, rel ? this.KS : this.KX) + 'px)')
      .replace(/translateY\((-?\d*\.?\d+)px\)/g, (m,v) => 'translateY(' + this._n(v, rel ? this.KS : this.KY) + 'px)');
  }

  // 애니메이션 프레임 안의 transform 문자열도 같은 규칙으로 옮긴다
  mapFrames(frames, rel) {
    if (this.KX === 1 && this.KY === 1 && this.KS === 1) return frames;
    const KX = rel ? this.KS : this.KX, KY = rel ? this.KS : this.KY;
    return frames.map(f => {
      if (!f || typeof f.transform !== 'string') return f;
      const t = f.transform
        .replace(/translateX\((-?\d*\.?\d+)px\)/g, (m,v) => 'translateX(' + this._n(v, KX) + 'px)')
        .replace(/translateY\((-?\d*\.?\d+)px\)/g, (m,v) => 'translateY(' + this._n(v, KY) + 'px)')
        .replace(/translate\((-?\d*\.?\d+)px\s*,\s*(-?\d*\.?\d+)px\)/g,
                 (m,a,b) => 'translate(' + this._n(a, KX) + 'px,' + this._n(b, KY) + 'px)');
      return Object.assign({}, f, { transform: t });
    });
  }

  /* cardAt = 연출이 카드를 올릴 시점(ms). 연출 안에서 cardIn() 을 부르면 그게 우선한다.
     dur 은 실제 연출 길이 — play() 가 이 값으로 정리 시점을 잡으니 반드시 맞춰 둔다. */
  ITEMS = [
    { key: 'gazua',  tier: '10만',    name: '가즈아',        note: '화염 분출',   dur: 1.8, cardAt: 620,  detail: '흰 컷이 때리고 빠지며 불기둥이 치솟습니다' },
    { key: 'lambada',tier: '13만',    name: '람바다',        note: '선셋 탱고',   dur: 2.2, cardAt: 700,  detail: '레트로 선셋이 떠오르고 야자 실루엣이 펼쳐집니다' },
    { key: 'hotel',  tier: '15만',    name: '부티호텔',      note: '간판 점등',   dur: 2.6, cardAt: 1050, detail: '암전 뒤 호텔 간판이 지지직거리다 탁 켜지고 별 다섯이 박힙니다' },
    { key: 'crazy',  tier: '16만',    name: '크레이지 러브', note: '하트 초신성', dur: 2.4, cardAt: 1250, detail: '한 점으로 빨려들었다 하트 충격파가 터집니다' },
    { key: 'bounce', tier: '18만',    name: '바운스',        note: '네온 낙하',   dur: 2.4, cardAt: 1500, detail: '네온 글자가 하나씩 떨어져 튕기고 마지막에 쿵 하고 붙습니다' },
    { key: 'martini',tier: '20만',    name: '마티니',        note: '마티니 타임', dur: 2.8, cardAt: 900,  detail: '화면이 흑백으로 내려앉고 금빛이 한 번 스칩니다' },
    { key: 'pocha',  tier: '200,001', name: '뽀카치포',      note: '스트립 질주', dur: 2.4, cardAt: 1900, detail: '네온 간판이 빛줄기로 흐르고 급브레이크로 멈춥니다' },
    { key: 'pucha',  tier: '30만',    name: '푸차',          note: '명패 각인',   dur: 3.0, cardAt: 1950, detail: '파란 대리석에 글자가 파이고 금물이 흘러 찹니다' },
    { key: 'edm',    tier: '35만',    name: 'EDM',           note: '크리스탈 파열', dur: 2.6, cardAt: 700,  detail: '초록 균열이 갈라지고 스캔라인이 어긋납니다' },
    { key: 'sail',   tier: '50만',    name: '출항',          note: '부채 펼침',   dur: 3.4, cardAt: 1500, detail: '접선부채가 살부터 펼쳐지고 비단 광택이 훑고 지나갑니다' },
    { key: 'shield', tier: '500,001', name: '50만 방패',     note: '방패 강림',   dur: 3.2, cardAt: 1040, detail: '방패가 내려찍히고 충격파와 분홍 번개가 터집니다' },
    { key: 'slash',  tier: '600,001', name: '74번 알림',     note: '참격',        dur: 2.6, cardAt: 1100, detail: 'X자로 두 번 베고 화면이 갈라집니다' },
    { key: 'nuna',   tier: '70만',    name: '누나누나',      note: '장미 개화',   dur: 3.2, cardAt: 1500, detail: '꽃잎이 테두리에 붙어 액자가 되고 결이 퍼집니다' },
    { key: 'club',   tier: '80만',    name: '클럽음악',      note: '드롭',        dur: 3.4, cardAt: 1400, detail: '빌드업 뒤 0.2초 정적, 그리고 드롭' },
    { key: 'vip',    tier: '100만',   name: 'VIP',           note: 'VIP 입장',    dur: 4.6, cardAt: 900,  detail: '금속 광택이 글자 위를 한 번 지나갑니다' },
    { key: 'angel',  tier: '200만',   name: '엔젤 VIP',      note: '천상 강림',   dur: 5.2, cardAt: 1100, detail: '빛기둥이 내려오고 날개가 천천히 펼쳐집니다' },
    { key: 'mvp',    tier: '300만',   name: 'MVP',           note: '대관식',      dur: 7.5, cardAt: 2500, detail: '불꽃놀이 뒤 왕관이 내려오고 인장이 찍힙니다' },
  ];

  play(key, stageEl, opts) {
    const item = this.ITEMS.find(i => i.key === key);
    if (!item) { console.warn('SigFX: 알 수 없는 key —', key); return 0; }
    this.opts = Object.assign({ speed: 1, impact: 1 }, opts);
    this._fit(stageEl);   // 판 크기를 재서 좌표 옮김 배율을 정한다

    // 시그니처 연동 재료. 없으면 null — 연출은 기본 색으로 그대로 간다.
    this.img  = this.opts.image || null;
    this.C    = (Array.isArray(this.opts.colors) && this.opts.colors.length) ? this.opts.colors : null;
    this.card = this.opts.card || null;

    // ⚠️ 앞 연출 정리를 먼저 한다. 후원이 연달아 들어올 때 여기서 흔적이 남아 사고가 난다.
    this._cleanup();
    const old = stageEl.querySelector(':scope > [data-sigfx]');
    if (old) old.remove();

    // 흔들 대상. 오버레이처럼 무대와 방송 내용물이 다른 요소일 때는 opts.shakeEl 로 지정한다.
    const shake = this.opts.shakeEl || stageEl.querySelector('[data-shake]') || stageEl.firstElementChild || stageEl;
    shake.getAnimations().forEach(a => a.cancel());
    this._shakeEl = shake;
    this._cardAnims = [];
    this._cardDone = false;
    this._glowPrev = null;
    this._glowEl = null;

    const fx = document.createElement('div');
    fx.setAttribute('data-sigfx', key);
    fx.style.cssText = 'position:absolute;inset:0;overflow:hidden;pointer-events:none;z-index:60;';
    stageEl.appendChild(fx);

    // ⚠️ 연출이 터져도 시그니처 재생은 그대로 가야 한다. 예외를 밖으로 내보내지 않는다.
    try { this['fx_' + key](fx, shake); }
    catch (e) { console.warn('SigFX: 연출 실패 —', key, e); }

    // 연출이 카드를 직접 다루지 않았으면 기본 시점에 올려준다.
    try { this.cardIn(item.cardAt != null ? item.cardAt : 300); } catch (e) {}

    const ms = (item.dur * 1000 + 160) / this.opts.speed;
    this._timer = setTimeout(() => {
      if (fx.parentNode) fx.remove();
      this._cleanup();
    }, ms);
    return ms;
  }

  /* 남은 것 되돌리기.
     ⚠️ transform 이 굳어 남는 사고가 실제로 있었다. 카드·흔들 대상의 애니메이션은
        commitStyles 하지 않고 cancel 해서 원래 스타일로 되돌린다. */
  /* 재생 중인 연출을 즉시 끝낸다. 방송의 '전체 비우기'(리액션 강제 중단)가 이 경로다.

     ⚠️ 레이어([data-sigfx])만 지우면 안 된다. 카드에 걸린 애니메이션은 fill:'both' 라
        카드 요소 쪽에 붙어 살아남는다 — 레이어를 지워도 카드가 투명한 채(opacity 0,
        scale 0.84) 화면에 남는다. 실제로 그 사고를 재현해 확인했다.
        반드시 _cleanup() 을 함께 불러 카드 애니메이션을 취소하고 발광색을 되돌려야 한다. */
  stop(stageEl) {
    this._cleanup();
    if (stageEl) stageEl.querySelectorAll('[data-sigfx]').forEach(n => n.remove());
  }

  _cleanup() {
    if (this._timer) { clearTimeout(this._timer); this._timer = null; }
    (this._cardAnims || []).forEach(a => { try { a.cancel(); } catch (e) {} });
    this._cardAnims = [];
    if (this._glowEl && this._glowPrev !== null) {
      try {
        // 원래 인라인 값이 없었으면 지운다. 빈 문자열을 써 넣는 것으로는 안 지워진다.
        if (this._glowPrev) this._glowEl.style.setProperty('--reac-glow', this._glowPrev);
        else this._glowEl.style.removeProperty('--reac-glow');
      } catch (e) {}
      this._glowPrev = null;
      this._glowEl = null;
    }
    if (this._shakeEl) {
      try { this._shakeEl.getAnimations().forEach(a => a.cancel()); } catch (e) {}
    }
  }

  /* ══ 시그니처 연동 도우미 ══ */

  // 사진에서 뽑은 색. 없으면 연출별 기본색으로 되돌아간다.
  col(i, fallback) {
    if (!this.C) return fallback;
    return this.C[i % this.C.length] || fallback;
  }

  /* ① 바탕을 시그니처 사진으로 깐다.
     크게 확대 + 블러 + 어둡게 → 연출의 색·질감이 사진과 어긋날 수가 없다.
     사진이 없으면 아무것도 만들지 않고 null 을 돌려준다(부르는 쪽은 신경 쓸 필요 없다). */
  photoBg(fx, o) {
    if (!this.img) return null;
    o = o || {};
    const from = o.from || 1.42, mid = o.mid || 1.2, to = o.to || 1.12;
    const max = o.max != null ? o.max : .85;
    const l = this.mk(fx, 'inset:0;background-image:url("' + this.img + '");background-size:cover;background-position:center;' +
      'filter:blur(' + (o.blur != null ? o.blur : 26) + 'px) brightness(' + (o.bright != null ? o.bright : .42) + ') saturate(' + (o.sat != null ? o.sat : 1.25) + ');' +
      'opacity:0;transform:scale(' + from + ');' + (o.blend ? 'mix-blend-mode:' + o.blend + ';' : ''));
    this.a(l, [
      { opacity: 0, transform: 'scale(' + from + ')' },
      { opacity: max, transform: 'scale(' + mid + ')', offset: .22 },
      { opacity: max, transform: 'scale(' + to + ')', offset: o.hold != null ? o.hold : .8 },
      { opacity: 0, transform: 'scale(' + to + ')' },
    ], o.dur || 2200, o.delay || 0, 'cubic-bezier(.3,0,.35,1)');
    return l;
  }

  /* ③ 카드 등장을 연출이 맡는다.
     fill:'both' 라서 delay 전에는 카드가 숨어 있다
     → "연출이 자리를 만들고, 그 자리에 카드가 놓인다" 가 한 동작이 된다.
     각 연출은 자기 클라이맥스 시점을 넘긴다. 안 부르면 play() 가 기본값으로 부른다. */
  cardIn(delay, o) {
    if (this._cardDone || !this.card) return;
    this._cardDone = true;
    o = o || {};
    const frames = o.frames || [
      { opacity: 0, transform: (o.from || 'scale(.84)'), offset: 0 },
      { opacity: 1, transform: 'scale(1.035)', offset: .62 },
      { opacity: 1, transform: 'scale(1)', offset: 1 },
    ];
    try {
      const timing = {
        duration: (o.dur || 520) / this.S,
        delay: Math.max(0, delay || 0) / this.S,
        easing: o.ease || 'cubic-bezier(.16,1,.3,1)',
        fill: 'both',
      };
      // ⚠️ transform 을 통째로 덮어쓰면 안 된다. 카드에는 대개 자리를 잡는
      //    transform(translate(-50%,-50%) 같은 것)이 이미 걸려 있는데, 여기서
      //    scale(.84) 로 갈아치우면 그 정렬이 날아가 카드가 화면 밖으로 밀린다.
      //    실측: 넘기는 순간 (156,466) → (601,1039) 로 튕겨 나갔다.
      //    그래서 두 갈래로 나눈다 —
      //      투명도는 그대로 덮어쓰고(replace),
      //      transform 은 원래 값 뒤에 이어 붙인다(composite:'add').
      const opa = frames.map(f => {
        const g = {};
        if (f.opacity !== undefined) g.opacity = f.opacity;
        if (f.offset !== undefined) g.offset = f.offset;
        return g;
      });
      const trs = frames.map(f => {
        const g = {};
        if (f.transform !== undefined) g.transform = f.transform;
        if (f.offset !== undefined) g.offset = f.offset;
        return g;
      });
      if (opa.some(g => g.opacity !== undefined)) {
        this._cardAnims.push(this.card.animate(opa, timing));
      }
      if (trs.some(g => g.transform !== undefined)) {
        this._cardAnims.push(this.card.animate(trs, Object.assign({ composite: 'add' }, timing)));
      }
    } catch (e) {}
  }

  /* ④ 연출의 빛이 카드에 닿게 — 카드 테두리 발광색을 연출 색과 맞춘다. */
  cardGlow(color) {
    if (!this.card || !color) return;
    try {
      if (this._glowPrev === null) {
        this._glowPrev = this.card.style.getPropertyValue('--reac-glow');
        // ⚠️ 되돌릴 대상을 같이 붙잡아 둔다. play() 는 this.card 를 새 카드로 바꾼 뒤에
        //    _cleanup() 을 부르기 때문에, this.card 만 보고 되돌리면 '앞 카드의 원래 색'
        //    을 '뒤 카드' 에 써버린다.
        this._glowEl = this.card;
      }
      this.card.style.setProperty('--reac-glow', color);
    } catch (e) {}
  }

  mk(p, css) {
    const d = document.createElement('div');
    d.style.cssText = 'position:absolute;' + this.mapCss(css, !this._stage(p));
    p.appendChild(d);
    return d;
  }
  a(el, frames, dur, delay, ease) {
    return el.animate(this.mapFrames(frames, !this._stage(el.parentNode)),
                      { duration: dur / this.S, delay: (delay || 0) / this.S, easing: ease || 'linear', fill: 'forwards' });
  }
  /* 히트스톱 — 착탄 순간 모든 것이 멈추는 구간.
     같은 transform 을 두 프레임에 넣어 '정지'를 만든다.
     ⚠️ 인라인 style 로는 안 된다. 앞선 애니메이션이 fill:'forwards' 라 style 을 이긴다.
        정지도 애니메이션이어야 걸린다.
     충격의 무게는 '계속 흐르는 것' 이 아니라 '멈추는 것' 에서 나온다. */
  hold(el, tf, ms, delay) {
    return this.a(el, [{ transform: tf }, { transform: tf }], ms, delay, 'linear');
  }
  txt(fx, content, css, top) {
    // ⚠️ 가로로 꽉 찬 줄이라 left/right 은 0 그대로 두고 top 만 옮긴다.
    // ⚠️ opacity:0 이 없으면 delay 동안 글자가 그대로 보인다. fill:'forwards' 는
    //    active 가 끝난 뒤에만 걸리므로 delay 구간(before)을 못 막는다.
    //    실측: 참격 1120ms · ANGEL VIP 1400ms · 방패 1040ms 동안 글자가 떠 있었다.
    //    ⚠️ 래퍼를 켜주는 애니메이션이 없는 연출은 글자가 영영 안 뜬다 —
    //       fx_martini · fx_angel 이 그랬고, 거기에 래퍼 켜기를 따로 넣어뒀다.
    // ⚠️ 여기서 KY 를 곱하면 안 된다 — mk→mapCss 가 top 을 또 접는다(KY² = 3.16배).
    //    그것 때문에 '가즈아'(설계 640)가 1138 이 아니라 2023 에 앉아 화면(1920) 밖으로
    //    나갔고, 퇴장 애니메이션이 밀어올리는 마지막 0.5초만 화면 맨 아래를 스쳤다.
    const w = this.mk(fx, 'left:0;right:0;top:' + top + 'px;display:flex;justify-content:center;opacity:0;');
    const d = document.createElement('div'); d.textContent = content;
    d.style.cssText = this.mapCss(css, true); w.appendChild(d);
    return { w: w, d: d };
  }
  flash(fx, color, op, dur, delay) {
    const f = this.mk(fx, 'inset:0;background:' + color + ';opacity:0;mix-blend-mode:screen;');
    this.a(f, [{ opacity: op }, { opacity: 0 }], dur, delay, 'linear');
    return f;
  }
  /* 화면 흔들기.
     ⚠️ 카드가 흔들 대상 밖에 있어서 예전엔 카드만 가만히 있어 붕 떠 보였다.
        같은 프레임을 카드에도 걸어 함께 흔든다(카드가 없으면 건너뛴다).
        composite:'add' 라 카드 등장 애니메이션의 scale 을 덮어쓰지 않는다. */
  shake(shake, amp, dur, delay) {
    const n = Math.max(6, Math.round(dur / 26)), fr = [];
    for (let i = 0; i <= n; i++) {
      const f = Math.pow(1 - i / n, 1.6);
      fr.push({ transform: 'translate(' + ((Math.random() * 2 - 1) * amp * this.P * f * this.KS).toFixed(1) + 'px,' + ((Math.random() * 2 - 1) * amp * this.P * f * this.KS).toFixed(1) + 'px)' });
    }
    fr.push({ transform: 'translate(0,0)' });
    const timing = { duration: dur / this.S, delay: (delay || 0) / this.S, easing: 'linear' };
    shake.animate(fr, timing);
    if (this.card && !this.card.contains(shake) && !shake.contains(this.card)) {
      try {
        const a = this.card.animate(fr, Object.assign({ composite: 'add' }, timing));
        this._cardAnims.push(a);
      } catch (e) {}
    }
  }
  rnd(a, b) { return a + Math.random() * (b - a); }

  /* ══ 10만 가즈아 — 화염 분출 (1.8s) ══
     착탄 프레임 IMP=150. 재료는 원본과 같고 '언제 터지느냐'만 바꿨다.
     ① 움츠림 0–95 → ② 돌진 95–150 → ③ 착탄 150–200(정지) → ④ 반동 → ⑤ 이차운동 */
  fx_gazua(fx, shake) {
    const FIRE = this.col(0, '#ff4d00'), EMBER = this.col(1, '#ffa02a'), SPARK = this.col(2, '#ffd24a');
    const IMP = 150;
    this.cardGlow(FIRE);
    // ⚠️ 사진은 반드시 맨 먼저 깐다. photoBg 는 fx 에 덧붙이므로 부르는 순서가 곧
    //    쌓이는 순서다 — 흰 종이 뒤에 부르면 사진이 종이 위에 얹혀 둘 다 죽는다.
    this.photoBg(fx, { delay: 600, dur: 1300, blur: 24, bright: .4, max: .8, from: 1.3, to: 1.1 });

    /* ① 움츠림 0–95 — 흰 띠가 한 점에서 가로로 찢어진다. 끝까지 가속. */
    const band = this.mk(fx, 'left:0;right:0;top:50%;height:6px;background:#fff;transform:translateY(-50%) scaleX(.02);opacity:0;');
    this.a(band, [{ transform: 'translateY(-50%) scaleX(.02)', opacity: .45 },
                  { transform: 'translateY(-50%) scaleX(1)',   opacity: 1 }],
           95, 0, 'cubic-bezier(.8,0,.95,.4)');

    /* ② 돌진 95–150 — 흰 종이가 42ms 만에 덮는다 (원본 400ms) */
    const sheet = this.mk(fx, 'inset:0;background:#f7f4ec;opacity:0;');
    this.a(sheet, [{ opacity: 0 }, { opacity: 1 }], 42, 95, 'cubic-bezier(.75,0,.9,.45)');
    this.a(sheet, [{ opacity: 1 }, { opacity: .95 }], 260, 137);
    this.a(sheet, [{ clipPath: 'inset(0 0 0 0)' }, { clipPath: 'inset(0 0 100% 0)' }],
           175, 430, 'cubic-bezier(.75,0,.2,1)');

    /* ③ 착탄 150–200 */
    this.flash(fx, '#ffffff', 1, 30, IMP);                       // 원본 110ms → 30ms
    this.a(band, [{ transform: 'translateY(-50%) scaleX(1) scaleY(1)',  opacity: 1 },
                  { transform: 'translateY(-50%) scaleX(1) scaleY(11)', opacity: 0 }],
           90, IMP, 'cubic-bezier(.1,.85,.25,1)');                // 띠가 세로로 터진다

    const lines = this.mk(fx, 'inset:-25%;opacity:0;background:repeating-conic-gradient(from 0deg at 50% 50%, #111 0deg .55deg, transparent .55deg 2.6deg);-webkit-mask-image:radial-gradient(circle at 50% 50%, transparent 24%, #000 62%);mask-image:radial-gradient(circle at 50% 50%, transparent 24%, #000 62%);');
    this.a(lines, [{ opacity: 0,  transform: 'scale(2.2)' },
                   { opacity: 1,  transform: 'scale(1) rotate(2deg)',    offset: .05 },
                   { opacity: .5, transform: 'scale(1.05) rotate(3deg)', offset: .45 },
                   { opacity: 0,  transform: 'scale(1.3) rotate(5deg)' }],
           1150, IMP, 'cubic-bezier(.06,.95,.2,1)');
    this.shake(shake, 42, 300, IMP);
    this.shake(shake, 9,  190, IMP + 320);

    /* 불기둥 — 원본은 180~380 에 흩어져 있었다. 착탄 프레임에 모은다. */
    [-620, -330, 0, 350, 640].forEach((x, i) => {
      const w = 40 + (i % 2) * 30;
      const ch = this.mk(fx, 'left:50%;bottom:0;width:' + w + 'px;height:920px;background:linear-gradient(to top,' + FIRE + ',' + EMBER + ' 40%,rgba(255,180,60,0));clip-path:polygon(50% 0,100% 14%,100% 100%,0 100%,0 14%);opacity:0;');
      this.a(ch, [{ transform: 'translateX(' + x + 'px) translateY(340px)',  opacity: 0 },
                  { transform: 'translateX(' + x + 'px) translateY(-120px)', opacity: .95, offset: .30 },
                  { transform: 'translateX(' + x + 'px) translateY(-760px)', opacity: 0 }],
             640, IMP + 20 + i * 26, 'cubic-bezier(.15,.9,.28,1)');
    });

    for (let i = 0; i < 20; i++) {
      const s = this.rnd(4, 9);
      const p = this.mk(fx, 'left:' + this.rnd(0, 1900).toFixed(0) + 'px;bottom:0;width:' + s.toFixed(1) + 'px;height:' + s.toFixed(1) + 'px;background:' + SPARK + ';');
      this.a(p, [{ transform: 'translateY(0)', opacity: 1 },
                 { transform: 'translateY(-' + this.rnd(500, 1000).toFixed(0) + 'px) translateX(' + this.rnd(-140, 140).toFixed(0) + 'px)', opacity: 0 }],
             this.rnd(650, 1200), IMP + this.rnd(0, 420), 'cubic-bezier(.3,0,.6,1)');
    }

    /* 글자 — 늘어남 → 히트스톱 → 반동. 원본은 균일 scale 이라 안 눌렸다.
       ⚠️ 아래 네 개는 만든 순서 = 시작 순서다. 나중에 만든 것이 앞의 fill 을 이긴다. */
    const t = this.txt(fx, '가즈아', "font-family:'Black Han Sans',sans-serif;font-size:214px;line-height:.9;color:#14110c;letter-spacing:-.02em;transform:skewX(-7deg);", 640);
    // ② 돌진 (95–150) : 세로로 늘어난 채 아래에서 솟는다
    this.a(t.w, [{ transform: 'translateY(150px) scale(.78,1.52)', opacity: 0 },
                 { transform: 'translateY(14px)  scale(.93,1.24)', opacity: 1 }],
           55, 95, 'cubic-bezier(.65,.02,.95,.5)');
    // ③ 히트스톱 (150–200) : 납작하게 눌린 채 정지. opacity 도 잡아둬야 해서 hold() 대신 a()
    this.a(t.w, [{ transform: 'translateY(0) scale(1.34,.70)', opacity: 1 },
                 { transform: 'translateY(0) scale(1.34,.70)', opacity: 1 }], 50, IMP);
    // ④ 반동 (200–540)
    this.a(t.w, [{ transform: 'translateY(0) scale(1.34,.70)' },
                 { transform: 'translateY(-6px) scale(.94,1.08)', offset: .42 },
                 { transform: 'translateY(0) scale(1.03,.98)',    offset: .72 },
                 { transform: 'translateY(0) scale(1,1)' }],
           340, IMP + 50, 'cubic-bezier(.2,.85,.3,1)');
    // ⑤ 떠 있다 퇴장
    this.a(t.w, [{ transform: 'translateY(0) scale(1,1)',         opacity: 1 },
                 { transform: 'translateY(-14px) scale(1,1)',     opacity: 1, offset: .62 },
                 { transform: 'translateY(-190px) scale(1.04,1)', opacity: 0 }],
           1220, IMP + 390, 'cubic-bezier(.4,0,.3,1)');
    this.a(t.d, [{ color: '#14110c' }, { color: '#fdfaf2' }], 1, 560);
  }

  /* ══ 13만 람바다 — 선셋 탱고 (2.2s) ══ */
  fx_lambada(fx) {
    const SUN = this.col(0, '#ff7a2e'), GLOW = this.col(2, '#ffd98a');
    this.cardGlow(SUN);
    this.photoBg(fx, { delay: 120, dur: 2000, blur: 28, bright: .4, max: .78 });
    const wash = this.mk(fx, 'inset:0;background:linear-gradient(to top,rgba(255,86,40,.62),rgba(255,150,60,.28) 48%,rgba(58,20,74,.34));opacity:0;');
    this.a(wash, [{ opacity: 0 }, { opacity: 1, offset: .22 }, { opacity: 1, offset: .8 }, { opacity: 0 }], 2200, 0, 'cubic-bezier(.3,0,.4,1)');

    const sun = this.mk(fx, 'left:50%;bottom:60px;width:520px;height:520px;border-radius:50%;background:linear-gradient(to top,' + SUN + ',' + GLOW + ');transform:translateX(-50%) translateY(340px);opacity:0;-webkit-mask-image:linear-gradient(#000 0 62%, transparent 62% 65%, #000 65% 74%, transparent 74% 78%, #000 78% 85%, transparent 85% 89%, #000 89%);mask-image:linear-gradient(#000 0 62%, transparent 62% 65%, #000 65% 74%, transparent 74% 78%, #000 78% 85%, transparent 85% 89%, #000 89%);');
    this.a(sun, [{ transform: 'translateX(-50%) translateY(340px)', opacity: 0 }, { transform: 'translateX(-50%) translateY(40px)', opacity: .95, offset: .34 }, { transform: 'translateX(-50%) translateY(0)', opacity: .95, offset: .78 }, { transform: 'translateX(-50%) translateY(-30px)', opacity: 0 }], 2200, 60, 'cubic-bezier(.16,1,.3,1)');

    // 야자 실루엣 (좌우 잎사귀 부채꼴)
    [[-40, 1], [1960, -1]].forEach((side, si) => {
      const trunk = this.mk(fx, 'left:' + side[0] + 'px;bottom:-40px;width:26px;height:520px;background:#180a14;transform-origin:50% 100%;transform:rotate(' + (side[1] * 9) + 'deg) scaleY(0);');
      this.a(trunk, [{ transform: 'rotate(' + (side[1] * 9) + 'deg) scaleY(0)' }, { transform: 'rotate(' + (side[1] * 9) + 'deg) scaleY(1)' }], 620, 120 + si * 90, 'cubic-bezier(.16,1,.3,1)');
      [-64, -30, 4, 40, 74].forEach((rot, i) => {
        const lf = this.mk(fx, 'left:' + side[0] + 'px;bottom:400px;width:340px;height:74px;background:#180a14;border-radius:100% 0 100% 0;transform-origin:0% 100%;transform:scaleX(' + side[1] + ') rotate(0deg) scale(.1);opacity:0;');
        this.a(lf, [{ transform: 'scaleX(' + side[1] + ') rotate(0deg) scale(.2)', opacity: 0 }, { transform: 'scaleX(' + side[1] + ') rotate(' + rot + 'deg) scale(1)', opacity: 1 }], 560, 380 + si * 90 + i * 55, 'cubic-bezier(.16,1,.3,1)');
      });
    });

    for (let i = 0; i < 12; i++) {
      const s = this.rnd(11, 20), c = ['#ffd07a', '#ff6a3d', '#ffe8bd'][i % 3];
      const p = this.mk(fx, 'left:' + this.rnd(100, 1820).toFixed(0) + 'px;top:-40px;width:' + s.toFixed(0) + 'px;height:' + (s * .62).toFixed(0) + 'px;border-radius:100% 0 100% 0;background:' + c + ';');
      this.a(p, [{ transform: 'translateY(0) rotate(0deg)', opacity: 0 }, { opacity: .9, offset: .12 }, { transform: 'translateY(1180px) translateX(' + this.rnd(-220, 220).toFixed(0) + 'px) rotate(' + this.rnd(-400, 400).toFixed(0) + 'deg)', opacity: 0 }], this.rnd(1500, 2100), this.rnd(0, 700), 'cubic-bezier(.4,0,.6,1)');
    }

    const t = this.txt(fx, '람바다', "font-family:'IBM Plex Sans KR',sans-serif;font-weight:600;font-size:104px;line-height:1;color:#fff6e6;letter-spacing:.3em;", 470);
    this.a(t.w, [{ transform: 'translateY(26px)', opacity: 0 }, { transform: 'translateY(0)', opacity: 1, offset: .3 }, { transform: 'translateY(0)', opacity: 1, offset: .78 }, { transform: 'translateY(-18px)', opacity: 0 }], 2100, 420, 'cubic-bezier(.16,1,.3,1)');
  }

  /* ══ 15만 부티호텔 — 간판 점등 (2.6s) ══
     밤 골목에서 호텔 네온 간판이 지지직거리다 '탁' 켜지는 그림.
     착탄 프레임 IMP=620 — 간판이 완전히 켜지는 그 순간에 전부 모은다.

     ⚠️ 처음부터 다시 짠 연출이다. 예전 판은 방송에서 "전혀 안 보인다" 였다.
        좌표가 잘려 45개 중 35개가 화면 밖에 그려진 탓도 있었지만, 그걸 고치고
        봐도 약했다 — 간판이 테두리뿐이라 속이 비었고, 창문이 34px 라 잔글씨
        같았고, 암전이 길어 '어두워졌다 밝아진다' 로만 보였다.

     ⚠️ 좌표: 가로는 ×0.5625, 크기는 ×0.782, 세로는 안전지대로 접힌다.
        배율이 다르므로 화면에서 원하는 자리를 먼저 정하고 거꾸로 계산했다. */
  fx_hotel(fx, shake) {
    const NEON = this.col(0, '#4fc3ff'), WARM = this.col(2, '#ffd48a'), GOLD = this.col(1, '#ffc861');
    const IMP = 620;
    this.cardGlow(NEON);
    // 사진 바탕은 점등 뒤에 들어온다 — 암전이 먼저여야 점등이 세다.
    this.photoBg(fx, { delay: 780, dur: 1700, blur: 30, bright: .34, max: .7 });

    /* ① 암전 — 툭 꺼진다. 짧게. (예전엔 0.3초 정적이라 늘어졌다) */
    const black = this.mk(fx, 'inset:0;background:#04060a;opacity:0;');
    this.a(black, [{ opacity: 0 }, { opacity: 1, offset: .05 }, { opacity: 1, offset: .18 },
                   { opacity: .74, offset: .28 }, { opacity: .58, offset: .84 }, { opacity: 0 }],
           2500, 0);

    /* ② 건물 창문 — 좌우 기둥에서 아래에서 위로 한 줄씩. 크게, 또렷하게.
       (예전엔 42개를 34px 로 흩뿌려서 아무것도 안 읽혔다 → 20개를 60px 로) */
    [[36, 200], [1600, 1764]].forEach((colx, ci) => {
      [940, 780, 620, 460, 300].forEach((wy, row) => {
        colx.forEach((wx, k) => {
          const w = this.mk(fx, 'left:' + wx + 'px;top:' + wy + 'px;width:77px;height:97px;background:' + WARM +
            ';box-shadow:0 0 34px ' + WARM + ';opacity:0;');
          this.a(w, [{ opacity: 0 }, { opacity: .9, offset: .05 }, { opacity: .5, offset: .72 }, { opacity: 0 }],
                 1900, 170 + row * 64 + k * 26 + ci * 34, 'steps(1,end)');
        });
      });
    });

    /* ③ 간판 몸통 — 꺼진 채로 아래에서 올라와 자리를 잡는다.
       속이 빈 테두리가 아니라 '판' 이다. 안에 꺼진 네온관(흐린 글자)이 비쳐 있다. */
    const sign = this.mk(fx, 'left:50%;top:428px;width:895px;height:300px;' +
      'transform:translate(-50%,-50%) translateY(80px) scale(.96);opacity:0;' +
      'background:linear-gradient(160deg,rgba(9,14,24,.95),rgba(5,8,15,.98));' +
      'border:9px solid rgba(86,116,146,.5);border-radius:20px;');
    const off = document.createElement('div');
    off.textContent = 'HOTEL';
    off.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;' +
      this.mapCss("font-family:'Anton',sans-serif;font-size:153px;letter-spacing:22px;color:rgba(124,154,180,.32);", true);
    sign.appendChild(off);
    this.a(sign, [{ transform: 'translate(-50%,-50%) translateY(80px) scale(.96)', opacity: 0 },
                  { transform: 'translate(-50%,-50%) translateY(0) scale(1)', opacity: 1 }],
           300, 260, 'cubic-bezier(.16,1,.3,1)');

    /* ④ 점등된 네온 — 지지직 두 번 실패하고, 착탄에서 완전히 붙는다.
       ⚠️ 만든 순서 = 시작 순서다. 나중에 만든 것이 앞의 fill 을 이긴다. */
    const neon = this.mk(fx, 'left:50%;top:428px;width:895px;height:300px;transform:translate(-50%,-50%);' +
      'border:9px solid ' + NEON + ';border-radius:20px;opacity:0;' +
      'box-shadow:0 0 64px ' + NEON + ', inset 0 0 52px ' + NEON + ';');
    const lit = document.createElement('div');
    lit.textContent = 'HOTEL';
    lit.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;' +
      this.mapCss("font-family:'Anton',sans-serif;font-size:153px;letter-spacing:22px;color:#f4fcff;", true) +
      'text-shadow:0 0 16px ' + NEON + ',0 0 44px ' + NEON + ',0 0 92px ' + NEON + ';';
    neon.appendChild(lit);
    this.a(neon, [{ opacity: .85 }, { opacity: 0 }], 70, IMP - 250, 'steps(1,end)');   // 지직
    this.a(neon, [{ opacity: 1 },   { opacity: 0 }], 50, IMP - 120, 'steps(1,end)');   // 지직
    this.a(neon, [{ opacity: 1 }, { opacity: 1, offset: .84 }, { opacity: 0 }], 1560, IMP);   // 탁

    /* ⑤ 착탄 620 — 플래시 · 히트스톱 · 흔들림 */
    this.flash(fx, '#eaf7ff', .85, 30, IMP);
    this.hold(sign, 'translate(-50%,-50%) scale(1.07,.91)', 50, IMP);
    this.hold(neon, 'translate(-50%,-50%) scale(1.07,.91)', 50, IMP);
    [sign, neon].forEach(el => {
      this.a(el, [{ transform: 'translate(-50%,-50%) scale(1.07,.91)' },
                  { transform: 'translate(-50%,-50%) scale(.98,1.04)', offset: .45 },
                  { transform: 'translate(-50%,-50%) scale(1,1)' }],
             320, IMP + 50, 'cubic-bezier(.2,.85,.3,1)');
    });
    this.shake(shake, 30, 300, IMP);
    this.shake(shake, 8, 180, IMP + 320);

    /* 간판에서 빛이 아래로 쏟아진다 */
    const spill = this.mk(fx, 'left:50%;top:579px;width:1150px;height:501px;transform:translate(-50%,0);' +
      'background:linear-gradient(to bottom,' + NEON + ',rgba(79,195,255,0) 78%);opacity:0;' +
      'clip-path:polygon(28% 0,72% 0,100% 100%,0 100%);mix-blend-mode:screen;');
    this.a(spill, [{ opacity: 0 }, { opacity: .5, offset: .1 }, { opacity: .2, offset: .6 }, { opacity: 0 }],
           1500, IMP, 'cubic-bezier(.2,.9,.3,1)');

    /* 별 다섯 — 호텔 등급. 착탄 뒤에 하나씩 톡톡 (이차운동) */
    [676, 800, 924, 1049, 1173].forEach((sx, i) => {
      const star = this.mk(fx, 'left:' + sx + 'px;top:172px;width:51px;height:51px;background:' + GOLD +
        ';clip-path:polygon(50% 0,61% 35%,98% 35%,68% 57%,79% 91%,50% 70%,21% 91%,32% 57%,2% 35%,39% 35%);' +
        'box-shadow:0 0 30px ' + GOLD + ';opacity:0;transform:scale(0) rotate(-40deg);');
      this.a(star, [{ transform: 'scale(0) rotate(-40deg)', opacity: 0 },
                    { transform: 'scale(1.35) rotate(7deg)', opacity: 1, offset: .5 },
                    { transform: 'scale(1) rotate(0deg)', opacity: 1 }],
             300, IMP + 60 + i * 80, 'cubic-bezier(.2,1.5,.4,1)');
      this.a(star, [{ opacity: 1 }, { opacity: 1, offset: .78 }, { opacity: 0 }],
             1180, IMP + 460 + i * 80);
    });

    /* 간판이 물러난다 */
    [sign, neon].forEach(el => {
      this.a(el, [{ transform: 'translate(-50%,-50%) scale(1,1)', opacity: 1 },
                  { transform: 'translate(-50%,-50%) scale(1,1)', opacity: 1, offset: .84 },
                  { transform: 'translate(-50%,-50%) translateY(-40px) scale(1.02)', opacity: 0 }],
             1540, IMP + 400, 'cubic-bezier(.4,0,.3,1)');
    });

    const cap = this.txt(fx, '부티호텔', "font-family:'IBM Plex Sans KR',sans-serif;font-weight:400;font-size:76px;letter-spacing:20px;color:rgba(222,242,255,.92);", 671);
    this.a(cap.w, [{ transform: 'translateY(24px)', opacity: 0 },
                   { transform: 'translateY(0)', opacity: 1, offset: .32 },
                   { transform: 'translateY(0)', opacity: 1, offset: .82 },
                   { transform: 'translateY(-16px)', opacity: 0 }],
           1480, IMP + 240, 'cubic-bezier(.16,1,.3,1)');

    this.cardIn(1050, { from: 'scale(.9)', dur: 480 });
  }

  /* ══ 16만 크레이지 러브 — 하트 초신성 (2.4s) ══
     사진은 분홍 글자 + 무지개 성운. 빨려들었다 '하트 모양' 으로 터진다. */
  fx_crazy(fx, shake) {
    const P1 = this.col(0, '#ff5fa2'), P2 = this.col(1, '#b06cff'), P3 = this.col(2, '#22e6ff');
    this.cardGlow(P1);
    this.photoBg(fx, { delay: 1150, dur: 1250, blur: 22, bright: .44, max: .85, from: 1.3, to: 1.08 });

    // 화면이 한 점으로 수축했다가 되돌아온다
    this.a(shake, [
      { transform: 'scale(1)' },
      { transform: 'scale(.74)', offset: .34 }, { transform: 'scale(.7)', offset: .44 },
      { transform: 'scale(1.06)', offset: .52 }, { transform: 'scale(1)', offset: .68 },
    ], 2300, 0, 'cubic-bezier(.5,0,.3,1)');

    // ① 주변을 삼키는 어둠 — 가운데 한 점만 남는다
    const suck = this.mk(fx, 'inset:0;background:radial-gradient(circle at 50% 50%, transparent 0%, rgba(2,0,6,.2) 12%, rgba(2,0,6,.97) 46%);transform:scale(2.2);opacity:0;');
    this.a(suck, [{ opacity: 0, transform: 'scale(2.4)' }, { opacity: 1, transform: 'scale(.5)', offset: .46 }, { opacity: .9, transform: 'scale(.42)', offset: .52 }, { opacity: 0, transform: 'scale(3)' }], 2300, 0, 'cubic-bezier(.55,0,.3,1)');

    const pt = this.mk(fx, 'left:960px;top:540px;width:30px;height:30px;border-radius:50%;background:#fff;box-shadow:0 0 60px #fff;transform:translate(-50%,-50%) scale(0);');
    this.a(pt, [{ transform: 'translate(-50%,-50%) scale(0)' }, { transform: 'translate(-50%,-50%) scale(1.5)', offset: .42 }, { transform: 'translate(-50%,-50%) scale(.4)', offset: .5 }, { transform: 'translate(-50%,-50%) scale(9)', opacity: 0, offset: .62 }, { opacity: 0 }], 2300, 0, 'cubic-bezier(.5,0,.3,1)');

    // ② 하트 충격파 — 원+사각 조합. 세 겹이 시차를 두고 터져 나간다.
    const IMP = 1150;
    this.flash(fx, '#ffffff', .95, 110, IMP);
    [[P1, 0, 1], [P2, 70, .8], [P3, 150, .55]].forEach(v => {
      const h = this.mk(fx, 'left:960px;top:540px;width:420px;height:420px;transform:translate(-50%,-50%) rotate(-45deg) scale(.06);mix-blend-mode:screen;opacity:' + v[2] + ';');
      this.mk(h, 'left:0;top:0;width:300px;height:300px;background:' + v[0] + ';');
      this.mk(h, 'left:-150px;top:0;width:300px;height:300px;border-radius:50%;background:' + v[0] + ';');
      this.mk(h, 'left:0;top:-150px;width:300px;height:300px;border-radius:50%;background:' + v[0] + ';');
      this.a(h, [{ transform: 'translate(-50%,-50%) rotate(-45deg) scale(.06)', opacity: v[2] }, { transform: 'translate(-50%,-50%) rotate(-45deg) scale(4.6)', opacity: 0 }], 900, IMP + v[1], 'cubic-bezier(.15,.9,.3,1)');
    });

    // ③ 지나간 자리에 남는 무지개 성운
    const neb = this.mk(fx, 'left:960px;top:540px;width:2000px;height:2000px;border-radius:50%;transform:translate(-50%,-50%) scale(.4);mix-blend-mode:screen;opacity:0;' +
      'background:conic-gradient(from 0deg,' + P1 + ',' + P2 + ',' + P3 + ',' + P1 + ');' +
      '-webkit-mask-image:radial-gradient(circle,transparent 26%,#000 44%,#000 62%,transparent 76%);mask-image:radial-gradient(circle,transparent 26%,#000 44%,#000 62%,transparent 76%);');
    this.a(neb, [{ opacity: 0, transform: 'translate(-50%,-50%) scale(.4) rotate(0deg)' }, { opacity: .8, transform: 'translate(-50%,-50%) scale(1) rotate(60deg)', offset: .3 }, { opacity: .6, transform: 'translate(-50%,-50%) scale(1.1) rotate(120deg)', offset: .8 }, { opacity: 0, transform: 'translate(-50%,-50%) scale(1.3) rotate(160deg)' }], 1250, IMP, 'cubic-bezier(.2,.8,.3,1)');

    this.shake(shake, 30, 340, IMP);
    this.cardIn(IMP + 100, { from: 'scale(.7)', dur: 460 });
  }

  
  /* ══ 18만 바운스 — 네온 낙하 (2.4s) ══
     네온 글자 여섯 자가 위에서 차례로 떨어져 바닥에 부딪히고 튕긴다.
     마지막 글자가 닿는 순간이 착탄이다. IMP=560.

     ⚠️ 처음부터 다시 짠 연출이다. 예전 판은 세 가지가 문제였다.
        · 부티호텔과 똑같이 생겼다 — 둘 다 화면 정중앙 700×235 네온 사각형
        · 착탄이 없다 (흔들림 6, 마무리 깜빡임 opacity .2) — 2.4초 내내
          천천히 차오르기만 하고 터지는 데가 없었다
        · 점 12개가 뜻 없이 흩뿌려져 지저분하기만 했다
        부티호텔은 '가만히 서 있는 간판', 이쪽은 '떨어져 튀는 글자' 로 갈랐다. */
  fx_bounce(fx, shake) {
    const RED = this.col(0, '#ff2d4d'), WARM = this.col(2, '#ffcf9a');
    const IMP = 560;
    this.cardGlow(RED);
    this.photoBg(fx, { delay: 180, dur: 2000, blur: 28, bright: .34, max: .76 });

    const dim = this.mk(fx, 'inset:0;background:rgba(6,2,6,.62);opacity:0;');
    this.a(dim, [{ opacity: 0 }, { opacity: 1, offset: .07 }, { opacity: 1, offset: .84 }, { opacity: 0 }], 2300);

    /* ① 바닥 네온 줄 — 글자가 여기에 부딪힌다. 가운데에서 좌우로 그어진다 */
    const floor = this.mk(fx, 'left:213px;top:645px;width:1074px;height:15px;background:' + RED +
      ';border-radius:15px;box-shadow:0 0 34px ' + RED + ', 0 0 70px ' + RED + ';transform:scaleX(0);');
    this.a(floor, [{ transform: 'scaleX(0)', opacity: 1 }, { transform: 'scaleX(1)', opacity: 1 }],
           260, 120, 'cubic-bezier(.16,1,.3,1)');

    /* ② 글자 여섯 자가 왼쪽부터 하나씩 낙하 → 닿는 자리에서 납작해졌다 튄다.
       ⚠️ 글자는 row 의 자식이라 좌표가 '부모 기준' 이다 — 옮기는 배율이 다르다. */
    const row = this.mk(fx, 'left:0;right:0;top:364px;display:flex;justify-content:center;gap:14px;');
    'BOUNCE'.split('').forEach((ch, i) => {
      const d = document.createElement('div');
      d.textContent = ch;
      d.style.cssText = this.mapCss("font-family:'Anton',sans-serif;font-size:215px;line-height:1;color:#fff3f4;", true) +
        'text-shadow:0 0 22px ' + RED + ',0 0 54px ' + RED + ',0 0 110px ' + RED + ';opacity:0;';
      row.appendChild(d);

      const land = IMP - 150 + i * 30;                    // 이 글자가 닿는 시각
      // 낙하 — 끝까지 가속해야 부딪히는 것으로 보인다
      this.a(d, [{ transform: 'translateY(-620px) scale(.86,1.3)', opacity: 0 },
                 { transform: 'translateY(-620px) scale(.86,1.3)', opacity: 1, offset: .06 },
                 { transform: 'translateY(0) scale(.92,1.16)', opacity: 1 }],
             300, land - 300, 'cubic-bezier(.7,0,.95,.45)');
      // 착지 — 납작하게 눌린 채 멈춘다
      this.a(d, [{ transform: 'translateY(0) scale(1.2,.76)', opacity: 1 },
                 { transform: 'translateY(0) scale(1.2,.76)', opacity: 1 }], 50, land);
      // 튄다
      this.a(d, [{ transform: 'translateY(0) scale(1.2,.76)' },
                 { transform: 'translateY(-58px) scale(.94,1.1)', offset: .42 },
                 { transform: 'translateY(0) scale(1.04,.97)', offset: .74 },
                 { transform: 'translateY(0) scale(1,1)' }],
             340, land + 50, 'cubic-bezier(.2,.85,.3,1)');
      // 여운 — 한 번 더 작게
      this.a(d, [{ transform: 'translateY(0) scale(1,1)' },
                 { transform: 'translateY(-16px) scale(.99,1.02)', offset: .45 },
                 { transform: 'translateY(0) scale(1,1)' }],
             300, land + 420, 'cubic-bezier(.3,.7,.4,1)');
      // 퇴장
      this.a(d, [{ transform: 'translateY(0) scale(1,1)', opacity: 1 },
                 { transform: 'translateY(0) scale(1,1)', opacity: 1, offset: .82 },
                 { transform: 'translateY(-40px) scale(1.02,1)', opacity: 0 }],
             900, IMP + 900, 'cubic-bezier(.4,0,.3,1)');
    });

    /* ③ 착탄 560 — 마지막 글자가 쿵 */
    this.flash(fx, '#ffe9ec', .8, 30, IMP);
    this.shake(shake, 34, 300, IMP);
    this.shake(shake, 9, 190, IMP + 320);
    // 바닥 줄이 한 번 굵어졌다 돌아온다
    this.a(floor, [{ transform: 'scaleX(1) scaleY(2.6)' },
                   { transform: 'scaleX(1) scaleY(1)' }], 260, IMP, 'cubic-bezier(.1,.9,.25,1)');
    // 윗 네온 줄이 탁 붙는다 (아래와 짝을 이뤄 사인이 완성된다)
    const top = this.mk(fx, 'left:213px;top:287px;width:1074px;height:15px;background:' + RED +
      ';border-radius:15px;box-shadow:0 0 34px ' + RED + ', 0 0 70px ' + RED + ';opacity:0;transform:scaleX(.2);');
    this.a(top, [{ transform: 'scaleX(.2)', opacity: 0 }, { transform: 'scaleX(1)', opacity: 1 }],
           220, IMP, 'cubic-bezier(.1,.9,.25,1)');

    /* 바닥에서 충격 링 두 겹 */
    [0, 90].forEach((d2, i) => {
      const ring = this.mk(fx, 'left:960px;top:645px;width:420px;height:120px;border-radius:50%;' +
        // ⚠️ opacity:0 으로 시작해야 한다 — 애니메이션이 560ms 부터라,
        //    그 앞 구간에는 fill 이 안 걸려 링이 처음부터 떠 있게 된다.
        'border:' + (10 - i * 3) + 'px solid ' + RED + ';transform:translate(-50%,-50%) scale(.2);opacity:0;');
      this.a(ring, [{ transform: 'translate(-50%,-50%) scale(.2)', opacity: .9 },
                    { transform: 'translate(-50%,-50%) scale(' + (3.4 + i) + ')', opacity: 0 }],
             720 + i * 120, IMP + d2, 'cubic-bezier(.12,.92,.28,1)');
    });

    /* ④ 네온 점 — 흩뿌리지 않는다. 바닥 줄에서 튀어오른다 */
    for (let i = 0; i < 10; i++) {
      const sz = this.rnd(20, 40), dia = i % 2 === 0;
      const p = this.mk(fx, 'left:' + (300 + i * 148).toFixed(0) + 'px;top:645px;' +
        'width:' + sz.toFixed(0) + 'px;height:' + sz.toFixed(0) + 'px;background:' + (i % 3 ? RED : WARM) + ';' +
        (dia ? 'transform:rotate(45deg);' : 'border-radius:50%;') +
        'opacity:0;box-shadow:0 0 26px ' + (i % 3 ? RED : WARM) + ';');
      this.a(p, [{ transform: 'translateY(0) rotate(0deg)', opacity: 0 },
                 { transform: 'translateY(-' + this.rnd(210, 430).toFixed(0) + 'px) translateX(' +
                   this.rnd(-90, 90).toFixed(0) + 'px) rotate(' + this.rnd(-200, 200).toFixed(0) + 'deg)',
                   opacity: .95, offset: .34 },
                 { transform: 'translateY(0) translateX(' + this.rnd(-140, 140).toFixed(0) + 'px) rotate(' +
                   this.rnd(-360, 360).toFixed(0) + 'deg)', opacity: 0 }],
             this.rnd(900, 1400), IMP + 20 + i * 34, 'cubic-bezier(.3,0,.6,1)');
    }

    /* 네온 줄 퇴장 */
    [floor, top].forEach(el => {
      this.a(el, [{ opacity: 1 }, { opacity: 1, offset: .8 }, { opacity: 0 }], 900, IMP + 900);
    });

    const cap = this.txt(fx, '바운스', "font-family:'IBM Plex Sans KR',sans-serif;font-weight:400;font-size:76px;letter-spacing:20px;color:rgba(255,228,231,.9);", 720);
    this.a(cap.w, [{ transform: 'translateY(22px)', opacity: 0 },
                   { transform: 'translateY(0)', opacity: 1, offset: .3 },
                   { transform: 'translateY(0)', opacity: 1, offset: .82 },
                   { transform: 'translateY(-16px)', opacity: 0 }],
           1420, IMP + 300, 'cubic-bezier(.16,1,.3,1)');

    this.cardIn(1500, { from: 'scale(.92)', dur: 440 });
  }

  /* ══ 20만 마티니 — 마티니 타임 (2.8s) ══ */
  fx_martini(fx) {
    const GOLD = this.col(2, '#c9a227');
    this.cardGlow(GOLD);
    // 흑백 배경 위라 사진은 아주 옅게만 — 여기서 진하게 깔면 흑백이 무너진다.
    this.photoBg(fx, { delay: 300, dur: 2300, blur: 34, bright: .3, max: .5 });
    const mono = this.mk(fx, 'inset:0;backdrop-filter:grayscale(1) contrast(1.06) brightness(.82);-webkit-backdrop-filter:grayscale(1) contrast(1.06) brightness(.82);opacity:0;');
    this.a(mono, [{ opacity: 0 }, { opacity: 1, offset: .22 }, { opacity: 1, offset: .8 }, { opacity: 0 }], 2800, 0, 'cubic-bezier(.4,0,.3,1)');
    const vig = this.mk(fx, 'inset:0;background:radial-gradient(100% 76% at 50% 48%,rgba(0,0,0,.15),rgba(0,0,0,.8));opacity:0;');
    this.a(vig, [{ opacity: 0 }, { opacity: 1, offset: .22 }, { opacity: 1, offset: .8 }, { opacity: 0 }], 2800);

    // 금 코너 브래킷 4개
    [[70, 70, 1, 1], [1850, 70, -1, 1], [70, 1010, 1, -1], [1850, 1010, -1, -1]].forEach((c, i) => {
      const h = this.mk(fx, 'left:' + c[0] + 'px;top:' + c[1] + 'px;width:220px;height:2px;background:' + GOLD + ';transform-origin:' + (c[2] > 0 ? '0%' : '100%') + ' 50%;transform:scaleX(0);');
      this.a(h, [{ transform: 'scaleX(0)' }, { transform: 'scaleX(' + c[2] + ')' }], 700, 200 + i * 70, 'cubic-bezier(.16,1,.3,1)');
      const v = this.mk(fx, 'left:' + c[0] + 'px;top:' + c[1] + 'px;width:2px;height:150px;background:' + GOLD + ';transform-origin:50% ' + (c[3] > 0 ? '0%' : '100%') + ';transform:scaleY(0);');
      this.a(v, [{ transform: 'scaleY(0)' }, { transform: 'scaleY(' + c[3] + ')' }], 700, 260 + i * 70, 'cubic-bezier(.16,1,.3,1)');
    });

    const sweep = this.mk(fx, 'top:-20%;bottom:-20%;left:0;width:340px;background:linear-gradient(90deg,rgba(255,240,200,0),rgba(255,238,190,.16),rgba(255,240,200,0));mix-blend-mode:screen;transform:skewX(-13deg) translateX(-460px);');
    this.a(sweep, [{ transform: 'skewX(-13deg) translateX(-460px)' }, { transform: 'skewX(-13deg) translateX(2100px)' }], 1500, 700, 'cubic-bezier(.42,0,.5,1)');

    [[430, 300], [1490, 250], [960, 790], [1660, 690], [330, 740]].forEach((p, i) => {
      const g = this.mk(fx, 'left:' + p[0] + 'px;top:' + p[1] + 'px;width:2px;height:56px;background:#f6e7b4;transform:translate(-50%,-50%);');
      const g2 = this.mk(fx, 'left:' + p[0] + 'px;top:' + p[1] + 'px;width:56px;height:2px;background:#f6e7b4;transform:translate(-50%,-50%);');
      [g, g2].forEach(e => this.a(e, [{ transform: 'translate(-50%,-50%) scale(0) rotate(0deg)', opacity: 0 }, { transform: 'translate(-50%,-50%) scale(1) rotate(45deg)', opacity: 1, offset: .35 }, { transform: 'translate(-50%,-50%) scale(0) rotate(90deg)', opacity: 0 }], 800, 700 + i * 230, 'cubic-bezier(.3,0,.4,1)'));
    });

    const t = this.txt(fx, 'MARTINI', "font-family:'Cormorant Garamond',serif;font-weight:300;font-size:132px;line-height:1;color:#f2e6c8;", 480);
    // 이 연출은 안쪽 글자만 움직인다. 래퍼는 글자가 시작하는 시각에 켜준다.
    this.a(t.w, [{ opacity: 1 }, { opacity: 1 }], 1, 300);
    this.a(t.d, [{ letterSpacing: '.62em', opacity: 0 }, { letterSpacing: '.34em', opacity: 1, offset: .34 }, { letterSpacing: '.32em', opacity: 1, offset: .8 }, { letterSpacing: '.32em', opacity: 0 }], 2600, 300, 'cubic-bezier(.16,1,.3,1)');
    const t2 = this.txt(fx, '마티니', "font-family:'IBM Plex Sans KR',sans-serif;font-weight:400;font-size:38px;color:rgba(242,230,200,.72);letter-spacing:.4em;", 660);
    this.a(t2.w, [{ opacity: 0 }, { opacity: 1, offset: .4 }, { opacity: 1, offset: .8 }, { opacity: 0 }], 2200, 900);
  }

  /* ══ 200,001 뽀카치포 — 스트립 질주 (2.4s) ══
     사진은 밤에 오픈카로 네온 스트립을 달리는 장면.
     간판이 소실점에서 튀어나와 양옆으로 흘러 지나간다 → 마지막에 급브레이크. */
  fx_pocha(fx, shake) {
    const N1 = this.col(0, '#ff2bd0'), N2 = this.col(1, '#22e6ff'), G = this.col(2, '#ffd24a');
    this.cardGlow(G);
    this.photoBg(fx, { delay: 0, dur: 2300, blur: 30, bright: .3, max: .72, from: 1.5, to: 1.15 });

    const night = this.mk(fx, 'inset:0;background:rgba(3,2,10,.6);opacity:0;');
    this.a(night, [{ opacity: 0 }, { opacity: 1, offset: .08 }, { opacity: 1, offset: .82 }, { opacity: 0 }], 2300);

    // ① 소실점에서 간판이 흘러 나온다. scale 이 커지면서 좌우로 밀려 지나간다.
    for (let i = 0; i < 26; i++) {
      const side = i % 2 ? 1 : -1;
      const c = [N1, N2, G][i % 3];
      const w = this.rnd(120, 300), h = this.rnd(26, 90);
      const y = 540 + this.rnd(-360, 360);
      const sg = this.mk(fx, 'left:960px;top:' + y.toFixed(0) + 'px;width:' + w.toFixed(0) + 'px;height:' + h.toFixed(0) + 'px;' +
        'background:linear-gradient(90deg,' + c + ',rgba(255,255,255,.9));box-shadow:0 0 30px ' + c + ';mix-blend-mode:screen;transform:translate(-50%,-50%) scale(.06);opacity:0;');
      this.a(sg, [
        { transform: 'translate(-50%,-50%) translateX(0px) scale(.06)', opacity: 0 },
        { opacity: 1, offset: .18 },
        { transform: 'translate(-50%,-50%) translateX(' + (side * 1500).toFixed(0) + 'px) scale(2.4)', opacity: 0 },
      ], this.rnd(420, 700), this.rnd(0, 1600), 'cubic-bezier(.35,0,.65,1)');
    }

    // ② 속도가 붙을수록 가장자리가 휜다
    const warp = this.mk(fx, 'inset:0;background:radial-gradient(58% 58% at 50% 50%, transparent 40%, rgba(2,2,8,.85) 100%);opacity:0;');
    this.a(warp, [{ opacity: 0, transform: 'scale(1.4)' }, { opacity: .5, transform: 'scale(1.1)', offset: .3 }, { opacity: .9, transform: 'scale(1)', offset: .78 }, { opacity: 0, transform: 'scale(1.2)' }], 2300, 0, 'cubic-bezier(.4,0,.5,1)');

    // 흔들림 간격이 좁아진다 = 속도감
    [60, 420, 720, 960, 1150, 1300, 1420, 1520, 1620, 1700, 1780].forEach((ms, i) => this.shake(shake, 8 + i, 130, ms));

    // ③ 급브레이크 — 흰 섬광, 정지, 그리고 카드가 박힌다
    const BRK = 1900;
    this.flash(fx, '#ffffff', .9, 130, BRK);
    this.a(shake, [{ transform: 'scale(1.04) skewX(-4deg)' }, { transform: 'scale(1) skewX(0)' }], 260, BRK, 'cubic-bezier(.1,.9,.2,1)');
    const streak = this.mk(fx, 'left:0;right:0;top:540px;height:14px;background:linear-gradient(90deg,transparent,' + G + ',transparent);mix-blend-mode:screen;transform:scaleX(0);');
    this.a(streak, [{ transform: 'scaleX(0)', opacity: 1 }, { transform: 'scaleX(1)', opacity: 1, offset: .3 }, { transform: 'scaleX(1)', opacity: 0 }], 500, BRK, 'cubic-bezier(.1,.9,.2,1)');
    this.shake(shake, 34, 300, BRK);
    this.cardIn(BRK, { from: 'scale(1.45)', dur: 340, ease: 'cubic-bezier(.08,.95,.2,1)' });
  }

  
  /* ══ 30만 푸차 — 명패 각인 (3.0s) ══
     사진은 '파란 대리석 명패 + 금색 글자 + 은빛 액자' 다. 바다가 아니다.
     ⚠️ nuna(70만) 와 같은 액자 계열이라 일부러 반대 성격 — 여기는 차갑게 '파는' 쪽. */
  fx_pucha(fx, shake) {
    const MARB = this.col(0, '#2a9df4'), DEEP = this.col(1, '#0b3a6b'), GOLD = '#e8c46a';
    this.cardGlow(MARB);
    this.photoBg(fx, { delay: 300, dur: 2600, blur: 32, bright: .32, max: .7 });

    const dim = this.mk(fx, 'inset:0;background:rgba(2,8,18,.72);opacity:0;');
    this.a(dim, [{ opacity: 0 }, { opacity: 1, offset: .12 }, { opacity: 1, offset: .84 }, { opacity: 0 }], 3000);

    // ① 빈 파란 대리석 판이 미끄러져 들어온다
    const slab = this.mk(fx, 'left:960px;top:520px;width:1200px;height:420px;transform:translate(-50%,-50%);' +
      'background:linear-gradient(152deg,' + MARB + ',' + DEEP + ' 46%,' + MARB + ' 78%,' + DEEP + ');' +
      'box-shadow:inset 0 0 90px rgba(0,0,0,.5);opacity:0;');
    // 대리석 결 — 흰 실선 몇 줄이 결처럼 지나간다
    for (let i = 0; i < 5; i++) {
      this.mk(slab, 'left:0;right:0;top:' + (40 + i * 78) + 'px;height:' + this.rnd(2, 6).toFixed(0) + 'px;background:rgba(255,255,255,' + this.rnd(.08, .2).toFixed(2) + ');transform:rotate(' + this.rnd(-4, 4).toFixed(1) + 'deg);');
    }
    this.a(slab, [{ transform: 'translate(-50%,-50%) translateX(-1500px)', opacity: 0 }, { transform: 'translate(-50%,-50%) translateX(0px)', opacity: 1, offset: .22 }, { transform: 'translate(-50%,-50%) translateX(0px)', opacity: 1, offset: .84 }, { transform: 'translate(-50%,-50%) translateX(0px)', opacity: 0 }], 2900, 120, 'cubic-bezier(.16,1,.3,1)');

    const FONT = "font-family:'Black Han Sans',sans-serif;font-size:190px;line-height:1;letter-spacing:14px;";

    // ② 글자가 한 획씩 깊게 파인다 — 어두운 홈이 왼→오로 드러난다
    const carve = document.createElement('div');
    carve.textContent = '푸차';
    carve.style.cssText = this.mapCss('position:absolute;inset:0;display:flex;align-items:center;justify-content:center;' + FONT) +
      ';color:rgba(4,22,44,.92);text-shadow:2px 3px 0 rgba(255,255,255,.22);';
    slab.appendChild(carve);
    this.a(carve, [{ clipPath: 'inset(0 100% 0 0)' }, { clipPath: 'inset(0 0 0 0)' }], 640, 700, 'cubic-bezier(.4,0,.4,1)');

    // ③ 파인 홈에 금물이 흘러 들어가 찬다 (각인보다 살짝 늦게)
    const gold = document.createElement('div');
    gold.textContent = '푸차';
    gold.style.cssText = this.mapCss('position:absolute;inset:0;display:flex;align-items:center;justify-content:center;' + FONT) +
      ';background-image:linear-gradient(102deg,#8a6a1c,' + GOLD + ' 34%,#fff3cf 50%,' + GOLD + ' 66%,#8a6a1c);' +
      '-webkit-background-clip:text;background-clip:text;color:transparent;';
    slab.appendChild(gold);
    this.a(gold, [{ clipPath: 'inset(100% 0 0 0)' }, { clipPath: 'inset(0 0 0 0)' }], 760, 1120, 'cubic-bezier(.3,0,.4,1)');

    // ④ 금속 광택이 글자 위를 스윽
    const sweep = this.mk(slab, 'top:-20%;bottom:-20%;left:0;width:260px;background:linear-gradient(90deg,rgba(255,255,255,0),rgba(255,248,220,.5),rgba(255,255,255,0));mix-blend-mode:screen;transform:skewX(-14deg) translateX(-400px);');
    this.a(sweep, [{ transform: 'skewX(-14deg) translateX(-400px)' }, { transform: 'skewX(-14deg) translateX(1400px)' }], 900, 1780, 'cubic-bezier(.42,0,.5,1)');

    // ⑤ 은빛 액자 모서리 네 개가 딱딱 물린다
    [[300, 290, 1, 1], [1620, 290, -1, 1], [300, 750, 1, -1], [1620, 750, -1, -1]].forEach((c, i) => {
      const h = this.mk(fx, 'left:' + c[0] + 'px;top:' + c[1] + 'px;width:180px;height:8px;background:linear-gradient(90deg,#f2f6fa,#8fa3b8);transform-origin:' + (c[2] > 0 ? '0%' : '100%') + ' 50%;transform:scaleX(0);');
      this.a(h, [{ transform: 'scaleX(0)' }, { transform: 'scaleX(' + c[2] + ')' }, { transform: 'scaleX(' + c[2] + ')', opacity: 1, offset: .9 }, { transform: 'scaleX(' + c[2] + ')', opacity: 0 }], 2400, 1500 + i * 90, 'cubic-bezier(.1,.95,.2,1)');
      const v = this.mk(fx, 'left:' + c[0] + 'px;top:' + c[1] + 'px;width:8px;height:130px;background:linear-gradient(180deg,#f2f6fa,#8fa3b8);transform-origin:50% ' + (c[3] > 0 ? '0%' : '100%') + ';transform:scaleY(0);');
      this.a(v, [{ transform: 'scaleY(0)' }, { transform: 'scaleY(' + c[3] + ')' }, { transform: 'scaleY(' + c[3] + ')', opacity: 1, offset: .9 }, { transform: 'scaleY(' + c[3] + ')', opacity: 0 }], 2400, 1540 + i * 90, 'cubic-bezier(.1,.95,.2,1)');
      this.shake(shake, 5, 110, 1500 + i * 90);
    });

    this.cardIn(1950, { from: 'scale(.9)', dur: 480 });
  }

  
  /* ══ 35만 EDM — 산성 파열 (2.6s) ══ */
  fx_edm(fx, shake) {
    const AC = this.col(0, '#59ff6a'), CY = this.col(1, '#22e6ff');
    this.cardGlow(AC);
    this.photoBg(fx, { delay: 100, dur: 2200, blur: 24, bright: .38, max: .8 });
    const dark = this.mk(fx, 'inset:0;background:radial-gradient(110% 80% at 50% 55%,rgba(6,14,8,.24),rgba(2,6,4,.76));opacity:0;');
    this.a(dark, [{ opacity: 0 }, { opacity: 1, offset: .06 }, { opacity: 1, offset: .9 }, { opacity: 0 }], 2400);
    const scan = this.mk(fx, 'inset:0;mix-blend-mode:overlay;opacity:0;background:repeating-linear-gradient(rgba(160,255,180,.13) 0 1px,transparent 1px 4px);');
    this.a(scan, [{ opacity: 0 }, { opacity: 1, offset: .05 }, { opacity: 1, offset: .92 }, { opacity: 0 }], 2400);

    // 균열 8줄
    for (let i = 0; i < 9; i++) {
      const rot = i * 41 + this.rnd(0, 16), len = this.rnd(620, 1180);
      const c = this.mk(fx, 'left:50%;top:50%;width:' + len.toFixed(0) + 'px;height:' + this.rnd(4, 11).toFixed(0) + 'px;background:linear-gradient(90deg,' + AC + ',rgba(89,255,106,0));transform-origin:0% 50%;transform:rotate(' + rot.toFixed(0) + 'deg) scaleX(0);mix-blend-mode:screen;clip-path:polygon(0 40%,14% 0,32% 62%,52% 8%,72% 70%,88% 20%,100% 50%,86% 100%,66% 34%,46% 94%,26% 30%,10% 88%);');
      this.a(c, [{ transform: 'rotate(' + rot.toFixed(0) + 'deg) scaleX(0)', opacity: 1 }, { transform: 'rotate(' + rot.toFixed(0) + 'deg) scaleX(1)', opacity: 1, offset: .18 }, { transform: 'rotate(' + rot.toFixed(0) + 'deg) scaleX(1)', opacity: 1, offset: .7 }, { transform: 'rotate(' + rot.toFixed(0) + 'deg) scaleX(1)', opacity: 0 }], 2200, 120 + i * 60, 'cubic-bezier(.1,.9,.2,1)');
    }
    this.flash(fx, AC, .3, 200, 120);

    // 글리치 바
    for (let i = 0; i < 16; i++) {
      const b = this.mk(fx, 'left:0;right:0;top:' + this.rnd(0, 1040).toFixed(0) + 'px;height:' + this.rnd(5, 34).toFixed(0) + 'px;background:' + (Math.random() > .5 ? AC : CY) + ';mix-blend-mode:screen;opacity:0;');
      const dx = this.rnd(-90, 90) * this.P;
      b.animate([{ opacity: 0, transform: 'translateX(0)' }, { opacity: .5, transform: 'translateX(' + dx.toFixed(0) + 'px)', offset: .3 }, { opacity: .28, transform: 'translateX(' + (-dx * .6).toFixed(0) + 'px)', offset: .7 }, { opacity: 0, transform: 'translateX(0)' }], { duration: 120 / this.S, delay: ([60, 480, 900, 1330][i % 4] + this.rnd(0, 110)) / this.S, easing: 'steps(1,end)', fill: 'forwards' });
    }
    [0, 430, 860, 1290].forEach((ms, i) => {
      this.flash(fx, i % 2 ? CY : AC, .14, 150, 170 + ms);
      fx.animate([{ transform: 'scale(1.014)' }, { transform: 'scale(1)' }], { duration: 130 / this.S, delay: (170 + ms) / this.S, easing: 'cubic-bezier(.2,.9,.3,1)' });
    });
    const vb = this.mk(fx, 'top:0;bottom:0;left:0;width:220px;background:linear-gradient(90deg,rgba(89,255,106,0),rgba(255,255,255,.5),rgba(89,255,106,0));mix-blend-mode:screen;');
    this.a(vb, [{ transform: 'translateX(-260px)' }, { transform: 'translateX(1920px)' }], 560, 900, 'cubic-bezier(.35,0,.4,1)');

    const mkT = (color, blend, z, off) => {
      // ⚠️ opacity:0 이 없으면 delay 120ms 동안 'EDM' 이 그대로 떠 있는다(txt() 와 같은 병).
      const w = this.mk(fx, 'opacity:0;left:0;right:0;top:700px;display:flex;justify-content:center;z-index:' + z + ';' + (blend ? 'mix-blend-mode:screen;' : ''));
      const d = document.createElement('div'); d.textContent = 'EDM';
      d.style.cssText = "font-family:'Anton',sans-serif;font-size:196px;line-height:.9;letter-spacing:.06em;color:" + color + ';';
      w.appendChild(d);
      w.animate([
        { transform: 'translateX(' + off * 4 + 'px) translateY(40px)', opacity: 0 },
        { transform: 'translateX(' + off + 'px)', opacity: 1, offset: .08 },
        { transform: 'translateX(' + off * 2.4 + 'px)', opacity: 1, offset: .19 },
        { transform: 'translateX(' + off + 'px)', opacity: 1, offset: .23 },
        { transform: 'translateX(' + off * -2 + 'px)', opacity: 1, offset: .53 },
        { transform: 'translateX(' + off + 'px)', opacity: 1, offset: .57 },
        { transform: 'translateX(' + off + 'px)', opacity: 1, offset: .93 },
        { transform: 'translateX(' + off + 'px)', opacity: 0 },
      ], { duration: 2400 / this.S, delay: 120 / this.S, easing: 'steps(1,end)', fill: 'forwards' });
    };
    mkT('#ff2bd0', true, 61, -14); mkT(CY, true, 62, 14); mkT('#ffffff', false, 63, 0);
    this.flash(fx, '#ffffff', .85, 70, 2380);

    this.shake(shake, 22, 240, 120);
    this.shake(shake, 9, 140, 600);
    this.shake(shake, 9, 140, 1030);
    this.shake(shake, 20, 260, 1450);
  }

  /* ══ 50만 출항 — 부채 펼침 (3.4s) ══
     사진은 한복·부채·비단이다.
     ⚠️ 살을 그냥 회전시키면 원형 그래프처럼 보인다. 실제 접선부채의 구조를 따른다:
        · 살(rib)은 종이보다 아래로 튀어나오고 축(pivot)에서 한 점으로 모인다
        · 외곽은 직선이 아니라 살마다 둥근 비늘 모양(부채는 원래 그렇다)
        · 종이는 살 사이에서 접혀 있어 골과 마루가 번갈아 진다
        · 축에는 리벳이 있고 종이는 축 근처까지 내려오지 않는다 */
  fx_sail(fx, shake) {
    const GOLD = this.col(0, '#d9b45a'), SILK = this.col(2, '#f2e4c4');
    this.cardGlow(GOLD);
    this.photoBg(fx, { delay: 400, dur: 2800, blur: 30, bright: .36, max: .76 });

    const dim = this.mk(fx, 'inset:0;background:radial-gradient(80% 70% at 50% 70%,rgba(24,14,4,.36),rgba(6,4,2,.88));opacity:0;');
    this.a(dim, [{ opacity: 0 }, { opacity: 1, offset: .16 }, { opacity: 1, offset: .8 }, { opacity: 0 }], 3400);

    const N = 17, SPAN = 62;          // 좌우 62도. 180도로 벌리면 납작해져 촌스럽다.
    const PAPER = 900, RIB = 985;     // 살촉은 85 만 내민다. 더 내밀면 종이와 뼈대가 벌어져 보인다.

    for (let i = 0; i < N; i++) {
      const rot = -SPAN + (i / (N - 1)) * SPAN * 2;
      const openAt = 140 + i * 40, closeAt = 2420 + (N - 1 - i) * 26;
      const fold = i % 2 === 0;       // 골과 마루 — 접힌 종이의 명암

      // ① 살 — 축에서 한 점으로 모이고 종이 밖으로 튀어나온다
      const rib = this.mk(fx, 'left:50%;bottom:70px;width:13px;height:' + RIB + 'px;transform-origin:50% 100%;' +
        'background:linear-gradient(to top,#6b4f12,' + GOLD + ' 22%,#fff0c4 74%,' + GOLD + ');' +
        'border-radius:7px;transform:translateX(-50%) rotate(0deg) scaleY(.06);opacity:0;');

      // ② 종이 한 폭 — 축 쪽은 좁고 끝은 넓다. 끝을 둥글려 비늘 모양을 만든다.
      const leaf = this.mk(fx, 'left:50%;bottom:' + (70 + RIB - PAPER) + 'px;width:258px;height:' + PAPER + 'px;transform-origin:50% 100%;' +
        'clip-path:polygon(46% 100%,54% 100%,100% 10%,90% 0,10% 0,0 10%);' +
        'background:linear-gradient(to top,rgba(140,102,32,' + (fold ? '.95' : '.8') + '),' + SILK + ' 46%,' + (fold ? 'rgba(255,255,255,.92)' : 'rgba(236,214,170,.9)') + ');' +
        'transform:translateX(-50%) rotate(0deg) scaleY(.06);opacity:0;');
      // 접힌 골의 그늘 — 종이가 평면이 아니라 접혀 있다는 신호
      this.mk(leaf, 'left:0;top:0;bottom:0;width:34px;background:linear-gradient(90deg,rgba(90,62,18,.42),transparent);');

      [[rib, 1], [leaf, fold ? .97 : .88]].forEach(v => {
        const el = v[0], op = v[1];
        this.a(el, [
          { transform: 'translateX(-50%) rotate(0deg) scaleY(.06)', opacity: 0 },
          { transform: 'translateX(-50%) rotate(' + (rot * 1.05).toFixed(1) + 'deg) scaleY(1)', opacity: op, offset: .78 },
          { transform: 'translateX(-50%) rotate(' + rot.toFixed(1) + 'deg) scaleY(1)', opacity: op },
        ], 560, openAt, 'cubic-bezier(.16,1,.3,1)');
        // 다 펼쳐진 뒤 아주 약하게 숨쉰다. 완전히 굳어 있으면 종이로 안 보인다.
        try {
          el.animate([{ transform: 'rotate(-1.2deg)' }, { transform: 'rotate(1.2deg)' }],
            { duration: 900 / this.S, delay: 1500 / this.S, iterations: 2, direction: 'alternate',
              easing: 'ease-in-out', composite: 'add' });
        } catch (e) {}
        this.a(el, [
          { transform: 'translateX(-50%) rotate(' + rot.toFixed(1) + 'deg) scaleY(1)', opacity: op },
          { transform: 'translateX(-50%) rotate(0deg) scaleY(.06)', opacity: 0 },
        ], 440, closeAt, 'cubic-bezier(.55,0,.4,1)');
      });
    }

    // ③ 축 리벳 — 여기가 없으면 부채가 아니라 부챗살 다발이다
    const hub = this.mk(fx, 'left:50%;bottom:34px;width:78px;height:78px;border-radius:50%;transform:translateX(-50%) scale(0);' +
      'background:radial-gradient(60% 60% at 38% 32%,#fff3cf,' + GOLD + ' 46%,#6b4f12);box-shadow:0 0 26px rgba(217,180,90,.8);');
    this.a(hub, [{ transform: 'translateX(-50%) scale(0)', opacity: 0 }, { transform: 'translateX(-50%) scale(1)', opacity: 1, offset: .1 }, { transform: 'translateX(-50%) scale(1)', opacity: 1, offset: .86 }, { transform: 'translateX(-50%) scale(.2)', opacity: 0 }], 3200, 140, 'cubic-bezier(.16,1,.3,1)');

    // ④ 비단 광택이 부채 면을 축 기준으로 훑고 지나간다
    const sheen = this.mk(fx, 'left:50%;bottom:70px;width:2600px;height:2600px;transform-origin:50% 100%;transform:translateX(-50%) rotate(-70deg);' +
      'background:conic-gradient(from 176deg at 50% 100%, transparent 0deg, rgba(255,248,220,.34) 5deg, transparent 11deg);mix-blend-mode:screen;opacity:0;');
    this.a(sheen, [
      { transform: 'translateX(-50%) rotate(-70deg)', opacity: 0 },
      { transform: 'translateX(-50%) rotate(-70deg)', opacity: 1, offset: .1 },
      { transform: 'translateX(-50%) rotate(70deg)', opacity: 1, offset: .9 },
      { transform: 'translateX(-50%) rotate(70deg)', opacity: 0 },
    ], 1300, 1180, 'cubic-bezier(.42,0,.5,1)');

    // ⑤ 금분 — 부채가 일으킨 바람
    for (let i = 0; i < 26; i++) {
      const sz = this.rnd(3, 7);
      const p = this.mk(fx, 'left:' + this.rnd(0, 1920).toFixed(0) + 'px;bottom:0;width:' + sz.toFixed(1) + 'px;height:' + sz.toFixed(1) + 'px;border-radius:50%;background:#f4e3ae;');
      this.a(p, [{ transform: 'translateY(0)', opacity: 0 }, { opacity: .7, offset: .2 }, { transform: 'translateY(-' + this.rnd(500, 1000).toFixed(0) + 'px) translateX(' + this.rnd(-140, 140).toFixed(0) + 'px)', opacity: 0 }], this.rnd(2000, 2900), this.rnd(200, 1400), 'cubic-bezier(.4,0,.6,1)');
    }

    this.shake(shake, 7, 180, 140);
    this.cardIn(1500, { from: 'scale(.88)', dur: 520 });
  }

  
  /* ══ 500,001 50만 방패 — 방패 강림 (3.2s) ══
     착탄 프레임 IMP=260. 원본은 820 이었고 낙하에만 620ms 를 썼다.
     ① 움츠림 0–140 → ② 급강하 140–260 → ③ 착탄 260–320(정지) → ④ 반동 → ⑤ 이차운동 */
  fx_shield(fx, shake) {
    const BOLT = this.col(0, '#ff5fa2');
    const IMP = 260;
    this.cardGlow(BOLT);
    this.photoBg(fx, { delay: 620, dur: 2400, blur: 26, bright: .4, max: .82 });

    /* ① 움츠림 0–140 — 화면이 급히 내려앉는다 (원본은 512ms 에 걸쳐 천천히) */
    const dim = this.mk(fx, 'inset:0;background:rgba(4,4,10,.6);opacity:0;');
    this.a(dim, [{ opacity: 0 }, { opacity: 1 }], 110, 0, 'cubic-bezier(.5,0,.9,.5)');
    this.a(dim, [{ opacity: 1 }, { opacity: 1, offset: .82 }, { opacity: 0 }], 3000, 110);

    /* ② 급강하 140–260 — 120ms. 끝까지 가속(원본은 착지 전에 감속했다).
       ⚠️ style 의 opacity:0 이 delay 동안 방패를 숨긴다. 첫 프레임에서 1 로 나타난다. */
    const sh = this.mk(fx, 'left:50%;top:470px;width:440px;height:540px;transform:translate(-50%,-50%) translateY(-1200px);clip-path:polygon(50% 0,100% 14%,100% 58%,50% 100%,0 58%,0 14%);background:linear-gradient(150deg,#eef3fa,#9fb0c6 38%,#5c6b80 62%,#c9d6e6);box-shadow:0 0 0 6px rgba(255,95,162,.5);opacity:0;');
    const emb = document.createElement('div');
    emb.style.cssText = 'position:absolute;left:50%;top:44%;width:2px;height:250px;transform:translate(-50%,-50%);background:rgba(60,74,92,.55);';
    sh.appendChild(emb);
    this.a(sh, [{ transform: 'translate(-50%,-50%) translateY(-1200px) scale(.82,1.45)', opacity: 1 },
                { transform: 'translate(-50%,-50%) translateY(-40px) scale(.9,1.28)',    opacity: 1 }],
           120, 140, 'cubic-bezier(.7,0,.95,.5)');

    /* ③ 착탄 260–320 — 히트스톱 60ms, 납작하게 눌린 채 정지 */
    this.hold(sh, 'translate(-50%,-50%) translateY(0) scale(1.3,.72)', 60, IMP);

    /* ④ 반동 320–700 */
    this.a(sh, [{ transform: 'translate(-50%,-50%) translateY(0) scale(1.3,.72)' },
                { transform: 'translate(-50%,-50%) translateY(-12px) scale(.94,1.08)', offset: .42 },
                { transform: 'translate(-50%,-50%) translateY(0) scale(1.03,.97)',     offset: .72 },
                { transform: 'translate(-50%,-50%) translateY(0) scale(1,1)' }],
           380, IMP + 60, 'cubic-bezier(.2,.85,.3,1)');

    /* ⑤ 서 있다 퇴장 */
    this.a(sh, [{ transform: 'translate(-50%,-50%) translateY(0) scale(1,1)',        opacity: 1 },
                { transform: 'translate(-50%,-50%) translateY(0) scale(1,1)',        opacity: 1, offset: .86 },
                { transform: 'translate(-50%,-50%) translateY(-40px) scale(1.04,1)', opacity: 0 }],
           2300, IMP + 440, 'cubic-bezier(.4,0,.3,1)');

    this.flash(fx, '#ffffff', 1, 30, IMP);                       // 원본 110ms → 30ms

    /* 충격파 링 — 같은 재료, 착탄에 모은다 (원본 간격 0/90/190 → 0/70/150) */
    [0, 70, 150].forEach((d, i) => {
      const ring = this.mk(fx, 'left:50%;top:470px;width:360px;height:360px;border-radius:50%;border:' + (14 - i * 4) + 'px solid rgba(255,95,162,' + (.85 - i * .2) + ');transform:translate(-50%,-50%) scale(.15);');
      this.a(ring, [{ transform: 'translate(-50%,-50%) scale(.15)', opacity: 1 },
                    { transform: 'translate(-50%,-50%) scale(' + (5.2 + i) + ')', opacity: 0 }],
             780 + i * 110, IMP + d, 'cubic-bezier(.12,.92,.28,1)');
    });

    /* 번개 7개 — 원본은 45ms 간격으로 흩어졌다. 22ms 로 좁혀 한 방으로 만든다. */
    for (let i = 0; i < 7; i++) {
      const rot = -100 + i * 33 + this.rnd(-8, 8);
      const b = this.mk(fx, 'left:50%;top:470px;width:26px;height:' + this.rnd(420, 780).toFixed(0) + 'px;background:linear-gradient(to bottom,' + BOLT + ',rgba(255,95,162,0));transform-origin:50% 0%;transform:rotate(' + rot.toFixed(0) + 'deg) scaleY(0);clip-path:polygon(50% 0,100% 22%,32% 42%,100% 62%,20% 100%,64% 52%,0 34%);mix-blend-mode:screen;');
      this.a(b, [{ transform: 'rotate(' + rot.toFixed(0) + 'deg) scaleY(0)', opacity: 1 },
                 { transform: 'rotate(' + rot.toFixed(0) + 'deg) scaleY(1)', opacity: 1, offset: .28 },
                 { transform: 'rotate(' + rot.toFixed(0) + 'deg) scaleY(1)', opacity: 0 }],
             500, IMP + 20 + i * 22, 'cubic-bezier(.08,.92,.2,1)');
    }

    this.shake(shake, 58, 420, IMP);
    this.shake(shake, 14, 220, IMP + 430);

    /* 글자는 본체가 멈춘 뒤에 '찍힌다' (이차운동) */
    const t = this.txt(fx, '방패', "font-family:'Black Han Sans',sans-serif;font-size:104px;color:#ffd9e8;letter-spacing:.3em;", 830);
    this.a(t.w, [{ transform: 'translateY(26px) scale(.62,1.25)', opacity: 0 },
                 { transform: 'translateY(-6px) scale(1.12,.92)', opacity: 1, offset: .5 },
                 { transform: 'translateY(0) scale(.98,1.02)',    opacity: 1, offset: .78 },
                 { transform: 'translateY(0) scale(1,1)',         opacity: 1 }],
           330, IMP + 200, 'cubic-bezier(.2,.9,.3,1)');
    this.a(t.w, [{ transform: 'translateY(0) scale(1,1)',     opacity: 1 },
                 { transform: 'translateY(0) scale(1,1)',     opacity: 1, offset: .82 },
                 { transform: 'translateY(-20px) scale(1,1)', opacity: 0 }],
           1900, IMP + 530, 'cubic-bezier(.4,0,.3,1)');
  }

  /* ══ 600,001 74번 알림 — 참격 (2.6s) ══ */
  fx_slash(fx, shake) {
    const BLADE = this.col(0, '#e63946');
    this.cardGlow(BLADE);
    this.photoBg(fx, { delay: 220, dur: 2200, blur: 24, bright: .36, max: .8 });
    const dim = this.mk(fx, 'inset:0;background:rgba(2,2,6,.42);opacity:0;');
    this.a(dim, [{ opacity: 0 }, { opacity: 1, offset: .1 }, { opacity: 1, offset: .84 }, { opacity: 0 }], 2600);

    [[32, 220], [-32, 760]].forEach((v, i) => {
      const rot = v[0], ms = v[1];
      const sl = this.mk(fx, 'left:50%;top:50%;width:2900px;height:16px;background:linear-gradient(90deg,rgba(255,255,255,0),#fff 12%,#fff 88%,rgba(255,255,255,0));transform:translate(-50%,-50%) rotate(' + rot + 'deg) scaleX(0);transform-origin:50% 50%;');
      this.a(sl, [{ transform: 'translate(-50%,-50%) rotate(' + rot + 'deg) scaleX(0)', opacity: 1 }, { transform: 'translate(-50%,-50%) rotate(' + rot + 'deg) scaleX(1)', opacity: 1, offset: .1 }, { transform: 'translate(-50%,-50%) rotate(' + rot + 'deg) scaleX(1) scaleY(.2)', opacity: .9, offset: .3 }, { transform: 'translate(-50%,-50%) rotate(' + rot + 'deg) scaleX(1) scaleY(.05)', opacity: 0 }], 900, ms, 'cubic-bezier(.05,.9,.2,1)');
      const red = this.mk(fx, 'left:50%;top:50%;width:2900px;height:5px;background:' + BLADE + ';transform:translate(-50%,-50%) rotate(' + rot + 'deg) translateY(20px) scaleX(0);');
      this.a(red, [{ transform: 'translate(-50%,-50%) rotate(' + rot + 'deg) translateY(22px) scaleX(0)', opacity: 1 }, { transform: 'translate(-50%,-50%) rotate(' + rot + 'deg) translateY(22px) scaleX(1)', opacity: 1, offset: .12 }, { transform: 'translate(-50%,-50%) rotate(' + rot + 'deg) translateY(22px) scaleX(1)', opacity: 1, offset: .6 }, { transform: 'translate(-50%,-50%) rotate(' + rot + 'deg) translateY(22px) scaleX(1)', opacity: 0 }], 1400, ms + 40, 'cubic-bezier(.05,.9,.2,1)');
      this.flash(fx, '#ffffff', .82, 90, ms + 30);
      this.shake(shake, 30, 300, ms + 20);
    });

    // 갈라짐 (X자 검은 틈)
    [32, -32].forEach((rot, i) => {
      const gap = this.mk(fx, 'left:50%;top:50%;width:2900px;height:0;background:#05050a;transform:translate(-50%,-50%) rotate(' + rot + 'deg);box-shadow:0 0 0 2px rgba(230,57,70,.6);opacity:0;');
      this.a(gap, [{ height: '0px', opacity: 0 }, { height: '26px', opacity: 1, offset: .18 }, { height: '26px', opacity: 1, offset: .66 }, { height: '0px', opacity: 0 }], 1500, 1080 + i * 90, 'cubic-bezier(.16,1,.3,1)');
    });
    const t = this.txt(fx, '참격', "font-family:'Black Han Sans',sans-serif;font-size:150px;color:#fff;letter-spacing:.3em;", 800);
    this.a(t.w, [{ transform: 'scale(1.3)', opacity: 0 }, { transform: 'scale(1)', opacity: 1, offset: .12 }, { transform: 'scale(1)', opacity: 1, offset: .74 }, { transform: 'scale(1.03)', opacity: 0 }], 1400, 1120, 'cubic-bezier(.16,1,.3,1)');
  }

  /* ══ 70만 누나누나 — 장미 개화 (3.2s) ══
     사진은 '분홍 대리석 + 로즈골드 액자 + 분홍 보석' 이다.
     ⚠️ pucha(30만) 와 같은 액자 계열이라 반대 성격 — 여기는 따뜻하게 '피는' 쪽. */
  fx_nuna(fx, shake) {
    const ROSE = this.col(0, '#ff7fa8'), GOLD = this.col(2, '#e8b978');
    this.cardGlow(ROSE);
    this.photoBg(fx, { delay: 200, dur: 2900, blur: 28, bright: .42, max: .82 });

    const wash = this.mk(fx, 'inset:0;background:radial-gradient(70% 60% at 50% 48%,rgba(255,140,175,.28),rgba(46,10,24,.76));opacity:0;');
    this.a(wash, [{ opacity: 0 }, { opacity: 1, offset: .14 }, { opacity: 1, offset: .82 }, { opacity: 0 }], 3200);

    // ① 분홍 대리석 결이 가운데서 물결처럼 퍼져 나간다
    for (let i = 0; i < 5; i++) {
      const r = this.mk(fx, 'left:960px;top:540px;width:520px;height:520px;border-radius:50%;transform:translate(-50%,-50%) scale(.2);' +
        'border:5px solid rgba(255,190,210,' + (.5 - i * .07).toFixed(2) + ');mix-blend-mode:screen;');
      this.a(r, [{ transform: 'translate(-50%,-50%) scale(.2)', opacity: .9 }, { transform: 'translate(-50%,-50%) scale(3.4)', opacity: 0 }], 1700, 300 + i * 230, 'cubic-bezier(.2,.85,.3,1)');
    }

    // ② 꽃잎이 회오리로 몰려와 화면 테두리에 붙어 액자가 된다.
    //    ⚠️ 목표 지점을 테두리 위로 잡아야 '액자' 로 읽힌다. 흩날리면 그냥 파티클이다.
    for (let i = 0; i < 44; i++) {
      const edge = i % 4, sz = this.rnd(26, 58);
      let tx, ty;
      if (edge === 0) { tx = this.rnd(-880, 880); ty = -470; }
      else if (edge === 1) { tx = this.rnd(-880, 880); ty = 470; }
      else if (edge === 2) { tx = -890; ty = this.rnd(-440, 440); }
      else { tx = 890; ty = this.rnd(-440, 440); }
      const p = this.mk(fx, 'left:960px;top:540px;width:' + sz.toFixed(0) + 'px;height:' + (sz * .66).toFixed(0) + 'px;' +
        'border-radius:100% 0 100% 0;background:linear-gradient(120deg,' + ROSE + ',' + GOLD + ');transform:translate(-50%,-50%) scale(.2);opacity:0;');
      this.a(p, [
        { transform: 'translate(-50%,-50%) translate(0px,0px) rotate(0deg) scale(.2)', opacity: 0 },
        { opacity: 1, offset: .18 },
        { transform: 'translate(-50%,-50%) translate(' + (tx * .55).toFixed(0) + 'px,' + (ty * .55).toFixed(0) + 'px) rotate(' + this.rnd(90, 220).toFixed(0) + 'deg) scale(1)', opacity: 1, offset: .5 },
        { transform: 'translate(-50%,-50%) translate(' + tx.toFixed(0) + 'px,' + ty.toFixed(0) + 'px) rotate(' + this.rnd(240, 400).toFixed(0) + 'deg) scale(1)', opacity: 1, offset: .74 },
        { transform: 'translate(-50%,-50%) translate(' + tx.toFixed(0) + 'px,' + ty.toFixed(0) + 'px) rotate(' + this.rnd(240, 400).toFixed(0) + 'deg) scale(1)', opacity: 0, offset: 1 },
      ], 3000, 180 + i * 26, 'cubic-bezier(.2,.8,.25,1)');
    }

    // ③ 보석이 순서대로 반짝
    [[430, 320], [1500, 300], [960, 830], [1660, 720], [300, 760], [1200, 240]].forEach((p, i) => {
      const g1 = this.mk(fx, 'left:' + p[0] + 'px;top:' + p[1] + 'px;width:4px;height:74px;background:#fff;box-shadow:0 0 20px ' + ROSE + ';');
      const g2 = this.mk(fx, 'left:' + p[0] + 'px;top:' + p[1] + 'px;width:74px;height:4px;background:#fff;box-shadow:0 0 20px ' + ROSE + ';');
      [g1, g2].forEach(e => this.a(e, [{ transform: 'translate(-50%,-50%) scale(0) rotate(0deg)', opacity: 0 }, { transform: 'translate(-50%,-50%) scale(1) rotate(45deg)', opacity: 1, offset: .35 }, { transform: 'translate(-50%,-50%) scale(0) rotate(90deg)', opacity: 0 }], 760, 900 + i * 250, 'cubic-bezier(.3,0,.4,1)'));
    });

    this.cardIn(1500, { from: 'scale(.86)', dur: 540 });
  }

  
  /* ══ 80만 클럽음악 — 드롭 (3.4s) ══
     ⚠️ 이 연출의 전부는 1.2~1.4초의 '멈춤' 이다. 계속 화려하게 채우면 밋밋해진다.
        빌드업(0~1.2) → 정적(1.2~1.4) → 드롭(1.4~). 이 구조를 흐리지 마라. */
  fx_club(fx, shake) {
    const PINK = this.col(0, '#ff2bd0'), CYAN = this.col(1, '#22e6ff'), GOLD = this.col(2, '#ffd24a');
    this.cardGlow(PINK);
    this.photoBg(fx, { delay: 1400, dur: 1900, blur: 26, bright: .42, max: .85, from: 1.3, to: 1.1 });

    const DROP = 1400;

    const dark = this.mk(fx, 'inset:0;background:rgba(3,2,10,.68);opacity:0;');
    this.a(dark, [{ opacity: 0 }, { opacity: 1, offset: .06 }, { opacity: 1, offset: .86 }, { opacity: 0 }], 3400);

    /* ── 빌드업 (0~1.2s) — 밝아지고, 떨림이 빨라지고, 레이저가 한 점으로 모인다 ── */
    const rise = this.mk(fx, 'inset:0;background:#ffffff;mix-blend-mode:screen;opacity:0;');
    this.a(rise, [{ opacity: 0 }, { opacity: .1, offset: .5 }, { opacity: .42, offset: .86 }, { opacity: .72, offset: 1 }], DROP, 0, 'cubic-bezier(.6,0,.9,1)');

    for (let i = 0; i < 8; i++) {
      const c = [PINK, CYAN, GOLD][i % 3], spread = (i - 3.5) * 15;
      const l = this.mk(fx, 'left:960px;top:-60px;width:190px;height:1500px;transform-origin:50% 0%;' +
        'clip-path:polygon(46% 0,54% 0,100% 100%,0 100%);background:linear-gradient(to bottom,' + c + ',rgba(0,0,0,0));mix-blend-mode:screen;opacity:0;');
      // 벌어져 있다가 위 한 점으로 모인다 = 터지기 직전의 긴장
      this.a(l, [
        { transform: 'translateX(-50%) rotate(' + spread + 'deg)', opacity: 0 },
        { transform: 'translateX(-50%) rotate(' + spread + 'deg)', opacity: .7, offset: .12 },
        { transform: 'translateX(-50%) rotate(' + (spread * .12).toFixed(1) + 'deg)', opacity: .95, offset: 1 },
      ], DROP, i * 30, 'cubic-bezier(.5,0,.6,1)');
      // 드롭 순간 사방으로 터진다
      this.a(l, [
        { transform: 'translateX(-50%) rotate(' + (spread * .12).toFixed(1) + 'deg)', opacity: .95 },
        { transform: 'translateX(-50%) rotate(' + (spread * 3.2).toFixed(1) + 'deg)', opacity: .85, offset: .3 },
        { transform: 'translateX(-50%) rotate(' + (spread * 2.6).toFixed(1) + 'deg)', opacity: .8, offset: .84 },
        { transform: 'translateX(-50%) rotate(' + (spread * 3).toFixed(1) + 'deg)', opacity: 0 },
      ], 1900, DROP, 'cubic-bezier(.1,.9,.3,1)');
    }
    // 저음 진동 — 간격이 점점 좁아진다
    [0, 300, 540, 730, 880, 1000, 1090, 1160, 1215].forEach((ms, i) => this.shake(shake, 5 + i * 1.5, 120, ms));

    /* ── 정적 (1.2~1.4s) — 아무 것도 움직이지 않는다 ── */
    const hold = this.mk(fx, 'inset:0;background:#ffffff;opacity:0;');
    this.a(hold, [{ opacity: 0, offset: 0 }, { opacity: .78, offset: .02 }, { opacity: .78, offset: .98 }, { opacity: 0, offset: 1 }], 200, 1200, 'steps(1,end)');

    /* ── 드롭 (1.4s~) ── */
    this.flash(fx, '#ffffff', 1, 90, DROP);
    this.shake(shake, 44, 480, DROP);

    // 좌우 스피커 충격파
    [[250, -1], [1670, 1]].forEach(sp => {
      for (let k = 0; k < 3; k++) {
        const r = this.mk(fx, 'left:' + sp[0] + 'px;top:540px;width:340px;height:340px;border-radius:50%;' +
          'border:' + (16 - k * 4) + 'px solid ' + (k % 2 ? CYAN : PINK) + ';transform:translate(-50%,-50%) scale(.1);mix-blend-mode:screen;');
        this.a(r, [{ transform: 'translate(-50%,-50%) scale(.1)', opacity: 1 }, { transform: 'translate(-50%,-50%) scale(' + (4.4 + k) + ')', opacity: 0 }], 820 + k * 120, DROP + k * 90, 'cubic-bezier(.15,.9,.3,1)');
      }
    });

    // 색종이
    for (let i = 0; i < 46; i++) {
      const w = this.rnd(14, 30), c = [PINK, CYAN, GOLD, '#ffffff'][i % 4];
      const p = this.mk(fx, 'left:' + this.rnd(0, 1920).toFixed(0) + 'px;top:-60px;width:' + w.toFixed(0) + 'px;height:' + (w * .6).toFixed(0) + 'px;background:' + c + ';');
      this.a(p, [{ transform: 'translateY(0) rotate(0deg)', opacity: 0 }, { opacity: 1, offset: .08 }, { transform: 'translateY(1250px) translateX(' + this.rnd(-260, 260).toFixed(0) + 'px) rotate(' + this.rnd(-720, 720).toFixed(0) + 'deg)', opacity: 0 }], this.rnd(1300, 1900), DROP + this.rnd(0, 700), 'cubic-bezier(.35,0,.6,1)');
    }

    // 비트마다 부풀었다 줄었다
    [0, 430, 860, 1290, 1720].forEach((ms, i) => {
      this.a(fx, [{ transform: 'scale(1.03)' }, { transform: 'scale(1)' }], 170, DROP + ms, 'cubic-bezier(.2,.9,.3,1)');
      if (i) this.shake(shake, 12, 150, DROP + ms);
      this.flash(fx, i % 2 ? CYAN : PINK, .16, 150, DROP + ms);
    });

    // 카드는 드롭 순간에 박힌다 — 정적의 대가가 이거다.
    this.cardIn(DROP, { from: 'scale(1.4)', dur: 380, ease: 'cubic-bezier(.08,.95,.2,1)' });
  }

  
  /* ══ 100만 VIP (4.6s) ══ */
  fx_vip(fx) {
    const GOLD = this.col(2, '#c9a227');
    this.cardGlow(GOLD);
    this.photoBg(fx, { delay: 260, dur: 4100, blur: 32, bright: .34, max: .68, hold: .84 });
    const vig = this.mk(fx, 'inset:0;background:radial-gradient(100% 78% at 50% 48%,rgba(4,4,6,.34),rgba(2,2,4,.92));opacity:0;');
    this.a(vig, [{ opacity: 0 }, { opacity: 1, offset: .2 }, { opacity: 1, offset: .84 }, { opacity: 0 }], 4500, 0, 'cubic-bezier(.4,0,.3,1)');

    [400, 800].forEach((y, i) => {
      const h = this.mk(fx, 'left:50%;top:' + y + 'px;width:1120px;height:1px;background:linear-gradient(90deg,rgba(201,162,39,0),' + GOLD + ' 22%,#f2dfa6 50%,' + GOLD + ' 78%,rgba(201,162,39,0));transform:translateX(-50%) scaleX(0);');
      this.a(h, [{ transform: 'translateX(-50%) scaleX(0)', opacity: 0 }, { transform: 'translateX(-50%) scaleX(1)', opacity: 1, offset: .3 }, { transform: 'translateX(-50%) scaleX(1)', opacity: 1, offset: .84 }, { transform: 'translateX(-50%) scaleX(.1)', opacity: 0 }], 4400, 240 + i * 120, 'cubic-bezier(.16,1,.3,1)');
    });

    const panel = this.mk(fx, 'left:50%;top:690px;width:760px;height:150px;transform:translate(-50%,-50%);opacity:0;background:rgba(255,255,255,.045);border:1px solid rgba(201,162,39,.34);backdrop-filter:blur(7px) saturate(1.15);-webkit-backdrop-filter:blur(7px) saturate(1.15);');
    const sub = document.createElement('div');
    sub.textContent = '시그니처 · 1,000,000원';
    sub.style.cssText = "position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-family:'IBM Plex Sans KR',sans-serif;font-size:34px;letter-spacing:.34em;color:rgba(240,232,212,.88);";
    panel.appendChild(sub);
    this.a(panel, [{ opacity: 0, transform: 'translate(-50%,-50%) translateY(38px)' }, { opacity: 1, transform: 'translate(-50%,-50%) translateY(0)', offset: .26 }, { opacity: 1, transform: 'translate(-50%,-50%) translateY(0)', offset: .82 }, { opacity: 0, transform: 'translate(-50%,-50%) translateY(-14px)' }], 4200, 520, 'cubic-bezier(.16,1,.3,1)');

    const w = this.mk(fx, 'left:0;right:0;top:440px;display:flex;justify-content:center;');
    const tx = document.createElement('div');
    tx.textContent = 'VIP';
    // ⚠️ opacity:0 이 없으면 delay 280ms 동안 'VIP' 가 그대로 떠 있는다(txt() 와 같은 병).
    tx.style.cssText = "opacity:0;font-family:'Cormorant Garamond',serif;font-weight:300;font-size:230px;line-height:1;background-image:linear-gradient(102deg,#7d6218 0%,#c9a227 28%,#f7ecc4 47%,#ffffff 50%,#f7ecc4 53%,#c9a227 72%,#7d6218 100%);background-size:320% 100%;background-position:-40% 0;-webkit-background-clip:text;background-clip:text;color:transparent;";
    w.appendChild(tx);
    this.a(tx, [{ letterSpacing: '.62em', opacity: 0 }, { letterSpacing: '.34em', opacity: 1, offset: .34 }, { letterSpacing: '.3em', opacity: 1, offset: .82 }, { letterSpacing: '.3em', opacity: 0 }], 4300, 280, 'cubic-bezier(.16,1,.3,1)');
    this.a(tx, [{ backgroundPosition: '-60% 0' }, { backgroundPosition: '170% 0' }], 2100, 900, 'cubic-bezier(.5,0,.4,1)');

    for (let i = 0; i < 26; i++) {
      const s = this.rnd(2, 4.6);
      const p = this.mk(fx, 'left:' + this.rnd(0, 1900).toFixed(0) + 'px;top:1100px;width:' + s.toFixed(1) + 'px;height:' + s.toFixed(1) + 'px;border-radius:50%;background:#f0dda4;');
      this.a(p, [{ transform: 'translateY(0)', opacity: 0 }, { opacity: .55, offset: .18 }, { transform: 'translateY(-' + this.rnd(700, 1200).toFixed(0) + 'px) translateX(' + this.rnd(-120, 120).toFixed(0) + 'px)', opacity: 0 }], this.rnd(3200, 5000), this.rnd(0, 2200), 'cubic-bezier(.4,0,.6,1)');
    }
    const sweep = this.mk(fx, 'top:-20%;bottom:-20%;left:0;width:300px;background:linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.09),rgba(255,255,255,0));mix-blend-mode:screen;');
    this.a(sweep, [{ transform: 'skewX(-14deg) translateX(-420px)' }, { transform: 'skewX(-14deg) translateX(2100px)' }], 1700, 1500, 'cubic-bezier(.42,0,.5,1)');
  }

  /* ══ 200만 엔젤 VIP — 천상 강림 (5.2s) ══ */
  fx_angel(fx) {
    this.cardGlow(this.col(2, '#ffecb4'));
    this.photoBg(fx, { delay: 300, dur: 4700, blur: 34, bright: .38, max: .72, hold: .84 });
    const holy = this.mk(fx, 'inset:0;background:radial-gradient(70% 90% at 50% 0%,rgba(255,240,200,.5),rgba(20,16,8,.62) 66%);opacity:0;');
    this.a(holy, [{ opacity: 0 }, { opacity: 1, offset: .2 }, { opacity: 1, offset: .84 }, { opacity: 0 }], 5200, 0, 'cubic-bezier(.4,0,.3,1)');

    const rays = this.mk(fx, 'left:50%;top:-700px;width:2400px;height:2400px;transform:translateX(-50%);mix-blend-mode:screen;opacity:0;background:conic-gradient(from 0deg,rgba(255,240,200,.16) 0 3deg,transparent 3deg 14deg);');
    this.a(rays, [{ opacity: 0, transform: 'translateX(-50%) rotate(0deg)' }, { opacity: 1, offset: .24 }, { opacity: 1, offset: .82 }, { opacity: 0, transform: 'translateX(-50%) rotate(24deg)' }], 5200, 200);

    [420, 960, 1500].forEach((x, i) => {
      const p = this.mk(fx, 'left:' + x + 'px;top:0;width:280px;height:1100px;transform:translateX(-50%) scaleY(0);transform-origin:50% 0%;background:linear-gradient(to bottom,rgba(255,246,214,.7),rgba(255,246,214,0));mix-blend-mode:screen;clip-path:polygon(38% 0,62% 0,100% 100%,0 100%);');
      this.a(p, [{ transform: 'translateX(-50%) scaleY(0)', opacity: 0 }, { transform: 'translateX(-50%) scaleY(1)', opacity: 1, offset: .22 }, { transform: 'translateX(-50%) scaleY(1)', opacity: 1, offset: .8 }, { transform: 'translateX(-50%) scaleY(1)', opacity: 0 }], 5000, 200 + i * 320, 'cubic-bezier(.16,1,.3,1)');
    });

    // 날개 (양쪽 깃 7장씩)
    [[720, 1], [1200, -1]].forEach((side, si) => {
      for (let i = 0; i < 7; i++) {
        const len = 320 + i * 44, rot = -8 - i * 15;
        const f = this.mk(fx, 'left:' + side[0] + 'px;top:480px;width:' + len + 'px;height:' + (54 + i * 5) + 'px;background:linear-gradient(90deg,rgba(255,252,240,.9),rgba(255,246,214,.15));border-radius:100% 0 100% 0;transform-origin:0% 100%;transform:scaleX(' + side[1] + ') rotate(0deg) scale(.2);opacity:0;');
        this.a(f, [{ transform: 'scaleX(' + side[1] + ') rotate(0deg) scale(.25)', opacity: 0 }, { transform: 'scaleX(' + side[1] + ') rotate(' + rot + 'deg) scale(1)', opacity: .9, offset: .3 }, { transform: 'scaleX(' + side[1] + ') rotate(' + (rot - 3) + 'deg) scale(1)', opacity: .9, offset: .8 }, { transform: 'scaleX(' + side[1] + ') rotate(' + (rot - 6) + 'deg) scale(1.05)', opacity: 0 }], 4400, 900 + si * 120 + i * 90, 'cubic-bezier(.16,1,.3,1)');
      }
    });

    const halo = this.mk(fx, 'left:50%;top:330px;width:420px;height:120px;border-radius:50%;border:8px solid rgba(255,236,180,.9);transform:translate(-50%,-50%) scale(.3);opacity:0;mix-blend-mode:screen;');
    this.a(halo, [{ transform: 'translate(-50%,-50%) scale(.3)', opacity: 0 }, { transform: 'translate(-50%,-50%) scale(1)', opacity: 1, offset: .2 }, { transform: 'translate(-50%,-50%) scale(1)', opacity: 1, offset: .8 }, { transform: 'translate(-50%,-50%) scale(1.1)', opacity: 0 }], 4200, 700, 'cubic-bezier(.16,1,.3,1)');

    for (let i = 0; i < 18; i++) {
      const s = this.rnd(20, 44);
      const f = this.mk(fx, 'left:' + this.rnd(0, 1880).toFixed(0) + 'px;top:-60px;width:' + s.toFixed(0) + 'px;height:' + (s * .5).toFixed(0) + 'px;border-radius:100% 0 100% 0;background:rgba(255,250,235,.9);');
      this.a(f, [{ transform: 'translateY(0) rotate(0)', opacity: 0 }, { opacity: .85, offset: .12 }, { transform: 'translateY(1200px) translateX(' + this.rnd(-260, 260).toFixed(0) + 'px) rotate(' + this.rnd(-300, 300).toFixed(0) + 'deg)', opacity: 0 }], this.rnd(3200, 4600), this.rnd(300, 2000), 'cubic-bezier(.4,0,.6,1)');
    }
    const t = this.txt(fx, 'ANGEL VIP', "font-family:'Cormorant Garamond',serif;font-weight:300;font-size:132px;color:#fff8e4;", 820);
    // 이 연출도 안쪽 글자만 움직인다. 래퍼는 글자가 시작하는 시각에 켜준다.
    this.a(t.w, [{ opacity: 1 }, { opacity: 1 }], 1, 1400);
    this.a(t.d, [{ letterSpacing: '.6em', opacity: 0 }, { letterSpacing: '.32em', opacity: 1, offset: .32 }, { letterSpacing: '.3em', opacity: 1, offset: .82 }, { letterSpacing: '.3em', opacity: 0 }], 4600, 1400, 'cubic-bezier(.16,1,.3,1)');
  }

  /* ══ 300만 MVP — 대관식 (7.5s) ══ */
  fx_mvp(fx, shake) {
    this.cardGlow(this.col(2, '#d9b45a'));
    this.photoBg(fx, { delay: 400, dur: 6800, blur: 34, bright: .34, max: .66, hold: .86 });
    const vig = this.mk(fx, 'inset:0;background:radial-gradient(100% 80% at 50% 46%,rgba(40,26,4,.2),rgba(2,2,4,.86));opacity:0;');
    this.a(vig, [{ opacity: 0 }, { opacity: 1, offset: .1 }, { opacity: 1, offset: .9 }, { opacity: 0 }], 7500);

    const cv = document.createElement('canvas');
    cv.width = this.W; cv.height = this.H;
    cv.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;mix-blend-mode:screen;';
    fx.appendChild(cv);
    this.fireworks(cv, 5200 / this.S);

    // 왕관
    const crown = this.mk(fx, 'left:50%;top:420px;width:520px;height:300px;transform:translate(-50%,-50%) translateY(-900px);opacity:0;clip-path:polygon(0 100%,100% 100%,100% 26%,84% 52%,68% 8%,50% 46%,32% 8%,16% 52%,0 26%);background:linear-gradient(160deg,#fff3cf,#e0bb5a 34%,#9a7420 62%,#f5e3ac);');
    this.a(crown, [{ transform: 'translate(-50%,-50%) translateY(-900px) rotate(-6deg)', opacity: 0 }, { transform: 'translate(-50%,-50%) translateY(0) rotate(2deg)', opacity: 1, offset: .28 }, { transform: 'translate(-50%,-50%) translateY(0) rotate(0deg)', opacity: 1, offset: .4 }, { transform: 'translate(-50%,-50%) translateY(0)', opacity: 1, offset: .88 }, { transform: 'translate(-50%,-50%) translateY(-30px)', opacity: 0 }], 4600, 2400, 'cubic-bezier(.16,1,.3,1)');
    const band = this.mk(fx, 'left:50%;top:530px;width:520px;height:44px;transform:translate(-50%,-50%);background:linear-gradient(180deg,#f7e6b6,#a97f24);opacity:0;');
    this.a(band, [{ opacity: 0, transform: 'translate(-50%,-50%) translateY(-40px)' }, { opacity: 1, transform: 'translate(-50%,-50%) translateY(0)', offset: .3 }, { opacity: 1, offset: .88 }, { opacity: 0 }], 4600, 2500, 'cubic-bezier(.16,1,.3,1)');

    // MVP 인장
    const STAMP = 5500;
    const seal = this.mk(fx, 'left:50%;top:760px;width:400px;height:400px;border-radius:50%;transform:translate(-50%,-50%) scale(1.9);opacity:0;border:5px solid #d9b45a;box-shadow:inset 0 0 0 14px rgba(0,0,0,.55), inset 0 0 0 18px #d9b45a;background:rgba(24,16,4,.72);');
    const sealTx = document.createElement('div');
    sealTx.textContent = 'MVP';
    sealTx.style.cssText = "position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-family:'Anton',sans-serif;font-size:118px;letter-spacing:.08em;color:#f6e7b4;";
    seal.appendChild(sealTx);
    this.a(seal, [{ transform: 'translate(-50%,-50%) scale(1.9) rotate(-8deg)', opacity: 0 }, { transform: 'translate(-50%,-50%) scale(1) rotate(0deg)', opacity: 1, offset: .06 }, { transform: 'translate(-50%,-50%) scale(1)', opacity: 1, offset: .9 }, { transform: 'translate(-50%,-50%) scale(1.02)', opacity: 0 }], 2000, STAMP, 'cubic-bezier(.1,.95,.2,1)');
    this.flash(fx, '#ffe9b0', .6, 200, STAMP + 40);
    const ring = this.mk(fx, 'left:50%;top:760px;width:400px;height:400px;border-radius:50%;border:10px solid rgba(217,180,90,.8);transform:translate(-50%,-50%) scale(.9);');
    this.a(ring, [{ transform: 'translate(-50%,-50%) scale(.9)', opacity: 1 }, { transform: 'translate(-50%,-50%) scale(3)', opacity: 0 }], 900, STAMP + 60, 'cubic-bezier(.15,.9,.3,1)');
    this.shake(shake, 30, 380, STAMP + 30);

    const sweep = this.mk(fx, 'top:-20%;bottom:-20%;left:0;width:340px;background:linear-gradient(90deg,rgba(255,255,255,0),rgba(255,244,210,.14),rgba(255,255,255,0));mix-blend-mode:screen;');
    this.a(sweep, [{ transform: 'skewX(-14deg) translateX(-460px)' }, { transform: 'skewX(-14deg) translateX(2100px)' }], 1800, STAMP + 500, 'cubic-bezier(.42,0,.5,1)');
  }

  fireworks(cv, totalMs) {
    const ctx = cv.getContext('2d');
    const parts = [];
    let alive = true;
    setTimeout(() => { alive = false; }, totalMs);
    // ⚠️ '아직 살아 있나' 는 parentNode 로 보면 안 된다.
    //    stop() 은 연출 레이어를 통째로 떼는데, 그래도 캔버스의 부모는 여전히
    //    그 레이어라서 parentNode 는 참으로 남는다. 그래서 예전에는 연출을 끊어도
    //    불꽃 연쇄와 rAF 루프가 원래 길이(최대 7.5초)만큼 계속 돌면서, 화면에
    //    붙어 있지도 않은 캔버스에 74개씩 입자를 뿌리고 그림을 그렸다.
    //    문서에 실제로 붙어 있는지를 봐야 한다.
    const onScreen = () => document.contains(cv);
    const burst = () => {
      if (!alive || !onScreen()) return;
      const x = this.rnd(260, 1660), y = this.rnd(140, 520);
      const hue = [45, 42, 38, 50, 330][Math.floor(Math.random() * 5)];
      const n = 74;
      for (let i = 0; i < n; i++) {
        const a = Math.random() * Math.PI * 2, v = 1.6 + Math.pow(Math.random(), .6) * 7.4;
        parts.push({ x: x, y: y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, life: 1, hue: hue + this.rnd(-8, 8), sz: this.rnd(1.8, 3.4) });
      }
      setTimeout(burst, this.rnd(320, 620) / this.S);
    };
    burst();
    setTimeout(burst, 240 / this.S);
    const tick = () => {
      if (!onScreen()) return;
      if (!alive && !parts.length) { ctx.clearRect(0, 0, this.W, this.H); return; }
      ctx.globalCompositeOperation = 'source-over';
      ctx.fillStyle = 'rgba(0,0,0,.22)';
      ctx.fillRect(0, 0, this.W, this.H);
      ctx.globalCompositeOperation = 'lighter';
      for (let i = parts.length - 1; i >= 0; i--) {
        const p = parts[i];
        p.x += p.vx; p.y += p.vy; p.vy += 0.055; p.vx *= 0.987; p.vy *= 0.987; p.life -= 0.0115;
        if (p.life <= 0) { parts.splice(i, 1); continue; }
        ctx.globalAlpha = Math.max(0, p.life) * (0.6 + Math.random() * 0.4);
        ctx.fillStyle = 'hsl(' + p.hue + ' 96% ' + (58 + p.life * 30) + '%)';
        ctx.beginPath(); ctx.arc(p.x, p.y, p.sz, 0, 7); ctx.fill();
      }
      ctx.globalAlpha = 1;
      requestAnimationFrame(tick);
    };
    tick();
  }
}

const SigFX = new SigEngine();
if (typeof module !== 'undefined' && module.exports) module.exports = SigFX;
global.SigFX = SigFX;
})(typeof window !== 'undefined' ? window : this);
