/* ✂️ 쇼츠 클립 — 이 방송판이 OBS 의 '리플레이 버퍼 저장' 담당이다(옛 overlay.html 의 CLIP 을 옮겼다 · 서버 domain/clip.py).

   그리는 것이 없는 모듈이라 층(칸)이 없다 — 시그니처 위젯(widgets/signature.js)이 붙을 때 같이 띄운다.
   다른 위젯은 stage.use('clip') 로 부른다: bigSig(대기줄 줄) · allClear(올클리어 ts).

   OBS 는 최근 몇 분을 늘 기억한다(블랙박스). 명장면이면 이 화면이 OBS 에 "저장" 이라고 말한다.
   ⏱ 대표님 09-30 "누르는 순간 기준 전 90초 ~ 후 90초" → 그 순간에서 **90초 뒤에** 저장한다
      = OBS 가 기억하는 180초가 앞 90초 + 뒤 90초. 조종실 [✂ 클립] · 큰 시그 · 올클리어 모두 같다.
      ⚠️ OBS 리플레이 버퍼 '최대 시간' 이 180초여야 한다(90초면 뒤 90초만 남는다). 방송판은 이 값을 못 바꾼다.
   누가 저장하나 — 두 방송판이 같은 클립을 두 번 저장하지 않게(옛 규칙 그대로)
      · OBS 브라우저 소스 속성 → 페이지 권한 → 'OBS 에 대한 고급 접근 권한'(4) 이상인 방송판만 저장한다.
        장면마다 방송판이 있어도 권한을 준 하나만 저장한다(조종실 안내: '한 곳에만 주세요').
      · OBS 밖(폰 · 편집기 · 브라우저)에는 window.obsstudio 가 없어 아무 일도 안 한다.
      · 미리보기(?monitor=1)는 OBS 안이어도 아무것도 안 한다 — 저장도, 서버에 알리기도.
   ⚠️ 두 순간이 30초 안에 붙으면 파일 하나로 담는다(뒤 순간 기준으로 저장 — 앞 순간은 앞쪽이 그만큼 덜 담긴다).
      그보다 멀면 따로 저장한다 — 버리지 않는다.
   💾 기다리는 저장은 이 방송판(OBS 안) 저장소에 적어 둔다. 90초를 기다리는 사이 새로고침되거나
      꺼졌다 켜져도 되살려 저장한다. 저장 시각이 2분 30초 넘게 지난 것은 버퍼(180초)에 거의 안 남아 버린다.
   조종실 [✂ 클립] — 공개 조각 clip.ask{id, at(서버 ms), label, delay_ms}. id 가 처음 보는 것이면 한 번 예약한다
      (옛 것은 SSE 'clip' 사건이었다). 누른 **서버 시각** 에서 90초 뒤로 잡는다 — 다시 붙어 늦게 받아도 순간이 그대로다.
      본 id 는 저장소에 적어 둔다(새로고침 뒤 같은 것을 또 예약하지 않게).
   권한 확인(3초 뒤 · 1분마다)이 끝나기 전에 온 순간은 들고 있다가 확인되면 건다(옛 것은 그 사이 순간을 놓쳤다). */

const CLIP_AFTER = 90000;          // 순간 뒤 90초에 저장 = 앞 90초 + 뒤 90초(버퍼 180초 기준)
const CLIP_MERGE = 30000;          // 이만큼 안에 붙은 순간은 파일 하나로
const STALE_MS = 150000;           // 저장 시각이 이만큼 지난 것은 버린다(버퍼에 거의 안 남는다)
const PEND_KEY = 'lm2_clip_pend';  // 기다리는 저장(새로고침 대비)
const SEEN_KEY = 'lm2_clip_seen';  // 이미 예약한 조종실 클립 id
const SEEN_MAX = 30;
const NOOP = Object.freeze({ bigSig() {}, allClear() {}, enabled: false });

function readJSON(key, dflt) {
    try { const v = JSON.parse(localStorage.getItem(key) || 'null'); return v == null ? dflt : v; } catch (e) { return dflt; }
}
function writeJSON(key, v) {
    try { localStorage.setItem(key, JSON.stringify(v)); } catch (e) { /* 저장소가 막혀도 저장 자체는 된다 */ }
}

export function mountClip(lm, opts) {
    const stage = opts.stage;
    const obs = () => (window.obsstudio && typeof window.obsstudio === 'object') ? window.obsstudio : null;
    if (opts.monitor || !obs()) {               // 미리보기 · OBS 밖 — 아무것도 안 한다
        stage.provide('clip', NOOP);
        return NOOP;
    }

    const C = { level: -1, checked: false, rb: null, err: '', timer: null, pend: [], firedRefs: null, confirmT: null,
                restored: false, recheck: false, early: [] };
    const seen = readJSON(SEEN_KEY, []).filter(x => typeof x === 'string');

    function hello(extra) {
        try {
            fetch('/api/clip/hello', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(Object.assign({ level: C.level, rb: C.rb, err: C.err }, extra || {})) }).catch(() => {});
        } catch (e) { /* 알리기 실패는 다음 1분에 */ }
    }

    function check() {
        const o = obs();
        if (!o) return;
        try {
            if (typeof o.getControlLevel !== 'function') { C.err = 'OBS 가 낡았어요(28 이상 필요)'; C.checked = true; hello(); return; }
            o.getControlLevel(lv => {
                C.level = Number(lv);
                C.checked = true;
                if (!(C.level >= 4)) { C.err = '페이지 권한이 낮아요'; C.rb = null; C.early = []; hello(); return; }
                restore();                     // 권한이 확인된 첫 순간 — 새로고침 전에 기다리던 저장을 되살린다
                flushEarly();
                o.getStatus(st => {
                    C.rb = !!(st && st.replaybuffer);
                    C.err = '';
                    // 리플레이 버퍼가 꺼져 있으면 켠다. OBS 설정에서 '리플레이 버퍼 사용' 이 꺼져 있으면 켜지지 않는다.
                    if (!C.rb) {
                        try { o.startReplayBuffer(); } catch (e) { C.err = '리플레이 버퍼를 못 켰어요'; }
                        // 켜졌는지 3초 뒤 다시 본다 — 켜짐 신호(obsReplaybufferStarted)가 안 오는 OBS 도 있다
                        if (!C.recheck) { C.recheck = true; setTimeout(() => { C.recheck = false; check(); }, 3000); }
                    }
                    hello();
                });
            });
        } catch (e) { C.err = String((e && e.message) || e).slice(0, 60); hello(); }
    }

    /* 💾 저장이 확인되면 '무엇을 저장했나(열쇠)' 를 서버에 알린다 — 회사 PC 도우미가 파일 이름을 붙일 때 쓴다.
       OBS 가 저장됨 신호(obsReplaybufferSaved)를 안 주면 4초 뒤 그냥 알린다. */
    function confirm() {
        if (!C.firedRefs) return;
        if (C.confirmT) { clearTimeout(C.confirmT); C.confirmT = null; }
        hello({ saved: true, refs: C.firedRefs.slice(0, 10) });
        C.firedRefs = null;
    }
    const persist = () => writeJSON(PEND_KEY, C.pend);
    // 다음 저장 시각에 맞춰 건다. ⚠️ 방금 저장한 것의 확인(4초)이 끝나기 전에 또 저장하지 않게 5초는 띄운다
    function arm() {
        if (C.timer) { clearTimeout(C.timer); C.timer = null; }
        const p = C.pend[0];
        if (!p) return;
        C.timer = setTimeout(fire, Math.max(p.due - Date.now(), C.firedRefs ? 5000 : 0, 0));
    }
    function fire() {
        C.timer = null;
        const p = C.pend.shift();
        persist();
        const o = obs();
        if (p && o) {
            try {
                if (C.firedRefs) confirm();    // 앞 저장 확인이 아직이면 먼저 알린다(열쇠가 섞이지 않게)
                o.saveReplayBuffer();
                console.log('✂️ [클립] 리플레이 저장 (앞 90초 + 뒤 90초)', p.refs);
                C.firedRefs = (p.refs || []).slice();
                C.confirmT = setTimeout(confirm, 4000);
            } catch (e) { C.err = '저장 실패'; hello(); }
        }
        arm();
    }
    /* 저장 예약 — at 은 이 PC 시계(ms) 기준 '저장할 때' */
    function saveAt(at, why, ref) {
        if (!C.checked) {                                                 // 권한 확인 전 — 들고 있다가(최근 20개)
            C.early.push([at, why, ref]);
            if (C.early.length > 20) C.early.shift();
            return;
        }
        if (!(C.level >= 4)) return;
        if (Date.now() - at >= STALE_MS) return;
        const r = ref ? String(ref) : '';
        console.log('✂️ [클립] 저장 예약 +' + Math.max(0, Math.round((at - Date.now()) / 1000)) + '초 · ' + (why || ''));
        const last = C.pend[C.pend.length - 1];
        if (last && at - last.first <= CLIP_MERGE && at >= last.first - CLIP_MERGE) {   // 붙은 순간 — 뒤 순간까지 기다려 파일 하나로
            if (r && last.refs.indexOf(r) < 0) last.refs.push(r);
            if (at > last.due) last.due = at;
        } else {
            C.pend.push({ due: at, first: at, refs: r ? [r] : [] });
            C.pend.sort((a, b) => a.due - b.due);
        }
        persist();
        arm();
    }
    function flushEarly() {
        const xs = C.early;
        C.early = [];
        xs.forEach(([at, why, ref]) => saveAt(at, why, ref));
    }
    function restore() {
        if (C.restored) return;
        C.restored = true;
        let old = readJSON(PEND_KEY, []);
        const now = Date.now();
        old = (Array.isArray(old) ? old : []).filter(p =>
            p && typeof p.due === 'number' && typeof p.first === 'number' && Array.isArray(p.refs) && now - p.due < STALE_MS);
        if (!old.length) { persist(); return; }
        console.log('✂️ [클립] 새로고침 전에 기다리던 저장 ' + old.length + '개를 되살림');
        C.pend = old.concat(C.pend).sort((a, b) => a.due - b.due);
        persist();
        arm();
    }
    // 저절로 저장 기준 — 끄면 0(옛 clipAuto)
    function autoMin() {
        const c = lm.get('clip') || {};
        return c.auto !== false ? (Number(c.auto_min) || 0) : 0;
    }

    // 조종실 [✂ 클립] — 누른 서버 시각 + 90초(+ 미룸)에 저장
    function onAsk(ask) {
        if (!ask || !ask.id || seen.indexOf(String(ask.id)) >= 0) return;
        seen.push(String(ask.id));
        while (seen.length > SEEN_MAX) seen.shift();
        writeJSON(SEEN_KEY, seen);
        const skew = lm.serverNow() - Date.now();                 // 서버 시계 - 이 PC 시계
        const pressed = (Number(ask.at) || lm.serverNow()) - skew;  // 이 PC 시계로 누른 때
        saveAt(pressed + CLIP_AFTER + Math.max(0, Number(ask.delay_ms) || 0), ask.label || '조종실', ask.id);
    }
    lm.on('clip', c => { try { onAsk(c && c.ask); } catch (e) { console.error('[클립]', e); } });

    window.addEventListener('obsReplaybufferSaved', () => { if (C.firedRefs) confirm(); else hello({ saved: true }); });
    window.addEventListener('obsReplaybufferStarted', () => { C.rb = true; hello(); });
    window.addEventListener('obsReplaybufferStopped', () => { C.rb = false; hello(); });
    setTimeout(check, 3000);
    setInterval(check, 60000);

    const api = {
        enabled: true,
        /* 🎵 시그니처가 실제로 재생된다 — 기준 금액 이상이면(반응까지 담기게) 90초 뒤 저장. it = 대기줄 줄 */
        bigSig(it) {
            const m = autoMin();
            if (m && Number(it && it.amount) >= m) saveAt(Date.now() + CLIP_AFTER, ((it.donator || '') + ' ' + it.amount).trim(), it.id);
        },
        /* 🃏 시그뒤집기 올클리어 — ts 는 서버가 찍은 연출 시각(목록 열쇠 'allclear:ts' 와 같다) */
        allClear(ts) {
            if (autoMin()) saveAt(Date.now() + CLIP_AFTER, '올클리어', 'allclear:' + ts);
        },
    };
    stage.provide('clip', api);
    window.__lmClip = { get state() { return { level: C.level, rb: C.rb, err: C.err, pend: C.pend.slice(), checked: C.checked }; } };   // 점검용
    return api;
}
