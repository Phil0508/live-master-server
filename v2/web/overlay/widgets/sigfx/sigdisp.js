/* 🖼️ 출연진 전광판 — 시그니처 그림만 크게(옛 /signature-display · signature_display.html 을 그대로 옮겼다).
   주소: /overlay/?only=sig            어두운 바탕(출연자들이 보는 모니터)
         /overlay/?only=sig&transparent=1   바탕 투명(OBS 소스로 쓸 때)

   - 대기줄 맨 앞(queue.items[0])이 '지금 나가는 시그니처' 다. 맨 앞이 바뀔 때만 새로 띄우고, 비면 바로 내린다.
     내리는 것은 자기 시계가 없다 = 방송판이 내리는 그 순간 같이 내려가 정확히 맞는다(옛 handleData 미러 그대로).
   - 📺 띄우는 때(10-17): 방송판이 **실제로 틀기 시작한** 뒤(서버 queue.items[0].started — 방송판이 reaction.started 로 알린다).
     옛 것은 맨 앞이 되자마자 그려서 방송판(후원 카드 2초 뒤 시작)보다 2~3초 먼저 떴고, 멈춤 · play_after 를 무시해
     슬롯 · 주사위 결과가 미리 보였다. 신호가 없으면(옛 방송판 · 방송판이 꺼짐) 멈춤이 아니고 play_after(서버 시계)가 지난 뒤
     STARTED_GRACE_MS(15초)를 더 기다려 띄운다(규칙은 ../../turns.js sigDispShow).
   - 소리 없음 · '다 틀었다'(reaction.done) 안 보냄 · 줄어들지 않음(가운데 크게 그대로) · 금액 등급 연출 없음.
   - 글: '후원자 · 금액' + 메시지(없으면 시그니처 제목). 사진이 없거나 못 받으면 사진 칸을 숨긴다
     (옛 것은 /money.png 로 대신했다 — v2 는 그 그림을 내주지 않는다).
   - 화면은 방송판처럼 1080×1920 으로 줄이지 않는다(groups/sigfx.js VIEWS.sig.native) — 옛 것처럼 창 크기 그대로, 카드 폭 600. */
import { formatNum } from '../../util.js';
import { sigMsgFor } from '../../donate_kit.js';   // 💬 묶음이면 이번 차례 메시지(방송판과 같은 규칙)
import { sigDue, sigDispShow } from '../../turns.js';

export function mount(root, lm, opts) {
    root.innerHTML = '<div class="sigdisp-card">'
        + '<img class="sigdisp-img" alt="시그니처 사진">'
        + '<div class="sigdisp-donator"></div>'
        + '<div class="sigdisp-msg"></div>'
        + '</div>';
    const card = root.firstElementChild;
    const img = root.querySelector('.sigdisp-img');
    const donatorEl = root.querySelector('.sigdisp-donator');
    const msgEl = root.querySelector('.sigdisp-msg');
    let curId = null, curMsg = null, clearTimer = null;
    let dueKey = null, dueSince = 0, waitTimer = null;   // 신호 없이 '시작 가능' 을 처음 본 서버 시각(맨 앞마다)
    const now = () => { try { const v = Number(lm.serverNow && lm.serverNow()); if (isFinite(v) && v > 0) return v; } catch (e) {} return Date.now(); };

    function hide() {
        card.classList.remove('show');
        clearTimeout(clearTimer);
        clearTimer = setTimeout(() => { img.removeAttribute('src'); }, 600);
    }

    function show(d) {
        clearTimeout(clearTimer); clearTimer = null;
        const amt = Number(d.amount) || 0;
        donatorEl.textContent = (d.donator || d.nickname || '익명') + (amt ? ' · ' + formatNum(amt) + '원' : '');
        const msg = String(sigMsgFor(d) || d.title || '');
        const ok = !!(msg && msg !== '수동 후원 송출');
        msgEl.textContent = ok ? msg : (d.title || '');
        msgEl.style.display = (ok || d.title) ? 'block' : 'none';
        img.onerror = () => { img.onerror = null; img.style.display = 'none'; };
        if (d.image_url) { img.style.display = 'block'; img.src = d.image_url; }
        else { img.removeAttribute('src'); img.style.display = 'none'; }
        card.classList.add('show');
    }

    function render() {
        clearTimeout(waitTimer); waitTimer = null;
        const q = lm.get('queue') || {};
        const head = ((q && q.items) || [])[0] || null;
        if (!head) {
            dueKey = null; dueSince = 0;
            if (curId !== null) { curId = null; hide(); }
            return;
        }
        // 같은 시그니처 · 같은 메시지면 다시 그리지 않는다(깜빡임 방지). [N번 다 틀기]면 차례마다 그 차례 메시지로(10-17)
        const key = head.id + '|' + (Number(head.replay) || 0);
        const msg = sigMsgFor(head);
        if (curId !== key) {
            // 📺 아직 방송판이 안 틀었다 — 앞의 것은 내리고(이미 끝났다) 기다린다
            const t = now();
            if (dueKey !== key) { dueKey = key; dueSince = 0; }
            if (!dueSince && sigDue(head, q, t, false)) dueSince = t;
            if (!sigDispShow(head, q, t, dueSince)) {
                if (curId !== null) { curId = null; hide(); }
                // 시각이 지나야 풀리는 것(play_after · 신호 기다림 한도)은 스스로 다시 본다 — 쪽지가 안 와도
                const pa = Number(head.play_after) || 0;
                waitTimer = setTimeout(render, Math.max(250, Math.min(1000, pa > t ? pa - t + 50 : 1000)));
                return;
            }
            curId = key; curMsg = msg;
            show(head);
        } else if (curMsg !== msg) {
            curMsg = msg;
            msgEl.textContent = msg || head.title || '';
            msgEl.style.display = (msg || head.title) ? 'block' : 'none';
        }
    }
    lm.on('queue', render);
}
