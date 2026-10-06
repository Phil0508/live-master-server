/* 🎛 조종실 시작점 — 연결 하나를 열고, 조각(slice)이 바뀔 때마다 화면을 다시 맞춘다.

   흐름
     LM.connect → 통째(snapshot) → 바뀐 조각(patch)만 계속
     로그인 안 됨 → 로그인 화면 · 방송 전(session.live = false) → 이름 적기 · 방송 중 → 운영 화면
   그리기
     조각이 몇 개 한꺼번에 와도 한 번만 그린다(같은 순간의 쪽지를 모아서).
     각 칸은 '바뀐 것만' 고친다 — 통째로 innerHTML 을 갈면 입력 중인 칸 · 누르려던 단추가 날아간다
     (옛 조종실 renderUI 는 그래서 입력칸에 커서가 있으면 그리기를 통째로 건너뛰었고, 그 사이 들어온 후원이 안 보였다). */
import { makeRun, toast, confirmBox } from './util.js';
import { mountHeader } from './header.js';
import { mountLogin } from './login.js';
import { mountSetup } from './setup.js';
import { mountPending } from './pending.js';
import { mountScores } from './scores.js';
import { mountUndo } from './undo.js';
import { mountQueue } from './queue.js';
import { mountGoal } from './goal.js';
import { mountTabs } from './tabs.js';
import { PANELS as GAME_PANELS } from './panels/games.js';
import { PANELS as TOOL_PANELS } from './panels/tools.js';
import { mountPhone } from './phone.js';     // 📱 폰 손보기(새 후원 띠 · 탭 줄) · 방송 전 시그니처 관리 바로가기

const lm = window.LM.connect({ kind: 'controller' });
let status = 'connecting', snapped = false, slices = {}, scheduled = false;

const ctx = {
    lm,
    toast,
    confirm: confirmBox,
    run: makeRun(lm, () => { toast('로그인이 풀렸어요 — 다시 들어가 주세요', 'err'); setTimeout(() => location.reload(), 1500); }),
    rerender: schedule,
    get slices() { return slices; },
};

const $ = id => document.getElementById(id);
const views = {
    header: mountHeader($('hdr'), ctx),
    login: mountLogin($('v-login'), ctx),
    setup: mountSetup($('v-setup'), ctx),
    pending: mountPending($('pending'), ctx),
    scores: mountScores($('scores'), ctx),
    undo: mountUndo($('undo'), $('logs'), ctx),
    queue: mountQueue($('queue'), ctx),
    goal: mountGoal($('goal'), ctx),
    tabs: mountTabs($('tabs'), ctx, [...GAME_PANELS, ...TOOL_PANELS]),
};
safe(() => mountPhone(ctx));               // 📱 phone.js — 넘어져도 조종실은 그대로

lm.onStatus(s => {
    status = s;
    if (s === 'live') snapped = true;
    schedule();
});
lm.on('*', s => { slices = s; schedule(); });

function schedule() {
    if (scheduled) return;
    scheduled = true;
    // ⚠️ requestAnimationFrame 은 가려진 창에서 멈춘다(방송 PC 는 OBS 가 앞에 있을 때가 많다) — 마이크로태스크로 모은다
    Promise.resolve().then(() => { scheduled = false; render(); });
}

function pickView() {
    if (!snapped) return 'splash';
    if (!lm.authed) return 'login';
    return (slices.session && slices.session.live) ? 'live' : 'setup';
}

function render() {
    const view = pickView();
    if (document.body.dataset.view !== view) document.body.dataset.view = view;
    $('down-banner').hidden = !(snapped && status === 'down');
    $('splash-msg').textContent = status === 'down' ? '서버에 닿지 않아요 — 다시 붙는 중…' : '서버에 연결하는 중…';
    safe(() => views.header.render(slices, status, view));
    if (view === 'setup') safe(() => views.setup.render(slices));
    if (view === 'live') {
        for (const k of ['pending', 'scores', 'undo', 'queue', 'goal', 'tabs']) safe(() => views[k].render(slices));
    }
    // 머리줄 높이 — 오른쪽 칸(대기함)을 머리줄 바로 아래에 붙여 두는 데 쓴다
    const hh = $('hdr').offsetHeight;
    if (hh && hh !== render._hh) { render._hh = hh; document.documentElement.style.setProperty('--hdr-h', hh + 'px'); }
}

function safe(fn) {
    try { fn(); } catch (e) { console.error('[조종실]', e); }
}

window.addEventListener('resize', schedule);
// 경과 시간(머리줄)만 30초마다
setInterval(() => safe(() => views.header.tick()), 30000);
