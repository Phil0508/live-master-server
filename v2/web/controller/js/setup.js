/* 🎬 방송 전 — 오늘 나올 플레이어 이름(1~10명)을 적고 [방송 시작] → session.start {names}.
   - 지난번 이름을 이 컴퓨터에 기억해 두었다가 채워 준다(편의일 뿐 — 없어도 된다).
   - 서버가 거절하면(겹치는 이름 · 0명 · 11명 이상) 그 까닭을 단추 바로 위에 보여 준다.
   ⚠️ 방송을 시작하면 서버가 대기함을 비운다. 방송 전에 들어온 후원이 있으면 미리 알려 준다. */
import { h, won } from './util.js';

const MAX = 10;
const KEY = 'lm2_last_names';

function loadNames() {
    try {
        const v = JSON.parse(localStorage.getItem(KEY) || '[]');
        if (Array.isArray(v) && v.length) return v.slice(0, MAX).map(String);
    } catch (e) { /* 기억이 없거나 막혀 있다 — 빈 칸으로 */ }
    return ['', '', ''];
}

function saveNames(names) {
    try { localStorage.setItem(KEY, JSON.stringify(names)); } catch (e) { /* 무시 */ }
}

export function mountSetup(root, ctx) {
    root.innerHTML = `
        <form class="card setup-card" novalidate>
            <h1>방송 시작 준비</h1>
            <p class="muted">오늘 나올 플레이어 이름을 적어 주세요. 1명에서 10명까지 — 이 순서대로 점수판에 올라갑니다.</p>
            <div class="pre-pending" hidden></div>
            <ol class="name-list"></ol>
            <button class="btn add-name" type="button">＋ 한 명 더</button>
            <p class="form-err" role="alert" hidden></p>
            <button class="btn pri big wide start-btn" type="submit">방송 시작</button>
        </form>`;
    const form = root.querySelector('form');
    const list = root.querySelector('.name-list');
    const addBtn = root.querySelector('.add-name');
    const err = root.querySelector('.form-err');
    const startBtn = root.querySelector('.start-btn');
    const pre = root.querySelector('.pre-pending');

    function row(value) {
        const input = h('input', { type: 'text', maxlength: 20, placeholder: '플레이어 이름', autocomplete: 'off', enterkeyhint: 'next' });
        input.value = value || '';
        const del = h('button', { class: 'icon-btn', type: 'button', title: '이 칸 빼기', 'aria-label': '이 칸 빼기' }, '×');
        const li = h('li', { class: 'name-row' }, h('span', { class: 'n' }), input, del);
        del.addEventListener('click', () => {
            if (list.children.length <= 1) { input.value = ''; input.focus(); return; }
            li.remove();
            renumber();
        });
        input.addEventListener('keydown', e => {
            if (e.key !== 'Enter' || e.isComposing) return;
            e.preventDefault();
            const next = li.nextElementSibling;
            if (next) next.querySelector('input').focus();
            else if (list.children.length < MAX && input.value.trim()) addRow('', true);
            else startBtn.focus();
        });
        return li;
    }

    function addRow(value, focus) {
        if (list.children.length >= MAX) return;
        const li = row(value);
        list.append(li);
        renumber();
        if (focus) li.querySelector('input').focus();
    }

    function renumber() {
        [...list.children].forEach((li, i) => { li.querySelector('.n').textContent = (i + 1) + '.'; });
        addBtn.disabled = list.children.length >= MAX;
        addBtn.textContent = list.children.length >= MAX ? '10명까지예요' : '＋ 한 명 더';
    }

    loadNames().forEach(n => addRow(n));
    addBtn.addEventListener('click', () => addRow('', true));

    form.addEventListener('submit', async e => {
        e.preventDefault();
        err.hidden = true;
        const names = [...list.querySelectorAll('input')].map(i => i.value.trim().replace(/\s+/g, ' ')).filter(Boolean);
        // 서버도 검사하지만, 흔한 실수는 바로 알려 준다
        if (!names.length) return showErr('이름을 한 명 이상 적어 주세요');
        const dup = names.find((n, i) => names.indexOf(n) !== i);
        if (dup) return showErr(`'${dup}' 이(가) 두 번 적혀 있어요`);
        startBtn.disabled = true;
        startBtn.textContent = '시작하는 중…';
        const res = await ctx.run('session.start', { names }, { quiet: true });
        startBtn.disabled = false;
        startBtn.textContent = '방송 시작';
        if (!res.ok) return showErr(res.error || '시작하지 못했어요');
        saveNames(names);
        ctx.toast(`방송을 시작했어요 — 플레이어 ${names.length}명`, 'ok');
    });

    function showErr(msg) {
        err.textContent = msg;
        err.hidden = false;
    }

    return {
        render(slices) {
            const pend = slices.pending || [];
            pre.hidden = !pend.length;
            if (pend.length) {
                const total = pend.reduce((a, x) => a + (Number(x.amount) || 0), 0);
                pre.textContent = `방송 전에 들어온 후원이 ${pend.length}건(${won(total)}) 있어요. ` +
                    '방송을 시작하면 대기함이 비워집니다 — 후원 기록 장부에는 남아요.';
            }
        },
    };
}
