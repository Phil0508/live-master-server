/* 💿 시그니처 관리 따로 열기(sig.html) — 조종실 탭(panels/sig/admin.js)을 그대로 얹는다.
   조종실 탭은 방송 중에만 보이므로, 방송 전 · 폰에서 바로 쓰려고 따로 연다(옛 /upload 가 여기로 온다).
   연결은 조종실과 같은 실시간 연결 하나 — 최근 바뀐 것(sig_admin 조각)이 다른 기기와 함께 맞춰진다.
   로그인이 안 돼 있으면 조종실에서 로그인하라고 알려 준다(같은 쿠키라 한 번이면 된다). */
import { h, toast, confirmBox, makeRun } from './util.js';
import { mountSigAdmin } from './panels/sig/admin.js';

const lm = window.LM.connect({ kind: 'controller' });
const root = document.getElementById('sg-root');
const conn = document.querySelector('.conn');
let slices = {}, api = null, snapped = false, scheduled = false;

const ctx = {
    lm,
    toast,
    confirm: confirmBox,
    run: makeRun(lm, () => { toast('로그인이 풀렸어요 — 조종실에서 다시 들어가 주세요', 'err'); }),
    rerender: schedule,
    get slices() { return slices; },
};

const CONN = { connecting: '연결 중', live: '연결됨', down: '끊김 · 다시 붙는 중' };
lm.onStatus(s => {
    if (s === 'live') snapped = true;
    conn.dataset.s = s in CONN ? s : 'connecting';
    conn.querySelector('.t').textContent = CONN[s] || CONN.connecting;
    schedule();
});
lm.on('*', s => { slices = s; schedule(); });

function schedule() {
    if (scheduled) return;
    scheduled = true;
    Promise.resolve().then(() => { scheduled = false; render(); });
}

function render() {
    if (!snapped) return;
    if (!lm.authed) {
        if (!root.querySelector('.sg-login')) {
            root.replaceChildren(h('div', { class: 'card sg-login' },
                h('h1', null, '로그인이 필요해요'),
                h('p', { class: 'muted' }, '조종실에서 비밀번호로 들어간 뒤 다시 열어 주세요. 같은 브라우저면 한 번만 하면 돼요.'),
                h('a', { class: 'btn pri big wide', href: '/controller/' }, '조종실로 가서 로그인')));
        }
        return;
    }
    if (!api) {
        const el = h('div', { class: 'tabpanel sg-solo' });
        root.replaceChildren(el);
        try { api = mountSigAdmin(el, ctx); } catch (e) {
            console.error('[시그니처 관리]', e);
            el.textContent = '화면을 여는 중에 문제가 생겼어요 — 새로 고쳐 주세요';
            return;
        }
    }
    try { api && api.render && api.render(slices); } catch (e) { console.error('[시그니처 관리]', e); }
}
