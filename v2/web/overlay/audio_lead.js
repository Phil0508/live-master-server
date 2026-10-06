/* 🔊 소리 담당(리더) 정하기 — 방송판을 여러 곳에 띄워도 소리는 한 창에서만(옛 isAudioLeader 그대로).
   같은 컴퓨터의 방송판끼리 BroadcastChannel 로 1초마다 '나 살아 있어'(heartbeat)를 주고받는다.
   정하는 법
     - ?monitor=1(미리보기)은 절대 소리를 안 낸다.
     - ?audio=1 을 붙인 창은 언제나 소리 담당(두 창에 같이 붙이면 소리가 두 번 난다 — 한 곳에만).
     - **보이는 창 먼저** — OBS 에서 숨긴 소스(다른 장면)도 페이지는 살아 있다. 그게 담당이 되면 OBS 는 안 보이는 소스의
       소리를 방송에 안 섞어서 시그니처가 통째로 무음이 된다(옛 사고 — 클릭으로도 안 풀렸다). 보이는 창이 있으면 숨은 창은 양보.
     - 같은 처지끼리는 번호(tabId)가 작은 쪽.
     - ⚠️ 잘못되면 '언제나 소리 냄' 쪽으로(fail-open) — 채널이 없거나 오류면 혼자인 것으로 본다. 절대 조용해지지 않게.
   '다 틀었다'(reaction.done)도 소리 담당이 보낸다 — 다른 창이 먼저 보내면 담당이 틀던 소리가 끊겼다(옛 '음원이 몇 초 만에 끝남').
   담당이 아니면 10초 기다렸다가, 그때도 같은 것이 맨 앞이고 담당이 아무것도 안 틀고 있을 때만 대신 보낸다(담당이 죽은 경우). */

const QS = new URLSearchParams(location.search);
const MONITOR = QS.get('monitor') === '1';
const FORCE = QS.get('audio') === '1';
const TAB_ID = Math.random().toString(36).slice(2) + '_' + performance.now().toFixed(0);
export const NON_LEADER_GRACE_MS = 10000;

const peers = {};          // tabId → {seen, visible, leader, playing}
const changeFns = [];
let channel = null, playing = null, lastLeader = null;

const visible = () => !document.hidden;

export function isLeader() {
    if (MONITOR) return false;
    if (FORCE) return true;
    const now = performance.now();
    const alive = [];
    for (const id in peers) {
        const p = peers[id];
        if (p && now - p.seen < 3000) alive.push({ id, visible: !!p.visible });
    }
    const me = visible();
    if (!me && alive.some(p => p.visible)) return false;
    let min = TAB_ID;
    for (const p of alive) {
        if (me && !p.visible) continue;
        if (p.id < min) min = p.id;
    }
    return min === TAB_ID;
}

/** 지금 무엇을 틀고 있나(시그니처 큐 id) — 다른 창이 '담당이 멈췄나' 를 가를 때 본다 */
export function setPlaying(id) { playing = id || null; beat(); }

/** 살아 있는 담당이 무언가를 틀고 있으면 그 정보, 아니면 null */
export function livePlayingLeader() {
    const now = performance.now();
    for (const id in peers) {
        const p = peers[id];
        if (p && now - p.seen <= 3000 && p.leader && p.playing) return p;
    }
    return null;
}

/** 담당이 바뀌면(창이 닫히거나 숨거나 새로 뜸) — 음소거를 다시 맞출 때 */
export function onLeaderChange(fn) { changeFns.push(fn); }

function beat() {
    try { if (channel) channel.postMessage({ tabId: TAB_ID, visible: visible(), leader: isLeader(), playing }); } catch (e) {}
}
function check() {
    const now = isLeader();
    if (now !== lastLeader) {
        lastLeader = now;
        console[now ? 'log' : 'warn'](now ? '🔊 이 창이 소리를 냅니다' : (MONITOR ? '🔇 미리보기 창 — 소리 없음' : '🔇 다른 방송판 창이 소리를 맡고 있어 이 창은 음소거'));
        changeFns.forEach(fn => { try { fn(now); } catch (e) { console.error(e); } });
    }
}

try {
    if (!MONITOR && 'BroadcastChannel' in window) {
        channel = new BroadcastChannel('lm2-overlay-audio');
        channel.onmessage = ev => {
            const d = ev && ev.data;
            if (d && d.tabId && d.tabId !== TAB_ID) {
                peers[d.tabId] = { seen: performance.now(), visible: !!d.visible, leader: !!d.leader, playing: d.playing || null };
            }
        };
        setInterval(() => {
            beat();
            const now = performance.now();
            for (const id in peers) if (now - peers[id].seen > 4000) delete peers[id];
            check();
        }, 1000);
        document.addEventListener('visibilitychange', () => { beat(); check(); });
        beat();
    }
} catch (e) { console.warn('[소리 담당] 채널을 못 열었어요 — 이 창은 언제나 소리를 냅니다', e); channel = null; }
check();

window.__lmAudio = { get leader() { return isLeader(); }, get peers() { return Object.keys(peers).length; }, tabId: TAB_ID };
