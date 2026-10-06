/* ✂️ 클립 탭 — [✂ 지금 클립] · OBS 저장 담당 상태 · 저절로 저장(큰 시그 · 올클리어) · 파일 이름 규칙 · 회사 PC 도우미 · 저장한 순간 목록.
   옛 조종실 시스템 탭 '쇼츠 클립'(controller.html clipNow · clipPaint …)을 옮겼다.

   서버(domain/clip.py)
     조각 clip(auto · auto_min · ask) · clip_log(name_fmt · log) — 실시간으로 온다
     명령 clip.now{label?} · clip.settings{auto?, auto_min?, name_fmt?, clear?} · clip.rename{id, name}
     GET /api/clip — OBS 저장 담당 상태(방송판이 1분마다 알린다). 이 탭이 열려 있는 동안 20초마다 읽는다.
     GET /api/clip/helper.zip — 회사 PC 도우미(서버 주소 · 목록 읽기 열쇠가 박혀 있다)
   흐름: [✂ 지금 클립] → 서버 목록 + 방송판(회사 OBS 안)에 알림 → 90초 뒤 OBS 가 '앞 90초 + 뒤 90초' 저장
         → 방송판이 '저장됨' 을 알리면 줄에 [저장됨] → 회사 PC 도우미가 파일을 옮기며 이름을 붙인다.
   ⚠️ 제목 칸을 치는 중에는 그 줄을 다시 쓰지 않는다(옛 것은 다시 그리다 글자가 날아갔다). */
import { h, num } from '../../util.js';
import { api, blockHead, onEnter, setVal, switchEl, once } from '../ops/common.js';

export const FMT_DEFAULT = '{날짜} {시각} {제목}';
const MINS = [[50000, '5만 원 이상'], [100000, '10만 원 이상'], [200000, '20만 원 이상'], [500000, '50만 원 이상'], [1000000, '100만 원 이상']];
const POLL_MS = 20000;

export function clipAgo(sec) {
    if (sec == null) return '';
    return sec < 60 ? sec + '초 전' : sec < 3600 ? Math.floor(sec / 60) + '분 전' : Math.floor(sec / 3600) + '시간 전';
}

/** OBS 저장 담당 상태 → [수준(ok · warn · off), 글] — 옛 clipObsText 그대로 */
export function obsText(o) {
    if (!o || !o.alive) return ['off', 'OBS 저장 담당이 안 보여요 — 회사 OBS 에 방송판이 켜져 있고 권한을 줬는지 확인 (아래 "처음 한 번만 할 것")'];
    if (!(o.level >= 4)) return ['warn', '방송판은 보이는데 권한이 낮아요 — 브라우저 소스 → 페이지 권한 → "OBS에 대한 고급 접근 권한"'];
    if (o.rb === false) return ['warn', '리플레이 버퍼가 꺼져 있어요 — OBS 설정 → 출력 → "리플레이 버퍼 사용" 체크'];
    return ['ok', 'OBS 연결됨 · 리플레이 버퍼 켜짐' + (o.saved_ago != null ? ' · 마지막 저장 ' + clipAgo(o.saved_ago) : '')];
}

/** 📁 파일 이름 — 도우미(clip_helper.ps1 Build-Name)와 같은 셈이어야 미리보기가 거짓말을 안 한다 */
export function clipFileName(fmt, title, ms, seq) {
    const d = new Date(Number(ms) + 9 * 3600 * 1000);           // 한국 시각(도우미와 같게)
    const p2 = n => String(n).padStart(2, '0');
    const date = d.getUTCFullYear() + '-' + p2(d.getUTCMonth() + 1) + '-' + p2(d.getUTCDate());
    const time = p2(d.getUTCHours()) + '-' + p2(d.getUTCMinutes()) + '-' + p2(d.getUTCSeconds());
    let n = String(fmt || FMT_DEFAULT).split('{날짜}').join(date).split('{시각}').join(time)
        .split('{번호}').join(p2(seq || 1)).split('{제목}').join(title || '클립');
    n = n.replace(/[\\/:*?"<>|\r\n\t]/g, '_').trim().replace(/\.+$/, '');
    return (n.slice(0, 120).trim() || '클립');
}

const p2 = n => String(n).padStart(2, '0');
const clockOf = ms => { const d = new Date(ms); return p2(d.getHours()) + ':' + p2(d.getMinutes()) + ':' + p2(d.getSeconds()); };
const hms = ms => { const t = Math.max(0, Math.floor(ms / 1000)); return Math.floor(t / 3600) + ':' + p2(Math.floor(t % 3600 / 60)) + ':' + p2(t % 60); };

export function mountClip(el, ctx) {
    el.classList.add('ops', 'mo');
    let obs = null, polling = false;

    // ── ① 지금 클립 · 상태 ──
    const dot = h('i', { 'aria-hidden': 'true' });
    const stText = h('span');
    const status = h('div', { class: 'mo-clip-st', 'data-lv': 'off', role: 'status' }, dot, stText);
    const refresh = h('button', { type: 'button', class: 'ops-mini', title: 'OBS 상태 다시 보기' }, '새로 고침');
    const nowBtn = h('button', { type: 'button', class: 'btn big pri mo-clip-now', title: '누른 순간 앞 90초 + 뒤 90초(3분)를 OBS 가 저장합니다 — 뒤 90초를 담으려고 90초 뒤에 저장돼요' },
        h('span', { 'aria-hidden': 'true' }, '✂'), ' 지금 클립');
    const head = h('div', { class: 'ops-blk' },
        h('div', { class: 'ops-bh' }, h('h3', null, '✂️ 쇼츠 클립'), h('span', { class: 'ops-sub' }, '명장면마다 OBS 가 그 순간 앞뒤를 저장해요'), refresh),
        status,
        nowBtn,
        h('p', { class: 'ops-hint' }, '⏱ 누른 순간 ', h('b', null, '앞 90초 + 뒤 90초(3분)'), '가 담겨요 — 뒤 90초를 기다려 ', h('b', null, '90초 뒤에'),
            ' 저장돼요. 회사 OBS 리플레이 버퍼 ', h('b', null, '최대 시간은 180초'), '여야 해요(90초면 뒤 90초만 남아요).'));

    // ── ② 저절로 ──
    const auto = switchEl('큰 시그 · 올클리어 때 저절로 저장', on => setAuto({ auto: on }));
    const minSel = h('select', { class: 'ops-select', 'aria-label': '저절로 저장 기준 금액' }, MINS.map(([v, l]) => h('option', { value: String(v) }, l)));
    minSel.addEventListener('change', () => setAuto({ auto_min: Number(minSel.value) || 100000 }));
    const autoBlk = h('div', { class: 'ops-blk' }, blockHead('저절로 저장', '시그는 실제로 재생될 때 · 올클리어는 그 순간'),
        h('div', { class: 'ops-row wrap' }, auto.el, h('label', { class: 'ops-row' }, h('span', null, '기준'), minSel)));

    // ── ③ 파일 이름 · 도우미 ──
    const fmt = h('input', { type: 'text', maxlength: '80', autocomplete: 'off', placeholder: FMT_DEFAULT, 'aria-label': '파일 이름 규칙', class: 'grow' });
    const ex = h('p', { class: 'ops-hint mo-fmt-ex' });
    const toks = ['{날짜}', '{시각}', '{제목}', '{번호}'].map(t => h('button', { type: 'button', class: 'ops-mini', onclick: () => tok(t) }, t.slice(1, -1)));
    const nameBlk = h('div', { class: 'ops-blk' }, blockHead('📁 파일 이름 규칙', '회사 PC 도우미가 3초마다 읽어 이름을 붙여요'),
        h('div', { class: 'ops-row wrap' }, fmt, h('span', { class: 'mo-toks' }, toks)), ex,
        h('div', { class: 'mo-helper' },
            h('div', null, h('b', null, '회사 컴퓨터용 도우미'),
                h('span', { class: 'ops-hint' }, 'OBS 가 저장한 클립을 고른 폴더로 옮기고 위 규칙대로 이름을 붙여요. 제목을 고치면 파일 이름도 따라 바뀌어요.')),
            h('a', { class: 'btn sm', href: '/api/clip/helper.zip', download: 'shorts_clip_helper.zip' }, '⬇ 도우미 받기')),
        h('p', { class: 'ops-hint' }, '🎛️ 스트림덱 단추로도 클립을 걸 수 있어요 — ', h('a', { href: '/streamdeck/', target: '_blank', rel: 'noopener' }, '가상 스트림덱 열기 ↗')));
    onEnter(fmt, () => fmt.blur());
    fmt.addEventListener('input', preview);
    fmt.addEventListener('change', saveFmt);

    // ── ④ 저장한 순간 ──
    const count = h('span', { class: 'ops-sub' });
    const clearBtn = h('button', { type: 'button', class: 'ops-mini del' }, '목록 비우기');
    const ol = h('ol', { class: 'mo-clip-log' });
    const empty = h('p', { class: 'empty' }, '아직 없어요.');
    const logBlk = h('div', { class: 'ops-blk' },
        h('div', { class: 'ops-bh' }, h('h3', null, '저장한 순간'), count, h('span', { class: 'ops-sub' }, '제목 칸을 고치면 파일 이름이 바뀌어요'), clearBtn),
        ol, empty);

    const guide = h('details', { class: 'mo-fold' },
        h('summary', null, '회사 컴퓨터에서 처음 한 번만 할 것 ', h('small', null, '세 가지')),
        h('div', { class: 'ops-hint' },
            h('p', null, '① ', h('b', null, '설정 → 출력 → 리플레이 버퍼'), ' — "리플레이 버퍼 사용" 체크, 최대 시간 ', h('b', null, '180초'), '(앞 90초 + 뒤 90초). 저장 폴더는 녹화 폴더와 같아요.'),
            h('p', null, '② 방송판 ', h('b', null, '브라우저 소스를 더블클릭 → 맨 아래 "페이지 권한" → "OBS에 대한 고급 접근 권한"'),
                '. 방송판이 여러 장면에 있으면 ', h('b', null, '한 곳에만'), ' 주세요(여러 곳이면 같은 클립이 여러 개 생겨요). 다 하면 위 줄이 초록 "OBS 연결됨" 으로 바뀌어요. 리플레이 버퍼는 방송판이 알아서 켜요.'),
            h('p', null, '③ 위 ', h('b', null, '[⬇ 도우미 받기]'), ' 를 회사 컴퓨터에서 받아 풀고 ', h('b', null, 'start_clip_helper.bat'),
                ' 더블클릭 → 폴더 두 개(OBS 녹화 폴더 · 클립 모을 폴더)를 고르면 끝. 방송 동안 까만 창을 켜 두세요. 리플레이 파일 이름은 OBS 기본("Replay …")으로 두세요.'),
            h('p', null, '큰 시그는 재생 순간, 올클리어는 그 순간을 가운데 두고 똑같이 담겨요. 30초 안에 붙은 순간은 파일 하나로, 그보다 멀면 따로 저장해요.')));

    el.append(head, autoBlk, nameBlk, logBlk, guide);

    // ── 하는 일 ──
    refresh.addEventListener('click', () => poll(true));
    nowBtn.addEventListener('click', () => once(nowBtn, async () => {
        const res = await ctx.run('clip.now', {});
        if (!res.ok) return;
        obs = res.obs || obs;
        paintStatus();
        const ok = obs && obs.alive && obs.level >= 4 && obs.rb !== false;
        ctx.toast(ok ? '✂️ 앞 90초 + 뒤 90초 — 90초 뒤에 OBS 가 저장해요' : '✂️ 목록에만 적었어요 — OBS 연결을 확인하세요(위 상태 줄)', ok ? 'ok' : 'info');
    }));
    async function setAuto(patch) {
        const res = await ctx.run('clip.settings', patch);
        if (res.ok) ctx.toast('저절로 저장 설정을 바꿨어요', 'ok');
        draw(true);
    }
    function tok(t) {
        const a = fmt.selectionStart != null ? fmt.selectionStart : fmt.value.length, b = fmt.selectionEnd != null ? fmt.selectionEnd : a;
        fmt.value = fmt.value.slice(0, a) + t + fmt.value.slice(b);
        fmt.focus();
        fmt.setSelectionRange(a + t.length, a + t.length);
        preview();
        saveFmt();
    }
    function preview() {
        ex.textContent = '예) ' + clipFileName(fmt.value.trim() || FMT_DEFAULT, '밍밍 1,000,000원 VIP', Date.now(), 3) + '.mp4';
    }
    async function saveFmt() {
        const want = fmt.value.trim() || FMT_DEFAULT;
        if (want === ((ctx.slices.clip_log || {}).name_fmt || FMT_DEFAULT)) return;
        const res = await ctx.run('clip.settings', { name_fmt: want });
        if (res.ok) ctx.toast('📁 파일 이름 규칙을 바꿨어요', 'ok');
    }
    clearBtn.addEventListener('click', async () => {
        const ok = await ctx.confirm({ title: '저장한 순간 목록을 비울까요?', body: 'OBS 에 저장된 영상 파일은 그대로 남아요.', ok: '목록 비우기', cancel: '그대로 두기' });
        if (!ok) return;
        const res = await ctx.run('clip.settings', { clear: true });
        if (res.ok) ctx.toast('목록을 비웠어요', 'info');
    });

    // OBS 상태 — 이 탭이 보일 때만 20초마다
    async function poll(force) {
        if (polling) return;
        if (!force && (el.hidden || document.visibilityState === 'hidden')) return;
        polling = true;
        const r = await api('/api/clip');
        polling = false;
        if (r.ok) obs = r.data.obs || null;
        else if (force) ctx.toast(r.error, 'err');
        paintStatus();
    }
    setInterval(() => poll(false), POLL_MS);
    poll(true);

    function paintStatus() {
        const [lv, txt] = obsText(obs);
        if (status.dataset.lv !== lv) status.dataset.lv = lv;
        if (stText.textContent !== txt) stText.textContent = txt;
    }

    // ── 목록 줄 — id 마다 한 번 만들고 바뀐 칸만 고친다 ──
    const rows = new Map();
    function rowFor(x) {
        let r = rows.get(x.id);
        if (r) return r;
        const time = h('time', { class: 'mo-t' });
        const at = h('span', { class: 'mo-at' });
        const kind = h('span', { class: 'tag' });
        const input = h('input', { type: 'text', maxlength: '60', autocomplete: 'off', class: 'mo-title', 'aria-label': '클립 제목' });
        const ok = h('span', { class: 'mo-ok' });
        const li = h('li', { class: 'mo-row' }, time, at, kind, input, ok);
        onEnter(input, () => input.blur());
        input.addEventListener('change', async () => {
            const res = await ctx.run('clip.rename', { id: x.id, name: input.value.trim() });
            if (res.ok) ctx.toast('✎ 제목을 바꿨어요 — 도우미가 파일 이름도 바꿔요', 'ok');
        });
        r = { li, time, at, kind, input, ok, sig: '' };
        rows.set(x.id, r);
        return r;
    }

    let lastC = null, lastL = null, lastStart = null;
    function draw(force) {
        const c = ctx.slices.clip || {};
        const cl = ctx.slices.clip_log || {};
        const start = Number((ctx.slices.session || {}).started_at) || 0;
        if (!force && c === lastC && cl === lastL && start === lastStart) return;
        lastC = c; lastL = cl; lastStart = start;
        auto.set(c.auto !== false);
        if (document.activeElement !== minSel) {
            const v = String(c.auto_min || 100000);
            if (!MINS.some(([m]) => String(m) === v)) {        // 목록에 없는 값(스트림덱 · 옛 설정) — 그 값도 보이게
                if (!minSel.querySelector('option[data-x]')) minSel.append(h('option', { value: v, 'data-x': '1' }));
                const xo = minSel.querySelector('option[data-x]');
                xo.value = v;
                xo.textContent = num(Number(v)) + '원 이상';
            }
            minSel.value = v;
        }
        minSel.disabled = c.auto === false;
        setVal(fmt, cl.name_fmt || FMT_DEFAULT);
        if (document.activeElement !== fmt) preview();

        const log = Array.isArray(cl.log) ? cl.log.slice().reverse() : [];
        count.textContent = log.length ? num(log.length) + '개' : '';
        empty.hidden = log.length > 0;
        clearBtn.disabled = !log.length;
        const keep = new Set(log.map(x => x.id));
        for (const [k, r] of rows) if (!keep.has(k)) { r.li.remove(); rows.delete(k); }
        log.forEach((x, i) => {
            const r = rowFor(x);
            const sig = JSON.stringify([x.ts, x.kind, x.label, x.name, x.saved_at, start]);
            if (sig !== r.sig) {
                r.sig = sig;
                r.time.textContent = clockOf(x.ts);
                // 방송 시작부터 몇 시간 몇 분인지 — 녹화본에서 그 자리를 찾을 때 쓴다
                r.at.textContent = start && x.ts >= start * 1000 && x.ts - start * 1000 < 16 * 3600 * 1000 ? '방송 +' + hms(x.ts - start * 1000) : '';
                r.kind.className = 'tag ' + (x.kind === 'manual' ? 'hot' : 'plain');
                r.kind.textContent = x.kind === 'manual' ? '직접' : '자동';
                r.input.placeholder = x.label || '제목';
                setVal(r.input, x.name || '');
                r.ok.className = 'mo-ok' + (x.saved_at ? ' on' : '');
                r.ok.textContent = x.saved_at ? '저장됨' : '대기';
                r.ok.title = x.saved_at ? 'OBS 가 저장했어요' : '뒤 90초를 담으려고 기다리는 중이거나, 아직 OBS 저장 확인이 안 왔어요';
            }
            if (ol.children[i] !== r.li) ol.insertBefore(r.li, ol.children[i] || null);
        });
    }

    return { render() { draw(false); if (!obs && !polling) paintStatus(); } };
}
