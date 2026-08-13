/* 🔢 천단위 콤마 자동 포매터 (프로젝트 공용)
 *
 * 대상: <input data-comma> 또는 원래 type="number"였던 입력칸(자동으로 text로 전환).
 *   - 콤마가 들어가면 안 되는 칸(계좌번호·OTP·시간·초·속도 등)은 data-no-comma 를 달아 제외한다.
 *   - 앞자리 '-'(마이너스)는 보존한다 → 점수 감점 보정 같은 음수 입력이 그대로 동작.
 *
 * 값 읽기: 코드에서 el.value 대신 window.rawNum(el 또는 id) 를 쓰면 콤마 없는 정수를 얻는다.
 *   - el.dataset.raw 에도 콤마 없는 숫자 문자열이 항상 보관된다.
 *
 * 동적 생성 입력칸: MutationObserver가 DOM에 추가되는 input을 자동으로 감지해 적용한다.
 */
(function () {
    'use strict';

    // 부호 보존 + 숫자만 남기기 ("−1,200원" → "-1200")
    function clean(s) {
        s = String(s == null ? '' : s);
        var neg = /^\s*-/.test(s);
        var d = s.replace(/[^\d]/g, '');
        return (neg && d ? '-' : (neg && !d ? '-' : '')) + d;
    }
    function fmt(s) {
        var c = clean(s);
        if (c === '' || c === '-') return c;
        return Number(c).toLocaleString('en-US');
    }

    function format(el) {
        var caretFromEnd = el.value.length - (el.selectionStart == null ? el.value.length : el.selectionStart);
        var formatted = fmt(el.value);
        if (el.value !== formatted) el.value = formatted;
        el.dataset.raw = clean(formatted);
        var pos = Math.max(0, formatted.length - caretFromEnd);
        try { el.setSelectionRange(pos, pos); } catch (e) {}
    }

    function attach(el) {
        if (!el || el._commaAttached) return;
        if (el.hasAttribute('data-no-comma')) return;
        el._commaAttached = true;
        if (el.type === 'number') {
            el.type = 'text';
            if (!el.getAttribute('inputmode')) el.setAttribute('inputmode', 'numeric');
        }
        el.addEventListener('input', function () { format(el); });
        el.addEventListener('blur', function () { format(el); });
        if (el.value) format(el);
    }

    function scan(root) {
        var nodes = (root || document).querySelectorAll('input[data-comma], input[type=number]');
        for (var i = 0; i < nodes.length; i++) attach(nodes[i]);
    }

    // 전역 도우미: 콤마 없는 정수값(부호 보존)
    window.rawNum = function (elOrId) {
        var el = (typeof elOrId === 'string') ? document.getElementById(elOrId) : elOrId;
        if (!el) return 0;
        var v = parseInt(clean(el.value), 10);
        return isNaN(v) ? 0 : v;
    };
    // 프로그램적으로 값을 넣은 뒤 다시 포맷
    window.commaFormat = function (elOrId) {
        var el = (typeof elOrId === 'string') ? document.getElementById(elOrId) : elOrId;
        if (el) { attach(el); format(el); }
    };
    window.commaScan = scan;

    // 초기 스캔
    if (document.readyState !== 'loading') scan();
    else document.addEventListener('DOMContentLoaded', function () { scan(); });

    // 동적으로 추가되는 입력칸 자동 적용
    try {
        var mo = new MutationObserver(function (muts) {
            for (var m = 0; m < muts.length; m++) {
                var added = muts[m].addedNodes;
                for (var n = 0; n < added.length; n++) {
                    var node = added[n];
                    if (node.nodeType !== 1) continue;
                    if (node.matches && node.matches('input[data-comma], input[type=number]')) attach(node);
                    if (node.querySelectorAll) scan(node);
                }
            }
        });
        function startObserver() { if (document.body) mo.observe(document.body, { childList: true, subtree: true }); }
        if (document.body) startObserver();
        else document.addEventListener('DOMContentLoaded', startObserver);
    } catch (e) { /* MutationObserver 미지원 시 초기 스캔만 동작 */ }
})();
