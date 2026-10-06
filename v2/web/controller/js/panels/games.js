/* 게임 탭 — 대결 · 룰렛 · 슬롯 · 주사위 · 시그뒤집기 · 퀴즈 · 핀볼 · 지옥탈출/퇴근빵.
   탭 하나 = { id, label, icon, group, mount(el, ctx) → { render(slices) } } — tabs.js 가 줄을 세운다.
   순서 = 옛 조종실에서 많이 누른 차례(대결 → 룰렛 → 슬롯 → 주사위 → 시그뒤집기 → 퀴즈 → 핀볼 → 지옥 · 퇴근).
   탭마다 파일 하나(panels/games/*.js) · 생김새는 css/games.css(gm-*). 공용 도구는 games/common.js. */
import { mountMatch } from './games/match.js';
import { mountRoulette } from './games/roulette.js';
import { mountSlot } from './games/slot.js';
import { mountDice } from './games/dice.js';
import { mountSiggame } from './games/siggame.js';
import { mountQuiz } from './games/quiz.js';
import { mountPinball } from './games/pinball.js';
import { mountRaces } from './games/races.js';
import { useLm } from './games/common.js';

/** 탭을 열 때 서버 시계(lm.serverNow)를 공용 도구에 건넨다 */
const withLm = mount => (el, ctx) => { useLm(ctx && ctx.lm); return mount(el, ctx); };

export const PANELS = [
    { id: 'match', label: '대결', icon: '⚔️', group: 'games', mount: withLm(mountMatch) },
    { id: 'roulette', label: '룰렛', icon: '🎡', group: 'games', mount: withLm(mountRoulette) },
    { id: 'slot', label: '슬롯머신', icon: '🎰', group: 'games', mount: withLm(mountSlot) },
    { id: 'dice', label: '주사위', icon: '🎲', group: 'games', mount: withLm(mountDice) },
    { id: 'siggame', label: '시그뒤집기', icon: '🃏', group: 'games', mount: withLm(mountSiggame) },
    { id: 'quiz', label: '퀴즈', icon: '🧩', group: 'games', mount: withLm(mountQuiz) },
    { id: 'pinball', label: '핀볼', icon: '🎱', group: 'games', mount: withLm(mountPinball) },
    { id: 'races', label: '지옥탈출 · 퇴근빵', icon: '🔥', group: 'games', mount: withLm(mountRaces) },
];
