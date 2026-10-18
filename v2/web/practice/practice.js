/* 🧪🎓 테스트 · 연습 페이지의 순수 함수(화면 없이) — node 로 검사한다(v2/tests/test_practice_page.py). */

// 화면 테스트 단추 — sig: true 면 '시그 고르기'에서 고른 금액을 쓴다
export const PRESETS = [
    { key: 'small', emo: '💬', label: '소액 5,000원', sub: '맨 위 소액 띠 · 띵동', body: { name: '귤까는중', amount: 5000, message: '사탕 대신 귤 드려요 ㅎㅎ', via: 'toon' } },
    { key: 'ten', emo: '💰', label: '1만 원', sub: '가운데 후원 카드', body: { name: '밤샘요정', amount: 10000, message: '오늘도 화이팅!', via: 'toon' } },
    { key: 'sig', emo: '🎵', label: '고른 시그니처', sub: '아래에서 고른 금액으로', sig: true, body: { name: '시그요정', message: '시그니처 보고 싶어요', via: 'toon' } },
    { key: 'big', emo: '🔥', label: '10만 원', sub: '큰 후원 연출', body: { name: '큰손등장', amount: 100000, message: '다들 고생 많아요!', via: 'toon' } },
    { key: 'huge', emo: '👑', label: '100만 원', sub: '가장 큰 카드', body: { name: '전설의후원자', amount: 1000000, message: '오늘 방송 최고!', via: 'toon' } },
    { key: 'title', emo: '💎', label: '칭호 + Lv', sub: '투네이션 공식 칭호 알약', body: { name: '다이아회원', amount: 50000, message: '칭호 테스트', via: 'toon', title: { name: '블랙노블레스' }, level: 37 } },
    { key: 'bundle', emo: '×3', label: '같은 사람 ×3', sub: '묶음 · [N번 다 틀기] 확인', sig: true, body: { name: '연속후원러', message: '한 번 더!', via: 'toon', count: 3 } },
    { key: 'bank', emo: '🏦', label: '계좌 입금 모양', sub: '투네 딱지 없이', body: { name: '계좌손님', amount: 30000, message: '계좌로 보냈어요', via: '' } },
    { key: 'long', emo: '📜', label: '긴 이름 · 긴 메시지', sub: '넘치는지 · 줄바꿈 확인',
        body: { name: '아주아주긴닉네임을쓰는시청자님', amount: 20000, via: 'toon',
            message: '오늘 방송 처음부터 끝까지 다 봤어요 정말 재밌었고 다음 주에도 꼭 올게요 멤버분들 다들 너무 고생 많으셨어요 사랑합니다 화이팅' } },
    { key: 'mask', emo: '🙈', label: '금칙어 메시지', sub: '전화번호 가림 확인', body: { name: '가림확인', amount: 10000, message: '연락 주세요 010-1234-5678', via: 'toon' } },
    { key: 'anon', emo: '👤', label: '익명', sub: '이름 없는 후원', body: { name: '', amount: 10000, message: '익명으로 응원해요', via: 'toon' } },
];

/** 단추 → 요청 몸통(시그 고르기 금액 반영) */
export function presetBody(p, sigAmount) {
    const b = JSON.parse(JSON.stringify(p.body));
    if (p.sig) b.amount = Number(sigAmount) || 20000;
    return b;
}

/** 몰아치기 — n건(1~20), gap 초(0.5~10). 여러 모양을 번갈아. [{body, wait(ms)}] */
export function burstPlan(n, gap, sigAmount) {
    const N = Math.max(1, Math.min(20, Math.floor(Number(n) || 1)));
    const G = Math.max(0.5, Math.min(10, Number(gap) || 1));
    const cycle = ['ten', 'small', 'sig', 'big', 'small', 'title', 'ten', 'bank'];
    const out = [];
    for (let i = 0; i < N; i++) {
        const p = PRESETS.find(x => x.key === cycle[i % cycle.length]);
        const b = presetBody(p, sigAmount);
        b.name = (b.name || '시청자') + (i + 1);
        out.push({ body: b, wait: Math.round(G * 1000) });
    }
    return out;
}

/** 연습 요약 → 화면 글 */
export function summaryLines(s) {
    s = s || {};
    const tiles = [
        { k: '연습 후원', v: (s.cards || 0) + '건' },
        { k: '멤버에게 줌', v: (s.given || 0) + '건' },
        { k: '무시', v: (s.ignored || 0) + '건' },
        { k: '정답(기록과 같음)', v: s.checked ? `${s.correct || 0} / ${s.checked}` : '—' },
        { k: '평균 걸린 시간', v: s.avg_sec != null ? s.avg_sec + '초' : '—' },
        { k: '연습 시간', v: (s.minutes || 0) + '분' },
    ];
    if (s.jar) tiles.splice(2, 0, { k: '모금함', v: s.jar + '건' });
    if (s.left) tiles.push({ k: '안 준 채 남음', v: s.left + '건' });
    const misses = (s.misses || []).map(m => `${m.name || '익명'} ${Number(m.amount || 0).toLocaleString('ko-KR')}원 — 기록은 ${m.expect}, 준 사람 ${(m.got || []).join(' · ') || '없음'}`);
    return { tiles, misses };
}

/** '밍밍, 행복한걸 예지랑' → ['밍밍', '행복한걸', '예지랑'] (겹침 · 빈칸 빼고 10명까지) */
export function parseNames(text) {
    const out = [];
    for (const w of String(text || '').split(/[,\s·/]+/)) {
        const n = w.trim();
        if (n && !out.includes(n)) out.push(n);
    }
    return out.slice(0, 10);
}
