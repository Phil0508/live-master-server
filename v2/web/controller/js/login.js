/* 🔑 로그인 — 비밀번호 하나. 맞으면 서버가 쿠키를 주고, 다시 불러 새 연결(로그인된 연결)로 붙는다. */
export function mountLogin(root) {
    root.innerHTML = `
        <form class="card login-card" autocomplete="on">
            <span class="logo big" aria-hidden="true"></span>
            <h1>조종실 들어가기</h1>
            <p class="muted">방송 운영용 비밀번호를 넣어 주세요.</p>
            <label class="field"><span>비밀번호</span>
                <input type="password" name="password" autocomplete="current-password" required></label>
            <p class="form-err" role="alert" hidden></p>
            <button class="btn pri big wide" type="submit">들어가기</button>
        </form>`;
    const form = root.querySelector('form');
    const input = form.querySelector('input');
    const err = form.querySelector('.form-err');
    const btn = form.querySelector('button');
    let shown = false;

    form.addEventListener('submit', async e => {
        e.preventDefault();
        err.hidden = true;
        btn.disabled = true;
        btn.textContent = '확인하는 중…';
        try {
            const r = await fetch('/login', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ password: input.value }), credentials: 'same-origin',
            });
            const j = await r.json().catch(() => ({}));
            if (r.ok && j.ok) { location.reload(); return; }
            showErr(j.error || '들어가지 못했어요');
        } catch (x) {
            showErr('서버에 닿지 않아요 — 잠시 뒤 다시 눌러 주세요');
        }
        btn.disabled = false;
        btn.textContent = '들어가기';
    });

    function showErr(msg) {
        err.textContent = msg;
        err.hidden = false;
        input.select();
    }

    // 로그인 화면이 처음 보일 때 칸에 바로 커서
    new MutationObserver(() => {
        const on = document.body.dataset.view === 'login';
        if (on && !shown) setTimeout(() => input.focus(), 30);
        shown = on;
    }).observe(document.body, { attributes: true, attributeFilter: ['data-view'] });

    return { render() {} };
}
