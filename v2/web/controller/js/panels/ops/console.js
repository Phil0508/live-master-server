/* 💸 후원 콘솔 — 옛 manual_send.html '수동 송출' · 조종실 오른쪽 '후원 콘솔'.
   [장부에 넣기] 켬 → POST /api/donation {name, amount, message, tx_id:'manual_<번호>[_i]'} × N번
                      실제 후원처럼 대기함 · 장부 · 후원 순위에 들어가고, 시그니처는 서버가 한 줄 ×N 으로 묶는다
   [장부에 넣기] 끔 → POST /api/signature/play {amount, name, message, count} — 시그니처만 튼다(장부 없음)
   미리보기: GET /api/signatures 로 어느 시그니처가 나갈지 — 서버와 같은 셈(그 금액 이상 중 제일 싼 것, 없으면 제일 비싼 것).
            제일 싼 시그니처(최대 1만 원)보다 적으면 시그니처 없이 화면에만(장부에 넣으면 대기함 + 소액 띠).
   ⚠️ 보내는 중에는 다시 못 보낸다(두 번 눌러 두 번 들어가는 사고).
   ⚠️ 장부 묶음이 중간에 실패하면 같은 내용으로 다시 누를 때 **같은 번호**를 쓴다 → 이미 들어간 것은 서버가 중복으로 거르고
      빠진 것만 들어간다(옛 manual_send 와 같다). 내용이 하나라도 다르면 새 번호.
   🏦 계좌 입금 추천 칸(bank.js)이 맨 위 — 카드 [채우기] → 여기서 보고 고쳐서 [송출]. 채운 송출은 tx_id 'manual_bank_<입금번호>'
      (두 번 눌러도 장부엔 한 번) · 이름을 비우면 '익명' · 끝나면 그 입금에 '씀' 표시 + '장부에 넣기' 를 채우기 전으로 되돌린다.
   🏦🐉 계좌 입금 대형 연출(10-24) — 계좌 카드에서 보낸 것만 첫 건에 bank_total(금액 × 건수) → 서버 cast.bank_fx 가
      50만 원↑ 🐉 용(+ 시그니처 동안 테두리) · 100만 원↑ 🛡 엔젤 방패를 그 시그니처 앞에 붙인다. 투네이션 · 손 송출은 안 붙는다.
   🏦 '이미 넣은 입금' 경고(대표님 10-17) — 채운 송출은 보내기 **전에** POST /api/bank/dupcheck 로 서버에 묻는다.
      같은 입금을 이미 송출했거나(장부 manual_bank_<번호> · 카드 '씀') 30분 안 같은 이름 · 같은 금액 장부 줄이 있거나
      '장부에 넣기' 를 끈 채 5만 원 이상이면 '그래도 보낼까요?' 를 한 번 묻는다. 막지는 않는다(묻는 길이 안 닿으면 그냥 보낸다).
   📦 미니(opts.mini — 오른쪽 칸 '후원 콘솔 미니' #con-mini · 폰 서랍 '시그 송출'): 같은 함수 · 같은 보내는 길.
      갤러리 · 긴 설명 · 계좌 입금 추천 칸은 안 그리고, 미리보기는 72px 사진만. [전체 열기] = 후원 콘솔 탭. */
import { h, num, won, sigOf, onEnter, once, api, parseWon, blockHead } from './common.js';
import { manWon } from '../../util.js';
import { mountBankBox } from './bank.js';
import { sendName, txBase } from '../../bankcore.js';

const SIG_ROUND_FLOOR = 10000;      // 서버 rules.SIG_ROUND_FLOOR — 최저선은 1만 원을 못 넘는다

// 미니에는 계좌 입금 추천 칸이 없다 — 같은 모양의 빈 상자(고른 입금 없음)
const NO_BANK = { el: null, note: null, pick: () => null, used() {}, render() {} };

export function mountConsole(el, ctx, opts = {}) {
    const mini = !!opts.mini;
    let sigs = null, sigErr = '', loading = false, sending = false, retry = null;

    const amtIn = h('input', { type: 'text', inputmode: 'numeric', autocomplete: 'off', placeholder: mini ? '금액(원)' : '10,000', 'aria-label': '후원 금액(원)', class: 'con-amt' });
    const nameIn = h('input', { type: 'text', maxlength: '20', autocomplete: 'off', placeholder: mini ? '후원자' : "비우면 '수동송출'", 'aria-label': '후원자 이름' });
    const msgIn = h('textarea', { rows: mini ? '1' : '2', maxlength: '120', placeholder: mini ? '메시지 (선택)' : '방송판에 함께 띄울 메시지 (선택)', 'aria-label': '후원 메시지', class: 'ops-ta' });
    const cntIn = h('input', { type: 'number', class: 'ops-num w-s', min: '1', max: '30', value: '1', inputmode: 'numeric', 'aria-label': '몇 번' });
    const ledger = h('input', { type: 'checkbox', class: mini ? 'sw' : null, 'aria-label': mini ? '장부에 넣기' : null });
    const info = h('p', { class: 'con-info', 'aria-live': 'polite' });
    const sendBtn = h('button', { type: 'button', class: mini ? 'btn pri con-send' : 'btn pri big wide con-send' }, '시그니처 송출');
    const pvImg = h('img', { alt: '', hidden: true, class: 'pv-img' });
    const pvEmpty = h('div', { class: 'pv-empty' }, mini ? '시그 사진' : '금액을 넣으면 나갈 시그니처가 여기에 보여요');
    const pvTitle = h('b', { class: 'pv-title' });
    const pvLine = h('p', { class: 'pv-line' });
    const pvMsg = h('p', { class: 'pv-msg', hidden: true });
    const gal = h('div', { class: 'con-gal' });
    const galHead = h('span', { class: 'ops-sub' });
    const reload = h('button', { type: 'button', class: 'ops-mini', title: '시그니처 목록 다시 받기', 'aria-label': '시그니처 목록 다시 받기', onclick: () => load(true) }, '↻');

    el.classList.add('ops', mini ? 'con-mini-box' : 'ops-console');
    // 🏦 계좌 입금 추천 — [채우기] 가 아래 칸을 채운다(송출은 아래 [송출] 단추만)
    const bank = mini ? NO_BANK : mountBankBox(ctx, { amtIn, nameIn, msgIn, cntIn, ledger, onFill: () => { retry = null; lastPv = ''; preview(); } });
    if (mini) el.append(
        h('div', { class: 'cm-head' },
            h('b', null, '💸 후원 콘솔'),
            h('span', { class: 'cm-sub' }, '놓친 후원 · 계좌 후원'),
            h('button', { type: 'button', class: 'btn xs cm-full', title: '계좌 입금 추천 · 빠른 선택이 있는 후원 콘솔 탭을 엽니다',
                onclick: () => { if (ctx.tabs) ctx.tabs.open('ops-console'); } }, '전체 열기')),
        h('div', { class: 'cm-grid' },
            h('div', { class: 'pv-imgwrap cm-pv' }, pvImg, pvEmpty),
            h('div', { class: 'cm-fields' }, amtIn, nameIn, msgIn)),
        h('div', { class: 'cm-foot' },
            h('label', { class: 'cm-ledger', title: '켜면 실제 후원처럼 대기함 · 장부 · 후원 순위에 들어가요. 끄면 시그니처만 틀어요.' }, ledger, h('span', null, '장부에 넣기')),
            h('label', { class: 'cm-cnt', title: '같은 시그니처를 여러 번 받았을 때' }, h('span', null, '×'), cntIn),
            sendBtn),
        info);
    else el.append(bank.el, h('div', { class: 'con-grid' },
        h('section', { class: 'ops-blk con-form' },
            blockHead('💸 후원 콘솔', '계좌 후원 · 놓친 후원을 손으로 넣어요'),
            h('label', { class: 'ops-field' }, h('span', null, '후원 금액 (원)'), amtIn),
            info,
            h('label', { class: 'ops-field' }, h('span', null, '후원자'), nameIn),
            h('label', { class: 'ops-field' }, h('span', null, '메시지 (선택)'), msgIn),
            h('div', { class: 'ops-row' }, h('span', { class: 'ops-lbl' }, '몇 번 ×'), cntIn,
                h('span', { class: 'ops-hint inline' }, '같은 시그니처를 여러 번 받았을 때')),
            h('label', { class: 'con-ledger' }, ledger, h('span', null, h('b', null, '장부에 넣기'),
                ' — 켜면 실제 후원처럼 대기함 · 장부 · 후원 순위에 들어가요. 끄면 시그니처만 틀어요.')),
            bank.note,
            sendBtn),
        h('section', { class: 'ops-blk con-pv' },
            h('div', { class: 'pv-card' }, h('span', { class: 'pv-badge' }, '미리보기'),
                h('div', { class: 'pv-imgwrap' }, pvImg, pvEmpty), pvTitle, pvLine, pvMsg),
            h('div', { class: 'ops-bh' }, h('h3', null, '빠른 선택'), galHead, reload),
            gal)));

    let seenVer = null;          // sig_admin.ver — 시그니처 관리가 바꾼 횟수
    /* ── 시그니처 목록 ── */
    async function load(force) {
        if (loading || (sigs && !force)) return;
        loading = true;
        galHead.textContent = '불러오는 중…';
        const r = await api('/api/signatures');
        loading = false;
        if (r.ok) {
            sigs = (r.data.signatures || []).filter(s => s && s.amount != null).sort((a, b) => (Number(a.amount) || 0) - (Number(b.amount) || 0));
            sigErr = '';
        } else {
            sigErr = r.error;
            if (!sigs) sigs = null;
        }
        paintGallery();
        preview();
    }
    function floor() {
        return sigs && sigs.length ? Math.min(Number(sigs[0].amount) || 0, SIG_ROUND_FLOOR) : 0;
    }
    function match(amount) {
        if (!sigs || !sigs.length || amount <= 0) return null;
        for (const s of sigs) if ((Number(s.amount) || 0) >= amount) return s;
        return sigs[sigs.length - 1];
    }
    function paintGallery() {
        if (!sigs) {
            galHead.textContent = sigErr ? '' : '불러오는 중…';
            gal.replaceChildren(h('p', { class: 'ops-hint bad' }, sigErr ? '시그니처 목록을 못 받았어요 — ' + sigErr + ' (↻ 로 다시)' : ''));
            return;
        }
        galHead.textContent = sigs.length + '개';
        if (!sigs.length) { gal.replaceChildren(h('p', { class: 'ops-hint' }, '등록된 시그니처가 없어요')); return; }
        gal.replaceChildren(...sigs.map(s => h('button', { type: 'button', class: 'con-sig', 'data-id': s.id, title: s.title || '',
            onclick: () => { amtIn.value = num(s.amount); preview(); amtIn.focus(); } },
            h('b', null, num(s.amount)), h('span', null, s.title || '시그니처'))));
    }

    /* ── 미리보기 ── */
    let lastPv = '';
    function preview() {
        const amount = parseWon(amtIn.value) || 0;
        const name = sendName(nameIn.value, bank.pick());
        const msg = msgIn.value.trim();
        const cnt = clampCount();
        const led = ledger.checked;
        const pvSig = sigOf(amount, name, msg, cnt, led, sigs ? sigs.length : -1, sigErr);
        if (pvSig === lastPv) return;
        lastPv = pvSig;
        const f = floor();
        const small = f > 0 && amount > 0 && amount < f;
        const sig = small ? null : match(amount);
        const max = sigs && sigs.length ? Number(sigs[sigs.length - 1].amount) || 0 : 0;
        const parts = [];
        let cls = 'con-info';
        if (amtIn.value.trim() && parseWon(amtIn.value) == null) { parts.push('금액은 원 단위 숫자로 적어 주세요'); cls += ' bad'; }
        else if (amount <= 0) parts.push('');
        else if (small) {
            cls += ' small';
            parts.push(led ? `💬 시그니처 없이 대기함 · 장부에 들어가고 방송판 소액 띠에 이름이 올라가요 — ${num(f)}원부터 시그니처`
                           : `💬 시그니처 없이 방송판 화면에만 떠요 — 1만 원 미만은 화면에만 (${num(f)}원부터 시그니처)`);
        } else if (mini && sig) parts.push(`${sig.title || '시그니처'} · ${num(sig.amount)}원${(Number(sig.amount) || 0) === amount ? '' : ' (올림)'}`);
        else if (!sigs) parts.push(sigErr ? '시그니처 목록을 못 받아 미리 못 봐요 — 보내면 서버가 고릅니다' : '시그니처 목록을 받는 중…');
        else if (!sig) { parts.push('나갈 시그니처가 없어요 — 서버도 못 찾으면 송출이 실패해요'); cls += ' bad'; }
        else if ((Number(sig.amount) || 0) === amount) { cls += ' exact'; parts.push(`✓ 정확히 일치 — ${sig.title || '시그니처'}`); }
        else if (amount > max) { cls += ' roundup'; parts.push(`↓ 제일 비싼 시그니처 ${num(sig.amount)}원 — ${sig.title || ''}`); }
        else { cls += ' roundup'; parts.push(`↑ 올림 → ${num(sig.amount)}원 시그니처 — ${sig.title || ''}`); }
        if (amount > 0 && led) parts.push(`대기함 카드 ${cnt > 1 ? cnt + '장 × ' : ''}${manWon(amount)}점`);
        if (amount > 0 && cnt > 1) parts.push(led ? `장부에 ${cnt}건 따로 · 시그니처는 한 줄 ×${cnt}` : `시그니처 한 줄 ×${cnt}`);
        info.className = cls;
        info.textContent = parts.filter(Boolean).join(' · ');

        if (sig && sig.image_url) { pvImg.src = sig.image_url; pvImg.hidden = false; pvEmpty.hidden = true; }
        else { pvImg.hidden = true; pvImg.removeAttribute('src'); pvEmpty.hidden = false; pvEmpty.textContent = mini ? (small ? '화면에만' : '시그 사진') : (small ? '시그니처 없음 — 화면에만' : '금액을 넣으면 나갈 시그니처가 여기에 보여요'); }
        pvTitle.textContent = sig ? `${sig.title || '시그니처'} · ${num(sig.amount)}원` : '';
        pvTitle.hidden = !sig;
        pvLine.replaceChildren(...(amount > 0 ? [h('b', null, name), '님이 ', h('b', { class: 'gold' }, num(amount) + '원'), ' 후원!' + (cnt > 1 ? ` ×${cnt}` : '')] : []));
        pvMsg.textContent = msg;
        pvMsg.hidden = !msg;
        gal.querySelectorAll('.con-sig').forEach(b => b.classList.toggle('on', !!sig && String(b.dataset.id) === String(sig.id)));
        sendBtn.textContent = sending ? sendBtn.textContent : (led ? '장부에 넣고 송출' : (mini ? '송출' : '시그니처 송출')) + (cnt > 1 ? ` ×${cnt}` : '');
    }
    function clampCount() {
        return Math.max(1, Math.min(30, parseInt(cntIn.value, 10) || 1));
    }
    [amtIn, nameIn, msgIn, cntIn].forEach(i => i.addEventListener('input', preview));
    ledger.addEventListener('change', preview);
    amtIn.addEventListener('blur', () => { const v = parseWon(amtIn.value); if (v != null && v > 0) amtIn.value = num(v); });

    /* ── 보내기 ── */
    async function send() {
        if (sending) return;
        const amount = parseWon(amtIn.value);
        if (!amount || amount <= 0) { ctx.toast('후원 금액을 원 단위 숫자로 넣어 주세요', 'err'); amtIn.focus(); return; }
        const pick = bank.pick();                       // 🏦 계좌 입금에서 채웠나
        const name = sendName(nameIn.value, pick);      // 채웠는데 이름을 비우면 '익명'
        const message = msgIn.value.trim();
        const cnt = clampCount();
        const led = ledger.checked;
        const key = sigOf(name, amount, message, cnt);
        const reuse = led && retry && retry.key === key;
        const stamp = reuse ? retry.stamp : Date.now();
        const base = txBase(pick, stamp);               // 계좌 입금에서 채운 것은 그 입금 번호 — 두 번 눌러도 장부엔 한 번
        // 🏦🐉 계좌 입금 대형 연출(10-24) — 계좌 카드를 채워 보낼 때만 첫 건에 합계(금액 × 건수). 금액 기준은 서버(cast.bank_fx)가 본다
        const bankTotal = pick ? amount * cnt : 0;
        const jobs = led
            ? Array.from({ length: cnt }, (_, i) => ['/api/donation', Object.assign({ name, amount, message, tx_id: base + (cnt > 1 ? '_' + (i + 1) : '') },
                i === 0 && bankTotal ? { bank_total: bankTotal } : {})])
            : [['/api/signature/play', Object.assign({ amount, name, message, count: cnt }, bankTotal ? { bank: 1, bank_total: bankTotal } : {})]];
        sending = true;
        sendBtn.disabled = true;
        // 🏦 계좌 입금에서 채운 송출 — 보내기 전에 '이미 넣은 입금' 인지 서버에 묻는다(빠진 것만 다시 넣는 재시도는 묻지 않는다)
        if (pick && !reuse) {
            const chk = await api('/api/bank/dupcheck', { id: pick.id, name, amount, ledger: led });
            const warns = chk.ok && Array.isArray(chk.data.warns) ? chk.data.warns.filter(w => w && w.text) : [];
            if (warns.length) {
                const dupish = warns.some(w => w.code !== 'no_ledger_big');
                const go = await ctx.confirm({
                    title: dupish ? '이미 넣은 것 같아요 — 그래도 보낼까요?' : "'장부에 넣기' 가 꺼져 있어요 — 그래도 보낼까요?",
                    body: warns.map(w => '· ' + w.text).join('\n') + `\n\n보낼 것: ${name} ${won(amount)}${cnt > 1 ? ' ×' + cnt : ''}${led ? ' (장부에 넣기)' : ' (시그니처만)'}`,
                    ok: '그래도 보내기', cancel: '안 보내기',
                });
                if (!go) {
                    sending = false;
                    sendBtn.disabled = false;
                    ctx.toast('안 보냈어요 — 칸은 그대로 두었어요', 'info');
                    return;
                }
            }
        }
        let okN = 0, lastErr = '', shownOnly = false, dup = 0;
        const nos = [];                                 // 🏷️ 장부 줄 번호(서버가 손 송출에만 돌려준다) — 토스트 끝에 작게 '#12'
        try {
            for (const [path, body] of jobs) {          // 차례로 — 한꺼번에 쏘면 순서가 섞여 대기줄에서 안 묶일 수 있다
                sendBtn.textContent = jobs.length > 1 ? `보내는 중… (${okN + 1}/${jobs.length})` : '보내는 중…';
                const r = await api(path, body);
                if (!r.ok) { lastErr = r.error; break; }
                okN++;
                if (r.data.display_only) shownOnly = true;
                if (/duplicate/i.test(String(r.data.message || ''))) dup++;
                if (r.data.no) nos.push(Number(r.data.no));
            }
        } finally {
            sending = false;
            sendBtn.disabled = false;
            lastPv = '';
            preview();
        }
        if (okN === jobs.length) {
            retry = null;
            const noTxt = nos.length ? (nos.length > 1 ? ` · 장부 #${nos[0]}~#${nos[nos.length - 1]}` : ` · 장부 #${nos[0]}`) : '';
            ctx.toast(pick && led && nos.length ? `✓ 계좌 입금 ${name} ${won(amount)}${cnt > 1 ? ' ×' + cnt : ''} — 장부 #${nos[0]}${nos.length > 1 ? '~#' + nos[nos.length - 1] : ''} 로 들어갔어요`
                : shownOnly ? (led ? `✓ ${name} ${won(amount)} — 대기함에 넣었어요 (시그니처 없음 · 소액)${noTxt}` : '✓ 방송판에 띄웠어요 (시그니처 없음 — 1만 원 미만은 화면에만)')
                : `✓ 송출했어요${cnt > 1 ? ' ×' + cnt : ''}${led ? ' (장부에 넣음' + (dup ? ` · ${dup}건은 이미 들어가 있어 건너뜀` : '') + noTxt + ')' : ''}`, 'ok');
            amtIn.value = ''; nameIn.value = ''; msgIn.value = ''; cntIn.value = '1';
            if (pick) bank.used(pick, name);            // 추천 칸에서 빼고 '장부에 넣기' 를 채우기 전으로
            lastPv = '';
            preview();
            amtIn.focus();
        } else {
            if (led) retry = { key, stamp };            // 칸은 그대로 — 그대로 다시 누르면 빠진 것만 들어간다
            ctx.toast(`송출 실패 (${okN}/${jobs.length}건 들어감)${led ? ' — 그대로 다시 누르면 빠진 것만 넣어요' : ''}: ${lastErr}`, 'err', 9000);
        }
    }
    sendBtn.addEventListener('click', () => once(sendBtn, send));
    [amtIn, nameIn, cntIn].forEach(i => onEnter(i, () => once(sendBtn, send)));
    // 메시지 칸은 여러 줄 — Ctrl/⌘+Enter 로 보낸다(그냥 Enter 는 줄바꿈)
    msgIn.addEventListener('keydown', e => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !e.isComposing && e.keyCode !== 229) { e.preventDefault(); once(sendBtn, send); }
    });

    paintGallery();
    preview();
    // 미니는 페이지를 열 때(로그인 전) 붙는다 — 로그인 전엔 묻지 않는다(401). 로그인되면 render 가 한 번 받는다
    if (!mini || ctx.lm.authed) load(false);
    let triedAuthed = mini ? false : !!ctx.lm.authed;
    return {
        // 서버 조각은 안 쓴다 — 목록은 열 때 한 번 받고 ↻ 로 다시.
        // 단, 로그인 전에 열려(첫 화면이 이 탭) 목록을 못 받았으면 로그인된 뒤 한 번만 다시 받는다
        render(slices) {
            try { bank.render(slices || ctx.slices); } catch (e) { console.error('[계좌 입금 추천]', e); }
            if (!sigs && !loading && !triedAuthed && ctx.lm.authed) { triedAuthed = true; load(true); }
            // 시그니처 관리에서 바꾸면(sig_admin.ver) 받아 둔 목록을 새로 받는다 — 새로 등록한 시그가 바로 미리보기에 잡히게
            const v = Number(((slices || ctx.slices || {}).sig_admin || {}).ver) || 0;
            if (seenVer !== null && v !== seenVer && sigs) load(true);
            seenVer = v;
        },
    };
}
