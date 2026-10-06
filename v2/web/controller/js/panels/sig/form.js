/* ✏️ 시그니처 등록 · 고치기 창 — 화면 위에 덮이는 판(폰에서는 화면 가득).

   새로: POST /api/signatures/add        form: title, amount, duration, image?, sound?, allow_dup?
   고치기: POST /api/signatures/update/{id} form: title?, amount?, duration?, image?, sound?, allow_dup? (바꿀 파일만 고른다)
   지우기(고치기 창 맨 아래): 확인 상자 → POST /api/signatures/delete/{id} — 행만 지우고 파일은 남긴다(되살리기 가능)
   방송에 틀기: POST /api/signature/play {sig_id, name:'수동송출'} — 옛 관리 화면의 [송출] 과 같다

   옛 규칙(upload.html · 후원 콘솔 시그니처 관리)
     - 금액은 꼭(0보다 크게). 제목이 비면 서버가 '10,000원 시그니처' 로 붙인다.
     - 새로 등록할 때는 사진이나 음원 중 하나는 있어야 한다.
     - 재생 시간은 음원이 없을 때 사진을 몇 초 보여 줄지 — 음원이 있으면 노래 길이만큼 나온다.
   더한 것
     - 같은 금액이 이미 있으면 적는 동안 알려 주고, 저장할 때 한 번 더 묻는다(서버 409 code:'dup' → allow_dup).
     - 제일 싼 시그니처보다 싸게 넣으면 '최저선이 내려간다' 고 알려 준다(그 금액 이상 후원부터 시그니처가 나간다).
     - 고른 사진 · 음원을 저장 전에 미리 보고 · 들어 본다(이 컴퓨터에서만 — 방송에는 안 나간다).
   ⚠️ 올리는 동안에는 닫기 · 저장을 막는다(반쯤 올라간 채 닫으면 무엇이 저장됐는지 모른다). */
import { h, num, parseWon, checkImage, checkSound, mb, call, upload, once, onEnter, label,
         MAX_MB, DUR_MIN, DUR_MAX, DUR_DEFAULT } from './common.js';

export function openForm(ctx, { sig = null, list = [], floor = 0, onDone } = {}) {
    const isEdit = !!sig;
    let busy = false, closed = false;
    const urls = [];                                  // 미리 보기용 임시 주소 — 닫을 때 놓아준다

    /* ── 칸 ── */
    const titleIn = h('input', { type: 'text', maxlength: '60', autocomplete: 'off', placeholder: '예: 사쿠란보 · 제로투', 'aria-label': '시그니처 제목' });
    const amtIn = h('input', { type: 'text', inputmode: 'numeric', autocomplete: 'off', placeholder: '예: 20,005', class: 'sg-amtin', 'aria-label': '후원 금액(원)' });
    const durIn = h('input', { type: 'text', inputmode: 'numeric', autocomplete: 'off', class: 'sg-dur', 'aria-label': '재생 시간(초)' });
    const amtNote = h('p', { class: 'sg-note', 'aria-live': 'polite', hidden: true });

    const imgFile = h('input', { type: 'file', accept: 'image/*', class: 'sg-file' });
    const sndFile = h('input', { type: 'file', accept: 'audio/*,video/mp4,.mp3,.m4a,.wav,.ogg,.aac', class: 'sg-file' });
    const imgPrev = h('img', { alt: '', class: 'sg-pick-img', hidden: true });
    const imgEmpty = h('span', { class: 'sg-pick-ic', 'aria-hidden': 'true' }, '🖼️');
    const imgName = h('span', { class: 'sg-pick-name' });
    const sndPrev = h('audio', { controls: true, preload: 'none', class: 'sg-audio', hidden: true });
    const sndName = h('span', { class: 'sg-pick-name' });
    const imgClear = h('button', { type: 'button', class: 'sg-mini', hidden: true, 'aria-label': '고른 사진 빼기' }, '✕');
    const sndClear = h('button', { type: 'button', class: 'sg-mini', hidden: true, 'aria-label': '고른 음원 빼기' }, '✕');

    const msg = h('p', { class: 'sg-msg', 'aria-live': 'polite', hidden: true });
    const saveBtn = h('button', { type: 'button', class: 'btn pri big sg-save' }, isEdit ? '저장' : '등록하기');
    const cancelBtn = h('button', { type: 'button', class: 'btn big' }, '닫기');
    const xBtn = h('button', { type: 'button', class: 'icon-btn sg-x', 'aria-label': '닫기' }, '×');

    const playBtn = isEdit ? h('button', { type: 'button', class: 'btn sm' }, '📺 방송에 틀기') : null;
    const delBtn = isEdit ? h('button', { type: 'button', class: 'btn sm ghost-danger' }, '🗑 지우기') : null;

    /* ── 판 ── */
    const head = h('div', { class: 'sg-sheet-head' },
        h('h2', { id: 'sg-sheet-t' }, isEdit ? '✏️ 시그니처 고치기' : '＋ 새 시그니처'),
        isEdit ? h('span', { class: 'tag plain' }, '#' + sig.id) : null, xBtn);
    const imgZone = h('label', { class: 'sg-pick' },
        h('span', { class: 'sg-pick-box' }, imgPrev, imgEmpty),
        h('span', { class: 'sg-pick-t' }, h('b', null, '사진 · 움짤'), imgName), imgFile);
    const sndZone = h('label', { class: 'sg-pick' },
        h('span', { class: 'sg-pick-box' }, h('span', { class: 'sg-pick-ic', 'aria-hidden': 'true' }, '🎵')),
        h('span', { class: 'sg-pick-t' }, h('b', null, '음원'), sndName), sndFile);
    const body = h('div', { class: 'sg-sheet-body' },
        h('label', { class: 'sg-field' }, h('span', null, '제목'), titleIn),
        h('div', { class: 'sg-row2' },
            h('label', { class: 'sg-field grow' }, h('span', null, '후원 금액 (원) ', h('em', null, '꼭')), amtIn),
            h('label', { class: 'sg-field' }, h('span', null, '재생 시간 (초)'), durIn)),
        amtNote,
        h('p', { class: 'sg-hint' }, '재생 시간은 ', h('b', null, '음원이 없을 때'), ' 사진을 몇 초 보여 줄지예요. 음원이 있으면 노래 길이만큼 나와요.'),
        h('div', { class: 'sg-picks' },
            h('div', { class: 'sg-pickrow' }, imgZone, imgClear),
            h('div', { class: 'sg-pickrow' }, sndZone, sndClear),
            sndPrev),
        h('p', { class: 'sg-hint' }, isEdit ? '사진 · 음원은 바꿀 때만 고르세요. 바꿔도 옛 파일은 남겨 두어 [최근 바뀐 것]에서 되돌릴 수 있어요.'
            : '사진이나 음원 중 하나는 꼭 골라 주세요. 사진은 작게 줄여 올리고, 움짤(GIF)은 그대로 올려요.'),
        msg);
    const foot = h('div', { class: 'sg-sheet-foot' }, cancelBtn, saveBtn);
    const extra = isEdit ? h('div', { class: 'sg-sheet-extra' }, playBtn, delBtn) : null;
    const card = h('div', { class: 'sg-sheet', role: 'dialog', 'aria-modal': 'true', 'aria-labelledby': 'sg-sheet-t' }, head, body, extra, foot);
    const wrap = h('div', { class: 'sg-sheet-wrap' }, card);

    /* ── 처음 값 ── */
    titleIn.value = isEdit ? (sig.title || '') : '';
    amtIn.value = isEdit && sig.amount ? num(sig.amount) : '';
    durIn.value = String(isEdit ? (sig.duration || DUR_DEFAULT) : DUR_DEFAULT);
    setPicked('img', null);
    setPicked('snd', null);

    function setPicked(kind, f) {
        if (kind === 'img') {
            const cur = isEdit ? sig.image_url : '';
            const src = f ? keep(URL.createObjectURL(f)) : cur;
            imgPrev.hidden = !src;
            imgEmpty.hidden = !!src;
            if (src) imgPrev.src = src; else imgPrev.removeAttribute('src');
            imgName.textContent = f ? `${f.name} (${mb(f.size)}) — 새로 고름` : (cur ? '등록됨 · 바꿀 때만 고르세요' : '눌러서 고르기 (png · jpg · gif)');
            imgName.classList.toggle('new', !!f);
            imgClear.hidden = !f;
        } else {
            const cur = isEdit ? sig.sound_url : '';
            const src = f ? keep(URL.createObjectURL(f)) : cur;
            sndPrev.hidden = !src;
            if (src) sndPrev.src = src; else sndPrev.removeAttribute('src');
            sndName.textContent = f ? `${f.name} (${mb(f.size)}) — 새로 고름` : (cur ? '등록됨 · 바꿀 때만 고르세요' : '눌러서 고르기 (mp3 · m4a · wav)');
            sndName.classList.toggle('new', !!f);
            sndClear.hidden = !f;
        }
    }
    function keep(u) { urls.push(u); return u; }

    imgFile.addEventListener('change', () => {
        const f = imgFile.files && imgFile.files[0];
        const why = checkImage(f);
        if (why) { imgFile.value = ''; say(why, 'bad'); setPicked('img', null); return; }
        say('');
        setPicked('img', f || null);
    });
    sndFile.addEventListener('change', () => {
        const f = sndFile.files && sndFile.files[0];
        const why = checkSound(f);
        if (why) { sndFile.value = ''; say(why, 'bad'); setPicked('snd', null); return; }
        say('');
        setPicked('snd', f || null);
    });
    imgClear.addEventListener('click', () => { imgFile.value = ''; setPicked('img', null); });
    sndClear.addEventListener('click', () => { sndFile.value = ''; setPicked('snd', null); });

    /* ── 금액 살피기 — 같은 금액 · 최저선 ── */
    function amountNote() {
        const a = parseWon(amtIn.value);
        const parts = [];
        let cls = 'sg-note';
        if (amtIn.value.trim() && a == null) { parts.push('금액은 원 단위 숫자로 적어 주세요'); cls += ' bad'; }
        else if (a > 0) {
            const dup = list.filter(s => Number(s.amount) === a && (!isEdit || String(s.id) !== String(sig.id)));
            if (dup.length) { parts.push(`⚠️ 같은 금액이 이미 있어요 — ${dup.slice(0, 2).map(label).join(', ')}. 자동으로는 둘 중 하나만 나가요.`); cls += ' warn'; }
            const others = list.filter(s => !isEdit || String(s.id) !== String(sig.id)).map(s => Number(s.amount) || 0).filter(x => x > 0);
            const cheapest = others.length ? Math.min(...others) : 0;
            if (floor > 0 && a < floor && (!cheapest || a < cheapest)) {
                parts.push(`💡 지금 제일 싼 시그니처보다 싸요 — 저장하면 ${num(a)}원 이상 후원부터 시그니처가 나가요 (지금은 ${num(floor)}원부터).`);
                if (!cls.includes('warn')) cls += ' info';
            }
        }
        amtNote.className = cls;
        amtNote.textContent = parts.join(' ');
        amtNote.hidden = !parts.length;
    }
    amtIn.addEventListener('input', amountNote);
    amtIn.addEventListener('blur', () => { const v = parseWon(amtIn.value); if (v != null && v > 0) amtIn.value = num(v); });
    amountNote();

    function say(text, kind) {
        msg.textContent = text || '';
        msg.className = 'sg-msg' + (kind ? ' ' + kind : '');
        msg.hidden = !text;
    }

    /* ── 저장 ── */
    async function save(allowDup) {
        if (busy) return;
        const amount = parseWon(amtIn.value);
        const dur = parseInt(String(durIn.value).trim(), 10);
        const img = imgFile.files && imgFile.files[0];
        const snd = sndFile.files && sndFile.files[0];
        amtIn.removeAttribute('aria-invalid');
        durIn.removeAttribute('aria-invalid');
        if (!amount || amount <= 0) { amtIn.setAttribute('aria-invalid', 'true'); say('후원 금액을 입력해 주세요', 'bad'); amtIn.focus(); return; }
        if (!(dur >= DUR_MIN && dur <= DUR_MAX)) { durIn.setAttribute('aria-invalid', 'true'); say(`재생 시간은 ${DUR_MIN}~${DUR_MAX}초로 넣어 주세요`, 'bad'); durIn.focus(); return; }
        if (!isEdit && !img && !snd) { say('사진이나 음원 중 하나는 등록해 주세요', 'bad'); return; }
        const why = checkImage(img) || checkSound(snd);
        if (why) { say(why, 'bad'); return; }
        const total = (img ? img.size : 0) + (snd ? snd.size : 0);
        if (total > MAX_MB * 1024 * 1024) { say(`파일이 너무 커요 (${mb(total)}) — 한 번에 ${MAX_MB}MB 까지`, 'bad'); return; }

        const fd = new FormData();
        fd.append('title', titleIn.value.trim());
        fd.append('amount', String(amount));
        fd.append('duration', String(dur));
        if (img) fd.append('image', img);
        if (snd) fd.append('sound', snd);
        if (allowDup) fd.append('allow_dup', '1');

        busy = true;
        lock(true);
        say(total ? `올리는 중… (${mb(total)})` : '저장하는 중…');
        const path = isEdit ? `/api/signatures/update/${encodeURIComponent(sig.id)}` : '/api/signatures/add';
        const r = await upload(path, fd, p => say(p < 100 ? `올리는 중… ${p}%` : '보관소에 저장하는 중…'));
        busy = false;
        lock(false);
        if (r.ok) {
            const s = r.data.signature || {};
            ctx.toast(isEdit ? (r.data.message === '변경 사항이 없습니다.' ? '바뀐 것이 없어요' : `저장했어요 — ${label(s)}`) : `등록했어요 — ${label(s)}`, 'ok');
            close();
            if (onDone) onDone(r.data);
            return;
        }
        if (r.status === 409 && r.data.code === 'dup') {
            say('');
            const ok = await ctx.confirm({
                title: '같은 금액의 시그니처가 있어요',
                body: `${(r.data.dup || []).slice(0, 3).map(label).join('\n')}\n\n같은 금액이면 후원이 왔을 때 자동으로는 하나만 나가요. 그래도 저장할까요?`,
                ok: '그래도 저장', cancel: '금액 고치기', danger: false,
            });
            if (ok) return save(true);
            amtIn.focus();
            return;
        }
        say(r.error, 'bad');
    }

    function lock(on) {
        [saveBtn, cancelBtn, xBtn, titleIn, amtIn, durIn, imgFile, sndFile, playBtn, delBtn].forEach(x => { if (x) x.disabled = on; });
        saveBtn.textContent = on ? '보내는 중…' : (isEdit ? '저장' : '등록하기');
        card.classList.toggle('busy', on);
    }

    /* ── 고치기 창에서만: 방송에 틀기 · 지우기 ── */
    async function playNow() {
        const r = await call('/api/signature/play', { sig_id: sig.id, name: '수동송출' });
        if (r.ok) ctx.toast(`📺 방송에 틀었어요 — ${sig.title || '시그니처'}`, 'ok');
        else ctx.toast('틀지 못했어요: ' + r.error, 'err');
    }
    async function del() {
        const ok = await ctx.confirm({
            title: `'${sig.title || '시그니처'}' 를 지울까요?`,
            body: `${label(sig)}\n\n후원 매칭 목록에서 바로 빠져요 — 방송에도 바로 반영돼요.\n사진 · 음원 파일은 보관소에 남겨 두고, [최근 바뀐 것]에서 되살릴 수 있어요.`,
            ok: '지우기', cancel: '그대로 두기',
        });
        if (!ok) return;
        busy = true;
        lock(true);
        say('지우는 중…');
        const r = await call(`/api/signatures/delete/${encodeURIComponent(sig.id)}`, {});
        busy = false;
        lock(false);
        if (r.ok) {
            ctx.toast(`지웠어요 — ${label(sig)} ([최근 바뀐 것]에서 되살릴 수 있어요)`, 'info', 6000);
            close();
            if (onDone) onDone(r.data);
        } else say('지우지 못했어요 — ' + r.error, 'bad');
    }
    if (playBtn) playBtn.addEventListener('click', () => once(playBtn, playNow));
    if (delBtn) delBtn.addEventListener('click', () => once(delBtn, del));

    /* ── 열고 닫기 ── */
    function close() {
        if (closed) return;
        closed = true;
        document.removeEventListener('keydown', onKey, true);
        try { sndPrev.pause(); } catch (e) { /* 무시 */ }
        urls.forEach(u => URL.revokeObjectURL(u));
        wrap.remove();
        document.body.classList.remove('sg-open');
    }
    function tryClose() { if (!busy) close(); }
    function onKey(e) {
        if (e.key === 'Escape' && !document.querySelector('.modal-wrap')) { e.preventDefault(); tryClose(); }
    }
    saveBtn.addEventListener('click', () => once(saveBtn, () => save(false)));
    cancelBtn.addEventListener('click', tryClose);
    xBtn.addEventListener('click', tryClose);
    wrap.addEventListener('click', e => { if (e.target === wrap) tryClose(); });
    [titleIn, amtIn, durIn].forEach(i => onEnter(i, () => once(saveBtn, () => save(false))));
    document.addEventListener('keydown', onKey, true);
    document.body.append(wrap);
    document.body.classList.add('sg-open');
    // 폰(손가락)에서는 바로 자판이 올라와 판을 가리므로 마우스일 때만 칸에 커서를 둔다
    if (window.matchMedia && matchMedia('(pointer: fine)').matches) setTimeout(() => (isEdit ? titleIn : amtIn).focus({ preventScroll: true }), 30);
    return { close };
}

