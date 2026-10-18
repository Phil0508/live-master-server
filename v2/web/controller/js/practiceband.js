/* 🎓 연습 중 띠 — 연습 모드(/practice/, 10-19)가 켜져 있으면 상태 줄 경보 띠에 '🎓 연습 중 — 진짜 후원 아님 · N건' + [연습 끝].
   연습 중 진짜 후원이 들어오면 빨간 띠 '진짜 후원 N건이 들어왔어요 — 연습을 끝내 주세요'(연습 중엔 진짜 카드를 줄 수 없다).
   ⚠️ 소리는 내지 않는다(대표님 규칙). 연습이 끝나면 띠가 저절로 내려간다. */
import { bandAdd, bandRemove } from './alarm.js';

/** 순수 — practice 조각 → 띠 두 개의 모양(검사용). 없으면 null */
export function practiceBands(slices) {
    const p = (slices && slices.practice) || {};
    if (!p.on) return { main: null, real: null };
    const n = Array.isArray(p.cards) ? p.cards.length : 0;
    const main = { level: 'warn', title: '🎓 연습 중 — 진짜 후원 아님', sub: `연습 후원 ${n}건 · [연습 끝]을 누르면 연습 전으로 돌아가요` };
    const real = Number(p.real || 0) > 0
        ? { level: 'bad', title: `🚨 진짜 후원 ${Number(p.real)}건이 들어왔어요`, sub: '연습 중엔 줄 수 없어요 — 연습을 끝내면 대기함에 그대로 남아요' }
        : null;
    return { main, real };
}

// 띠는 다른 경보(🙋 확인할 후원 등)와 한 줄을 나눠 써서 '외 1건' 뒤로 숨을 수 있다 — 연습 중엔 화면 가장자리 호박색 테두리 +
// 왼쪽 아래 고정 딱지를 따로 띄워 절대 못 놓치게 한다(누르면 [연습 끝]).
let tag = null;
function paintTag(b, end) {
    if (!tag) {
        const st = document.createElement('style');
        // ⚠️ body::after 는 조종실 바탕 그림(유리 옷)이 쓴다 — 거기에 걸면 화면 전체를 덮는다(10-19 실제로 그랬다). 따로 칸을 만든다
        st.textContent = '#lm-practice-frame{position:fixed;inset:0;border:4px solid #f5a524;pointer-events:none;z-index:2147483000}'
            + '#lm-practice-tag{position:fixed;left:50%;transform:translateX(-50%);bottom:12px;max-width:calc(100% - 24px);z-index:2147483001;display:flex;align-items:center;gap:8px;padding:8px 12px;'
            + 'border-radius:12px;background:#f5a524;color:#241006;font:800 13px/1.3 Pretendard,"Malgun Gothic",sans-serif;box-shadow:0 8px 24px rgba(0,0,0,.45);border:0;cursor:pointer}'
            + '#lm-practice-tag.real{background:#ff6b6b;color:#2a0606}';
        document.head.appendChild(st);
        const fr = document.createElement('div');
        fr.id = 'lm-practice-frame'; fr.hidden = true;
        document.body.appendChild(fr);
        tag = document.createElement('button');
        tag.type = 'button'; tag.id = 'lm-practice-tag'; tag.dataset.stat = '연습 딱지';
        document.body.appendChild(tag);
    }
    document.getElementById('lm-practice-frame').hidden = !b.main;
    tag.hidden = !b.main;
    if (!b.main) return;
    tag.textContent = b.real ? b.real.title + ' · 연습 끝 누르기' : b.main.title + ' · ' + b.main.sub.split(' · ')[0];
    tag.classList.toggle('real', !!b.real);
    tag.onclick = end;
}

let last = '';
export function syncPracticeBand(slices, ctx) {
    const b = practiceBands(slices);
    const sig = JSON.stringify(b);
    if (sig === last) return;
    last = sig;
    const end = async () => {
        const ok = await ctx.confirm({ title: '연습을 끝낼까요?', body: '연습 전 판으로 돌아가요. 연습 후원 · 점수는 지워지고, 진짜 후원은 그대로 남아요.',
            ok: '연습 끝', cancel: '계속 연습', danger: false });
        if (!ok) return;
        const r = await ctx.run('practice.end', {});
        if (r && r.ok) {
            const s = r.summary || {};
            ctx.toast(`🎓 연습 끝 — ${s.cards || 0}건 중 ${s.given || 0}건 줌` + (s.checked ? ` · 정답 ${s.correct}/${s.checked}` : ''), 'ok');
        }
    };
    paintTag(b, end);
    if (b.main) bandAdd('practice', Object.assign({ act: { label: '연습 끝', fn: end } }, b.main));
    else bandRemove('practice');
    if (b.real) bandAdd('practice-real', Object.assign({ act: { label: '연습 끝', fn: end } }, b.real));
    else bandRemove('practice-real');
}
