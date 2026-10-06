/* ⚔️ 대결 — 대결자(팀) 2~4 · 타이머 · 후원판 점수 연동 · 손 점수 · 기록 되돌리기.

   [방송에 띄우기] match.open(무대에 올림) · [방송 중 · 내리기] match.close(끝내기 — 시계를 얼리고 무대에서 내림)
   타이틀 match.title · 이글이글 match.fire{on} · 대결자 추가 match.add_team · 연동 match.link{mode}
   타이머: [시작] match.start · [정지] match.pause · ±시간 match.add_time{sec} · 분/초 match.set_time{min, sec} ·
           [리셋] match.reset_time · [지금 끝내기] match.end
   대결자 줄: 이름 match.rename_team{id, to} · [+점수] Enter → match.score{id, delta} · 🗑 match.remove_team{id} ·
             팀원 칩 match.member{id, member}
   기록: 손 점수 → match.undo{ref} · 후원판에서 따라온 점수 → score.undo{ref}(후원판 점수까지 같이 돌아간다)
   ⚠️ 줄은 대결자 id 로 찾는다 — 이름이 바뀌어도 칸(입력 중인 +점수)이 그대로 남는다. */
import { h, num, signed, clock } from '../../util.js';
import { head, seg, memo, syncVal, serverNow, mmss, okToTake, numInput, toInt, shown, onEnter, rosterNames, STAGE_LABEL } from './common.js';

const LINK_HINT = {
    off: '켜면 아래에서 고른 사람이 후원판에서 받은 점수가 대결 점수로도 같이 올라가요',
    solo: '개인전 — 대결자마다 점수판 한 명을 고르면, 그 사람 후원판 점수가 대결 점수로도 올라가요',
    team: '팀전 — 팀마다 팀원을 고르면, 팀원들의 후원판 점수가 그 팀 점수로 같이 올라가요',
};
const ADD_TIMES = [[10, '+10초'], [30, '+30초'], [60, '+1분'], [180, '+3분'], [300, '+5분'], [-60, '−1분']];

export function mountMatch(el, ctx) {
    const paint = memo();
    let m = {}, slices = {};

    const hd = head('⚔️ 대결', async on => {
        if (on) {
            if (!(await okToTake(ctx, 'match', '대결'))) return;
            const res = await ctx.run('match.open', {});
            if (res.ok) ctx.toast('대결을 방송에 띄웠어요', 'ok');
        } else {
            const res = await ctx.run('match.close', {});
            if (res.ok) ctx.toast('대결을 끝내고 방송에서 내렸어요 (점수는 그대로)', 'info');
        }
    });
    const closeLink = h('button', { type: 'button', class: 'btn sm ghost-danger', hidden: true, onclick: async () => {
        const res = await ctx.run('match.close', {});
        if (res.ok) ctx.toast('대결을 닫았어요', 'info');
    } }, '대결 닫기');
    hd.el.insertBefore(closeLink, hd.el.querySelector('.gm-sp'));

    /* 꾸미기 줄 */
    const title = h('input', { type: 'text', class: 'gm-in grow', maxlength: 40, placeholder: '대결 타이틀 (선택) — Enter', autocomplete: 'off', 'aria-label': '대결 타이틀' });
    const sendTitle = async () => {
        const v = title.value.trim();
        if (v === String(m.title || '')) return;
        const res = await ctx.run('match.title', { title: v });
        if (res.ok) { title.dataset.sv = v; ctx.toast(v ? `타이틀: ${v}` : '타이틀을 지웠어요', 'ok'); }
    };
    onEnter(title, () => title.blur());          // 칸을 떠나면 change 가 한 번 보낸다(두 번 안 가게)
    title.addEventListener('change', sendTitle);
    const fire = h('button', { type: 'button', class: 'btn gm-fire', 'aria-pressed': 'false', onclick: async () => {
        const on = !m.fire;
        const res = await ctx.run('match.fire', { on });
        if (res.ok) ctx.toast(on ? '🔥 이글이글 효과를 켰어요' : '이글이글 효과를 껐어요', 'info');
    } }, '🔥 이글이글');
    const addBtn = h('button', { type: 'button', class: 'btn', onclick: async () => {
        const res = await ctx.run('match.add_team', {});
        if (res.ok) ctx.toast('대결자를 더했어요 — 이름을 고쳐 주세요', 'ok');
    } }, '＋ 대결자 추가');

    const linkSeg = seg([['off', '끔'], ['solo', '개인전'], ['team', '팀전']], async v => {
        if (v === m.link) return;
        const res = await ctx.run('match.link', { mode: v });
        if (res.ok) ctx.toast(v === 'off' ? '후원판 연동을 껐어요' : v === 'solo' ? '개인전 연동 — 대결자마다 점수판 사람을 골라 주세요' : '팀전 연동 — 팀마다 팀원을 골라 주세요', 'ok');
    }, '후원판 점수 연동');
    const linkHint = h('span', { class: 'gm-info' });

    /* 타이머 */
    const clk = h('div', { class: 'gm-clock', 'aria-live': 'off' }, '03:00');
    const heldTag = h('span', { class: 'tag warn', hidden: true }, '시그 재생 중 — 끝나면 이어서 돌아요');
    const goBtn = h('button', { type: 'button', class: 'btn big pri gm-go', onclick: async () => {
        const t = m.timer || {};
        const res = await ctx.run(t.running ? 'match.pause' : 'match.start', {});
        if (res.ok && !res.already) ctx.toast(t.running ? '타이머를 멈췄어요' : '타이머 시작!', 'info');
    } }, '▶ 시작');
    const resetT = h('button', { type: 'button', class: 'btn big ghost-danger', onclick: async () => {
        const res = await ctx.run('match.reset_time', {});
        if (res.ok) ctx.toast('타이머를 3분으로 되돌렸어요', 'info');
    } }, '리셋');
    const endBtn = h('button', { type: 'button', class: 'btn ghost-danger', onclick: async () => {
        const ok = await ctx.confirm({ title: '대결을 지금 끝낼까요?', body: '남은 시간이 있어도 0 으로 만들고 방송판에 \'시간종료\' 를 띄웁니다.', ok: '지금 끝내기', cancel: '계속' });
        if (!ok) return;
        const res = await ctx.run('match.end', {});
        if (res.ok) ctx.toast('대결 시간을 끝냈어요', 'info');
    } }, '지금 끝내기');
    const addRow = h('div', { class: 'gm-chiprow' }, ADD_TIMES.map(([sec, label]) => h('button', {
        type: 'button', class: 'btn sm' + (sec < 0 ? ' ghost-danger' : ''), onclick: async () => {
            const res = await ctx.run('match.add_time', { sec });
            if (res.ok) ctx.toast(`타이머 ${label}`, 'info');
        },
    }, label)));
    const inMin = numInput({ placeholder: '3', 'aria-label': '분', maxlength: 3, class: 'gm-in num w64' });
    const inSec = numInput({ placeholder: '00', 'aria-label': '초', maxlength: 3, class: 'gm-in num w64' });
    const setTime = async () => {
        const mi = inMin.value.trim() === '' ? 0 : toInt(inMin.value);
        const se = inSec.value.trim() === '' ? 0 : toInt(inSec.value);
        if (mi === null || se === null || mi < 0 || se < 0) { ctx.toast('분 · 초는 0 이상의 숫자로 적어 주세요', 'err'); return; }
        const res = await ctx.run('match.set_time', { min: mi, sec: se });
        if (res.ok) {
            ctx.toast(`타이머를 ${mi}분 ${se}초로 맞췄어요`, 'ok');
            inMin.value = ''; inSec.value = '';
            inMin.blur(); inSec.blur();
        }
    };
    onEnter(inMin, setTime);
    onEnter(inSec, setTime);
    inMin.addEventListener('keydown', e => {
        if (e.key === 'ArrowRight' && inMin.selectionStart === inMin.value.length) { e.preventDefault(); inSec.focus(); }
    });
    const setForm = h('div', { class: 'gm-row gm-settime' },
        h('span', { class: 'gm-lbl' }, '시간 넣기'), inMin, h('span', null, '분'), inSec, h('span', null, '초'),
        h('button', { type: 'button', class: 'btn sm pri', onclick: setTime }, '맞추기 (Enter)'));

    /* 대결자 표 */
    const teamsBox = h('div', { class: 'gm-teams' });
    const teamsEmpty = h('p', { class: 'empty' }, '대결자가 없어요 — [＋ 대결자 추가] 를 눌러 주세요');
    const rows = new Map();
    const resetBtn = h('button', { type: 'button', class: 'btn sm ghost-danger', onclick: async () => {
        const ok = await ctx.confirm({ title: '새 판으로 할까요?', body: '대결 점수를 전부 0 으로 하고 대결 기록을 비웁니다.\n이름 · 팀원 · 시계는 그대로예요.', ok: '점수 0 으로', cancel: '그대로 두기' });
        if (!ok) return;
        const res = await ctx.run('match.reset', {});
        if (res.ok) ctx.toast('대결 점수를 0 으로 했어요', 'info');
    } }, '새 판 · 점수 0');

    /* 기록 */
    const logBox = h('ol', { class: 'gm-log' });
    const logEmpty = h('p', { class: 'empty' }, '아직 대결 점수 기록이 없어요');

    el.append(h('div', { class: 'gm' },
        hd.el,
        h('div', { class: 'gm-row' }, title, fire, addBtn),
        h('div', { class: 'gm-row' }, h('span', { class: 'gm-lbl' }, '후원판 점수 연동'), linkSeg.el, linkHint),
        h('section', { class: 'gm-box' },
            h('div', { class: 'gm-sub' }, h('b', null, '⏱️ 타이머'), heldTag),
            h('div', { class: 'gm-row gm-timer' }, clk, goBtn, resetT, endBtn),
            addRow, setForm),
        h('section', { class: 'gm-box' },
            h('div', { class: 'gm-sub' }, h('b', null, '대결자'), h('span', { class: 'gm-sp' }), resetBtn),
            teamsBox, teamsEmpty),
        h('section', { class: 'gm-box' },
            h('div', { class: 'gm-sub' }, h('b', null, '대결 기록'), h('span', { class: 'gm-info' }, '되돌리면 그 점수가 빠져요')),
            logBox, logEmpty)));

    function makeRow(t) {
        const name = h('input', { type: 'text', class: 'gm-in', maxlength: 20, autocomplete: 'off', 'aria-label': '대결자 이름' });
        const rename = async () => {
            const v = name.value.trim();
            const cur = rows.get(t.id) && rows.get(t.id).t;
            if (!cur || v === cur.name) return;
            if (!v) { name.value = cur.name; return; }
            const res = await ctx.run('match.rename_team', { id: t.id, to: v });
            if (res.ok) ctx.toast(`대결자 이름: ${v}`, 'ok');
            else { name.dataset.sv = ''; ctx.rerender(); }
        };
        onEnter(name, () => name.blur());
        name.addEventListener('change', rename);
        const score = h('b', { class: 'gm-score' }, '0');
        const add = numInput({ placeholder: '+점수', enterkeyhint: 'done', class: 'gm-in num w96', 'aria-label': '대결 점수 더하기' });
        onEnter(add, async () => {
            const d = toInt(add.value);
            if (d === null || d === 0) { add.classList.add('bad'); setTimeout(() => add.classList.remove('bad'), 600); ctx.toast('더하거나 뺄 점수를 정수로 적어 주세요 (예: 5, -3)', 'err'); return; }
            add.disabled = true;
            const res = await ctx.run('match.score', { id: t.id, delta: d });
            add.disabled = false;
            if (res.ok) { add.value = ''; ctx.toast(`[대결] ${rows.get(t.id).t.name} ${signed(d)}점`, 'ok'); }
            add.focus();
        });
        const del = h('button', { type: 'button', class: 'icon-btn gm-del', title: '이 대결자 빼기', 'aria-label': '이 대결자 빼기', onclick: async () => {
            const cur = rows.get(t.id).t;
            const ok = await ctx.confirm({ title: `'${cur.name}' 을(를) 뺄까요?`, body: `점수 ${num(cur.score)}점이 사라집니다.`, ok: '빼기', cancel: '그대로 두기' });
            if (!ok) return;
            const res = await ctx.run('match.remove_team', { id: t.id });
            if (res.ok) ctx.toast(`'${cur.name}' 을(를) 뺐어요`, 'info');
        } }, '🗑');
        const members = h('div', { class: 'gm-members' });
        const row = h('div', { class: 'gm-team', 'data-id': t.id },
            h('div', { class: 'gm-team-main' }, h('span', { class: 'gm-dot' }), name, score, add, del), members);
        return { el: row, name, score, members, t, sig: '' };
    }

    function paintMembers(r, t, roster, link) {
        const mine = t.members || [];
        const kids = [];
        if (link === 'off') { r.members.hidden = true; r.members.replaceChildren(); return; }
        r.members.hidden = false;
        kids.push(h('span', { class: 'gm-info' }, link === 'solo' ? '점수판의 누구?' : '팀원'));
        if (!roster.length) kids.push(h('span', { class: 'gm-info' }, '점수판에 사람이 없어요'));
        roster.forEach(nm => {
            const on = mine.includes(nm);
            kids.push(h('button', { type: 'button', class: 'gm-chip' + (on ? ' on' : ''), 'aria-pressed': String(on), onclick: async () => {
                const res = await ctx.run('match.member', { id: t.id, member: nm });
                if (res.ok) ctx.toast(on ? `${nm} 을(를) 뺐어요` : `${nm} → ${rows.get(t.id).t.name}`, 'info');
            } }, on ? '✓ ' : '', nm));
        });
        const orphans = mine.filter(x => !roster.includes(x));
        if (orphans.length) kids.push(h('div', { class: 'gm-warn' }, `⚠️ 점수판에 없는 팀원: ${orphans.join(', ')} — 다시 골라 주세요 (합산이 멈춰 있어요)`));
        if (link === 'solo' && !mine.length && roster.length) kids.push(h('div', { class: 'gm-warn soft' }, '한 명을 골라야 점수가 따라 올라가요'));
        r.members.replaceChildren(...kids);
    }

    function paintTeams() {
        const teams = m.teams || [];
        const roster = rosterNames(slices);
        const lead = new Set(m.lead || []);
        teamsEmpty.hidden = teams.length > 0;
        const ids = new Set(teams.map(t => t.id));
        for (const [id, r] of rows) if (!ids.has(id)) { r.el.remove(); rows.delete(id); }
        teams.forEach((t, i) => {
            let r = rows.get(t.id);
            if (!r) { r = makeRow(t); rows.set(t.id, r); }
            r.t = t;
            syncVal(r.name, t.name);
            r.score.textContent = num(t.score);
            r.el.classList.toggle('lead', lead.size === 1 && lead.has(t.id));
            r.el.style.setProperty('--tc', ['#ff6b6b', '#5aa9ff', '#3ddc84', '#ffb36b', '#c77dff', '#ffd166'][i % 6]);
            const sig = JSON.stringify([t.members, roster, m.link]);
            if (sig !== r.sig) { paintMembers(r, t, roster, m.link || 'off'); r.sig = sig; }
            if (teamsBox.children[i] !== r.el) teamsBox.insertBefore(r.el, teamsBox.children[i] || null);
        });
    }

    function paintLogs(logs) {
        const list = (logs || []).slice(0, 12);
        logEmpty.hidden = list.length > 0;
        const seenRef = new Set();
        logBox.replaceChildren(...list.map(r => {
            const isLink = r.kind === 'link';
            const first = !seenRef.has(r.ref);
            seenRef.add(r.ref);
            const text = isLink ? `${r.member || '?'} ${signed(r.val)} → ${r.name}` : `${r.name} ${signed(r.val)}점`;
            return h('li', { class: 'gm-logrow' + (isLink ? ' link' : '') },
                h('span', { class: 'gm-lt' }, clock(r.at, true)),
                h('span', { class: 'gm-lx' }, text, h('small', null, ` (${num(r.before)} → ${num(r.after)})`)),
                isLink ? h('span', { class: 'tag plain' }, '후원판') : null,
                first ? h('button', { type: 'button', class: 'btn sm', onclick: () => undo(r) }, '되돌리기') : null);
        }));
    }

    async function undo(r) {
        if (r.kind === 'link') {
            const ok = await ctx.confirm({ title: '후원판 점수째 되돌릴까요?', body: `${r.member || ''} ${signed(r.val)} 은(는) 후원판(점수판)에서 따라온 점수예요.\n되돌리면 점수판 점수와 대결 점수가 같이 빠집니다.`,
                ok: '같이 되돌리기', cancel: '그대로 두기' });
            if (!ok) return;
            const res = await ctx.run('score.undo', { ref: r.ref });
            if (res.ok) ctx.toast('후원판 점수와 대결 점수를 되돌렸어요', 'info');
            return;
        }
        const res = await ctx.run('match.undo', { ref: r.ref });
        if (res.ok) ctx.toast(`되돌렸어요 — ${r.name} ${signed(-r.val)}점`, 'info');
    }

    function paintClock() {
        const t = m.timer || {};
        const left = t.running ? Math.max(0, Number(t.end_ms || 0) - serverNow()) : Number(t.left_ms || 0);
        const sec = Math.ceil(left / 1000);
        const txt = sec <= 0 ? '시간종료' : mmss(sec);
        if (clk.textContent !== txt) clk.textContent = txt;
        clk.classList.toggle('run', !!t.running);
        clk.classList.toggle('hot', !!t.running && sec > 0 && sec <= 10);
        clk.classList.toggle('over', sec <= 0);
    }
    setInterval(() => { if (shown(clk) && (m.timer || {}).running) paintClock(); }, 250);

    return {
        render(s) {
            slices = s;
            m = s.match || {};
            const stage = (s.show || {}).stage;
            const onStage = !!m.active && stage === 'match';
            hd.setAir(onStage);
            closeLink.hidden = !(m.active && stage !== 'match');
            hd.setPill(m.active ? (onStage ? '진행 중' : `열림 · 지금 무대: ${STAGE_LABEL[stage] || '비어 있음'}`) : '꺼짐', m.active ? (onStage ? 'live' : 'warn') : '');
            syncVal(title, m.title || '');
            fire.classList.toggle('on', !!m.fire);
            fire.setAttribute('aria-pressed', String(!!m.fire));
            addBtn.disabled = (m.teams || []).length >= 4;
            addBtn.title = addBtn.disabled ? '대결자는 4명(팀)까지예요' : '';
            linkSeg.set(m.link || 'off');
            linkHint.textContent = LINK_HINT[m.link || 'off'];
            const t = m.timer || {};
            goBtn.textContent = t.running ? '⏸ 정지' : '▶ 시작';
            goBtn.classList.toggle('pri', !t.running);
            goBtn.classList.toggle('danger', !!t.running);
            heldTag.hidden = !t.held;
            paintClock();
            paintTeams();          // 줄마다 바뀐 것만 고친다(입력 중인 칸은 그대로)
            paint('logs', s.match_logs || [], () => paintLogs(s.match_logs));
        },
    };
}
