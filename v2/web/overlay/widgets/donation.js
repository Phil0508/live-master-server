/* 🎁 후원 카드(화면 한가운데) — popup 조각의 donation.
   - 새 후원(id 가 바뀜)이 오면 카드를 띄운다: 이름 · '님이 후원하셨습니다!' · 금액(원은 작게) · 메시지.
   - 여러 건이 몰려도 하나도 안 빠지게 줄을 세워 하나씩(옛 것은 새 카드가 앞 카드를 덮어 앞의 것이 사라졌다).
   - 붙은 직후 통째로 받은 후원은 30초 안의 것만(다시 붙을 때 지난 후원이 또 뜨지 않게). 방송 중일 때만.
   - 어디로 갈지(util.classifyDonation): 소액 · 화면에만 → 맨 위 띠(small-don 위젯) / 시그니처가 걸린 후원 → 시그니처가
     틀기 직전에 이 카드를 부탁한다(옛 playReaction 이 카드를 먼저 띄우던 것) / 나머지 → 여기서 바로.
   - 시간: 카드 2초(옛 toonPopupTimer 2000ms) → 0.4초 동안 사라짐 → 다음 카드.
   - 👑 특별 후원자(tallies.vip — 이번 방송 후원 순위 1~10위, 서버가 매긴다)면 카드를 등급 색으로 입힌다(옛 showToonPopup 의 VIP 부분 그대로):
     1위 훈장(메달이 카드 밖으로) · 2~3위 머리띠 · 4위 이하 딱지('다이아 6위'). 등급은 카드를 **띄우는 순간** 의 tallies 로 본다 —
     후원과 순위가 같은 쪽지로 오므로 '이 후원으로 1위' 가 그 카드에 바로 보인다. 생김새는 css/basics2.css 8번.
     ⏸️ 지금은 꺼져 있다(대표님 10-13 — 서버 donors.VIP_ON, tallies.vip_on false 면 등급 옷을 안 입힌다).
   - 🏷️ 투네이션 공식 칭호 알약(이름 위 한 줄) · 이름 뒤 Lv — popup.donation 의 donor_title · donor_level(옛 44584ff, ../donate_kit.js).
   - ↻ popup.donation.encore(조종실 '다시 송출', 10-17) — 카드 위 '↻ 다시 보기' 딱지. 화면에만 한 번 더(장부 · 점수엔 안 든다).
   다른 위젯에 주는 것(stage.provide('donationCard')):
     show({name, amount, message, rq}) → 카드가 내려가는 순간 끝나는 Promise(시그니처가 그때 시작한다).
         시그니처가 부탁한 카드(rq)는 줄 맨 앞에 선다 — 시그니처가 일반 카드 뒤로 밀리지 않게(10-17)
     busy() → 카드가 **떠 있으면**(사라지는 0.4초 포함) true. 줄 선 카드는 안 센다(10-17 — 옛 것은 줄까지 세어 시그가 계속 밀렸다)
     onIdle(fn) → 줄이 다 비면 부른다
     retext(rq, message) → 시그니처 줄(rq id)로 띄운 카드 · 줄 선 카드의 메시지만 바꾼다
   🚦 시그니처와 차례(10-17, 규칙은 ../turns.js cardTurn): 시그가 가운데에 있는 동안(줄어들기 전 · 'OO업' · 전용 연출 · 경보)은
     새 카드를 안 꺼낸다(옛 것은 시그 카드 밑에 깔렸다) · 시그가 틀 차례를 기다리면 새 카드보다 먼저 넘긴다.
     시그니처 쪽은 stage.use('sigCenter') — {center(), wants(), kick(), onFree(fn)}. 시그니처 칸이 없는 화면이면 옛 것 그대로.
   🔌 다시 붙을 때(10-17): 끊긴 사이 들어온 카드를 서버 popup.recent(최근 몇 개, id 와 함께)에서 아직 안 본 것 · 30초 안의 것만
     차례로 띄운다(옛 것은 popup.donation 한 칸이라 마지막 하나만 떴다). 시그니처가 걸린 후원(sig)은 빼고.
   - 🙈 [가리기] · 금칙어(10-17 mask): 서버는 가린 글만 보낸다. 같은 후원(id)이 메시지만 바뀌어 다시 오면
     떠 있는 카드 · 줄 선 카드의 글자만 바꾼다(카드를 다시 띄우지 않는다). */
import { esc, formatNum, classifyDonation, FRESH_MS } from '../util.js';
import { donorTag, donorLv } from '../donate_kit.js';
import { cardTurn, pendingCards, cardKey } from '../turns.js';

export const HOLD_MS = 2000;     // 카드가 떠 있는 시간(옛 2초) — 바꾸려면 여기 하나만
const GAP_MS = 450;              // 사라지는 연출(0.4초) + 숨 고르기
const SEEN_MAX = 200;            // 본 후원 열쇠를 이만큼만 기억한다(서버 popup.recent 보다 넉넉히)

/* 👑 등급 찾기 — tallies.vip 의 열쇠는 서버 norm_donor 와 같은 규칙(공백 정리 · 끝 '님' 떼기)으로 다듬은 이름 */
function vipKey(x) {
    let n = String(x == null ? '' : x).trim().replace(/\s+/g, ' ');
    if (n.endsWith('님')) n = n.slice(0, -1).trim();
    return n || '익명';
}
function vipOf(name, tallies) {
    if (tallies && tallies.vip_on === false) return null;     // ⏸️ VIP 등급 꺼 둠(10-13) — 남은 값이 있어도 안 입힌다
    const lv = (tallies && tallies.vip) || {};
    const raw = String(name == null ? '' : name).trim();
    return lv[vipKey(raw)] || lv[raw] || null;
}
const VIP_VARS = ['--vip-glow-color', '--vip-glow-color-bg', '--vip-glow-color-border', '--vip-card-2', '--vip-c-lite', '--vip-c-dark', '--vip-ink'];
// 화면에 찍는 글자만 대표님이 부르시는 이름으로(서버 값 VVIP/VIP/DIAMOND/BRONZE 는 그대로). GOLD 는 7~10위의 옛 이름.
const GRADE_NAME = { DIAMOND: '다이아', BRONZE: '브론즈', GOLD: '골드' };

export function mount(root, lm, opts) {
    root.innerHTML = '<div class="donation-popup-content">'
        + '<div class="toon-vip-deco" aria-hidden="true"></div>'
        + '<div class="d-encore" aria-hidden="true">↻ 다시 보기</div>'
        + '<div class="donator-text"><span class="donator-name"></span> <span class="d-action">님이 후원하셨습니다!</span></div>'
        + '<div class="donation-amount"></div>'
        + '<div class="donation-message"></div>'
        + '</div>';
    const card = root.firstElementChild;
    const nameEl = root.querySelector('.donator-name');
    const actEl = root.querySelector('.d-action');
    const amtEl = root.querySelector('.donation-amount');
    const msgEl = root.querySelector('.donation-message');
    const decoEl = root.querySelector('.toon-vip-deco');
    const encoreEl = root.querySelector('.d-encore');
    const queue = [];
    const idleFns = [];
    let busy = false;
    const seen = new Set();      // 본 후원(id) — 같은 것이 다시 와도 한 번만(다시 붙어 받은 popup.recent 도)
    let shown = null;            // 지금 떠 있는 카드의 d

    /* 🙈 같은 후원의 메시지가 바뀌었다(가리기 · 금칙어) — 줄 선 것 · 떠 있는 것의 글자만 */
    function retext(match, message) {
        const msg = String(message || '');
        queue.forEach(q => { if (match(q.d)) q.d.message = msg; });
        if (shown && match(shown) && String(shown.message || '') !== msg) {
            shown.message = msg;
            try { fill(shown); } catch (e) { msgEl.textContent = ''; msgEl.style.display = 'none'; }
        }
    }

    /* 👑 등급 옷 — 먼저 앞 사람의 흔적을 지운다(안 지우면 다음 일반 후원에도 메달이 남는다) */
    function dressVip(name) {
        card.classList.remove('vip-premium-card', 'vip-rank-top', 'vip-rank-mid');
        VIP_VARS.forEach(v => card.style.removeProperty(v));
        decoEl.innerHTML = '';
        nameEl.className = 'donator-name';
        const v = vipOf(name, lm.get('tallies'));
        if (!v) { nameEl.textContent = name; return; }
        const color = v.color || v.custom_color || '#ffd700';
        let r = 255, g = 215, b = 0;
        const hex = String(color).replace('#', '');
        if (/^[0-9a-fA-F]{6}$/.test(hex)) {
            r = parseInt(hex.slice(0, 2), 16); g = parseInt(hex.slice(2, 4), 16); b = parseInt(hex.slice(4, 6), 16);
        }
        card.classList.add('vip-premium-card');
        card.style.setProperty('--vip-glow-color', color);
        card.style.setProperty('--vip-glow-color-bg', `rgba(${r}, ${g}, ${b}, 0.15)`);
        card.style.setProperty('--vip-glow-color-border', `rgba(${r}, ${g}, ${b}, 0.3)`);
        // 🎨 등급색을 어두운 바탕(#1c1c1e)에 22% 섞은 **불투명** 색(알파로 칠하면 밝은 화면이 비쳐 카드가 사라진다)
        const mix = (c, base) => Math.round(base * 0.78 + c * 0.22);
        card.style.setProperty('--vip-card-2', `rgb(${mix(r, 28)}, ${mix(g, 28)}, ${mix(b, 30)})`);
        // 🎖️ 메달 테두리 · 머리띠 그라데이션에 쓰는 밝은/어두운 짝 · 머리띠 위 글자색(밝은 등급색이면 검정)
        const lite = c => Math.round(c + (255 - c) * 0.45), dark = c => Math.round(c * 0.58);
        card.style.setProperty('--vip-c-lite', `rgb(${lite(r)}, ${lite(g)}, ${lite(b)})`);
        card.style.setProperty('--vip-c-dark', `rgb(${dark(r)}, ${dark(g)}, ${dark(b)})`);
        card.style.setProperty('--vip-ink', (0.299 * r + 0.587 * g + 0.114 * b) > 150 ? '#1c1206' : '#ffe9b0');

        const grade = v.grade || 'VIP';
        const badge = v.badge || '👑';
        const gradeName = GRADE_NAME[grade] || grade;
        const rank = Number(v.rank || 0);
        nameEl.className = 'donator-name vip-grade-text';
        if (rank === 1) {
            // 1위 — 훈장. 메달이 순위를 달았으니 딱지는 등급 이름만 크게
            card.classList.add('vip-rank-top');
            decoEl.innerHTML = '<div class="medal-in"><span class="medal-em">' + esc(badge) + '</span><span class="medal-rk">' + rank + '위</span></div>';
            nameEl.innerHTML = '<span class="vip-badge-tag">' + esc(gradeName) + '</span>' + esc(name);
        } else if (rank >= 2 && rank <= 3) {
            // 2~3위 — 머리띠. 등급은 왼쪽, 순위는 오른쪽
            card.classList.add('vip-rank-mid');
            decoEl.innerHTML = '<span class="hdr-g">' + esc(badge) + ' ' + esc(gradeName) + '</span><span class="hdr-r">' + rank + '위</span>';
            nameEl.textContent = name;
        } else {
            // 4위 이하 — 딱지('다이아 6위')
            nameEl.innerHTML = '<span class="vip-badge-tag">' + esc(gradeName + (rank ? ' ' + rank + '위' : '')) + '</span>'
                + esc(badge) + ' ' + esc(name);
        }
    }

    function fill(d) {
        try { dressVip(d.name || '익명'); }
        catch (e) { console.error('[후원 카드] 등급 옷 실패 — 이름만 띄운다:', e); nameEl.className = 'donator-name'; nameEl.textContent = d.name || '익명'; }
        // 🏷️ 칭호 알약(이름 위 한 줄 — css/donate.css) · Lv(이름 뒤). 등급 딱지와 같이 붙어도 된다(옛 것과 같다)
        try {
            const tg = donorTag(d.donor_title), lv = donorLv(d.donor_level);
            if (tg) nameEl.prepend(tg);
            if (lv) nameEl.appendChild(lv);
        } catch (e) { console.error('[후원 카드] 칭호 붙이기 실패:', e); }
        encoreEl.classList.toggle('on', !!d.encore);         // ↻ 조종실 '다시 송출' — 한 번 더 보여 주는 것임을 알린다(10-17)
        let msg = String(d.message || '');
        const m = msg.match(/^\[시그니처 신청:\s*(.*?)\]/);
        if (m) {
            actEl.textContent = '님이 신청하셨습니다!';
            amtEl.textContent = '"' + (m[1] || '시그니처') + '"';
            msg = msg.replace(/^\[시그니처 신청:\s*.*?\]\s*/, '');
        } else {
            actEl.textContent = '님이 후원하셨습니다!';
            const a = Number(d.amount) || 0;
            if (a === 0) amtEl.textContent = '후원';
            else amtEl.innerHTML = esc(formatNum(a)) + '<span class="won">원</span>';
        }
        msgEl.textContent = msg;
        msgEl.style.display = msg ? '' : 'none';
    }

    /* 🚦 시그니처 쪽 사정 — 칸이 없거나 넘어지면 '없음' 으로 본다(카드가 멈추지 않게) */
    function sigState() {
        const sig = opts.stage.use('sigCenter');
        if (!sig) return { sig: null, center: false, wants: false };
        let center = false, wants = false;
        try { center = !!sig.center(); } catch (e) {}
        try { wants = !!sig.wants(); } catch (e) {}
        return { sig, center, wants };
    }

    function next() {
        let s = sigState();
        let turn = cardTurn({ busy, queued: queue.length, sigCenter: s.center, sigWants: s.wants });
        if (turn === 'yield') {
            // 시그가 차례를 기다린다 — 새 카드를 꺼내기 전에 먼저 넘긴다. 시그가 카드를 부탁하면 그 카드가 맨 앞으로 와서
            // 아래 재귀 next() 가 이미 띄웠다(busy). 시그가 곧장 시작하면 가운데를 잡는다(center). 둘 다 아니면 그냥 카드를 띄운다.
            try { s.sig.kick(); } catch (e) { console.error('[후원 카드] 시그니처에 차례 넘기기 실패 — 카드를 띄운다:', e); }
            s = sigState();
            turn = cardTurn({ busy, queued: queue.length, sigCenter: s.center, sigWants: false });
        }
        if (turn === 'wait' || turn === 'center') return;         // 'center' — 시그가 비키면 onFree 가 다시 부른다
        const it = turn === 'show' ? queue.shift() : null;
        if (!it) { idleFns.slice().forEach(fn => { try { fn(); } catch (e) {} }); return; }
        busy = true;
        shown = it.d;
        try {
            fill(it.d);
            card.classList.remove('show');
            void card.offsetWidth;
            card.classList.add('show');
            // ✨ 테마를 입었을 때만 그 테마 모양 입자를 적게(기본 테마 · 테마 연출 끔이면 아무것도 안 한다 — widgets/fx/burst.js)
            try { const fx = opts.stage.use('fx'); if (fx) fx.burst(card, 'donation', it.d.amount); } catch (e) {}
        } catch (e) {
            // ⚠️ 그리기가 실패해도 아래 타이머는 반드시 건다 — 안 그러면 줄과 시그니처가 영영 멈춘다(옛 사고)
            console.error('[후원 카드] 그리기 실패 — 다음으로 넘어간다:', e);
        }
        setTimeout(() => {
            card.classList.remove('show');
            shown = null;
            if (it.done) { try { it.done(); } catch (e) {} }
            setTimeout(() => { busy = false; next(); }, GAP_MS);
        }, HOLD_MS);
    }

    function enqueue(d, done) {
        // 🚦 시그니처가 부탁한 카드(rq)는 맨 앞 — 시그가 일반 카드 뒤로 밀리지 않게(줄 선 다른 시그 카드보다는 뒤)
        if (d && d.rq) {
            let i = 0;
            while (i < queue.length && queue[i].d && queue[i].d.rq) i++;
            queue.splice(i, 0, { d, done });
        } else {
            queue.push({ d, done });
        }
        next();
    }

    opts.stage.provide('donationCard', {
        show(d) { return new Promise(resolve => enqueue(d || {}, resolve)); },
        busy() { return busy; },
        onIdle(fn) { idleFns.push(fn); },
        retext(rq, message) { if (rq) retext(d => d && d.rq === rq, message); },
    });
    // 🚦 시그니처가 가운데를 비우면 다시 본다(시그니처 칸이 나중에 붙어도 되게 한 박자 뒤에 건다)
    setTimeout(() => { const sig = opts.stage.use('sigCenter'); if (sig && sig.onFree) sig.onFree(() => next()); }, 0);

    function remember(keys) {
        keys.forEach(k => { seen.delete(k); seen.add(k); });
        while (seen.size > SEEN_MAX) seen.delete(seen.values().next().value);
    }

    lm.on('popup', (pop, slices) => {
        const d = pop && pop.donation;
        // 🔌 최근 카드 알림(서버 popup.recent — 오래된 순). 옛 서버라 없으면 donation 한 칸만
        let list = Array.isArray(pop && pop.recent) ? pop.recent.slice() : [];
        if (d && !list.some(x => x && cardKey(x) === cardKey(d))) list.push(d);
        if (!list.length) return;
        // 🙈 이미 본 후원이 다시 왔다 — 가리기 · 금칙어로 글만 바뀐 것. 떠 있는 · 줄 선 카드의 글자만
        list.forEach(x => { if (x && x.id && seen.has(cardKey(x))) retext(y => y && y.id === x.id, x.message); });
        const streaming = opts.isFresh(0);                      // 실시간 쪽지면 true, 붙은 직후 통째면 false
        const live = !!((slices.session || {}).live);
        let fresh;
        if (streaming) {
            // 실시간 — 새로 온 것만(보통 하나). 시그니처 갈래는 옛 것 그대로 대기줄로 가린다(classifyDonation)
            const keys = list.map(cardKey).filter(Boolean);
            fresh = list.filter(x => x && cardKey(x) && !seen.has(cardKey(x)));
            remember(keys);
        } else {
            // 다시 붙음 · 처음 붙음 — 아직 안 본 것 · 30초 안의 것만 차례로(../turns.js pendingCards)
            const r = pendingCards(list, seen, Date.now(), FRESH_MS);
            fresh = r.fresh;
            remember(r.keys);
        }
        if (!live) return;                                      // 방송 중이 아니면 알림 없음(옛 것과 같다)
        if (!opts.stage.alertOn('popup')) return;               // 조종실 알림 스위치 [후원 팝업]
        fresh.forEach(x => {
            if (classifyDonation(x, slices.queue) !== 'card') return;
            enqueue(x);
        });
    });
}
