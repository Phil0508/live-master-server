// ==UserScript==
// @name         🎯 투네이션 마스터 V10.9 (실시간 정밀 디버깅 로그 탑재)
// @namespace    http://tampermonkey.net/
// @version      10.9
// @description  시그니처 및 일반 캐시 후원 감지 시 디버그 로그를 상세히 출력하여 인식이 안 되는 구간을 명확히 추적합니다.
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

    console.log("🎯 [투네이션 마스터] V10.9 (실시간 디버깅 모드) 가동 완료!");

    let lastSentState = "";      
    let lastFilteredState = "";  
    let sendingState = "";       
    
    let lastSeenState = "";      
    let stableTicks = 0;         

    setInterval(() => {
        // 1. 필요한 DOM 요소 추출
        const animTexts = Array.from(document.querySelectorAll('.template-animated-text')).map(el => el.innerText.trim());
        const sigCashEl = document.querySelector('[class*="SignatureCash"]');
        const sigCashText = sigCashEl ? sigCashEl.innerText.trim() : "";

        // 텍스트 영역이 감지되었을 때 디버깅 로그 출력
        if (animTexts.length > 0) {
            console.log(`🔍 [감지 로그] 텍스트 노드 개수: ${animTexts.length} | 시그니처 돔 존재: ${!!sigCashEl} ("${sigCashText}")`);
            console.log(`  ▶ 텍스트 목록:`, animTexts);
        } else {
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
            if (sigCashText) {
                amountText = sigCashText;
            } else {
                const otherTexts = animTexts.filter(t => t !== matchedAnimText);
                amountText = otherTexts.length > 0 ? otherTexts[0] : "";
            }
            console.log(`  ⭐ [시그니처 판정] 이름: ${name} | 금액 텍스트 후보: ${amountText} | 상품명: ${sigProduct}`);
        } else {
            // 일반 후원 파싱 로직 (최소 2개 이상의 텍스트가 존재해야 함)
            if (animTexts.length < 2) {
                console.log(`  ⚠️ [일반 후원 대기] 텍스트가 2개 미만이라 파싱을 보류합니다.`);
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
            console.log(`  👤 [일반 후원 판정] 이름 후보: ${name} | 금액 후보: ${amountText}`);
        }

        let amount = parseInt(amountText.replace(/[^\d]/g, '')) || 0;

        // 4. 메시지 파싱
        let message = "";
        const msgSpan = document.querySelector('.template-content span') || document.querySelector('.text-content span');
        if (msgSpan) {
            message = msgSpan.innerText.trim();
        }

        if (isSignature && sigProduct) {
            message = `[시그니처 신청: ${sigProduct}]` + (message ? ` ${message}` : "");
        }

        console.log(`  📝 [최종 파싱 데이터] 이름: ${name} | 금액: ${amount}원 | 메시지: "${message}"`);

        if (amount <= 0 || !name) {
            console.log(`  ❌ [데이터 오류] 금액 또는 이름이 올바르지 않아 중단합니다.`);
            return;
        }

        const currentTextState = `${name}_${amount}_${message}`;

        // 5. 전송 락 및 중복 정산 검증 (메모리 락 검사)
        if (currentTextState === lastSentState || currentTextState === lastFilteredState || currentTextState === sendingState) {
            console.log(`  🔒 [락 검증] 이미 처리되었거나 처리 중인 상태입니다. 무시합니다. (State: ${currentTextState})`);
            return;
        }

        // 6. 애니메이션/타이프라이터 텍스트 안정화 검증 (Debounce)
        if (currentTextState === lastSeenState) {
            stableTicks += 1;
            console.log(`  ⏳ [안정화 진행 중] 동일 상태 유지 틱: ${stableTicks}/5`);
        } else {
            stableTicks = 0; 
            lastSeenState = currentTextState;
            console.log(`  🔄 [상태 변화 감지] 새로운 상태로 틱 초기화: ${currentTextState}`);
        }

        if (stableTicks < 5) {
            return; 
        }

        // 7. 후원 필터링 (1만원 미만 무시)
        if (amount < 10000) {
            console.log(`  🗑️ [필터 컷] 1만원 미만 후원은 서버로 전송하지 않고 필터 락 처리합니다. (금액: ${amount}원)`);
            lastFilteredState = currentTextState; 
            return;
        }

        // 8. 서버로 비동기 후원 접수 전송
        sendingState = currentTextState;
        console.log(`  📡 [서버 전송 트리거] ${name}님 ${amount}원 전송 프로세스 가동`);

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
                        console.log(`  ✅ [서버 전송 성공] ${name}님 ${amount}원 (TX: ${txId})`);
                        lastSentState = currentTextState; 
                        sendingState = ""; 
                    } else {
                        console.error(`  ❌ [서버 응답 오류] 상태코드: ${response.status}. 3초 후 재시도합니다.`);
                        setTimeout(sendDonation, 3000);
                    }
                },
                onerror: function(err) {
                    console.error("  ❌ [네트워크 연결 실패] 서버 연결 오류. 5초 후 재시도합니다.", err);
                    setTimeout(sendDonation, 5000);
                }
            });
        };

        sendDonation();
    }, 200);
})();
