/* 📥 옛 배치 가져오기 — 옛 방송판의 위젯 자리 파일(layout.json, 옛 편집기가 저장한 것)을 v2 자리로 옮긴다.
   셈은 서버가 한다(layout.import_old — v2/server/domain/oldlayout.py, 검사 test_oldlayout). 여기는 고르기 · 재기 · 보내기만.
     옛 것: 모든 위젯이 '왼쪽 위' 기준(left · top · scale, transform-origin top left).
     v2: 칸마다 기준점(anchor)이 다르다(점수판 · 계좌 · 퇴근빵 = 오른쪽 위 · 팝업 · 주사위판 = 가운데 위 · …) →
         기준점이 다른 칸은 폭을 알아야 바꿀 수 있다.
   여기(편집기)서 하는 까닭: 계좌는 글자 길이(은행 · 예금주 · 번호)로 폭이 바뀐다 — 이 화면의 방송판에서 **지금 계좌 칸의 폭을 재서**
   같이 보낸다(sizes). 못 재면 서버가 보통 폭으로 셈하고 '확인 필요' 로 돌려준다.
   옛 규칙 그대로(서버가 지킨다): __v 2 미만 파일은 안 읽는다 · __free 가 아니면 안전지대(115~954) 안으로 · 전광판(notice)은 안 옮긴다.
   ⚠️ 옛 파일이 가리키는 v2 칸은 전부 옛 것대로 바뀐다(파일에 없던 칸은 기본 자리로). v2 에만 있는 칸(퀴즈 등)은 그대로. */
const E = window.__lmEditor;
const lm = E && E.S && E.S.lm;

function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
        if (v == null || v === false) continue;
        if (k === 'class') el.className = v;
        else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
        else el.setAttribute(k, v === true ? '' : String(v));
    }
    kids.flat().forEach(c => { if (c != null && c !== false) el.append(c instanceof Node ? c : document.createTextNode(String(c))); });
    return el;
}

/** 지금 방송판(이 화면의 미리보기)에서 잰 폭 — 글자 · 내용으로 폭이 바뀌는 칸만. 못 재면 빈 것 */
export function measure(doc) {
    const out = {};
    if (!doc) return out;
    const acc = doc.querySelector('[data-layer="account"] .acc-box-v2');
    // 계좌 상자는 안 보일 때(gone)도 글자는 채워져 있어 폭을 잴 수 있다 — 은행 · 번호가 다 비면 못 잰다
    if (acc && acc.offsetWidth > 50 && (acc.textContent || '').replace(/[🏦\s]/gu, '')) out.account = { w: acc.offsetWidth };
    ['homeRace', 'hell'].forEach(id => {
        const el = doc.querySelector('[data-layer="' + id + '"]');
        if (el && el.offsetWidth > 50) out[id] = { w: el.offsetWidth };
    });
    return out;
}

function mount() {
    const after = document.querySelector('.list-card');
    if (!lm || !after) return;
    const file = h('input', { type: 'file', accept: '.json,application/json', 'aria-label': '옛 배치 파일 고르기' });
    const what = h('p', { class: 'muted small' });
    const go = h('button', { class: 'btn pri wide', type: 'button', disabled: true }, '이 자리로 옮기기');
    const out = h('p', { class: 'muted small', 'aria-live': 'polite' });
    const card = h('details', { class: 'card ed2', id: 'ed2-oldlayout' },
        h('summary', null, h('h2', null, '📥 옛 배치 가져오기')),
        h('p', { class: 'muted small ed2-note' }, '옛 서버의 ', h('b', null, 'layout.json'), '(옛 편집기가 저장한 위젯 자리)을 고르면 v2 자리로 바꿔 옮겨요. ',
            '점수판처럼 오른쪽 끝이 기준인 칸도 옛 화면과 같은 곳에 서요. 계좌 폭은 이 화면에서 재서 맞춰요.'),
        file, what, go, out);
    after.after(card);
    let layout = null;

    file.addEventListener('change', () => {
        layout = null; go.disabled = true; out.textContent = '';
        const f = file.files && file.files[0];
        if (!f) { what.textContent = ''; return; }
        const rd = new FileReader();
        rd.onload = () => {
            let j = null;
            try { j = JSON.parse(String(rd.result || '')); } catch (e) { /* 아래에서 알린다 */ }
            const ids = j && typeof j === 'object' && !Array.isArray(j)
                ? Object.keys(j).filter(k => !k.startsWith('__') && j[k] && typeof j[k] === 'object' && 'x_px' in j[k]) : [];
            if (!ids.length) { what.textContent = '옛 배치 파일(layout.json)이 아니에요 — {위젯: {x_px, y_px, scale}} 모양이어야 해요'; return; }
            if (!((Number(j.__v) || 0) >= 2)) { what.textContent = '옛 판(__v 2 미만) 파일이에요 — 옛 방송판도 이 파일은 안 읽었어요'; return; }
            layout = j;
            go.disabled = false;
            what.textContent = '📐 ' + f.name + ' — 위젯 ' + ids.length + '칸' + (j.ranking ? ` · 점수판 왼쪽 ${j.ranking.x_px} · 위 ${j.ranking.y_px} · ${j.ranking.scale || 1}배` : '');
        };
        rd.readAsText(f, 'utf-8');
    });
    go.addEventListener('click', async () => {
        if (!layout || go.disabled) return;
        go.disabled = true;
        try { if (E.flushAll) E.flushAll(); } catch (e) {}          // 아직 안 보낸 손 자리를 먼저(명령은 보낸 순서대로)
        let sizes = {};
        try { const fw = E.frameWin && E.frameWin(); sizes = measure(fw && fw.document); } catch (e) {}
        let r;
        try { r = await lm.cmd('layout.import_old', { layout, sizes }); } catch (e) { r = { ok: false, error: '보내지 못했어요 — 다시 눌러 주세요' }; }
        go.disabled = false;
        if (!r || !r.ok) { out.textContent = '❌ ' + ((r && r.error) || '못 옮겼어요'); return; }
        const parts = ['✅ ' + (r.moved || []).length + '칸을 옮겼어요'];
        if ((r.approx || []).length) parts.push('보통 폭으로 셈한 칸: ' + r.approx.join(' · ') + ' — 한 번 봐 주세요');
        if ((r.skipped || []).length) parts.push('안 옮긴 것: ' + r.skipped.join(' · '));
        out.textContent = parts.join(' / ');
    });
    window.__lmEditorOldLayout = { measure: () => { try { return measure(E.frameWin().document); } catch (e) { return {}; } } };   // 점검용
}

mount();
