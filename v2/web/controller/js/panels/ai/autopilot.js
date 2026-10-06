/* 🚗 오토파일럿 — 자리를 비운 동안 '확실한 후원만' 대신 준다. 돈이 걸린 기능이라 원칙을 못 박아 둔다(옛 조종실 그대로):
     1) 서버가 tier 'auto'(이름이 메시지에 딱 · 별명 · 늘 같은 사람)라고 한 것만. 애매하면 손대지 않고 대기함에 둔다
        (틀리게 주는 것보다 안 주고 기다리는 게 언제나 낫다).
     2) 그 이름이 지금 판 선수여야 한다(환각 · 그새 빠진 선수 막기).
     3) 한 번에 한 건 — 주고 나서 다음 것을 본다. 같은 후원은 한 번만(이 화면을 연 동안 계속 기억한다).
     4) 한 일은 전부 적고, 끌 때 보여 준다. 잘못 갔으면 그 자리에서 [되돌리기] → score.undo{ref: 후원 id}
        (점수가 빠지고 후원이 대기함으로 돌아온다 · 서버의 '후원자 기억' 도 잊는다) → 맞는 사람에게 다시 준다.
     5) 새로 고치면 꺼진 채로 시작한다 — 켜져 있는 걸 모르는 상태가 가장 위험하다. 그래서 어디에도 저장하지 않는다.
   v2 에서 더한 것
     · 되돌려 돌아온 후원(returned)은 자동으로 주지 않는다 — 사람이 되돌린 것은 사람이 다시 정한다.
     · 방송이 끝나면 저절로 꺼진다(기록은 보여 준다).
     · 켜져 있는 동안 머리줄 아래에 붉은 띠 — 어느 탭을 보고 있어도 보인다. [끄기] 가 거기 있다. */
import { h, currentNames, isDonation, getCtx, openAiTab, hms } from './common.js';
import * as sug from './suggest.js';
import * as chat from './chatlog.js';
import { manWon, won } from '../../util.js';

const st = { on: false, busy: false, log: [], handled: new Set(), banner: null, count: null, subs: new Set(), watching: false };

export function isOn() { return st.on; }
export function onChange(fn) { st.subs.add(fn); }
function changed() {
    st.subs.forEach(fn => { try { fn(st.on); } catch (e) { console.error('[오토파일럿]', e); } });
    paintBanner();
}

export function toggle() { setOn(!st.on); }

export function setOn(on, why) {
    on = !!on;
    if (on === st.on) return;
    const ctx = getCtx();
    st.on = on;
    if (on) {
        st.log = [];
        watchSession(ctx);
        chat.add('sys', '🚗 오토파일럿을 켰어요. 확실한 후원(✓ 거의 확실)만 대신 주고, 애매한 건 대기함에 그대로 둡니다. 새로 고치면 꺼져요.');
        if (ctx) ctx.toast('🚗 오토파일럿 켜짐 — 확실한 후원만 대신 줘요', 'info');
        changed();
        sweep();
    } else {
        changed();
        report(why);
    }
}

/* 방송이 끝나면 저절로 끈다 — 다음 방송에 켜진 채로 넘어가지 않게 */
function watchSession(ctx) {
    if (st.watching || !ctx || !ctx.lm || typeof ctx.lm.on !== 'function') return;
    st.watching = true;
    ctx.lm.on('session', s => { if (st.on && !(s && s.live)) setOn(false, '방송이 끝나서'); });
}

/** 대기함을 훑어 '확실한 것만' 한 건 준다. 대기함이 바뀔 때 · 답이 들어올 때마다 불린다. */
export async function sweep() {
    const ctx = getCtx();
    if (!st.on || st.busy || !ctx) return;
    const slices = ctx.slices || {};
    if (!(slices.session || {}).live) return;
    const names = currentNames(slices);
    for (const it of (slices.pending || []).slice()) {
        if (!isDonation(it) || it.returned) continue;
        if (st.handled.has(it.id)) continue;
        const s = sug.get(it.id);
        if (!s || !s.target || s.tier !== 'auto') continue;      // 확신 부족 · 모름 → 손대지 않는다
        if (!names.includes(s.target)) continue;                 // 지금 판에 없는 이름 → 손대지 않는다

        st.handled.add(it.id);
        st.busy = true;
        const pts = manWon(it.amount);
        let res;
        try {
            // ⚠️ 번호가 아니라 이름으로 — 화면 단추 순서는 바뀔 수 있다
            // via:'ap' — 서버 자동 진행(그림자) 채점이 이것을 '사람 판단' 으로 세지 않게(autopilot.py _on_assign)
            res = await ctx.run('pending.assign', { id: it.id, name: s.target, via: 'ap' }, { quiet: true });
        } finally {
            st.busy = false;
        }
        if (res && res.ok && !res.already) {
            const row = { id: it.id, time: hms(), donor: it.name || '익명', amount: Number(it.amount) || 0,
                          message: it.message || '', target: s.target, pts, why: s.why || '', undone: false };
            st.log.push(row);
            chat.add('sys', `🚗 ${row.donor}님 ${won(row.amount)} → ${row.target} +${pts}점` + (row.why ? `\n근거: ${row.why}` : ''), { notify: true });
            ctx.toast(`🚗 자동으로 줬어요 — ${row.donor} ${won(row.amount)} → ${row.target} +${pts}점`, 'info');
        } else if (res && !res.ok) {
            chat.add('sys', `⚠️ 🚗 ${it.name || '익명'}님 ${won(it.amount)} 을(를) ${s.target}에게 주지 못했어요 — 대기함에 그대로 있어요. (${res.error || '실패'})`, { notify: true });
        }
        paintBanner();
        // 한 건 하고 빠진다 — 서버 답(대기함 갱신)을 받은 뒤 다음 것을 본다
        setTimeout(sweep, 300);
        return;
    }
}

/* 끌 때 — '무슨 일이 있었는지'. 자리를 비운 뒤엔 이게 가장 중요하다 */
function report(why) {
    const ctx = getCtx();
    const head = '🚗 오토파일럿을 껐어요' + (why ? ` (${why})` : '') + '.';
    if (!st.log.length) {
        chat.add('sys', head + ' 자동으로 준 후원은 없어요.', { notify: true });
        if (ctx) ctx.toast(head + ' 자동으로 준 건 없어요', 'info');
        return;
    }
    const lines = st.log.map((r, i) => `${i + 1}. [${r.time}] ${r.donor} ${won(r.amount)} → ${r.target} +${r.pts}점` + (r.message ? `\n    "${r.message.slice(0, 60)}"` : ''));
    chat.add('sys', `${head} 그동안 ${st.log.length}건을 자동으로 줬어요:\n\n${lines.join('\n')}\n\n잘못 간 게 있으면 아래 [되돌리기] 를 누른 뒤 맞는 사람에게 다시 주세요.`,
        { notify: true, apReport: st.log.map(r => r.id) });
    if (ctx) ctx.toast(`${head} ${st.log.length}건을 자동으로 줬어요 — AI 도우미 탭에서 확인하세요`, 'info', 6000);
    openAiTab(true);
}

/** 기록 한 줄(후원 id)을 찾는다 — 끌 때 보여 준 [되돌리기] 단추가 쓴다 */
export function entry(id) { return st.log.find(r => r.id === id) || null; }

/** 잘못 간 자동 배정 되돌리기 — 후원이 대기함으로 돌아온다(맞는 사람에게는 사람이 다시 준다) */
export async function undo(id) {
    const ctx = getCtx();
    const r = entry(id);
    if (!ctx || !r || r.undone) return false;
    const ok = await ctx.confirm({
        title: '이 자동 배정을 되돌릴까요?',
        body: `${r.donor} ${won(r.amount)} → ${r.target} +${r.pts}점\n${r.target}의 점수에서 빼고, 후원은 대기함으로 돌아와요.\n그다음 맞는 사람에게 다시 주세요.`,
        ok: '되돌리기', cancel: '그대로 두기',
    });
    if (!ok) return false;
    const res = await ctx.run('score.undo', { ref: r.id });
    if (!res.ok) return false;
    r.undone = true;
    chat.add('sys', `↩ 되돌렸어요 — ${r.donor} ${won(r.amount)} 후원이 대기함으로 돌아왔어요. 맞는 사람에게 다시 주세요.`);
    ctx.toast(`↩ ${r.donor} ${won(r.amount)} — 대기함으로 돌아왔어요`, 'ok');
    return true;
}

/* ── 머리줄 아래 붉은 띠 ── 켜져 있는 동안 어느 탭에서든 보인다 */
function paintBanner() {
    const hdr = document.getElementById('hdr');
    if (!st.banner && hdr) {
        st.count = h('span', { class: 'ap-count' }, '0건');
        st.banner = h('div', { class: 'ap-banner', role: 'status', hidden: true },
            h('span', { class: 'ap-dot', 'aria-hidden': 'true' }),
            h('span', { class: 'ap-text' }, '🚗 ', h('b', null, '오토파일럿 작동 중'),
                h('span', { class: 'ap-long' }, ' — 확실한 후원만 AI 가 대신 주고 있어요'), ' · 자동으로 준 것 '),
            st.count,
            h('button', { type: 'button', class: 'btn sm ap-off', onclick: () => setOn(false) }, '끄기'));
        hdr.append(st.banner);
    }
    if (!st.banner) return;
    st.banner.hidden = !st.on;
    st.count.textContent = st.log.length + '건';
    document.body.classList.toggle('autopilot-on', st.on);
    const ctx = getCtx();
    if (ctx) ctx.rerender();           // 머리줄 높이가 바뀌었다 — 오른쪽 칸 자리를 다시 잰다
}
