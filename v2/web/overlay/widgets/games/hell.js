/* 🔥 지옥탈출 판 — hell · players 조각 + show.stage == 'hell'. 생김새 · 규칙은 homerace_board.js(퇴근빵 판에 지옥 옷). */
import { mountRace } from './homerace_board.js';

export function mount(root, lm, opts) {
    mountRace(root, lm, opts, 'hell');
}
