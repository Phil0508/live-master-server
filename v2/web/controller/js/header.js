/* 🧭 머리 두 줄 — 시안 B(10-17). 보는 것과 누르는 것을 위아래로 나눴다.
   1줄 상태 줄(.sb — 보기만): 로고 · 서버 연결 · [방송 화면] [후원 받기] [계좌] 점 · 자동 진행 · 경보 띠(#sb-band) · 방송 중 N분 · 시계 · [방송 끝]
   2줄 조종 줄(.cb — 누르기만, 로그인 뒤에만):
        #ctl-bgm  BGM(panels/records/bgm.js 미니 — 영상이 올라와 있을 때만, 없으면 [BGM 고르기])  ← [D] 가 시안 모양으로
        #ctl-sig  시그: #ctl-rx(리액션 모드 스위치 — [D]) · 시그 소리 · 중단 · 건너뛰기(queue.js — [C])
        #ctl-misc 클립(clipbtn.js) · 에디터(새 창 /controller/editor/)
        [🔍 찾기] — Ctrl+K 상자(cmdk.js)를 연다('lm:cmdk'). 폰은 단축키가 없어 이 단추가 길 — 조종 줄이 꽉 차서 상태 줄 오른쪽 끝으로 옮긴다(10-24)
        [⋯ 더보기] — 폰(900 아래)에서만. BGM · 클립 · 에디터 · 방송 끝 · 로그아웃을 아래에서 올라오는 판(#ctl-more)으로 옮긴다
                   (노드를 옮긴다 — 다시 만들지 않아 누르는 길 · 클릭 기록이 그대로). 시그 소리 막대 자리는 #ctl-more-sig([C]).
   [방송 끝] 은 점수판 · 대기함 · 시그니처 대기줄을 비운다(서버 session.end) → 화면 안 확인 상자로 한 번 묻는다.
   ⚠️ 경보 · 알림에 소리 없음(alarm.js · bankext.js). ⚠️ 로그인 전(연결 중 · 로그인)에는 연결 점만 — 비공개 값을 그리지 않는다.
   💰 이번 방송 후원 알약은 뺐다 — 숫자 카드 ①(kpis.js, [B])로 간다. */
import { h, clock } from './util.js';
import { icon } from './icons.js';
import { mountAlarm } from './alarm.js';
import { mountBgmMini } from './panels/records/bgm.js';
import { mountClipButton } from './clipbtn.js';            // ✂️ 어느 탭에서든 클립(옛 머리줄 단추)
import { mountAutoPill } from './panels/auto/pill.js';     // ☕ 휴식 중일 때만 표시 — 누르면 학습 · 휴식 탭
import { mountBankAlarm } from './bankext.js';            // 🏦 은행 확장 점 · 계좌 입금 띠(로그인한 조종실에만)
import { logout } from './panels/settings_menu.js';

const PHONE = '(max-width: 899px)';
const CONN = {
    connecting: ['connecting', '서버 연결 중', '연결 중'],
    live: ['live', '서버 연결', '연결'],
    down: ['down', '서버 끊김 · 다시 붙는 중', '끊김'],
};

export function mountHeader(root, ctx) {
    // ── 1줄: 상태 줄 ──
    const brand = h('div', { class: 'brand' }, h('span', { class: 'logo', 'aria-hidden': 'true' }), h('b', null, '조종실'));
    const conn = h('span', { class: 'st conn', 'data-s': 'connecting', title: '서버와의 실시간 연결' },
        h('i', { class: 'dot', 'aria-hidden': 'true' }), h('span', { class: 't' }, '서버 연결 중'), h('span', { class: 'ts' }, '연결 중'));
    const dots = h('div', { class: 'sb-dots', id: 'sb-dots' }, conn);
    const band = h('div', { class: 'sb-band', id: 'sb-band', hidden: true });
    const sinceL = h('span', { class: 'since' }), sinceS = h('span', { class: 'since-s' });
    const onair = h('span', { class: 'st onair', hidden: true },
        h('i', { class: 'dot', 'aria-hidden': 'true' }), h('b', { class: 'onair-t' }, '방송 중 ', sinceL, sinceS));
    const clockEl = h('span', { class: 'sb-clock', hidden: true, 'aria-label': '지금 시각' });
    const endBtn = h('button', { class: 'btn xs dgr end-btn', type: 'button', hidden: true }, '방송 끝');
    const endSlot = h('span', { class: 'end-slot' }, endBtn);
    const sbr = h('div', { class: 'sbr' }, onair, clockEl, endSlot);
    const sb = h('div', { class: 'sb' }, h('div', { class: 'sb-l' }, brand, dots), band, sbr);

    // ── 2줄: 조종 줄 ──
    const gcap = t => h('span', { class: 'gcap', 'aria-hidden': 'true' }, t);
    const bgmPick = h('button', { type: 'button', class: 'btn sm cb-bgm-pick', title: 'BGM 탭 열기',
        onclick: () => { closeSheet(); if (ctx.tabs) ctx.tabs.open('bgm'); } }, icon('bgm'), 'BGM 고르기');
    const ctlBgm = h('div', { class: 'cb-grp cb-bgm', id: 'ctl-bgm', role: 'group', 'aria-label': 'BGM' }, gcap('BGM'), bgmPick);
    const ctlRx = h('div', { class: 'cb-rx', id: 'ctl-rx' });                        // [D] 리액션 모드 스위치(rxswitch.js)
    const ctlSig = h('div', { class: 'cb-grp cb-sig', id: 'ctl-sig', role: 'group', 'aria-label': '시그니처' }, gcap('시그'), ctlRx);   // [C] 시그 소리 · 중단 · 건너뛰기
    const editor = h('a', { class: 'btn sm cb-editor', href: '/controller/editor/', target: '_blank', rel: 'noopener', title: '방송판 배치 편집기 — 새 창' },
        icon('edit'), '에디터');
    const ctlMisc = h('div', { class: 'cb-grp cb-misc', id: 'ctl-misc', role: 'group', 'aria-label': '클립 · 에디터' }, editor);
    const moreBtn = h('button', { type: 'button', class: 'btn cb-more', 'aria-expanded': 'false', 'aria-controls': 'ctl-more', title: 'BGM · 클립 · 에디터 · 방송 끝 · 로그아웃' },
        icon('more'), h('span', { class: 'cb-more-t' }, '더보기'));
    // 🔍 찾기 — Ctrl+K 상자(cmdk.js)를 연다. 폰은 키보드 단축키가 없어서 이 단추가 들어가는 길(폰은 상태 줄 오른쪽 끝 — place())
    const findBtn = h('button', { type: 'button', class: 'btn sm cb-find', title: '무엇이든 찾기 · 말로 시키기 (Ctrl+K)', 'aria-label': '찾기 (Ctrl+K)',
        onclick: () => { closeSheet(); document.dispatchEvent(new CustomEvent('lm:cmdk')); } },
        icon('search'), h('span', { class: 'cb-find-t' }, '찾기'), h('kbd', { class: 'cb-find-k', 'aria-hidden': 'true' }, 'Ctrl K'));
    const sepSig = h('span', { class: 'vsep', 'aria-hidden': 'true' });
    const sepMisc = h('span', { class: 'vsep', 'aria-hidden': 'true' });
    const cb = h('div', { class: 'cb', hidden: true }, ctlBgm, sepSig, ctlSig, sepMisc, ctlMisc, findBtn, moreBtn);

    // ── ⋯ 판(폰) ──
    const sheetBgm = h('div', { class: 'cbs-row cbs-bgm' }, h('small', { class: 'cbs-cap' }, 'BGM — 이 기기(폰)에서 소리가 나요'));
    const sheetSig = h('div', { class: 'cbs-row', id: 'ctl-more-sig' });                // [C] 시그 소리 막대
    const sheetMisc = h('div', { class: 'cbs-row cbs-misc' });
    const sheetEnd = h('div', { class: 'cbs-row cbs-end' });
    const outBtn = h('button', { type: 'button', class: 'btn sm cbs-logout', onclick: () => { closeSheet(); logout(ctx); } }, icon('logout'), '로그아웃');
    const sheetPanel = h('div', { class: 'cbs-panel', role: 'dialog', 'aria-label': '더보기' },
        h('div', { class: 'cbs-grab', 'aria-hidden': 'true' }),
        sheetBgm, sheetSig, sheetMisc, sheetEnd,
        h('div', { class: 'cbs-row cbs-foot' }, outBtn, h('button', { type: 'button', class: 'btn sm', onclick: () => closeSheet() }, '닫기')));
    const sheet = h('div', { class: 'cb-sheet', id: 'ctl-more', hidden: true }, sheetPanel);
    sheet.addEventListener('click', e => { if (e.target === sheet) closeSheet(); });

    root.replaceChildren(sb, cb, sheet);

    function openSheet() { sheet.hidden = false; moreBtn.setAttribute('aria-expanded', 'true'); }
    function closeSheet() { sheet.hidden = true; moreBtn.setAttribute('aria-expanded', 'false'); }
    moreBtn.addEventListener('click', () => (sheet.hidden ? openSheet() : closeSheet()));
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && !sheet.hidden) closeSheet(); });

    const alarm = mountAlarm(dots, band, ctx);             // 점 두 개 · 경보 띠(#sb-band)
    const bankAlarm = mountBankAlarm(null, root, ctx);    // '계좌' 점은 그 두 점 옆 · 띠는 같은 경보 띠에
    const bgm = mountBgmMini(ctlBgm);
    const bgmMini = ctlBgm.querySelector('.bgm-mini');
    if (bgmMini) ctlBgm.insertBefore(bgmMini, bgmPick);    // 'BGM' 글자 뒤로
    const autoPill = mountAutoPill(dots);                  // 점 줄 끝
    const clipBtn = mountClipButton(ctlMisc, ctx);         // 클립 · 에디터 순서(방송 중에만)
    // 🧪 시험판(서버 LM2_TRIAL) — 옛 프로그램과 같이 쓰는 기능(시그니처 보관소 · 리스너 설정 · 서버 버전)이 잠겨 있다는 표시
    fetch('/api/health', { cache: 'no-store' }).then(r => r.json()).then(hh => {
        if (!hh || !hh.trial) return;
        const t = document.createElement('span');
        t.className = 'pill trial';
        t.title = '시험판 — 지금 방송 중인 옛 프로그램과 같이 쓰는 것(시그니처 등록 · 지우기, 투네이션 테스트 계정, 서버 버전 바꾸기)은 잠가 뒀어요. 나머지는 마음껏 눌러 보셔도 돼요.';
        t.textContent = '🧪 시험판';
        brand.append(t);
    }).catch(() => {});

    // 폰 ↔ 넓은 화면 — BGM · 클립/에디터 · [방송 끝] 을 ⋯ 판과 제자리 사이에서 옮긴다
    const mq = window.matchMedia ? matchMedia(PHONE) : { matches: false };
    function place() {
        if (mq.matches) {
            if (ctlBgm.parentNode !== sheetBgm) sheetBgm.append(ctlBgm);
            if (ctlMisc.parentNode !== sheetMisc) sheetMisc.append(ctlMisc);
            if (endBtn.parentNode !== sheetEnd) sheetEnd.append(endBtn);
            if (findBtn.parentNode !== sb) sb.append(findBtn);          // 🔍 폰: 조종 줄이 꽉 차서 상태 줄 오른쪽 끝(css 가 셋째 칸으로)
        } else {
            if (ctlBgm.parentNode !== cb) cb.insertBefore(ctlBgm, sepSig);
            if (ctlMisc.parentNode !== cb) cb.insertBefore(ctlMisc, moreBtn);
            if (findBtn.parentNode !== cb) cb.insertBefore(findBtn, ctlMisc.nextSibling);
            if (endBtn.parentNode !== endSlot) endSlot.append(endBtn);
            closeSheet();
        }
    }
    place();
    if (mq.addEventListener) mq.addEventListener('change', () => { place(); if (ctx.rerender) ctx.rerender(); });

    let startedAt = 0, busy = false;

    endBtn.addEventListener('click', async () => {
        if (busy) return;
        closeSheet();
        const s = ctx.slices;
        const pend = (s.pending || []).length;
        const q = ((s.queue || {}).items || []).length;
        const lines = ['점수판 · 기록이 비워지고, 방송판의 점수도 0 으로 돌아갑니다.'];
        if (pend) lines.push(`⚠️ 대기함에 아직 ${pend}건이 남아 있어요 — 끝내면 대기함에서 사라집니다(후원 기록 장부에는 남아요).`);
        if (q) lines.push(`시그니처 대기줄 ${q}개도 멈추고 비워집니다.`);
        lines.push('잘못 끝냈으면 12시간 안에 왼쪽 줄 [백업](또는 방송 준비 화면 맨 위)에서 끝내기 직전으로 되살릴 수 있어요.');
        const ok = await ctx.confirm({ title: '방송을 끝낼까요?', body: lines.join('\n'), ok: '방송 끝내기', cancel: '계속 방송' });
        if (!ok) return;
        busy = true;
        endBtn.disabled = true;
        const res = await ctx.run('session.end', {});
        busy = false;
        endBtn.disabled = false;
        if (res.ok) ctx.toast('방송을 끝냈어요. 수고하셨습니다! (잘못 눌렀으면 왼쪽 줄 [백업])', 'ok');
    });

    function tick() {
        const now = new Date();
        const c = String(now.getHours()).padStart(2, '0') + ':' + String(now.getMinutes()).padStart(2, '0');
        if (clockEl.textContent !== c) clockEl.textContent = c;
        if (!startedAt) { sinceL.textContent = ''; sinceS.textContent = ''; onair.title = ''; return; }
        const min = Math.max(0, Math.floor((Date.now() / 1000 - startedAt) / 60));
        sinceL.textContent = min >= 60 ? `${Math.floor(min / 60)}시간 ${min % 60}분` : `${min}분`;
        sinceS.textContent = `${Math.floor(min / 60)}:${String(min % 60).padStart(2, '0')}`;
        onair.title = `${clock(startedAt)} 시작 · ${sinceL.textContent}째`;
    }

    return {
        render(slices, status, view) {
            const [cls, label, short] = CONN[status] || CONN.connecting;
            if (conn.dataset.s !== cls) {
                conn.dataset.s = cls;
                conn.querySelector('.t').textContent = label;
                conn.querySelector('.ts').textContent = short;
            }
            const authed = view === 'setup' || view === 'live';
            const sess = slices.session || {};
            const live = !!sess.live && view === 'live';
            if (cb.hidden === authed) cb.hidden = !authed;
            if (findBtn.hidden === authed) findBtn.hidden = !authed;      // 🔍 로그인 전엔 안 보인다(폰은 상태 줄에 있다)
            if (!authed) closeSheet();
            onair.hidden = !live;
            endBtn.hidden = !live;
            sheetEnd.hidden = !live;
            clockEl.hidden = !authed;
            const want = live ? (Number(sess.started_at) || 0) : 0;
            if (want !== startedAt) startedAt = want;
            tick();
            // 비어 있는 묶음(아직 아무도 안 채운 시그 칸)은 칸막이와 같이 숨긴다
            const sigEmpty = !ctlRx.children.length && ctlSig.children.length <= 2;
            if (ctlSig.hidden !== sigEmpty) { ctlSig.hidden = sigEmpty; sepSig.hidden = sigEmpty; }
            if (bgmMini) bgmPick.hidden = !bgmMini.hidden;
            // 하나가 넘어져도 머리(연결 · 방송 끝)는 그대로 돌게 따로 감싼다
            try { alarm.render(slices, status, view); } catch (e) { console.error('[점검]', e); }
            try { bankAlarm.render(slices, status, view); } catch (e) { console.error('[계좌 입금 띠]', e); }
            try { bgm.render(slices, view); } catch (e) { console.error('[BGM]', e); }
            try { autoPill.render(slices, view); } catch (e) { console.error('[자동 진행 표시]', e); }
            try { clipBtn.render(slices, view); } catch (e) { console.error('[클립 단추]', e); }
        },
        tick,
    };
}
