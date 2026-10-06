/* 📣 안내 전광판 — notice 조각(msgs · period · speed · now) + tallies.notice_donors(소액 후원자 한 줄).
   옛 renderNotice 그대로:
   - 머리 줄(6,115 · 폭 1068 · 높이 48). TV 밑 자막처럼 오른쪽 밖에서 들어와 왼쪽 밖으로 한 번 흐른다.
   - **서버 시계**로 '지금 띄울 차례' 를 계산한다 — period 초마다 한 줄씩 차례로(회차 번호 = 서버 시각 / period).
     방송판이 몇 개든 같은 문구가 같은 순간 같은 자리를 흐른다(서버가 주기마다 밀어 주지 않는다).
   - 한 바퀴 시간 = (칸 폭 + 글자 폭) / 속도. 길수록 오래 — 다음 회차를 밀지 않게 period - 1초까지.
   - 진행자가 '지금 띄우기'(now.ts 가 바뀜)를 누르면 그 줄을 바로 한 바퀴 — 한 바퀴면 끝(옛 사고: 2분간 자동 전광판이 안 떴다).
     now.text 가 있으면(v2: 목록에 없는 한 줄) 그 글을 흘린다.
   - 소액 후원자(시그니처를 안 튼 것)는 **한 줄로 묶어** 순환에 끼운다(최근 8명 · 나머지는 '외 N분').
   - *강조* 는 굵은 금색. 문구는 운영자가 적는 글이라 글자로 만든 뒤 강조만 바꾼다.
   - 계좌가 머리 줄로 올라와 있으면(게임판이 점수판 자리를 쓰는 동안) 오른쪽으로 물러난다(654 · 폭 388) — 옛 syncAccountPos.
   - 띠가 내려가 있을 때는 칸이 자리를 안 차지한다(게이지 금액 딱지가 비킬 판으로 안 센다 — 옛 placeGoalTip 과 같다). */
import { serverNow, startClock } from './clock.js';
import { AWAY_STAGES } from './account.js';

const DONOR_SHOW = 8;
const FULL_W = 1068, AWAY_X = 648, AWAY_W = 388;     // 칸이 6 에 있으니 654 - 6 = 648

function markup(t) {
    const esc = String(t).replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[m]));
    return esc.replace(/\*([^*]+)\*/g, '<b>$1</b>');
}

function donorLine(list) {
    if (!Array.isArray(list) || !list.length) return '';
    const last = list.slice(-DONOR_SHOW);
    const part = last.map(x => '*' + String((x && x.name) || '익명') + '* '
        + (Number((x && x.amount) || 0)).toLocaleString() + '원').join(' · ');
    const more = list.length > last.length ? ' 외 ' + (list.length - last.length) + '분' : '';
    return '💛 후원 고맙습니다 — ' + part + more;
}

export function mount(root, lm, opts) {
    startClock(lm);
    root.innerHTML = '<div class="notice-board">'
        + '<span class="notice-ico">📣</span>'
        + '<div class="notice-view"><span class="notice-txt"></span>'
        + '<span class="notice-txt notice-measure" aria-hidden="true"></span></div></div>';
    const bar = root.querySelector('.notice-board');
    const view = root.querySelector('.notice-view');
    const txt = root.querySelector('.notice-txt:not(.notice-measure)');
    const mel = root.querySelector('.notice-measure');
    const wCache = {};
    let lastText = '', cycle = '', lastAway = null;

    function dur(t, viewW, speed, period) {
        if (wCache[t] == null) {
            mel.innerHTML = markup(t);
            const w = mel.scrollWidth;
            if (!w) return 8000;                 // 아직 못 잼(글꼴 · 칸이 안 그려짐) — 기억하지 않는다
            wCache[t] = w;
        }
        const d = (viewW + wCache[t]) / speed * 1000;
        return Math.max(3000, Math.min(d, period - 1000));   // 다음 회차를 밀지 않게
    }

    function hide() {
        if (bar.classList.contains('show')) { bar.classList.remove('show'); opts.stage.layoutChanged(); }
        cycle = '';
    }

    function render() {
        // 계좌가 머리 줄에 올라와 있으면 오른쪽으로 물러난다(띠가 내려가 있어도 자리는 미리)
        const sh = lm.get('show') || {};
        const away = AWAY_STAGES.includes(sh.stage) || !!(lm.get('players') || {}).extra_active;
        if (away !== lastAway) {
            lastAway = away;
            bar.style.setProperty('--nb-x', (away ? AWAY_X : 0) + 'px');
            bar.style.setProperty('--nb-w', (away ? AWAY_W : FULL_W) + 'px');
            for (const k in wCache) delete wCache[k];          // 칸 폭이 바뀌면 한 바퀴 시간도 바뀐다
            cycle = '';
        }
        if (!opts.stage.isOn(opts.layer.id)) { hide(); return; }   // 고정 자리 스위치 [공지] 꺼짐

        const n = lm.get('notice') || {};
        const msgs = (n.msgs || []).map(m => String(m || '')).filter(m => m.trim());
        const tal = lm.get('tallies') || {};
        const dl = donorLine(tal.notice_donors);
        if (dl) msgs.push(dl);
        const donorIdx = dl ? msgs.length - 1 : -1;
        const donorTag = dl ? ':' + (tal.notice_donors || []).length : '';

        const now = serverNow();
        const period = Math.max(20, parseInt(n.period, 10) || 300) * 1000;
        const speed = Math.max(40, Math.min(600, parseInt(n.speed, 10) || 130));   // 초당 px
        const viewW = view.clientWidth || 1000;

        // ⚠️ 수동으로 띄운 것도 '한 바퀴' 면 끝이다
        let idx = -1, elapsed = 0, cyc = '', t = '';
        const nw = n.now || {};
        const mEl = nw.ts ? (now - Number(nw.ts)) : -1;
        if (mEl >= 0) {
            let mt = '', mTag = '';
            if (nw.text) mt = String(nw.text);
            else if (msgs.length) {
                const mi = Math.max(0, Math.min(msgs.length - 1, parseInt(nw.idx, 10) || 0));
                mt = msgs[mi];
                if (mi === donorIdx) mTag = donorTag;
            }
            if (mt && mEl < dur(mt, viewW, speed, period)) { t = mt; elapsed = mEl; cyc = 'M' + nw.ts + mTag; idx = 0; }
        }
        if (idx < 0 && msgs.length) {
            // 주기 구간마다 한 번 흐른다. 구간 번호가 곧 회차다.
            const pIdx = Math.floor(now / period) % msgs.length;
            const pEl = now % period;
            if (pEl < dur(msgs[pIdx], viewW, speed, period)) {
                t = msgs[pIdx]; elapsed = pEl; idx = pIdx;
                // ⚠️ 소액 줄은 후원이 들어올 때마다 글자가 바뀐다 — 인원을 붙여 바뀐 순간 흐름을 다시 시작한다
                cyc = 'C' + Math.floor(now / period) + (pIdx === donorIdx ? donorTag : '');
            }
        }
        if (idx < 0) { hide(); return; }

        const d = dur(t, viewW, speed, period);
        if (t !== lastText) { lastText = t; txt.innerHTML = markup(t); }
        if (cyc !== cycle) {
            cycle = cyc;
            // 서버 시계가 가리키는 지점부터 튼다(음수 지연) — 방송판이 몇 개든 같은 자리를 흐른다
            txt.style.setProperty('--nw', viewW + 'px');
            txt.style.animation = 'none';
            void txt.offsetWidth;
            txt.style.animation = 'noticeFlow ' + Math.round(d) + 'ms linear -' + Math.round(elapsed) + 'ms 1 both';
        }
        if (!bar.classList.contains('show')) { bar.classList.add('show'); opts.stage.layoutChanged(); }
    }

    const safe = () => { try { render(); } catch (e) { console.error('[안내 전광판] 갱신 실패 — 방송은 계속됩니다:', e); } };
    ['notice', 'tallies', 'show', 'players', 'session'].forEach(k => lm.on(k, safe));
    // 시계로 판단하므로 상태가 안 와도 스스로 때를 안다(옛 것과 같은 0.25초)
    setInterval(safe, 250);
    // 글꼴이 늦게 받아지면 글자 폭이 바뀐다 — 다시 잰다
    try { document.fonts.addEventListener('loadingdone', () => { for (const k in wCache) delete wCache[k]; }); } catch (e) {}
}
