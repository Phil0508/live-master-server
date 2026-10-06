/* 🎰 시그니처 슬롯머신 — 당첨은 서버가 뽑는다(POST /api/slot/spin · 옛 조종실 · 폰과 같은 주소).

   [돌리기] → 무대에 잠깐 올라가고, 당첨 시그는 대기줄로(릴이 선 뒤 재생) · 기여도 카드는 대기함으로 → 4초 뒤 원래 무대
   한 판 값 slot.config{price} · 이번 방송 후보 slot.config{pool:[id…]}(비면 전체에서)
   ⚠️ 옛 조종실은 브라우저에서 당첨을 뽑아 보냈다 — 이제 몸통을 안 보낸다(서버만 뽑는다).
   화면 약속 2: 조종실도 ends_at + 1초에 slot.done{round} 를 한 번 보낸다(방송판이 꺼져 있어도 무대가 돌아오게). */
import { h, num, won } from '../../util.js';
import { head, memo, syncVal, serverNow, okToTake, tile, post, loadSigs, sigsNow, sigsError, numInput, toInt, onEnter, shown } from './common.js';

export function mountSlot(el, ctx) {
    const paint = memo();
    let s = {}, ops = {}, slices = {}, pickerOpen = false, busy = false, last = null;
    const doneSent = new Set();

    const hd = head('🎰 슬롯머신', async on => {
        if (on) {
            if (!(await okToTake(ctx, 'slot', '슬롯머신'))) return;
            const res = await ctx.run('show.stage', { stage: 'slot' });
            if (res.ok) ctx.toast('슬롯머신을 방송에 띄웠어요 (기계만 미리)', 'ok');
        } else {
            const res = await ctx.run('show.stage', { stage: (slices.show || {}).ret || null });
            if (res.ok) ctx.toast('슬롯머신을 내렸어요', 'info');
        }
    });

    const spinT = tile('돌리기', '저절로 뜨고, 당첨 뒤 내려가요', spin, 'go');
    const pickT = tile('후보 고르기', '사진 목록 펼치기', () => { pickerOpen = !pickerOpen; if (pickerOpen) loadSigs().then(() => ctx.rerender()); ctx.rerender(); });
    const strip = h('p', { class: 'gm-status' });

    const price = numInput({ class: 'gm-in num w120', placeholder: '20000', 'aria-label': '한 판 값(원)' });
    const sendPrice = async () => {
        const v = toInt(price.value);
        if (v === null || v < 0) { ctx.toast('한 판 값은 0 이상의 숫자(원)로 적어 주세요', 'err'); return; }
        if (v === Number(ops.price)) return;
        const res = await ctx.run('slot.config', { price: v });
        if (res.ok) ctx.toast(`한 판 값: ${won(v)}`, 'ok');
    };
    onEnter(price, () => price.blur());
    price.addEventListener('change', sendPrice);

    const chips = h('div', { class: 'gm-chips' });
    const search = h('input', { type: 'search', class: 'gm-in grow', placeholder: '이름 또는 금액으로 찾기', 'aria-label': '시그니처 찾기', autocomplete: 'off' });
    search.addEventListener('input', () => paintPicker(true));
    const grid = h('div', { class: 'gm-sigs' });
    const total = h('span', { class: 'gm-info' });
    const picker = h('section', { class: 'gm-box', hidden: true },
        h('div', { class: 'gm-sub' }, h('b', null, '후보 고르기'), total),
        h('div', { class: 'gm-row' }, search,
            h('button', { type: 'button', class: 'btn sm', onclick: () => savePool((sigsNow() || []).map(x => String(x.id))) }, '전체 선택'),
            h('button', { type: 'button', class: 'btn sm', onclick: async () => { await loadSigs(true); ctx.rerender(); paintPicker(true); } }, '새로고침')),
        grid);

    el.append(h('div', { class: 'gm' },
        hd.el,
        h('div', { class: 'gm-tiles' }, spinT, pickT),
        strip,
        h('section', { class: 'gm-box' },
            h('div', { class: 'gm-sub' }, h('b', null, '이번 방송 후보'), h('span', { class: 'gm-sp' }),
                h('button', { type: 'button', class: 'btn sm', onclick: pickRandom }, '🔀 무작위 20개'),
                h('button', { type: 'button', class: 'btn sm ghost-danger', onclick: () => savePool([]) }, '전부 빼기')),
            chips,
            h('div', { class: 'gm-row' }, h('span', { class: 'gm-lbl' }, '한 판 값'), price, h('span', null, '원'),
                h('span', { class: 'gm-info' }, '당첨 시그 값에서 이만큼 뺀 몫이 기여도 카드로 대기함에 와요 (받을 사람은 대기함에서 고릅니다)'))),
        picker));

    async function spin() {
        if (busy) return;
        if (!(await okToTake(ctx, 'slot', '슬롯머신'))) return;
        busy = true;
        spinT.disabled = true;
        const r = await post('/api/slot/spin', {});
        busy = false;
        spinT.disabled = false;
        if (r.status === 200 && r.data.status === 'success') {
            last = r.data.winner || null;
            const w = last ? `${last.title} ${won(last.amount)}` : '';
            ctx.toast(`🎰 돌려요 — 당첨 ${w}`.trim(), 'ok', 5000);
            if (r.data.pool_missing) ctx.toast('고른 후보가 목록에 하나도 없어 전체에서 뽑았어요', 'info', 6000);
        } else {
            ctx.toast(r.why, 'err');
            if (r.status === 401) setTimeout(() => location.reload(), 1500);
        }
        ctx.rerender();
    }

    async function savePool(ids) {
        const res = await ctx.run('slot.config', { pool: ids });
        if (res.ok) ctx.toast(ids.length ? `후보 ${ids.length}개 — 이 안에서만 뽑아요` : '후보를 비웠어요 — 전체에서 뽑아요', 'info');
    }
    function toggle(id) {
        const pool = (ops.pool || []).map(String);
        const k = String(id);
        savePool(pool.includes(k) ? pool.filter(x => x !== k) : pool.concat([k]));
    }
    async function pickRandom() {
        const all = (await loadSigs()) || [];
        if (!all.length) { ctx.toast(sigsError() || '시그니처 목록이 비어 있어요', 'err'); return; }
        const a = all.slice();
        for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; }
        savePool(a.slice(0, 20).map(x => String(x.id)));
    }

    function paintChips() {
        const all = sigsNow();
        const pool = (ops.pool || []).map(String);
        const by = new Map((all || []).map(x => [String(x.id), x]));
        if (!pool.length) {
            chips.replaceChildren(h('span', { class: 'gm-info' }, all ? (all.length ? `고른 후보가 없어요 — 전체 ${all.length}개에서 뽑아요` : (sigsError() || '등록된 시그니처가 없어요')) : '시그니처 목록을 불러오는 중…'));
            return;
        }
        chips.replaceChildren(...pool.map(id => {
            const x = by.get(id);
            return h('span', { class: 'gm-chip on sig' },
                x && x.image_url ? h('img', { src: x.image_url, alt: '', loading: 'lazy' }) : null,
                x ? x.title || '시그니처' : `#${id} (목록에 없음)`,
                x ? h('em', null, num(x.amount)) : null,
                h('button', { type: 'button', class: 'gm-x', title: '후보에서 빼기', 'aria-label': '후보에서 빼기', onclick: () => toggle(id) }, '✕'));
        }));
    }

    function paintPicker(force) {
        picker.hidden = !pickerOpen;
        pickT.classList.toggle('on', pickerOpen);
        pickT.setSub(pickerOpen ? '사진 목록 닫기' : '사진 목록 펼치기');
        if (!pickerOpen) return;
        const all = sigsNow();
        const pool = new Set((ops.pool || []).map(String));
        const q = search.value.trim().toLowerCase();
        paint('grid', [all ? all.length : -1, [...pool], q, force ? Math.random() : 0], () => {
            if (!all) { grid.replaceChildren(h('p', { class: 'empty' }, '시그니처 목록을 불러오는 중…')); return; }
            total.textContent = `사진을 눌러 넣고 빼요 · 전체 ${all.length}개 · 고른 ${pool.size}개`;
            const list = q ? all.filter(x => String(x.title || '').toLowerCase().includes(q) || String(x.amount || '').includes(q)) : all;
            if (!list.length) { grid.replaceChildren(h('p', { class: 'empty' }, all.length ? '찾는 시그니처가 없어요' : (sigsError() || '등록된 시그니처가 없어요'))); return; }
            grid.replaceChildren(...list.map(x => {
                const on = pool.has(String(x.id));
                return h('button', { type: 'button', class: 'gm-sig' + (on ? ' on' : ''), 'aria-pressed': String(on), onclick: () => toggle(x.id) },
                    x.image_url ? h('img', { src: x.image_url, alt: '', loading: 'lazy' }) : h('span', { class: 'gm-noimg' }, '🎵'),
                    h('span', { class: 'gm-sig-t' }, on ? '✓ ' : '', x.title || '시그니처'),
                    h('span', { class: 'gm-sig-a' }, won(x.amount)));
            }));
        });
    }

    function paintStrip() {
        const all = sigsNow();
        const pool = (ops.pool || []).length;
        let t = pool ? `후보 ${pool}개 중에서 뽑아요` : all && all.length ? `후보를 안 골라서 전체 ${all.length}개에서 뽑아요` : '후보를 안 골라서 전체에서 뽑아요';
        t += ` · 한 판 ${won(ops.price || 0)}`;
        const left = Number(s.ends_at || 0) - serverNow();
        if (s.phase === 'spinning' && left > 0) t += ` · 🎰 도는 중 (${Math.ceil(left / 1000)}초)`;
        const w = s.winner || last;
        if (w) t += ` · 방금 ${w.title} ${won(w.amount)}`;
        if (strip.textContent !== t) strip.textContent = t;
        spinT.disabled = busy || (s.phase === 'spinning' && left > 0);
        spinT.setSub(s.phase === 'spinning' && left > 0 ? '도는 중이에요' : '저절로 뜨고, 당첨 뒤 내려가요');
    }
    setInterval(() => { if (shown(strip) && s.phase === 'spinning') paintStrip(); }, 500);

    function scheduleDone() {
        if (s.phase !== 'spinning' || doneSent.has(s.round)) return;
        doneSent.add(s.round);
        const rnd = s.round;
        setTimeout(() => { ctx.run('slot.done', { round: rnd }, { quiet: true }); }, Math.max(0, Number(s.ends_at || 0) + 1000 - serverNow()));
    }

    let asked = false;
    return {
        render(sl) {
            slices = sl;
            s = sl.slot || {};
            ops = sl.slot_ops || {};
            if (!asked) { asked = true; loadSigs().then(() => ctx.rerender()); }
            hd.setAir((sl.show || {}).stage === 'slot');
            hd.setPill(s.phase === 'spinning' ? '도는 중' : '', 'hot');
            syncVal(price, ops.price == null ? '' : ops.price);
            paint('chips', [(ops.pool || []), sigsNow() ? sigsNow().length : -1], paintChips);
            paintPicker(false);
            paintStrip();
            scheduleDone();
        },
    };
}
