/* 🧰 운영 도구 탭(무대 · 공지 · 계좌 · 모금함 · 영상 · 후원 콘솔)이 같이 쓰는 작은 도구.
   ⚠️ 바깥 글자(이름 · 공지 · 주소)는 전부 h()/textContent 로 넣는다 — innerHTML 금지.
   ⚠️ 적는 중인 칸은 서버 값으로 덮지 않는다(setVal) — 옛 조종실은 그리기가 칸을 덮어 글자가 날아갔다. */
import { h, num, won } from '../../util.js';

export { h, num, won };

/** 한글 입력 중(조합 중) Enter 는 무시한다 — 안 그러면 마지막 글자가 두 번 들어가거나 덜 들어간 채 보내진다 */
export function onEnter(input, fn) {
    input.addEventListener('keydown', e => {
        if (e.key !== 'Enter' || e.isComposing || e.keyCode === 229) return;
        e.preventDefault();
        fn(e);
    });
}

/** 적는 중이 아니면 칸 값을 맞춘다 */
export function setVal(input, v) {
    const s = v == null ? '' : String(v);
    if (document.activeElement === input) return;
    if (input.value !== s) input.value = s;
}

/** '1,234' · ' 5000 ' · '-3000' → 정수. 정수가 아니면 null(소수점 · 글자는 오타로 본다) */
export function parseWon(s, allowNeg) {
    const t = String(s == null ? '' : s).trim().replace(/[−–—]/g, '-').replace(/[,\s원₩]/g, '');
    if (!(allowNeg ? /^[+-]?\d{1,10}$/ : /^\+?\d{1,10}$/).test(t)) return null;
    return parseInt(t, 10);
}

/** 자식 갈아 끼우기 — ⚠️ replaceChildren 은 null 을 'null' 글자로 넣는다. 빈 것은 걸러서 넘긴다 */
export function fill(el, ...kids) {
    el.replaceChildren(...kids.flat().filter(k => k != null && k !== false && k !== ''));
}

/** 바뀌었는지 보기 위한 서명 */
export const sigOf = (...xs) => JSON.stringify(xs);

/** 옛 주소(쿠키 로그인)로 보내기 — 답은 {ok, status, data, error}.
 *  v2 옛 주소는 성공을 {status:'success'} 또는 {ok:true} 로 준다 — 둘 다 성공으로 본다. */
export async function api(path, body) {
    try {
        const init = { method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', headers: {}, cache: 'no-store' };
        if (body instanceof FormData) init.body = body;
        else if (body !== undefined) { init.headers['Content-Type'] = 'application/json'; init.body = JSON.stringify(body); }
        const r = await fetch(path, init);
        const data = await r.json().catch(() => ({}));
        const ok = r.ok && (data.ok === true || data.status === 'success');
        return { ok, status: r.status, data, error: ok ? '' : (data.message || data.error || ('실패했어요 (' + r.status + ')')) };
    } catch (e) {
        return { ok: false, status: 0, data: {}, error: '서버에 닿지 않아요 — 다시 눌러 주세요' };
    }
}

/** 영상 주소인가(올린 파일 · 직접 주소) */
export const isUrl = v => /^https?:\/\//i.test(String(v || '').trim());

/** 유튜브 링크 → 영상 번호(11자). 못 알아보면 ''.
 *  ⚠️ 옛 노래방의 '아무 11글자나' 마지막 시도는 뺐다 — 엉뚱한 주소가 영상 번호로 읽혔다. */
export function ytId(raw) {
    const url = String(raw || '').trim();
    if (!url) return '';
    if (/^[A-Za-z0-9_-]{11}$/.test(url)) return url;
    const pats = [/[?&]v=([A-Za-z0-9_-]{11})/, /youtu\.be\/([A-Za-z0-9_-]{11})/, /\/embed\/([A-Za-z0-9_-]{11})/,
                  /\/shorts\/([A-Za-z0-9_-]{11})/, /\/live\/([A-Za-z0-9_-]{11})/];
    for (const p of pats) { const m = url.match(p); if (m) return m[1]; }
    return '';
}

/** 저장된 영상 값 → 칸에 보일 글자(유튜브 번호는 링크 모양으로) */
export const videoText = v => !v ? '' : (isUrl(v) ? v : 'https://youtu.be/' + v);

/** 켜고 끄는 스위치 — {el, set(on), input}. onchange(on) 가 실패하면 스스로 되돌린다(서버 값이 다시 그린다) */
export function switchEl(label, onchange, title) {
    const input = h('input', { type: 'checkbox', role: 'switch' });
    const el = h('label', { class: 'ops-switch', title: title || null }, input, h('span', { class: 'ops-slider', 'aria-hidden': 'true' }), h('span', { class: 'ops-switch-t' }, label));
    let busy = false;
    input.addEventListener('change', async () => {
        if (busy) return;
        busy = true;
        const want = input.checked;
        try { await onchange(want); } finally { busy = false; }
    });
    return { el, input, set(on) { if (!busy && input.checked !== !!on) input.checked = !!on; } };
}

/** 단추 하나를 '보내는 중' 으로 묶는다 — 두 번 눌러도 한 번만 */
export async function once(btn, fn) {
    if (!btn || btn.dataset.busy) return undefined;
    btn.dataset.busy = '1';
    btn.classList.add('wait');
    btn.setAttribute('aria-busy', 'true');
    try { return await fn(); } finally {
        delete btn.dataset.busy;
        btn.classList.remove('wait');
        btn.removeAttribute('aria-busy');
    }
}

/** 모금함 켜기 — 옛 조종실은 스위치 하나(fundjar.enabled = 방송판 깃발)였다.
 *  v2 서버는 fundjar.enabled 와 show.hud.fundjar 가 따로라, 조종실이 둘을 같이 맞춘다. */
export async function setJar(ctx, on) {
    const a = await ctx.run('fundjar.set', { enabled: !!on });
    if (!a.ok) return a;
    const b = await ctx.run('show.hud', { key: 'fundjar', on: !!on });
    return b;
}

/** 블록 제목 */
export function blockHead(title, sub) {
    return h('div', { class: 'ops-bh' }, h('h3', null, title), sub ? h('span', { class: 'ops-sub' }, sub) : null);
}
