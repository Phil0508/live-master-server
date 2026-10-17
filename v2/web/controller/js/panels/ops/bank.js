/* 🏦 후원 콘솔 '계좌 입금 추천' 칸 — 옛 manual_send.html #bank-box(10-13 ~ 10-16)를 옮겼다.
   은행 확장 · 폰 앱이 잡은 입금이 카드로 뜬다. ⚠️ 송출은 안 한다 — [채우기] 로 아래 칸을 채우면 대표님이 보고 고쳐서 [송출].
   대표님 10-13: "바로 다 송출하면 누가 누구인지 · 누구 플러스인지 모른다". 배정은 지금처럼 대기함에서 — '＋?' 는 예상만.
   메모를 닉네임 · 할 말로 나눈 건 추천이라 원래 메모를 늘 같이 보여준다. 실명이 들어 있어 로그인한 이 화면만 읽는다.

   서버: GET /api/bank/inbox · POST /api/bank/inbox/{id}/{used|dismiss|restore} · GET /api/bank/key · POST /api/bank/key/reset
   언제 다시 읽나: 비공개 조각 bank.ver 가 바뀔 때(새 입금 · 예상 끝 · 다른 화면에서 처리) + 이 탭이 보이는 동안 4초마다(연결 상태 글자).
   송출은 후원 콘솔(console.js)이 한다 — 여기는 칸을 채우고(fill), 송출이 끝나면 '씀' 표시만(used).
   ⚠️ 이 파일은 /api/donation 을 부르지 않는다(스스로 송출하는 길이 없다). */
import { h, num, api, fill as fillEl } from './common.js';
import { cardView, linkChip, makePick, bankAgo } from '../../bankcore.js';

export { bankBadge } from '../../bankcore.js';

/** form: {amtIn, nameIn, msgIn, cntIn, ledger, onFill()} — 후원 콘솔의 칸들 */
export function mountBankBox(ctx, form) {
    let BANK = { items: [], hidden: [], link: {}, key_set: false, key_tail: '' };
    let sig = '', loaded = false, loading = false, seenVer = null, keyFull = '';
    const P = makePick();

    const link = h('span', { class: 'bank-link' }, '불러오는 중…');
    const hiddenBtn = h('button', { type: 'button', class: 'bank-tool', hidden: true }, '숨긴 입금');
    const setupBtn = h('button', { type: 'button', class: 'bank-tool' }, '⚙ 은행 확장 연결');
    const keyCode = h('code', { class: 'bank-key' }, '••••••••');
    const keyShow = h('button', { type: 'button', class: 'bank-tool' }, '보기');
    const keyCopy = h('button', { type: 'button', class: 'bank-tool' }, '복사');
    const keyNew = h('button', { type: 'button', class: 'bank-tool' }, '새 열쇠');
    const keyMsg = h('p', { class: 'ops-hint', hidden: true });
    const setup = h('div', { class: 'bank-setup', hidden: true },
        h('p', null, '크롬의 ', h('b', null, '엔젤 입금확인'), ' 상자에 있는 ', h('b', null, '열쇠'),
            ' 칸에 아래 열쇠를 붙여 넣으세요. 이 열쇠로는 이 칸에 추천 카드만 만들 수 있어요(송출 · 점수는 여기서 눌러야 가요).'),
        h('div', { class: 'bank-key-row' }, keyCode, keyShow, keyCopy, keyNew),
        keyMsg,
        h('p', null, '📱 폰(공기계) 앱도 같은 열쇠를 써요 — ', h('a', { href: '/download/bankphone.apk', class: 'bank-a' }, '폰 앱 받기(APK)'),
            " · QR 은 🖥️ 시스템 탭 → '폰 입금알림 앱'"));
    const list = h('div', { class: 'bank-list' }, h('div', { class: 'bank-empty' }, '불러오는 중…'));
    const hidList = h('div', { class: 'bank-list' });
    const hid = h('div', { class: 'bank-hidden', hidden: true }, hidList);
    const el = h('section', { class: 'ops-blk bank', 'aria-label': '계좌 입금 추천' },
        h('div', { class: 'bank-head' }, h('h3', null, '🏦 계좌 입금 추천'), link, h('span', { class: 'sp' }), hiddenBtn, setupBtn),
        setup, list, hid);

    // [채우기] 뒤 송출 칸 아래에 붙는 알림 — '🏦 계좌 입금에서 채움 — 50,000원 · 송출하면 추천 칸에서 빠져요 [비우기]'
    const pickText = h('span');
    const pickClear = h('button', { type: 'button', class: 'bank-tool sm' }, '비우기');
    const note = h('div', { class: 'bank-pick-note', hidden: true, 'aria-live': 'polite' }, pickText, pickClear);

    function setLedger(v) {
        if (v === null || v === undefined) return;
        if (form.ledger.checked !== !!v) {
            form.ledger.checked = !!v;
            form.ledger.dispatchEvent(new Event('change'));
        }
    }

    function card(it, hidden) {
        const v = cardView(it, Date.now() / 1000);
        const picked = P.get() && P.get().id === it.id;
        return h('div', { class: 'bank-card' + (picked ? ' picked' : ''), 'data-id': it.id },
            h('div', { class: 'bk-top' }, h('span', { class: 'bk-amt' }, num(v.amount) + '원'),
                h('span', { class: 'bk-time' }, v.clock ? v.clock + ' · ' : '', h('span', { class: 'bk-ago', 'data-at': String(Number(it.at) || 0) }, v.ago),
                    v.phone ? ' · 폰' : '')),
            h('div', { class: 'bk-sug' }, v.name ? h('span', { class: 'bk-name' }, v.name) : h('span', { class: 'bk-name none' }, '닉네임 없음'),
                v.message ? h('span', { class: 'bk-msg' }, v.message) : null),
            h('div', { class: 'bk-meta' }, v.how ? h('span', { class: 'bk-how ' + v.how.cls }, v.how.text) : null,
                v.target ? h('span', { class: 'bk-tgt', title: v.target.title || null }, v.target.text) : null),
            v.raw ? h('div', { class: 'bk-raw' }, v.raw) : null,
            h('div', { class: 'bk-btns' }, hidden
                ? h('button', { type: 'button', class: 'bk-back', 'data-act': 'restore' }, '되살리기')
                : [h('button', { type: 'button', class: 'bk-fill', 'data-act': 'fill' }, '⬇ 채우기'),
                   h('button', { type: 'button', class: 'bk-hide', 'data-act': 'dismiss' }, '숨기기')]));
    }

    function paintNote() {
        const p = P.get();
        note.hidden = !p;
        form.nameIn.placeholder = p ? "비우면 '익명'" : "비우면 '수동송출'";
        if (p) pickText.textContent = '🏦 계좌 입금에서 채움 — ' + num(p.amount) + '원 · 송출하면 추천 칸에서 빠져요';
    }

    function paint(force) {
        const c = linkChip(BANK);
        link.className = 'bank-link' + (c.cls ? ' ' + c.cls : '');
        link.textContent = c.text;
        hiddenBtn.hidden = !BANK.hidden.length;
        hiddenBtn.textContent = '숨긴 입금 ' + BANK.hidden.length;
        // ⚠️ 목록은 내용이 바뀔 때만 다시 그린다 — 통째로 다시 그리면 누르려던 단추가 그 사이에 바뀐다.
        //    '3분 전' 같은 시각 글자는 그 자리에서만 고친다.
        el.querySelectorAll('.bk-ago').forEach(x => { x.textContent = bankAgo(Date.now() / 1000 - Number(x.dataset.at || 0)); });
        const s = JSON.stringify([BANK.items, BANK.hidden, P.get() && P.get().id]);
        if (!force && s === sig) return;
        sig = s;
        fillEl(list, BANK.items.length ? BANK.items.map(it => card(it, false))
            : h('div', { class: 'bank-empty' }, '아직 들어온 계좌 입금이 없어요. 은행 확장이 30초마다 확인해서, 새 입금이 오면 여기 카드로 떠요.'));
        fillEl(hidList, BANK.hidden.map(it => card(it, true)));
        if (!BANK.hidden.length) hid.hidden = true;
        paintNote();
    }

    async function load() {
        if (loading) return;
        loading = true;
        const r = await api('/api/bank/inbox');
        loading = false;
        if (!r.ok) {
            link.className = 'bank-link';
            link.textContent = r.status ? '추천 목록을 못 읽었어요 (HTTP ' + r.status + ')' : '서버에 연결하지 못했어요';
            return;
        }
        const d = r.data;
        loaded = true;
        BANK = { items: d.items || [], hidden: d.hidden || [], link: d.link || {}, key_set: !!d.key_set, key_tail: d.key_tail || '' };
        if (!keyFull) keyCode.textContent = BANK.key_tail || '(열쇠 없음 — [보기] 를 누르면 만들어요)';
        setLedger(P.releaseIfGone(BANK.items.map(it => it.id)));          // 다른 화면에서 송출 · 숨김
        paint(false);
    }

    function fillFrom(id) {
        const it = BANK.items.find(x => x.id === id);
        if (!it) return;
        form.amtIn.value = num(it.amount);
        form.nameIn.value = it.name || '';
        form.msgIn.value = it.message || '';
        if (form.cntIn) form.cntIn.value = '1';
        setLedger(P.fill(it, form.ledger.checked));                       // 채우기 전 장부 체크를 기억해 둔다
        if (form.onFill) form.onFill();
        paint(true);
        try { form.nameIn.scrollIntoView({ behavior: 'smooth', block: 'center' }); } catch (e) { /* 옛 브라우저 */ }
        form.nameIn.focus();
        // 안내 글의 단추 이름 = 지금 아래 단추 글자(console.js preview — 장부에 넣기 켬이면 '장부에 넣고 송출', 끔이면 '시그니처 송출').
        //   ⚠️ 예전엔 늘 '[시그니처 송출]' 이라 했는데 채우면 장부에 넣기가 켜져 실제 단추는 '장부에 넣고 송출' 이었다(10-17)
        const btn = form.ledger.checked ? '장부에 넣고 송출' : '시그니처 송출';
        ctx.toast(it.name ? `채웠어요 — 확인하고 [${btn}]` : `채웠어요 — 닉네임을 적고 [${btn}]`, 'info');
    }

    async function act(id, a) {
        const r = await api('/api/bank/inbox/' + encodeURIComponent(id) + '/' + a, {});
        if (!r.ok) { ctx.toast(r.status ? '처리하지 못했어요 (HTTP ' + r.status + ')' : '서버에 연결하지 못했어요', 'err'); return; }
        if (a === 'dismiss') {
            setLedger(P.releaseIf(id));
            ctx.toast('숨겼어요 — [숨긴 입금]에서 되살릴 수 있어요', 'info');
        }
        if (a === 'restore') ctx.toast('되살렸어요', 'ok');
        load();
    }

    list.addEventListener('click', e => {
        const b = e.target.closest('button[data-act]');
        if (!b) return;
        const id = b.closest('.bank-card').dataset.id;
        if (b.dataset.act === 'fill') fillFrom(id); else act(id, b.dataset.act);
    });
    hidList.addEventListener('click', e => {
        const b = e.target.closest('button[data-act]');
        if (b) act(b.closest('.bank-card').dataset.id, b.dataset.act);
    });
    hiddenBtn.addEventListener('click', () => { hid.hidden = !hid.hidden; });
    setupBtn.addEventListener('click', () => { setup.hidden = !setup.hidden; });

    /* ── 열쇠 — 처음엔 끝 네 글자만(조종실 화면이 방송에 잡혀도 새지 않게). [보기] · [복사] 때만 통째로 받는다 ── */
    async function getKey() {
        if (keyFull) return keyFull;
        const r = await api('/api/bank/key');
        if (!r.ok) {
            keyMsg.hidden = false;
            keyMsg.className = 'ops-hint bad';
            keyMsg.textContent = r.error;
            return '';
        }
        keyFull = r.data.key || '';
        keyMsg.hidden = r.data.from !== 'env';
        keyMsg.className = 'ops-hint';
        keyMsg.textContent = '이 열쇠는 서버 설정(LM2_BANK_KEY)에 들어 있어요 — 바꾸려면 서버 설정을 고쳐야 해요.';
        return keyFull;
    }
    keyShow.addEventListener('click', async () => {
        if (keyShow.dataset.on) { keyShow.dataset.on = ''; keyShow.textContent = '보기'; keyCode.textContent = BANK.key_tail || '••••'; return; }
        const k = await getKey();
        if (!k) return;
        keyCode.textContent = k;
        keyShow.dataset.on = '1';
        keyShow.textContent = '가리기';
        load();
    });
    keyCopy.addEventListener('click', async () => {
        const k = await getKey();
        if (!k) return;
        try {
            await navigator.clipboard.writeText(k);
            ctx.toast('열쇠를 복사했어요 — 은행 확장 상자에 붙여 넣으세요', 'ok');
        } catch (e) {
            keyCode.textContent = k;
            keyShow.dataset.on = '1';
            keyShow.textContent = '가리기';
            const sel = window.getSelection(), rg = document.createRange();
            rg.selectNodeContents(keyCode);
            sel.removeAllRanges();
            sel.addRange(rg);
            ctx.toast('열쇠를 골라 뒀어요 — Ctrl+C 로 복사하세요', 'info');
        }
    });
    keyNew.addEventListener('click', async () => {
        const ok = await ctx.confirm({ title: '새 열쇠를 만들까요?', ok: '새 열쇠 만들기', cancel: '그만두기',
            body: '지금 은행 확장 · 폰 앱에 넣어 둔 열쇠는 더 이상 안 통해서, 새 열쇠를 다시 붙여 넣어야 해요.' });
        if (!ok) return;
        const r = await api('/api/bank/key/reset', {});
        if (!r.ok) { ctx.toast(r.error || '만들지 못했어요', 'err', 8000); return; }
        keyFull = r.data.key || '';
        keyCode.textContent = keyFull;
        keyShow.dataset.on = '1';
        keyShow.textContent = '가리기';
        ctx.toast('새 열쇠를 만들었어요 — 은행 확장 · 폰 앱에 다시 붙여 넣으세요', 'ok', 6000);
        load();
    });
    // 비우기 — 카드에서 채운 칸을 비우고 그 입금과의 연결도 끊는다(입금 카드는 추천 칸에 그대로 남는다)
    pickClear.addEventListener('click', () => {
        setLedger(P.release());
        form.amtIn.value = '';
        form.nameIn.value = '';
        form.msgIn.value = '';
        if (form.onFill) form.onFill();
        paint(true);
    });

    // 이 탭이 보이는 동안만 4초마다(연결 상태 글자 · 다른 화면에서 처리한 것)
    const timer = setInterval(() => {
        if (!el.isConnected) { clearInterval(timer); return; }
        if (el.offsetParent && document.visibilityState === 'visible' && ctx.lm.authed) load();
    }, 4000);

    return {
        el,
        note,
        /** 지금 [채우기] 로 고른 입금 {id, amount, prevLedger} 또는 null */
        pick: () => P.get(),
        /** 송출이 끝났다 — 장부 체크를 되돌리고, 그 입금에 '씀' 표시(송출할 때 쓴 이름은 서버가 닉네임으로 기억) */
        async used(pick, name) {
            // 옛 bankMarkUsed 와 같다 — 송출이 끝나면 칸이 비워지므로, 그사이 다른 카드를 골랐어도 같이 놓는다
            //   (다른 카드는 '원래 장부 상태' 를 이어 받아 두었으므로 되돌리는 값은 같다)
            setLedger(P.release());
            paintNote();
            paint(true);
            await api('/api/bank/inbox/' + encodeURIComponent(pick.id) + '/used', { name });
            load();
        },
        render(slices) {
            const v = Number(((slices || {}).bank || {}).ver) || 0;
            if (!ctx.lm.authed) return;
            if (!loaded || (seenVer !== null && v !== seenVer)) load();
            seenVer = v;
        },
    };
}
