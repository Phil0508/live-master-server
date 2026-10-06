/* 🧰 운영 도구 탭 — 무대 · 공지 · 계좌/시작·끝 화면 · 모금함 · 고액 영상/노래방 · 후원 콘솔.
   옛 조종실(controller.html)의 방송 화면 칸 · 공지 탭 · 계좌 · 모금함 줄 · 노래방/계좌 영상 · 후원 콘솔(manual_send.html)을 옮겼다.
   탭 하나 = { id, label, icon, group, mount(el, ctx) → { render(slices) } } — tools.js 가 이 목록을 펼쳐 넣는다.
   ⚠️ 열린 탭만 그려진다(tabs.js). 각 탭은 바뀐 조각만 다시 그린다(서명 비교). */
import { mountStage } from './ops/stage.js';
import { mountNotice } from './ops/notice.js';
import { mountScreen } from './ops/screen.js';
import { mountFundjar } from './ops/fundjar.js';
import { mountMedia } from './ops/media.js';
import { mountConsole } from './ops/console.js';
import { mountBot } from './ops/bot.js';
import { mountVersion } from './ops/version.js';
import { mountMigrate } from './ops/migrate.js';
import { mountSystem } from './ops/system.js';

const G = 'tools';

export const PANELS = [
    { id: 'ops-stage', label: '무대', icon: '📺', group: G, mount: mountStage },
    { id: 'ops-notice', label: '공지', icon: '📣', group: G, mount: mountNotice },
    { id: 'ops-console', label: '후원 콘솔', icon: '💸', group: G, mount: mountConsole },
    { id: 'ops-fundjar', label: '모금함', icon: '🏺', group: G, mount: mountFundjar },
    { id: 'ops-screen', label: '계좌 · 화면', icon: '🏦', group: G, mount: mountScreen },
    { id: 'ops-media', label: '영상 · 노래방', icon: '🎞️', group: G, mount: mountMedia },
    { id: 'ops-bot', label: '진행봇', icon: '🤖', group: G, mount: mountBot },
    { id: 'ops-version', label: '버전', icon: '🕹️', group: G, mount: mountVersion },
    { id: 'ops-system', label: '시스템', icon: '🖥️', group: G, mount: mountSystem },
    { id: 'ops-migrate', label: '옛 설정 옮기기', icon: '📦', group: G, mount: mountMigrate },
];
