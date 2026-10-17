/* 🎵 시그니처 재생 — queue 조각 {items, paused, volume}. 맨 앞(items[0])이 지금 틀 것이다.

   흐름(옛 checkReactionQueue · playReaction · onReactionEnded 를 옮겼다)
     1) 맨 앞이 있고 · 멈춤(paused)이 아니고 · play_after 시각이 지났고 · 후원 카드가 떠 있지 않으면 시작한다.
        ⏸️ 멈춤은 '새로 시작' 만 막는다 — 이미 나가고 있는 것은 끝까지 튼다(돈 낸 후원자의 시그니처를 자르지 않는다).
     2) 시작 전에 후원 카드를 먼저 2초(stage 의 donationCard) — 단 슬롯처럼 자체 연출이 있는 것(skip_popup) ·
        대기줄이 밀린 때(2건 이상) · 10만 원 이상 · '다 틀기' 되풀이는 카드 없이 곧장(옛 것과 같다).
     3) 사진 + '후원자 · 금액' + 메시지 카드가 가운데에 뜨고 2.5초 뒤 왼쪽(180,600)으로 작게. 가운데에는 하나만(옛 갈래 순서 — sigfx/rules.titlePlan):
          🚨 25만 원 '계엄령' 시그니처 → 'OO업' 대신 붉은 경보 4초(sigfx/warn.js)
          🎆 전용 연출이 있는 시그니처(10만~300만 18가지 — 옛 17선 + 진압해) → 그 연출(sigfx/stage.js). 'OO업' 은 안 띄운다(연출마다 자기 글자가 있다).
             연출이 카드 등장을 맡는 동안은 카드 축소를 연출이 끝난 뒤로 미룬다(rules.shrinkWait — 안 그러면 카드가 '툭' 순간이동한다).
             연출을 못 띄우면(파일을 아직 못 받음 · 실패) 'OO업' 으로 간다.
          그 밖에는 10만 원 이상이면 'OO업' 배너 3.5초 · 슬롯 당첨은 시그니처 이름 · 🎲 주사위 시그는 '누구 · 시그 칸 도착'(금액 · '업' 없음).
        🎚️ 크기 · 줄어드는 시간 · 줄어든 자리 · 배너 글자 크기 · 시간 · 붙는 말은 편집기 설정(sigview 조각, 옛 reaction_* 설정)을 따른다.
           숫자는 CSS 변수(--reac-big · --reac-small · --reac-min-x · --reac-min-y · --reac-title-size)로 칸에 붙인다.
     4) 음원을 queue.volume 으로 튼다(?monitor=1 이면 소리 끔). 끝나는 때:
          음원 'ended' · 음원 오류면 시그니처 길이(duration)만큼 지난 뒤 · 음원이 없으면 duration 초 ·
          안전 타이머(길이를 알면 길이+2초, 모르면 max(30초, duration+5초))
     5) 끝나면 reaction.done {id} 를 **한 번** 보낸다(로그인 없이 되는 명령). 서버가 맨 앞에서 빼 줄 때까지 같은 것을 다시 틀지 않는다.
        실패하면(연결 끊김) 그것이 여전히 맨 앞인 동안 0.5 · 1 · 1.5 … 5초 간격으로 다시 보낸다.
        ?monitor=1(미리보기)은 보내지 않는다 — 진짜 방송판이 보낸다(옛 IS_MONITOR 와 같다. 두 번 빠지는 사고 방지).
     6) 틀고 있는데 맨 앞이 바뀌면(조종실 건너뛰기 · 지우기 · 전체 멈춤) 그 자리에서 끊는다(done 은 안 보낸다).
     7) '다 틀기'(play_all) ×N — 서버가 같은 id 에 replay 번호를 올려 준다 → 같은 시그니처를 카드 없이 다시 튼다.
     8) 방송판이 여러 개면 소리 · done 은 담당 창 하나만(audio_lead.js) — 담당이 아니면 소리 없이 그리고, done 은 10초 기다려 본다.
     9) 🎁 후원 받기 갈래(10-17 이사 — 도구는 ../donate_kit.js):
        🏷️ 이름 앞 투네이션 칭호 알약 · 뒤 Lv(it.donor_title · donor_level, 옛 44584ff) · 💙 사진 왼쪽 위 '투네' 딱지(it.via 'toon', 옛 97cbc4c)
        💬 묶음(×N) 메시지 — [N번 다 틀기]면 이번 차례 메시지, 한 번이면 다 같이(it.msgs, 옛 5d179b0). 트는 사이 더 오면 바로 고친다
        🔁 이어 틀기 줄(seq_base) — '2 / 3' 부터 센다(옛 rxComboSync)

     9) 🔊 자동재생이 막히면(브라우저 정책) 소리 없이라도 끝까지 튼다(사진 · 길이 · 차례 그대로). 방송판을 **한 번 누르면**(클릭 · 키 · 터치)
        음소거를 풀어 그 자리부터 소리를 살린다 — 음소거 재생마저 막혀 멈춰 있었으면 지금 시그니처 소리를 처음부터 다시 튼다(옛 recoverFromAutoplayBlock).
        빨간 경고 띠는 알림창 화면(?only=alert)에만 뜬다(sigfx/unlock.js) — 방송판에는 옛 것처럼 안 띄운다(대표님 08-13 요청).
        재생이 새 요청 · 정지로 끊긴 것(AbortError)이면 같은 시그니처를 한 번만 다시 튼다(옛 tryPlay(true)).

   금액 등급 기본 연출(플래시 · 흔들림 · 테두리 빛 · 가장자리 어둡게)은 여기서, 전용 연출 · 경보는 widgets/sigfx/(stage.provide 'sigfx' · 'sigWarn').
   💡 비트 점멸 · 사진 대표색(화면 네온 + 이 카드 테두리)은 widgets/fx/neon.js — 시작 · 끝에 stage 'neon' 을 부른다. */
import { esc, formatNum, restartClass, BIG_DONATION_MIN } from '../util.js';
import { paintDonorName, sigMsgFor, comboOf } from '../donate_kit.js';
import { titlePlan, bannerText, bannerAmount, shrinkWait, MARTIAL_LAW_MESSAGE } from './sigfx/rules.js';
// 🔊 방송판을 여러 곳에 띄워도 소리 · '다 틀었다'(done)는 담당 창 하나만 — 옛 isAudioLeader(audio_lead.js 머리말)
import { isLeader, setPlaying, livePlayingLeader, onLeaderChange, NON_LEADER_GRACE_MS } from '../audio_lead.js';

const SHRINK_MS = 2500;      // 가운데 → 왼쪽으로 작게(옛 reaction_shrink_delay 기본) — sigview.shrink_delay 가 없을 때
const TITLE_MS = 3500;       // 'OO업' 배너(옛 reaction_title_duration 기본) — sigview.title_duration 이 없을 때
const HIDE_DELAY_MS = 350;   // 끝난 뒤 카드를 내리기까지 — 바로 다음 것(되풀이 · 다음 시그)이면 깜빡이지 않게

function tier(amount) {
    const a = parseInt(amount, 10) || 0;
    if (a >= 200000) return { level: 4, flash: 1.00, shake: 'shake-strong', vignette: 0.62, glow: '#ffe08c', gold: true };
    if (a >= 100000) return { level: 3, flash: 0.85, shake: 'shake',        vignette: 0.55, glow: '#ffd76b', gold: true };
    if (a >= 50000)  return { level: 2, flash: 0.60, shake: '',             vignette: 0.40, glow: '#ffb347', gold: true };
    if (a >= 30000)  return { level: 1, flash: 0.35, shake: '',             vignette: 0.22, glow: '#ff2d78', gold: false };
    return             { level: 0, flash: 0,    shake: '',             vignette: 0,    glow: '#ff2d78', gold: false };
}

export function mount(root, lm, opts) {
    root.innerHTML = '<div class="sig-root">'
        + '<div class="sig-vignette"></div><div class="sig-flash"></div>'
        + '<div class="reaction-screen-overlay">'
        +   '<div class="reaction-img-box"><div class="reaction-combo"></div><div class="reaction-via" aria-hidden="true">투네</div>'
        +     '<img class="reaction-img" alt=""><div class="reaction-shine"></div></div>'
        +   '<div class="reaction-title-plate"></div>'
        +   '<div class="reaction-text-donator"></div>'
        +   '<div class="reaction-text-message"></div>'
        + '</div>'
        + '<div class="reaction-title-banner"></div>'
        + '</div>';
    const $ = s => root.querySelector(s);
    const overlay = $('.reaction-screen-overlay'), box = $('.reaction-img-box'), img = $('.reaction-img');
    const combo = $('.reaction-combo'), plate = $('.reaction-title-plate'), viaEl = $('.reaction-via');
    const donatorEl = $('.reaction-text-donator'), msgEl = $('.reaction-text-message');
    const banner = $('.reaction-title-banner'), vig = $('.sig-vignette'), flash = $('.sig-flash');
    const audio = new Audio();
    audio.preload = 'auto';

    let cur = null;               // 지금 맡은 것 {key, id, replay, item, token, phase:'card'|'play', timers[], startedAt}
    const doneKeys = new Map();   // 다 틀고 done 을 보낸 것(key → id) — 서버가 뺄 때까지 다시 안 튼다
    let tickTimer = null, hideTimer = null, bannerTimer = null, comboTimer = null;
    let comboShown = { key: null, count: 0, all: false };
    let blocked = false;          // 🔊 브라우저가 소리 있는 재생을 막았다(누르면 살린다 — recover)

    const Q = () => lm.get('queue') || { items: [], paused: false, volume: 0.5 };
    // 🎚️ 편집기 설정(sigview) — 값이 없거나 이상하면 옛 기본값
    const SV = () => lm.get('sigview') || {};
    const svNum = (k, d) => { const v = Number(SV()[k]); return isFinite(v) && v > 0 ? v : d; };
    const svPos = (k, d) => { const v = SV()[k]; return typeof v === 'number' && isFinite(v) ? v : d; };    // 자리는 0 도 된다
    function applyView() {
        const st = root.style;
        st.setProperty('--reac-big', String(svNum('big_scale', 1)));
        st.setProperty('--reac-small', String(svNum('small_scale', 0.6)));
        st.setProperty('--reac-min-x', svPos('min_x', 180) + 'px');
        st.setProperty('--reac-min-y', svPos('min_y', 600) + 'px');
        st.setProperty('--reac-title-size', svNum('title_size', 150) + 'px');
    }
    lm.on('sigview', applyView);
    applyView();
    const keyOf = it => it.id + '#' + (Number(it.replay) || 0);
    const vol = () => { const v = Number(Q().volume); return isFinite(v) ? Math.max(0, Math.min(1, v)) : 0.5; };
    const log = (...a) => console.log('[시그니처]', ...a);

    function schedule(ms) {
        clearTimeout(tickTimer);
        tickTimer = setTimeout(tick, ms || 0);
    }

    // ── 화면 ──
    function cancelHide() { if (hideTimer) { clearTimeout(hideTimer); hideTimer = null; } }
    function hideVisuals() {
        cancelHide();
        overlay.classList.remove('show', 'minimize');
        vig.classList.remove('show');
        box.classList.remove('glow', 'shine', 'shake', 'shake-strong');
        hideBanner();
        clearInterval(comboTimer);
        combo.className = 'reaction-combo'; combo.textContent = '';
        comboShown = { key: null, count: 0, all: false };
        // 🎆 전용 연출 · 🚨 경보도 같이 걷는다 — 재생을 끊었는데 연출 · 붉은 화면만 남아 돌면 어수선하다(옛 stopReactionVisuals).
        //    ⚠️ 경보는 이 한 겹만 — 조종실에서 따로 쏜 연출은 건드리지 않는다.
        try { const fx = opts.stage.use('sigfx'); if (fx) fx.stop(); } catch (e) {}
        try { const w = opts.stage.use('sigWarn'); if (w) w.clear(); } catch (e) {}
    }
    function hideSoon() { cancelHide(); hideTimer = setTimeout(hideVisuals, HIDE_DELAY_MS); }
    function hideBanner() { clearTimeout(bannerTimer); bannerTimer = null; banner.classList.remove('show'); }

    function showBanner(it) {
        hideBanner();
        if (!opts.stage.alertOn('reaction_title')) return;
        // 슬롯 당첨 — 시그니처 이름만 · 🎲 주사위 — '누구 · 시그 칸 도착' · 그 밖에는 10만 원 이상만 '이름 + 업'(옛 reaction_title_suffix, 비우면 이름만)
        const text = bannerText(it, SV().title_suffix, BIG_DONATION_MIN);
        if (!text) return;
        const t = tier(bannerAmount(it));
        banner.classList.remove('tier-2', 'tier-3', 'tier-4');
        if (t.level >= 4) banner.classList.add('tier-4');
        else if (t.level >= 3) banner.classList.add('tier-3');
        else if (t.level >= 2) banner.classList.add('tier-2');
        banner.textContent = text;
        banner.style.fontSize = '';
        try {   // 긴 글은 화면 폭(980)에 맞춰 줄인다 — offsetWidth 는 scale 을 안 탄다
            const w = banner.offsetWidth;
            if (w > 980) banner.style.fontSize = Math.floor(parseFloat(getComputedStyle(banner).fontSize) * 980 / w) + 'px';
        } catch (e) {}
        restartClass(banner, 'show');
        bannerTimer = setTimeout(() => banner.classList.remove('show'), svNum('title_duration', TITLE_MS));
    }

    /* 가운데 한 가지 — 🚨 계엄령 경보 · 🎆 전용 연출 · 'OO업' 배너(옛 startPlayback 의 갈래). 연출이 돌면 그 길이(ms), 아니면 0 */
    function headline(it) {
        const plan = titlePlan(it);
        if (plan === 'warn') {
            hideBanner();                                          // 계엄령: 이름을 부르지 않는다. 사이렌이 먼저다
            const w = opts.stage.use('sigWarn');
            if (w) w.fire({ message: MARTIAL_LAW_MESSAGE });
            return 0;
        }
        if (plan === 'fx') {
            const fx = opts.stage.use('sigfx');
            const ms = fx ? fx.play(it, { card: overlay }) : 0;
            if (ms > 0) { hideBanner(); return ms; }               // 연출마다 자기 글자가 있어 'OO업' 과 겹친다
        }
        showBanner(it);
        return 0;
    }

    function effects(it) {
        const t = tier(it.amount);
        box.style.setProperty('--reac-glow', t.glow);
        box.classList.toggle('glow', t.level >= 1);
        box.classList.remove('shine', 'shake', 'shake-strong');
        void box.offsetWidth;
        box.classList.add('shine');
        if (t.shake) box.classList.add(t.shake);
        if (t.flash > 0) {
            flash.classList.toggle('gold', !!t.gold);
            flash.style.setProperty('--flash-peak', t.flash);
            restartClass(flash, 'flash-go');
        }
        if (t.vignette > 0) { vig.style.setProperty('--vig-peak', t.vignette); vig.classList.add('show'); }
        else vig.classList.remove('show');
    }

    /* 🔁 ×N — 같은 사람 · 같은 시그니처가 묶였다. '다 틀기'면 '몇 번째 / 모두' */
    function syncCombo(it) {
        const cb = comboOf(it);             // 이어 틀기 줄은 앞에서 튼 만큼(seq_base)을 더해 센다
        const cnt = cb.count;
        const all = cb.all;
        const total = cb.total;
        if (total <= 1 || !all) {                // 🙈 [N번 다 틀기] 전에는 ×N 을 안 띄운다(대표님 10-17)
            if (comboShown.key !== null) { clearInterval(comboTimer); combo.className = 'reaction-combo'; combo.textContent = ''; }
            comboShown = { key: null, count: 0, all: false };
            return;
        }
        const key = keyOf(it);
        const was = comboShown;
        if (was.key === key && was.count === cnt && was.all === all) return;
        comboShown = { key, count: cnt, all };
        clearInterval(comboTimer);
        if (all) {
            combo.className = 'reaction-combo count';
            combo.innerHTML = '<b>' + cb.nth + '</b> / ' + total;
            return;
        }
        const bump = k => { combo.textContent = '×' + k; restartClass(combo, 'pop'); };
        combo.className = 'reaction-combo burst';
        if (was.key !== key || was.all) {
            let k = 1; bump(1);                                       // ×1 → ×N 으로 톡톡
            comboTimer = setInterval(() => { k++; bump(k); if (k >= cnt) clearInterval(comboTimer); }, 260);
        } else {
            bump(cnt);                                                // 트는 사이 같은 후원이 더 왔다
        }
    }

    function fill(it) {
        const amt = Number(it.amount) || 0;
        // 🏷️ 이름 앞 칭호 알약 · 뒤 Lv(없으면 이름만)
        paintDonorName(donatorEl, (it.donator || '익명') + (amt ? ' · ' + formatNum(amt) + '원' : ''), it.donor_title, it.donor_level);
        msgEl.textContent = sigMsgFor(it);                         // 💬 묶음이면 이번 차례 메시지(또는 전부)
        viaEl.classList.toggle('on', it.via === 'toon');           // 💙 투네이션에서 온 후원
        if (it.image_url) {
            img.src = it.image_url;
            img.alt = it.title || '';
            box.classList.remove('no-img');
            plate.classList.remove('on');
        } else {
            img.removeAttribute('src');
            box.classList.add('no-img');
            plate.textContent = it.title || '시그니처';               // 사진이 없으면 제목 판
            plate.classList.add('on');
        }
    }

    // ── 소리 ──
    function silence() {
        audio.onended = audio.onerror = audio.onloadedmetadata = null;
        try { audio.pause(); } catch (e) {}
        if (audio.getAttribute('src')) { audio.removeAttribute('src'); try { audio.load(); } catch (e) {} }
    }
    function clearCur() {
        if (!cur) return;
        cur.timers.forEach(clearTimeout);
        cur.timers = [];
        silence();
        setPlaying(null);
        try { const neon = opts.stage.use('neon'); if (neon) neon.sigEnd(); } catch (e) {}   // 💡 사진 색 · 비트 정리(옛 stopReaction)
    }
    // 담당이 바뀌면(다른 창이 닫히거나 숨거나 새로 뜸) 지금 틀던 소리의 음소거만 다시 맞춘다
    onLeaderChange(lead => { if (cur && !cur.forcedMute) audio.muted = !!opts.monitor || !lead; });

    // ── 차례 ──
    // 🙈 수동 리액션 모드(lights.manual — 조종 줄 스위치)가 켜져 있으면 시그니처가 없어도 리액션 모드(위젯 숨김 · 조명).
    //    시그니처 쪽 판단(sigOn)은 따로 기억해 두고 둘 중 하나라도 켜져 있으면 켠다 — 시그가 끝나도 손으로 켠 것은 남는다.
    let sigOn = false;
    const manualOn = () => !!((lm.get('lights') || {}).manual);
    function setReaction(on) { sigOn = !!on; opts.stage.setMode('reaction', sigOn || manualOn()); }
    lm.on('lights', () => setReaction(sigOn));

    function tick() {
        tickTimer = null;
        const q = Q();
        const items = q.items || [];
        const head = items[0];
        const ids = new Set(items.map(it => it.id));
        doneKeys.forEach((id, k) => { if (!ids.has(id)) doneKeys.delete(k); });

        if (cur) {
            if (head && keyOf(head) === cur.key) {
                if (cur.phase === 'play') {
                    audio.volume = vol(); syncCombo(head);
                    const m = sigMsgFor(head);                       // 💬 트는 사이 같은 시그가 더 오면 메시지도 바로 덧붙인다(옛 rxMsgRefresh)
                    if (msgEl.textContent !== m) msgEl.textContent = m;
                }
                setReaction(true);
                return;
            }
            stop(head ? '맨 앞이 바뀜(건너뛰기 · 지우기)' : '대기줄이 비었다');
        }
        if (!head) { setReaction(false); return; }
        const key = keyOf(head);
        if (doneKeys.has(key)) { setReaction(true); return; }          // 서버가 뺄 때까지 기다린다
        if (q.paused) { setReaction(false); return; }                   // 새로 시작하지 않는다
        const wait = (Number(head.play_after) || 0) - Date.now();
        if (wait > 0) { setReaction(false); schedule(Math.min(wait + 50, 60000)); return; }
        setReaction(true);
        const card = opts.stage.use('donationCard');
        if (card && card.busy()) return;                                 // 카드가 내려가면 onIdle 이 다시 부른다
        start(head, items.length);
    }

    function start(it, qlen) {
        const token = {};
        cur = { key: keyOf(it), id: it.id, replay: Number(it.replay) || 0, item: it, token, phase: 'card', timers: [], startedAt: 0 };
        setPlaying(it.id);
        const repeat = cur.replay > 0;
        const big = (Number(it.amount) || 0) >= BIG_DONATION_MIN;
        const backlog = qlen > 1;
        const card = opts.stage.use('donationCard');
        if (card && !it.skip_popup && !backlog && !big && !repeat) {
            card.show({ name: it.donator || '익명', amount: it.amount || 0, message: it.message || '' })
                .then(() => { if (cur && cur.token === token) begin(); });
        } else {
            begin();
        }
    }

    function begin() {
        const it = cur.item, token = cur.token;
        cur.phase = 'play';
        cur.startedAt = Date.now();
        log('시작', it.title, it.donator, it.amount, '#' + cur.replay);
        // ✂️ 기준 금액 이상 시그가 실제로 재생된다 — 쇼츠 클립 예약(조건 · 시각은 widgets/more/clip.js)
        try { const clip = opts.stage.use('clip'); if (clip) clip.bigSig(it); } catch (e) { /* 클립이 넘어져도 재생은 그대로 */ }
        cancelHide();
        blocked = false;                  // 새 재생마다 '소리 있는 재생' 을 다시 해 본다(옛 startPlayback — 한 번 막혔다고 방송 내내 무음이 되지 않게)
        try {
            fill(it);
            overlay.classList.remove('minimize');
            overlay.classList.add('show');
            syncCombo(it);
            effects(it);
        } catch (e) { console.error('[시그니처] 그리기 실패 — 소리 · 차례는 계속:', e); }
        // 💡 조명(widgets/fx/neon.js) — 사진 대표색(화면 네온 · 이 카드 테두리) · 30만 등급 비트 맞추기(옛 applySignatureThemeColor · beginBeatSync)
        try {
            const neon = opts.stage.use('neon');
            if (neon) neon.sigPlay(it, audio).then(rgb => { if (rgb && cur && cur.token === token) box.style.setProperty('--reac-glow', rgb); });
        } catch (e) { /* 조명이 넘어져도 재생은 그대로 */ }
        // 🚨 계엄령 · 🎆 전용 연출 · 'OO업' — 연출이 카드를 붙잡고 있는 동안은 축소를 미룬다
        let fxMs = 0;
        try { fxMs = headline(it); } catch (e) { console.error('[시그니처] 가운데 연출 실패 — 소리 · 차례는 계속:', e); }
        const busyUntil = fxMs > 0 ? Date.now() + fxMs : 0;
        cur.timers.push(setTimeout(() => overlay.classList.add('minimize'), shrinkWait(svNum('shrink_delay', SHRINK_MS), busyUntil, Date.now())));

        const durMs = Math.max(1, Number(it.duration) || 5) * 1000;
        if (!it.audio_url) { finishAfter(token, durMs, '사진만(duration)'); return; }
        playAudio(it, token, durMs);
    }

    function finishAfter(token, ms, why) {
        if (!cur || cur.token !== token) return null;
        const t = setTimeout(() => finish(token, why), Math.max(0, ms));
        cur.timers.push(t);
        return t;
    }

    function setBlocked(on) {
        blocked = !!on;
        try { const w = opts.stage.use('autoplayWarn'); if (w) (on ? w.show() : w.hide()); } catch (e) {}
    }

    function playAudio(it, token, durMs) {
        let safety = null;
        const arm = (ms, why) => {
            if (!cur || cur.token !== token) return;
            clearTimeout(safety);
            safety = setTimeout(() => finish(token, why), ms);
            cur.timers.push(safety);
        };
        audio.onended = () => finish(token, '재생 끝');
        audio.onerror = () => {
            // 음원을 못 받았다 — 시그니처 길이만큼은 사진을 보여 주고 넘긴다
            if (!cur || cur.token !== token) return;
            audio.onerror = null;
            clearTimeout(safety);
            finishAfter(token, durMs - (Date.now() - cur.startedAt), '음원 오류');
        };
        audio.onloadedmetadata = () => {
            const d = audio.duration;
            if (isFinite(d) && d > 0) arm(d * 1000 + 2000, '안전 타이머');
        };
        arm(Math.max(30000, durMs + 5000), '음원 응답 없음');
        audio.src = it.audio_url;
        audio.volume = vol();
        audio.muted = !!opts.monitor || !isLeader();      // 담당이 아닌 창은 소리 없이 함께 그린다
        const tryPlay = isRetry => {
            const p = audio.play();
            if (!p || !p.then) return;
            p.then(() => {
                if (cur && cur.token === token && !cur.forcedMute) setBlocked(false);
            }).catch(err => {
                if (!cur || cur.token !== token) return;
                if (err && err.name === 'AbortError') {
                    // 새 재생 요청 · 정지로 중간에 끊겼다 — 이 시그니처가 여전히 지금 것이고 멈춰 있으면 한 번만 다시(옛 tryPlay(true))
                    if (!isRetry) setTimeout(() => {
                        if (cur && cur.token === token && !cur.forcedMute && audio.getAttribute('src') && audio.paused) tryPlay(true);
                    }, 150);
                    return;
                }
                // 자동재생 차단 — 소리 없이라도 튼다(사진 · 길이 · 차례는 그대로). 방송판을 한 번 누르면 소리가 살아난다(recover).
                // 그마저 안 되면 길이만큼 보여 주고 넘긴다 — 그 사이 누르면 소리를 처음부터 다시 튼다.
                console.warn('[시그니처] 자동재생 차단 — 음소거로 재생합니다. 화면을 한 번 누르면 소리가 나옵니다:', err && err.name);
                setBlocked(true);
                cur.forcedMute = true;
                audio.muted = true;
                audio.play().catch(() => {
                    if (!cur || cur.token !== token) return;
                    cur.forcedMute = false;
                    cur.audioDead = true;
                    silence(); clearTimeout(safety);
                    cur.deadTimer = finishAfter(token, durMs - (Date.now() - cur.startedAt), '재생 불가');
                });
            });
        };
        tryPlay(false);
    }

    /* 🔊 방송판을 한 번 누르면(클릭 · 키 · 터치 = 브라우저가 인정하는 '사람 손') 막힌 소리를 살린다 — 옛 recoverFromAutoplayBlock.
       ⚠️ 실제로 막혔을 때만(blocked) 손댄다 — 막 로딩 중인 소리를 우연한 클릭이 한 번 더 틀어 두 번 나가던 옛 사고. */
    function recover() {
        try { const w = opts.stage.use('autoplayWarn'); if (w) w.hide(); } catch (e) {}
        if (!blocked) return;
        if (!cur || cur.phase !== 'play') { blocked = false; return; }
        if (cur.forcedMute && audio.getAttribute('src') && !audio.paused) {
            // 음소거로 이미 나가고 있다 — 소리만 켠다(다시 틀면 처음부터 나가 버린다)
            cur.forcedMute = false;
            blocked = false;
            audio.muted = !!opts.monitor || !isLeader();
            log('누름 — 음소거를 풀어 소리를 살립니다(재생 위치 그대로)');
            return;
        }
        if (cur.audioDead && cur.item.audio_url) {
            // 음소거 재생마저 막혀 소리가 멈춰 있다 — 지금 시그니처 소리를 처음부터 다시
            blocked = false;
            cur.audioDead = false;
            clearTimeout(cur.deadTimer); cur.deadTimer = null;
            cur.startedAt = Date.now();
            log('누름 — 막혔던 소리를 처음부터 다시 틉니다');
            playAudio(cur.item, cur.token, Math.max(1, Number(cur.item.duration) || 5) * 1000);
        }
    }
    window.addEventListener('click', recover);
    window.addEventListener('keydown', recover);
    window.addEventListener('touchstart', recover, { passive: true });

    function finish(token, why) {
        if (!cur || cur.token !== token) return;          // 지난 것의 늦은 신호
        const { id, key, replay } = cur;
        log('끝', why, id, '#' + replay);
        clearCur();
        cur = null;
        doneKeys.set(key, id);
        hideSoon();
        if (!opts.monitor) {
            if (isLeader()) sendDone(id, replay, 0);
            else {
                // 담당이 아니면 바로 안 넘긴다 — 내 음원만 먼저 끝났을 수 있다(담당이 틀던 소리가 끊긴 옛 사고).
                // 10초 뒤에도 같은 것이 맨 앞이고 담당이 아무것도 안 틀고 있으면(담당이 죽음) 대신 넘긴다.
                setTimeout(() => {
                    const head = (Q().items || [])[0];
                    if (!head || head.id !== id || (Number(head.replay) || 0) !== replay) return;
                    const lead = livePlayingLeader();
                    if (lead && !isLeader()) { log('담당 창이 아직 틀고 있어 안 넘김', id); return; }
                    console.warn('[시그니처] 담당 창이 멈춘 것 같아 대신 넘깁니다:', id);
                    sendDone(id, replay, 0);
                }, NON_LEADER_GRACE_MS);
            }
        }
        schedule(0);
    }

    function sendDone(id, replay, attempt) {
        Promise.resolve(lm.cmd('reaction.done', { id, replay })).then(res => {
            if (res && res.ok) return;
            const head = (Q().items || [])[0];
            if (!head || head.id !== id || (Number(head.replay) || 0) !== replay) return;   // 이미 빠졌다
            console.warn('[시그니처] done 실패 — 다시 보낸다:', res && res.error);
            setTimeout(() => sendDone(id, replay, attempt + 1), Math.min(5000, 500 * (attempt + 1)));
        });
    }

    function stop(why) {
        if (!cur) return;
        log('끊음', why, cur.id);
        clearCur();
        cur = null;
        hideVisuals();
    }

    // 🎚️ 편집기 미리보기 — ?monitor=1(편집기 · 폰 미리보기)에서만. 서버 · 대기줄 · 소리 없이 지금 설정(sigview)으로
    //    카드 → 줄어들기 → 'OO업' 배너를 한 번 보여 준다. 진짜 시그니처가 도는 중이면 안 한다(OBS 방송판에는 아예 없다).
    if (opts.monitor) {
        let pvTimers = [];
        opts.stage.provide('sigPreview', {
            play(sample) {
                if (cur) return false;
                pvTimers.forEach(clearTimeout);
                pvTimers = [];
                const it = Object.assign({ donator: '테스트', amount: BIG_DONATION_MIN, message: '미리보기', title: '시그니처 미리보기' }, sample || {});
                hideVisuals();
                void overlay.offsetWidth;
                try { fill(it); overlay.classList.add('show'); effects(it); showBanner(it); } catch (e) { console.error('[시그니처] 미리보기 실패:', e); }
                setReaction(true);
                const shrink = svNum('shrink_delay', SHRINK_MS);
                pvTimers.push(setTimeout(() => { if (!cur) overlay.classList.add('minimize'); }, shrink));
                pvTimers.push(setTimeout(() => { if (!cur) { hideVisuals(); schedule(0); } },
                    Math.max(shrink, svNum('title_duration', TITLE_MS)) + 2500));
                return true;
            },
        });
    }

    const card = opts.stage.use('donationCard');
    if (card) card.onIdle(() => schedule(0));
    lm.on('queue', () => schedule(0));          // 같은 쪽지 안의 후원 카드가 먼저 자리 잡게 한 박자 뒤에

    // ✂️ 쇼츠 클립(OBS 리플레이 저장 담당) — 그리는 것이 없어 칸 없이 여기서 띄운다. 못 불러와도 시그니처는 그대로 돈다.
    //    따로 띄우는 화면(?only=alert, 옛 /alertbox)은 클립을 맡지 않는다(옛 알림창에도 없었다 — 저장이 두 번 되지 않게).
    if (!opts.view) import('./more/clip.js').then(m => m.mountClip(lm, opts)).catch(e => console.error('[클립] 못 불러옴:', e));

    // 점검용 — 콘솔에서 지금 상태 보기
    window.__lmSig = { get cur() { return cur && { key: cur.key, phase: cur.phase, title: cur.item.title, forcedMute: !!cur.forcedMute, audioDead: !!cur.audioDead }; },
                       get blocked() { return blocked; }, doneKeys, audio };
}
