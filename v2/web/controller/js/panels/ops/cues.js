/* 💾 순서표(세이브 슬롯) — 옛 조종실 '방송 화면' 칸 윗줄(psRender · showCue · psEdit*)과 옛 편집기 세이브 슬롯을 옮겼다(서버 settings2.py).
   단계 하나 = 위젯 자리 · 크기 + 고정 자리 + 무대. 누르면 저장한 그 모습으로 바뀐다(preset.apply).
     [◀] [1. 오프닝] [2. 1차 대결] … [다음 ▶ 이름]  → show.cue {dir: 'prev' | 'next'}
     [＋ 지금 화면을 단계로]                          → preset.save {name}(비우면 '슬롯 N')
     ✏️ 편집 — 고칠 단계를 고르고: 이름 저장(preset.rename) · 📸 지금 화면으로 바꾸기(preset.save {id}) ·
               ◀ 앞으로 / 뒤로 ▶(preset.move) · 🗑 지우기(preset.delete). 덮어쓰기 · 지우기는 3초 안에 한 번 더 눌러야 한다.
   ⚠️ 편집 중엔 단계를 눌러도 방송판이 안 바뀐다 — 고치기만(옛 것과 같다).
   ⚠️ 게임 속 내용(룰렛 칸 · 핀볼 명단) · 점수 · 테마는 단계가 안 바꾼다. 대결 · 지옥탈출 · 퇴근빵 진행도 그대로(무대에 올리고 내리기만).
   ⚠️ 이름은 h()/textContent 로만 넣는다(innerHTML 금지). 확인은 화면 안에서(prompt · confirm 안 씀). */
import { h, sigOf, once, onEnter, setVal, blockHead, fill } from './common.js';

const NAME_MAX = 30;
const ARM_MS = 3000;          // 덮어쓰기 · 지우기 — 3초 안에 한 번 더

export function mountCues(ctx, stageName) {
    const SN = stageName || {};
    const list = () => (((ctx.slices.presets || {}).list) || []).filter(p => p && p.id);
    const atNow = () => { const v = Number(((ctx.slices.show || {}).cue_at)); return isFinite(v) ? v : -1; };

    let editing = false, pick = '', delArmed = 0, overArmed = 0;

    const prevBtn = h('button', { type: 'button', class: 'ops-mini', title: '이전 단계', 'aria-label': '이전 단계', onclick: () => once(prevBtn, () => cue('prev')) }, '◀');
    const chips = h('div', { class: 'ops-chips', role: 'group', 'aria-label': '순서표 단계' });
    const nextBtn = h('button', { type: 'button', class: 'btn pri sm', title: '순서표 다음 단계로', onclick: () => once(nextBtn, () => cue('next')) }, '다음 ▶');
    const newName = h('input', { type: 'text', autocomplete: 'off', maxlength: String(NAME_MAX), class: 'grow', placeholder: '새 단계 이름 (예: 1차 대결, 휴식, 지옥탈출)', 'aria-label': '새 단계 이름' });
    const newBtn = h('button', { type: 'button', class: 'btn sm', title: '지금 화면(위젯 자리 · 무대 · 고정 자리)을 순서표 끝에 단계로 저장합니다',
        onclick: () => once(newBtn, saveNew) }, '＋ 지금 화면을 단계로');
    onEnter(newName, () => once(newBtn, saveNew));
    const editBtn = h('button', { type: 'button', class: 'btn sm', 'aria-pressed': 'false', title: '단계 이름 바꾸기 · 순서 바꾸기 · 지우기',
        onclick: () => toggleEdit() }, '✏️ 편집');

    // 편집 줄
    const hint = h('p', { class: 'ops-hint' });
    const eName = h('input', { type: 'text', autocomplete: 'off', maxlength: String(NAME_MAX), class: 'grow', placeholder: '단계 이름', 'aria-label': '단계 이름' });
    const eRename = h('button', { type: 'button', class: 'btn sm', onclick: () => once(eRename, rename) }, '✓ 이름 저장');
    onEnter(eName, () => once(eRename, rename));
    const eOver = h('button', { type: 'button', class: 'btn sm', title: '이 단계를 지금 방송판 모습(무대 · 고정 자리 · 위젯 자리)으로 바꿉니다',
        onclick: () => once(eOver, overwrite) });
    const eLeft = h('button', { type: 'button', class: 'btn sm', title: '한 칸 앞으로', onclick: () => once(eLeft, () => move(-1)) }, '◀ 앞으로');
    const eRight = h('button', { type: 'button', class: 'btn sm', title: '한 칸 뒤로', onclick: () => once(eRight, () => move(1)) }, '뒤로 ▶');
    const eDel = h('button', { type: 'button', class: 'btn sm danger', onclick: () => once(eDel, del) });
    const eDone = h('button', { type: 'button', class: 'btn sm', onclick: () => toggleEdit(false) }, '다 했어요');
    const tools = h('div', { class: 'ops-row wrap' }, eName, eRename, eOver, eLeft, eRight, eDel);
    const editBox = h('div', { class: 'ops-note gold', hidden: true },
        h('div', { class: 'ops-row wrap' }, hint, h('span', { style: 'margin-left:auto' }, eDone)), tools);

    const el = h('section', { class: 'ops-blk ops-cues' },
        blockHead('💾 순서표', '단계 = 위젯 자리 + 고정 자리 + 무대 — 누르면 그 모습으로 바뀌어요(점수 · 게임 속 내용 · 테마는 그대로)'),
        h('div', { class: 'ops-row wrap' }, prevBtn, chips, h('span', { style: 'margin-left:auto' }, nextBtn)),
        h('div', { class: 'ops-row wrap' }, newName, newBtn, editBtn),
        editBox);

    // ── 보내기 ──
    async function cue(dir) {
        const res = await ctx.run('show.cue', { dir });
        if (res.ok) ctx.toast('📺 ' + (res.at + 1) + '. ' + (res.name || '단계'), 'ok');
    }
    async function apply(id) {
        const res = await ctx.run('preset.apply', { id });
        if (res.ok) ctx.toast('📺 "' + (res.name || '단계') + '" 으로 바꿨어요', 'ok');
    }
    async function saveNew() {
        const name = newName.value.trim().slice(0, NAME_MAX);
        const res = await ctx.run('preset.save', { name });
        if (res.ok) { newName.value = ''; ctx.toast('💾 "' + (res.name || '단계') + '" 저장했어요 — 순서표 끝에 붙었어요', 'ok'); }
    }
    function disarm() {
        if (delArmed) { clearTimeout(delArmed); delArmed = 0; }
        if (overArmed) { clearTimeout(overArmed); overArmed = 0; }
    }
    function toggleEdit(on) {
        editing = on === undefined ? !editing : !!on;
        if (!editing) pick = '';
        disarm();
        paint(true);
    }
    function choose(id) {
        pick = pick === id ? '' : id;
        disarm();
        const p = list().find(x => x.id === pick);
        eName.value = p ? (p.name || '') : '';
        paint(true);
        if (pick) { eName.focus(); eName.select(); }
    }
    async function rename() {
        const name = eName.value.trim();
        if (!pick) return;
        if (!name) { ctx.toast('이름을 적어 주세요', 'err'); return; }
        const res = await ctx.run('preset.rename', { id: pick, name });
        if (res.ok) { eName.blur(); ctx.toast('✏️ 이름을 바꿨어요', 'ok'); }
    }
    async function move(dir) {
        if (!pick) return;
        disarm();
        await ctx.run('preset.move', { id: pick, dir });
    }
    async function overwrite() {
        if (!pick) return;
        if (!overArmed) {
            disarm();
            overArmed = setTimeout(() => { overArmed = 0; paint(true); }, ARM_MS);
            paint(true);
            return;
        }
        disarm();
        const res = await ctx.run('preset.save', { id: pick });
        paint(true);
        if (res.ok) ctx.toast('📸 지금 화면으로 바꿨어요', 'ok');
    }
    async function del() {
        if (!pick) return;
        if (!delArmed) {                       // 실수로 한 번에 지워지지 않게 3초 안에 두 번
            disarm();
            delArmed = setTimeout(() => { delArmed = 0; paint(true); }, ARM_MS);
            paint(true);
            return;
        }
        disarm();
        const res = await ctx.run('preset.delete', { id: pick });
        if (res.ok) { pick = ''; ctx.toast('🗑️ 지웠어요', 'info'); }
        paint(true);
    }

    // ── 그리기 ──
    let lastSig = '';
    function paint(force) {
        const ps = list(), at = atNow();
        const sig = sigOf(ps.map(p => [p.id, p.name, p.stage, p.board]), at, editing, pick, !!delArmed, !!overArmed);
        if (!force && sig === lastSig) return;
        lastSig = sig;
        if (pick && !ps.some(p => p.id === pick)) pick = '';
        el.classList.toggle('editing', editing);
        editBtn.classList.toggle('on', editing);
        editBtn.setAttribute('aria-pressed', String(editing));
        const nx = ps[at + 1];
        nextBtn.textContent = nx ? '다음 ▶ ' + nx.name : (ps.length ? '끝' : '다음 ▶');
        nextBtn.disabled = !nx;
        prevBtn.disabled = !(at > 0 && at - 1 < ps.length);
        if (!ps.length) {
            fill(chips, h('span', { class: 'ops-hint inline' }, '순서표가 비어 있어요 — 화면을 맞추고 [＋ 지금 화면을 단계로] 로 저장하세요'));
        } else {
            fill(chips, ps.map((p, i) => {
                const st = p.stage !== undefined ? p.stage : p.board;
                const cls = 'ops-chip sm' + (editing ? (p.id === pick ? ' on' : '') : (i === at ? ' on' : ''));
                const b = h('button', { type: 'button', class: cls, 'data-cue': p.id,
                    'aria-pressed': String(editing ? p.id === pick : i === at),
                    title: editing ? '이 단계 고치기' : '무대: ' + (SN[st] || '없음') + (p.old ? ' · 옛 프로그램에서 옮겨 온 단계(위젯 자리 없음)' : ''),
                    style: (editing ? 'border-style:dashed;' : '') + (!editing && i < at ? 'opacity:.6;' : '') },
                    (i + 1) + '. ' + (p.name || ''));
                b.addEventListener('click', () => { if (editing) choose(p.id); else once(b, () => apply(p.id)); });
                return b;
            }));
        }
        editBox.hidden = !editing;
        const hit = ps.find(p => p.id === pick);
        tools.hidden = !hit;
        hint.textContent = hit ? (ps.indexOf(hit) + 1) + '번 단계 — 고칠 것을 누르세요'
            : (ps.length ? '고칠 단계를 위 순서표에서 누르세요' : '순서표가 비어 있어요');
        if (hit) setVal(eName, hit.name || '');
        eDel.textContent = delArmed ? '🗑 정말 지울까요? 한 번 더' : '🗑 지우기';
        eOver.textContent = overArmed ? '📸 한 번 더 누르면 덮어써요' : '📸 지금 화면으로 바꾸기';
        eOver.classList.toggle('pri', !!overArmed);
    }
    return { el, render: () => paint(false) };
}
