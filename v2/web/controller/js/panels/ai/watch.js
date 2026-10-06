/* 🔔 먼저 알려 주기 — 셈과 감지는 코드가 한다(공짜 · 바로). 알릴 만한 순간만 AI 대화에 한 줄 띄운다(옛 aiProactiveCheck).
   ⚠️ 소리는 내지 않는다. AI 탭이 안 보이면 탭 단추에 안 읽은 숫자 + 짧은 알림(토스트).
   규칙(옛 것과 같은 기준)
     · 큰 후원(5만 원 이상)이 대기함에 들어옴 · 1분에 4건 넘게 몰림(1분에 한 번)
     · 대기함에 6건 넘게 밀림(1분 반에 한 번)
     · 후원이 3분째 대기 중 — 점수를 아직 안 줬다(후원 1건에 한 번)
     · 대결 30초 남음(대결 1번에 한 번)
     · 목표를 넘었는데 축하 연출을 아직 안 눌렀음(목표 1개에 한 번)
   켜고 끄기는 이 컴퓨터에 기억한다(lm2_ai_proactive — 처음엔 켜짐). 옛 '오프라인 백업 알림' 은 v2 에 백업 단추가 없어 뺐다. */
import { serverNow, aiTabVisible, getCtx } from './common.js';
import * as chat from './chatlog.js';
import { won, num } from '../../util.js';

const KEY = 'lm2_ai_proactive';
const BIG = 50000;
const FORGOT_MS = 180000;

let enabled = readOn();
let seeded = false;
const seen = new Set();          // 이미 본 대기함 후원 id
const forgot = new Set();        // '3분째' 알린 id
let arrivals = [];               // 최근 후원이 들어온 시각(ms)
const lastAt = {};               // 규칙 → 마지막 알린 시각
const subs = new Set();

function readOn() {
    try { return localStorage.getItem(KEY) !== 'off'; } catch (e) { return true; }
}
export function isOn() { return enabled; }
export function onChange(fn) { subs.add(fn); }
export function toggle() {
    enabled = !enabled;
    try { localStorage.setItem(KEY, enabled ? 'on' : 'off'); } catch (e) { /* 기억 못 해도 된다 */ }
    subs.forEach(fn => { try { fn(enabled); } catch (e) { /* 무시 */ } });
}

function can(key, gapMs) {
    const now = Date.now();
    if (lastAt[key] && now - lastAt[key] < gapMs) return false;
    lastAt[key] = now;
    return true;
}

function say(text) {
    chat.add('alert', '🔔 ' + text);
    const ctx = getCtx();
    if (ctx && !aiTabVisible()) ctx.toast('🔔 ' + text, 'info', 5000);
}

/** 조각이 바뀔 때 · 15초마다 */
export function check(slices) {
    if (!slices) return;
    const live = !!(slices.session || {}).live;
    const pend = (slices.pending || []).filter(x => x && x.type !== 'off_work');
    // 처음 한 번은 '이미 있던 것' 으로 적어만 둔다(새로 고칠 때마다 큰 후원 · 3분째 알림이 한꺼번에 쏟아지지 않게 —
    // 오래 기다린 후원은 상황판 대기함 칸이 주황으로 알린다)
    if (!seeded) {
        const sNow0 = serverNow();
        pend.forEach(x => {
            seen.add(x.id);
            if (Number(x.at) && sNow0 - Number(x.at) >= FORGOT_MS) forgot.add(x.id);
        });
        seeded = true;
        return;
    }
    const ids = new Set(pend.map(x => x.id));
    const now = Date.now();
    pend.forEach(x => {
        if (seen.has(x.id)) return;
        seen.add(x.id);
        if (x.kind === 'contrib' || x.returned) return;
        arrivals.push(now);
        if (enabled && live && (Number(x.amount) || 0) >= BIG) say(`방금 ${x.name || '익명'}님 ${won(x.amount)} 후원! 큰 금액이에요 🎉`);
    });
    for (const id of [...seen]) if (!ids.has(id)) seen.delete(id);
    arrivals = arrivals.filter(t => now - t < 60000);
    if (!enabled || !live) return;

    if (arrivals.length >= 4 && can('surge', 60000)) say(`후원이 몰리고 있어요 — 최근 1분에 ${arrivals.length}건. 대기함을 봐 주세요.`);
    if (pend.length >= 6 && can('backlog', 90000)) say(`대기함에 후원 ${pend.length}건이 밀려 있어요. 잠깐 정리하는 게 좋아요.`);

    // 3분째 대기 — 대기함 시각(at)은 서버 시각(ms)
    const sNow = serverNow();
    pend.forEach(x => {
        if (x.kind === 'contrib' || forgot.has(x.id)) return;
        const at = Number(x.at) || 0;
        if (at && sNow - at >= FORGOT_MS) {
            forgot.add(x.id);
            const mins = Math.max(1, Math.round((sNow - at) / 60000));
            say(`${x.name || '익명'}님 ${won(x.amount)} 후원이 ${mins}분째 대기 중이에요 — 아직 점수를 안 줬어요!`);
        }
    });
    for (const id of [...forgot]) if (!ids.has(id)) forgot.delete(id);

    // 대결 30초 남음 — 대결 한 번에 한 번
    const m = slices.match || {};
    const tm = m.timer || {};
    const left = tm.running && tm.end_ms ? Number(tm.end_ms) - sNow : -1;
    if (m.active && left > 0 && left <= 30000) {
        if (!lastAt.match_end) {
            lastAt.match_end = now;
            const ps = (m.teams || []).slice().sort((a, b) => (Number(b.score) || 0) - (Number(a.score) || 0));
            if (ps.length >= 2) {
                const gap = (Number(ps[0].score) || 0) - (Number(ps[1].score) || 0);
                say(gap ? `대결 30초 남았어요! ${ps[0].name} ${num(gap)}점 앞섬 (${ps[0].name} ${num(ps[0].score)} : ${ps[1].name} ${num(ps[1].score)})`
                        : `대결 30초 남았어요! 지금 동점이에요 (${num(ps[0].score)} : ${num(ps[1].score)})`);
            } else say('대결 30초 남았어요!');
        }
    }
    if (!m.active) delete lastAt.match_end;

    // 목표 — 막대와 같은 셈(운영비 + 본판 점수 합 + 보정). 축하 연출(goal.celebrate)을 이 목표로 눌렀으면 끝
    const g = slices.goal || {};
    const tgt = Number(g.target) || 0;
    const P = slices.players || {};
    const cur = (Number((P.bottom || {}).score) || 0) + (P.list || []).reduce((a, p) => a + (Number(p.score) || 0), 0) + (Number(g.offset) || 0);
    const pg = (slices.popup || {}).goal || null;
    const waitGoal = tgt > 0 && cur >= tgt && !(pg && Number(pg.target) === tgt);
    if (waitGoal && can('goal', 3600000)) say(`목표 ${num(tgt)}점을 넘었어요 (지금 ${num(cur)}점). 달성 축하 연출이 아직 안 나갔어요.`);
    if (!waitGoal) delete lastAt.goal;
}
