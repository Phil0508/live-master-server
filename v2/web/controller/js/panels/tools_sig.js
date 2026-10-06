/* 💿 시그니처 관리 · 👀 방송 화면 보기 탭.
   - 시그니처 관리: 음원 · 사진 등록 · 고치기 · 지우기(되살리기) — 옛 upload.html · 후원 콘솔 '시그니처 관리'
     방송 전에도 쓰도록 따로 열리는 화면이 있다: /controller/sig.html (옛 주소 /upload 도 거기로 간다)
   - 방송 화면 보기: 옛 폰 조종실(mobile.html)의 '방송 화면' — /overlay/?monitor=1 을 작게 띄운다
   탭 하나 = { id, label, icon, group, mount(el, ctx) → { render(slices) } } — panels/tools.js 가 끝에 붙인다.
   서버: v2/server/domain/sigadmin.py · 화면: panels/sig/*.js · 생김새: css/tools_sig.css */
import { mountSigAdmin } from './sig/admin.js';
import { mountMonitor } from './sig/monitor.js';

export const PANELS = [
    { id: 'sig-admin', label: '시그니처 관리', icon: '💿', group: 'sigs', mount: mountSigAdmin },
    { id: 'sig-monitor', label: '방송 화면 보기', icon: '👀', group: 'sigs', mount: mountMonitor },
];
