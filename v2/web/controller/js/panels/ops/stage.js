/* 📺 무대 — 방송판에 무엇을 띄울지(옛 조종실 '방송 화면' 칸 · 서버 show.py).
   무대(한 번에 하나) → show.stage {stage|null}
   고정 자리(늘 떠 있는 것) → show.hud {key, on}   ⚠️ 모금함은 fundjar.enabled 도 같이 맞춘다(setJar)
   알림(뜨는 것) → show.alert {key, on}
   테마(방송판 옷) → look.theme {theme} — 이름은 옛 overlay.html THEMES 14벌 + 기본
   💾 순서표(세이브 슬롯) → cues.js(preset.* · show.cue) · 🔊 효과음 → look.sfx {on}(옛 sfx_enabled, 기본 켜짐) */
import { h, sigOf, once, setJar, blockHead, fill, switchEl } from './common.js';
import { mountCues } from './cues.js';

export const STAGES = [['', '없음'], ['match', '대결'], ['pinball', '핀볼'], ['dicegame', '주사위'], ['siggame', '시그뒤집기'],
    ['roulette', '룰렛'], ['slot', '슬롯'], ['home_race', '퇴근빵'], ['hell', '지옥탈출'], ['quiz', '퀴즈']];
export const STAGE_NAME = Object.fromEntries(STAGES.filter(s => s[0]));
export const HUDS = [['ranking', '점수판'], ['gauge', '게이지'], ['account', '계좌'], ['notice', '공지'],
    ['donor_rank', '후원 순위'], ['sig_tally', '시그 순위'], ['best', '최고 후원'], ['fundjar', '모금함']];
export const ALERTS = [['popup', '후원 팝업'], ['takeover', '1등 탈환'], ['reaction_title', '시그 제목'], ['small', '1천~9천 알림']];
// 옛 overlay.html THEMES 와 같은 순서 · 옛 조종실 테마 칸과 같은 이름
export const THEMES = [['default', '기본 (금색 유리판)'], ['rose', '👑 로즈골드'], ['pastel', '🎀 파스텔'], ['royal', '💎 로얄'],
    ['chuseok', '🌕 추석'], ['hospital', '🏥 병원'], ['halloween', '🎃 할로윈'], ['concert', '💜 콘서트'], ['sports', '🏟️ 스포츠 중계'],
    ['news', '📰 뉴스 속보'], ['arcade', '👾 아케이드'], ['mintchoco', '🍫 민트초코'], ['y2k', '💿 Y2K'], ['hanji', '🏮 한지·먹'], ['winter', '❄️ 첫눈']];

export function mountStage(el, ctx) {
    const sum = h('p', { class: 'ops-now' });
    const stageBtns = {}, hudBtns = {}, alertBtns = {};
    const seg = h('div', { class: 'ops-seg', role: 'group', 'aria-label': '무대' }, STAGES.map(([k, n]) => {
        const b = h('button', { type: 'button', class: 'ops-segb', 'data-stage': k || 'none', 'aria-pressed': 'false',
            onclick: () => once(b, () => setStage(k)) }, n);
        stageBtns[k] = b;
        return b;
    }));
    const retNote = h('p', { class: 'ops-hint' });
    const chip = (map, kind, k, n) => {
        const b = h('button', { type: 'button', class: 'ops-chip', ['data-' + kind]: k, 'aria-pressed': 'false',
            onclick: () => once(b, () => toggle(kind, k, n)) }, h('i', { 'aria-hidden': 'true' }), n);
        map[k] = b;
        return b;
    };
    const hudRow = h('div', { class: 'ops-chips' }, HUDS.map(([k, n]) => chip(hudBtns, 'hud', k, n)));
    const alertRow = h('div', { class: 'ops-chips' }, ALERTS.map(([k, n]) => chip(alertBtns, 'alert', k, n)));
    const themeSel = h('select', { class: 'ops-select', 'aria-label': '방송판 테마' }, THEMES.map(([k, n]) => h('option', { value: k }, n)));
    themeSel.addEventListener('change', async () => {
        const t = themeSel.value;
        const res = await ctx.run('look.theme', { theme: t });
        if (res.ok) ctx.toast('테마: ' + (THEMES.find(x => x[0] === t) || [t, t])[1], 'ok');
        else { lastSig = ''; ctx.rerender(); }
    });

    // 💾 순서표 · 🔊 효과음 — 옛 조종실 '방송 화면' 칸 윗줄 · '기본 설정' 의 효과음 스위치
    const cues = mountCues(ctx, STAGE_NAME);
    const sfxSw = switchEl('🔊 효과음', async on => {
        const res = await ctx.run('look.sfx', { on });
        if (res.ok) ctx.toast(on ? '🔊 효과음을 켰어요' : '🔇 효과음을 껐어요 — 시그니처 · 노래방 · 영상 소리는 그대로예요', on ? 'ok' : 'info');
        else { lastSig = ''; ctx.rerender(); }
    }, '주사위 · 목표 달성 · 모금함 · 시그뒤집기 · 대결 삑 소리. 방송 중에 거슬리면 끄세요');
    // ✨ 테마 연출 — 옛 조종실 테마 칸 옆 체크(theme_fx_enabled) → look.fx {on}(서버 lights.py · 방송판 widgets/fx/burst.js)
    const fxSw = switchEl('✨ 테마 연출', async on => {
        const res = await ctx.run('look.fx', { on });
        if (res.ok) ctx.toast(on ? '✨ 테마 연출을 켰어요 — 테마를 입었을 때만 입자가 나와요' : '✨ 테마 연출을 껐어요', on ? 'ok' : 'info');
        else { lastSig = ''; ctx.rerender(); }
    }, '테마를 입었을 때 후원 알림에 테마 모양 입자(하트 · 리본 · 보석 · 금가루)를 조금 뿌립니다. 기본 테마에서는 원래대로 아무것도 안 나옵니다.');

    el.classList.add('ops', 'ops-stage');
    el.append(
        sum,
        cues.el,
        h('section', { class: 'ops-blk' }, blockHead('무대', '한 번에 하나 — 올리면 다른 판은 내려가요'), seg, retNote),
        h('section', { class: 'ops-blk' }, blockHead('고정 자리', '방송판에 늘 떠 있는 것 — 눌러서 켜고 끄기'), hudRow),
        h('section', { class: 'ops-blk' }, blockHead('알림', '들어올 때 잠깐 뜨는 것'), alertRow,
            h('div', { class: 'ops-row wrap' }, sfxSw.el,
                h('span', { class: 'ops-hint inline' }, '주사위 · 목표 · 모금함 · 시그뒤집기 · 대결 삑 — 시그니처 · 노래방 · 영상 소리는 안 꺼져요'))),
        h('section', { class: 'ops-blk' }, blockHead('테마', '방송판 위젯의 옷만 바뀌어요 — 자리 · 크기는 그대로'), h('div', { class: 'ops-row wrap' }, themeSel, fxSw.el)),
    );

    async function setStage(k) {
        const res = await ctx.run('show.stage', { stage: k || null });
        if (res.ok) ctx.toast(k ? `무대에 ${STAGE_NAME[k]} 을(를) 올렸어요` : '무대를 비웠어요', 'ok');
    }

    async function toggle(kind, k, n) {
        const s = (ctx.slices.show) || {};
        if (kind === 'hud') {
            const on = !(s.hud || {})[k];
            const res = k === 'fundjar' ? await setJar(ctx, on) : await ctx.run('show.hud', { key: k, on });
            if (res.ok) ctx.toast(`${n} ${on ? '켰어요' : '껐어요'}`, on ? 'ok' : 'info');
        } else {
            const on = (s.alerts || {})[k] === false;
            const res = await ctx.run('show.alert', { key: k, on });
            if (res.ok) ctx.toast(`${n} 알림 ${on ? '켰어요' : '껐어요'}`, on ? 'ok' : 'info');
        }
    }

    let lastSig = '';
    function render(slices) {
        cues.render(slices);
        sfxSw.set((slices.look || {}).sfx !== false);      // 값이 없는 옛 상태는 켜짐
        fxSw.set((slices.look || {}).fx !== false);        // ✨ 테마 연출 — 값이 없으면 켜짐(옛 theme_fx_enabled !== false)
        const s = slices.show || {};
        const theme = (slices.look || {}).theme || 'default';
        const sig = sigOf(s.stage, s.ret, s.hud, s.alerts, theme);
        if (sig === lastSig) return;
        lastSig = sig;
        const cur = s.stage || '';
        fill(sum, '지금 무대 ', h('b', null, STAGE_NAME[cur] || '비어 있음'),
            s.ret ? h('span', { class: 'ops-dim' }, ` · 끝나면 ${STAGE_NAME[s.ret] || s.ret}(으)로 돌아가요`) : null);
        Object.entries(stageBtns).forEach(([k, b]) => { const on = k === cur; b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on)); });
        retNote.textContent = s.ret ? `잠깐 올라온 판 — 끝나면 ${STAGE_NAME[s.ret] || ''}(으)로 돌아가요` : '';
        retNote.hidden = !s.ret;
        Object.entries(hudBtns).forEach(([k, b]) => { const on = !!(s.hud || {})[k]; b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on)); });
        Object.entries(alertBtns).forEach(([k, b]) => { const on = (s.alerts || {})[k] !== false; b.classList.toggle('on', on); b.setAttribute('aria-pressed', String(on)); });
        const want = theme === 'pink' ? 'rose' : theme;      // 'pink' = 뺀 옛 네온 핑크
        const known = THEMES.some(t => t[0] === want);
        if (document.activeElement !== themeSel) themeSel.value = known ? want : 'default';
    }
    return { render };
}
