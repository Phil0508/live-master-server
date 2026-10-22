/* ☕ 휴식 모드 — 조종 줄(위에서 둘째 줄) [☕ 휴식] 단추로 켜고 끈다.
   ⭐ 10-22 대표님 "휴식모드: 투네는 자동, 계좌입금되면 지금처럼 초록색" — 휴식 = 서버 자동 진행 '켬'(autopilot.mode 'on').
     켜면 확실한 투네 후원은 서버가 바로 점수를 넣고(autopilot.py), 이 화면은 아래처럼 사람을 부른다. 끄면 📚 학습('shadow').
     모든 기기가 같은 값을 본다(예전엔 기기마다 localStorage 였다). 켤 때만 화면 안 상자로 묻는다(panels/auto/rest.js — 학습·휴식 탭과 같은 길).
     방송이 끝나면 서버가 저절로 학습으로 돌린다.
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
import { bankTrack, holdTrack, holdLine, pushAlert, emptyAlert, titleText, cardView } from './restcore.js';
import { setRest } from './panels/auto/rest.js';

const BLINK_MS = 1000;      // 탭 제목 번갈아

export function mountRest(ctx) {
    const st = {
        on: false,           // 서버 autopilot.mode === 'on' 을 render 가 따라간다
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
        title: '휴식 모드 — 확실한 투네 후원은 기계가 바로 점수를 넣고, 애매한 후원 · 계좌 입금이 오면 화면 가장자리가 초록으로 깜빡이며 가운데 카드가 떠요(소리 없음). 방송이 끝나면 저절로 꺼져요.' },
    h('span', { class: 'rest-ic', 'aria-hidden': 'true' }, '☕'), lbl, state);
    let busy = false;
    btn.addEventListener('click', async () => {
        if (busy) return;
        busy = true;
        btn.disabled = true;
        try { await setRest(ctx, !st.on); } finally { busy = false; btn.disabled = false; }
    });
    // PC · 반 화면: 조종 줄 맨 오른쪽(에디터 뒤). 폰(900 아래): 조종 줄이 꽉 차서(리액션 · 중단 · 건너뛰기 · 더보기)
    // BGM · 클립처럼 [⋯ 더보기] 판 안 한 줄로 옮긴다 — 켜 두면 [더보기] 단추에 ☕ 표시(.rest-on)
    const cb = document.querySelector('#hdr .cb');
    const moreBtn = cb ? cb.querySelector('.cb-more') : null;
    const sheetRow = h('div', { class: 'cbs-row cbs-rest' }, h('small', { class: 'cbs-cap' }, '휴식 모드 — 자리를 비울 때: 확실한 투네 후원은 기계가 넣고, 애매한 것 · 계좌 입금은 화면 깜빡임으로 알려요(소리 없음)'));
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

    // ── 새 계좌 입금 — bankext.js 가 읽을 때마다(로그인한 화면에서만 읽는다) ──
    onExt(d => {
        if (!d) return;
        const r = bankTrack(st.bank, d);
        st.bank = r.st;
        if (r.add && r.line && st.on && st.authed) ping(r.line, r.add);
    });

    function setOn(on) {
        if (!!on === st.on) return;
        st.on = !!on;
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
            const ap = (slices && slices.autopilot) || {};
            setOn(ap.mode === 'on');                          // 서버 값을 따라간다(다른 기기에서 켜고 꺼도)
            const authed = (view === 'setup' || view === 'live') && !!(ctx.lm && ctx.lm.authed);
            if (authed !== st.authed) { st.authed = authed; paint(); }
            if (!authed) return;
            // 새 '🙋 확인할 후원(보류)' — 방송 중 대기함에만 생긴다. 처음 본 것(페이지를 열 때 있던 것)은 알리지 않는다
            if (view !== 'live') return;
            const r = holdTrack(st.hold, heldCards(slices), ap.mode !== 'on');   // 휴식이 아니면(보류 띠 없음) 본 것 그대로
            st.hold = r.seen;
            if (st.on) for (const it of r.fresh) ping(holdLine(it), 1);
        },
    };
}
