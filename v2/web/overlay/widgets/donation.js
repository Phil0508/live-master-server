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
   다른 위젯에 주는 것(stage.provide('donationCard')):
     show({name, amount, message}) → 카드가 내려가는 순간 끝나는 Promise(시그니처가 그때 시작한다)
     busy() → 카드가 떠 있거나 줄이 있으면 true · onIdle(fn) → 줄이 다 비면 부른다 */
import { esc, formatNum, classifyDonation } from '../util.js';

export const HOLD_MS = 2000;     // 카드가 떠 있는 시간(옛 2초) — 바꾸려면 여기 하나만
const GAP_MS = 450;              // 사라지는 연출(0.4초) + 숨 고르기

/* 👑 등급 찾기 — tallies.vip 의 열쇠는 서버 norm_donor 와 같은 규칙(공백 정리 · 끝 '님' 떼기)으로 다듬은 이름 */
function vipKey(x) {
    let n = String(x == null ? '' : x).trim().replace(/\s+/g, ' ');
    if (n.endsWith('님')) n = n.slice(0, -1).trim();
    return n || '익명';
}
function vipOf(name, tallies) {
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
    const queue = [];
    const idleFns = [];
    let busy = false;
    let seen;                    // 마지막으로 본 후원(id) — 같은 것이 다시 와도 한 번만

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

    function next() {
        if (busy) return;
        const it = queue.shift();
        if (!it) { idleFns.slice().forEach(fn => { try { fn(); } catch (e) {} }); return; }
        busy = true;
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
            if (it.done) { try { it.done(); } catch (e) {} }
            setTimeout(() => { busy = false; next(); }, GAP_MS);
        }, HOLD_MS);
    }

    function enqueue(d, done) {
        queue.push({ d, done });
        next();
    }

    opts.stage.provide('donationCard', {
        show(d) { return new Promise(resolve => enqueue(d || {}, resolve)); },
        busy() { return busy || queue.length > 0; },
        onIdle(fn) { idleFns.push(fn); },
    });

    lm.on('popup', (pop, slices) => {
        const d = pop && pop.donation;
        if (!d) return;
        const key = d.id || String(d.at);
        if (key === seen) return;
        seen = key;
        if (!opts.isFresh(d.at)) return;                        // 다시 붙었을 때 지난 후원
        if (!((slices.session || {}).live)) return;             // 방송 중이 아니면 알림 없음(옛 것과 같다)
        if (classifyDonation(d, slices.queue) !== 'card') return;
        if (!opts.stage.alertOn('popup')) return;               // 조종실 알림 스위치 [후원 팝업]
        enqueue(d);
    });
}
