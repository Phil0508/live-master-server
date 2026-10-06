/* 🤖 대기함 카드 배지 — 서버 자동 진행(autopilot)이 그 후원을 판단했으면(카드의 auto) 이 배지를 쓴다.
   panels/ai/assist.js 의 badge() 가 부른다 — 그때는 /api/audit/suggest 를 따로 안 묻는다(panels/ai/suggest.js).
     그림자 · 확실   '🤖 자동이라면 → 하율 (거의 확실) · 까닭'
     그림자 · 보류   '🤖 자동이라면 보류 — 하율로 보임 · 까닭'   /  '… — 누구 것인지 모름'
     켬 · 보류       '🤖 몰라서 보류 — 하율로 보임 · 까닭'        ← 대기함에 남은 것 = 사람이 봐야 하는 것
     켬 · 다른 까닭  '🤖 자동으로 안 줌 — 되돌려 돌아온 후원이라 사람이 다시 정해요'
     금액 게임이 걸렸으면 아랫줄에 '🎡 이 후원이면 룰렛을 돌렸을 거예요' · '🎡 룰렛을 돌렸어요 …'
   ⚠️ 바깥 글자(이름 · 까닭)는 h()/textContent 로만. */
import { h, GAMES, HELD } from './common.js';
import { josaRo } from '../ai/common.js';

const SEEN_MIN_CONF = 0.6;      // 'OO로 보임' — 옛 배지(AUDIT_MIN_CONF)와 같은 문턱

function guess(a) {
    if (!a.target || (Number(a.confidence) || 0) < SEEN_MIN_CONF) return null;
    return [' — ', h('b', null, a.target), josaRo(a.target) + ' 보임'];
}

/** a = 카드의 auto(얼린 것), hist = 지난 배정 [{name, count}] */
export function autoBadge(a, hist) {
    if (!a) return null;
    const why = a.why ? h('span', { class: 'ai-why' }, ' · ' + a.why) : null;
    let cls, main, showWhy = true;
    if (a.asking) {
        cls = 'lv-asking';
        main = ['🤖 자동 진행이 누구 것인지 보는 중…'];
        showWhy = false;
    } else if (a.retry && !a.target) {
        cls = 'lv-wait';
        main = ['⏳ AI 가 붐벼요 — 자동 진행이 곧 다시 물어봐요'];
    } else if (a.mode === 'on') {
        if (a.held && a.held !== 'unsure') {
            cls = 'lv-held';
            main = ['🤖 자동으로 안 줌 — ', HELD[a.held] || a.held, a.held_err ? ` (${a.held_err})` : ''];
            if (a.target) main.push(' · 기계 판단: ', h('b', null, a.target));
        } else {
            cls = 'lv-held';
            main = ['🤖 몰라서 보류', guess(a) || ' — 사람이 정해 주세요'];
        }
    } else if (a.act) {
        cls = 'lv-auto';
        main = ['🤖 자동이라면 → ', h('b', null, a.target), ' (거의 확실)'];
        if (a.held && a.held !== 'unsure') main.push(' — 단, ', HELD[a.held] || a.held);
    } else {
        cls = 'lv-unknown';
        main = ['🤖 자동이라면 보류', guess(a) || ' — 누구 것인지 모름'];
    }
    const g = a.game;
    const h3 = (hist || []).slice(0, 3).filter(x => x && x.name);
    return h('div', { class: 'ai-sug au-sug' },
        h('div', { class: 'ai-badge ' + cls, title: a.source ? '판단 근거: ' + a.source + ' · 자동 진행 탭에서 기록을 볼 수 있어요' : '자동 진행 탭에서 기록을 볼 수 있어요' },
            ...main, showWhy ? why : null),
        g && g.text ? h('div', { class: 'au-cgame s-' + (g.status || '') }, ((GAMES[g.game] || {}).icon || '🎮') + ' ' + g.text) : null,
        h3.length ? h('div', { class: 'ai-hist' }, '지난 배정 · ' + h3.map(x => `${x.name} ${x.count}번`).join(' · ')) : null);
}
