/* 📇 후원자 딱지 · 후원자 카드(옆 서랍) — 대기함 카드 · 장부 줄 · ⚙ 후원자 목록이 같이 쓴다(10-17 후원자 장부 5단계).

   딱지: 이름 옆 작은 알약 — 💛밍밍 전담 · 23회 / 🧡 주력 / 🌈 여러 멤버 / 🌱 새 얼굴 / 📌 고정 / 🏷️ 팬클럽.
         비공개 조각 donor_tags 에서 그 이름(norm)을 찾는다. 조각이 없거나 이름이 없으면(익명) 아무것도 안 그린다.
   카드: 이름을 누르면 오른쪽(폰은 아래)에서 서랍이 나온다 — GET /api/donors/person/{pid}
         멤버별 횟수 막대 · 예전 닉네임들([떼기]) · 마지막으로 온 날 · 최근 후원 20 · 열린 제안 [묶기] [아니에요]
         · [📌 고정](서버가 pin_on:false 면 숨김) · [🧪 시험 이름 표시] · 메모.
   명령(서버 donor_book.py): donor.merge {a, b}(b 를 a 로) · donor.split {name} · donor.suggest_reject {id}
         · donor.pin {pid, player|null} · donor.mark_test {pid, test} · donor.note {pid, note}
   ⚠️ 이름 · 메시지 · 메모는 바깥 글자 — h()(textContent)로만. 메시지는 서버가 가림(mask)을 적용해 준 것만 보인다.
   ⚠️ 무언가 바꾸면 document 에 'lm:donors' 이벤트를 쏜다 — 열린 후원자 목록이 다시 받는다. */
import { h, won, num, clock } from './util.js';
import { getJSON } from './panels/records/api.js';
import { chipsFor, tagFor, chipText, clubText, playerBars, recentTo, relDay, ymd, whyText, pinOn } from './donorcore.js';

/** 이름 옆 딱지 요소들(0~2개) */
export function donorChips(slices, name) {
    return chipsFor((slices || {}).donor_tags, name).map(c => h('span', { class: c.cls, title: c.title }, c.text));
}

/** 이름 — 카드가 있는 사람이면 누르는 단추(후원자 카드를 연다), 아니면 굵은 글자.
 *  cls: 원래 이름 칸 class(pc-name · rc-name) — 자리 · 크기는 원래 css 를 그대로 받는다 */
export function donorName(ctx, name, cls, shown) {
    const text = shown || name || '익명';
    const e = tagFor((ctx.slices || {}).donor_tags, name);
    if (!e || !e.pid) return h('b', { class: cls, title: text }, text);
    return h('button', { type: 'button', class: cls + ' dk-link', title: text + ' — 누르면 후원자 카드', 'data-stat': '후원자 이름',
        onclick: ev => { ev.stopPropagation(); openDonor(ctx, e.pid); } }, text);
}

export function changed() {
    try { document.dispatchEvent(new CustomEvent('lm:donors')); } catch (e) { /* 옛 브라우저 */ }
}

/* ── 서랍 ── 하나만 띄운다(다른 사람을 누르면 내용만 바뀐다) */
let sheet = null;

function players(ctx) {
    const P = (ctx.slices || {}).players || {};
    return (P.list || []).map(r => r && r.name).filter(Boolean);
}

export function closeDonor() {
    if (!sheet) return;
    const s = sheet;
    sheet = null;
    document.removeEventListener('keydown', s.onKey, true);
    s.wrap.remove();
    try { s.prev && s.prev.focus && s.prev.focus(); } catch (e) { /* 무시 */ }
}

export function openDonor(ctx, pid) {
    if (!pid) return;
    if (!sheet) {
        const body = h('div', { class: 'dk-body' });
        const closeBtn = h('button', { type: 'button', class: 'btn xs dk-x', 'aria-label': '후원자 카드 닫기', onclick: () => closeDonor() }, '✕ 닫기');
        const card = h('aside', { class: 'dk-sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': '후원자 카드', 'data-panel': 'donor-card' },
            h('div', { class: 'dk-grab', 'aria-hidden': 'true' }), closeBtn, body);
        const wrap = h('div', { class: 'dk-wrap' }, card);
        wrap.addEventListener('click', e => { if (e.target === wrap) closeDonor(); });
        const onKey = e => {
            // 확인 상자(.modal-wrap)가 떠 있으면 Esc 는 그 상자 몫
            if (e.key === 'Escape' && !document.querySelector('.modal-wrap')) { e.preventDefault(); closeDonor(); }
        };
        document.addEventListener('keydown', onKey, true);
        document.body.append(wrap);
        sheet = { wrap, body, closeBtn, onKey, prev: document.activeElement, pid: '', seq: 0 };
        closeBtn.focus();
    }
    sheet.pid = pid;
    load(ctx);
}

async function load(ctx) {
    const s = sheet;
    if (!s) return;
    const my = ++s.seq;
    if (!s.body.firstChild || s.body.dataset.pid !== s.pid) s.body.replaceChildren(h('p', { class: 'muted dk-loading' }, '불러오는 중…'));
    let j;
    try {
        j = await getJSON('/api/donors/person/' + encodeURIComponent(s.pid));
    } catch (e) {
        if (sheet !== s || my !== s.seq) return;
        s.body.replaceChildren(h('p', { class: 'dk-err', role: 'alert' }, e.message || '후원자 카드를 못 불러왔어요'));
        return;
    }
    if (sheet !== s || my !== s.seq) return;
    s.body.dataset.pid = s.pid;
    paint(ctx, s, j && j.person && typeof j.person === 'object' ? j.person : j);
}

/** 명령 하나 — 되면 카드를 다시 받고 목록에 알린다 */
async function act(ctx, type, data, okMsg, btn) {
    if (btn) btn.disabled = true;
    const res = await ctx.run(type, data);
    if (btn) btn.disabled = false;
    if (res && res.ok) {
        if (okMsg) ctx.toast(okMsg, 'ok');
        changed();
        if (sheet) load(ctx);
    }
    return res;
}

function paint(ctx, s, p) {
    p = p || {};
    const pid = p.pid || s.pid;
    const label = p.label || '(이름 없음)';
    // 카드 길(/api/donors/person)은 선수별 횟수만 준다 — 딱지 글자에 쓸 n · share · 선수는 거기서 센다(주면 그것을 쓴다)
    const bars = playerBars(p.players);
    const sum = bars.reduce((t, b) => t + b.n, 0);
    const e = { tag: p.tag, player: p.pin || p.player || (bars[0] && bars[0].name) || '', n: p.n != null ? p.n : sum,
        share: p.share != null ? p.share : (sum ? bars[0].n / sum : 0), club: p.club };
    const chips = [chipText(e), clubText(e)].filter(Boolean).map(c => h('span', { class: c.cls, title: c.title }, c.text));
    const names = Array.isArray(p.names) ? p.names : [];
    const recent = Array.isArray(p.recent) ? p.recent : [];
    const lastAt = Math.max(0, ...names.map(x => Number(x && x.last_at) || 0), ...recent.map(r => Number(r && r.at) || 0));

    const head = h('header', { class: 'dk-head' },
        h('h2', { class: 'dk-label' }, label),
        h('div', { class: 'dk-chips' }, chips, p.test ? h('span', { class: 'dk-tag t-test' }, '🧪 시험 이름')
            : p.suspect ? h('span', { class: 'dk-tag t-suspect', title: String(p.suspect) }, '❓ 시험 의심 · ' + String(p.suspect)) : null),
        h('p', { class: 'dk-last muted small' }, lastAt ? `마지막으로 온 날 · ${relDay(lastAt)} (${ymd(lastAt)})` : '언제 왔는지 기록이 없어요'));

    // 멤버별 횟수 막대
    const barSec = h('section', { class: 'dk-sec dk-bars' },
        h('h3', null, '멤버별 횟수'),
        bars.length ? h('ol', { class: 'dk-barlist' }, bars.map(b => h('li', { class: 'dk-bar' },
            h('span', { class: 'dk-bar-n' }, b.name),
            h('span', { class: 'dk-bar-track', 'aria-hidden': 'true' }, h('span', { class: 'dk-bar-fill', style: `width:${b.w}%` })),
            h('span', { class: 'dk-bar-v' }, `${num(b.n)}회 · ${b.pct}%`))))
            : h('p', { class: 'muted small' }, '아직 누구에게 갔는지 기억이 없어요'));

    // 열린 제안 — [묶기](그 카드를 이 카드로) · [아니에요]
    const sugg = Array.isArray(p.suggest) ? p.suggest : [];
    const sugSec = sugg.length ? h('section', { class: 'dk-sec dk-sugs' },
        h('h3', null, '같은 사람일까요? ', h('span', { class: 'dk-badge' }, String(sugg.length))),
        h('ul', { class: 'dk-suglist' }, sugg.map(g => {
            const mergeBtn = h('button', { type: 'button', class: 'btn xs pri', onclick: async () => {
                const ok = await ctx.confirm({ title: `'${g.other_label || '그 카드'}' 를 '${label}' 에 묶을까요?`,
                    body: `두 카드의 닉네임 · 기록이 '${label}' 한 장으로 모여요.\n나중에 닉네임마다 [떼기]로 다시 나눌 수 있어요.`,
                    ok: '묶기', cancel: '그대로 두기', danger: false });
                if (ok) act(ctx, 'donor.merge', { a: pid, b: g.other_pid }, `🔗 ${g.other_label || '그 카드'} → ${label} 묶었어요`, mergeBtn);
            } }, '묶기');
            const noBtn = h('button', { type: 'button', class: 'btn xs', onclick: () => act(ctx, 'donor.suggest_reject', { id: g.id }, '다른 사람으로 둘게요', noBtn) }, '아니에요');
            return h('li', { class: 'dk-sug' },
                h('div', { class: 'dk-sug-t' },
                    g.other_pid ? h('button', { type: 'button', class: 'dk-link dk-sug-name', 'data-stat': '제안 — 다른 카드 열기', onclick: () => openDonor(ctx, g.other_pid) }, g.other_label || g.other_pid)
                        : h('b', null, g.other_label || '?'),
                    h('span', { class: 'muted small' }, whyText(g.why) + (g.detail ? ' · ' + g.detail : ''))),
                h('div', { class: 'dk-sug-b' }, mergeBtn, noBtn));
        }))) : null;

    // 예전 닉네임들 — 두 개 이상이면 [떼기](그 닉네임을 새 카드로)
    const nameSec = h('section', { class: 'dk-sec dk-names' },
        h('h3', null, '쓴 닉네임 ', h('span', { class: 'muted small' }, `${names.length}개`)),
        names.length ? h('ul', { class: 'dk-namelist' }, names.map(x => {
            const nm = String((x && x.name) || '');
            const cut = names.length > 1 ? h('button', { type: 'button', class: 'btn xs', title: '이 닉네임을 다른 사람으로 — 새 카드로 떼어 내요', onclick: async () => {
                const ok = await ctx.confirm({ title: `'${nm}' 를 떼어 낼까요?`, body: '이 닉네임과 그 기록이 새 카드 한 장으로 나가요.', ok: '떼기', cancel: '그대로 두기', danger: false });
                if (ok) act(ctx, 'donor.split', { name: nm }, `✂️ ${nm} 를 새 카드로 뗐어요`, cut);
            } }, '떼기') : null;
            return h('li', { class: 'dk-nm' },
                h('b', null, nm),
                h('span', { class: 'muted small' }, [x && x.n ? `${num(x.n)}번` : '', x && x.first_at ? ymd(x.first_at) + ' ~ ' + ymd(x.last_at || x.first_at) : ''].filter(Boolean).join(' · ')),
                cut);
        })) : h('p', { class: 'muted small' }, '닉네임 기록이 없어요'));

    // 최근 후원 20 — 메시지는 서버가 가린 것 그대로
    const recSec = h('section', { class: 'dk-sec dk-recent' },
        h('h3', null, '최근 후원 ', h('span', { class: 'muted small' }, recent.length ? `${Math.min(20, recent.length)}건` : '')),
        recent.length ? h('ol', { class: 'dk-reclist' }, recent.slice(0, 20).map(r => {
            const to = recentTo(r);
            return h('li', { class: 'dk-rec' },
                h('div', { class: 'dk-rec-l' },
                    h('span', { class: 'dk-rec-t muted small' }, ymd(r.at) + ' ' + clock(r.at)),
                    Number(r.amount) ? h('b', { class: 'dk-rec-a' }, won(r.amount)) : null,
                    to ? h('span', { class: 'dk-rec-to' }, '→ ' + to) : h('span', { class: 'muted small' }, '받은 사람 기록 없음')),
                r.message ? h('p', { class: 'dk-rec-m' }, '“' + String(r.message) + '”') : null);
        })) : h('p', { class: 'muted small' }, '장부에 남은 후원이 없어요'));

    // 관리 — 📌 고정 · 🧪 시험 이름 · 메모
    const mng = [];
    if (pinOn(p)) {
        const sel = h('select', { class: 'dk-pin-sel', 'aria-label': '고정할 선수' },
            h('option', { value: '' }, '고정 안 함'),
            [...new Set([...players(ctx), ...(p.pin ? [p.pin] : [])])].map(n => h('option', { value: n, selected: n === p.pin }, n)));
        const pinBtn = h('button', { type: 'button', class: 'btn xs', onclick: () => {
            const v = sel.value || null;
            if ((v || null) === (p.pin || null)) { ctx.toast('바뀐 게 없어요', 'info'); return; }
            act(ctx, 'donor.pin', { pid, player: v }, v ? `📌 ${label} → ${v} 고정` : `📌 ${label} 고정을 풀었어요`, pinBtn);
        } }, '📌 고정');
        mng.push(h('div', { class: 'dk-row' }, h('span', { class: 'dk-k' }, '고정'), sel, pinBtn,
            h('span', { class: 'muted small' }, p.pin ? `지금 ${p.pin}` : '기억과 상관없이 이 선수 팬으로')));
    }
    const testBtn = h('button', { type: 'button', class: 'btn xs' + (p.test ? ' on' : ''), 'aria-pressed': p.test ? 'true' : 'false',
        onclick: () => act(ctx, 'donor.mark_test', { pid, test: !p.test }, p.test ? '시험 이름 표시를 뺐어요' : '🧪 시험 이름으로 표시했어요 — 목록 · 딱지에서 빠져요', testBtn) },
        p.test ? '🧪 시험 이름 표시 빼기' : '🧪 시험 이름 표시');
    mng.push(h('div', { class: 'dk-row' }, h('span', { class: 'dk-k' }, '시험'), testBtn));
    const note = h('textarea', { class: 'dk-note', rows: '3', maxlength: '500', placeholder: '이 후원자에 대한 메모 (조종실에서만 보여요)', 'aria-label': '메모' });
    note.value = String(p.note || '');
    const saveBtn = h('button', { type: 'button', class: 'btn xs pri', onclick: () => {
        if (note.value === String(p.note || '')) { ctx.toast('바뀐 게 없어요', 'info'); return; }
        act(ctx, 'donor.note', { pid, note: note.value.slice(0, 500) }, '메모를 저장했어요', saveBtn);
    } }, '메모 저장');
    mng.push(h('div', { class: 'dk-notebox' }, note, h('div', { class: 'dk-note-b' }, saveBtn)));
    const mngSec = h('section', { class: 'dk-sec dk-mng' }, h('h3', null, '관리'), mng);

    s.body.replaceChildren(head, sugSec, barSec, nameSec, recSec, mngSec);
}

