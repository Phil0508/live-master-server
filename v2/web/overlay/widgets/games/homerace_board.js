/* 🏃 퇴근빵 · 🔥 지옥탈출 공용 판 — 옛 overlay.html renderHomeRace · GOAL 줄 순환 · HellFire 를 옮겼다.
   옛 것은 판 하나(#home-race-container)를 둘이 나눠 썼다(.hell 이면 지옥 옷). v2 는 칸이 둘(homerace · hell)이고 생김새는 이 파일 하나.

   - 퇴근빵(kind 'home'): show.stage == 'home_race' 이고 점수판 선수가 있을 때. 진행 = 점수(score) / 목표(home.goals[이름], 점).
     오른쪽 배지 = 목표(만 단위 짧게), 아래 GOAL 줄 = 5초마다 다음 사람의 '남은 점수'(다 채우면 '퇴근 완료 🎉').
   - 지옥탈출(kind 'hell'): show.stage == 'hell' 이고 hell.on. 명단 = 목표 큰 순(= 시작 순간 1등부터 — 서버가 그 순서로 적었다).
     진행 = 시작 뒤 받은 점수(score − base) / 목표(점 = 만원) — 숫자에 '만'. 다 채우면 배지 '탈출!'(초록), 모두 채우면 제목 '😇 전원 탈출!'.
     GOAL 줄은 없다(판을 짧게). 판 뒤로 진짜 불(WebGL) · 용암 균열 · 불티 · 열기 — 그래픽카드가 없으면 불만 빠진다.
   - 막대는 줄을 한 번만 만들고 값만 바꾼다(통째로 갈면 0.8초 차오르기가 끊긴다).
   - 판이 무대에 있으면 stage 모드(game-home / game-hell) — 점수판(ranking)이 이 자리를 비켜 준다(옛 rankHiddenBy.race). */
import { formatNum } from '../../util.js';
import { makeFader, coverOn } from './dice_kit.js';

// 금액을 '만' 단위 짧은 배지로(260000 → 26만, 아니면 콤마) — 옛 manLabel
function manLabel(v) {
    v = parseInt(v, 10) || 0;
    if (v >= 10000 && v % 10000 === 0) return (v / 10000) + '만';
    if (v >= 10000) return (v / 10000).toFixed(1).replace(/\.0$/, '') + '만';
    return formatNum(v);
}

const EMBERS = [[8, 6, 3.4, -0.0, 14], [18, 4, 2.8, -1.1, -10], [29, 5, 3.9, -0.6, 18], [41, 7, 3.1, -2.0, -16], [50, 4, 2.6, -0.3, 10],
                [58, 6, 3.6, -1.6, -12], [67, 5, 3.0, -0.9, 16], [76, 4, 3.8, -2.4, -8], [85, 6, 2.9, -0.4, 12], [93, 5, 3.3, -1.8, -14]];

/* 🔥 지옥 불 — 그래픽카드(WebGL)가 그린다. 판 아래 · 양옆 가장자리가 불씨. 반 해상도 · 초당 30장 · 지옥탈출 중에만 돈다(옛 HellFire 그대로). */
function makeHellFire(cv) {
    const F = {
        on: false, gl: null, u: null, raf: 0, last: 0, t0: 0, w: 0, h: 0, broken: false,
        K: 0.5, PADX: 34, PADB: 8,
        VS: 'attribute vec2 a;void main(){gl_Position=vec4(a,0.,1.);}',
        FS: [
            'precision mediump float;',
            'uniform vec2 R;uniform float T;uniform vec4 B;uniform vec3 F;',
            'float h(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}',
            'float n(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);',
            ' return mix(mix(h(i),h(i+vec2(1.,0.)),f.x),mix(h(i+vec2(0.,1.)),h(i+vec2(1.,1.)),f.x),f.y);}',
            'float fbm(vec2 p){float v=0.,a=.5;for(int i=0;i<5;i++){v+=a*n(p);p=p*2.03+vec2(1.7,9.2);a*=.5;}return v;}',
            'vec3 ramp(float f){vec3 c=mix(vec3(0.),vec3(.42,.02,0.),smoothstep(0.,.22,f));',
            ' c=mix(c,vec3(.92,.16,.02),smoothstep(.18,.48,f));c=mix(c,vec3(1.,.5,.06),smoothstep(.42,.72,f));',
            ' return mix(c,vec3(1.,.9,.6),smoothstep(.8,1.,f));}',
            'void main(){',
            ' vec2 p=gl_FragCoord.xy; vec2 q=p/F.z;',
            ' float t=T;',
            ' float tb=fbm(q*vec2(1.,.62)-vec2(0.,t*1.35))*.62+fbm(q*vec2(2.1,1.3)-vec2(t*.25,t*2.6))*.38;',
            ' float hb=(p.y-B.y)/F.x; if(hb<0.) hb=-hb*4.;',
            ' float xin=smoothstep(B.x-F.y*1.2,B.x+F.y*.3,p.x)*(1.-smoothstep(B.z-F.y*.3,B.z+F.y*1.2,p.x));',
            ' float fb=(.9-hb-(tb-.5)*1.7)*xin;',
            ' float ds=min(abs(p.x-B.x),abs(p.x-B.z))/F.y;',
            ' float up=clamp((p.y-B.y)/(B.w-B.y),0.,1.);',
            ' float fs=(1.-ds-(tb-.5)*1.4)*(1.-up*.8)*step(B.y-F.x*.5,p.y);',
            ' float f=clamp(max(fb,fs*.85),0.,1.); f=pow(f,1.3);',
            ' f*=1.-smoothstep(B.w-F.y*.9,B.w,p.y);',
            ' float al=smoothstep(.06,.4,f)*.82;',
            ' gl_FragColor=vec4(ramp(f)*al,al);',
            '}'].join('\n'),
        set(on) {
            on = !!on && !this.broken;
            if (on === this.on) return;
            this.on = on;
            if (on) { if (!this.gl && !this.init()) { this.on = false; return; } this.t0 = performance.now(); this.tick(); }
            else { if (this.raf) cancelAnimationFrame(this.raf); this.raf = 0; if (this.gl) this.gl.clear(this.gl.COLOR_BUFFER_BIT); }
        },
        init() {
            try {
                const gl = cv.getContext('webgl', { premultipliedAlpha: true, alpha: true, antialias: false }) || cv.getContext('experimental-webgl');
                if (!gl) { this.broken = true; return false; }
                const sh = (type, src) => { const x = gl.createShader(type); gl.shaderSource(x, src); gl.compileShader(x);
                    if (!gl.getShaderParameter(x, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(x)); return x; };
                const pr = gl.createProgram();
                gl.attachShader(pr, sh(gl.VERTEX_SHADER, this.VS));
                gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, this.FS));
                gl.linkProgram(pr);
                if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(pr));
                gl.useProgram(pr);
                const buf = gl.createBuffer();
                gl.bindBuffer(gl.ARRAY_BUFFER, buf);
                gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
                const loc = gl.getAttribLocation(pr, 'a');
                gl.enableVertexAttribArray(loc);
                gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
                gl.clearColor(0, 0, 0, 0);
                this.u = { R: gl.getUniformLocation(pr, 'R'), T: gl.getUniformLocation(pr, 'T'),
                           B: gl.getUniformLocation(pr, 'B'), F: gl.getUniformLocation(pr, 'F') };
                this.gl = gl;
                return true;
            } catch (e) {
                console.warn('지옥불(WebGL) 못 켬 — 불만 빼고 나머지는 그대로:', e);
                this.broken = true;
                return false;
            }
        },
        fit() {
            // offsetWidth 는 배율을 뺀 제 크기 — 편집기에서 판을 키워도 계산이 안 틀어진다
            const box = cv.parentElement;
            const bw = box.offsetWidth, bh = box.offsetHeight;
            if (!bw || !bh) return false;
            const k = this.K;
            const w = Math.round((bw + this.PADX * 2) * k), h = Math.round((bh + this.PADB) * k);
            if (w !== this.w || h !== this.h) { this.w = cv.width = w; this.h = cv.height = h; this.gl.viewport(0, 0, w, h); }
            this.gl.uniform4f(this.u.B, this.PADX * k, this.PADB * k, (this.PADX + bw) * k, (this.PADB + bh) * k);
            this.gl.uniform3f(this.u.F, 44 * k, 28 * k, 40 * k);   // 아래 불 높이 44 · 옆 불 두께 28 · 무늬 크기 40
            this.gl.uniform2f(this.u.R, w, h);
            return true;
        },
        tick() {
            this.raf = requestAnimationFrame(now => {
                this.raf = 0;
                if (!this.on) return;
                if (now - this.last >= 33) {
                    this.last = now;
                    if (this.fit()) {
                        this.gl.uniform1f(this.u.T, ((now - this.t0) / 1000) % 600);
                        this.gl.drawArrays(this.gl.TRIANGLE_STRIP, 0, 4);
                    }
                }
                this.tick();
            });
        },
    };
    return F;
}

export function mountRace(root, lm, opts, kind) {
    const hellKind = kind === 'hell';
    const stage = opts.stage;
    const embers = EMBERS.map(e => '<b style="--x:' + e[0] + '%;--sz:' + e[1] + 'px;--d:' + e[2] + 's;--dl:' + e[3] + 's;--dx:' + e[4] + 'px"></b>').join('');
    root.innerHTML = '<div class="gb-wrap hr-wrap' + (hellKind ? ' hell' : '') + '"><div class="home-race-box">'
        + (hellKind ? '<div class="hf-glow" aria-hidden="true"></div><div class="hell-fx" aria-hidden="true"><div class="hf-cracks"></div>'
                      + '<canvas class="hf-fire"></canvas><div class="hf-embers">' + embers + '</div></div>' : '')
        + '<div class="home-race-title">' + (hellKind ? '🔥 지옥탈출' : '🏃 퇴근빵') + '</div>'
        + '<div class="home-race-rows"></div>'
        + (hellKind ? '' : '<div class="home-race-goal-line" style="display:none;">'
            + '<span class="home-race-goal-badge">GOAL</span><span class="hr-goal-name">-</span>'
            + '<span class="hr-goal-label">남은 점수</span><span class="hr-goal-remain">-</span>'
            + '<span class="hr-goal-target">목표 -</span><span class="hr-goal-count">-</span></div>')
        + '</div></div>';
    const wrap = root.firstElementChild;
    const titleEl = root.querySelector('.home-race-title');
    const rowsEl = root.querySelector('.home-race-rows');
    const goalLine = root.querySelector('.home-race-goal-line');
    const fire = hellKind ? makeHellFire(root.querySelector('.hf-fire')) : null;
    const fade = makeFader(wrap, stage);
    const modeName = hellKind ? 'game-hell' : 'game-home';

    let rowNames = null;
    let cycle = [], cycleIdx = 0, cycleTimer = null;

    function paintGoal(animate) {
        if (!goalLine) return;
        if (!cycle.length) { goalLine.style.display = 'none'; return; }
        if (cycleIdx >= cycle.length) cycleIdx = 0;
        const p = cycle[cycleIdx];
        const remain = Math.max(0, (p.goal || 0) - (p.cur || 0));
        goalLine.style.display = 'flex';
        goalLine.querySelector('.hr-goal-name').textContent = p.name;
        // ⚠️ 여기 값은 '점'이다(만 원당 1점) — '원' 으로 적었다가 방송에서 잘못 안내된 적이 있다
        goalLine.querySelector('.hr-goal-remain').innerHTML = (p.goal > 0 && remain === 0) ? '퇴근 완료 🎉'
            : (formatNum(remain) + '<span class="hr-unit">점</span>');
        goalLine.querySelector('.hr-goal-target').textContent = '목표 ' + manLabel(p.goal) + '점';
        goalLine.querySelector('.hr-goal-count').textContent = (cycleIdx + 1) + '/' + cycle.length;
        if (animate) { goalLine.classList.remove('swap'); void goalLine.offsetWidth; goalLine.classList.add('swap'); }
    }
    function startCycle() {
        paintGoal(false);
        if (cycleTimer || !goalLine) return;
        cycleTimer = setInterval(() => {
            if (!cycle.length) return;
            cycleIdx = (cycleIdx + 1) % cycle.length;
            paintGoal(true);
        }, 5000);
    }
    function stopCycle() { if (cycleTimer) { clearInterval(cycleTimer); cycleTimer = null; } }

    function render() {
        const players = lm.get('players') || {};
        const list = Array.isArray(players.list) ? players.list : [];
        const st = (lm.get('show') || {}).stage;
        const hell = lm.get('hell') || {};
        const home = lm.get('home') || {};
        let bjs = list;
        let goals = {};
        if (hellKind) {
            const hg = hell.goals || {};
            // 시작 순간 등수 순(서버가 1등부터 적었다) — 목표가 같은 5등 아래도 그 순서(정렬은 안정적이다)
            const order = Object.keys(hg).sort((x, y) => (Number(hg[y]) || 0) - (Number(hg[x]) || 0));
            bjs = order.map(n => list.find(b => b.name === n)).filter(Boolean);
            goals = hg;
        } else {
            goals = home.goals || {};
        }
        const base = hell.base || {};
        const cur = b => hellKind ? Math.max(0, (Number(b.score) || 0) - (parseInt(base[b.name], 10) || 0)) : (Number(b.score) || 0);
        const onStage = (hellKind ? (st === 'hell' && !!hell.on) : st === 'home_race') && bjs.length > 0;
        stage.setMode(modeName, onStage);
        const visible = onStage && !coverOn(lm);
        fade(visible);
        if (fire) fire.set(visible);
        if (!onStage) { stopCycle(); return; }

        // 모두 채우면 '전원 탈출!' — 판정 · 벌칙은 없다
        const allOut = hellKind && bjs.every(b => { const g = parseInt(goals[b.name], 10) || 0; return g > 0 && cur(b) >= g; });
        const titleTxt = hellKind ? (allOut ? '😇 전원 탈출!' : '🔥 지옥탈출') : '🏃 퇴근빵';
        if (titleEl.textContent !== titleTxt) titleEl.textContent = titleTxt;

        const names = bjs.map(b => b.name).join('\n');
        if (rowNames !== names) {
            rowNames = names;
            rowsEl.innerHTML = bjs.map(() => '<div class="home-race-row"><div class="home-race-name"></div>'
                + '<div class="home-race-bar-bg"><div class="home-race-bar-fill"></div></div>'
                + '<div class="home-race-nums"><span class="cur"></span></div><div class="home-race-goal-tag"></div></div>').join('');
        }
        const rows = rowsEl.children;
        bjs.forEach((b, i) => {
            const row = rows[i];
            if (!row) return;
            const goal = parseInt(goals[b.name], 10) || 0;
            const c = cur(b);
            const pct = goal > 0 ? Math.min(100, (c / goal) * 100) : 0;
            const reached = goal > 0 && c >= goal;
            const nameEl = row.querySelector('.home-race-name');
            const fillEl = row.querySelector('.home-race-bar-fill');
            const curEl = row.querySelector('.home-race-nums .cur');
            const tagEl = row.querySelector('.home-race-goal-tag');
            if (nameEl.textContent !== b.name) nameEl.textContent = b.name;
            fillEl.style.width = pct + '%';
            fillEl.classList.toggle('goal-reached', reached);
            const curTxt = hellKind ? formatNum(c) + '만' : formatNum(c);      // 🔥 지옥탈출은 점 = 만원
            if (curEl.textContent !== curTxt) curEl.textContent = curTxt;
            const tagTxt = hellKind ? (reached ? '탈출!' : goal + '만') : manLabel(goal);
            if (tagEl.textContent !== tagTxt) tagEl.textContent = tagTxt;
            tagEl.classList.toggle('escaped', hellKind && reached);
        });
        cycle = bjs.map(b => ({ name: b.name, cur: cur(b), goal: parseInt(goals[b.name], 10) || 0 }));
        startCycle();
    }

    lm.on('players', render);
    lm.on('show', render);
    lm.on('screen', render);
    lm.on(hellKind ? 'hell' : 'home', render);
}
