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
  constructor() { this.opts = { speed: 1, impact: 1 }; }

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
    // 세로 판에서는 폭이 좁아 그대로 줄이면 글자가 너무 작다. 화면을 채우게 키운다.
    this.KS = (W / 1920) * (portrait ? 1.6 : 1);
    this.KY = H / 1080;
  }
  _n(v, k) { return +(parseFloat(v) * k).toFixed(1); }
  // 가로 위치: 가운데 기준으로 접는다
  _x(v) { return +(this.W / 2 + (parseFloat(v) - 960) * this.KS).toFixed(1); }
  _r(v) { return +(this.W / 2 - (960 - parseFloat(v)) * this.KS).toFixed(1); }

  mapCss(css) {
    if (!css || (this.KS === 1 && this.KY === 1)) return css;
    return css
      // 위치 — 0 은 화면 끝이므로 그대로 둔다
      .replace(/(^|[;{\s])left:\s*(-?\d*\.?\d+)px/g,   (m,p,v) => +v === 0 ? m : p + 'left:'   + this._x(v) + 'px')
      .replace(/(^|[;{\s])right:\s*(-?\d*\.?\d+)px/g,  (m,p,v) => +v === 0 ? m : p + 'right:'  + this._r(v) + 'px')
      .replace(/(^|[;{\s])top:\s*(-?\d*\.?\d+)px/g,    (m,p,v) => +v === 0 ? m : p + 'top:'    + this._n(v, this.KY) + 'px')
      .replace(/(^|[;{\s])bottom:\s*(-?\d*\.?\d+)px/g, (m,p,v) => +v === 0 ? m : p + 'bottom:' + this._n(v, this.KY) + 'px')
      // 길이·글자 — 한 배율로만
      .replace(/(width|height|font-size|letter-spacing|border-radius|border-width|padding|margin|blur|gap):\s*(-?\d*\.?\d+)px/g,
               (m,p,v) => +v === 0 ? m : p + ':' + this._n(v, this.KS) + 'px')
      .replace(/border:\s*(-?\d*\.?\d+)px/g, (m,v) => 'border:' + this._n(v, this.KS) + 'px')
      .replace(/blur\((-?\d*\.?\d+)px\)/g,  (m,v) => 'blur('   + this._n(v, this.KS) + 'px)')
      .replace(/translateX\((-?\d*\.?\d+)px\)/g, (m,v) => 'translateX(' + this._n(v, this.KS) + 'px)')
      .replace(/translateY\((-?\d*\.?\d+)px\)/g, (m,v) => 'translateY(' + this._n(v, this.KY) + 'px)');
  }

  // 애니메이션 프레임 안의 transform 문자열도 같은 규칙으로 옮긴다
  mapFrames(frames) {
    if (this.KS === 1 && this.KY === 1) return frames;
    return frames.map(f => {
      if (!f || typeof f.transform !== 'string') return f;
      const t = f.transform
        .replace(/translateX\((-?\d*\.?\d+)px\)/g, (m,v) => 'translateX(' + this._n(v, this.KS) + 'px)')
        .replace(/translateY\((-?\d*\.?\d+)px\)/g, (m,v) => 'translateY(' + this._n(v, this.KY) + 'px)')
        .replace(/translate\((-?\d*\.?\d+)px\s*,\s*(-?\d*\.?\d+)px\)/g,
                 (m,a,b) => 'translate(' + this._n(a, this.KS) + 'px,' + this._n(b, this.KY) + 'px)');
      return Object.assign({}, f, { transform: t });
    });
  }

  ITEMS = [
    { key: 'gazua',  tier: '10만',    name: '가즈아',        note: '화염 분출',   dur: 1.8, detail: '흰 컷이 때리고 빠지며 불기둥이 치솟습니다' },
    { key: 'lambada',tier: '13만',    name: '람바다',        note: '선셋 탱고',   dur: 2.2, detail: '레트로 선셋이 떠오르고 야자 실루엣이 펼쳐집니다' },
    { key: 'hotel',  tier: '15만',    name: '부티호텔',      note: '동결',        dur: 2.4, detail: '가장자리부터 결정이 자라고 HOTEL 사인이 점등됩니다' },
    { key: 'crazy',  tier: '16만',    name: '크레이지 러브', note: '블랙홀',      dur: 2.4, detail: '화면이 소용돌이로 빨려들었다 무지개로 터집니다' },
    { key: 'bounce', tier: '18만',    name: '바운스',        note: '바운스',      dur: 2.0, detail: '착지마다 화면이 눌리고 늘어납니다' },
    { key: 'martini',tier: '20만',    name: '마티니',        note: '마티니 타임', dur: 2.8, detail: '화면이 흑백으로 내려앉고 금빛이 한 번 스칩니다' },
    { key: 'pocha',  tier: '200,001', name: '뽀카치포',      note: '질주',        dur: 2.2, detail: '헤드라이트가 훑고 화면이 드리프트합니다' },
    { key: 'pucha',  tier: '30만',    name: '푸차',          note: '심해',        dur: 2.8, detail: '물결이 두 겹으로 차오르고 기포가 올라옵니다' },
    { key: 'edm',    tier: '35만',    name: 'EDM',           note: '산성 파열',   dur: 2.6, detail: '초록 균열이 갈라지고 스캔라인이 어긋납니다' },
    { key: 'sail',   tier: '50만',    name: '출항',          note: '출항이요',    dur: 3.4, detail: '비단이 흐른 뒤 두루마리가 좌우로 펼쳐집니다' },
    { key: 'shield', tier: '500,001', name: '50만 방패',     note: '방패 강림',   dur: 3.2, detail: '방패가 내려찍히고 충격파와 분홍 번개가 터집니다' },
    { key: 'slash',  tier: '600,001', name: '74번 알림',     note: '참격',        dur: 2.6, detail: 'X자로 두 번 베고 화면이 갈라집니다' },
    { key: 'nuna',   tier: '70만',    name: '누나누나',      note: '심쿵',        dur: 3.2, detail: '실제 심장 리듬으로 두 번씩 두근거립니다' },
    { key: 'club',   tier: '80만',    name: '클럽음악',      note: '클럽 개장',   dur: 3.4, detail: '레이저가 스윙하고 이퀄라이저가 비트를 칩니다' },
    { key: 'vip',    tier: '100만',   name: 'VIP',           note: 'VIP 입장',    dur: 4.6, detail: '금속 광택이 글자 위를 한 번 지나갑니다' },
    { key: 'angel',  tier: '200만',   name: '엔젤 VIP',      note: '천상 강림',   dur: 5.2, detail: '빛기둥이 내려오고 날개가 천천히 펼쳐집니다' },
    { key: 'mvp',    tier: '300만',   name: 'MVP',           note: '대관식',      dur: 7.5, detail: '불꽃놀이 뒤 왕관이 내려오고 인장이 찍힙니다' },
  ];

  play(key, stageEl, opts) {
    const item = this.ITEMS.find(i => i.key === key);
    if (!item) throw new Error('SigFX: 알 수 없는 key — ' + key);
    this.opts = Object.assign({ speed: 1, impact: 1 }, opts);
    this._fit(stageEl);   // 판 크기를 재서 좌표 옮김 배율을 정한다
    const old = stageEl.querySelector(':scope > [data-sigfx]');
    if (old) old.remove();
    // 흔들 대상. 오버레이처럼 무대와 방송 내용물이 다른 요소일 때는 opts.shakeEl 로 지정한다.
    const shake = this.opts.shakeEl || stageEl.querySelector('[data-shake]') || stageEl.firstElementChild || stageEl;
    shake.getAnimations().forEach(a => a.cancel());
    const fx = document.createElement('div');
    fx.setAttribute('data-sigfx', key);
    fx.style.cssText = 'position:absolute;inset:0;overflow:hidden;pointer-events:none;z-index:60;';
    stageEl.appendChild(fx);
    this['fx_' + key](fx, shake);
    const ms = (item.dur * 1000 + 160) / this.opts.speed;
    setTimeout(() => { if (fx.parentNode) fx.remove(); }, ms);
    return ms;
  }

  mk(p, css) { const d = document.createElement('div'); d.style.cssText = 'position:absolute;' + this.mapCss(css); p.appendChild(d); return d; }
  a(el, frames, dur, delay, ease) {
    return el.animate(this.mapFrames(frames), { duration: dur / this.S, delay: (delay || 0) / this.S, easing: ease || 'linear', fill: 'forwards' });
  }
  txt(fx, content, css, top) {
    // ⚠️ 가로로 꽉 찬 줄이라 left/right 은 0 그대로 두고 top 만 옮긴다.
    const w = this.mk(fx, 'left:0;right:0;top:' + this._n(top, this.KY) + 'px;display:flex;justify-content:center;');
    const d = document.createElement('div'); d.textContent = content;
    d.style.cssText = this.mapCss(css); w.appendChild(d);
    return { w: w, d: d };
  }
  flash(fx, color, op, dur, delay) {
    const f = this.mk(fx, 'inset:0;background:' + color + ';opacity:0;mix-blend-mode:screen;');
    this.a(f, [{ opacity: op }, { opacity: 0 }], dur, delay, 'linear');
    return f;
  }
  shake(shake, amp, dur, delay) {
    const n = Math.max(6, Math.round(dur / 26)), fr = [];
    for (let i = 0; i <= n; i++) {
      const f = Math.pow(1 - i / n, 1.6);
      fr.push({ transform: 'translate(' + ((Math.random() * 2 - 1) * amp * this.P * f * this.KS).toFixed(1) + 'px,' + ((Math.random() * 2 - 1) * amp * this.P * f * this.KS).toFixed(1) + 'px)' });
    }
    fr.push({ transform: 'translate(0,0)' });
    shake.animate(fr, { duration: dur / this.S, delay: (delay || 0) / this.S, easing: 'linear' });
  }
  rnd(a, b) { return a + Math.random() * (b - a); }

  /* ══ 10만 가즈아 — 화염 분출 (1.8s) ══ */
  fx_gazua(fx, shake) {
    const band = this.mk(fx, 'left:0;right:0;top:50%;height:6px;background:#fff;transform:translateY(-50%) scaleX(.15);');
    this.a(band, [{ transform: 'translateY(-50%) scaleX(.15)', opacity: .6 }, { transform: 'translateY(-50%) scaleX(1)', opacity: 1 }], 70, 0, 'cubic-bezier(.2,.9,.3,1)');
    this.a(band, [{ opacity: 1 }, { opacity: 0 }], 90, 70);

    const sheet = this.mk(fx, 'inset:0;background:#f7f4ec;opacity:0;');
    this.a(sheet, [{ opacity: 0, offset: 0 }, { opacity: 1, offset: .02 }, { opacity: .95, offset: 1 }], 400, 65);
    this.a(sheet, [{ clipPath: 'inset(0 0 0 0)' }, { clipPath: 'inset(0 0 100% 0)' }], 190, 430, 'cubic-bezier(.7,0,.2,1)');

    const lines = this.mk(fx, 'inset:-25%;opacity:0;background:repeating-conic-gradient(from 0deg at 50% 50%, #111 0deg .55deg, transparent .55deg 2.6deg);-webkit-mask-image:radial-gradient(circle at 50% 50%, transparent 24%, #000 62%);mask-image:radial-gradient(circle at 50% 50%, transparent 24%, #000 62%);');
    this.a(lines, [{ opacity: 0, transform: 'scale(1.55)' }, { opacity: 1, transform: 'scale(1) rotate(2deg)', offset: .12 }, { opacity: .5, transform: 'scale(1.05) rotate(3deg)', offset: .5 }, { opacity: 0, transform: 'scale(1.3) rotate(5deg)' }], 1250, 70, 'cubic-bezier(.1,.9,.2,1)');

    [-620, -330, 0, 350, 640].forEach((x, i) => {
      const w = 40 + (i % 2) * 30;
      const ch = this.mk(fx, 'left:50%;bottom:0;width:' + w + 'px;height:920px;background:linear-gradient(to top,#ff4d00,#ffa02a 40%,rgba(255,180,60,0));clip-path:polygon(50% 0,100% 14%,100% 100%,0 100%,0 14%);opacity:0;');
      this.a(ch, [{ transform: 'translateX(' + x + 'px) translateY(340px)', opacity: 0 }, { transform: 'translateX(' + x + 'px) translateY(-120px)', opacity: .95, offset: .34 }, { transform: 'translateX(' + x + 'px) translateY(-760px)', opacity: 0 }], 780, 180 + i * 50, 'cubic-bezier(.2,.85,.3,1)');
    });
    for (let i = 0; i < 20; i++) {
      const s = this.rnd(4, 9);
      const p = this.mk(fx, 'left:' + this.rnd(0, 1900).toFixed(0) + 'px;bottom:0;width:' + s.toFixed(1) + 'px;height:' + s.toFixed(1) + 'px;background:#ffd24a;');
      this.a(p, [{ transform: 'translateY(0)', opacity: 1 }, { transform: 'translateY(-' + this.rnd(500, 1000).toFixed(0) + 'px) translateX(' + this.rnd(-140, 140).toFixed(0) + 'px)', opacity: 0 }], this.rnd(700, 1300), this.rnd(120, 700), 'cubic-bezier(.3,0,.6,1)');
    }

    const t = this.txt(fx, '가즈아', "font-family:'Black Han Sans',sans-serif;font-size:214px;line-height:.9;color:#14110c;letter-spacing:-.02em;transform:skewX(-7deg);", 640);
    this.a(t.w, [{ transform: 'translateY(90px) scale(1.35)', opacity: 0 }, { transform: 'translateY(-10px) scale(.97)', opacity: 1, offset: .1 }, { transform: 'translateY(0) scale(1)', opacity: 1, offset: .18 }, { transform: 'translateY(-14px) scale(1)', opacity: 1, offset: .72 }, { transform: 'translateY(-190px) scale(1.04)', opacity: 0 }], 1760, 85, 'cubic-bezier(.14,1,.3,1)');
    this.a(t.d, [{ color: '#14110c' }, { color: '#fdfaf2' }], 1, 560);

    this.shake(shake, 26, 320, 60);
    this.shake(shake, 9, 200, 470);
  }

  /* ══ 13만 람바다 — 선셋 탱고 (2.2s) ══ */
  fx_lambada(fx) {
    const wash = this.mk(fx, 'inset:0;background:linear-gradient(to top,rgba(255,86,40,.62),rgba(255,150,60,.28) 48%,rgba(58,20,74,.34));opacity:0;');
    this.a(wash, [{ opacity: 0 }, { opacity: 1, offset: .22 }, { opacity: 1, offset: .8 }, { opacity: 0 }], 2200, 0, 'cubic-bezier(.3,0,.4,1)');

    const sun = this.mk(fx, 'left:50%;bottom:60px;width:520px;height:520px;border-radius:50%;background:linear-gradient(to top,#ff7a2e,#ffd98a);transform:translateX(-50%) translateY(340px);opacity:0;-webkit-mask-image:linear-gradient(#000 0 62%, transparent 62% 65%, #000 65% 74%, transparent 74% 78%, #000 78% 85%, transparent 85% 89%, #000 89%);mask-image:linear-gradient(#000 0 62%, transparent 62% 65%, #000 65% 74%, transparent 74% 78%, #000 78% 85%, transparent 85% 89%, #000 89%);');
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

  /* ══ 15만 부티호텔 — 동결 (2.4s) ══ */
  fx_hotel(fx) {
    const tint = this.mk(fx, 'inset:0;background:linear-gradient(180deg,rgba(120,190,255,.26),rgba(180,225,255,.14));opacity:0;');
    this.a(tint, [{ opacity: 0 }, { opacity: 1, offset: .18 }, { opacity: 1, offset: .78 }, { opacity: 0 }], 2400);

    const frost = this.mk(fx, 'inset:0;');
    this.a(frost, [{ boxShadow: 'inset 0 0 0 0 rgba(200,232,255,0)' }, { boxShadow: 'inset 0 0 220px 90px rgba(206,234,255,.82)', offset: .3 }, { boxShadow: 'inset 0 0 220px 90px rgba(206,234,255,.82)', offset: .76 }, { boxShadow: 'inset 0 0 0 0 rgba(200,232,255,0)' }], 2400, 0, 'cubic-bezier(.2,.8,.3,1)');

    // 결정 스파이크 (가장자리에서 안쪽으로)
    for (let i = 0; i < 22; i++) {
      const edge = i % 4, len = this.rnd(140, 380), w = this.rnd(16, 40);
      let css = 'width:' + w.toFixed(0) + 'px;height:' + len.toFixed(0) + 'px;background:linear-gradient(to bottom,rgba(255,255,255,.9),rgba(160,214,255,0));clip-path:polygon(50% 100%,100% 0,0 0);transform-origin:50% 0%;opacity:0;';
      if (edge === 0) css += 'top:0;left:' + this.rnd(0, 1880).toFixed(0) + 'px;';
      if (edge === 1) css += 'bottom:0;left:' + this.rnd(0, 1880).toFixed(0) + 'px;transform:rotate(180deg);';
      if (edge === 2) css += 'left:0;top:' + this.rnd(0, 1000).toFixed(0) + 'px;transform:rotate(-90deg);transform-origin:50% 0%;';
      if (edge === 3) css += 'right:0;top:' + this.rnd(0, 1000).toFixed(0) + 'px;transform:rotate(90deg);';
      const sp = this.mk(fx, css);
      const base = edge === 1 ? 'rotate(180deg)' : edge === 2 ? 'rotate(-90deg)' : edge === 3 ? 'rotate(90deg)' : '';
      this.a(sp, [{ transform: base + ' scaleY(0)', opacity: 0 }, { transform: base + ' scaleY(1)', opacity: .85, offset: .3 }, { transform: base + ' scaleY(1)', opacity: .85, offset: .78 }, { transform: base + ' scaleY(.9)', opacity: 0 }], 2300, 60 + i * 32, 'cubic-bezier(.16,1,.3,1)');
    }

    // HOTEL 네온 사인
    const sign = this.mk(fx, 'left:50%;top:250px;transform:translateX(-50%);padding:26px 54px;border:3px solid rgba(120,200,255,.85);box-shadow:inset 0 0 0 9px rgba(0,0,0,.35);opacity:0;');
    const label = document.createElement('div');
    label.textContent = 'HOTEL';
    label.style.cssText = "font-family:'Anton',sans-serif;font-size:126px;line-height:.92;letter-spacing:.14em;color:#d6ecff;";
    sign.appendChild(label);
    this.a(sign, [{ opacity: 0, offset: 0 }, { opacity: 1, offset: .06 }, { opacity: 0, offset: .09 }, { opacity: 1, offset: .13 }, { opacity: 0, offset: .16 }, { opacity: 1, offset: .2 }, { opacity: 1, offset: .8 }, { opacity: 0, offset: 1 }], 2300, 260, 'steps(1,end)');
    const halo = this.mk(fx, 'left:50%;top:250px;width:820px;height:230px;transform:translateX(-50%);background:radial-gradient(60% 70% at 50% 50%,rgba(110,200,255,.4),transparent 70%);opacity:0;mix-blend-mode:screen;');
    this.a(halo, [{ opacity: 0 }, { opacity: 1, offset: .2 }, { opacity: 1, offset: .8 }, { opacity: 0 }], 2300, 260);

    for (let i = 0; i < 24; i++) {
      const s = this.rnd(3, 6);
      const sn = this.mk(fx, 'left:' + this.rnd(0, 1900).toFixed(0) + 'px;top:-20px;width:' + s.toFixed(1) + 'px;height:' + s.toFixed(1) + 'px;border-radius:50%;background:#f0f9ff;');
      this.a(sn, [{ transform: 'translateY(0)', opacity: 0 }, { opacity: .85, offset: .1 }, { transform: 'translateY(1150px) translateX(' + this.rnd(-120, 120).toFixed(0) + 'px)', opacity: 0 }], this.rnd(1600, 2200), this.rnd(0, 700), 'cubic-bezier(.4,0,.6,1)');
    }
  }

  /* ══ 16만 크레이지 러브 — 블랙홀 (2.4s) ══ */
  fx_crazy(fx, shake) {
    this.a(shake, [{ transform: 'scale(1) rotate(0deg)' }, { transform: 'scale(.52) rotate(-16deg)', offset: .42 }, { transform: 'scale(.5) rotate(12deg)', offset: .56 }, { transform: 'scale(1.06) rotate(0deg)', offset: .78 }, { transform: 'scale(1) rotate(0deg)' }], 2300, 0, 'cubic-bezier(.55,0,.3,1)');

    const dark = this.mk(fx, 'inset:0;background:radial-gradient(50% 50% at 50% 50%, rgba(0,0,0,.92), rgba(0,0,0,.2) 70%, transparent);opacity:0;');
    this.a(dark, [{ opacity: 0, transform: 'scale(.2)' }, { opacity: 1, transform: 'scale(1.1)', offset: .48 }, { opacity: 0, transform: 'scale(2.2)' }], 2300, 0, 'cubic-bezier(.4,0,.5,1)');

    const vx = this.mk(fx, 'left:50%;top:50%;width:1500px;height:1500px;border-radius:50%;transform:translate(-50%,-50%) scale(.15);mix-blend-mode:screen;background:conic-gradient(from 0deg,rgba(176,108,255,0),#b06cff 18%,rgba(34,230,255,0) 34%,#22e6ff 56%,rgba(176,108,255,0) 74%,#b06cff 92%,rgba(176,108,255,0));-webkit-mask-image:radial-gradient(circle,transparent 22%,#000 42%,#000 66%,transparent 78%);mask-image:radial-gradient(circle,transparent 22%,#000 42%,#000 66%,transparent 78%);');
    this.a(vx, [{ transform: 'translate(-50%,-50%) scale(.15) rotate(0deg)', opacity: 0 }, { transform: 'translate(-50%,-50%) scale(.85) rotate(420deg)', opacity: 1, offset: .45 }, { transform: 'translate(-50%,-50%) scale(.2) rotate(760deg)', opacity: .8, offset: .58 }, { transform: 'translate(-50%,-50%) scale(2.6) rotate(900deg)', opacity: 0 }], 2300, 0, 'cubic-bezier(.5,0,.35,1)');

    this.flash(fx, '#ffffff', .9, 90, 1360);
    const ring = this.mk(fx, 'left:50%;top:50%;width:400px;height:400px;border-radius:50%;border:14px solid transparent;border-image:conic-gradient(#ff5fa2,#ffd24a,#59ff9e,#22e6ff,#b06cff,#ff5fa2) 1;transform:translate(-50%,-50%) scale(.1);mix-blend-mode:screen;');
    this.a(ring, [{ transform: 'translate(-50%,-50%) scale(.1)', opacity: 1 }, { transform: 'translate(-50%,-50%) scale(5.4)', opacity: 0 }], 720, 1380, 'cubic-bezier(.2,.9,.3,1)');

    for (let i = 0; i < 18; i++) {
      const ang = i / 18 * Math.PI * 2, r = this.rnd(360, 860);
      const c = ['#ff5fa2', '#b06cff', '#22e6ff', '#ffffff'][i % 4];
      const st = this.mk(fx, 'left:50%;top:50%;width:6px;height:26px;background:' + c + ';transform:translate(-50%,-50%) rotate(' + (ang * 180 / Math.PI) + 'deg);');
      this.a(st, [{ transform: 'translate(-50%,-50%) rotate(' + (ang * 180 / Math.PI + 90) + 'deg) translateY(0)', opacity: 1 }, { transform: 'translate(-50%,-50%) rotate(' + (ang * 180 / Math.PI + 90) + 'deg) translateY(-' + r.toFixed(0) + 'px)', opacity: 0 }], 700, 1400 + i * 12, 'cubic-bezier(.15,.9,.3,1)');
    }
    const t = this.txt(fx, '크레이지 러브', "font-family:'IBM Plex Sans KR',sans-serif;font-weight:700;font-size:96px;line-height:1;color:#fff;letter-spacing:.14em;", 760);
    this.a(t.w, [{ transform: 'scale(1.5)', opacity: 0 }, { transform: 'scale(1)', opacity: 1, offset: .18 }, { transform: 'scale(1)', opacity: 1, offset: .78 }, { transform: 'scale(1.04)', opacity: 0 }], 940, 1400, 'cubic-bezier(.16,1,.3,1)');
  }

  /* ══ 18만 바운스 (2.0s) ══ */
  fx_bounce(fx, shake) {
    const hits = [120, 640, 1080, 1420];
    this.a(shake, [
      { transform: 'translateY(0) scale(1,1)', offset: 0 },
      { transform: 'translateY(-150px) scale(.96,1.06)', offset: .1 },
      { transform: 'translateY(0) scale(1.07,.9)', offset: .2 },
      { transform: 'translateY(-96px) scale(.98,1.04)', offset: .32 },
      { transform: 'translateY(0) scale(1.05,.93)', offset: .44 },
      { transform: 'translateY(-54px) scale(.99,1.02)', offset: .56 },
      { transform: 'translateY(0) scale(1.03,.96)', offset: .66 },
      { transform: 'translateY(-24px) scale(1,1.01)', offset: .76 },
      { transform: 'translateY(0) scale(1,1)', offset: .86 },
      { transform: 'translateY(0) scale(1,1)', offset: 1 },
    ], 1900, 0, 'cubic-bezier(.4,0,.5,1)');

    const floor = this.mk(fx, 'left:0;right:0;bottom:78px;height:7px;background:#fff;transform:scaleX(.2);opacity:0;');
    this.a(floor, [{ transform: 'scaleX(.2)', opacity: 0 }, { transform: 'scaleX(1)', opacity: 1, offset: .1 }, { transform: 'scaleX(1)', opacity: 1, offset: .82 }, { transform: 'scaleX(.9)', opacity: 0 }], 1900, 0, 'cubic-bezier(.16,1,.3,1)');

    hits.forEach((ms, k) => {
      this.flash(fx, '#ff3b30', .22 - k * .04, 130, ms);
      for (let i = 0; i < 6; i++) {
        const s = this.rnd(16, 40);
        const p = this.mk(fx, 'left:50%;bottom:' + (78 + this.rnd(0, 26)).toFixed(0) + 'px;width:' + s.toFixed(0) + 'px;height:' + s.toFixed(0) + 'px;border-radius:50%;background:rgba(255,255,255,.5);');
        this.a(p, [{ transform: 'translateX(0) scale(.3)', opacity: .7 }, { transform: 'translateX(' + this.rnd(-560, 560).toFixed(0) + 'px) translateY(-' + this.rnd(20, 90).toFixed(0) + 'px) scale(1.5)', opacity: 0 }], 480, ms, 'cubic-bezier(.2,.9,.3,1)');
      }
    });

    const t = this.txt(fx, 'BOUNCE!', "font-family:'Anton',sans-serif;font-size:184px;line-height:.92;letter-spacing:.03em;color:#fff;-webkit-text-stroke:0;", 400);
    this.a(t.w, [
      { transform: 'translateY(-360px) scale(1,1.3)', opacity: 0 },
      { transform: 'translateY(0) scale(1,1)', opacity: 1, offset: .07 },
      { transform: 'translateY(20px) scale(1.16,.8)', opacity: 1, offset: .1 },
      { transform: 'translateY(-70px) scale(.94,1.1)', offset: .2 },
      { transform: 'translateY(14px) scale(1.1,.87)', offset: .32 },
      { transform: 'translateY(-38px) scale(.98,1.04)', offset: .46 },
      { transform: 'translateY(6px) scale(1.05,.94)', offset: .58 },
      { transform: 'translateY(0) scale(1,1)', offset: .74 },
      { transform: 'translateY(0) scale(1,1)', opacity: 1, offset: .86 },
      { transform: 'translateY(0) scale(1.06,1)', opacity: 0 },
    ], 1900, 0, 'cubic-bezier(.4,0,.5,1)');
  }

  /* ══ 20만 마티니 — 마티니 타임 (2.8s) ══ */
  fx_martini(fx) {
    const mono = this.mk(fx, 'inset:0;backdrop-filter:grayscale(1) contrast(1.06) brightness(.82);-webkit-backdrop-filter:grayscale(1) contrast(1.06) brightness(.82);opacity:0;');
    this.a(mono, [{ opacity: 0 }, { opacity: 1, offset: .22 }, { opacity: 1, offset: .8 }, { opacity: 0 }], 2800, 0, 'cubic-bezier(.4,0,.3,1)');
    const vig = this.mk(fx, 'inset:0;background:radial-gradient(100% 76% at 50% 48%,rgba(0,0,0,.15),rgba(0,0,0,.8));opacity:0;');
    this.a(vig, [{ opacity: 0 }, { opacity: 1, offset: .22 }, { opacity: 1, offset: .8 }, { opacity: 0 }], 2800);

    // 금 코너 브래킷 4개
    [[70, 70, 1, 1], [1850, 70, -1, 1], [70, 1010, 1, -1], [1850, 1010, -1, -1]].forEach((c, i) => {
      const h = this.mk(fx, 'left:' + c[0] + 'px;top:' + c[1] + 'px;width:220px;height:2px;background:#c9a227;transform-origin:' + (c[2] > 0 ? '0%' : '100%') + ' 50%;transform:scaleX(0);');
      this.a(h, [{ transform: 'scaleX(0)' }, { transform: 'scaleX(' + c[2] + ')' }], 700, 200 + i * 70, 'cubic-bezier(.16,1,.3,1)');
      const v = this.mk(fx, 'left:' + c[0] + 'px;top:' + c[1] + 'px;width:2px;height:150px;background:#c9a227;transform-origin:50% ' + (c[3] > 0 ? '0%' : '100%') + ';transform:scaleY(0);');
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
    this.a(t.d, [{ letterSpacing: '.62em', opacity: 0 }, { letterSpacing: '.34em', opacity: 1, offset: .34 }, { letterSpacing: '.32em', opacity: 1, offset: .8 }, { letterSpacing: '.32em', opacity: 0 }], 2600, 300, 'cubic-bezier(.16,1,.3,1)');
    const t2 = this.txt(fx, '마티니', "font-family:'IBM Plex Sans KR',sans-serif;font-weight:400;font-size:38px;color:rgba(242,230,200,.72);letter-spacing:.4em;", 660);
    this.a(t2.w, [{ opacity: 0 }, { opacity: 1, offset: .4 }, { opacity: 1, offset: .8 }, { opacity: 0 }], 2200, 900);
  }

  /* ══ 200,001 뽀카치포 — 질주 (2.2s) ══ */
  fx_pocha(fx, shake) {
    this.a(shake, [{ transform: 'skewX(0) translateX(0) rotate(0)' }, { transform: 'skewX(-7deg) translateX(70px) rotate(1.6deg)', offset: .14 }, { transform: 'skewX(4deg) translateX(-46px) rotate(-1deg)', offset: .38 }, { transform: 'skewX(-2deg) translateX(16px) rotate(.4deg)', offset: .62 }, { transform: 'skewX(0) translateX(0) rotate(0)', offset: .8 }], 2100, 0, 'cubic-bezier(.3,0,.4,1)');

    const dim = this.mk(fx, 'inset:0;background:rgba(4,4,8,.5);opacity:0;');
    this.a(dim, [{ opacity: 0 }, { opacity: 1, offset: .1 }, { opacity: 1, offset: .8 }, { opacity: 0 }], 2100);

    for (let i = 0; i < 34; i++) {
      const y = this.rnd(0, 1080), w = this.rnd(180, 620), h = this.rnd(2, 7);
      const l = this.mk(fx, 'left:-700px;top:' + y.toFixed(0) + 'px;width:' + w.toFixed(0) + 'px;height:' + h.toFixed(0) + 'px;background:linear-gradient(90deg,rgba(255,255,255,0),rgba(255,255,255,.85));');
      this.a(l, [{ transform: 'translateX(0)', opacity: 0 }, { opacity: 1, offset: .12 }, { transform: 'translateX(2900px)', opacity: 0 }], this.rnd(260, 480), this.rnd(0, 1500), 'cubic-bezier(.35,0,.5,1)');
    }
    [140, 1080].forEach(ms => {
      const hl = this.mk(fx, 'left:-800px;top:50%;width:900px;height:640px;border-radius:50%;transform:translateY(-50%);background:radial-gradient(50% 50% at 50% 50%,rgba(255,255,255,.85),rgba(255,240,200,.22) 55%,transparent 76%);mix-blend-mode:screen;');
      this.a(hl, [{ transform: 'translateY(-50%) translateX(0)' }, { transform: 'translateY(-50%) translateX(3000px)' }], 700, ms, 'cubic-bezier(.4,0,.5,1)');
    });
    const red = this.mk(fx, 'left:0;right:0;top:712px;height:9px;background:#ff2d2d;transform-origin:0 50%;transform:scaleX(0);');
    this.a(red, [{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)', offset: .2 }, { transform: 'scaleX(1)', offset: .78 }, { transform: 'scaleX(1) translateX(2000px)', opacity: 0 }], 2100, 260, 'cubic-bezier(.2,.9,.3,1)');

    const t = this.txt(fx, '뽀카치포', "font-family:'Black Han Sans',sans-serif;font-size:170px;line-height:.95;color:#fff;letter-spacing:-.02em;transform:skewX(-13deg);", 530);
    this.a(t.w, [{ transform: 'translateX(-900px)', opacity: 0 }, { transform: 'translateX(0)', opacity: 1, offset: .22 }, { transform: 'translateX(0)', opacity: 1, offset: .74 }, { transform: 'translateX(1200px)', opacity: 0 }], 2100, 200, 'cubic-bezier(.16,1,.3,1)');
  }

  /* ══ 30만 푸차 — 심해 (2.8s) ══ */
  fx_pucha(fx) {
    const tint = this.mk(fx, 'inset:0;background:linear-gradient(to top,rgba(10,60,120,.62),rgba(26,127,212,.26));opacity:0;');
    this.a(tint, [{ opacity: 0 }, { opacity: 1, offset: .25 }, { opacity: 1, offset: .8 }, { opacity: 0 }], 2800);

    [[0, 'rgba(26,127,212,.5)', 1200, 0], [1, 'rgba(60,170,235,.42)', 1500, 160]].forEach(v => {
      const layer = this.mk(fx, 'left:-10%;right:-10%;bottom:0;height:1100px;transform:translateY(1100px);');
      const body = this.mk(layer, 'left:0;right:0;bottom:0;top:70px;background:' + v[1] + ';');
      const wave = this.mk(layer, 'left:-20%;right:-20%;top:0;height:150px;background:' + v[1] + ';border-radius:50% 50% 0 0 / 100% 100% 0 0;');
      this.a(layer, [{ transform: 'translateY(1100px)' }, { transform: 'translateY(330px)', offset: .38 }, { transform: 'translateY(300px)', offset: .78 }, { transform: 'translateY(1100px)' }], 2700, v[3], 'cubic-bezier(.3,0,.35,1)');
      this.a(wave, [{ transform: 'translateX(-120px) scaleY(1)' }, { transform: 'translateX(120px) scaleY(.7)', offset: .5 }, { transform: 'translateX(-120px) scaleY(1)' }], v[2] * 1.6, 0, 'ease-in-out').updatePlaybackRate ? null : null;
      wave.animate([{ transform: 'translateX(-140px) scaleY(1)' }, { transform: 'translateX(140px) scaleY(.72)' }, { transform: 'translateX(-140px) scaleY(1)' }], { duration: v[2] / this.S, iterations: 3, easing: 'ease-in-out' });
    });

    const caus = this.mk(fx, 'inset:0;mix-blend-mode:soft-light;opacity:0;background:repeating-linear-gradient(74deg,rgba(255,255,255,.16) 0 3px,transparent 3px 46px);');
    this.a(caus, [{ opacity: 0, transform: 'translateX(-60px)' }, { opacity: 1, offset: .25 }, { opacity: 1, offset: .8 }, { opacity: 0, transform: 'translateX(60px)' }], 2800);

    for (let i = 0; i < 20; i++) {
      const d = this.rnd(20, 68);
      const b = this.mk(fx, 'left:' + this.rnd(0, 1880).toFixed(0) + 'px;bottom:-90px;width:' + d.toFixed(0) + 'px;height:' + d.toFixed(0) + 'px;border-radius:50%;border:3px solid rgba(214,240,255,.72);');
      this.a(b, [{ transform: 'translateY(0)', opacity: 0 }, { opacity: .9, offset: .14 }, { transform: 'translateY(-' + this.rnd(700, 1150).toFixed(0) + 'px) translateX(' + this.rnd(-90, 90).toFixed(0) + 'px)', opacity: 0 }], this.rnd(1500, 2300), this.rnd(200, 1200), 'cubic-bezier(.35,0,.6,1)');
    }
    const t = this.txt(fx, '푸차', "font-family:'IBM Plex Sans KR',sans-serif;font-weight:700;font-size:132px;line-height:1;color:#e6f6ff;letter-spacing:.24em;", 440);
    this.a(t.w, [{ transform: 'translateY(30px)', opacity: 0 }, { transform: 'translateY(0)', opacity: 1, offset: .28 }, { transform: 'translateY(-16px)', opacity: 1, offset: .78 }, { transform: 'translateY(-40px)', opacity: 0 }], 2700, 420, 'cubic-bezier(.16,1,.3,1)');
  }

  /* ══ 35만 EDM — 산성 파열 (2.6s) ══ */
  fx_edm(fx, shake) {
    const AC = '#59ff6a', CY = '#22e6ff';
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
      const w = this.mk(fx, 'left:0;right:0;top:700px;display:flex;justify-content:center;z-index:' + z + ';' + (blend ? 'mix-blend-mode:screen;' : ''));
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

  /* ══ 50만 출항이요 (3.4s) ══ */
  fx_sail(fx) {
    const glow = this.mk(fx, 'inset:0;background:radial-gradient(90% 70% at 50% 52%,rgba(201,162,39,.2),rgba(20,12,4,.72));opacity:0;');
    this.a(glow, [{ opacity: 0 }, { opacity: 1, offset: .2 }, { opacity: 1, offset: .82 }, { opacity: 0 }], 3400);

    [[130, -6, 0], [470, 5, 260], [820, -4, 520]].forEach(v => {
      const s = this.mk(fx, 'left:-40%;width:180%;top:' + v[0] + 'px;height:120px;transform:rotate(' + v[1] + 'deg) translateX(-100%);background:linear-gradient(90deg,rgba(179,64,43,0),#b3402b 18%,#e0745c 42%,#b3402b 62%,rgba(179,64,43,0));border-top:2px solid rgba(255,214,150,.5);border-bottom:2px solid rgba(120,30,20,.6);opacity:.9;');
      this.a(s, [{ transform: 'rotate(' + v[1] + 'deg) translateX(-110%) scaleY(.6)', opacity: 0 }, { transform: 'rotate(' + v[1] + 'deg) translateX(-6%) scaleY(1)', opacity: .92, offset: .34 }, { transform: 'rotate(' + v[1] + 'deg) translateX(4%) scaleY(1)', opacity: .92, offset: .74 }, { transform: 'rotate(' + v[1] + 'deg) translateX(110%) scaleY(.7)', opacity: 0 }], 3300, v[2], 'cubic-bezier(.3,0,.35,1)');
    });

    // 두루마리
    const scroll = this.mk(fx, 'left:50%;top:540px;width:1180px;height:230px;transform:translate(-50%,-50%) scaleX(0);background:linear-gradient(180deg,#f4e6c8,#e8d3a6);box-shadow:inset 0 0 40px rgba(140,100,40,.35);');
    this.a(scroll, [{ transform: 'translate(-50%,-50%) scaleX(0)' }, { transform: 'translate(-50%,-50%) scaleX(1)', offset: .28 }, { transform: 'translate(-50%,-50%) scaleX(1)', offset: .78 }, { transform: 'translate(-50%,-50%) scaleX(0)' }], 3200, 700, 'cubic-bezier(.16,1,.3,1)');
    const inner = document.createElement('div');
    inner.textContent = '출항이요';
    inner.style.cssText = "position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-family:'Black Han Sans',sans-serif;font-size:126px;color:#3a2408;letter-spacing:.16em;";
    scroll.appendChild(inner);
    this.a(inner, [{ clipPath: 'inset(0 50% 0 50%)' }, { clipPath: 'inset(0 0 0 0)' }], 700, 1000, 'cubic-bezier(.16,1,.3,1)');

    [[-590], [590]].forEach((v, i) => {
      const rod = this.mk(fx, 'left:50%;top:540px;width:30px;height:290px;transform:translate(-50%,-50%);background:linear-gradient(90deg,#7d5a1c,#d9b45a 45%,#7d5a1c);');
      this.a(rod, [{ transform: 'translate(-50%,-50%) translateX(0)', opacity: 0 }, { transform: 'translate(-50%,-50%) translateX(0)', opacity: 1, offset: .04 }, { transform: 'translate(-50%,-50%) translateX(' + v[0] + 'px)', opacity: 1, offset: .3 }, { transform: 'translate(-50%,-50%) translateX(' + v[0] + 'px)', opacity: 1, offset: .78 }, { transform: 'translate(-50%,-50%) translateX(0)', opacity: 0 }], 3200, 700, 'cubic-bezier(.16,1,.3,1)');
    });

    for (let i = 0; i < 24; i++) {
      const s = this.rnd(2, 5);
      const p = this.mk(fx, 'left:' + this.rnd(0, 1900).toFixed(0) + 'px;top:1120px;width:' + s.toFixed(1) + 'px;height:' + s.toFixed(1) + 'px;border-radius:50%;background:#f0dda4;');
      this.a(p, [{ transform: 'translateY(0)', opacity: 0 }, { opacity: .6, offset: .2 }, { transform: 'translateY(-' + this.rnd(700, 1150).toFixed(0) + 'px) translateX(' + this.rnd(-120, 120).toFixed(0) + 'px)', opacity: 0 }], this.rnd(2200, 3000), this.rnd(0, 1200), 'cubic-bezier(.4,0,.6,1)');
    }
  }

  /* ══ 500,001 방패 강림 (3.2s) ══ */
  fx_shield(fx, shake) {
    const dim = this.mk(fx, 'inset:0;background:rgba(4,4,10,.6);opacity:0;');
    this.a(dim, [{ opacity: 0 }, { opacity: 1, offset: .16 }, { opacity: 1, offset: .82 }, { opacity: 0 }], 3200);

    const sh = this.mk(fx, 'left:50%;top:470px;width:440px;height:540px;transform:translate(-50%,-50%) translateY(-1200px);clip-path:polygon(50% 0,100% 14%,100% 58%,50% 100%,0 58%,0 14%);background:linear-gradient(150deg,#eef3fa,#9fb0c6 38%,#5c6b80 62%,#c9d6e6);box-shadow:0 0 0 6px rgba(255,95,162,.5);');
    this.a(sh, [{ transform: 'translate(-50%,-50%) translateY(-1200px) scale(1.3)' }, { transform: 'translate(-50%,-50%) translateY(0) scale(1)', offset: .2 }, { transform: 'translate(-50%,-50%) translateY(0) scale(1)', offset: .8 }, { transform: 'translate(-50%,-50%) translateY(-40px) scale(1.04)', opacity: 0 }], 3100, 200, 'cubic-bezier(.6,0,.2,1)');
    const emb = document.createElement('div');
    emb.style.cssText = 'position:absolute;left:50%;top:44%;width:2px;height:250px;transform:translate(-50%,-50%);background:rgba(60,74,92,.55);';
    sh.appendChild(emb);

    const IMP = 820;
    this.flash(fx, '#ffffff', .9, 110, IMP);
    [0, 90, 190].forEach((d, i) => {
      const ring = this.mk(fx, 'left:50%;top:470px;width:360px;height:360px;border-radius:50%;border:' + (14 - i * 4) + 'px solid rgba(255,95,162,' + (.85 - i * .2) + ');transform:translate(-50%,-50%) scale(.15);');
      this.a(ring, [{ transform: 'translate(-50%,-50%) scale(.15)', opacity: 1 }, { transform: 'translate(-50%,-50%) scale(' + (5.2 + i) + ')', opacity: 0 }], 900 + i * 120, IMP + d, 'cubic-bezier(.15,.9,.3,1)');
    });
    for (let i = 0; i < 7; i++) {
      const rot = -100 + i * 33 + this.rnd(-8, 8);
      const b = this.mk(fx, 'left:50%;top:470px;width:26px;height:' + this.rnd(420, 780).toFixed(0) + 'px;background:linear-gradient(to bottom,#ff5fa2,rgba(255,95,162,0));transform-origin:50% 0%;transform:rotate(' + rot.toFixed(0) + 'deg) scaleY(0);clip-path:polygon(50% 0,100% 22%,32% 42%,100% 62%,20% 100%,64% 52%,0 34%);mix-blend-mode:screen;');
      this.a(b, [{ transform: 'rotate(' + rot.toFixed(0) + 'deg) scaleY(0)', opacity: 1 }, { transform: 'rotate(' + rot.toFixed(0) + 'deg) scaleY(1)', opacity: 1, offset: .3 }, { transform: 'rotate(' + rot.toFixed(0) + 'deg) scaleY(1)', opacity: 0 }], 620, IMP + 40 + i * 45, 'cubic-bezier(.1,.9,.2,1)');
    }
    const t = this.txt(fx, '방패', "font-family:'Black Han Sans',sans-serif;font-size:104px;color:#ffd9e8;letter-spacing:.3em;", 830);
    this.a(t.w, [{ transform: 'translateY(30px)', opacity: 0 }, { transform: 'translateY(0)', opacity: 1, offset: .16 }, { transform: 'translateY(0)', opacity: 1, offset: .8 }, { transform: 'translateY(-20px)', opacity: 0 }], 2100, IMP + 220, 'cubic-bezier(.16,1,.3,1)');

    this.shake(shake, 40, 420, IMP);
    this.shake(shake, 12, 220, IMP + 420);
  }

  /* ══ 600,001 74번 알림 — 참격 (2.6s) ══ */
  fx_slash(fx, shake) {
    const dim = this.mk(fx, 'inset:0;background:rgba(2,2,6,.42);opacity:0;');
    this.a(dim, [{ opacity: 0 }, { opacity: 1, offset: .1 }, { opacity: 1, offset: .84 }, { opacity: 0 }], 2600);

    [[32, 220], [-32, 760]].forEach((v, i) => {
      const rot = v[0], ms = v[1];
      const sl = this.mk(fx, 'left:50%;top:50%;width:2900px;height:16px;background:linear-gradient(90deg,rgba(255,255,255,0),#fff 12%,#fff 88%,rgba(255,255,255,0));transform:translate(-50%,-50%) rotate(' + rot + 'deg) scaleX(0);transform-origin:50% 50%;');
      this.a(sl, [{ transform: 'translate(-50%,-50%) rotate(' + rot + 'deg) scaleX(0)', opacity: 1 }, { transform: 'translate(-50%,-50%) rotate(' + rot + 'deg) scaleX(1)', opacity: 1, offset: .1 }, { transform: 'translate(-50%,-50%) rotate(' + rot + 'deg) scaleX(1) scaleY(.2)', opacity: .9, offset: .3 }, { transform: 'translate(-50%,-50%) rotate(' + rot + 'deg) scaleX(1) scaleY(.05)', opacity: 0 }], 900, ms, 'cubic-bezier(.05,.9,.2,1)');
      const red = this.mk(fx, 'left:50%;top:50%;width:2900px;height:5px;background:#e63946;transform:translate(-50%,-50%) rotate(' + rot + 'deg) translateY(20px) scaleX(0);');
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

  /* ══ 70만 누나누나 — 심쿵 (3.2s) ══ */
  fx_nuna(fx) {
    const wash = this.mk(fx, 'inset:0;background:radial-gradient(70% 60% at 50% 50%,rgba(255,92,138,.4),rgba(60,6,24,.66));opacity:0;');
    this.a(wash, [{ opacity: 0 }, { opacity: 1, offset: .16 }, { opacity: 1, offset: .82 }, { opacity: 0 }], 3200);

    const heart = this.mk(fx, 'left:50%;top:460px;width:340px;height:340px;transform:translate(-50%,-50%) rotate(-45deg) scale(.2);opacity:0;');
    const sq = this.mk(heart, 'left:0;top:0;width:240px;height:240px;background:#ff5c8a;');
    const c1 = this.mk(heart, 'left:-120px;top:0;width:240px;height:240px;border-radius:50%;background:#ff5c8a;');
    const c2 = this.mk(heart, 'left:0;top:-120px;width:240px;height:240px;border-radius:50%;background:#ff5c8a;');
    this.a(heart, [{ transform: 'translate(-50%,-50%) rotate(-45deg) scale(.2)', opacity: 0 }, { transform: 'translate(-50%,-50%) rotate(-45deg) scale(1)', opacity: 1, offset: .12 }, { transform: 'translate(-50%,-50%) rotate(-45deg) scale(1)', opacity: 1, offset: .84 }, { transform: 'translate(-50%,-50%) rotate(-45deg) scale(1.1)', opacity: 0 }], 3100, 100, 'cubic-bezier(.16,1,.3,1)');

    // 심장 리듬 (쿵-쿵, 쉬고)
    const beats = [420, 1180, 1940, 2560];
    beats.forEach((ms, i) => {
      const inner = heart;
      inner.animate([
        { transform: 'translate(-50%,-50%) rotate(-45deg) scale(1)' },
        { transform: 'translate(-50%,-50%) rotate(-45deg) scale(' + (1.14 + i * .03) + ')', offset: .16 },
        { transform: 'translate(-50%,-50%) rotate(-45deg) scale(1.02)', offset: .34 },
        { transform: 'translate(-50%,-50%) rotate(-45deg) scale(' + (1.2 + i * .04) + ')', offset: .52 },
        { transform: 'translate(-50%,-50%) rotate(-45deg) scale(1)', offset: 1 },
      ], { duration: 620 / this.S, delay: ms / this.S, easing: 'cubic-bezier(.3,0,.4,1)', composite: 'replace' });
      const ring = this.mk(fx, 'left:50%;top:460px;width:420px;height:420px;border-radius:50%;border:5px solid rgba(255,180,205,.75);transform:translate(-50%,-50%) scale(.6);');
      this.a(ring, [{ transform: 'translate(-50%,-50%) scale(.6)', opacity: .9 }, { transform: 'translate(-50%,-50%) scale(2.4)', opacity: 0 }], 760, ms + 60, 'cubic-bezier(.15,.9,.3,1)');
      this.flash(fx, '#ff9ebd', .12, 260, ms + 40);
    });

    for (let i = 0; i < 16; i++) {
      const s = this.rnd(14, 26);
      const p = this.mk(fx, 'left:' + this.rnd(0, 1880).toFixed(0) + 'px;top:-40px;width:' + s.toFixed(0) + 'px;height:' + (s * .68).toFixed(0) + 'px;border-radius:100% 0 100% 0;background:' + ['#ffd0dd', '#ff5c8a', '#fff0f4'][i % 3] + ';');
      this.a(p, [{ transform: 'translateY(0) rotate(0)', opacity: 0 }, { opacity: .9, offset: .12 }, { transform: 'translateY(1180px) translateX(' + this.rnd(-200, 200).toFixed(0) + 'px) rotate(' + this.rnd(-360, 360).toFixed(0) + 'deg)', opacity: 0 }], this.rnd(2000, 2800), this.rnd(0, 1400), 'cubic-bezier(.4,0,.6,1)');
    }
    const t = this.txt(fx, '누나누나', "font-family:'IBM Plex Sans KR',sans-serif;font-weight:600;font-size:104px;color:#fff;letter-spacing:.24em;", 790);
    this.a(t.w, [{ transform: 'translateY(26px)', opacity: 0 }, { transform: 'translateY(0)', opacity: 1, offset: .2 }, { transform: 'translateY(0)', opacity: 1, offset: .82 }, { transform: 'translateY(-16px)', opacity: 0 }], 3000, 300, 'cubic-bezier(.16,1,.3,1)');
  }

  /* ══ 80만 클럽음악 — 클럽 개장 (3.4s) ══ */
  fx_club(fx, shake) {
    const cols = ['#ff2bd0', '#7a5cff', '#22e6ff', '#59ff9e', '#ffd24a'];
    const dark = this.mk(fx, 'inset:0;background:rgba(3,2,10,.66);opacity:0;');
    this.a(dark, [{ opacity: 0 }, { opacity: 1, offset: .08 }, { opacity: 1, offset: .86 }, { opacity: 0 }], 3400);

    for (let i = 0; i < 8; i++) {
      const c = cols[i % 5], base = (i - 3.5) * 15;
      const l = this.mk(fx, 'left:50%;top:-40px;width:190px;height:1300px;transform-origin:50% 0%;clip-path:polygon(46% 0,54% 0,100% 100%,0 100%);background:linear-gradient(to bottom,' + c + ',rgba(0,0,0,0));mix-blend-mode:screen;opacity:0;');
      this.a(l, [{ opacity: 0, transform: 'translateX(-50%) rotate(' + (base - 20) + 'deg)' }, { opacity: .8, offset: .08 }, { opacity: .8, offset: .88 }, { opacity: 0, transform: 'translateX(-50%) rotate(' + (base + 20) + 'deg)' }], 3300, i * 40);
      l.animate([{ transform: 'translateX(-50%) rotate(' + (base - 16) + 'deg)' }, { transform: 'translateX(-50%) rotate(' + (base + 16) + 'deg)' }, { transform: 'translateX(-50%) rotate(' + (base - 16) + 'deg)' }], { duration: 1500 / this.S, iterations: 3, easing: 'ease-in-out', composite: 'replace' });
    }

    for (let i = 0; i < 26; i++) {
      const c = cols[i % 5];
      const b = this.mk(fx, 'left:' + (i * 74 + 12) + 'px;bottom:0;width:56px;height:' + this.rnd(90, 300).toFixed(0) + 'px;background:linear-gradient(to top,' + c + ',rgba(255,255,255,.85));transform-origin:50% 100%;transform:scaleY(0);');
      this.a(b, [{ transform: 'scaleY(0)', opacity: 0 }, { transform: 'scaleY(1)', opacity: .95, offset: .06 }, { transform: 'scaleY(1)', opacity: .95, offset: .9 }, { transform: 'scaleY(0)', opacity: 0 }], 3300, 60);
      b.animate([{ transform: 'scaleY(.3)' }, { transform: 'scaleY(1.5)' }, { transform: 'scaleY(.5)' }], { duration: this.rnd(260, 520) / this.S, iterations: 14, direction: 'alternate', easing: 'ease-in-out', delay: this.rnd(0, 300) / this.S, composite: 'replace' });
    }

    for (let k = 0; k < 7; k++) {
      const ms = 160 + k * 469;
      this.a(fx, [{ transform: 'scale(1.02)' }, { transform: 'scale(1)' }], 160, ms, 'cubic-bezier(.2,.9,.3,1)');
      if (k % 2 === 0) this.flash(fx, '#ffffff', .2, 70, ms);
      this.shake(shake, 8, 130, ms);
    }
    const t = this.txt(fx, 'CLUB OPEN', "font-family:'Anton',sans-serif;font-size:150px;letter-spacing:.1em;color:#fff;", 420);
    this.a(t.w, [{ transform: 'scale(1.25)', opacity: 0 }, { transform: 'scale(1)', opacity: 1, offset: .1 }, { transform: 'scale(1)', opacity: 1, offset: .84 }, { transform: 'scale(1.05)', opacity: 0 }], 3300, 200, 'cubic-bezier(.16,1,.3,1)');
  }

  /* ══ 100만 VIP (4.6s) ══ */
  fx_vip(fx) {
    const GOLD = '#c9a227';
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
    tx.style.cssText = "font-family:'Cormorant Garamond',serif;font-weight:300;font-size:230px;line-height:1;background-image:linear-gradient(102deg,#7d6218 0%,#c9a227 28%,#f7ecc4 47%,#ffffff 50%,#f7ecc4 53%,#c9a227 72%,#7d6218 100%);background-size:320% 100%;background-position:-40% 0;-webkit-background-clip:text;background-clip:text;color:transparent;";
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
    this.a(t.d, [{ letterSpacing: '.6em', opacity: 0 }, { letterSpacing: '.32em', opacity: 1, offset: .32 }, { letterSpacing: '.3em', opacity: 1, offset: .82 }, { letterSpacing: '.3em', opacity: 0 }], 4600, 1400, 'cubic-bezier(.16,1,.3,1)');
  }

  /* ══ 300만 MVP — 대관식 (7.5s) ══ */
  fx_mvp(fx, shake) {
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
    const burst = () => {
      if (!alive || !cv.parentNode) return;
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
      if (!cv.parentNode) return;
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
