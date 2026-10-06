/* 🧰 조종실 작은 도구 — 글자 만들기 · 숫자 · 알림(토스트) · 확인 창 · 명령 보내기.
   ⚠️ alert() · confirm() · prompt() 는 쓰지 않는다 — 방송 PC 에서 창이 OBS 뒤로 숨거나
      페이지 전체를 멈춰 세운다. 확인은 화면 안의 상자(confirmBox)로 묻는다. */

/* 🧯 빈칸 거르기 — el.replaceChildren(a, 조건 ? b : null) 처럼 넘기면 브라우저가 'null' 글자를 그대로 넣는다
   (10-07 룰렛 결과 줄에 'nullnull' 이 찍혔다). 조건부 자식을 넘기는 곳이 많아 한 곳에서 거른다 — null · undefined · false 만 뺀다. */
for (const name of (typeof Element === 'undefined' ? [] : ['replaceChildren', 'append', 'prepend'])) {
    const orig = Element.prototype[name];
    if (orig && !orig.__lmSafe) {
        const safe = function (...kids) { return orig.apply(this, kids.filter(k => k != null && k !== false)); };
        safe.__lmSafe = true;
        Element.prototype[name] = safe;
    }
}

/** 요소 만들기 — h('button', {class:'btn', onclick: fn}, '글자', 다른요소…)
 *  ⚠️ 사람 이름 · 메시지 같은 바깥 글자는 반드시 여기(textContent)로 넣는다. innerHTML 로 넣으면 안 된다. */
export function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    if (attrs) {
        for (const [k, v] of Object.entries(attrs)) {
            if (v == null || v === false) continue;
            if (k === 'class') el.className = v;
            else if (k === 'text') el.textContent = v;
            else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
            else if (k === 'dataset') Object.assign(el.dataset, v);
            else if (v === true) el.setAttribute(k, '');
            else el.setAttribute(k, String(v));
        }
    }
    for (const kid of kids.flat(Infinity)) {
        if (kid == null || kid === false || kid === '') continue;
        el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
    }
    return el;
}

export const $ = (sel, root = document) => root.querySelector(sel);

/** 1234567 → '1,234,567' */
export const num = n => Number(n || 0).toLocaleString('ko-KR');
/** 30000 → '₩30,000' */
export const won = n => '₩' + num(n);
/** +5 · −3 (빼기는 눈에 잘 띄는 긴 줄표) */
export const signed = n => (Number(n) < 0 ? '−' + num(Math.abs(n)) : '+' + num(n));

/** 원 → 점수 — 서버 rules.man_won 과 같다: (금액 + 4000) // 10000. 5,999 → 0 · 6,000 → 1 · 16,000 → 2 */
export function manWon(amount) {
    const a = Math.trunc(Number(amount) || 0);
    return Math.floor((a + 4000) / 10000);
}

/** 나눠 주기 — 서버 rules.split_points 와 같다: 똑같이 나누고 남는 점수는 앞사람부터 1점씩 */
export function splitPoints(total, n) {
    if (n <= 0) return [];
    const t = Math.trunc(Number(total) || 0);
    const base = Math.floor(t / n), rem = t - base * n;
    return Array.from({ length: n }, (_, i) => base + (i < rem ? 1 : 0));
}

/** 시각 — 대기함은 ms, 점수 기록은 초로 온다. 둘 다 받는다 */
export function clock(at, withSec) {
    const n = Number(at) || 0;
    if (!n) return '';
    const d = new Date(n < 1e12 ? n * 1000 : n);
    const p = x => String(x).padStart(2, '0');
    return p(d.getHours()) + ':' + p(d.getMinutes()) + (withSec ? ':' + p(d.getSeconds()) : '');
}

/** '+5' · '-3' · '5' · '−3' → 정수. 숫자가 아니면 null */
export function parseDelta(s) {
    const t = String(s || '').trim().replace(/[−–—]/g, '-').replace(/[,\s]/g, '');
    if (!/^[+-]?\d{1,7}$/.test(t)) return null;
    return parseInt(t, 10);
}

/* ── 알림(토스트) ── 화면 아래쪽에 잠깐 떴다 사라진다. 실패는 더 오래, 빨갛게. */
let toastBox = null;
export function toast(msg, kind = 'ok', ms) {
    if (!toastBox) {
        toastBox = h('div', { class: 'toasts', 'aria-live': 'polite', role: 'status' });
        document.body.append(toastBox);
    }
    const icon = kind === 'err' ? '!' : kind === 'info' ? 'i' : '✓';
    const t = h('div', { class: 'toast ' + kind }, h('span', { class: 'ti', 'aria-hidden': 'true' }, icon), h('span', { class: 'tm' }, msg));
    t.addEventListener('click', () => t.remove());
    toastBox.append(t);
    while (toastBox.children.length > 3) toastBox.firstChild.remove();     // 많이 쌓이면 점수판을 가린다
    setTimeout(() => { t.classList.add('out'); setTimeout(() => t.remove(), 300); }, ms || (kind === 'err' ? 6500 : 3200));
}

/* ── 확인 상자 ── 지우기 · 끝내기 같은 되돌리기 어려운 일 앞에서 한 번 묻는다.
   ⚠️ 기본 손가락 자리는 [취소] — Enter 를 습관처럼 눌러도 지워지지 않게. Esc · 바깥 누르기 = 취소. */
export function confirmBox({ title, body, ok = '확인', cancel = '취소', danger = true }) {
    return new Promise(resolve => {
        const prev = document.activeElement;
        const okBtn = h('button', { class: 'btn big ' + (danger ? 'danger' : 'pri'), type: 'button' }, ok);
        const noBtn = h('button', { class: 'btn big', type: 'button' }, cancel);
        const card = h('div', { class: 'modal', role: 'alertdialog', 'aria-modal': 'true', 'aria-labelledby': 'mdl-t' },
            h('h2', { id: 'mdl-t' }, title),
            body ? h('p', { class: 'modal-body' }, body) : null,
            h('div', { class: 'modal-btns' }, noBtn, okBtn));
        const wrap = h('div', { class: 'modal-wrap' }, card);
        function close(v) {
            document.removeEventListener('keydown', onKey, true);
            wrap.remove();
            try { prev && prev.focus && prev.focus(); } catch (e) { /* 무시 */ }
            resolve(v);
        }
        function onKey(e) {
            if (e.key === 'Escape') { e.preventDefault(); close(false); }
            else if (e.key === 'Tab') {             // 상자 밖으로 초점이 나가지 않게
                e.preventDefault();
                (document.activeElement === okBtn ? noBtn : okBtn).focus();
            }
        }
        okBtn.addEventListener('click', () => close(true));
        noBtn.addEventListener('click', () => close(false));
        wrap.addEventListener('click', e => { if (e.target === wrap) close(false); });
        document.addEventListener('keydown', onKey, true);
        document.body.append(wrap);
        noBtn.focus();
    });
}

/** 명령 보내기 — 실패하면 서버가 준 까닭을 빨간 알림으로 보여 준다. 결과는 그대로 돌려준다. */
export function makeRun(lm, onNeedLogin) {
    return async function run(type, data, opts = {}) {
        let res;
        try { res = await lm.cmd(type, data || {}); } catch (e) { res = { ok: false, error: '보내지 못했습니다 — 다시 눌러 주세요' }; }
        res = res || { ok: false, error: '응답이 없습니다' };
        if (!res.ok) {
            if (Number(res.code) === 401 && onNeedLogin) onNeedLogin();
            if (!opts.quiet) toast(res.error || '실패했습니다', 'err');
        }
        return res;
    };
}
