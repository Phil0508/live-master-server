/* 🗣️ 바로 하는 말(명령 꼴) — 'AI 에게 물어보기' 글칸(chat.js)과 Ctrl+K 빠른 명령(cmdk.js)이 **같이** 쓴다(옛 aiTryCommand).
   맞으면 AI 를 안 거치고 바로 서버 명령을 보낸다 → true. 아니면 false(AI 에게 넘기거나 '모르는 말').
   ⚠️ 한 곳에만 둔다 — 두 화면이 규칙을 따로 들고 있으면 한쪽만 고쳐져 어긋난다(검사 도구는 실물과 같아야 한다).
   out = { said(글) → 줄, done(줄, 글), toast? } — 부른 쪽이 '하는 중…' 을 적고 결과로 고친다(대화창 줄 · 빠른 명령 상자 줄).
         toast: false 면 여기서 알림(토스트)을 안 띄운다(빠른 명령 상자는 결과 글을 스스로 띄운다 — 두 번 안 뜨게).

   말                                   하는 일
   '하율 3점' · '하율한테 3점 줘' · '하율 +3' · '밍밍 5'   score.add(번외 판이 켜져 있으면 번외 판) — 이름이 여럿 맞으면 묻는다
   '슬롯 돌려' · '룰렛 돌려'                              /api/slot/spin · roulette.spin(다른 판이 떠 있으면 한 번 묻는다)
   '대결 시작' · '대결 정지' · '대결'(켜고 끄기)            match.start · match.pause
   '+1분' · '1분 추가' · '-30초'                         match.add_time {sec}
   '건너뛰어' · '스킵'                                    reaction.skip
   '올클리어'                                            sig.allclear(남은 칸이 있으면 묻는다)
   '클립'                                                clip.now
   '다음' · '다음 단계' · '이전 단계'                       show.cue {dir: next · prev} */
import { call, currentNames } from './common.js';
import { okToTake, useLm } from '../games/common.js';

/** 빠른 명령 상자 · 대화창 안내에 보여 줄 예시(이 파일이 아는 말만) */
export const COMMAND_HINTS = ['슬롯 돌려', '룰렛 돌려', '대결 시작', '대결 정지', '+1분', '-1분', '건너뛰어', '올클리어', '클립', '다음 단계', '이전 단계'];

const SCORE_RE = /^([가-힣A-Za-z0-9]+?)\s*(?:한테|에게)?\s*\+?(\d+)\s*점?\s*(?:줘|주기|추가)?$/;
const TIME_RE = /^([+-])?\s*(\d+)\s*(분|초)\s*(추가|더|빼기|빼|줄이기)?$/;

/** 말 하나 → 명령. 맞으면 true(보냈거나 · 안 하기로 했거나 · 왜 못 하는지 알렸거나), 아니면 false */
export async function runCommand(ctx, q, out) {
    q = String(q || '').trim();
    if (!q) return false;
    useLm(ctx.lm);                    // 무대 뺏기 확인(okToTake)이 서버 시계를 쓴다
    const slices = ctx.slices || {};
    const said = msg => out.said(msg);
    const done = (row, msg) => out.done(row, msg);
    const pop = (msg, kind) => { if (out.toast !== false) ctx.toast(msg, kind || 'ok'); };

    // '하율 3점' · '하율한테 3점 줘' · '하율 +3'
    const m = q.match(SCORE_RE);
    if (m) {
        const P = slices.players || {};
        const key = P.extra_active ? 'extra' : 'list';
        const names = currentNames(slices);
        const exact = names.filter(n => n === m[1]);
        const hit = exact.length ? exact : names.filter(n => n.indexOf(m[1]) !== -1);
        if (hit.length === 1) {
            const nm = hit[0], pts = parseInt(m[2], 10);
            const row = said(`⏳ ${nm} +${pts}점…`);
            const res = await ctx.run('score.add', { name: nm, delta: pts, list: key }, { quiet: true });
            done(row, res.ok ? `✔ ${key === 'extra' ? '[번외] ' : ''}${nm} +${pts}점 — 틀렸으면 [되돌리기]` : `⚠️ 못 줬어요 — ${res.error || '서버 전송 오류'}`);
            if (res.ok) pop(`${key === 'extra' ? '[번외] ' : ''}${nm} +${pts}점`);
            return true;
        }
        if (hit.length > 1) { said(`⚠️ '${m[1]}' 이(가) 여럿이에요: ${hit.join(', ')} — 이름을 정확히 적어 주세요`); return true; }
        // 선수 이름이 아니면 질문으로 본다(예: '1등 3' 같은 말) — 부른 쪽이 AI 에게 넘긴다
    }
    if (/^슬롯\s*(돌려|시작|고)?!?$/.test(q)) {
        if (!(await okToTake(ctx, 'slot', '슬롯머신'))) { said('🎰 슬롯은 그대로 뒀어요'); return true; }
        const row = said('🎰 슬롯을 돌려요…');
        const r = await call('/api/slot/spin', {});
        const w = r.data && r.data.winner;
        done(row, r.ok ? `🎰 돌려요${w ? ` — 당첨 ${w.title || ''}` : ''}` : `⚠️ 못 돌렸어요 — ${(r.data && (r.data.message || r.data.error)) || '실패 (' + r.status + ')'}`);
        return true;
    }
    if (/^룰렛\s*(돌려|시작|고)?!?$/.test(q)) {
        if (!(await okToTake(ctx, 'roulette', '룰렛'))) { said('🎡 룰렛은 그대로 뒀어요'); return true; }
        const row = said('🎡 룰렛을 돌려요…');
        const res = await ctx.run('roulette.spin', {}, { quiet: true });
        done(row, res.ok ? (res.already ? '🎡 이미 돌고 있어요' : '🎡 돌려요 — 룰렛 탭의 [정지!!] 로 세워요') : `⚠️ 못 돌렸어요 — ${res.error || '실패'}`);
        return true;
    }
    const mt = q.match(/^(대결|타이머)\s*(시작|정지|스톱|멈춰)?$/);
    if (mt) {
        const tm = ((slices.match || {}).timer) || {};
        const want = mt[2] ? (mt[2] === '시작' ? 'start' : 'pause') : (tm.running ? 'pause' : 'start');
        if (want === 'start' && tm.running) { said('⚔️ 대결 타이머는 이미 돌고 있어요'); return true; }
        if (want === 'pause' && !tm.running) { said('⚔️ 대결 타이머는 이미 멈춰 있어요'); return true; }
        const row = said(want === 'start' ? '⚔️ 대결 타이머를 켜요…' : '⚔️ 대결 타이머를 멈춰요…');
        const res = await ctx.run(want === 'start' ? 'match.start' : 'match.pause', {}, { quiet: true });
        done(row, res.ok ? (want === 'start' ? '⚔️ 대결 타이머 시작!' : '⚔️ 대결 타이머를 멈췄어요') : `⚠️ 못 했어요 — ${res.error || '실패'}`);
        return true;
    }
    const tt = q.replace(/^대결\s*/, '').match(TIME_RE);
    if (tt && (tt[1] || tt[4])) {
        const n = parseInt(tt[2], 10);
        const minus = tt[1] === '-' || /^(빼기|빼|줄이기)$/.test(tt[4] || '');
        const sec = (tt[3] === '분' ? n * 60 : n) * (minus ? -1 : 1);
        if (!sec || Math.abs(sec) > 3 * 3600) { said('⚠️ 시간을 다시 적어 주세요 — 예: +1분 · -30초'); return true; }
        const label = (minus ? '−' : '+') + n + tt[3];
        const row = said(`⏱ 대결 시간 ${label}…`);
        const res = await ctx.run('match.add_time', { sec }, { quiet: true });
        done(row, res.ok ? `⏱ 대결 시간 ${label}` : `⚠️ 못 했어요 — ${res.error || '실패'}`);
        if (res.ok) pop(`⏱ 대결 시간 ${label}`);
        return true;
    }
    if (/^(건너뛰|스킵|넘겨)/.test(q)) {
        const row = said('⏭ 재생 중인 시그니처를 넘겨요…');
        const res = await ctx.run('reaction.skip', {}, { quiet: true });
        done(row, res.ok ? '⏭ 넘겼어요' : `⚠️ 못 넘겼어요 — ${res.error || '실패'}`);
        return true;
    }
    if (/^올\s*클리어|^올클/.test(q)) {
        const g = slices.siggame || {};
        const left = (g.cards || []).filter(c => c && c.flippedAt && !c.doneAt).length;
        if (left > 0) {
            const ok = await ctx.confirm({ title: '올클리어 할까요?', body: `아직 ${left}장이 남아 있어요.\n남은 목표를 전부 달성 처리하고 올클리어를 터뜨립니다.`, ok: '올클리어', cancel: '아직', danger: false });
            if (!ok) { said('🃏 올클리어는 안 했어요'); return true; }
        }
        const row = said('🎉 올클리어!…');
        const res = await ctx.run('sig.allclear', {}, { quiet: true });
        done(row, res.ok ? `🎉 ALL CLEAR!${res.count ? ` (${res.count}장)` : ''}` : `⚠️ 못 했어요 — ${res.error || '실패'}`);
        return true;
    }
    if (/^(클립|✂)\s*(따|저장|해)?줘?!?$/.test(q)) {
        const row = said('✂️ 클립을 남겨요…');
        const res = await ctx.run('clip.now', {}, { quiet: true });
        done(row, res.ok ? '✂️ 앞 90초 + 뒤 90초 — 90초 뒤에 OBS 가 저장해요' : `⚠️ 못 했어요 — ${res.error || '실패'}`);
        if (res.ok) pop('✂️ 클립을 남겼어요');
        return true;
    }
    const cue = q.match(/^(다음|이전)\s*(단계|순서)?\s*(로|으로)?$/);
    if (cue) {
        const dir = cue[1] === '다음' ? 'next' : 'prev';
        const row = said(dir === 'next' ? '▶ 순서표 다음 단계로…' : '◀ 순서표 이전 단계로…');
        const res = await ctx.run('show.cue', { dir }, { quiet: true });
        done(row, res.ok ? (dir === 'next' ? '▶ 다음 단계로 넘겼어요' : '◀ 이전 단계로 돌렸어요') : `⚠️ 못 했어요 — ${res.error || '실패'}`);
        return true;
    }
    return false;
}
