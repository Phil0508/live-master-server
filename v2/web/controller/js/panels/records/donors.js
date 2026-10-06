/* 👑 후원자 탭 — 이번 방송 후원 순위 · 특별 후원자 등급 · 순위에서 빼기 / 다시 넣기.

   조각(읽기만): tallies.donors {정규화 이름: {name, total, count}} · tallies.vip {정규화 이름: {rank, grade, color, badge}}
                 donor_rules.excluded [정규화 이름] (비공개 — 조종실만 받는다)
   명령: donor.exclude {name} · donor.include {name} · vip.set {name, grade} · vip.remove {name}
     직접 준 등급(donor_rules.manual) 은 순위(1~10위)에 못 든 사람에게만 붙는다(서버) — 방송을 넘어 남는다.
     뺀 이름은 후원 순위 · 한 방 최고 · 소액 띠에서 빠진다(서버). 장부(후원 기록) · 점수는 그대로다.
     다시 넣으면 서버가 이번 방송 장부에서 다시 센다.
   순위: 동점은 같은 순위, 다음은 건너뛴다(1 · 1 · 3) — 서버 donors.recompute_vip 과 같다.
   ⚠️ 집계 · 뺀 이름 조각이 바뀔 때만 다시 그린다. 줄은 한 번 만들고 바뀐 줄만 고친다. */
import { h, won, num } from '../../util.js';

const PAGE = 50;

export function mountDonors(el, ctx) {
    const summary = h('span', { class: 'muted small' });
    const q = h('input', { type: 'text', class: 'rc-q', placeholder: '후원자 이름으로 찾기', autocomplete: 'off', 'aria-label': '후원자 이름으로 찾기' });
    const ol = h('ol', { class: 'dn-list' });
    const more = h('button', { type: 'button', class: 'btn sm rc-more', hidden: true });
    const empty = h('p', { class: 'empty', hidden: true });
    const exHead = h('h3', { class: 'sub-h' }, '순위에서 뺀 이름 ', h('small', null, '(이번 방송 장부에서 다시 세어 넣어요)'));
    const exList = h('ul', { class: 'dn-ex' });
    const exBox = h('div', { class: 'dn-exbox', hidden: true }, exHead, exList);
    // 👑 직접 준 등급 — 순위에 못 든 단골에게 붙이는 예외용(옛 '특별 후원자 등록')
    const GRADES = [['VVIP', '🏆 VVIP'], ['VIP', '👑 VIP'], ['DIAMOND', '💎 DIAMOND'], ['BRONZE', '🥉 BRONZE']];
    const mvName = h('input', { type: 'text', class: 'rc-q', placeholder: '후원자 이름', autocomplete: 'off', maxlength: 30, 'aria-label': '등급 줄 후원자 이름' });
    const mvGrade = h('select', { class: 'rc-q', 'aria-label': '등급' }, ...GRADES.map(([v, l]) => h('option', { value: v }, l)));
    const mvAdd = h('button', { type: 'button', class: 'btn sm' }, '등급 주기');
    const mvList = h('ul', { class: 'dn-ex' });
    const mvBox = h('div', { class: 'dn-exbox' },
        h('h3', { class: 'sub-h' }, '직접 준 등급 ', h('small', null, '(1~10위 밖의 사람에게만 붙어요 · 방송이 끝나도 남아요)')),
        h('div', { class: 'rc-bar' }, mvName, mvGrade, mvAdd), mvList);
    async function mvSet() {
        const name = mvName.value.trim();
        if (!name) { ctx.toast('후원자 이름을 적어 주세요', 'err'); mvName.focus(); return; }
        mvAdd.disabled = true;
        const res = await ctx.run('vip.set', { name, grade: mvGrade.value });
        mvAdd.disabled = false;
        if (res.ok) { ctx.toast(`'${name}' 님에게 ${mvGrade.value} 등급을 줬어요`, 'ok'); mvName.value = ''; }
    }
    mvAdd.addEventListener('click', mvSet);
    mvName.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) mvSet(); });
    let lastManual = null;
    el.append(
        h('div', { class: 'sec-head' }, h('h2', null, '👑 후원자 순위'), summary),
        h('p', { class: 'muted small dn-lead' }, '이번 방송 후원 합계 순서예요. [순위에서 빼기] 를 누르면 방송판의 후원 순위 · 한 방 최고 · 소액 띠에서 빠집니다(장부 · 점수는 그대로).'),
        h('div', { class: 'rc-bar' }, q),
        ol, more, empty, exBox, mvBox);

    let shown = PAGE, lastT = null, lastR = null, busy = new Set();
    const rows = new Map();
    const exRows = new Map();
    let qt = 0;
    q.addEventListener('input', () => { clearTimeout(qt); qt = setTimeout(() => { shown = PAGE; draw(true); }, 150); });
    more.addEventListener('click', () => { shown += PAGE; draw(true); });

    async function exclude(d) {
        if (busy.has(d.key)) return;
        const ok = await ctx.confirm({
            title: `'${d.name}' 님을 순위에서 뺄까요?`,
            body: '방송판의 후원 순위 · 한 방 최고 · 소액 띠에서 빠집니다.\n후원 기록(장부)과 점수는 그대로예요. 아래 [다시 넣기] 로 되돌릴 수 있어요.',
            ok: '순위에서 빼기', cancel: '그대로 두기',
        });
        if (!ok) return;
        busy.add(d.key);
        draw(true);
        const res = await ctx.run('donor.exclude', { name: d.name });
        busy.delete(d.key);
        draw(true);
        if (res.ok) ctx.toast(`'${d.name}' 님을 순위에서 뺐어요`, 'info');
    }

    async function include(key) {
        if (busy.has('ex:' + key)) return;
        busy.add('ex:' + key);
        draw(true);
        const res = await ctx.run('donor.include', { name: key });
        busy.delete('ex:' + key);
        draw(true);
        if (res.ok) ctx.toast(`'${key}' 님을 순위에 다시 넣었어요`, 'ok');
    }

    function fill(li, d) {
        li.className = 'dn-row' + (d.vip ? ' vip' : '') + (d.rank === 1 ? ' first' : '');
        const grade = d.vip ? h('span', { class: 'dn-grade', style: `--g:${/^#[0-9a-f]{3,8}$/i.test(d.vip.color || '') ? d.vip.color : '#bcb0a6'}` },
            (d.vip.badge || '') + ' ' + d.vip.grade) : null;
        li.replaceChildren(
            h('span', { class: 'dn-rank' }, String(d.rank)),
            h('div', { class: 'dn-main' },
                h('div', { class: 'dn-line' }, h('b', { class: 'dn-name' }, d.name), grade),
                h('span', { class: 'dn-sub' }, `${num(d.count)}번 후원`)),
            h('b', { class: 'dn-total' }, won(d.total)),
            h('button', { type: 'button', class: 'btn sm ghost-danger dn-ex-btn', disabled: d.busy, onclick: () => exclude(d) },
                d.busy ? '빼는 중…' : '순위에서 빼기'));
    }

    function draw(force) {
        const s = ctx.slices;
        const t = s.tallies || {};
        const r = s.donor_rules || {};
        if (!force && t === lastT && r === lastR) return;
        lastT = t;
        lastR = r;
        const donors = t.donors || {}, vip = t.vip || {};
        const all = Object.entries(donors)
            .map(([key, v]) => ({ key, name: v.name || key, total: Number(v.total) || 0, count: Number(v.count) || 0 }))
            .filter(d => d.total > 0)
            .sort((a, b) => b.total - a.total || (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
        let rank = 0, prev = null, sum = 0;
        all.forEach((d, i) => {
            if (d.total !== prev) { rank = i + 1; prev = d.total; }
            d.rank = rank;
            sum += d.total;
        });
        const sm = all.length ? `${num(all.length)}명 · ${won(sum)}` : '';
        if (summary.textContent !== sm) summary.textContent = sm;

        const qv = q.value.trim().toLowerCase();
        const pick = qv ? all.filter(d => d.name.toLowerCase().includes(qv) || d.key.toLowerCase().includes(qv)) : all;
        const view = pick.slice(0, shown);
        const keep = new Set(view.map(d => d.key));
        for (const [k, row] of rows) if (!keep.has(k)) { row.el.remove(); rows.delete(k); }
        view.forEach((d, i) => {
            const v = vip[d.key];
            const item = { key: d.key, name: d.name, total: d.total, count: d.count, rank: d.rank,
                vip: v ? { grade: v.grade, color: v.color, badge: v.badge } : null, busy: busy.has(d.key) };
            let row = rows.get(d.key);
            if (!row) { row = { el: h('li'), sig: '' }; rows.set(d.key, row); }
            const sig = JSON.stringify(item);
            if (sig !== row.sig) { fill(row.el, item); row.sig = sig; }
            if (ol.children[i] !== row.el) ol.insertBefore(row.el, ol.children[i] || null);
        });
        more.hidden = pick.length <= shown;
        more.textContent = `더 보기 (${num(pick.length - shown)}명 남음)`;
        empty.hidden = pick.length > 0;
        empty.textContent = all.length ? '찾는 후원자가 없어요' : '이번 방송 후원자가 아직 없어요';

        // 뺀 이름
        const ex = Array.isArray(r.excluded) ? r.excluded : [];
        const exNames = (r.names && typeof r.names === 'object') ? r.names : {};
        exBox.hidden = !ex.length;
        const exKeep = new Set(ex);
        for (const [k, row] of exRows) if (!exKeep.has(k)) { row.el.remove(); exRows.delete(k); }
        ex.forEach((key, i) => {
            let row = exRows.get(key);
            const b = busy.has('ex:' + key);
            if (!row) {
                row = { el: h('li', { class: 'dn-exrow' }), b: null };
                exRows.set(key, row);
            }
            const shownName = exNames[key] || key;     // 뺄 때 보이던 이름(없으면 키)
            if (row.b !== b || row.n !== shownName) {
                row.b = b; row.n = shownName;
                row.el.replaceChildren(h('b', { class: 'dn-name' }, shownName),
                    h('button', { type: 'button', class: 'btn sm', disabled: b, onclick: () => include(key) }, b ? '넣는 중…' : '다시 넣기'));
            }
            if (exList.children[i] !== row.el) exList.insertBefore(row.el, exList.children[i] || null);
        });

        // 직접 준 등급
        const manual = (r.manual && typeof r.manual === 'object') ? r.manual : {};
        const msig = JSON.stringify([manual, Object.keys(vip).filter(k => vip[k].manual)]);
        if (msig !== lastManual) {
            lastManual = msig;
            const ents = Object.entries(manual).sort((a, b) => (a[1].name || a[0]).localeCompare(b[1].name || b[0], 'ko'));
            mvList.replaceChildren(...(ents.length ? ents.map(([key, m]) => {
                const live = vip[key];
                const note = live && live.manual ? '방송판에 붙어 있어요' : live ? `지금 ${live.rank}위라 순위 등급(${live.grade})이 먼저예요` : '순위에서 뺀 이름이라 안 붙어요';
                return h('li', { class: 'dn-exrow' },
                    h('span', { class: 'dn-line' },
                        h('b', { class: 'dn-name' }, m.name || key),
                        h('span', { class: 'dn-grade', style: `--g:${/^#[0-9a-f]{6}$/i.test(m.color || '') ? m.color : '#bcb0a6'}` }, (m.badge || '') + ' ' + m.grade),
                        h('small', { class: 'muted' }, ' ' + note)),
                    h('button', { type: 'button', class: 'btn sm ghost-danger', onclick: async () => {
                        const ok = await ctx.confirm({ title: `'${m.name || key}' 님의 직접 준 등급을 뺄까요?`, body: '순위로 받은 등급은 그대로예요.', ok: '등급 빼기', cancel: '그대로 두기' });
                        if (!ok) return;
                        const res = await ctx.run('vip.remove', { name: key });
                        if (res.ok) ctx.toast('등급을 뺐어요', 'info');
                    } }, '빼기'));
            }) : [h('li', { class: 'empty' }, '직접 준 등급이 없어요')]));
        }
    }

    return { render() { draw(false); } };
}
