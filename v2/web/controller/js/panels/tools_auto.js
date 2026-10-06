/* 🤖 자동 진행(무인 방송) 탭 — 대표님 10-07 "모든 걸 맡기고 쉴 정도의 자동화".
   서버 약속: v2/server/domain/autopilot.py 맨 위(조각 autopilot · 명령 auto.set · auto.games · auto.reset_stats).
     위: 모드 스위치 끔 · 👀 그림자 · 🤖 켬(켬은 그림자 기록 — 맞힌 비율을 먼저 보여 주고 한 번 묻는다) · AI 에게도 묻기
     숫자: 이번 방송 · 전체 — 맞힘 · 틀림 · 몰라서 보류 · 자동으로 줌
     기록: 최근 60건 — 기계 판단 · 까닭 · 사람이 한 일 · 금액 게임
     금액 → 게임 줄 고치기
   대기함 카드의 '🤖 자동이라면 …' 배지는 이 탭을 안 열어도 보인다(panels/auto/badge.js — panels/ai/assist.js 가 부른다).
   머리줄 '🤖 그림자 · 켬' 표시는 panels/auto/pill.js(header.js 가 붙인다).
   탭 하나 = { id, label, icon, group, mount(el, ctx) → { render(slices) } } — panels/tools.js 가 끝에 붙인다. */
import { h } from '../util.js';
import { mountMode } from './auto/mode.js';
import { mountStats } from './auto/stats.js';
import { mountLog } from './auto/log.js';
import { mountRules } from './auto/rules.js';

function mountAuto(el, ctx) {
    const mode = mountMode(ctx);
    const stats = mountStats(ctx);
    const log = mountLog(ctx);
    const rules = mountRules(ctx);
    el.classList.add('ops', 'au-panel');
    // 넓은 화면: 기록(왼쪽) · 금액 게임(오른쪽) / 좁은 화면: 위아래
    el.append(mode.el, stats.el, h('div', { class: 'au-cols' }, log.el, rules.el));
    return {
        render(slices) {
            const ap = slices.autopilot || {};
            // 하나가 넘어져도 나머지는 그려지게 따로 감싼다
            for (const [name, part] of [['모드', () => mode.render(ap)], ['숫자', () => stats.render(ap)],
                ['기록', () => log.render(ap, slices)], ['금액 게임', () => rules.render(ap)]]) {
                try { part(); } catch (e) { console.error('[자동 진행 ' + name + ']', e); }
            }
        },
    };
}

export const PANELS = [
    { id: 'auto', label: '자동 진행', icon: '🤖', group: 'ai', mount: mountAuto },
];
