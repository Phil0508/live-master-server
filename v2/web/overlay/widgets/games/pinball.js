/* 🎱 구슬 핀볼 — pinball 조각 {names, balls, picks, rule(first|last), map, skills, seed, round_id, running, started_at,
   result, winners}. 구슬이 못 · 레일에 튕기며 떨어져 먼저(또는 끝까지 남아) 도착한 순서로 순위가 난다.
   옛 overlay.html 의 pb* 코드(box2d · 맵 4개 · 카메라 · 슬로모션 · 밀어내기 · 결과 딱지)를 그대로 옮겼다.

   ⚠️ 물리는 여기(방송판)서 굴린다. 서버는 심판만 본다(v2/server/domain/pinball.py).
      ① 서버가 준 씨앗(seed)으로 **모든 난수를 뽑는다** — 같은 씨앗이면 어느 창이든 같은 경기
      ② 고정 걸음(10ms)으로만 물리를 민다 — 프레임이 흔들려도 · 슬로모션이 껴도 결과가 안 바뀐다
      ③ 결과는 lm.cmd('pinball.result', {round_id, result}) — 서버는 **지금 판의 첫 보고만** 받는다.
         ?monitor=1(미리보기)은 보내지 않는다(진짜 방송판이 보낸다).
   ⚠️ box2d · 맵 파일(/vendor/box2d/Box2D.js · /vendor/pinball-maps.js)을 못 읽으면 핀볼만 빠진다 — 방송은 계속된다.
      맵 파일이 없으면 우리 기본 코스로 굴린다.
   ⚠️ 늦게 붙은 창(굴러가는 중에 새로 연 창): 처음부터 굴리되, 서버 started_at 에서 지난 만큼은 그리지 않고 빨리 감는다
      (한 그림에 걸음 30개씩) — 같은 경기라 결국 같은 자리에 온다.
   보이기: 무대(show.stage)가 'pinball' 일 때만 · 시그니처가 도는 동안(hideInReaction) · 시작/끝 화면 동안은 숨는다. */
import { serverNow, loadScript, screenCovered, rng as pbRng, boom, esc } from './slot-roulette-kit.js';

const PB_W = 980, PB_H = 840;          // **화면** 크기(캔버스와 같아야 한다)
/* 🗺️ 우리 기본 코스 — 구역 한 벌(못밭→바람개비→레일)을 PB_SEGS 번 되풀이 */
const PB_SEG_H = 620, PB_SEGS = 3, PB_TOP = 140;
const PB_WORLD_OWN = PB_TOP + PB_SEG_H * PB_SEGS + 200;
const PB_WALL = 14, PB_GOAL_H = 54, PB_R = 15;
const PB_BALL_MAX = 800;                     // ⚠️ 서버 PINBALL_MAX 와 같아야 한다
const PB_SPAWN_BAND = PB_W - 320;
const PB_SPAWN_GAP = PB_R * 2 + 6;
const PB_SPAWN_ROWH = PB_R * 2 + 16;
const PB_SPAWN_PER = Math.max(1, Math.floor(PB_SPAWN_BAND / PB_SPAWN_GAP));
const PB_SPAWN_Y0 = 40;
/* 🧢 뚜껑은 제일 윗줄보다 위 — 800알이 여러 줄로 쌓여도 윗줄이 뚜껑 위에서 시작하지 않게 */
const PB_CEIL = PB_SPAWN_Y0 - (Math.ceil(PB_BALL_MAX / PB_SPAWN_PER) - 1) * PB_SPAWN_ROWH - 60;
const PB_NAME_MAX = 40;                // 구슬이 이보다 많으면 이름은 주인공만
const PB_BANNER_MAX = 8;               // 결과 딱지에 쓰는 이름 수
const PB_STEP = 10;                    // 물리 한 걸음(ms) — 고정이어야 결과가 같다
const PB_MAX_MS = 180000;              // 3분이 넘으면 강제로 끝낸다
const PB_STUCK_MS = 5000;              // 이만큼 거의 안 움직이면 흔든다
const PB_NOGAIN_PX = 4;
const PB_STALL_STEPS = 100 * 20;       // 아무도 못 나아간 채 20초면 그 자리 순위로 끝
const PB_SKILL_COOL = 100 * 4;         // 밀어내기 — 4초마다 굴려 보고
const PB_SKILL_RATE = 0.25;            // 그때 터질 확률
const PB_SKILL_CROWD = 30;             // 구슬이 많으면 확률을 나눈다
const PB_SKILL_R_M = 10;               // 밀리는 범위(미터)
const PB_SKILL_FX_MS = 500;
const PB_TGT_HOLD = 12;                // 카메라 주인공 갈아타기 뜸(프레임)
const PB_ZOOM_BASE = 1.9, PB_ZOOM_START = 3, PB_ZOOM_MAX = 3.2, PB_ZOOM_TH = 5, PB_SLOW_MIN = 0.25;
const PB_G_MPS2 = 10;
const PB_MAX_STEPS = 100 * 200;
const PB_CATCHUP_MIN_MS = 1500;        // 서버 시작보다 이만큼 늦게 붙은 창만 빨리 감는다
const PB_CATCHUP_PER_FRAME = 30;
const PB_COLS = ['#ff4d6d', '#ffd166', '#4dd6a8', '#4da3ff', '#c77dff', '#ff9e4d',
                 '#7bed9f', '#ff6ec7', '#5ee7df', '#ffe066', '#a29bfe', '#fd79a8'];
const PB_READY_NAMES = 8;
const FONT = 'Pretendard, "Malgun Gothic", sans-serif';

/* ⚙️ 물리 엔진 — box2d(원본 lazygyu/roulette 와 같은 엔진, box2d-wasm 7.0.0 · Zlib). 한 번만 읽는다(창 하나에 판 하나). */
let enginePromise = null;
function loadEngine() {
    if (!enginePromise) {
        enginePromise = loadScript('/vendor/pinball-maps.js', () => Array.isArray(window.PB_MAPS)).catch(() => null)
            .then(() => loadScript('/vendor/box2d/Box2D.js', () => typeof window.Box2D === 'function'))
            .then(() => window.Box2D({ locateFile: f => '/vendor/box2d/' + f }));
    }
    return enginePromise;
}

export function mount(root, lm, opts) {
    // ⚠️ 캔버스 id(pb-canvas)는 테마(css/themes.css 의 #canvas.themed #pb-canvas)가 본다 — 창 하나에 핀볼은 하나뿐이다
    root.innerHTML = '<div class="pb-wrap gm-board">'
        + '<canvas class="pb-canvas" id="pb-canvas" width="' + PB_W + '" height="' + PB_H + '"></canvas>'
        + '<div class="pb-winner"></div><div class="pb-ready"></div></div>';
    const box = root.firstElementChild;
    const cv = root.querySelector('.pb-canvas');
    const winEl = root.querySelector('.pb-winner');
    const readyEl = root.querySelector('.pb-ready');

    let PB_WORLD = PB_WORLD_OWN;
    let pbR = PB_R;
    let pbBalls = [], pbRAF = null, pbLast = 0, pbAcc = 0;
    let pbRound = -1, pbFinish = [], pbStartedAt = 0, pbReported = false;
    let pbPreviewKey = null, pbGoalLine = 0, pbZoomY = 0, pbScale = 60, pbSpawn = null;
    let pbRule = 'first', pbPicks = 1;
    let pbCamX = 0, pbCamY = 0, pbZoom = 1;
    let pbSteps = 0, pbOverAt = 0, pbPops = [], pbStall = 0, pbSkillOn = true, pbFx = [];
    let pbTgt = null, pbTgtCand = null, pbTgtN = 0, pbRandom = null;
    let pbB2 = null, pbWorld = null, pbEnts = [], pbSC = 60, pbOX = 0, pbAlpha = 0, pbLastG = null, pbV = null;
    let pbCatchup = 0;                // 빨리 감을 걸음 수(늦게 붙은 창)
    let pbLiveRound = 0;              // 지금 굴리는 판의 서버 round_id(보고용)

    loadEngine().then(B => {
        pbB2 = B;
        pbV = new B.b2Vec2(0, 0);
        if (pbLastG) { pbRound = -1; pbPreviewKey = null; try { pbUpdate(pbLastG); } catch (e) { console.error('[핀볼]', e); } }
    }).catch(e => console.warn('[핀볼] box2d 를 못 읽었다 — 핀볼만 빠진다:', e));

    function pbVec(x, y) { pbV.set_x(x); pbV.set_y(y); return pbV; }

    /* 🗺️ 맵 한 판을 box2d 세상에 짓는다(원본 physics-box2d.createEntities 그대로). 물리는 미터, 그림은 픽셀. */
    function pbBuildStage(st) {
        const B = pbB2;
        pbWorld = new B.b2World(pbVec(0, PB_G_MPS2));
        pbEnts = [];
        st.entities.forEach(e => {
            const p = e.position || { x: 0, y: 0 }, sh = e.shape || {}, pr = e.props || {};
            const kin = e.type === 'kinematic';
            const bd = new B.b2BodyDef();
            bd.set_type(kin ? B.b2_kinematicBody : B.b2_staticBody);
            const body = pbWorld.CreateBody(bd);
            B.destroy(bd);
            const fd = new B.b2FixtureDef();
            fd.set_density(pr.density === undefined ? 1 : pr.density);
            fd.set_restitution(pr.restitution === undefined ? 0 : pr.restitution);
            let g = null, bb = 0;
            if (sh.type === 'box') {
                const s = new B.b2PolygonShape();
                const c = new B.b2Vec2(0, 0);
                s.SetAsBox(sh.width || .1, sh.height || .1, c, sh.rotation || 0);
                B.destroy(c);
                fd.set_shape(s); body.CreateFixture(fd); B.destroy(s);
                g = { t: 'box', w: sh.width || .1, h: sh.height || .1, r: sh.rotation || 0 };
                bb = Math.hypot(g.w, g.h);
            } else if (sh.type === 'circle') {
                const s = new B.b2CircleShape();
                s.set_m_radius(sh.radius || .3);
                fd.set_shape(s); body.CreateFixture(fd); B.destroy(s);
                g = { t: 'circle', r: sh.radius || .3 };
                bb = g.r;
            } else if (sh.type === 'polyline' && sh.points && sh.points.length > 1) {
                for (let i = 0; i < sh.points.length - 1; i++) {
                    const a = sh.points[i], b = sh.points[i + 1];
                    const v1 = new B.b2Vec2(a[0], a[1]), v2 = new B.b2Vec2(b[0], b[1]);
                    const edge = new B.b2EdgeShape();
                    edge.SetTwoSided(v1, v2);
                    body.CreateFixture(edge, 1);
                    B.destroy(edge); B.destroy(v1); B.destroy(v2);
                }
                g = { t: 'line', pts: sh.points };
                sh.points.forEach(q => { bb = Math.max(bb, Math.hypot(q[0], q[1])); });
            }
            B.destroy(fd);
            body.SetAngularVelocity(pr.angularVelocity || 0);
            body.SetTransform(pbVec(p.x, p.y), 0);
            if (!g) return;
            pbEnts.push({ body, g, x: p.x, y: p.y, bb, kin, pop: (Number(pr.life) || 0) > 0, gone: false, wall: !!e.pbWall,
                          label: kin ? 'spin' : (g.t === 'circle' ? 'peg' : 'rail') });
        });
    }

    /* 🗺️ 가져온 맵 — 원본 맵 그대로, 화면 폭에 맞는 배율만 정한다 */
    function pbStageFromMap(mapIdx) {
        const maps = window.PB_MAPS || null;
        if (!maps || !maps.length) return null;
        const st = maps[((mapIdx | 0) % maps.length + maps.length) % maps.length];
        if (!st || !st.entities) return null;
        let minX = Infinity, maxX = -Infinity;
        st.entities.forEach(e => {
            const p = e.position || { x: 0, y: 0 }, sh = e.shape || {};
            if (sh.type === 'polyline' && sh.points) {
                sh.points.forEach(pt => { minX = Math.min(minX, p.x + pt[0]); maxX = Math.max(maxX, p.x + pt[0]); });
            } else {
                const half = (sh.type === 'circle') ? (sh.radius || 0) : (sh.width || 0);
                minX = Math.min(minX, p.x - half); maxX = Math.max(maxX, p.x + half);
            }
        });
        if (!isFinite(minX) || maxX <= minX) return null;
        const goalY = st.goalY || 100;
        // 원본 맵도 옆벽을 그리지만, 만일을 위해 바깥에 벽과 바닥을 덧댄다(안 그려진다)
        const extra = [
            { position: { x: minX - .2, y: goalY / 2 }, type: 'static', pbWall: true,
              shape: { type: 'box', width: .2, height: goalY, rotation: 0 }, props: { density: 1, restitution: 0 } },
            { position: { x: maxX + .2, y: goalY / 2 }, type: 'static', pbWall: true,
              shape: { type: 'box', width: .2, height: goalY, rotation: 0 }, props: { density: 1, restitution: 0 } },
            { position: { x: (minX + maxX) / 2, y: goalY + 3 }, type: 'static', pbWall: true,
              shape: { type: 'box', width: (maxX - minX), height: .2, rotation: 0 }, props: { density: 1, restitution: 0 } },
        ];
        return { entities: st.entities.concat(extra), goalY, zoomY: (st.zoomY === undefined ? goalY : st.zoomY), title: st.title || '',
                 sc: PB_W / (maxX - minX), ox: -minX * PB_W / (maxX - minX), fromMap: true };
    }

    /* 🧱 우리 코스 — 못밭 → 바람개비 → 레일 × 3 + 깔때기(미터 단위로 적어 가져온 맵과 같은 길로 짓는다, 60px/m) */
    function pbStageOwn(rng) {
        const S = 60, m = px => px / S;
        const E = [];
        const box = (x, y, w, h, rot, rest, extra) => {
            E.push(Object.assign({ position: { x: m(x), y: m(y) }, type: 'static',
                shape: { type: 'box', width: m(w) / 2, height: m(h) / 2, rotation: rot || 0 },
                props: { density: 1, restitution: rest } }, extra || {}));
        };
        box(PB_W / 2, PB_CEIL - PB_WALL / 2, PB_W, PB_WALL, 0, .45, { pbWall: true });
        const wallH = PB_WORLD_OWN - PB_CEIL + PB_WALL * 4, wallY = (PB_CEIL + PB_WORLD_OWN) / 2;
        box(-PB_WALL / 2, wallY, PB_WALL, wallH, 0, .45, { pbWall: true });
        box(PB_W + PB_WALL / 2, wallY, PB_WALL, wallH, 0, .45, { pbWall: true });
        box(PB_W / 2, PB_WORLD_OWN + PB_WALL / 2, PB_W * 2, PB_WALL, 0, .45, { pbWall: true });
        for (let seg = 0; seg < PB_SEGS; seg++) {
            const base = PB_TOP + seg * PB_SEG_H;
            const gapY = 66, gapX = 98;
            for (let r = 0; r < 5; r++) {
                const y = base + r * gapY;
                const off = ((r + seg) % 2) ? gapX / 2 : 0;
                for (let x = off + 60; x < PB_W - 40; x += gapX) {
                    E.push({ position: { x: m(x + (rng() - .5) * 12), y: m(y + (rng() - .5) * 10) }, type: 'static',
                             shape: { type: 'circle', radius: m(9) }, props: { density: 1, restitution: .62 } });
                }
            }
            const dir = seg % 2 ? -1 : 1;
            [[300, dir], [680, -dir]].forEach(sp => {
                E.push({ position: { x: m(sp[0]), y: m(base + 340) }, type: 'kinematic',
                         shape: { type: 'box', width: m(210) / 2, height: m(16) / 2, rotation: 0 },
                         props: { density: 1, restitution: .58, angularVelocity: sp[1] * (1.08 + rng() * .72) } });
            });
            const tilt = seg % 2 ? -0.30 : 0.30;
            [[330, 450, tilt], [650, 540, -tilt]].forEach(r => { box(r[0], base + r[1], 380, 18, r[2], .5); });
        }
        const fy = PB_WORLD_OWN - 90;
        box(120, fy, 330, 18, 0.40, .5);
        box(PB_W - 120, fy, 330, 18, -0.40, .5);
        const goal = m(PB_WORLD_OWN - PB_GOAL_H);
        return { entities: E, goalY: goal, zoomY: goal, title: '', sc: S, ox: 0, fromMap: false };
    }

    /* 🔴 구슬 — 반지름 0.25m, 밀도 1~2배(씨앗 난수). 출발 자리는 매 판 섞는다. */
    function pbMakeBalls(names, rng) {
        const B = pbB2, n = names.length;
        const per = Math.min(n, PB_SPAWN_PER);
        const lane = PB_SPAWN_BAND / Math.max(1, per);
        const cmap = {};
        let ci = 0;
        names.forEach(nm => { if (cmap[nm] === undefined) cmap[nm] = ci++; });
        const who = names.map((_, i) => i);
        for (let i = who.length - 1; i > 0; i--) {
            const j = Math.floor(rng() * (i + 1));
            const t = who[i]; who[i] = who[j]; who[j] = t;
        }
        return who.map((i, slot) => {
            const nm = names[i];
            let mx, my;
            if (pbSpawn) {
                // 🚿 가져온 맵 — 원본 자리 그대로: x = 10.25 + (번호 % 10) × 0.6, 한 줄 10개씩 위로
                const maxLine = Math.ceil(n / 10), line = Math.floor(slot / 10);
                const lineDelta = -Math.max(0, Math.ceil(maxLine - 5));
                mx = 10.25 + (slot % 10) * 0.6; my = maxLine - line + lineDelta;
            } else {
                const px = 160 + lane * ((slot % per) + .5) + (rng() - .5) * (lane * .3);
                const py = PB_SPAWN_Y0 - Math.floor(slot / per) * PB_SPAWN_ROWH;
                mx = (px - pbOX) / pbSC; my = py / pbSC;
            }
            const bd = new B.b2BodyDef();
            bd.set_type(B.b2_dynamicBody);
            bd.set_position(pbVec(mx, my));
            const body = pbWorld.CreateBody(bd);
            B.destroy(bd);
            const cs = new B.b2CircleShape();
            cs.set_m_radius(0.25);
            body.CreateFixture(cs, 1 + rng());
            B.destroy(cs);
            body.SetAwake(false);
            body.SetEnabled(false);                // 출발 전엔 멈춰 있다
            const b = {
                body, pbName: nm, pbColor: PB_COLS[cmap[nm] % PB_COLS.length], pbDone: false,
                position: { x: mx * pbSC + pbOX, y: my * pbSC },
                pbCool: 1 + Math.floor(rng() * PB_SKILL_COOL),
                pbStuckMs: 0, pbLx: mx, pbLy: my,
            };
            b.pbPx = b.position.x; b.pbPy = b.position.y;
            return b;
        });
    }

    function pbStop() {
        if (pbRAF) { cancelAnimationFrame(pbRAF); pbRAF = null; }
        if (pbWorld && pbB2) { try { pbB2.destroy(pbWorld); } catch (e) {} }
        pbWorld = null; pbBalls = []; pbEnts = []; pbPops = [];
    }

    /* ▶️ 한 판 시작 — 서버가 준 씨앗으로 짓는다. lagMs: 서버 시작에서 지난 시간(늦게 붙은 창이 빨리 감을 몫) */
    function pbStart(names, seed, mapIdx, previewOnly, lagMs) {
        if (!pbB2) return;
        pbStop();
        const rng = pbRng(seed);
        pbRandom = pbRng(seed ^ 0x5bf03635);   // 흔들기 · 밀어내기 전용 — 코스 난수와 섞이지 않게
        let st = null;
        const maps = window.PB_MAPS || null;
        if (maps && maps.length && mapIdx >= 0 && mapIdx < maps.length) st = pbStageFromMap(mapIdx);
        if (!st) st = pbStageOwn(rng);
        pbSC = st.sc; pbOX = st.ox;
        pbSpawn = st.fromMap ? true : null;
        pbScale = pbSC;
        pbR = 0.25 * pbSC;
        pbGoalLine = st.goalY * pbSC;
        pbZoomY = st.zoomY * pbSC;
        PB_WORLD = st.fromMap ? (st.goalY * pbSC + 140) : PB_WORLD_OWN;
        pbBuildStage(st);
        pbBalls = pbMakeBalls(names, rng);
        pbFinish = []; pbReported = false; pbOverAt = 0; pbStall = 0; pbFx = []; pbPops = [];
        pbTgt = null; pbTgtCand = null; pbTgtN = 0;
        pbStartedAt = performance.now(); pbLast = pbStartedAt;
        pbAcc = 0; pbAlpha = 0; pbSteps = 0;
        pbCatchup = (!previewOnly && lagMs > PB_CATCHUP_MIN_MS) ? Math.floor(Math.min(lagMs, PB_MAX_MS) / PB_STEP) : 0;
        // 카메라를 구슬 무리에 맞춰 두고 시작한다(첫 프레임에 화면이 튀지 않게)
        let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
        pbBalls.forEach(b => {
            x0 = Math.min(x0, b.position.x); x1 = Math.max(x1, b.position.x);
            y0 = Math.min(y0, b.position.y); y1 = Math.max(y1, b.position.y);
        });
        if (!isFinite(x0)) { x0 = x1 = PB_W / 2; y0 = y1 = 0; }
        const mg = pbR * 6;
        pbZoom = Math.max(PB_ZOOM_BASE, Math.min(PB_ZOOM_START,
            Math.min(PB_W / Math.max(1, (x1 - x0) + mg * 2), PB_H / Math.max(1, (y1 - y0) + mg * 2))));
        pbCamX = (x0 + x1) / 2;
        pbCamY = (y0 + y1) / 2;
        if (previewOnly) { pbDraw(); return; }
        pbBalls.forEach(b => { b.body.SetEnabled(true); b.body.SetAwake(true); });
        pbLoop();
    }

    /* 🏁 결승선 아래로 내려간 구슬 — 순서에 넣고 세상에서 치운다 */
    function pbCheckGoal() {
        for (let i = 0; i < pbBalls.length; i++) {
            const b = pbBalls[i];
            if (b.pbDone || b.position.y < pbGoalLine) continue;
            b.pbDone = true;
            pbFinish.push(b.pbName);
            try { pbWorld.DestroyBody(b.body); } catch (e) {}
            b.body = null;
        }
    }

    /* 🩹 5초 동안 거의 안 움직이면 아무 쪽으로 툭 친다(씨앗 난수 · 걸음 수로 센다 — 화면마다 같다) */
    function pbShake() {
        for (let i = 0; i < pbBalls.length; i++) {
            const b = pbBalls[i];
            if (b.pbDone) continue;
            const p = b.body.GetPosition();
            const dx = p.get_x() - b.pbLx, dy = p.get_y() - b.pbLy;
            b.pbLx = p.get_x(); b.pbLy = p.get_y();
            if (dx * dx + dy * dy < 0.00001) {
                b.pbStuckMs += PB_STEP;
                if (b.pbStuckMs > PB_STUCK_MS) {
                    b.body.ApplyLinearImpulseToCenter(pbVec(pbRandom() * 10 - 5, pbRandom() * 10 - 5), true);
                    b.pbStuckMs = 0;
                }
            } else {
                b.pbStuckMs = 0;
            }
        }
    }

    /* 아직 안 내려온 구슬을 앞선 순서로(맨 앞 = 골에 가장 가까움) */
    function pbActive() {
        const a = [];
        for (let i = 0; i < pbBalls.length; i++) if (!pbBalls[i].pbDone) a.push(pbBalls[i]);
        a.sort((p, q) => q.position.y - p.position.y);
        return a;
    }

    function pbTargetIdx(act) {
        const want = (pbRule === 'last') ? (pbBalls.length - 1) : (pbPicks - 1);
        const i = want - pbFinish.length;
        return Math.max(0, Math.min(act.length - 1, i));
    }

    /* 🐢 슬로모션 — 결승선 앞에서 경쟁자가 붙어 있을 때만. 걸음 크기는 그대로, 걸음을 띄엄띄엄 민다 */
    function pbSlowFactor() {
        if (!pbZoomY) return 1;
        const t = pbTgt;
        if (!t || t.pbDone) return 1;
        const act = pbActive();
        if (act.length < 2) return 1;
        const ti = act.indexOf(t);
        if (ti < 0) return 1;
        const d = Math.abs(pbZoomY - t.position.y) / pbScale;
        if (d >= PB_ZOOM_TH) return 1;
        if (!act[ti - 1] && !act[ti + 1]) return 1;
        return Math.max(PB_SLOW_MIN, d / PB_ZOOM_TH);
    }

    /* 💢 한 구슬이 주변을 밀어낸다(원본 impact — 10m 안, 0.81×5) */
    function pbImpact(src) {
        const sp = src.body.GetPosition(), sx = sp.get_x(), sy = sp.get_y();
        for (let i = 0; i < pbBalls.length; i++) {
            const b = pbBalls[i];
            if (b === src || b.pbDone) continue;
            const p = b.body.GetPosition();
            let dx = p.get_x() - sx, dy = p.get_y() - sy;
            const d2 = dx * dx + dy * dy;
            if (d2 >= PB_SKILL_R_M * PB_SKILL_R_M || d2 < 1e-9) continue;
            const d = Math.sqrt(d2);
            dx /= d; dy /= d;
            const k = 0.81 * 5;
            b.body.ApplyLinearImpulseToCenter(pbVec(dx * k, dy * k), true);
            b.pbHit = performance.now();
        }
        pbFx.push({ x: src.position.x, y: src.position.y, r: PB_SKILL_R_M * pbSC, t: performance.now() });
        if (pbFx.length > 24) pbFx.splice(0, pbFx.length - 24);
    }

    function pbSkills() {
        if (!pbSkillOn || !pbRandom) return;
        const rate = PB_SKILL_RATE * Math.min(1, PB_SKILL_CROWD / Math.max(1, pbBalls.length));
        for (let i = 0; i < pbBalls.length; i++) {
            const b = pbBalls[i];
            if (b.pbDone) continue;
            b.pbCool = (b.pbCool || 0) - 1;
            if (b.pbCool > 0) continue;
            b.pbCool = PB_SKILL_COOL;
            if (pbRandom() < rate) pbImpact(b);
        }
    }

    /* 💥 닿으면 깨지는 것 — 걸음 뒤에 닿아 있으면 치운다 */
    function pbPopCheck() {
        const B = pbB2;
        for (let i = 0; i < pbEnts.length; i++) {
            const e = pbEnts[i];
            if (!e.pop || e.gone) continue;
            const edge = e.body.GetContactList();
            if (!B.getPointer(edge)) continue;
            const c = edge.get_contact();
            if (!B.getPointer(c) || !c.IsTouching()) continue;
            e.gone = true;
            try { pbWorld.DestroyBody(e.body); } catch (err) {}
            pbPops.push({ x: e.x * pbSC + pbOX, y: e.y * pbSC, r: Math.max(8, e.bb * pbSC), t: performance.now() });
        }
        if (pbPops.length > 60) pbPops.splice(0, pbPops.length - 60);
    }

    /* 👣 물리 한 걸음(10ms) */
    function pbStepOnce() {
        for (let i = 0; i < pbBalls.length; i++) {
            const b = pbBalls[i];
            b.pbPx = b.position.x; b.pbPy = b.position.y;
        }
        pbSkills();
        pbWorld.Step(PB_STEP / 1000, 6, 2);
        pbPopCheck();
        for (let i = 0; i < pbBalls.length; i++) {
            const b = pbBalls[i];
            if (b.pbDone) continue;
            const p = b.body.GetPosition();
            b.position.x = p.get_x() * pbSC + pbOX;
            b.position.y = p.get_y() * pbSC;
        }
        pbShake();
        pbSteps++;
        pbCheckGoal();
        pbStallWatch();
    }

    function pbPos(b) {
        if (b.pbPx === undefined) return b.position;
        const a = Math.max(0, Math.min(1, pbAlpha));
        return { x: b.pbPx + (b.position.x - b.pbPx) * a, y: b.pbPy + (b.position.y - b.pbPy) * a };
    }

    function pbEntPath(g, e) {
        const ang = e.kin ? e.body.GetAngle() : 0;
        const ca = Math.cos(ang), sa = Math.sin(ang);
        const W = (lx, ly) => [(e.x + lx * ca - ly * sa) * pbSC + pbOX, (e.y + lx * sa + ly * ca) * pbSC];
        g.beginPath();
        if (e.g.t === 'circle') {
            const c = W(0, 0);
            g.arc(c[0], c[1], e.g.r * pbSC, 0, Math.PI * 2);
            return true;
        }
        if (e.g.t === 'box') {
            const cr = Math.cos(e.g.r), sr = Math.sin(e.g.r), w = e.g.w, h = e.g.h;
            [[-w, -h], [w, -h], [w, h], [-w, h]].forEach((q, k) => {
                const p = W(q[0] * cr - q[1] * sr, q[0] * sr + q[1] * cr);
                if (k) g.lineTo(p[0], p[1]); else g.moveTo(p[0], p[1]);
            });
            g.closePath();
            return true;
        }
        e.g.pts.forEach((q, k) => { const p = W(q[0], q[1]); if (k) g.lineTo(p[0], p[1]); else g.moveTo(p[0], p[1]); });
        return false;
    }

    /* 🎯 카메라 주인공 — 규칙이 가리키는 구슬을 따르되 뜸을 들여 바꾼다 */
    function pbTarget() {
        const act = pbActive();
        const want = act.length ? act[pbTargetIdx(act)] : null;
        if (!pbTgt || pbTgt.pbDone || act.indexOf(pbTgt) < 0) {
            pbTgt = want; pbTgtCand = null; pbTgtN = 0;
        } else if (want === pbTgt) {
            pbTgtCand = null; pbTgtN = 0;
        } else if (want === pbTgtCand) {
            if (++pbTgtN >= PB_TGT_HOLD) { pbTgt = want; pbTgtCand = null; pbTgtN = 0; }
        } else {
            pbTgtCand = want; pbTgtN = 1;
        }
        return pbTgt;
    }

    function pbStallWatch() {
        let moved = false;
        for (let i = 0; i < pbBalls.length; i++) {
            const b = pbBalls[i];
            if (b.pbDone) continue;
            if (b.pbTop === undefined || b.position.y > b.pbTop + PB_NOGAIN_PX) { b.pbTop = b.position.y; moved = true; }
        }
        pbStall = moved ? 0 : (pbStall + 1);
    }

    /* 📤 결과 보고 — 지금 판의 첫 보고만 서버가 받는다. 미리보기 창은 안 보낸다. */
    function pbReport(roundId) {
        if (pbReported) return;
        pbReported = true;
        const order = pbFinish.slice();
        // 못 내려온 것은 뒤로 — 앞선 순서대로(끝까지 남기 규칙에서 꼴찌가 곧 우승자다)
        pbActive().forEach(b => { order.push(b.pbName); });
        if (opts.monitor) return;
        lm.cmd('pinball.result', { round_id: roundId, result: order }).then(res => {
            if (res && !res.ok) console.log('[핀볼] 결과 보고를 서버가 안 받음(다른 창이 먼저 보냈을 수 있다):', res.error);
        }).catch(() => {});
    }

    function pbLoop() {
        pbRAF = requestAnimationFrame(pbLoop);
        if (!pbWorld) return;
        const now = performance.now();
        let dt = now - pbLast; pbLast = now;
        if (dt > 250) dt = 250;
        if (pbCatchup > 0) {
            // ⏩ 늦게 붙은 창 — 지난 몫을 그리지 않고 민다(같은 걸음이라 같은 경기)
            let k = 0;
            while (pbCatchup > 0 && k++ < PB_CATCHUP_PER_FRAME) { pbStepOnce(); pbCatchup--; }
            pbAcc = 0;
        } else {
            pbAcc += dt * pbSlowFactor();
            let guard = 0;
            while (pbAcc >= PB_STEP && guard++ < 40) { pbAcc -= PB_STEP; pbStepOnce(); }
            if (pbAcc > PB_STEP) pbAcc = PB_STEP;
        }
        pbAlpha = pbAcc / PB_STEP;
        pbDraw();

        /* 🏁 필요한 등수까지만 나오면 끝 — 먼저 골인: 뽑는 수만큼 들어오면 / 끝까지 남기: 한 명만 남으면.
           갈린 즉시 보고하지 않고 0.7초 더 굴린다(들어가는 장면을 보여 줘야 한다). */
        const left = pbBalls.length - pbFinish.length;
        const decided = (pbRule === 'last') ? (left <= 1) : (pbFinish.length >= pbPicks);
        if (decided && !pbOverAt) { pbOverAt = now; if (pbCatchup <= 0) pbBoom(); }
        const stalled = pbStall > PB_STALL_STEPS;
        const timeout = stalled || (now - pbStartedAt > PB_MAX_MS) || (pbSteps > PB_MAX_STEPS);
        if (!pbReported && ((pbOverAt && now - pbOverAt > 700) || timeout)) pbReport(pbLiveRound);
    }

    /* 🎥 카메라 — 주인공 구슬을 따라다니며 골 근처에서 당긴다(그리기용 — 물리와 무관) */
    function pbCamera() {
        const t = pbTarget();
        let wz = PB_ZOOM_BASE, wx = PB_W / 2, wy = pbCamY;
        if (t) {
            const tp = pbPos(t);
            wx = tp.x; wy = tp.y;
            if (pbZoomY) {
                const d = Math.abs(pbZoomY - tp.y) / pbScale;
                if (d < PB_ZOOM_TH) wz = Math.max(PB_ZOOM_BASE, (1 - d / PB_ZOOM_TH) * PB_ZOOM_MAX);
            }
        }
        const hw = PB_W / (2 * wz), hh = PB_H / (2 * wz);
        wx = (hw >= PB_W / 2) ? PB_W / 2 : Math.max(hw, Math.min(PB_W - hw, wx));
        const loY = hh, hiY = Math.max(hh, PB_WORLD - hh);
        wy = Math.max(loY, Math.min(hiY, wy));
        pbZoom += (wz - pbZoom) * 0.08;
        pbCamX += (wx - pbCamX) * 0.10;
        pbCamY += (wy - pbCamY) * 0.12;
    }

    function pbTally(names) {
        const at = {}, out = [];
        (names || []).forEach(nm => {
            if (at[nm] === undefined) { at[nm] = out.length; out.push([nm, 0]); }
            out[at[nm]][1]++;
        });
        return out;
    }
    function pbColorOf() {
        const m = {};
        pbBalls.forEach(b => { if (m[b.pbName] === undefined) m[b.pbName] = b.pbColor; });
        return m;
    }
    function pbDot(g, x, y, col) {
        g.beginPath(); g.arc(x, y - 7, 7, 0, Math.PI * 2);
        g.fillStyle = col || '#dfe6f2'; g.fill();
        g.lineWidth = 2; g.strokeStyle = 'rgba(0,0,0,.9)'; g.stroke();
    }

    /* 🎨 판 그리기 — 방송판 네온 느낌. 세상 좌표를 카메라만큼 밀어 그린다. */
    function pbDraw() {
        if (!pbWorld) return;
        const g = cv.getContext('2d');
        g.clearRect(0, 0, PB_W, PB_H);
        pbCamera();
        const half = PB_H / (2 * pbZoom), halfW = PB_W / (2 * pbZoom);
        const top = pbCamY - half, bot = pbCamY + half;
        const lft = pbCamX - halfW, rgt = pbCamX + halfW;
        const Z = pbZoom;

        g.save();
        g.translate(PB_W / 2, PB_H / 2);
        g.scale(Z, Z);
        g.translate(-pbCamX, -pbCamY);

        // 골 구역
        const gy = pbGoalLine || (PB_WORLD - PB_GOAL_H);
        if (gy < bot && gy + PB_GOAL_H * 2 > top) {
            const grd = g.createLinearGradient(0, gy, 0, gy + PB_GOAL_H);
            grd.addColorStop(0, 'rgba(255,207,77,.05)');
            grd.addColorStop(1, 'rgba(255,207,77,.22)');
            g.fillStyle = grd; g.fillRect(0, gy, PB_W, PB_GOAL_H);
            g.strokeStyle = 'rgba(255,207,77,.75)'; g.lineWidth = 3 / Z;
            g.beginPath(); g.moveTo(0, gy); g.lineTo(PB_W, gy); g.stroke();
        }

        // 장애물 — 화면에 걸리는 것만
        for (let i = 0; i < pbEnts.length; i++) {
            const e = pbEnts[i];
            if (e.gone || e.wall) continue;
            const ex = e.x * pbSC + pbOX, ey = e.y * pbSC, er = e.bb * pbSC + 40;
            if (ey + er < top || ey - er > bot || ex + er < lft || ex - er > rgt) continue;
            const closed = pbEntPath(g, e);
            if (e.pop) { g.fillStyle = 'rgba(255,120,190,.16)'; g.strokeStyle = 'rgba(255,140,200,.80)'; }
            else if (e.label === 'peg') { g.fillStyle = 'rgba(150,225,255,.30)'; g.strokeStyle = 'rgba(150,225,255,.85)'; }
            else if (e.label === 'spin') { g.fillStyle = 'rgba(255,160,90,.28)'; g.strokeStyle = 'rgba(255,170,100,.95)'; }
            else { g.fillStyle = 'rgba(255,255,255,.16)'; g.strokeStyle = 'rgba(255,255,255,.80)'; }
            g.lineWidth = (closed ? 2.5 : 3) / Z;
            if (closed) g.fill();
            g.stroke();
        }

        // 구슬 + 이름 — 글씨 · 테두리는 화면 기준 굵기(배율로 나눈다)
        g.font = '900 ' + (19 / Z).toFixed(2) + 'px ' + FONT;
        g.textAlign = 'center'; g.textBaseline = 'middle';
        const tgt = pbTgt;
        const nowMs = performance.now();
        for (let i = 0; i < pbBalls.length; i++) {
            const b = pbBalls[i];
            if (b.pbDone) continue;
            const p = pbPos(b);
            if (p.y < top - 40 || p.y > bot + 40) continue;
            if (p.x < lft - 40 || p.x > rgt + 40) continue;
            if (b === tgt) {
                g.beginPath(); g.arc(p.x, p.y, pbR + 7 / Z, 0, Math.PI * 2);
                g.strokeStyle = 'rgba(255,209,102,.95)'; g.lineWidth = 3 / Z; g.stroke();
            }
            g.beginPath(); g.arc(p.x, p.y, pbR, 0, Math.PI * 2);
            g.fillStyle = b.pbColor; g.shadowColor = b.pbColor;
            const hit = b.pbHit ? Math.max(0, 1 - (nowMs - b.pbHit) / 400) : 0;
            g.shadowBlur = (16 + hit * 26) / Z;
            g.fill(); g.shadowBlur = 0;
            if (hit > 0) { g.fillStyle = 'rgba(255,255,255,' + (hit * .55).toFixed(2) + ')'; g.fill(); }
            g.strokeStyle = 'rgba(255,255,255,.9)'; g.lineWidth = 2 / Z; g.stroke();
            g.lineWidth = 4 / Z; g.strokeStyle = 'rgba(0,0,0,.92)';
            if (pbBalls.length > PB_NAME_MAX && b !== tgt) continue;
            g.strokeText(b.pbName, p.x, p.y + pbR + 15 / Z);
            g.fillStyle = '#fff';
            g.fillText(b.pbName, p.x, p.y + pbR + 15 / Z);
        }

        // 💢 밀어낸 자리 — 옅은 고리
        for (let i = 0; i < pbFx.length; i++) {
            const f = pbFx[i];
            const k = (nowMs - f.t) / PB_SKILL_FX_MS;
            if (k < 0 || k > 1) continue;
            if (f.y < top - f.r || f.y > bot + f.r) continue;
            g.beginPath(); g.arc(f.x, f.y, f.r * k, 0, Math.PI * 2);
            g.strokeStyle = 'rgba(255,255,255,' + ((1 - k) * 0.5).toFixed(2) + ')';
            g.lineWidth = 1.8 / Z; g.stroke();
        }
        // 💥 깨지는 순간
        for (let i = 0; i < pbPops.length; i++) {
            const p = pbPops[i];
            const k = (nowMs - p.t) / 350;
            if (k < 0 || k > 1) continue;
            if (p.y < top - 60 || p.y > bot + 60) continue;
            g.beginPath(); g.arc(p.x, p.y, p.r * (1 + k * 0.7), 0, Math.PI * 2);
            g.strokeStyle = 'rgba(255,150,205,' + (1 - k).toFixed(2) + ')';
            g.lineWidth = 3 / Z; g.stroke();
        }
        g.restore();

        // 📏 진행 막대 — 오른쪽 끝(노란 표 = 선두)
        const barX = PB_W - 12, barTop = 20, barH = PB_H - 40;
        g.fillStyle = 'rgba(255,255,255,.10)';
        g.fillRect(barX - 3, barTop, 6, barH);
        for (let i = 0; i < pbBalls.length; i++) {
            const b = pbBalls[i];
            if (b.pbDone) continue;
            const f = Math.max(0, Math.min(1, b.position.y / (pbGoalLine || PB_WORLD)));
            g.fillStyle = b.pbColor; g.globalAlpha = .75;
            g.fillRect(barX - 5, barTop + barH * f - 2, 10, 4);
            g.globalAlpha = 1;
        }

        // 도착한 순서(왼쪽 위) — '끝까지 남기' 는 이름별 떨어진 수
        if (pbFinish.length) {
            g.textAlign = 'left';
            g.font = '900 20px ' + FONT;
            const col = pbColorOf();
            if (pbRule !== 'last') {
                pbFinish.slice(0, 6).forEach((nm, i) => {
                    const y = 26 + i * 27;
                    pbDot(g, 23, y, col[nm]);
                    g.lineWidth = 4; g.strokeStyle = 'rgba(0,0,0,.92)';
                    g.strokeText((i + 1) + '. ' + nm, 36, y);
                    g.fillStyle = (i < pbPicks) ? '#ffd166' : '#dfe6f2';
                    g.fillText((i + 1) + '. ' + nm, 36, y);
                });
            } else {
                const tot = {};
                pbTally(pbBalls.map(b => b.pbName)).forEach(e => { tot[e[0]] = e[1]; });
                const rows = pbTally(pbFinish).map(e => [e[0], e[1], tot[e[0]] || e[1]]);
                rows.sort((x, y) => (x[1] >= x[2]) - (y[1] >= y[2]) || y[1] - x[1]);
                const shownRows = rows.slice(0, 6);
                shownRows.forEach((r, i) => {
                    const y = 26 + i * 27;
                    const out = r[1] >= r[2];
                    const txt = r[0] + '  ' + r[1] + '/' + r[2] + (out ? ' 탈락' : '');
                    g.globalAlpha = out ? .45 : 1;
                    pbDot(g, 23, y, col[r[0]]);
                    g.globalAlpha = 1;
                    g.lineWidth = 4; g.strokeStyle = 'rgba(0,0,0,.92)';
                    g.strokeText(txt, 36, y);
                    g.fillStyle = out ? '#8a93a6' : '#dfe6f2';
                    g.fillText(txt, 36, y);
                });
                g.font = '800 15px ' + FONT;
                g.lineWidth = 4; g.strokeStyle = 'rgba(0,0,0,.92)';
                const y2 = 26 + shownRows.length * 27 + 4;
                const cap = '↑ 떨어진 구슬 수' + (rows.length > 6 ? ' (외 ' + (rows.length - 6) + '명)' : '');
                g.strokeText(cap, 16, y2);
                g.fillStyle = '#9fb0c9';
                g.fillText(cap, 16, y2);
            }
        }
    }

    /* 🏆 결과 딱지 — '끝까지 남기' 면 맨 마지막에 들어온 사람이 1등(서버 winners 가 이미 뒤집어 준다) */
    function pbWinnersOf(order) {
        if (!order || !order.length) return [];
        const k = Math.max(1, Math.min(pbPicks, order.length));
        return (pbRule === 'last') ? order.slice(order.length - k).reverse() : order.slice(0, k);
    }

    function pbShowWinner(list) {
        if (!list || !list.length) { winEl.classList.remove('show'); winEl.innerHTML = ''; return; }
        const sub = (pbRule === 'last')
            ? (list.length > 1 ? ('끝까지 남은 ' + list.length + '명') : '끝까지 살아남음')
            : (list.length > 1 ? ('먼저 들어온 ' + list.length + '명') : '1등');
        const head = list.slice(0, PB_BANNER_MAX);
        const rest = list.length - head.length;
        winEl.innerHTML = '🏆 ' + head.map(n => esc(n)).join(' · ')
                        + (rest > 0 ? (' 외 ' + rest + '명') : '')
                        + '<span class="pb-w-sub">' + sub + '</span>';
        winEl.classList.toggle('many', list.length > 1);
        winEl.classList.add('show');
    }

    /* 🎉 우승 폭죽 — 판 한가운데에서(편집기로 옮겨도 따라간다) */
    function pbBoom() {
        if (!box.classList.contains('on')) return;
        const r = box.getBoundingClientRect();
        if (!r.width || !r.height) return;
        // ✨ 테마를 입었으면 그 테마 모양으로 터뜨리고 끝(옛 pbBoom 그대로 — widgets/fx/burst.js)
        try { const fx = opts.stage.use('fx'); if (fx && fx.burst(box, 'win')) return; } catch (e) {}
        boom({ particleCount: 160, spread: 95, startVelocity: 42,
               origin: { x: (r.left + r.width / 2) / window.innerWidth, y: (r.top + r.height * 0.45) / window.innerHeight },
               colors: ['#ffd166', '#ff6ec7', '#5ee7df', '#7bed9f'], zIndex: 99999 });
    }

    /* 🎱 대기 딱지 — 굴리기 전 '구슬 N개 · 곧 굴러갑니다' + 같은 이름은 '밍밍 ×80' 으로 묶어 색 구슬과 함께 */
    function pbShowReady(list) {
        if (!list || !list.length) { readyEl.classList.remove('show'); return; }
        const t = pbTally(list), col = pbColorOf();
        readyEl.textContent = '🎱 구슬 ' + list.length + '개 · 곧 굴러갑니다';
        const sub = document.createElement('span');
        sub.className = 'pb-ready-who';
        const shownT = t.slice(0, PB_READY_NAMES);
        shownT.forEach((e, i) => {
            const one = document.createElement('span');
            one.className = 'pb-one';
            const dot = document.createElement('i');
            dot.className = 'pb-dot';
            if (col[e[0]]) dot.style.background = col[e[0]];
            one.appendChild(dot);
            one.appendChild(document.createTextNode(e[1] > 1 ? e[0] + ' ×' + e[1] : e[0]));
            if (i < shownT.length - 1) { const sp = document.createElement('span'); sp.className = 'pb-sep'; sp.textContent = '·'; one.appendChild(sp); }
            sub.appendChild(one);
            sub.appendChild(document.createTextNode(' '));
        });
        if (t.length > PB_READY_NAMES) sub.appendChild(document.createTextNode(' 외 ' + (t.length - PB_READY_NAMES) + '명'));
        readyEl.appendChild(sub);
        readyEl.classList.add('show');
    }

    function onStage() {
        return (lm.get('show') || {}).stage === 'pinball';
    }

    /* 📡 pinball · show · screen 조각이 바뀔 때마다 */
    function pbUpdate(g) {
        g = g || {};
        const on = onStage();
        box.classList.toggle('on', on && !screenCovered(lm));
        opts.stage.setMode('pinball-game', on);
        if (!on) { pbStop(); pbShowWinner(null); pbShowReady(0); pbRound = -1; pbPreviewKey = null; pbLastG = null; return; }
        pbLastG = g;                       // 엔진이 늦게 읽히면 다 읽힌 뒤 이걸로 다시 그린다
        if (!pbB2) return;

        pbRule = (g.rule === 'last') ? 'last' : 'first';
        pbPicks = Math.max(1, Number(g.picks) || 1);
        pbSkillOn = (g.skills === undefined || g.skills === null) ? true : !!g.skills;
        const balls = ((g.balls && g.balls.length) ? g.balls : (g.names || [])).slice();
        const map = (g.map === undefined || g.map === null) ? -1 : Number(g.map);
        const rid = Number(g.round_id) || 0;
        if (g.running) {
            if (rid !== pbRound) {           // 새 판이면 굴린다 — 같은 판이면 그대로 둔다
                pbRound = rid;
                pbLiveRound = rid;
                pbPreviewKey = null;
                pbShowWinner(null);
                pbShowReady(0);
                const lag = (Number(g.started_at) > 0) ? serverNow() - Number(g.started_at) : 0;
                pbStart(balls, Number(g.seed) || 1, map, false, lag);
            }
        } else {
            // 서버가 결과를 받아 문을 닫았다 — 굴리던 것을 멈추고 1등을 띄운다
            if (pbRound !== -1 && rid === pbRound && pbRAF) {
                cancelAnimationFrame(pbRAF); pbRAF = null;
                pbDraw();
            }
            const res = g.result || [];
            if (!res.length) {
                // 아직 결과가 없다 = 굴리기 전 — 코스와 참가자 구슬을 줄 세워 보여 준다
                const key = JSON.stringify([balls, map, Number(g.seed) || 1]);
                if (balls.length && key !== pbPreviewKey) {
                    pbPreviewKey = key;
                    pbRound = -1;
                    pbStart(balls, Number(g.seed) || 1, map, true, 0);
                }
                pbShowReady(balls);
            } else {
                pbShowReady(0);
            }
            pbShowWinner((Array.isArray(g.winners) && g.winners.length) ? g.winners : pbWinnersOf(res));
        }
    }

    lm.on('pinball', pbUpdate);
    lm.on('show', () => pbUpdate(lm.get('pinball')));
    lm.on('screen', () => box.classList.toggle('on', onStage() && !screenCovered(lm)));
}
