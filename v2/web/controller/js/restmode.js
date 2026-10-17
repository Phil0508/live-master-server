/* ☕ 휴식 모드 — 조종 줄(위에서 둘째 줄) [☕ 휴식] 단추로 켜고 끈다. 이 기기(브라우저)마다 따로 기억(localStorage — 못 읽으면 끔).
   켜 두면, 새 계좌 입금(bankext.js 가 읽는 /api/bank/ext — onExt 로 같이 받는다) · 새 '🙋 확인할 후원(보류)'(holdband.js heldCards)이 올 때
     ① 화면 가장자리 전체가 초록으로 천천히 깜빡(움직임 줄이기 설정이면 깜빡이지 않고 굵은 테두리)
     ② 가운데 큰 카드 '🏦 계좌 입금 30,000원 · 영원(추정)' + [확인]
     ③ 브라우저 탭 제목이 '🔔 입금 1건 · …' 과 원래 제목을 번갈아
   [확인] 을 누를 때까지 계속, 여러 건이면 건수가 쌓인다. 휴식을 끄면 바로 멈춘다.
   꺼져 있으면 아무것도 안 한다 — 지금처럼 상태 줄 조용한 띠(bankext.js · holdband.js)만.
   ⚠️ 소리 · 진동 · 알림 권한 0. ⚠️ 입금자 실명은 띄우지 않는다(restcore.safeBankName — 추정 닉네임 · 금액만).
   계산은 restcore.js(node 검사). */
import { h } from './util.js';
import { onExt } from './bankext.js';
import { heldCards } from './panels/auto/holdband.js';
import { readRest, writeRest, bankTrack, holdTrack, holdLine, pushAlert, emptyAlert, titleText, cardView, REST_KEY } from './restcore.js';

const BLINK_MS = 1000;      // 탭 제목 번갈아

function store() {
    try { return window.localStorage; } catch (e) { return null; }
}

export function mountRest(ctx) {
    const st = {
        on: readRest(store()),
        authed: false,
        bank: null,          // bankTrack 상태
        hold: null,          // holdTrack 본 것
        alert: emptyAlert(),
        base: document.title,
        phase: false,
        timer: 0,
    };

    // ── 조종 줄 단추 ──
    const lbl = h('span', { class: 'rest-t' }, '휴식');
    const state = h('span', { class: 'rest-s' });
    const btn = h('button', { type: 'button', class: 'btn sm rest-btn', id: 'ctl-rest', 'aria-pressed': 'false',
        title: '휴식 모드 — 켜 두면 새 계좌 입금 · 확인할 후원이 올 때 화면 가장자리가 초록으로 깜빡이고 가운데 카드가 떠요(소리 없음). 이 기기에만 기억해요.' },
    h('span', { class: 'rest-ic', 'aria-hidden': 'true' }, '☕'), lbl, state);
    btn.addEventListener('click', () => setOn(!st.on, true));
    // PC · 반 화면: 조종 줄 맨 오른쪽(에디터 뒤). 폰(900 아래): 조종 줄이 꽉 차서(리액션 · 중단 · 건너뛰기 · 더보기)
    // BGM · 클립처럼 [⋯ 더보기] 판 안 한 줄로 옮긴다 — 켜 두면 [더보기] 단추에 ☕ 표시(.rest-on)
    const cb = document.querySelector('#hdr .cb');
    const moreBtn = cb ? cb.querySelector('.cb-more') : null;
    const sheetRow = h('div', { class: 'cbs-row cbs-rest' }, h('small', { class: 'cbs-cap' }, '휴식 모드 — 자리를 비울 때 켜 두면 새 입금 · 확인할 후원을 화면 깜빡임으로 알려요(소리 없음)'));
    const panel = document.querySelector('#ctl-more .cbs-panel');
    if (panel) panel.insertBefore(sheetRow, panel.querySelector('.cbs-foot'));
    const mq = window.matchMedia ? window.matchMedia('(max-width: 899px)') : { matches: false };
    function place() {
        if (mq.matches && panel) { if (btn.parentNode !== sheetRow) sheetRow.append(btn); }
        else if (cb && btn.parentNode !== cb) cb.insertBefore(btn, moreBtn);
    }
    place();
    if (mq.addEventListener) mq.addEventListener('change', place);

    // ── 가장자리 · 카드 ──
    const edge = h('div', { class: 'rest-edge', 'aria-hidden': 'true', hidden: true });
    const cHead = h('div', { class: 'rest-head' });
    const cTitle = h('div', { class: 'rest-title' });
    const cSub = h('div', { class: 'rest-sub' });
    const cList = h('ul', { class: 'rest-list' });
    const okBtn = h('button', { type: 'button', class: 'btn rest-ok', id: 'rest-ok' }, '확인');
    okBtn.addEventListener('click', () => clear());
    const card = h('div', { class: 'rest-card', id: 'rest-card', role: 'alertdialog', 'aria-modal': 'false', 'aria-labelledby': 'rest-card-t', hidden: true },
        cHead, cTitle, cSub, cList, h('div', { class: 'rest-foot' }, h('small', { class: 'rest-note' }, '☕ 휴식 모드 알림 — [확인] 을 누를 때까지 깜빡여요'), okBtn));
    cTitle.id = 'rest-card-t';
    document.body.append(edge, card);
    document.addEventListener('keydown', e => { if (e.key === 'Escape' && !card.hidden) clear(); });

    // 다른 탭에서 켜고 끄면 따라간다(같은 기기)
    window.addEventListener('storage', e => { if (e.key === REST_KEY) setOn(readRest(store()), false); });

    // ── 새 계좌 입금 — bankext.js 가 읽을 때마다(로그인한 화면에서만 읽는다) ──
    onExt(d => {
        if (!d) return;
        const r = bankTrack(st.bank, d);
        st.bank = r.st;
        if (r.add && r.line && st.on && st.authed) ping(r.line, r.add);
    });

    function setOn(on, byHand) {
        st.on = !!on;
        if (byHand) {
            const saved = writeRest(store(), st.on);
            if (ctx && ctx.toast) ctx.toast(st.on ? '☕ 휴식 모드 켬 — 새 계좌 입금 · 확인할 후원이 오면 화면이 초록으로 깜빡여요(소리 없음)'
                + (saved ? '' : ' · 이 창에서만(기억 못 함)') : '휴식 모드 끔 — 지금처럼 위 띠로만 알려요', 'ok', 3500);
        }
        if (!st.on) clear();
        paintBtn();
    }

    function paintBtn() {
        btn.setAttribute('aria-pressed', st.on ? 'true' : 'false');
        btn.classList.toggle('on', st.on);
        if (moreBtn) moreBtn.classList.toggle('rest-on', st.on);
        state.textContent = st.on ? ' 켬' : '';
    }

    function ping(line, add) {
        if (!st.alert.lines.length && !/^🔔 /.test(document.title)) st.base = document.title;
        st.alert = pushAlert(st.alert, line, add);
        paint();
    }

    function clear() {
        st.alert = emptyAlert();
        paint();
    }

    function paint() {
        const any = st.alert.lines.length > 0 && st.on && st.authed;
        edge.hidden = !any;
        card.hidden = !any;
        document.body.classList.toggle('rest-alert', any);
        if (any) {
            const v = cardView(st.alert);
            cHead.textContent = v.head;
            cTitle.textContent = v.title;
            cSub.textContent = v.sub;
            cList.replaceChildren(...v.rest.map(t => h('li', null, t)), ...(v.left ? [h('li', { class: 'rest-left' }, '외 ' + v.left + '건')] : []));
            cList.hidden = !v.rest.length && !v.left;
            if (!st.timer) {
                st.timer = setInterval(() => { st.phase = !st.phase; document.title = titleText(st.alert, st.base, st.phase); }, BLINK_MS);
                st.phase = true;
                document.title = titleText(st.alert, st.base, true);
            } else if (st.phase) document.title = titleText(st.alert, st.base, true);
        } else {
            if (st.timer) { clearInterval(st.timer); st.timer = 0; }
            if (document.title !== st.base && /^🔔 /.test(document.title)) document.title = st.base;
            st.phase = false;
        }
    }

    paintBtn();

    return {
        render(slices, view) {
            const authed = (view === 'setup' || view === 'live') && !!(ctx.lm && ctx.lm.authed);
            if (authed !== st.authed) { st.authed = authed; paint(); }
            if (!authed) return;
            // 새 '🙋 확인할 후원(보류)' — 방송 중 대기함에만 생긴다. 처음 본 것(페이지를 열 때 있던 것)은 알리지 않는다
            if (view !== 'live') return;
            const ap = (slices && slices.autopilot) || {};
            const r = holdTrack(st.hold, heldCards(slices), !ap.mode || ap.mode === 'off');   // 자동 진행 끔 → 본 것 그대로
            st.hold = r.seen;
            if (st.on) for (const it of r.fresh) ping(holdLine(it), 1);
        },
    };
}
