/* 🎞️ 고액 영상 · 🎤 노래방 — 방송판에 영상을 띄우는 것들(서버 media.py).
   고액 영상: 금액대(구간)마다 영상 하나. 운영자가 구간을 **골라서** 튼다(자동 매칭 없음 — 옛 것과 같다)
     ▶ 틀기 → acctvid.play {tier} (영상이 없으면 서버가 played:false · reason:'no_video')
     ■ 멈추기 → acctvid.stop
     주소 → acctvid.set {tier, video} — 유튜브 링크는 영상 번호(11자)로, 올린 파일 · 직접 주소는 그대로(옛 것과 같은 모양)
     ⬆ 파일 → POST /api/account/video/upload (form: tier, file) — mp4 · webm · mov · m4v, 60MB 까지
   노래방: karaoke.play {video: 유튜브 번호} · karaoke.stop · 🔊 영상 음량 karaoke.volume {volume 0~100}(옛 karaoke_volume, 기본 70 · 5씩)
     ⚠️ 음량 막대는 끄는 동안 초당 수십 번 바뀐다 — 글자는 바로, 서버에는 멈춘 뒤 0.15초에 한 번(옛 changeKaraokeVolume) */
import { h, sigOf, onEnter, setVal, once, isUrl, ytId, videoText, blockHead } from './common.js';

const VIDEO_MAX_MB = 60;
const VIDEO_EXT = ['mp4', 'webm', 'mov', 'm4v'];
const YT_HOST = /^https?:\/\/([a-z0-9-]+\.)*(youtube\.com|youtu\.be)\//i;

export function mountMedia(el, ctx) {
    /* ── 고액 영상 ── */
    const nowLine = h('p', { class: 'ops-now' });
    const stopBtn = h('button', { type: 'button', class: 'btn sm danger', onclick: () => once(stopBtn, stop) }, '■ 영상 멈추기');
    const rowsBox = h('div', { class: 'av-rows' });
    const upMsg = h('p', { class: 'ops-hint', 'aria-live': 'polite' });
    const file = h('input', { type: 'file', accept: 'video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov,.m4v', hidden: true });
    let upTier = -1, uploading = false;
    const rows = [];          // 구간 번호 → {play, input, badge, up, clear}

    /* ── 노래방 ── */
    const kState = h('p', { class: 'ops-now' });
    const kIn = h('input', { type: 'text', autocomplete: 'off', class: 'grow', placeholder: '유튜브 노래방(inst) 링크 — https://youtu.be/… 또는 watch?v=…', 'aria-label': '노래방 유튜브 링크' });
    const kPlay = h('button', { type: 'button', class: 'btn pri sm', onclick: () => once(kPlay, karaokeOn) }, '▶ 노래방 켜기');
    const kStop = h('button', { type: 'button', class: 'btn sm danger', onclick: () => once(kStop, karaokeOff) }, '■ 끄기');
    onEnter(kIn, () => once(kPlay, karaokeOn));
    const kVol = h('input', { type: 'range', min: '0', max: '100', step: '5', value: '70', class: 'gm-range', 'aria-label': '노래방 영상 음량' });
    const kVolTxt = h('b', { class: 'ops-dim', style: 'min-width:48px;text-align:right' }, '70%');
    let kVolTimer = 0, kVolPending = false;      // 보내는 중엔 서버 값으로 막대를 되돌리지 않는다(튀지 않게)
    kVol.addEventListener('input', () => {
        const v = Math.max(0, Math.min(100, parseInt(kVol.value, 10) || 0));
        kVolTxt.textContent = v + '%';
        kVolPending = true;
        clearTimeout(kVolTimer);
        kVolTimer = setTimeout(async () => {
            try { await ctx.run('karaoke.volume', { volume: v }); } finally { kVolPending = false; ctx.rerender(); }
        }, 150);
    });
    kVol.addEventListener('pointerup', () => setTimeout(() => kVol.blur(), 0));   // 놓은 뒤에는 서버 값이 다시 보이게

    el.classList.add('ops', 'ops-media');
    el.append(
        h('section', { class: 'ops-blk' }, blockHead('🏦 고액 후원 영상', '구간을 골라 직접 틀어요 — 칸에 링크를 붙이고 Enter 로 저장'),
            h('div', { class: 'ops-row wrap' }, nowLine, stopBtn),
            rowsBox, upMsg, file),
        h('section', { class: 'ops-blk' }, blockHead('🎤 노래방', '켜면 방송판에 유튜브 영상이 떠요'),
            kState, h('div', { class: 'ops-row wrap' }, kIn, kPlay, kStop),
            h('div', { class: 'ops-row' }, h('span', null, '🔊 영상 음량'), kVol, kVolTxt)),
    );

    async function play(i) {
        const t = (((ctx.slices.acct_video || {}).tiers) || [])[i] || {};
        const res = await ctx.run('acctvid.play', { tier: i });
        if (!res.ok) return;
        if (res.played) ctx.toast(`▶ ${res.label || t.label} 영상을 틀어요`, 'ok');
        else if (res.reason === 'no_video') ctx.toast(`${res.label || t.label} 구간에는 영상이 없어요 — 먼저 링크나 파일을 넣어 주세요`, 'err');
    }
    async function stop() {
        const res = await ctx.run('acctvid.stop', {});
        if (res.ok) ctx.toast('영상을 멈췄어요', 'info');
    }

    async function saveVideo(i, input) {
        const tiers = ((ctx.slices.acct_video || {}).tiers) || [];
        const t = tiers[i];
        if (!t) return;
        const raw = input.value.trim();
        let video;
        if (!raw) {
            if (!t.video) return;
            const ok = await ctx.confirm({ title: `${t.label} 영상을 지울까요?`, body: '이 구간은 영상 없이 남아요. 올린 파일이었다면 다시 올려야 해요.', ok: '지우기', cancel: '그대로 두기' });
            if (!ok) { input.value = videoText(t.video); return; }
            video = '';
        } else if (isUrl(raw) && !YT_HOST.test(raw)) {
            video = raw;                                   // 올린 파일 · 직접 영상 주소
        } else {
            // ⚠️ 유튜브 주소는 번호로 바꿔 저장한다 — 방송판은 http 로 시작하면 '파일' 로 틀어서(옛 overlay acctVideoIsFile)
            //    옛 조종실처럼 유튜브 주소를 그대로 저장하면 방송판에서 안 나온다.
            video = ytId(raw);
            if (!video) { input.setAttribute('aria-invalid', 'true'); ctx.toast(`${t.label}: 유튜브 링크를 알아보지 못했어요 — 주소를 확인해 주세요`, 'err'); return; }
        }
        input.removeAttribute('aria-invalid');
        if (video === (t.video || '')) { input.value = videoText(video); return; }
        const res = await ctx.run('acctvid.set', { tier: i, video });
        if (res.ok) { ctx.toast(video ? `${t.label} 영상을 저장했어요` : `${t.label} 영상을 지웠어요`, video ? 'ok' : 'info'); lastTiers = ''; ctx.rerender(); }
        else input.value = videoText(t.video);
    }

    function pick(i) {
        if (uploading) { ctx.toast('다른 영상을 올리는 중이에요 — 끝난 뒤에 다시 눌러 주세요', 'info'); return; }
        upTier = i;
        file.value = '';
        file.click();
    }
    file.addEventListener('change', () => {
        const f = file.files && file.files[0];
        if (f && upTier >= 0) upload(upTier, f);
    });

    function upload(i, f) {
        const t = (((ctx.slices.acct_video || {}).tiers) || [])[i] || { label: (i + 1) + '번 구간' };
        const ext = (f.name.split('.').pop() || '').toLowerCase();
        const mb = f.size / 1024 / 1024;
        if (!VIDEO_EXT.includes(ext)) { ctx.toast(`${ext || '?'} 형식은 못 올려요 (mp4 · webm · mov · m4v)`, 'err'); return; }
        if (mb > VIDEO_MAX_MB) { ctx.toast(`파일이 ${mb.toFixed(0)}MB 예요 — ${VIDEO_MAX_MB}MB 아래로 줄여 주세요`, 'err'); return; }
        uploading = true;
        paintUploading(i);
        upMsg.textContent = `${t.label} 구간에 올리는 중… (${mb.toFixed(1)}MB)`;
        // ⚠️ fetch 는 올리는 진행을 못 본다 — 60MB 는 오래 걸려 '멈췄나?' 싶다. XHR 로 몇 % 인지 보여 준다
        const fd = new FormData();
        fd.append('tier', String(i));
        fd.append('file', f);
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/account/video/upload');
        xhr.withCredentials = true;
        xhr.upload.onprogress = e => {
            if (!e.lengthComputable) return;
            const p = Math.round(e.loaded / e.total * 100);
            upMsg.textContent = p < 100 ? `${t.label} 구간에 올리는 중… ${p}%` : `${t.label} — 보관소에 저장하는 중…`;
        };
        const done = (ok, msg) => {
            uploading = false;
            upTier = -1;
            paintUploading(-1);
            upMsg.textContent = msg;
            upMsg.className = 'ops-hint ' + (ok ? 'good' : 'bad');
            ctx.toast(msg, ok ? 'ok' : 'err');
            lastTiers = '';
            ctx.rerender();
        };
        xhr.onload = () => {
            let d = {};
            try { d = JSON.parse(xhr.responseText || '{}'); } catch (e) { d = {}; }
            if (xhr.status >= 200 && xhr.status < 300 && (d.ok || d.status === 'success')) done(true, `${t.label} 영상을 올렸어요 (${d.size_mb != null ? d.size_mb : mb.toFixed(1)}MB) ✓`);
            else if (xhr.status === 401) done(false, '로그인이 풀렸어요 — 새로 고쳐 다시 들어가 주세요');
            else done(false, '올리지 못했어요 — ' + (d.message || d.error || ('HTTP ' + xhr.status)));
        };
        xhr.onerror = () => done(false, '올리지 못했어요 — 서버에 닿지 않아요');
        xhr.send(fd);
    }
    function paintUploading(i) {
        rows.forEach((r, k) => { r.up.disabled = uploading; r.up.textContent = k === i ? '올리는 중…' : '⬆ 파일'; });
    }

    function buildRows(tiers) {
        rows.length = 0;
        rowsBox.replaceChildren(...tiers.map((t, i) => {
            const playB = h('button', { type: 'button', class: 'btn sm av-play', title: `${t.label} 영상 틀기` }, '▶ ', t.label);
            playB.addEventListener('click', () => once(playB, () => play(i)));
            const input = h('input', { type: 'text', autocomplete: 'off', placeholder: '유튜브 링크 · 영상 주소 (비우면 지우기)', 'aria-label': `${t.label} 영상 주소` });
            input.addEventListener('change', () => saveVideo(i, input));
            onEnter(input, () => input.blur());
            input.addEventListener('keydown', e => { if (e.key === 'Escape') { input.value = videoText(((((ctx.slices.acct_video || {}).tiers) || [])[i] || {}).video); input.removeAttribute('aria-invalid'); input.blur(); } });
            const badge = h('span', { class: 'av-badge' });
            const up = h('button', { type: 'button', class: 'btn sm', title: `영상 파일 올리기 (mp4 · ${VIDEO_MAX_MB}MB 까지)`, onclick: () => pick(i) }, '⬆ 파일');
            const clear = h('button', { type: 'button', class: 'ops-mini del', title: `${t.label} 영상 지우기`, 'aria-label': `${t.label} 영상 지우기`,
                onclick: () => { input.value = ''; saveVideo(i, input); } }, '✕');
            rows.push({ play: playB, input, badge, up, clear });
            return h('div', { class: 'av-row' }, playB, input, badge, up, clear);
        }));
        paintUploading(uploading ? upTier : -1);
    }

    async function karaokeOn() {
        const id = ytId(kIn.value);
        if (!id) { kIn.setAttribute('aria-invalid', 'true'); ctx.toast('유튜브 링크를 알아보지 못했어요 — 링크를 다시 확인해 주세요', 'err'); kIn.focus(); return; }
        kIn.removeAttribute('aria-invalid');
        const res = await ctx.run('karaoke.play', { video: id });
        if (res.ok) { ctx.toast('🎤 노래방을 켰어요', 'ok'); kIn.value = ''; }
    }
    async function karaokeOff() {
        const res = await ctx.run('karaoke.stop', {});
        if (res.ok) ctx.toast('🎤 노래방을 껐어요', 'info');
    }

    let lastTiers = '', lastShape = '', lastNow = '', lastK = '';
    function render(slices) {
        const av = slices.acct_video || {};
        const tiers = av.tiers || [];
        const shape = sigOf(tiers.map(t => t.label));
        if (shape !== lastShape) { lastShape = shape; lastTiers = ''; buildRows(tiers); }
        const tsig = sigOf(tiers);
        if (tsig !== lastTiers) {
            lastTiers = tsig;
            tiers.forEach((t, i) => {
                const r = rows[i];
                if (!r) return;
                const v = t.video || '';
                r.play.disabled = !v;
                r.play.classList.toggle('pri', !!v);
                r.clear.hidden = !v;
                if (r.input.getAttribute('aria-invalid') !== 'true') setVal(r.input, videoText(v));
                r.badge.className = 'av-badge ' + (v ? (isUrl(v) ? 'file' : 'yt') : 'none');
                r.badge.textContent = v ? (isUrl(v) ? '🎬 영상 파일' : '▶ 유튜브') : '비어 있음';
                r.badge.title = v ? (isUrl(v) ? '광고 · 추천 영상 없이 바로 재생돼요' : '유튜브는 광고가 붙거나 끝난 뒤 추천 영상이 뜰 수 있어요') : '';
            });
        }
        const now = av.now;
        const nsig = sigOf(now);
        if (nsig !== lastNow) {
            lastNow = nsig;
            nowLine.className = 'ops-now' + (now ? '' : ' off');
            nowLine.replaceChildren(...(now ? ['▶ 지금 ', h('b', null, now.label || '영상'), ' 영상이 방송판에서 재생 중'] : ['재생 중인 영상 없음']));
            stopBtn.disabled = !now;
        }
        const k = slices.karaoke || {};
        const kv = Number.isFinite(Number(k.volume)) ? Math.max(0, Math.min(100, Math.round(Number(k.volume)))) : 70;   // 없으면 옛 기본 70
        if (document.activeElement !== kVol && !kVolPending) { if (kVol.value !== String(kv)) kVol.value = String(kv); kVolTxt.textContent = kv + '%'; }
        const ksig = sigOf(k.on, k.video);
        if (ksig !== lastK) {
            lastK = ksig;
            kState.className = 'ops-now' + (k.on ? '' : ' off');
            if (k.on && k.video) {
                const href = isUrl(k.video) ? k.video : 'https://youtu.be/' + k.video;
                kState.replaceChildren('🟢 노래방 켜짐 · ', h('a', { href, target: '_blank', rel: 'noopener noreferrer' }, href.replace(/^https?:\/\//, '') + ' ↗'));
            } else kState.replaceChildren('⚫ 꺼짐');
            kStop.disabled = !k.on;
        }
    }
    return { render };
}
