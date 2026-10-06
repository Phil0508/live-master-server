/* 🎬 방송 시작 전 · 끝 화면 — screen 조각(mode off|start|end · title · start_at · names · snap). 옛 renderStageScreen 그대로.
   - 캔버스 전체를 **불투명**하게 덮는다(대표님 09-30 "반투명한 거 없애줘"). 0.8초에 걸쳐 나타나고 사라진다.
   - 덮는 동안 stage.setMode('stage', true) — 위젯판 · 게임판은 내려간다(옛 body.stage-on).
     이 묶음의 칸(계좌 · 전광판 · 모금함 · 목표 달성)은 css/basics2.css 가 내린다. 후원 알림 · 시그니처 · 계좌 영상 · 노래방은 남는다
     (기다리는 동안 들어온 후원도 알림은 떠야 하고, 영상은 기다리는 동안 틀어 두는 것이다).
   🌸 시작 화면 — 엔젤 오락실 그림(vendor/stage/start_bg.jpg, 그림 속에 '곧 방송이 시작됩니다' 상자가 있다).
     그림 아래 알약에 카운트다운(서버 시계). 0 이 되면 '곧 시작해요!'. 제목을 적었으면 알약 윗줄이 제목.
     그림은 WebGL 로 가장자리(리본)만 일렁이고 하트 보석이 둥실(옛 StageArt) — WebGL 을 못 쓰면 그림만 가만히.
     ⚠️ 옛 시작 화면의 '곧 시작합니다 · 오늘 함께할 멤버' 카드는 그림이 대신하면서 비웠다 — names 는 화면에 안 쓴다(옛 것과 같다).
   🌸 끝 화면 — 엔젤 오락실 B: 분홍 물방울 바탕 · '오늘도 고마워요' · 흰 카드(오늘의 1등 · 한 방 최고 + 후원해 주신 분 사탕 칩 8개).
     방송 중이면 **지금 조각들**(players · tallies · look)로 그리고, 방송을 끝낸 뒤면 끝내는 순간 얼린 screen.snap 으로 그린다.
     ⚠️ 글씨는 안전지대(115~954) 안 — 폰에서는 그 아래가 채팅에 가린다. 아래쪽엔 하트 장식만. */
import { serverNow, startClock } from './clock.js';

const SNAP_DONORS = 8;

const HEART = '<svg viewBox="0 0 24 24"><path d="M12 21s-7.5-4.6-9.5-9.4C1.2 8.4 3.3 5 6.6 5c2 0 3.4 1.1 4.4 2.6C12 6.1 13.4 5 15.4 5c3.3 0 5.4 3.4 4.1 6.6C19.5 16.4 12 21 12 21z" fill="%C"/></svg>';
const SE_ICON = {
    trophy: '<svg viewBox="0 0 24 24" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
          + '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0V4z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/></g></svg>',
    bolt: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round"/></svg>',
};

function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
}
const won = n => Number(n || 0).toLocaleString() + '원';

function artHtml() {
    const sparks = [['14%', '9%', 43, 2.4, 0], ['82%', '11%', 54, 3.1, 0.8], ['9%', '40%', 38, 2.8, 1.4], ['90%', '44%', 49, 2.2, 0.3],
                    ['20%', '64%', 32, 3.4, 2.0], ['78%', '66%', 43, 2.6, 1.1], ['50%', '6%', 32, 2.9, 1.7], ['66%', '30%', 32, 3.2, 0.5]]
        .map(([x, y, s, d, dl]) => '<i class="sa-spark" style="--x:' + x + ';--y:' + y + ';--s:' + s + 'px;--d:' + d + 's;--dl:-' + dl + 's"></i>').join('');
    const hearts = [['12%', 65, 10, 0], ['30%', 43, 12, 4], ['55%', 54, 11, 7], ['72%', 65, 9, 2], ['88%', 43, 13, 5.5]]
        .map(([x, s, d, dl]) => '<i class="sa-heart" style="--x:' + x + ';--s:' + s + 'px;--d:' + d + 's;--dl:-' + dl + 's"></i>').join('');
    return '<div class="ss-art"><canvas class="sa-photo"></canvas><div class="sa-halo"></div><div class="sa-sweep"></div>'
        + sparks + hearts + '<div class="sa-glow"></div>'
        + '<div class="sa-pill"><span class="sa-lab">방송 시작까지</span><span class="sa-num"></span></div></div>';
}

function endBgHtml() {
    const hearts = [['11%', 1250, 92, 2.6, '#ffb3d3'], ['74%', 1390, 128, 3.2, '#ffc7df'], ['41%', 1640, 76, 2.9, '#d9c8ff'],
                    ['84%', 1060, 60, 3.6, '#ffd3e6'], ['6%', 1520, 58, 3.4, '#e6dbff']]
        .map(([x, y, s, d, c]) => '<i class="se-heart" style="--x:' + x + ';--y:' + y + 'px;--s:' + s + 'px;--d:' + d + 's">' + HEART.replace('%C', c) + '</i>').join('');
    return '<div class="ss-end-bg" aria-hidden="true"><div class="se-band"></div>' + hearts + '</div>';
}

/* 🌸 시작 화면 그림을 살아 있게 — 그림 한 장을 매 순간 살짝 일그러뜨려 다시 그린다(옛 StageArt 그대로, 대표님 09-22 확정)
   · 가장자리(리본)만 크게 물결 — 제목 · 날개 · 문구 상자는 가림막(still)으로 꼼짝 못 하게(글씨가 안 깨진다)
   · 하트 보석 자리만 둥실 · 그림 속 제일 밝은 점만 부드럽게 깜빡 · 전체는 아주 천천히 줌. 떠 있을 때만 돈다(초당 30장).
   ⚠️ WebGL 을 못 쓰면 조용히 빠진다 — 그림은 .ss-art 배경으로 가만히 깔려 있다. */
function makeArt(cv) {
    const A = {
        on: false, gl: null, u: null, raf: 0, last: 0, t0: 0, broken: false, ready: false, K: 0.75,
        VS: 'attribute vec2 a;varying vec2 v;void main(){v=vec2(a.x*.5+.5,.5-a.y*.5);gl_Position=vec4(a,0.,1.);}',
        FS: [
            'precision mediump float;',
            'uniform sampler2D img; uniform float T; varying vec2 v;',
            'float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}',
            'float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(h(i),h(i+vec2(1.,0.)),f.x),mix(h(i+vec2(0.,1.)),h(i+vec2(1.,1.)),f.x),f.y);}',
            'float fbm(vec2 p){float s=0.,a=.5;for(int i=0;i<4;i++){s+=a*n(p);p=p*2.1+3.7;a*=.5;}return s;}',
            'float box(vec2 p,vec4 r,float f){vec2 a=smoothstep(r.xy-f,r.xy+f,p)*(1.-smoothstep(r.zw-f,r.zw+f,p));return a.x*a.y;}',
            'float gem(vec2 p,vec2 c,float r){return 1.-smoothstep(r*.55,r,length((p-c)*vec2(.56,1.)));}',
            'void main(){',
            ' vec2 p=v; float m;',
            ' float z=1.+.05*(.5-.5*cos(T*.26));',
            ' p=vec2(.5,.45)+(p-vec2(.5,.45))/z;',
            ' float still=max(box(p,vec4(.13,.09,.87,.67),.035),box(p,vec4(.19,.69,.81,.87),.03));',
            ' vec2 q=p*vec2(2.6,4.2);',
            ' vec2 d=vec2(fbm(q+vec2(T*.24,T*.09))-.5,fbm(q+vec2(5.2-T*.17,1.3+T*.2))-.5);',
            ' p+=d*.045*(1.-still);',
            ' m=gem(p,vec2(.925,.227),.075); p+=vec2(cos(T*.9)*.006,sin(T*1.25)*.014)*m;',
            ' m=gem(p,vec2(.11,.805),.075);  p+=vec2(cos(T*.8+1.)*.006,sin(T*1.05+1.7)*.014)*m;',
            ' m=gem(p,vec2(.86,.868),.08);   p+=vec2(cos(T*.85+2.)*.006,sin(T*1.15+3.1)*.014)*m;',
            ' m=gem(p,vec2(.14,.172),.055);  p+=vec2(cos(T*1.1+.5)*.005,sin(T*.95+4.4)*.012)*m;',
            ' m=gem(p,vec2(.06,.315),.05);   p+=vec2(cos(T*1.2+3.)*.004,sin(T*1.35+2.2)*.011)*m;',
            ' vec4 c=texture2D(img,clamp(p,.001,.999));',
            ' float l=dot(c.rgb,vec3(.299,.587,.114));',
            ' c.rgb+=smoothstep(.95,.995,l)*smoothstep(.35,.85,n(p*vec2(38.,68.)+vec2(T*.35,-T*.25)))*.34;',
            ' gl_FragColor=vec4(c.rgb,1.);',
            '}'].join('\n'),
        set(on) {
            on = !!on && !this.broken;
            if (on === this.on) return;
            this.on = on;
            if (on) { if (!this.gl && !this.init()) { this.on = false; return; } this.t0 = performance.now(); this.tick(); }
            else if (this.raf) { cancelAnimationFrame(this.raf); this.raf = 0; }
        },
        init() {
            try {
                const gl = cv.getContext('webgl', { antialias: false });   // 투명 — 그림이 준비되기 전엔 뒤 배경 그림이 보인다
                if (!gl) { this.broken = true; return false; }
                const sh = (ty, src) => { const x = gl.createShader(ty); gl.shaderSource(x, src); gl.compileShader(x);
                    if (!gl.getShaderParameter(x, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(x)); return x; };
                const pr = gl.createProgram();
                gl.attachShader(pr, sh(gl.VERTEX_SHADER, this.VS)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, this.FS));
                gl.linkProgram(pr);
                if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(pr));
                gl.useProgram(pr);
                gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
                gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
                const loc = gl.getAttribLocation(pr, 'a'); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
                this.u = { T: gl.getUniformLocation(pr, 'T') };
                this.gl = gl;
                const img = new Image();
                img.onload = () => {
                    const tex = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, tex);
                    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, img);
                    [gl.TEXTURE_MIN_FILTER, gl.TEXTURE_MAG_FILTER].forEach(k => gl.texParameteri(gl.TEXTURE_2D, k, gl.LINEAR));
                    [gl.TEXTURE_WRAP_S, gl.TEXTURE_WRAP_T].forEach(k => gl.texParameteri(gl.TEXTURE_2D, k, gl.CLAMP_TO_EDGE));
                    this.ready = true;
                };
                img.onerror = () => { this.broken = true; this.set(false); };
                img.src = '/vendor/stage/start_bg.jpg';
                return true;
            } catch (e) {
                console.warn('시작 화면 움직임(WebGL) 못 켬 — 그림만 가만히:', e);
                this.broken = true;
                return false;
            }
        },
        tick() {
            this.raf = requestAnimationFrame(now => {
                this.raf = 0;
                if (!this.on) return;
                if (this.ready && now - this.last >= 33) {
                    this.last = now;
                    const w = Math.round(cv.offsetWidth * this.K), h = Math.round(cv.offsetHeight * this.K);
                    if (w && (cv.width !== w || cv.height !== h)) { cv.width = w; cv.height = h; this.gl.viewport(0, 0, w, h); }
                    this.gl.uniform1f(this.u.T, ((now - this.t0) / 1000) % 3600);
                    this.gl.drawArrays(this.gl.TRIANGLE_STRIP, 0, 4);
                }
                this.tick();
            });
        },
    };
    return A;
}

/* 방송 중 '오늘의 기록' — 서버 snapshot()(extras.py)과 같은 모양 · 같은 규칙으로 지금 조각에서 만든다 */
function liveSnap(lm) {
    const look = lm.get('look') || {};
    const withAnon = !!look.donor_anon, showAmt = look.donor_amount !== false;
    const rows = ((lm.get('players') || {}).list || []).slice()
        .sort((a, b) => (Number(b.contribution) || 0) - (Number(a.contribution) || 0));
    const members = rows.slice(0, 3).map(r => ({ name: r.name, score: r.score, contribution: r.contribution }));
    const t = lm.get('tallies') || {};
    const donors = Object.entries(t.donors || {})
        .map(([k, v]) => ({ key: k, name: (v && v.name) || k, total: Number((v && v.total) || 0) }))
        .filter(r => r.total > 0 && (withAnon || r.key !== '익명'));
    donors.sort((a, b) => (b.total - a.total) || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    const b = t.best;
    return {
        members,
        donors: donors.slice(0, SNAP_DONORS).map(r => ({ name: r.name, total: showAmt ? r.total : null })),
        donor_count: donors.length, show_amount: showAmt,
        best: (b && b.amount) ? { name: b.name, amount: b.amount, member: b.member || '' } : null,
    };
}

function endHtml(ss, snap) {
    const sub = ss.title ? '<div class="se-sub">' + esc(ss.title) + '</div>' : '';
    const top = (snap.members || [])[0];
    const best = snap.best;
    const tiles = [];
    if (top && (Number(top.contribution) > 0 || Number(top.score) > 0)) {
        tiles.push('<div class="se-tile se-top"><div class="se-lab">' + SE_ICON.trophy + '오늘의 1등</div><div class="se-big">' + esc(top.name) + '</div>'
            + '<div class="se-small">기여도 ' + Number(top.contribution || 0).toLocaleString() + '</div></div>');
    }
    if (best && best.amount > 0) {
        tiles.push('<div class="se-tile se-best"><div class="se-lab">' + SE_ICON.bolt + '한 방 최고</div><div class="se-big">' + esc(best.name) + '</div>'
            + '<div class="se-small">' + won(best.amount) + (best.member ? ' → ' + esc(best.member) : '') + '</div></div>');
    }
    const donors = snap.donors || [];
    const more = Math.max(0, (snap.donor_count || 0) - donors.length);
    const inner = (tiles.length ? '<div class="se-duo' + (tiles.length === 1 ? ' one' : '') + '">' + tiles.join('') + '</div>' : '')
        // ⚠️ '후원해 주신 분' 제목 줄은 칩 아래 인사 줄과 합쳤다 — 다 차면 카드 아래끝이 채팅선(954)을 넘었다
        + (donors.length ? '<div class="se-chips' + (snap.show_amount === false ? ' names' : '') + '">'
            + donors.map(r => '<div class="se-chip"><b>' + esc(r.name) + '</b>'
                + (r.total != null ? '<span>' + Number(r.total).toLocaleString() + '</span>' : '') + '</div>').join('') + '</div>'
            + '<div class="se-more">' + (more ? '외 ' + more + '분까지, ' : '') + '후원해 주신 분들 모두 고마워요 ♥</div>' : '');
    return '<div class="se-pill">엔젤 오락실 · 오늘 방송 끝</div>'
        + '<div class="se-title">오늘도 고마워요</div>' + sub
        // 기록이 하나도 없으면(방송 전 · 후원 0) 빈 카드 대신 인사 한 줄
        + '<div class="se-card">' + (inner || '<div class="se-lab2">다음 방송에서 또 만나요 ♥</div>') + '</div>';
}

export function mount(root, lm, opts) {
    startClock(lm);
    root.innerHTML = '<div class="ss-root" data-mode="off" aria-hidden="true">' + artHtml() + endBgHtml() + '<div class="se-wrap"></div></div>';
    const box = root.firstElementChild;
    const card = root.querySelector('.se-wrap');
    const pill = root.querySelector('.sa-pill');
    const lab = root.querySelector('.sa-lab');
    const num = root.querySelector('.sa-num');
    const art = makeArt(root.querySelector('.sa-photo'));
    let html = null, timer = null, startAt = 0;

    function clock() {
        if (!startAt) return;
        const left = startAt - serverNow();
        if (left <= 0) {
            if (!num.classList.contains('soon')) { num.classList.add('soon'); num.textContent = '곧 시작해요!'; }
            return;
        }
        const s = Math.ceil(left / 1000), p2 = x => String(x).padStart(2, '0');
        const txt = s >= 3600 ? Math.floor(s / 3600) + ':' + p2(Math.floor(s % 3600 / 60)) + ':' + p2(s % 60)
                              : p2(Math.floor(s / 60)) + ':' + p2(s % 60);
        num.classList.remove('soon');
        if (num.textContent !== txt) num.textContent = txt;
    }

    function render() {
        const ss = lm.get('screen') || {};
        const mode = (ss.mode === 'start' || ss.mode === 'end') ? ss.mode : 'off';
        box.classList.toggle('show', mode !== 'off');
        box.setAttribute('data-mode', mode);
        opts.stage.setMode('stage', mode !== 'off');           // 위젯판 · 게임판을 내린다(옛 body.stage-on)
        startAt = mode === 'start' ? (Number(ss.start_at) || 0) : 0;

        // 🌸 시작 — 알약에 카운트다운(없으면 제목 한 줄만). 둘 다 없으면 알약을 안 띄운다.
        const hasCount = mode === 'start' && !!startAt;
        const hasTitle = mode === 'start' && !!ss.title;
        pill.classList.toggle('on', hasCount || hasTitle);
        const labTxt = ss.title ? String(ss.title) : '방송 시작까지';
        if (lab.textContent !== labTxt) lab.textContent = labTxt;
        if (!hasCount && num.textContent) { num.textContent = ''; num.classList.remove('soon'); }
        try { art.set(mode === 'start'); } catch (e) {}

        let h = '';
        if (mode === 'end') {
            const live = !!(lm.get('session') || {}).live;
            h = endHtml(ss, live ? liveSnap(lm) : (ss.snap || {}));
        }
        if (h !== html) { card.innerHTML = h; html = h; }
        if (startAt) {
            clock();
            if (!timer) timer = setInterval(clock, 250);
        } else if (timer) { clearInterval(timer); timer = null; }
    }

    const safe = () => { try { render(); } catch (e) { console.error('[시작/끝 화면] 그리기 실패 — 방송은 계속됩니다:', e); } };
    ['screen', 'session', 'players', 'tallies', 'look'].forEach(k => lm.on(k, safe));
}
