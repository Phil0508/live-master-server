/* 🧠 AI 도우미 탭 — 옛 조종실 왼쪽 끝 'AI 서포트' 서랍(▶)을 탭 하나로 옮겼다. 서버 약속: v2/server/domain/ai.py '화면 약속'.
     위: 상황판 네 칸(대기함 · 대결 · 목표 · 퇴근빵) + AI 상태 점 + 이번 방송 후원 — 탭이 보일 때만 4초마다(panels/ai/board.js)
     아래: AI 에게 물어보기 — 빠른 질문(⚡ 서버 계산) · 글로 묻기(🤖 AI) · 명령 꼴은 바로 명령(panels/ai/chat.js)
     머리: [🤖 안전한 건 AI 가 바로] [🔔 알림] [지우기]  (🚗 오토파일럿은 10-22 ☕ 휴식으로 합쳐 뺐다 — panels/auto/rest.js)
       🤖 스위치(10-17, 서버 ai_opts.direct · 기본 켬) — 켜면 공지 · 한마디 · 무대 · 조명 · 순서표 · BGM 같은 '점수 · 돈과 상관없는 것' 은
       말하면 AI 가 바로 하고 [되돌리기] 를 붙인다. 끄면 전부 [실행] 카드. 점수 · 대기함 · 게임은 스위치와 상관없이 늘 [실행].
   대기함 카드의 AI 한 줄 · 추천 단추 · 먼저 알림은 이 탭을 안 열어도 돈다(panels/ai/assist.js — 대기함이 부른다).
   탭 하나 = { id, label, icon, group, mount(el, ctx) → { render(slices) } } — panels/tools.js 가 끝에 붙인다. */
import { h, setCtx } from './ai/common.js';
import { mountBoard } from './ai/board.js';
import { mountChat } from './ai/chat.js';
import * as watch from './ai/watch.js';
import * as chat from './ai/chatlog.js';

function mountAi(el, ctx) {
    setCtx(ctx);
    let chatApi = null;
    const board = mountBoard(ctx, intent => chatApi && chatApi.ask(intent));
    chatApi = mountChat(ctx, board);

    const alBtn = h('button', { type: 'button', class: 'btn sm ai-al-btn', 'aria-pressed': 'false',
        title: '큰 후원 · 대기함 밀림 · 3분째 대기 · 대결 30초 · 목표 달성을 먼저 알려 줘요 (소리 없음)',
        onclick: () => watch.toggle() });
    const dirBtn = h('button', { type: 'button', class: 'btn sm ai-dir-btn', 'aria-pressed': 'true',
        title: "켜면: 공지 · 화면에 한마디 · 무대 · 조명 · 순서표 · BGM 처럼 점수 · 돈과 상관없는 것은 말하면 AI 가 바로 해요([되돌리기] 있음).\n끄면: 전부 [실행] 을 눌러야 해요. 점수 · 대기함 · 게임은 늘 [실행].",
        onclick: async () => {
            const on = !((ctx.slices.ai_opts || {}).direct !== false);
            dirBtn.disabled = true;
            const res = await ctx.run('ai.set', { direct: on });
            dirBtn.disabled = false;
            if (res.ok) ctx.toast(on ? '🤖 안전한 건 AI 가 바로 해요 (되돌리기 있음)' : '🤖 AI 가 말한 건 전부 [실행] 을 눌러야 해요', 'info');
            paintDir();
        } });
    const paintDir = () => {
        const on = (ctx.slices.ai_opts || {}).direct !== false;
        const t = on ? '🤖 안전한 건 AI 가 바로 · 켬' : '🤖 안전한 건 AI 가 바로 · 끔';
        if (dirBtn.textContent !== t) dirBtn.textContent = t;
        dirBtn.classList.toggle('on', on);
        dirBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
    };
    paintDir();
    const clrBtn = h('button', { type: 'button', class: 'btn sm', title: '대화 내용을 지워요 (이 컴퓨터에만 있던 것)', onclick: () => chat.clear() }, '지우기');
    const paintAl = on => {
        alBtn.textContent = on ? '🔔 알림 켜짐' : '🔕 알림 꺼짐';
        alBtn.classList.toggle('on', on);
        alBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
    };
    watch.onChange(paintAl);
    paintAl(watch.isOn());

    el.classList.add('ai-panel');
    el.append(
        h('div', { class: 'ai-head' },
            h('div', { class: 'ai-title' }, h('h3', null, 'AI 도우미'), board.els.dot),
            h('div', { class: 'ai-tools' }, dirBtn, alBtn, clrBtn)),
        h('div', { class: 'ai-cols' },
            h('div', { class: 'ai-left' },
                board.els.today,
                board.els.grid,
                board.els.note,
                h('p', { class: 'ai-legend' },
                    h('span', { class: 'ai-src ai-src-calc' }, '⚡ 서버 계산'), ' 서버가 센 값 — 늘 맞아요 · ',
                    h('span', { class: 'ai-src ai-src-ai' }, '🤖 AI'), ' 말을 다듬은 답 — 가끔 틀릴 수 있어요. AI 가 점수를 바꾸려면 늘 [실행] 을 눌러야 해요.')),
            h('div', { class: 'ai-right' },
                chatApi.els.log,
                chatApi.els.quick,
                chatApi.els.row,
                chatApi.els.hint)));

    const shown = () => el.isConnected && !el.hidden && document.body.dataset.view === 'live';
    // 탭이 다시 보일 때 — 대화 맨 아래로 · 안 읽은 숫자 지우기 (숨겨져 있을 때는 높이를 못 재서 그때 내린다)
    new MutationObserver(() => {
        if (el.hidden) return;
        chatApi.scrollEnd();
        chat.readAll();
    }).observe(el, { attributes: true, attributeFilter: ['hidden'] });
    return {
        render() {
            paintDir();
            board.wake(shown);
            if (shown()) chat.readAll();
        },
    };
}

export const PANELS = [
    { id: 'ai', label: 'AI 도우미', icon: '🧠', group: 'ai', mount: mountAi },
];
