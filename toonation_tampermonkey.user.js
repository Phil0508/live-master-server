// ==UserScript==
// @name         🎯 투네이션 마스터 V10.8 (시그니처 캐시 돔 완벽 연동)
// @namespace    http://tampermonkey.net/
// @version      10.8
// @description  시그니처 전용 캐시 클래스(_SignatureCash_) 감지 및 시그니처 정규식 파싱을 완벽히 지원합니다.
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

    console.log("🎯 [투네이션 마스터] V10.8 (시그니처 캐시 정밀 연동) 가동 완료!");

    // 메모리 상에서 완료/처리 중 상태 추적 (DOM 재사용 시 상태 초기화 안 되는 현상 영구 방지)
    let lastSentState = "";      // 성공적으로 전송 완료된 후원 상태 (name_amount_message)
    let lastFilteredState = "";  // 필터링되어(1만원 미만 등) 스킵 처리 완료된 상태
    let sendingState = "";       // 현재 전송 처리 중인 상태
    
    let lastSeenState = "";      // 이전 프레임에서 조회된 텍스트 상태
    let stableTicks = 0;         // 텍스트 상태가 변화 없이 유지된 누적 카운트

    setInterval(() => {
        // 1. 필요한 DOM 요소 추출
        const animTexts = Array.from(document.querySelectorAll('.template-animated-text')).map(el => el.innerText.trim());
        const sigCashEl = document.querySelector('[class*="SignatureCash"]');
        const sigCashText = sigCashEl ? sigCashEl.innerText.trim() : "";

        // 텍스트 영역이 하나도 로드되지 않았으면 대기
        if (animTexts.length === 0) {
            return;
        }

        // 2. 시그니처 후원 텍스트 패턴 판별 (예: '홍길동님이 "시그니처1"을 신청하셨어요')
        const signatureRegex = /^(.+?)님이\s+["'“]?(.*?)["'”?]?(?:을|를)\s+신청하셨어요/;
        let isSignature = false;
        let sigName = "";
        let sigProduct = "";
        let matchedAnimText = "";

        for (const txt of animTexts) {
            if (signatureRegex.test(txt)) {
                const match = txt.match(signatureRegex);
                sigName = match[1].trim();
                sigProduct = match[2].trim();
                isSignature = true;
                matchedAnimText = txt;
                break;
            }
        }

        let name = "";
        let amountText = "";

        if (isSignature) {
            name = sigName;
            // 시그니처 캐시 전용 클래스 돔이 존재하면 거기서 금액을 가져옴
            if (sigCashText) {
                amountText = sigCashText;
            } else {
                // 없을 경우 차선책으로 시그니처 텍스트가 아닌 다른 애니메이션 텍스트에서 금액 파싱 시도
                const otherTexts = animTexts.filter(t => t !== matchedAnimText);
                amountText = otherTexts.length > 0 ? otherTexts[0] : "";
            }
        } else {
            // 3. 일반 후원 파싱 로직 (최소 2개 이상의 텍스트가 존재해야 함)
            if (animTexts.length < 2) {
                return;
            }
            const t1 = animTexts[0];
            const t2 = animTexts[1];

            const isNumericAmount = (str) => {
                const cleaned = str.replace(/[\s,원₩$]/g, '');
                return cleaned.length > 0 && /^\d+$/.test(cleaned);
            };

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
        }

        let amount = parseInt(amountText.replace(/[^\d]/g, '')) || 0;

        // 4. 메시지 파싱
        let message = "";
        const msgSpan = document.querySelector('.template-content span') || document.querySelector('.text-content span');
        if (msgSpan) {
            message = msgSpan.innerText.trim();
        }

        // 시그니처 상품 정보가 있으면 메시지 영역에 동봉
        if (isSignature && sigProduct) {
            message = `[시그니처 신청: ${sigProduct}]` + (message ? ` ${message}` : "");
        }

        if (amount <= 0 || !name) {
            return;
        }

        // 현재 추출된 후원 텍스트 상태 키 생성
        const currentTextState = `${name}_${amount}_${message}`;

        // 5. 전송 락 및 중복 정산 검증 (메모리 락 검사)
        if (currentTextState === lastSentState || currentTextState === lastFilteredState || currentTextState === sendingState) {
            return;
        }

        // 6. 애니메이션/타이프라이터 텍스트 안정화 검증 (Debounce)
        if (currentTextState === lastSeenState) {
            stableTicks += 1;
        } else {
            stableTicks = 0; 
            lastSeenState = currentTextState;
        }

        // 5번의 틱(1초) 동안 텍스트 상태가 변화 없이 고정되어야 완료된 데이터로 신뢰
        if (stableTicks < 5) {
            return; 
        }

        // 7. 후원 필터링 (1만원 미만 무시)
        if (amount < 10000) {
            console.log(`🗑️ [필터 컷] ${name}님 ${amount}원 (1만원 미만 무시) - 상태: ${currentTextState}`);
            lastFilteredState = currentTextState; // 필터 락 등록
            return;
        }

        // 8. 서버로 비동기 후원 접수 전송
        sendingState = currentTextState;
        console.log(`📡 [서버 전송 시도] ${name}님 ${amount}원 ("${message}")`);

        const sendDonation = () => {
            const txId = (typeof crypto !== 'undefined' && crypto.randomUUID) ? crypto.randomUUID() : (Math.random().toString(36).substring(2) + Date.now().toString(36));
            GM_xmlhttpRequest({
                method: "POST",
                url: "https://live-master-server.onrender.com/api/donation",
                headers: { 
                    "Content-Type": "application/json",
                    "Authorization": "Bearer isacbin_master_key_0508"
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
                        lastSentState = currentTextState; // 전송 완료 락 등록
                        sendingState = ""; // 전송 중 락 해제
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
