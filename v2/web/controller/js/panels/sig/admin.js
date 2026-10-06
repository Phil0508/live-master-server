/* 🎵 시그니처 탭 — 목록 · 찾기 · 새로 등록 · 고치기 · 지우기 · 최근 바뀐 것.
   옛 upload.html(음원 · 사진 등록) + 후원 콘솔(manual_send.html)의 '시그니처 관리' 를 옮겼다.

   목록: GET /api/sigadmin/list — 보관소(Supabase)에서 새로 받는다(서버의 후원 매칭 목록도 같이 새로워진다)
     탭을 열 때 한 번 · [↻] · 그리고 sig_admin.ver 가 바뀔 때(다른 기기 · 이 기기에서 바꿨을 때) 다시 받는다.
   카드: 사진 · 금액 · 제목 · 음원 있음/없음 · 재생 시간 · [▶] 미리 듣기(이 컴퓨터에서만 — 방송에는 안 나간다)
     카드를 누르면 고치기 창(form.js) — 거기서 저장 · 방송에 틀기 · 지우기(확인 상자).
   ⚠️ 시그니처 보관소는 개발 · 방송이 같이 쓴다 — 여기서 바꾸면 방송에도 바로 반영된다(화면 위에 늘 적어 둔다).
   ⚠️ 탭이 가려지면(다른 탭을 열면) 미리 듣기를 멈춘다. */
import { h, num, call, once, label } from './common.js';
import { openForm } from './form.js';
import { mountHistory } from './history.js';

export function mountSigAdmin(el, ctx) {
    let sigs = null, err = '', configured = true, floor = 0, loading = false, again = false, loadedVer = -1, triedAuthed = false;
    const audio = new Audio();
    audio.preload = 'none';
    let playingId = null;

    const count = h('span', { class: 'count-badge zero' }, '0');
    const sub = h('span', { class: 'sg-sub' });
    const reload = h('button', { type: 'button', class: 'sg-mini', title: '목록 다시 받기', 'aria-label': '시그니처 목록 다시 받기' }, '↻');
    const q = h('input', { type: 'text', autocomplete: 'off', placeholder: '🔍 제목 · 금액으로 찾기', 'aria-label': '시그니처 찾기', class: 'sg-q' });
    const addBtn = h('button', { type: 'button', class: 'btn pri sg-add' }, '＋ 새 시그니처');
    const state = h('p', { class: 'sg-state', 'aria-live': 'polite', hidden: true });
    const grid = h('div', { class: 'sg-grid' });
    const empty = h('p', { class: 'empty', hidden: true });
    const histBox = h('section', { class: 'sg-blk sg-hist' });

    el.classList.add('sg');
    el.append(
        h('section', { class: 'sg-blk' },
            h('div', { class: 'sg-bh' }, h('h3', null, '💿 시그니처', count), sub, reload),
            h('p', { class: 'sg-warn' }, '⚠️ 여기서 바꾼 것은 ', h('b', null, '방송에 바로 반영'), '돼요(개발 · 방송이 같은 보관소를 써요). 지운 것은 아래 [최근 바뀐 것]에서 되살릴 수 있어요.'),
            h('div', { class: 'sg-bar' }, q, addBtn),
            state, grid, empty),
        histBox);
    const hist = mountHistory(histBox, ctx, { onChanged: () => load() });

    /* ── 목록 받기 ── */
    async function load() {
        if (loading) { again = true; return; }          // 받는 중에 또 바뀌었다 — 끝나면 한 번 더
        loading = true;
        reload.disabled = true;
        if (!sigs) paintState('불러오는 중…');
        const verAt = ((ctx.slices.sig_admin || {}).ver) || 0;
        const r = await call('/api/sigadmin/list');
        loading = false;
        reload.disabled = false;
        if (r.ok) {
            sigs = (r.data.signatures || []).filter(s => s && s.amount != null)
                .sort((a, b) => (Number(a.amount) || 0) - (Number(b.amount) || 0) || (Number(a.id) || 0) - (Number(b.id) || 0));
            configured = r.data.configured !== false;
            floor = Number(r.data.floor) || 0;
            err = r.data.error ? `보관소에서 새로 받지 못해 전에 받은 목록을 보여요 (${r.data.error})` : '';
            loadedVer = Math.max(verAt, Number(r.data.ver) || 0);
        } else {
            err = r.error;
            loadedVer = Math.max(loadedVer, verAt);      // 실패해도 이 번호는 시도했다 — 쪽지마다 다시 묻지 않게(↻ 로 다시)
            if (r.status === 401) triedAuthed = false;
        }
        paint();
        if (again) { again = false; load(); }
    }
    reload.addEventListener('click', () => once(reload, load));

    function paintState(t, kind) {
        state.textContent = t || '';
        state.className = 'sg-state' + (kind ? ' ' + kind : '');
        state.hidden = !t;
    }

    /* ── 카드 ── */
    const cards = new Map();          // id → {el, sig}
    function card(s) {
        const hasSnd = !!s.sound_url;
        const play = hasSnd ? h('button', { type: 'button', class: 'sg-play', 'aria-label': `${s.title || '시그니처'} 미리 듣기`, title: '미리 듣기(이 컴퓨터에서만)' },
            playingId === s.id ? '■' : '▶') : null;
        if (play) play.addEventListener('click', e => { e.stopPropagation(); toggle(s); });
        const thumb = h('div', { class: 'sg-thumb' },
            s.image_url ? h('img', { src: s.image_url, alt: '', loading: 'lazy', decoding: 'async' }) : h('span', { class: 'sg-noimg' }, '사진 없음'),
            h('span', { class: 'sg-id' }, '#' + s.id), play);
        const meta = hasSnd ? h('span', { class: 'sg-snd ok' }, '🎵 음원')
            : h('span', { class: 'sg-snd no' }, `⚠ 음원 없음 · 사진 ${num(s.duration || 10)}초`);
        const dup = sigs.filter(x => Number(x.amount) === Number(s.amount)).length > 1;
        const b = h('button', { type: 'button', class: 'sg-card' + (dup ? ' dup' : '') + (playingId === s.id ? ' playing' : ''), 'aria-label': `${label(s)} 고치기` },
            thumb,
            h('span', { class: 'sg-amt' }, num(s.amount) + '원', dup ? h('span', { class: 'tag warn' }, '같은 금액') : null),
            h('span', { class: 'sg-title' }, s.title || '시그니처'),
            meta);
        b.addEventListener('click', () => edit(s.id));
        return b;
    }

    function paint() {
        if (!configured) {
            paintState('시그니처 보관소(Supabase)가 설정되지 않았어요 — 서버의 SUPABASE_URL · SUPABASE_SECRET_KEY 를 확인해 주세요', 'bad');
        } else if (err) paintState(err, 'bad');
        else paintState('');
        addBtn.disabled = !configured;
        const list = sigs || [];
        count.textContent = String(list.length);
        count.classList.toggle('zero', !list.length);
        sub.textContent = sigs && floor ? `${num(floor)}원부터 시그니처가 나가요` : '';
        const qv = q.value.trim().toLowerCase().replace(/[,원]/g, '');
        const view = qv ? list.filter(s => String(s.title || '').toLowerCase().includes(qv) || String(s.amount || '').includes(qv) || String(s.id) === qv.replace('#', '')) : list;
        const keep = new Set(view.map(s => String(s.id)));
        for (const [id, c] of cards) if (!keep.has(id)) { c.el.remove(); cards.delete(id); }
        view.forEach((s, i) => {
            const id = String(s.id);
            const dup = list.filter(x => Number(x.amount) === Number(s.amount)).length > 1;
            const sig = JSON.stringify([s, dup, playingId === s.id]);
            let c = cards.get(id);
            if (!c || c.sig !== sig) {
                const fresh = card(s);
                if (c) c.el.replaceWith(fresh);
                c = { el: fresh, sig };
                cards.set(id, c);
            }
            if (grid.children[i] !== c.el) grid.insertBefore(c.el, grid.children[i] || null);
        });
        empty.hidden = !sigs || view.length > 0;
        empty.textContent = list.length ? '찾는 시그니처가 없어요' : '등록된 시그니처가 없어요 — [＋ 새 시그니처] 로 등록해 주세요';
    }
    let qt = 0;
    q.addEventListener('input', () => { clearTimeout(qt); qt = setTimeout(paint, 120); });

    /* ── 미리 듣기 — 이 컴퓨터에서만 ── */
    function toggle(s) {
        if (playingId === s.id) { stopAudio(); return; }
        stopAudio();
        playingId = s.id;
        audio.src = s.sound_url;
        audio.volume = 0.6;
        audio.play().catch(() => { ctx.toast('미리 듣기를 못 했어요 — 음원 주소를 열 수 없어요', 'err'); stopAudio(); });
        paint();
    }
    function stopAudio() {
        try { audio.pause(); } catch (e) { /* 무시 */ }
        audio.removeAttribute('src');
        if (playingId != null) { playingId = null; paint(); }
    }
    audio.addEventListener('ended', stopAudio);
    // 다른 탭을 열면(이 판이 가려지면) 멈춘다
    new MutationObserver(() => { if (el.hidden) stopAudio(); }).observe(el, { attributes: true, attributeFilter: ['hidden'] });

    /* ── 등록 · 고치기 창 ── */
    function edit(id) {
        const s = (sigs || []).find(x => String(x.id) === String(id));
        if (!s) return;
        stopAudio();
        openForm(ctx, { sig: s, list: sigs || [], floor, onDone: () => load() });
    }
    addBtn.addEventListener('click', () => {
        if (!configured) return;
        stopAudio();
        openForm(ctx, { sig: null, list: sigs || [], floor, onDone: () => load() });
    });

    load();
    triedAuthed = !!ctx.lm.authed;
    return {
        render(slices) {
            hist.render(slices);
            // 다른 기기(또는 여기)에서 바꿨다 → 목록 다시 받기
            const ver = ((slices.sig_admin || {}).ver) || 0;
            if (sigs && ver > loadedVer && !loading) load();
            // 로그인 전에 열려 목록을 못 받았으면 로그인된 뒤 한 번 다시
            if (!sigs && !loading && !triedAuthed && ctx.lm.authed) { triedAuthed = true; load(); }
        },
    };
}
