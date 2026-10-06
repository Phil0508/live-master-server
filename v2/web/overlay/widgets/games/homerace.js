/* 🏃 퇴근빵 판 — home · players 조각 + show.stage == 'home_race'. 생김새 · 규칙은 homerace_board.js(지옥탈출과 같은 판). */
import { mountRace } from './homerace_board.js';

export function mount(root, lm, opts) {
    mountRace(root, lm, opts, 'home');
}
