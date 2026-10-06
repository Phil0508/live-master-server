/* 기록 · 안전 · BGM 탭 — BGM(유튜브) · 장부 · 후원자(순위 빼기) · 방송 전 점검.
   탭 하나 = { id, label, icon, group, mount(el, ctx) → { render(slices) } } — tabs.js 가 줄을 세운다.
   panels/tools.js 가 이 목록을 받아 도구 탭 끝에 붙인다.
   ⚠️ 방송 전 점검표는 방송 전 화면(이름 적기 옆)에도 저절로 보인다(alarm.js) — 이 탭은 방송 중에 다시 보는 자리다. */
import { mountBgmPanel } from './records/bgm.js';
import { mountLedger } from './records/ledger.js';
import { mountDonors } from './records/donors.js';
import { mountChecklist } from '../alarm.js';

export const PANELS = [
    { id: 'bgm', label: 'BGM', icon: '🎵', group: 'bgm', mount: (el, ctx) => mountBgmPanel(el, ctx) },
    { id: 'ledger', label: '장부', icon: '📒', group: 'records', mount: (el, ctx) => mountLedger(el, ctx) },
    { id: 'donors', label: '후원자', icon: '👑', group: 'records', mount: (el, ctx) => mountDonors(el, ctx) },
    { id: 'check', label: '점검', icon: '🛫', group: 'records', mount: (el, ctx) => mountChecklist(el, ctx) },
];
