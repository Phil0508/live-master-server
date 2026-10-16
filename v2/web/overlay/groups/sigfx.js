/* 층 표 묶음 — 🎆 시그니처 전용 연출 · 🚨 계엄령 경보 · 🔊 자동재생 경고 띠 · 🖼️ 출연진 전광판.
   layers.js 와 같은 모양의 칸 목록. layers.js 가 이 목록을 이어 붙인다(이 파일만 고치면 된다).

   층(z) — 옛 방송판의 겹침 그대로:
     시그니처 카드 · 'OO업' 50 < 전용 연출 55(옛 #sigfx-stage 101005) < 계엄령 경보 58(옛 #op-fx-warn 101011) < 경고 띠 60(옛 alertbox 999999)
     ⚠️ 56 · 57 은 비워 둔다 — 옛 후원 콘솔 '이펙트'(번쩍 101000 · 충격파 101008 · 글리치 101009 · 전체 카드 101010)를 옮길 때 그 사이에 넣는다.
   viewOnly — 그 화면(?only=…)에서만 만든다. 평소 방송판에는 없다.

   📺 따로 띄우는 화면(VIEWS) — 같은 방송판에서 일부 칸만 보인다. 옛 주소는 서버가 이리로 넘긴다(v2/server/domain/sigfx.py).
     /overlay/?only=alert   옛 /alertbox — 후원 카드 · 소액 띠 · 시그니처(소리 · '다 틀었다' 포함) · 전용 연출 · 계엄령 · 자동재생 경고 띠
     /overlay/?only=sig     옛 /signature-display — 시그니처 그림만(출연진 전광판, 소리 없음). native = 1080×1920 으로 줄이지 않고 창 크기 그대로
     /overlay/?only=slot    옛 /slot — 슬롯머신만(방송판과 같은 자리 · 소리는 시그니처 대기줄이 방송판에서 낸다)
     kind = 서버 연결 이름표(조종실 시스템 칸 · 점검표가 '방송판' 과 따로 센다). */
export const LAYERS = [
    // 🎆 전용 연출 무대 — 캔버스 전체(연출이 판 크기를 재서 세로로 옮겨 그린다)
    { id: 'sigfx',     widget: 'sigfx/stage',   z: 55, x: 0,   y: 0,  w: 1080, h: 1920 },
    // 🚨 계엄령 붉은 경보 — 캔버스 전체
    { id: 'sigWarn',   widget: 'sigfx/warn',    z: 58, x: 0,   y: 0,  w: 1080, h: 1920 },
    // 🔊 자동재생 차단 경고 띠 — 맨 위 한가운데(옛 alertbox top 20px). 알림창 화면에만
    { id: 'sigUnlock', widget: 'sigfx/unlock',  z: 60, x: 540, y: 20, anchor: 'tc', viewOnly: true },
    // 🖼️ 출연진 전광판 카드 — 창 한가운데(native 화면이라 카드가 스스로 가운데에 선다)
    { id: 'sigDisp',   widget: 'sigfx/sigdisp', z: 50, x: 0,   y: 0,  viewOnly: true },
];

export const VIEWS = {
    alert: { kind: 'alertbox', layers: ['donation', 'smallDon', 'signature', 'sigfx', 'sigWarn', 'sigUnlock'] },
    sig:   { kind: 'sigdisp',  layers: ['sigDisp'], native: true },
    slot:  { kind: 'slot',     layers: ['slot'] },
};
