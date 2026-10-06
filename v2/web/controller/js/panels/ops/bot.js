/* 🤖 진행봇 — 유튜브 채팅에 후원 인사 · 순위 · 안내를 올리는 **다른 프로그램**(v2/tools/bot_v2.py)의 설정.
   서버는 설정(announce_bot 조각)을 적어 두기만 하고, 봇이 그걸 보고 스스로 입을 다문다.
   명령: bot.set {enabled?, min_interval_sec?, live_url?} · bot.say {key, on} · bot.notice {key, min}
   봇이 붙으면 bot.hello 로 모드(dry 입 막음 · live 진짜)를 알린다 → announce_status. 붙어 있는지는 /api/screens 의 kind 'bot'.
   ⚠️ 봇이 안 떠 있으면 여기서 뭘 눌러도 채팅엔 아무 일도 없다 — 그 사실을 화면에 그대로 보여 준다(옛 조종실과 같다). */
import { h, sigOf, onEnter, setVal, once, switchEl, fill, api, blockHead } from './common.js';

const SAY = [
    ['donation', '💝 후원 감사', '리액션이 화면에 나올 때 “누가 얼마”를 적어요'],
    ['rank_top', '👑 1위 바뀜', '순위 1등이 바뀌면 알려요'],
    ['rank_close', '🔥 접전(점수차)', '1 · 2위가 바짝 붙으면 “단 2만 차이!”라고 외쳐요'],
    ['goal', '🎯 목표 진행', '25 · 50 · 75 · 90%를 지날 때와 달성했을 때'],
    ['dice', '🎲 주사위', '굴림 · 한 바퀴 · 황금열쇠 · 뺏기 · 블랙홀. 켜면 말이 많아져요'],
    ['idle', '💬 조용할 때 질문', '아무 일도 없으면 채팅에 말을 걸어요'],
];
const NOTICE = [
    ['account_min', '💛 후원 계좌', '폰에서는 화면의 계좌번호를 복사할 수 없어요. 채팅에 있으면 길게 눌러 복사돼요'],
    ['rank_min', '📊 순위 요약', '지금 1 · 2 · 3위와 점수차를 한 줄로'],
    ['fundjar_min', '🏺 모금함', '지금 모금함에 얼마 쌓였는지'],
];

export function mountBot(el, ctx) {
    const sw = switchEl('진행봇 켜기', async on => {
        const res = await ctx.run('bot.set', { enabled: on });
        if (res.ok) ctx.toast(on ? '🤖 진행봇을 켰어요' : '🤖 진행봇을 껐어요 — 한마디도 안 해요', on ? 'ok' : 'info');
        else sw.input.checked = !on;
    }, '끄면 봇이 채팅에 아무것도 안 올려요(후원 인사는 쌓아 뒀다가 다시 켜면 올려요)');
    const alive = h('p', { class: 'ops-note gold' });
    const urlIn = h('input', { type: 'text', autocomplete: 'off', class: 'grow', placeholder: 'https://youtube.com/live/… 또는 watch?v=…', 'aria-label': '유튜브 라이브 주소' });
    const urlSave = h('button', { type: 'button', class: 'btn pri sm', onclick: () => once(urlSave, saveUrl) }, '저장');
    const urlClear = h('button', { type: 'button', class: 'btn sm', onclick: () => once(urlClear, () => { urlIn.value = ''; return saveUrl(); }) }, '비우기');
    const urlNow = h('p', { class: 'ops-dim small' });
    const ivIn = h('input', { type: 'range', min: '5', max: '120', step: '5', 'aria-label': '최소 간격(초)' });
    const ivT = h('b', null, '25초');
    const sayBox = h('div', { class: 'ab-list' });
    const ntcBox = h('div', { class: 'ab-list' });
    onEnter(urlIn, () => once(urlSave, saveUrl));
    ivIn.addEventListener('input', () => { ivT.textContent = ivIn.value + '초'; });
    ivIn.addEventListener('change', async () => {
        const res = await ctx.run('bot.set', { min_interval_sec: Number(ivIn.value) });
        if (res.ok) ctx.toast(`🤖 한 줄 간격 ${ivIn.value}초`, 'ok');
    });

    el.classList.add('ops', 'ops-bot');
    el.append(
        h('div', { class: 'ops-toprow' }, sw.el),
        alive,
        h('section', { class: 'ops-blk' }, blockHead('라이브 주소', '봇이 채팅을 칠 방송 — 비우면 봇이 제 계정의 라이브를 찾아요'),
            h('div', { class: 'ops-row wrap' }, urlIn, urlSave, urlClear), urlNow),
        h('section', { class: 'ops-blk' }, blockHead('한 줄 간격', '채팅이 도배되지 않게 — 최소 몇 초에 한 줄'),
            h('div', { class: 'ops-row' }, ivIn, ivT)),
        h('section', { class: 'ops-blk' }, blockHead('무엇을 말할까', '켠 것만 말해요'), sayBox),
        h('section', { class: 'ops-blk' }, blockHead('되풀이 안내', '몇 분마다 — 0 이면 꺼요'), ntcBox),
    );

    async function saveUrl() {
        const res = await ctx.run('bot.set', { live_url: urlIn.value.trim() });
        if (res.ok) ctx.toast(urlIn.value.trim() ? '🤖 이 방송에 칠게요' : '🤖 주소를 비웠어요 — 봇이 라이브를 찾아요', 'ok');
    }

    // 붙어 있는 봇 — /api/screens 의 kind 'bot'. 10초마다(이 탭이 열려 있을 때만 그린다)
    let botOn = null, lastPoll = 0;
    async function poll() {
        lastPoll = Date.now();
        const r = await api('/api/screens');
        botOn = r.ok ? (r.data.screens || []).some(s => s.kind === 'bot') : null;
        paintAlive();
    }

    let lastB = null, lastS = null;
    function paintAlive() {
        const s = ctx.slices || {};
        const b = s.announce_bot || {}, st = s.announce_status || {}, live = !!(s.session || {}).live;
        const mode = st.mode === 'live' ? '진짜로 치는 중(live)' : st.mode === 'dry' ? '연습(dry — 채팅엔 안 올림)' : '';
        let line;
        if (!b.enabled) line = ['⚫ ', h('b', null, '꺼 둔 상태'), '예요 — 봇이 한마디도 안 해요.'];
        else if (botOn === false) line = ['🔴 ', h('b', null, '봇 프로그램이 안 붙어 있어요'), ' — 켜 둬도 채팅엔 아무것도 안 올라가요.'];
        else if (!live) line = ['🟡 켜져 있지만 ', h('b', null, '방송이 시작되지 않았어요'), '. 봇은 방송 중에만 말해요.'];
        else line = ['🟢 켜짐 · 방송 중', botOn ? ' · 봇 붙어 있음' : ''];
        fill(alive, ...line, mode ? h('span', { class: 'ops-dim' }, ' · ' + mode) : null);
        alive.className = 'ops-note ' + (b.enabled && botOn === false ? 'warn' : 'gold');
    }

    function render(slices) {
        if (Date.now() - lastPoll > 10000) poll();
        const b = slices.announce_bot || {};
        sw.set(!!b.enabled);
        setVal(urlIn, b.live_url || '');
        fill(urlNow, b.live_video_id ? ['✅ 이 방송에 쳐요 — 영상 번호 ', h('b', null, b.live_video_id)]
            : ['비어 있어요 — 봇이 ', h('b', null, '제 계정의'), ' 라이브를 찾아요. 방송을 다른 계정으로 하면 못 찾아요.']);
        if (document.activeElement !== ivIn) { ivIn.value = String(b.min_interval_sec || 25); ivT.textContent = ivIn.value + '초'; }
        if (b !== lastB || slices.announce_status !== lastS) { lastB = b; lastS = slices.announce_status; paintAlive(); }
        const say = b.say || {}, ntc = b.notices || {};
        const sig = sigOf(say, ntc);
        if (sayBox.dataset.sig === sig) return;
        sayBox.dataset.sig = sig;
        fill(sayBox, SAY.map(([k, t, d]) => {
            const c = h('input', { type: 'checkbox', checked: !!say[k] || null });
            c.addEventListener('change', async () => {
                const res = await ctx.run('bot.say', { key: k, on: c.checked });
                if (!res.ok) c.checked = !c.checked;
            });
            return h('label', { class: 'ab-row' }, c, h('span', { class: 'ab-txt' }, h('b', null, t), h('small', null, d)));
        }));
        fill(ntcBox, NOTICE.map(([k, t, d]) => {
            const n = h('input', { type: 'number', min: '0', max: '120', inputmode: 'numeric', value: String(ntc[k] || 0), class: 'ab-num', 'aria-label': t + ' 몇 분마다' });
            n.addEventListener('change', async () => {
                const min = Math.max(0, Math.min(120, parseInt(n.value, 10) || 0));
                n.value = String(min);
                const res = await ctx.run('bot.notice', { key: k, min });
                if (res.ok) ctx.toast(min ? `🤖 ${t} — ${min}분마다` : `🤖 ${t} 안내를 껐어요`, 'ok');
            });
            return h('div', { class: 'ab-row' }, h('span', { class: 'ab-txt' }, h('b', null, t), h('small', null, d)), n, h('span', { class: 'ops-dim' }, '분'));
        }));
    }

    return { render };
}
