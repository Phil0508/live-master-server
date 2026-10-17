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
import { mountOpFx } from './ops/opfx.js';           // ✨ 이펙트 — 옛 후원 콘솔 '이펙트' 탭(조종실 후원 연출)
import { bankBadge } from './ops/bank.js';          // 🏦 아직 안 쓴 계좌 입금 수(비공개 조각 bank.new)
import { mountBot } from './ops/bot.js';
import { mountVersion } from './ops/version.js';
import { mountMigrate } from './ops/migrate.js';
import { mountSystem } from './ops/system.js';
import { mountMask } from './ops/mask.js';           // 🙈 메시지 거르기(금칙어 · 전화 · 계좌 · 주소 — 10-17)

const G = 'tools';

export const PANELS = [
    { id: 'ops-stage', label: '무대', icon: '📺', group: G, pre: true, mount: mountStage },
    { id: 'ops-notice', label: '공지', icon: '📣', group: G, pre: true, mount: mountNotice },
    { id: 'ops-console', label: '후원 콘솔', short: '후원콘솔', icon: '💸', group: G, rail: true, mount: mountConsole, badge: bankBadge },
    { id: 'ops-opfx', label: '이펙트', icon: '✨', group: G, mount: mountOpFx },
    { id: 'ops-fundjar', label: '모금함', icon: '🏺', group: G, mount: mountFundjar },
    { id: 'ops-screen', label: '계좌 · 화면', icon: '🏦', group: G, pre: true, mount: mountScreen },
    { id: 'ops-media', label: '영상 · 노래방', icon: '🎞️', group: G, mount: mountMedia },
    { id: 'ops-mask', label: '메시지 거르기', icon: '🙈', group: G, pre: true, mount: mountMask },
    { id: 'ops-bot', label: '진행봇', icon: '🤖', group: G, pre: true, mount: mountBot },
    { id: 'ops-version', label: '버전', icon: '🕹️', group: G, pre: true, mount: mountVersion },
    { id: 'ops-system', label: '시스템', icon: '🖥️', group: G, pre: true, mount: mountSystem },
    { id: 'ops-migrate', label: '옛 설정 옮기기', icon: '📦', group: G, pre: true, mount: mountMigrate },
];
