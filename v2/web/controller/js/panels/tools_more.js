/* 운영 더하기 탭 — ✂️ 클립 · 📊 많이 누른 것 · 🗓️ 월별 순위(+ 조종실 클릭 세기).
   탭 하나 = { id, label, icon, group, mount(el, ctx) → { render(slices) } } — panels/tools.js 가 끝에 붙인다.
   🎛️ 스트림덱 단추판은 탭이 아니라 따로 연 페이지(/streamdeck/) — 클립 탭에 여는 길이 있다.
   ⚠️ 클릭 세기는 탭을 안 열어도 돌아야 한다(조종실 전체를 센다) — 이 파일을 불러올 때 한 번 건다.
      세기는 지켜보기만 하고 무엇도 막지 않는다(panels/more/uistats.js). */
import { mountClip } from './more/clip.js';
import { mountUiStats, installClickStats } from './more/uistats.js';
import { mountMonthly } from './more/monthly.js';

try { installClickStats(); } catch (e) { console.error('[클릭 기록]', e); }

export const PANELS = [
    { id: 'monthly', label: '월별 순위', icon: '🗓️', group: 'records', mount: (el, ctx) => mountMonthly(el, ctx) },
    { id: 'clip', label: '클립', icon: '✂️', group: 'more', mount: (el, ctx) => mountClip(el, ctx) },
    { id: 'uistats', label: '누른 것', icon: '📊', group: 'more', mount: (el, ctx) => mountUiStats(el, ctx) },
];
