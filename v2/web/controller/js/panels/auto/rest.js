/* ☕ 휴식 켜고 끄기 — 머리줄 [☕ 휴식](restmode.js) · 학습·휴식 탭(mode.js)이 같이 쓴다(대표님 10-22).
   서버 명령은 auto.set {mode} 하나 — 휴식 = 'on', 학습 = 'shadow'. 모든 기기가 같은 값을 본다(예전 휴식은 기기마다였다).
   켤 때만 화면 안 상자로 한 번 묻는다 — 돈이 걸린 일(기계가 점수를 넣는다). 끌 때는 바로. */
import { num, hitLine, guessRate } from './common.js';

/** 켤 때 상자에 보여 줄 줄 */
export function restLines(ap) {
    const a = ap || {};
    const tot = (a.stats || {}).total || {};
    const g = guessRate(tot);
    return [
        '켜면 그다음 후원부터:',
        '· 투네 후원 중 확실한 것(메시지에 선수 이름 · 별명 · 늘 같은 선수)은 기계가 바로 점수를 넣어요',
        '· 애매한 투네 후원 · 계좌 입금은 화면 가장자리가 초록으로 깜빡이며 불러요 (소리 없음)',
        `· 계좌 입금 · ${num(a.assign_max || 100000)}원 이상은 기계가 절대 안 줘요`,
        '· 잘못 갔으면 평소처럼 [되돌리기] — 후원이 대기함으로 돌아와요',
        '· 방송이 끝나면 저절로 📚 학습으로 돌아가요',
        '',
        '📚 지금까지 학습 성적',
        '· ' + hitLine(tot) + ' — 휴식 때 기계가 혼자 줄 것들',
        '· ' + (g ? `기계 답 전체: ${num(g.judged)}건 중 ${num(g.hit)}건 맞힘(${g.pct}%)` : '기계 답 전체: 아직 채점된 게 없어요'),
    ];
}

/** on = true 면 휴식, false 면 학습. 바뀌었으면 true */
export async function setRest(ctx, on) {
    const ap = (ctx.slices && ctx.slices.autopilot) || {};
    if (on) {
        const ok = await ctx.confirm({ title: '☕ 휴식 모드를 켤까요?', body: restLines(ap).join('\n'), ok: '켜기', cancel: '그대로 두기', danger: false });
        if (!ok) return false;
    }
    const res = await ctx.run('auto.set', { mode: on ? 'on' : 'shadow' });
    if (res.ok) {
        ctx.toast(on ? '☕ 휴식 켬 — 확실한 투네 후원은 기계가 줘요 · 애매한 것 · 계좌 입금은 초록으로 불러요'
            : '📚 학습으로 — 점수는 사람이 줘요 · 기계는 답만 적고 채점해요', on ? 'ok' : 'info', 4000);
    }
    return !!res.ok;
}
