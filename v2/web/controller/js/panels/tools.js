/* 도구 탭 — 공지 · 계좌 · 무대 · 시작/끝 화면 · 모금함 · 고액 영상 · 노래방 · 후원 순위 빼기 · 장부 · 방송 전 점검.
   탭 하나 = { id, label, icon, group, mount(el, ctx) → { render(slices) } } — tabs.js 가 줄을 세운다. */
import { PANELS as OPS } from './tools_ops.js';
import { PANELS as RECORDS } from './tools_records.js';
import { PANELS as MORE } from './tools_more.js';
import { PANELS as SIGS } from './tools_sig.js';
import { PANELS as FX } from './tools_fx.js';          // 💡 조명(네온 · 아우디 · 속도 · 색 9칸) — 시그니처 탭 옆
import { PANELS as AI } from './tools_ai.js';          // 🧠 AI 도우미(상황판 · 물어보기 · 오토파일럿)
import { PANELS as AUTO } from './tools_auto.js';      // 🤖 자동 진행(무인 방송 — 끔 · 그림자 · 켬 · 금액 게임)

export const PANELS = [...OPS, ...RECORDS, ...MORE, ...SIGS, ...FX, ...AI, ...AUTO];
