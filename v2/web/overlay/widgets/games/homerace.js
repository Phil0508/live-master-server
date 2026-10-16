/* 🏃 퇴근빵 판 — home · players 조각(home.on — 무대 아님, race_view.js). 생김새 · 규칙은 homerace_board.js(지옥탈출과 같은 판). */
import { mountRace } from './homerace_board.js';

export function mount(root, lm, opts) {
    mountRace(root, lm, opts, 'home');
}
