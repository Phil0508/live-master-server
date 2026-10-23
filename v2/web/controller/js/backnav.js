/* ◀ 뒤로가기(10-24 대표님 '사이트에서 뒤로가기 누르면 자꾸 나가지더라') — 폰 · 브라우저 뒤로가기를 조종실 · 후원 콘솔 안에서 쓴다.

   누를 때마다 차례대로:
     ① 열린 것을 닫는다 — 확인 상자 · 후원자 카드 · 시그니처 고치기 · 찾기 상자(Ctrl+K) · 더보기 · 폰 서랍(펼친 것)
     ② 그 전에 보던 탭으로 돌아간다(탭을 누른 차례대로)
     ③ 첫 화면이면 '뒤로가기를 한 번 더 누르면 나가요' — 바로 또 누르면 정말 나간다(그 사이 화면을 만지면 다시 지킨다)
   구조: 열 때마다 history 에 칸을 하나 쌓고(pushState), 뒤로가기(popstate)는 맨 위 칸을 뺀다 — 이 파일의 stack 이 그 칸들의 짝.
     guard — 맨 아래 지킴 칸(첫 화면에서 바로 나가지 않게). tab — 지나온 탭. layer — 열린 것.
     화면 단추(✕ · 닫기 · 바깥 누르기)로 닫으면 그 칸을 조용히 뺀다(silent back) — 다음 뒤로가기가 헛돌지 않게.
   ⚠️ 크롬은 '사람이 누르지 않았는데 쌓은 칸' 이 있으면 뒤로가기 때 앞 칸을 건너뛴다(뒤로가기 가두기 막기).
      그래서 칸은 사람이 누른 직후(navigator.userActivation.isActive)에만 쌓는다 — 저절로 열린 서랍 같은 것은 안 쌓는다.
   열린 것은 화면을 보고 안다(probes) — 각 화면 파일을 고치지 않는다. 닫을 때는 그 화면의 [닫기] · [취소] 단추를 대신 누른다
   (Esc 를 쏘면 ☕ 휴식 초록 카드처럼 Esc 를 듣는 다른 것까지 같이 닫혀서). 단추를 못 찾으면 Esc. 서랍은 lm:drawer. */

const DOUBLE_MS = 2500;
const PHONE = '(max-width: 899px)';

const shown = sel => { const el = document.querySelector(sel); return !!el && !el.hidden && el.isConnected; };
const esc = () => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }));
/** 그 칸의 닫기 단추를 누른다(여럿이면 맨 위 — 마지막에 붙은 것). 없으면 Esc */
const press = sel => () => { const all = document.querySelectorAll(sel); const b = all[all.length - 1]; if (b) b.click(); else esc(); };
const onPhone = () => !!(window.matchMedia && matchMedia(PHONE).matches);

/* 열린 것들 — 위(먼저 닫을 것)부터. key 는 stack 칸 이름 */
const PROBES = [
    { key: 'modal', open: () => !!document.querySelector('.modal-wrap'), close: press('.modal-wrap .modal-btns > button:first-child') },   // [취소]
    { key: 'donor', open: () => !!document.querySelector('.dk-wrap'), close: press('.dk-wrap .dk-x') },
    { key: 'sigform', open: () => !!document.querySelector('.sg-sheet'), close: press('.sg-sheet .sg-sheet-foot > button:first-child') },   // [닫기]
    { key: 'cmdk', open: () => shown('#cmdk'), close: press('#cmdk .cmdk-close') },
    { key: 'more', open: () => shown('#ctl-more'), close: press('#ctl-more .cbs-foot > button:last-child') },                         // [닫기]
    { key: 'drawer', open: () => onPhone() && !!document.querySelector('#drawer.open'),
      close: () => document.dispatchEvent(new CustomEvent('lm:drawer', { detail: { open: false } })) },
];

const activated = () => !navigator.userActivation || navigator.userActivation.isActive;

let stack = [];            // history 칸의 짝 — {kind:'guard'|'tab'|'layer', key?, from?}
let silent = 0;            // 조용히 뺄 칸 수(화면 단추로 닫은 것)
let cfg = null;
let warnAt = 0;
let syncQueued = false;

function push(item) {
    try { history.pushState({ lmBack: stack.length + 1 }, ''); } catch (e) { return false; }
    stack.push(item);
    return true;
}
function hasLayer(key) { return stack.some(it => it.kind === 'layer' && it.key === key && !it.dead); }

/* 화면을 보고 stack 을 맞춘다 — 새로 열린 것은 칸을 쌓고, 단추로 닫힌 것은 칸을 뺀다 */
function sync() {
    syncQueued = false;
    if (!cfg) return;
    for (const p of PROBES) {
        let open = false;
        try { open = p.open(); } catch (e) { open = false; }
        if (open && !hasLayer(p.key)) {
            if (activated()) { arm(); push({ kind: 'layer', key: p.key }); }
        } else if (!open && hasLayer(p.key)) {
            const top = stack[stack.length - 1];
            if (top && top.kind === 'layer' && top.key === p.key) {
                stack.pop();
                silent++;
                try { history.back(); } catch (e) { silent--; }
            } else {
                stack.forEach(it => { if (it.kind === 'layer' && it.key === p.key) it.dead = true; });   // 위에 탭 칸이 있다 — 뺄 때 건너뛴다
            }
        }
    }
}
function queueSync() { if (!syncQueued) { syncQueued = true; Promise.resolve().then(sync); } }

/** 맨 아래 지킴 칸 — 사람이 처음 만질 때(크롬이 건너뛰지 않게) */
function arm() {
    if (!cfg || stack.some(it => it.kind === 'guard')) return;
    if (!activated()) return;
    // 지킴 칸은 늘 맨 아래 — 위에 쌓인 것이 없을 때만 깐다(있으면 다음 기회에)
    if (stack.length) return;
    push({ kind: 'guard' });
}

function onPop() {
    if (silent > 0) { silent--; return; }
    const top = stack.pop();
    if (!top) { rootWarn(); return; }
    if (top.dead) { try { history.back(); } catch (e) { /* 무시 */ } return; }      // 이미 닫힌 것 — 한 칸 더
    if (top.kind === 'layer') {
        const p = PROBES.find(x => x.key === top.key);
        let open = false;
        try { open = !!(p && p.open()); } catch (e) { open = false; }
        if (open) { try { p.close(); } catch (e) { /* 무시 */ } }
        else { try { history.back(); } catch (e) { /* 무시 */ } }      // 이미 없으면 다음 할 일로
        return;
    }
    if (top.kind === 'tab') {
        try { cfg.goTab(top.from); } catch (e) { console.error('[뒤로가기] 탭 돌아가기 실패:', e); }
        return;
    }
    rootWarn();      // guard
}

function rootWarn() {
    const now = Date.now();
    if (now - warnAt < DOUBLE_MS) return;          // 두 번째 — 지킴 칸이 이미 없다(다음 뒤로가기는 그냥 나간다)
    warnAt = now;
    try { cfg.toast(`◀ 뒤로가기를 한 번 더 누르면 ${cfg.name}에서 나가요`, 'info', DOUBLE_MS); } catch (e) { /* 무시 */ }
}

/**
 * 켜기 — {name: '조종실', toast(msg, kind, ms), goTab(id)}. 한 페이지에 한 번.
 */
export function initBack(opts) {
    if (cfg || typeof history === 'undefined' || !history.pushState) return;
    cfg = opts;
    window.addEventListener('popstate', onPop);
    // 사람이 만질 때 — 지킴 칸 깔기(처음 · '한 번 더 누르면 나가요' 뒤에 다시 만지면 처음부터 다시 지킨다)
    const touch = () => { if (!stack.length) warnAt = 0; arm(); };
    ['pointerdown', 'keydown'].forEach(t => window.addEventListener(t, touch, { capture: true, passive: true }));
    // 열고 닫히는 것 보기 — 몸통 아래 바뀜(상자 붙고 떨어짐 · hidden · class)
    if ('MutationObserver' in window) {
        new MutationObserver(queueSync).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['hidden', 'class'] });
    }
}

/** 탭을 사람이 바꿨다 — 지나온 탭(from)을 칸으로 쌓는다. 뒤로가기로 돌아간 탭은 부르지 않는다 */
export function tabChanged(from, to) {
    if (!cfg || !from || from === to || !activated()) return;
    arm();
    push({ kind: 'tab', from });
}

/* 검사용 */
export const _t = { get stack() { return stack; }, PROBES };
