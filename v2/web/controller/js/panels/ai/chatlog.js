/* 💬 AI 대화 기록 — 이 컴퓨터(localStorage)에만 둔다. 서버는 기억하지 않는다(화면 약속 3).
   새로 고쳐도 남고, [지우기] 로 비운다. 마지막 60개만 남긴다(옛 것은 40개).

   한 줄 = {id, role, text, source?, at}
     role  user(내가 물은 것) · ai(답 — source: calc ⚡ 서버 계산 · ai 🤖 AI · none ℹ️ 안내)
           sys(가운데 작은 글 — 명령 결과 · 오토파일럿 기록) · alert(🔔 먼저 알림)
   ⚠️ 서버에 '직전 대화' 로 보내는 것은 user · ai 줄만, 말만(source 같은 화면용 꼬리표는 뺀다).
   🔴 안 읽은 알림 수 — AI 탭이 안 보일 때 들어온 알림 · 오토파일럿 기록을 탭 단추 옆 숫자로 보여 준다. */
import { aiTabVisible } from './common.js';

const KEY = 'lm2_ai_chat';
const MAX = 60;
let rows = load();
let seq = 0;
let unread = 0;
const subs = new Set();

function load() {
    try {
        const v = JSON.parse(localStorage.getItem(KEY) || '[]');
        return Array.isArray(v) ? v.filter(r => r && typeof r.text === 'string' && r.role).slice(-MAX) : [];
    } catch (e) { return []; }
}
function save() {
    try { localStorage.setItem(KEY, JSON.stringify(rows.filter(r => !r.temp).slice(-MAX))); } catch (e) { /* 개인 창 등 — 기억 못 해도 된다 */ }
}
function notify(kind, row) {
    subs.forEach(fn => { try { fn(kind, row); } catch (e) { console.error('[AI 대화]', e); } });
}

export function all() { return rows; }
export function subscribe(fn) { subs.add(fn); return () => subs.delete(fn); }

/** 한 줄 더하기. temp = 아직 답을 기다리는 '생각 중…' 줄(저장 안 함) */
export function add(role, text, extra) {
    const row = Object.assign({ id: 'c' + Date.now().toString(36) + (seq++), role, text: String(text || ''), at: Date.now() }, extra || {});
    rows.push(row);
    if (rows.length > MAX + 10) rows = rows.slice(-MAX);
    if (!row.temp) save();
    if ((role === 'alert' || row.notify) && !aiTabVisible()) setUnread(unread + 1);
    notify('add', row);
    return row;
}

/** 줄 고치기 — '생각 중…' 을 답으로 바꿀 때 */
export function update(row, patch) {
    Object.assign(row, patch || {});
    if (!row.temp) save();
    notify('update', row);
}

export function clear() {
    rows = [];
    save();
    notify('clear', null);
}

/** 서버에 보낼 직전 대화 — user · ai 줄만, 마지막 n 개 */
export function history(n) {
    return rows.filter(r => !r.temp && (r.role === 'user' || r.role === 'ai'))
        .slice(-n).map(r => ({ role: r.role === 'ai' ? 'assistant' : 'user', content: r.text }));
}

/* ── 안 읽은 알림 ── 탭 단추(tabs.js 가 만든 것)에 작은 숫자를 붙인다 */
export function setUnread(n) {
    unread = Math.max(0, n);
    const b = document.querySelector('.tabbar .tab[data-tab="ai"]');
    if (!b) return;
    let dot = b.querySelector('.ai-unread');
    if (!unread) { if (dot) dot.remove(); return; }
    if (!dot) {
        dot = document.createElement('span');
        dot.className = 'ai-unread';
        dot.setAttribute('aria-label', '안 읽은 AI 알림');
        b.append(dot);
    }
    dot.textContent = unread > 9 ? '9+' : String(unread);
}
export function readAll() { if (unread) setUnread(0); }
