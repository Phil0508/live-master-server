/* 🎛 조종실 시작점 — 연결 하나를 열고, 조각(slice)이 바뀔 때마다 화면을 다시 맞춘다.

   흐름
     LM.connect → 통째(snapshot) → 바뀐 조각(patch)만 계속
     로그인 안 됨 → 로그인 화면 · 방송 전(session.live = false) → 방송 준비 · 방송 중 → 운영 화면
   틀(시안 B 10-17 — index.html 의 칸 id 약속)
     #hdr 머리 두 줄(header.js) · #v-shell = #rail 왼쪽 줄(tabs.js) · #center 가운데 · #side 오른쪽 · #drawer 폰 서랍
     방송 전에도 세 칸이 보인다 — 가운데 '랭킹' 자리에 #v-setup(방송 준비), 오른쪽에 점검표. 탭은 pre 표시가 있는 것만 열린다.
   그리기
     조각이 몇 개 한꺼번에 와도 한 번만 그린다(같은 순간의 쪽지를 모아서).
     각 칸은 '바뀐 것만' 고친다 — 통째로 innerHTML 을 갈면 입력 중인 칸 · 누르려던 단추가 날아간다
     (옛 조종실 renderUI 는 그래서 입력칸에 커서가 있으면 그리기를 통째로 건너뛰었고, 그 사이 들어온 후원이 안 보였다).
   다음 작업자 자리 — 아래 [B] [C] [D] 주석 줄을 자기 줄만 채운다(같은 줄을 두 사람이 고치지 않게). */
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
import { FRAME_PANELS } from './panels/frame.js';     // 🧱 랭킹 · 로그 · 전광판 · 설정 · 백업(왼쪽 줄 틀 탭)
import { PANELS as GAME_PANELS } from './panels/games.js';
import { PANELS as TOOL_PANELS } from './panels/tools.js';
import { mountPhone } from './phone.js';     // 📱 폰 손보기(새 후원 띠 · 탭 줄) · 방송 전 시그니처 관리 바로가기
import { mountCastBox } from './castbox.js'; // 💬 화면에 한마디 · ⬆ UP 자막 — 오른쪽 칸 맨 위(#say-slot)
import { mountKpis } from './kpis.js';         // 🔢 숫자 카드 4장 · 💱 정산 차액(랭킹 탭)
import { mountStagebar } from './stagebar.js'; // 🎬 무대 줄 · 순서표 · 진행 중인 판 단추(탭을 바꿔도 남는다)
import { mountDrawer } from './drawer.js';   // [C] 🗄 오른쪽 칸 자리(되돌리기 · 콘솔 미니) · 📱 폰 아래 서랍
import { mountCmdk } from './cmdk.js';                 // [D] import { mountCmdk } — ⌨️ Ctrl+K 빠른 명령(w2feat 채움)
import { mountRxSwitch } from './rxswitch.js';         // [D] import { mountRxSwitch } — 🙈 조종 줄 리액션 모드 스위치(w2feat 채움)
import { bindBgm } from './panels/records/bgm.js';     // [D] 🎵 조종 줄 BGM ▶ 가 BGM 탭을 미리 그리게(ctx.tabs.prepare)
import { syncHoldBand } from './panels/auto/holdband.js'; // 🙋 자동 진행 '⏸ 보류' 카드 → 상태 줄 띠(소리 없음, 10-17)
import { guardRun, askBig } from './bigok.js';           // 🛡️ 큰 금액은 한 번 더 확인 — 점수가 들어가는 명령은 ctx.run 한 곳에서 거른다(10-17 bigok)
import { mountRest } from './restmode.js';
import { syncPracticeBand } from './practiceband.js';   // 🎓 연습 중 띠 · 연습 중 진짜 후원 빨간 띠(10-19 /practice/)            // ☕ 휴식 모드 — 새 입금 · 보류가 오면 가장자리 초록 깜빡 · 가운데 카드(소리 없음, 10-17)

const lm = window.LM.connect({ kind: 'controller' });
let status = 'connecting', snapped = false, slices = {}, scheduled = false;

const ctx = {
    lm,
    toast,
    confirm: confirmBox,
    run: makeRun(lm, () => { toast('로그인이 풀렸어요 — 다시 들어가 주세요', 'err'); setTimeout(() => location.reload(), 1500); }),
    rerender: schedule,
    get slices() { return slices; },
    tabs: null,               // mountTabs 뒤에 채운다 — ctx.tabs.open('ops-stage') 처럼 탭을 연다
};
// 🛡️ 대기함 · 추천 · 나눠 주기 · 폰 서랍 · AI 카드 · 손 점수 · Ctrl+K — 모두 ctx.run 을 지나므로 여기서 한 번에 묻는다.
//    이미 물어본 길은 ctx.run(type, data, {bigOk: true}). 오토파일럿(via 'ap')은 묻지 않는다(js/bigok.js 맨 위).
ctx.run = guardRun(ctx.run, () => slices, needs => askBig(ctx, needs),
    () => toast('취소했어요 — 점수는 그대로예요', 'info'));

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
    tabs: mountTabs({ rail: $('rail'), body: $('tabbody'), center: $('center') }, ctx, [...FRAME_PANELS, ...GAME_PANELS, ...TOOL_PANELS]),
    kpis: mountKpis($('kpis'), ctx),
    stagebar: mountStagebar($('stagebar'), ctx),
    drawer: mountDrawer(ctx),     // [C] pending · undo 를 옮기므로 그 둘 뒤에
};
ctx.tabs = views.tabs;
safe(() => mountPhone(ctx));               // 📱 phone.js — 넘어져도 조종실은 그대로
safe(() => mountCastBox(ctx));             // 💬 castbox.js — 넘어져도 조종실은 그대로
safe(() => mountCmdk(ctx));                // [D] safe(() => mountCmdk(ctx)); — ⌨️ Ctrl+K(w2feat 채움)
safe(() => mountRxSwitch($('ctl-rx'), ctx)); // [D] 🙈 리액션 모드 스위치(#ctl-rx)
safe(() => bindBgm(ctx));                  // [D] 🎵 BGM — 조종 줄 ▶ · 제목 누르기
let rest = null;
safe(() => { rest = mountRest(ctx); });   // ☕ 조종 줄 [☕ 휴식](#ctl-rest) — header 뒤에(.cb 에 붙는다)

// 방송 중에만 그리는 칸 — 한 줄에 하나씩(다음 작업자가 자기 줄만 더한다)
const LIVE = [
    'pending', 'scores', 'undo', 'queue', 'goal',
    'kpis', 'stagebar',
    'drawer',     // [C]
];

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
    if (view === 'live') for (const k of LIVE) if (views[k]) safe(() => views[k].render(slices));
    safe(() => syncHoldBand(slices, view));
    safe(() => syncPracticeBand(slices, ctx));
    if (rest) safe(() => rest.render(slices, view));
    // 탭은 방송 전에도(열린 탭만 그리므로 가볍다) — 방송 전엔 pre 표시가 있는 탭만 열린다
    if (view === 'setup' || view === 'live') safe(() => views.tabs.render(slices, view));
    // 머리 높이 — PC 는 세 칸 높이 · 왼쪽 줄 자리, 폰은 탭 줄을 머리 밑에 붙이는 데 쓴다
    const hh = $('hdr').offsetHeight;
    if (hh && hh !== render._hh) { render._hh = hh; document.documentElement.style.setProperty('--hdr-h', hh + 'px'); }
}

function safe(fn) {
    try { fn(); } catch (e) { console.error('[조종실]', e); }
}

window.addEventListener('resize', schedule);
// 머리 높이가 바뀌면(경보 띠 · 오토파일럿 띠 · 폭) 다시 잰다 — 왼쪽 줄 자리 · 폰 탭 줄이 따라온다
if ('ResizeObserver' in window) new ResizeObserver(() => schedule()).observe($('hdr'));
// 경과 시간 · 시계(머리줄)만 30초마다
setInterval(() => safe(() => views.header.tick()), 30000);
