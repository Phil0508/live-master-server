/* 🧠 AI 도우미 탭 — 옛 조종실 왼쪽 끝 'AI 서포트' 서랍(▶)을 탭 하나로 옮겼다. 서버 약속: v2/server/domain/ai.py '화면 약속'.
     위: 상황판 네 칸(대기함 · 대결 · 목표 · 퇴근빵) + AI 상태 점 + 이번 방송 후원 — 탭이 보일 때만 4초마다(panels/ai/board.js)
     아래: AI 에게 물어보기 — 빠른 질문(⚡ 서버 계산) · 글로 묻기(🤖 AI) · 명령 꼴은 바로 명령(panels/ai/chat.js)
     머리: [🚗 오토파일럿] [🔔 알림] [지우기]
   대기함 카드의 배지 · '지급할까요?' · 오토파일럿 · 먼저 알림은 이 탭을 안 열어도 돈다(panels/ai/assist.js — 대기함이 부른다).
   탭 하나 = { id, label, icon, group, mount(el, ctx) → { render(slices) } } — panels/tools.js 가 끝에 붙인다. */
import { h, setCtx } from './ai/common.js';
import { mountBoard } from './ai/board.js';
import { mountChat } from './ai/chat.js';
import * as ap from './ai/autopilot.js';
import * as watch from './ai/watch.js';
import * as chat from './ai/chatlog.js';

function mountAi(el, ctx) {
    setCtx(ctx);
    let chatApi = null;
    const board = mountBoard(ctx, intent => chatApi && chatApi.ask(intent));
    chatApi = mountChat(ctx, board);

    const apBtn = h('button', { type: 'button', class: 'btn sm ai-ap-btn', 'aria-pressed': 'false',
        title: '자리 비울 때: 확실한 후원(✓ 거의 확실)만 AI 가 대신 줘요. 애매한 건 대기함에 그대로 둬요. 새로 고치면 꺼져요.',
        onclick: () => ap.toggle() });
    const alBtn = h('button', { type: 'button', class: 'btn sm ai-al-btn', 'aria-pressed': 'false',
        title: '큰 후원 · 대기함 밀림 · 3분째 대기 · 대결 30초 · 목표 달성을 먼저 알려 줘요 (소리 없음)',
        onclick: () => watch.toggle() });
    const clrBtn = h('button', { type: 'button', class: 'btn sm', title: '대화 내용을 지워요 (이 컴퓨터에만 있던 것)', onclick: () => chat.clear() }, '지우기');
    const paintAp = on => {
        apBtn.textContent = on ? '🚗 오토파일럿 켜짐 · 끄기' : '🚗 오토파일럿';
        apBtn.classList.toggle('on', on);
        apBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
    };
    const paintAl = on => {
        alBtn.textContent = on ? '🔔 알림 켜짐' : '🔕 알림 꺼짐';
        alBtn.classList.toggle('on', on);
        alBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
    };
    ap.onChange(paintAp);
    watch.onChange(paintAl);
    paintAp(ap.isOn());
    paintAl(watch.isOn());

    el.classList.add('ai-panel');
    el.append(
        h('div', { class: 'ai-head' },
            h('div', { class: 'ai-title' }, h('h3', null, 'AI 도우미'), board.els.dot),
            h('div', { class: 'ai-tools' }, apBtn, alBtn, clrBtn)),
        h('div', { class: 'ai-cols' },
            h('div', { class: 'ai-left' },
                board.els.today,
                board.els.grid,
                board.els.note,
                h('p', { class: 'ai-legend' },
                    h('span', { class: 'ai-src ai-src-calc' }, '⚡ 서버 계산'), ' 서버가 센 값 — 늘 맞아요 · ',
                    h('span', { class: 'ai-src ai-src-ai' }, '🤖 AI'), ' 말을 다듬은 답 — 가끔 틀릴 수 있어요. AI 는 점수를 절대 안 바꿔요.')),
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
            board.wake(shown);
            if (shown()) chat.readAll();
        },
    };
}

export const PANELS = [
    { id: 'ai', label: 'AI 도우미', icon: '🧠', group: 'ai', mount: mountAi },
];
