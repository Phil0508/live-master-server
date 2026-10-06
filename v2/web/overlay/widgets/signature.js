/* 🎵 시그니처 재생 — queue 조각 {items, paused, volume}. 맨 앞(items[0])이 지금 틀 것이다.

   흐름(옛 checkReactionQueue · playReaction · onReactionEnded 를 옮겼다)
     1) 맨 앞이 있고 · 멈춤(paused)이 아니고 · play_after 시각이 지났고 · 후원 카드가 떠 있지 않으면 시작한다.
        ⏸️ 멈춤은 '새로 시작' 만 막는다 — 이미 나가고 있는 것은 끝까지 튼다(돈 낸 후원자의 시그니처를 자르지 않는다).
     2) 시작 전에 후원 카드를 먼저 2초(stage 의 donationCard) — 단 슬롯처럼 자체 연출이 있는 것(skip_popup) ·
        대기줄이 밀린 때(2건 이상) · 10만 원 이상 · '다 틀기' 되풀이는 카드 없이 곧장(옛 것과 같다).
     3) 사진 + '후원자 · 금액' + 메시지 카드가 가운데에 뜨고 2.5초 뒤 왼쪽(180,600)으로 작게. 10만 원 이상이면 'OO업' 배너 3.5초.
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

   ⚠️ 옛 시그니처 전용 연출(sig-fx 17종 · 계엄령 경보)은 다음 단계. 여기는 사진 · 글 · 소리와
      금액 등급 기본 연출(플래시 · 흔들림 · 테두리 빛 · 가장자리 어둡게)까지만.
      💡 비트 점멸 · 사진 대표색(화면 네온 + 이 카드 테두리)은 widgets/fx/neon.js — 시작 · 끝에 stage 'neon' 을 부른다. */
import { esc, formatNum, restartClass, BIG_DONATION_MIN } from '../util.js';
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
        +   '<div class="reaction-img-box"><div class="reaction-combo"></div><img class="reaction-img" alt=""><div class="reaction-shine"></div></div>'
        +   '<div class="reaction-title-plate"></div>'
        +   '<div class="reaction-text-donator"></div>'
        +   '<div class="reaction-text-message"></div>'
        + '</div>'
        + '<div class="reaction-title-banner"></div>'
        + '</div>';
    const $ = s => root.querySelector(s);
    const overlay = $('.reaction-screen-overlay'), box = $('.reaction-img-box'), img = $('.reaction-img');
    const combo = $('.reaction-combo'), plate = $('.reaction-title-plate');
    const donatorEl = $('.reaction-text-donator'), msgEl = $('.reaction-text-message');
    const banner = $('.reaction-title-banner'), vig = $('.sig-vignette'), flash = $('.sig-flash');
    const audio = new Audio();
    audio.preload = 'auto';

    let cur = null;               // 지금 맡은 것 {key, id, replay, item, token, phase:'card'|'play', timers[], startedAt}
    const doneKeys = new Map();   // 다 틀고 done 을 보낸 것(key → id) — 서버가 뺄 때까지 다시 안 튼다
    let tickTimer = null, hideTimer = null, bannerTimer = null, comboTimer = null;
    let comboShown = { key: null, count: 0, all: false };

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
    }
    function hideSoon() { cancelHide(); hideTimer = setTimeout(hideVisuals, HIDE_DELAY_MS); }
    function hideBanner() { clearTimeout(bannerTimer); bannerTimer = null; banner.classList.remove('show'); }

    function showBanner(it) {
        hideBanner();
        if (!opts.stage.alertOn('reaction_title')) return;
        let text;
        if (it.skip_popup) {
            text = String(it.title || '').trim();                    // 슬롯 당첨 — 시그니처 이름만(접미사 없음)
        } else {
            if ((parseInt(it.amount, 10) || 0) < BIG_DONATION_MIN) return;   // '@@업' 은 10만 원 이상만
            let name = String(it.donator || '').trim();
            if (name.endsWith('님')) name = name.slice(0, -1);
            if (!name) return;
            const sfx = SV().title_suffix;
            text = name + (typeof sfx === 'string' ? sfx : '업');          // 옛 reaction_title_suffix(비우면 이름만)
        }
        if (!text) return;
        const t = tier(it.amount);
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
        const cnt = Number(it.count) || 1;
        const rep = Number(it.replay) || 0;
        const all = !!it.play_all;
        const total = cnt + rep;
        if (total <= 1) {
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
            combo.innerHTML = '<b>' + (rep + 1) + '</b> / ' + total;
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
        donatorEl.textContent = (it.donator || '익명') + (amt ? ' · ' + formatNum(amt) + '원' : '');
        const msg = String(it.message || '');
        msgEl.textContent = (msg && msg !== '수동 후원 송출') ? msg : '';
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
    function setReaction(on) { opts.stage.setMode('reaction', on); }

    function tick() {
        tickTimer = null;
        const q = Q();
        const items = q.items || [];
        const head = items[0];
        const ids = new Set(items.map(it => it.id));
        doneKeys.forEach((id, k) => { if (!ids.has(id)) doneKeys.delete(k); });

        if (cur) {
            if (head && keyOf(head) === cur.key) {
                if (cur.phase === 'play') { audio.volume = vol(); syncCombo(head); }
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
        try {
            fill(it);
            overlay.classList.remove('minimize');
            overlay.classList.add('show');
            syncCombo(it);
            effects(it);
            showBanner(it);
        } catch (e) { console.error('[시그니처] 그리기 실패 — 소리 · 차례는 계속:', e); }
        // 💡 조명(widgets/fx/neon.js) — 사진 대표색(화면 네온 · 이 카드 테두리) · 30만 등급 비트 맞추기(옛 applySignatureThemeColor · beginBeatSync)
        try {
            const neon = opts.stage.use('neon');
            if (neon) neon.sigPlay(it, audio).then(rgb => { if (rgb && cur && cur.token === token) box.style.setProperty('--reac-glow', rgb); });
        } catch (e) { /* 조명이 넘어져도 재생은 그대로 */ }
        cur.timers.push(setTimeout(() => overlay.classList.add('minimize'), svNum('shrink_delay', SHRINK_MS)));

        const durMs = Math.max(1, Number(it.duration) || 5) * 1000;
        const after = (ms, why) => { if (cur && cur.token === token) cur.timers.push(setTimeout(() => finish(token, why), Math.max(0, ms))); };
        if (!it.audio_url) { after(durMs, '사진만(duration)'); return; }

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
            after(durMs - (Date.now() - cur.startedAt), '음원 오류');
        };
        audio.onloadedmetadata = () => {
            const d = audio.duration;
            if (isFinite(d) && d > 0) arm(d * 1000 + 2000, '안전 타이머');
        };
        arm(Math.max(30000, durMs + 5000), '음원 응답 없음');
        audio.src = it.audio_url;
        audio.volume = vol();
        audio.muted = !!opts.monitor || !isLeader();      // 담당이 아닌 창은 소리 없이 함께 그린다
        const p = audio.play();
        if (p && p.catch) p.catch(err => {
            if (!cur || cur.token !== token) return;
            if (err && err.name === 'AbortError') return;
            // 자동재생 차단 — 소리 없이라도 튼다(사진 · 길이 · 차례는 그대로). 그마저 안 되면 길이만큼 보여 주고 넘긴다
            console.warn('[시그니처] 자동재생 차단 — 음소거로 재생:', err && err.name);
            cur.forcedMute = true;
            audio.muted = true;
            audio.play().catch(() => {
                if (!cur || cur.token !== token) return;
                silence(); clearTimeout(safety);
                after(durMs - (Date.now() - cur.startedAt), '재생 불가');
            });
        });
    }

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
    import('./more/clip.js').then(m => m.mountClip(lm, opts)).catch(e => console.error('[클립] 못 불러옴:', e));

    // 점검용 — 콘솔에서 지금 상태 보기
    window.__lmSig = { get cur() { return cur && { key: cur.key, phase: cur.phase, title: cur.item.title }; }, doneKeys, audio };
}
