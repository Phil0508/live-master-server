/* 🔌 연결 표시 — ?debug=1 일 때만 칸이 생긴다(layers.js debugOnly). 상태 · 쪽지 번호(seq) · 마지막으로 받은 때. */
export function mount(root, lm, opts) {
    root.innerHTML = '<div class="conn-pill connecting"><span class="conn-dot"></span><span class="conn-text">연결 중</span></div>';
    const pill = root.firstElementChild;
    const text = root.querySelector('.conn-text');
    let st = 'connecting', last = 0;
    const LABEL = { live: '연결됨', connecting: '연결 중', down: '끊김' };
    function draw() {
        pill.className = 'conn-pill ' + st;
        const ago = last ? Math.round((Date.now() - last) / 1000) + '초 전' : '-';
        text.textContent = (LABEL[st] || st) + ' · seq ' + lm.seq + ' · ' + ago + (opts.monitor ? ' · 미리보기' : '');
    }
    lm.onStatus(s => { st = s; draw(); });
    lm.on('*', () => { last = Date.now(); draw(); });
    setInterval(draw, 1000);
    draw();
}
