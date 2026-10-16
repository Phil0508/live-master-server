/* 🧱 틀 탭(시안 B 왼쪽 줄) — 랭킹(첫 화면) · 로그 · 전광판 · 설정 · 백업.
   - 랭킹(home): 그리는 탭이 아니다. 방송 중엔 #home(숫자 카드 · 점수판 · 기본 설정), 방송 전엔 #v-setup(방송 준비).
   - 로그(logs): 옛 오른쪽 아래 '최근 기록' 칸(section#logs — undo.js 가 그린다)을 이 탭 안으로 옮긴다(다시 만들지 않는다).
   - 전광판(sigdisp): 출연진 전광판 화면(/overlay/?only=sig — 방송판과 같은 서버, 로그인 없이 열리는 화면) 여는 길 · 주소 복사.
   - 설정(settings): panels/settings_menu.js
   - 백업(restore): ⏪ 방송 끝 되돌리기(endundo.js) — 방송 준비 화면 맨 위 상자와 같은 것. 방송을 잘못 끝냈을 때 12시간 안. */
import { h } from '../util.js';
import { mountEndUndo, endUndoView } from '../endundo.js';
import { SETTINGS_PANEL } from './settings_menu.js';

const SIGDISP = '/overlay/?only=sig';

function mountLogs(el) {
    const sec = document.getElementById('logs');
    el.classList.add('fr-logs');
    if (sec) { el.append(sec); sec.hidden = false; }
    else el.append(h('p', { class: 'empty' }, '기록 칸을 못 찾았어요 — 새로 고쳐 주세요'));
    return { render() {} };
}

function mountSigDisp(el, ctx) {
    const url = location.origin + SIGDISP;
    const copy = async (text, what) => {
        try { await navigator.clipboard.writeText(text); ctx.toast(what + ' 주소를 복사했어요', 'ok'); }
        catch (e) { ctx.toast('복사가 막혔어요 — 주소를 길게 눌러 복사해 주세요', 'info'); }
    };
    el.classList.add('fr-sigdisp');
    el.append(
        h('div', { class: 'sec-head' }, h('h2', null, '🖼️ 출연진 전광판')),
        h('p', { class: 'muted' }, '출연자들이 보는 화면이에요 — 지금 나오는 시그니처 카드를 크게 보여 줘요. 소리는 안 나요(소리는 방송판이 냅니다).'),
        h('div', { class: 'fr-row' },
            h('a', { class: 'btn pri', href: SIGDISP, target: '_blank', rel: 'noopener' }, '새 창으로 열기'),
            h('a', { class: 'btn', href: SIGDISP + '&transparent=1', target: '_blank', rel: 'noopener' }, '투명 바탕으로 열기(OBS 용)')),
        h('div', { class: 'fr-url' }, h('code', null, url),
            h('button', { type: 'button', class: 'btn sm', onclick: () => copy(url, '전광판') }, '주소 복사')),
        h('p', { class: 'muted small' }, '출연자 모니터 · 태블릿에서 이 주소를 열어 두면 돼요. 붙어 있는지는 설정 → 시스템에서 볼 수 있어요.'));
    return { render() {} };
}

function mountRestore(el, ctx) {
    const note = h('p', { class: 'muted fr-note' });
    const box = h('div', { class: 'fr-restore' });
    el.classList.add('fr-restore-panel');
    el.append(
        h('div', { class: 'sec-head' }, h('h2', null, '⏪ 백업 — 방송 끝 되돌리기')),
        h('p', { class: 'muted' }, '[방송 끝] 을 잘못 눌렀을 때, 끝낸 지 12시간 안이면 끝내기 직전으로 되살려요. ' +
            '점수판 · 대기함 · 점수 기록 · 시그니처 대기줄 · 무대가 돌아오고, 끝낸 뒤 들어온 후원도 잃지 않아요.'),
        box, note);
    const eu = mountEndUndo(box, ctx);
    const nowSec = () => (ctx.lm && ctx.lm.serverNow ? ctx.lm.serverNow() : Date.now()) / 1000;
    return {
        render(slices) {
            eu.render(slices);
            const live = !!((slices || {}).session || {}).live;
            const v = endUndoView((slices || {}).endundo, nowSec());
            const t = v.show ? '' : live ? '지금은 방송 중이에요 — 방송을 끝낸 뒤에만 쓸 수 있어요.' : '지금 되살릴 방송이 없어요.';
            if (note.textContent !== t) note.textContent = t;
            note.hidden = !t;
        },
    };
}

export const FRAME_PANELS = [
    { id: 'home', label: '랭킹', short: '랭킹', icon: '🏆', rail: true, pre: true, home: true },
    { id: 'logs', label: '로그', short: '로그', icon: '📜', rail: true, mount: mountLogs },
    { id: 'sigdisp', label: '출연진 전광판', short: '전광판', icon: '🖼️', rail: true, pre: true, mount: mountSigDisp },
    SETTINGS_PANEL,
    { id: 'restore', label: '백업', short: '백업', icon: '⏪', rail: true, pre: true, mount: mountRestore },
];
