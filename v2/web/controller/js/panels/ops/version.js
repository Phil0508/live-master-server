/* 🕹️ 버전 — 어떤 코드를 돌릴지 고른다(옛 조종실 [버전] 그대로).
   GET /api/version/list · POST /api/version/switch {sha, during_live?} · POST /api/version/latest
   ⚠️ 되돌리면 자동 배포가 멈춘다(그 버전에 '고정'). 안 그러면 2분 뒤 최신으로 도로 끌려 올라간다. [최신으로] 를 눌러야 풀린다.
   ⚠️ v2 가 없던 버전(has_ui=false)으로 되돌리면 조종실에서 돌아올 방법이 사라진다 — 세게 알린다.
   옮긴 뒤엔 서버가 다시 켜질 때까지 기다렸다가 화면을 새로 읽는다(새 코드로). */
import { h, fill, api, once, blockHead } from './common.js';

export function mountVersion(el, ctx) {
    const cur = h('div', { class: 'ver-cur' });
    const list = h('ol', { class: 'ver-list' });
    const note = h('p', { class: 'ops-note warn', hidden: true });
    const reloadBtn = h('button', { type: 'button', class: 'btn sm', onclick: () => once(reloadBtn, () => load(true)) }, '다시 불러오기');
    el.classList.add('ops', 'ops-version');
    el.append(
        h('section', { class: 'ops-blk' }, blockHead('지금 버전', '문제가 생기면 여기서 바로 전 버전으로 되돌려요'), cur, note),
        h('section', { class: 'ops-blk' }, h('div', { class: 'ops-bh' }, h('h3', null, '최근 버전 20개'), reloadBtn), list),
    );

    let loaded = false, busy = false;

    async function load(force) {
        if (loaded && !force) return;
        const r = await api('/api/version/list');
        if (!r.ok) { fill(cur); fill(list, h('li', { class: 'empty' }, '버전 정보를 불러오지 못했어요 — ' + r.error)); return; }
        loaded = true;
        const d = r.data, c = d.current || {};
        fill(cur,
            h('div', { class: 'ver-now' + (d.pinned ? ' pinned' : '') },
                h('span', { class: 'ops-lbl' }, '지금 돌고 있는 버전'),
                h('div', { class: 'ver-big' }, h('b', null, c.label || ''), h('span', null, c.subject || '(알 수 없음)')),
                h('small', { class: 'ops-dim' }, `${c.short || ''} · ${c.date || ''}`),
                d.needs_restart ? h('p', { class: 'ops-note warn' }, '⚠️ 파일은 이 버전으로 바뀌었지만 서버가 아직 다시 켜지지 않았어요 — 옛 코드가 돌고 있어요. (서버의 재시작 권한(sudoers)을 확인해야 해요)') : null,
                d.pinned
                    ? [h('p', { class: 'ver-pin' }, '📌 이 버전에 고정돼 있어요 — 새 버전이 올라와도 자동으로 안 바뀌어요'),
                       h('button', { type: 'button', class: 'btn pri sm', onclick: e => once(e.currentTarget, latest) }, '⬆ 최신으로 돌아가기')]
                    : h('p', { class: 'ver-ok' }, '✓ 최신을 따라가는 중 (새 버전이 올라오면 2분 안에 자동 반영)')));
        const rows = d.commits || [];
        fill(list, rows.length ? rows.map((v, i) => {
            const now = v.sha === c.sha;
            return h('li', { class: 'ver-row' + (now ? ' now' : '') },
                h('b', { class: 'ver-lbl' }, v.label || v.short),
                h('div', { class: 'ver-main' },
                    h('span', { class: 'ver-sub' }, v.subject),
                    h('small', { class: 'ops-dim' }, `${v.short} · ${v.date}`, i === 0 ? h('em', { class: 'ver-new' }, ' · 최신') : null,
                        v.has_ui === false ? h('em', { class: 'ver-noui' }, ' · v2 없음') : null)),
                now ? h('span', { class: 'ver-here' }, '지금 이것')
                    : h('button', { type: 'button', class: 'btn sm', onclick: () => switchTo(v) }, '이 버전으로'));
        }) : h('li', { class: 'empty' }, '기록이 없어요'));
    }

    async function waitBack(msg) {
        note.hidden = false;
        note.textContent = '🔄 ' + (msg || '서버가 다시 켜지고 있어요') + ' — 돌아오면 화면을 새로 읽어요';
        await new Promise(r => setTimeout(r, 2500));          // 재시작까지 1초 — 아직 안 꺼졌을 수 있다
        const t0 = Date.now();
        while (Date.now() - t0 < 120000) {
            try {
                const r = await fetch('/api/health', { cache: 'no-store' });
                if (r.ok) { location.reload(); return; }
            } catch (e) { /* 아직 꺼져 있다 */ }
            await new Promise(r => setTimeout(r, 2000));
        }
        note.textContent = '⚠️ 2분이 지나도 서버가 안 돌아왔어요 — /health 를 폰으로 열어 확인해 주세요';
    }

    async function switchTo(v) {
        if (busy) return;
        const noWay = v.has_ui === false ? '\n\n⚠️ 이 버전에는 v2 가 없어요.\n되돌리면 이 조종실이 안 떠서 최신으로 못 돌아와요 —\n서버에 직접 들어가 DEPLOY_PIN 파일을 지워야 해요.' : '';
        const ok = await ctx.confirm({
            title: `${v.label || v.short} 로 되돌릴까요?`,
            body: '· 서버가 몇 초 동안 껐다 켜져요 (방송 화면이 잠깐 끊길 수 있어요)\n· 그 사이 들어온 후원은 사라지지 않고 다시 보내져요\n· 되돌려 두면 자동 배포가 멈춰요 ([최신으로] 를 눌러야 다시 따라가요)' + noWay,
            ok: '되돌리기', cancel: '그대로 두기',
        });
        if (!ok) return;
        busy = true;
        try {
            let r = await api('/api/version/switch', { sha: v.sha });
            if (!r.ok && r.data && r.data.need_confirm) {
                const again = await ctx.confirm({ title: '지금 방송 중이에요', body: r.data.message, ok: '그래도 옮기기', cancel: '방송 끝나고 하기' });
                if (!again) return;
                r = await api('/api/version/switch', { sha: v.sha, during_live: true });
            }
            if (!r.ok) { ctx.toast('되돌리지 못했어요 — ' + r.error, 'err', 6000); return; }
            if (!r.data.restarting) { ctx.toast(r.data.message || '이미 그 버전이에요', 'info'); return; }
            await waitBack(r.data.message);
        } finally { busy = false; }
    }

    async function latest() {
        if (busy) return;
        const ok = await ctx.confirm({ title: '최신 버전으로 돌아갈까요?', body: '자동 배포도 다시 켜져요.\n서버가 몇 초 동안 껐다 켜져요.', ok: '최신으로', cancel: '그대로 두기' });
        if (!ok) return;
        busy = true;
        try {
            const r = await api('/api/version/latest', {});
            if (!r.ok) { ctx.toast('되돌리지 못했어요 — ' + r.error, 'err', 6000); return; }
            if (!r.data.restarting) { ctx.toast(r.data.message || '이미 최신이에요', 'info'); await load(true); return; }
            await waitBack(r.data.message);
        } finally { busy = false; }
    }

    return { render() { load(false); } };
}
