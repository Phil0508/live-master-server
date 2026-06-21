// ==UserScript==
// @name         🎯 투네이션 마스터 V10.6 (안정된 스마트 추적 & 자동 재전송)
// @namespace    http://tampermonkey.net/
// @version      10.6
// @description  애니메이션/타이핑 중 중복 전송을 완벽 방지하고, 비동기 재시도 및 오정산 방지를 지원합니다.
// @match        https://toon.at/widget/alertbox/14460fd01a5dfbeca46ec0bf85263efc*
// @noframes
// @grant        GM_xmlhttpRequest
// @connect      live-master-server.onrender.com
// @connect      127.0.0.1
// @connect      localhost
// ==/UserScript==

(function() {
    'use strict';

    if (window !== window.parent) {
        return;
    }

    console.log("🎯 [투네이션 마스터] V10.6 (안정화 연동 모드) 가동 완료!");

    setInterval(() => {
        const texts = document.querySelectorAll('.template-animated-text');

        if (texts.length < 2) {
            return;
        }

        // 1. DOM 요소 획득 및 전송 상태 체크
        const rootElement = texts[0];
        if (rootElement.getAttribute('data-v10-sent') === 'true' || rootElement.getAttribute('data-v10-sending') === 'true') {
            return;
        }

        let t1 = texts[0].innerText.trim();
        let t2 = texts[1].innerText.trim();

        if (!t1 || !t2) {
            return; // 렌더링 대기
        }

        // 2. 이름 및 금액 구분 (통화 기호, 공백, 콤마 등 제거 후 숫자로만 판별)
        const isNumericAmount = (str) => {
            const cleaned = str.replace(/[\s,원₩$]/g, '');
            return cleaned.length > 0 && /^\d+$/.test(cleaned);
        };

        let name = "";
        let amountText = "";

        if (isNumericAmount(t1) && !isNumericAmount(t2)) {
            amountText = t1;
            name = t2;
        } else if (isNumericAmount(t2) && !isNumericAmount(t1)) {
            amountText = t2;
            name = t1;
        } else {
            const numDigits = (str) => (str.match(/\d/g) || []).length;
            if (numDigits(t1) > numDigits(t2)) {
                amountText = t1;
                name = t2;
            } else {
                name = t1;
                amountText = t2;
            }
        }

        let amount = parseInt(amountText.replace(/[^\d]/g, '')) || 0;

        // 3. 메시지 파싱
        let message = "";
        const msgSpan = document.querySelector('.template-content span') || document.querySelector('.text-content span');
        if (msgSpan) {
            message = msgSpan.innerText.trim();
        }

        if (amount <= 0 || !name) {
            return;
        }

        // 4. 애니메이션/타이프라이터 텍스트 안정화 검증 (Debounce)
        const currentTextState = `${name}_${amount}_${message}`;
        const lastSeenState = rootElement.getAttribute('data-v10-last-state') || "";
        let stableTicks = parseInt(rootElement.getAttribute('data-v10-stable-ticks') || "0");

        if (currentTextState === lastSeenState) {
            stableTicks += 1;
        } else {
            stableTicks = 0; 
            rootElement.setAttribute('data-v10-last-state', currentTextState);
        }
        rootElement.setAttribute('data-v10-stable-ticks', stableTicks.toString());

        // 5번의 틱(1초) 동안 텍스트 상태가 완벽히 유지되어야 완료된 텍스트로 판정
        if (stableTicks < 5) {
            return; 
        }

        // 5. 후원 필터링 및 비동기 전송
        if (amount < 10000) {
            console.log(`🗑️ [필터 컷] ${name}님 ${amount}원 (1만원 미만 무시)`);
            rootElement.setAttribute('data-v10-sent', 'true'); 
            return;
        }

        rootElement.setAttribute('data-v10-sending', 'true');
        console.log(`📡 [서버 전송 시도] ${name}님 ${amount}원 ("${message}")`);

        const sendDonation = () => {
            const txId = (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : (Math.random().toString(36).substring(2) + Date.now().toString(36));
            GM_xmlhttpRequest({
                method: "POST",
                url: "https://live-master-server.onrender.com/api/donation",
                headers: { 
                    "Content-Type": "application/json",
                    "Authorization": "Bearer isacbin_master_key_0508" // 만약 auth_config.json에서 session_secret을 수정하셨다면 이 부분을 변경하십시오.
                },
                data: JSON.stringify({
                    name: name,
                    amount: amount,
                    message: message,
                    tx_id: txId
                }),
                onload: function(response) {
                    if (response.status === 200) {
                        console.log(`✅ [서버 전송 성공] ${name}님 ${amount}원 (TX: ${txId})`);
                        rootElement.removeAttribute('data-v10-sending');
                        rootElement.setAttribute('data-v10-sent', 'true');
                    } else {
                        console.error(`❌ [서버 응답 오류] 상태코드: ${response.status}. 3초 후 재시도합니다.`);
                        setTimeout(sendDonation, 3000);
                    }
                },
                onerror: function(err) {
                    console.error("❌ [네트워크 연결 실패] 서버 연결 오류. 5초 후 재시도합니다.", err);
                    setTimeout(sendDonation, 5000);
                }
            });
        };

        sendDonation();
    }, 200);
})();
