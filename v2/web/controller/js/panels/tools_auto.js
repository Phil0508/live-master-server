/* 📚 학습 · ☕ 휴식 탭 — 대표님 10-22 "이정도야": 평소엔 📚 학습(기계도 답을 적고 채점), 자리 비울 땐 ☕ 휴식(확실한 투네는 기계가 준다).
   서버 약속: v2/server/domain/autopilot.py 맨 위(조각 autopilot · 명령 auto.set · auto.games · auto.reset_stats).
     위: 📚 학습 · ☕ 휴식 고르기(휴식은 켤 때 한 번 묻는다 — panels/auto/rest.js, 머리줄 [☕ 휴식] 과 같은 길) · 고급(접어 둠)
     📚 학습 성적: 오늘 · 전체 — 기계 답 맞힘 · 확실했던 것 · 몰라서 · 휴식 때 준 것 / 지난 방송(그날마다)
     기록: 최근 60건 — 기계 답 · 까닭 · 사람이 한 일
     금액 → 게임(지금 안 씀) — 맨 아래 접어 둔다
   대기함 카드의 '📚 기계 답 …' 배지는 이 탭을 안 열어도 보인다(panels/auto/badge.js — panels/ai/assist.js 가 부른다).
   머리줄 '☕ 휴식 중' 표시는 panels/auto/pill.js(header.js 가 붙인다).
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
    el.append(mode.el, stats.el, log.el,
        h('details', { class: 'au-adv au-adv-games' }, h('summary', null, '금액 → 게임 자동 (지금 안 써요 — ☕ 휴식일 때만 움직여요)'), rules.el));
    return {
        render(slices) {
            const ap = slices.autopilot || {};
            // 하나가 넘어져도 나머지는 그려지게 따로 감싼다
            for (const [name, part] of [['모드', () => mode.render(ap)], ['숫자', () => stats.render(ap)],
                ['기록', () => log.render(ap, slices)], ['금액 게임', () => rules.render(ap)]]) {
                try { part(); } catch (e) { console.error('[학습 · 휴식 ' + name + ']', e); }
            }
        },
    };
}

export const PANELS = [
    { id: 'auto', label: '학습 · 휴식', short: '학습', icon: '📚', group: 'ai', mount: mountAuto },
];
