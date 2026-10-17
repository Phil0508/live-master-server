/* 📇 후원자 목록 탭(⚙ 설정 → 기록 → 후원자 목록) — 후원자 한 명 = 카드 한 장(10-17 후원자 장부 5단계).

   서버(읽기만): GET /api/donors/book → {persons:[…], counts, open_suggest} · GET /api/donors/suggest → 열린 제안
   보이는 것
     맨 위   카드 수 · 🔗 열린 제안 수 · [새로 고침] · [다시 세기](donor.rebuild — 처음 채우기와 같은 계산, 여러 번 해도 같다)
     찾기    이름 · 예전 닉네임 · 선수 · 팬클럽 말 · 줄 세우기(최근 온 · 많이 준 · 자주 온)
     거르기  전체 · 💛 전담 · 🧡 주력 · 🌈 여러 멤버 · 🌱 새 얼굴 · 📌 고정 · 🏷️ 팬클럽 · 🔗 묶을까? · 💤 쉬는 중 · 🧪 시험 이름
     🔗 같은 사람일까요?  열린 제안 — [묶기](donor.merge {a, b} — b 를 a 로) · [아니에요](donor.suggest_reject {id})
     목록    줄을 누르면 후원자 카드(donorcard.js) · 100줄씩 [더 보기]
     🏷️ 팬클럽 사전  비공개 조각 donor_clubs — 확정 · 추정. 추정은 '추정' 딱지 + [맞아요] [아니에요] · 선수 고르기(donor.club_set)
   탭 배지(설정 타일 숫자) = 열린 제안 수 — 5분에 한 번만 /api/donors/suggest 를 읽는다(탭이 닫혀 있어도).
   ⚠️ 이름 · 닉네임 · 팬클럽 말은 바깥 글자 — h()(textContent)로만. */
import { h, won, num } from '../../util.js';
import { getJSON } from './api.js';
import { openDonor, changed } from '../../donorcard.js';
import {
    FILTERS, SORT_LABELS, filterPersons, filterCounts, chipText, clubText, relDay, whyText, clubRows, clubGuessCount, suggestList,
} from '../../donorcore.js';

const PAGE = 100;
const BADGE_EVERY_MS = 5 * 60 * 1000;
const RELOAD_AFTER_TAGS_MS = 4000;     // 배정 · 되돌리기로 딱지 조각이 바뀌면 — 열려 있을 때만, 모아서 한 번

/* ── 탭 배지 — 열린 제안 수 ── */
let openSug = 0, badgeAt = 0, badgeBusy = false;
function badgeRefresh(force) {
    if (badgeBusy || (!force && Date.now() - badgeAt < BADGE_EVERY_MS)) return;
    badgeBusy = true;
    badgeAt = Date.now();
    getJSON('/api/donors/suggest').then(j => { openSug = suggestList(j).length; }).catch(() => { /* 서버에 아직 없으면 조용히 */ })
        .finally(() => { badgeBusy = false; });
}
export function donorBadge() {
    badgeRefresh(false);
    return openSug > 0 ? String(openSug) : '';
}

export function mountDonorBook(el, ctx) {
    const q = h('input', { type: 'text', class: 'rc-q db-q', placeholder: '이름 · 예전 닉네임 · 선수로 찾기', autocomplete: 'off', 'aria-label': '후원자 찾기' });
    const sortSel = h('select', { class: 'db-sort', 'aria-label': '줄 세우기' }, SORT_LABELS.map(([k, t]) => h('option', { value: k }, t)));
    const refresh = h('button', { type: 'button', class: 'btn sm', onclick: () => load() }, '새로 고침');
    const rebuild = h('button', { type: 'button', class: 'btn sm', title: '장부 · 기억에서 카드 · 딱지를 처음부터 다시 셉니다 (묶은 것 · 고정 · 메모는 그대로)', onclick: () => doRebuild() }, '다시 세기');
    const sum = h('span', { class: 'muted small db-sum' });
    const sugBadge = h('span', { class: 'dk-badge db-sugn', hidden: true, title: '열린 제안 — 같은 사람일까요?' });
    const chipsEl = h('div', { class: 'rc-chips db-chips', role: 'group', 'aria-label': '딱지로 거르기' });
    const status = h('p', { class: 'rc-status', role: 'status', hidden: true });
    const ol = h('ol', { class: 'db-list' });
    const more = h('button', { type: 'button', class: 'btn sm rc-more', hidden: true, onclick: () => { shown += PAGE; draw(); } });
    const empty = h('p', { class: 'empty', hidden: true });
    const sugBody = h('ul', { class: 'dk-suglist db-suglist' });
    const sugN = h('span', { class: 'dk-badge' }, '0');
    const sugBox = h('details', { class: 'db-fold db-sugs', hidden: true }, h('summary', null, '🔗 같은 사람일까요? ', sugN), sugBody);
    const clubN = h('span', { class: 'muted small' });
    const clubBody = h('div', { class: 'db-clubs' });
    const clubBox = h('details', { class: 'db-fold db-clubbox' }, h('summary', null, '🏷️ 팬클럽 사전 ', clubN), clubBody);

    el.classList.add('db-panel');
    el.dataset.zone = 'donorbook';      // 클릭 기록 구역(설정 화면의 data-zone 과 같은 방식)
    el.append(
        h('div', { class: 'sec-head' },
            h('h2', null, '📇 후원자 목록 ', sugBadge),
            h('span', { class: 'rc-headr' }, sum, refresh, rebuild)),
        h('p', { class: 'muted small db-help' }, '후원자 한 명 = 카드 한 장. 누구 팬인지 딱지가 저절로 붙어요. 같은 사람 같으면 제안만 올라오고, [묶기]를 눌러야 묶여요.'),
        h('div', { class: 'rc-bar db-bar' }, q, sortSel),
        chipsEl, sugBox, status, ol, more, empty, clubBox);

    let persons = [], sugs = [], filter = 'all', shown = PAGE, loading = false, again = false, loaded = false, err = '';
    const chips = {};
    for (const [k, label] of FILTERS) {
        const b = h('button', { type: 'button', class: 'rc-chip', 'data-k': k, 'aria-pressed': k === 'all' ? 'true' : 'false',
            onclick: () => { filter = k; shown = PAGE; draw(); } }, h('span', null, label), h('b', { class: 'n' }, '0'));
        chips[k] = b;
        chipsEl.append(b);
    }
    let qt = 0;
    q.addEventListener('input', () => { clearTimeout(qt); qt = setTimeout(() => { shown = PAGE; draw(); }, 150); });
    sortSel.addEventListener('change', () => { shown = PAGE; draw(); });
    document.addEventListener('lm:donors', () => { if (el.isConnected) load(); });

    async function load() {
        if (loading) { again = true; return; }
        loading = true;
        refresh.disabled = true;
        try {
            const [book, sg] = await Promise.all([
                getJSON('/api/donors/book?all=1'),        // all=1 — 🧪 시험 카드도 받아야 '시험 이름' 거르기에서 다시 풀 수 있다(목록은 거르기가 뺀다)
                getJSON('/api/donors/suggest').catch(() => null),
            ]);
            persons = Array.isArray(book.persons) ? book.persons : [];
            sugs = sg ? suggestList(sg) : [];
            openSug = sg ? sugs.length : Number(book.open_suggest) || 0;
            badgeAt = Date.now();
            err = '';
            loaded = true;
        } catch (e) {
            err = e.message || '목록을 못 불러왔어요';
        }
        loading = false;
        refresh.disabled = false;
        draw();
        if (again) { again = false; load(); }
    }

    async function doRebuild() {
        const ok = await ctx.confirm({ title: '후원자 카드를 다시 셀까요?',
            body: '장부 · 지난 기억에서 카드 · 딱지 · 제안을 다시 계산해요.\n대표님이 묶은 것 · 고정 · 메모 · 시험 표시는 그대로예요. 점수는 안 바뀌어요.',
            ok: '다시 세기', cancel: '그만두기', danger: false });
        if (!ok) return;
        rebuild.disabled = true;
        const res = await ctx.run('donor.rebuild', {});
        rebuild.disabled = false;
        if (res && res.ok) { ctx.toast('📇 후원자 카드를 다시 셌어요', 'ok'); load(); }
    }

    /* 목록 줄 — 키(pid)로 기억해 두고 바뀐 줄만 다시 쓴다 */
    const made = new Map();
    function fillRow(li, p) {
        const c = chipText(p), cl = clubText(p);
        const names = Array.isArray(p.names) ? p.names.map(x => (x && typeof x === 'object') ? x.name : x).filter(Boolean) : [];
        const others = names.filter(n => n !== p.label);
        li.className = 'db-row' + (p.test ? ' test' : '') + (p.dormant ? ' dormant' : '');
        li.replaceChildren(
            h('button', { type: 'button', class: 'db-open', title: (p.label || '') + ' — 후원자 카드 열기', 'data-stat': '후원자 목록 줄', onclick: () => openDonor(ctx, p.pid) },
                h('span', { class: 'db-l1' },
                    h('b', { class: 'db-name' }, p.label || '(이름 없음)'),
                    c ? h('span', { class: c.cls, title: c.title }, c.text) : null,
                    cl ? h('span', { class: cl.cls, title: cl.title }, cl.text) : null,
                    p.big ? h('span', { class: 'dk-tag t-big', title: '누적 후원 상위 10%' }, '⭐ 큰손') : null,
                    p.dormant ? h('span', { class: 'dk-tag t-dormant', title: '마지막 후원이 30일도 넘었어요' }, '💤 쉬는 중') : null,
                    Number(p.sugg) > 0 ? h('span', { class: 'dk-tag t-sugg', title: '같은 사람일 수 있는 카드가 있어요' }, '🔗 ' + num(p.sugg)) : null,
                    p.test ? h('span', { class: 'dk-tag t-test' }, '🧪 시험') : null,
                    !p.test && p.suspect ? h('span', { class: 'dk-tag t-suspect', title: '시험 이름 같아요 — ' + p.suspect + ' (지우지 않아요 · 카드에서 🧪 표시)' }, '❓ 시험 의심') : null),
                h('span', { class: 'db-l2 muted small' },
                    [Number(p.n) ? `${num(p.n)}회` : '', Number(p.total_won) ? won(p.total_won) : '', p.last_at ? relDay(p.last_at) : '',
                        others.length ? `다른 닉네임 ${others.slice(0, 3).join(' · ')}${others.length > 3 ? ` 외 ${others.length - 3}` : ''}` : '']
                        .filter(Boolean).join(' · '))));
    }
    function drawRows(list) {
        const keep = new Set(list.map(p => p.pid));
        for (const [k, r] of made) if (!keep.has(k)) { r.el.remove(); made.delete(k); }
        list.forEach((p, i) => {
            let r = made.get(p.pid);
            if (!r) { r = { el: h('li'), sig: '' }; made.set(p.pid, r); }
            const sig = JSON.stringify(p);
            if (sig !== r.sig) { fillRow(r.el, p); r.sig = sig; }
            if (ol.children[i] !== r.el) ol.insertBefore(r.el, ol.children[i] || null);
        });
    }

    const labelOf = pid => { const p = persons.find(x => x.pid === pid); return p ? p.label : ''; };
    function drawSugs() {
        sugN.textContent = num(sugs.length);
        sugBox.hidden = !sugs.length;
        sugBadge.textContent = '🔗 ' + num(sugs.length);
        sugBadge.hidden = !sugs.length;
        sugBody.replaceChildren(...sugs.slice(0, 50).map(g => {
            const a = g.a || g.pid_a, b = g.b || g.pid_b;
            const al = g.a_label || g.label_a || labelOf(a) || a, bl = g.b_label || g.label_b || labelOf(b) || b;
            const mergeBtn = h('button', { type: 'button', class: 'btn xs pri', onclick: async () => {
                const ok = await ctx.confirm({ title: `'${bl}' 를 '${al}' 에 묶을까요?`,
                    body: `두 카드의 닉네임 · 기록이 '${al}' 한 장으로 모여요.\n나중에 후원자 카드에서 닉네임마다 [떼기]로 다시 나눌 수 있어요.`,
                    ok: '묶기', cancel: '그대로 두기', danger: false });
                if (!ok) return;
                mergeBtn.disabled = true;
                const res = await ctx.run('donor.merge', { a, b });
                mergeBtn.disabled = false;
                if (res && res.ok) { ctx.toast(`🔗 ${bl} → ${al} 묶었어요`, 'ok'); changed(); }
            } }, '묶기');
            const noBtn = h('button', { type: 'button', class: 'btn xs', onclick: async () => {
                noBtn.disabled = true;
                const res = await ctx.run('donor.suggest_reject', { id: g.id });
                noBtn.disabled = false;
                if (res && res.ok) { ctx.toast('다른 사람으로 둘게요', 'info'); changed(); }
            } }, '아니에요');
            return h('li', { class: 'dk-sug' },
                h('div', { class: 'dk-sug-t' },
                    h('span', { class: 'db-pair' },
                        a ? h('button', { type: 'button', class: 'dk-link', 'data-stat': '제안 — 카드 열기', onclick: () => openDonor(ctx, a) }, al) : h('b', null, al),
                        h('span', { class: 'muted', 'aria-hidden': 'true' }, ' ⇄ '),
                        b ? h('button', { type: 'button', class: 'dk-link', 'data-stat': '제안 — 카드 열기', onclick: () => openDonor(ctx, b) }, bl) : h('b', null, bl)),
                    h('span', { class: 'muted small' }, whyText(g.why) + (g.detail ? ' · ' + g.detail : ''))),
                h('div', { class: 'dk-sug-b' }, mergeBtn, noBtn));
        }));
    }

    function draw() {
        status.textContent = err || (!loaded ? '불러오는 중…' : '');
        status.dataset.lv = err ? 'bad' : '';
        status.hidden = !status.textContent;
        const cnt = filterCounts(persons);
        for (const [k, b] of Object.entries(chips)) {
            b.querySelector('.n').textContent = num(cnt[k] || 0);
            b.setAttribute('aria-pressed', k === filter ? 'true' : 'false');
            b.classList.toggle('on', k === filter);
            b.hidden = k !== 'all' && k !== filter && !cnt[k] && ['pin', 'sugg', 'test', 'dormant', 'club', 'suspect'].includes(k);   // 없으면 숨김(고른 것은 남김)
        }
        sum.textContent = loaded ? `카드 ${num(cnt.all)}장` : '';
        const pick = filterPersons(persons, { filter, q: q.value, sort: sortSel.value });
        drawRows(pick.slice(0, shown));
        more.hidden = pick.length <= shown;
        more.textContent = `더 보기 (${num(pick.length - shown)}명 남음)`;
        empty.hidden = !loaded || pick.length > 0;
        empty.textContent = persons.length ? '찾는 후원자가 없어요' : '아직 후원자 카드가 없어요 — [다시 세기]로 장부에서 채울 수 있어요';
        drawSugs();
        drawClubs();
    }

    /* ── 🏷️ 팬클럽 사전 ── */
    let clubSig = '';
    const newWord = h('input', { type: 'text', class: 'db-cw', maxlength: '20', placeholder: '새 팬클럽 말 (예: 밍플단)', autocomplete: 'off', 'aria-label': '새 팬클럽 말' });
    const newSel = h('select', { class: 'db-cp', 'aria-label': '그 팬클럽의 선수' });
    const addBtn = h('button', { type: 'button', class: 'btn xs pri', onclick: () => {
        const w = newWord.value.trim();
        if (!w) { ctx.toast('팬클럽 말을 적어 주세요', 'info'); return; }
        if (!newSel.value) { ctx.toast('어느 선수 팬클럽인지 골라 주세요', 'info'); return; }
        clubSet(w, newSel.value, true, addBtn, `🏷️ ${w} → ${newSel.value} 팬클럽으로 넣었어요`).then(ok => { if (ok) newWord.value = ''; });
    } }, '더하기');
    function playerNames() {
        const P = (ctx.slices || {}).players || {};
        return (P.list || []).map(r => r && r.name).filter(Boolean);
    }
    async function clubSet(word, player, confirmed, btn, msg) {
        if (btn) btn.disabled = true;
        const res = await ctx.run('donor.club_set', { word, player, confirmed });
        if (btn) btn.disabled = false;
        if (res && res.ok) { ctx.toast(msg, 'ok'); changed(); return true; }
        clubSig = '';            // 안 됐다 — 고른 칸을 조각 값으로 되돌린다
        drawClubs();
        return false;
    }
    function drawClubs() {
        const clubs = (ctx.slices || {}).donor_clubs;
        const rows = clubRows(clubs);
        const names = playerNames();
        const sig = JSON.stringify([rows, names]);
        if (sig === clubSig) return;
        clubSig = sig;
        const guess = clubGuessCount(clubs);
        clubN.textContent = rows.length ? `${num(rows.length)}개` + (guess ? ` · 확인 기다림 ${num(guess)}` : '') : '';
        const opts = (cur) => [h('option', { value: '' }, '선수 고르기'), ...[...new Set([...names, ...(cur ? [cur] : [])])].map(n => h('option', { value: n, selected: n === cur }, n))];
        if (document.activeElement !== newSel) newSel.replaceChildren(...opts(''));
        clubBody.replaceChildren(
            h('p', { class: 'muted small' }, '닉네임에 이 말이 들어 있으면 그 선수 팬클럽 딱지(🏷️)가 붙어요. ', h('b', null, '추정'), '은 지난 기록으로 짐작한 것 — 대표님이 [맞아요]를 누르기 전엔 딱지에 안 써요.'),
            rows.length ? h('ul', { class: 'db-clublist' }, rows.map(r => {
                const sel = h('select', { class: 'db-cp', 'aria-label': r.word + ' 선수 고르기' }, opts(r.player));
                sel.addEventListener('change', () => {
                    if (!sel.value) return;
                    clubSet(r.word, sel.value, true, sel, `🏷️ ${r.word} → ${sel.value} 팬클럽으로 정했어요`);
                });
                const yes = !r.confirmed && r.player ? h('button', { type: 'button', class: 'btn xs pri', onclick: () => clubSet(r.word, r.player, true, yes, `🏷️ ${r.word} = ${r.player} 팬클럽 (확정)`) }, '맞아요') : null;
                // [아니에요] · [빼기] = '팬클럽 말 아님' 으로 정한다(confirmed + 선수 없음) — 서버 다시 세기가 같은 짐작을 또 올리지 않는다
                const no = r.no ? null : h('button', { type: 'button', class: 'btn xs', title: r.confirmed ? '이 말을 팬클럽 딱지에서 빼요' : '짐작이 틀렸어요 — 딱지에 안 써요',
                    onclick: async () => {
                        if (r.confirmed) {
                            const ok = await ctx.confirm({ title: `'${r.word}' 를 팬클럽 사전에서 뺄까요?`,
                                body: `지금 '${r.word}' 가 든 닉네임에 ${r.player} 팬클럽 딱지가 붙어 있어요.
빼면 딱지가 사라져요. 나중에 선수를 다시 고르면 돌아와요.`,
                                ok: '빼기', cancel: '그대로 두기', danger: false });
                            if (!ok) return;
                        }
                        clubSet(r.word, null, true, no, `${r.word} — 팬클럽 말이 아니라고 적어 뒀어요`);
                    } }, r.confirmed ? '빼기' : '아니에요');
                const why = !r.confirmed && r.n ? `지난 기억 ${num(r.n)}번 중 ${r.player || '가장 많은 선수'} ${Math.round(r.share * 100)}%` : '';
                return h('li', { class: 'db-club' + (r.no ? ' no' : r.confirmed ? ' ok' : ' guess') },
                    h('b', { class: 'db-cword' }, r.word),
                    h('span', { class: 'db-carrow', 'aria-hidden': 'true' }, '→'),
                    h('span', { class: 'db-cwho' }, r.no ? '팬클럽 아님' : (r.player || '?')),
                    r.no ? h('span', { class: 'dk-tag t-test' }, '안 씀')
                        : r.confirmed ? h('span', { class: 'dk-tag t-ok' }, '확정')
                        : h('span', { class: 'dk-tag t-guess', title: '지난 기록으로 짐작했어요 — 확인 전엔 딱지에 안 써요' + (why ? '
' + why : '') }, '추정'),
                    why ? h('span', { class: 'muted small' }, why) : null,
                    h('span', { class: 'db-cbtns' }, yes, no, sel));
            })) : h('p', { class: 'muted small' }, '아직 사전이 비어 있어요'),
            h('div', { class: 'db-cadd' }, newWord, newSel, addBtn));
    }

    let seenTags, tagTimer = 0;
    return {
        render(slices) {
            if (!loaded && !loading && !err) load();
            // 배정 · 되돌리기로 딱지가 바뀌면 열려 있는 동안만 모아서 다시 받는다
            if (seenTags !== undefined && seenTags !== slices.donor_tags) {
                clearTimeout(tagTimer);
                tagTimer = setTimeout(() => { if (el.isConnected && !el.closest('[hidden]')) load(); }, RELOAD_AFTER_TAGS_MS);
            }
            seenTags = slices.donor_tags;
            drawClubs();
        },
    };
}
