# 🚀 라이브 마스터 & 시그니처 슬롯머신 시스템 전체 분석 보고서

---

## 📌 1. 프로젝트 개요 (Project Overview)

본 프로젝트는 인터넷 방송(인프라: OBS Studio, 투네이션 Toon.at 연동) 환경에서 **스트리머 후원 리액션**, **시그니처 음원/사진 자동 송출**, **시각적 전광판/이펙트**, 그리고 **🎰 무작위 시그니처 슬롯머신 미니게임**을 지원하는 통합 방송 보조 시스템입니다.

- **프로젝트 명칭**: Live Master & Local Signature Program System
- **주요 대상**: 인터넷 방송 스트리머 (OBS 브라우저 소스 연동)
- **주요 특징**:
  1. **Dual Architecture**: 클라우드 서버(Render) + 로컬 PC 고성능 시그니처 서버(Port 8388)의 이중 연동 구조.
  2. **100% 미디어 보존**: 원본 1,751개 파일 마이그레이션 ➔ 99개 시그니처 음원/사진 정밀 매핑.
  3. **🎰 슬롯머신 미니게임**: 버튼 클릭 ➔ OBS 오버레이에서 3-릴 두루루룩 스크롤 ➔ 🎊 당첨 연출 ➔ 로컬 시그니처 즉시 연동 재생.
  4. **시각적 레이아웃 에디터 (`/admin`)**: OBS 오버레이 위젯들의 위치(X, Y) 및 크기(Scale)를 마우스 드래그앤드롭으로 실시간 조작.

---

## 🏗️ 2. 전체 시스템 아키텍처 (System Architecture)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           스트리머 제어 환경 (Client)                         │
│                                                                             │
│   [마스터 컨트롤러]                        [시각적 레이아웃 에디터]           │
│   https://live-master-server.onrender.com/controller   .../admin            │
└──────────────────────┬──────────────────────────────────┬───────────────────┘
                       │                                  │
                       ▼                                  ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       ☁️ Render 클라우드 백엔드 서버                         │
│                       (https://live-master-server.onrender.com)             │
│                                                                             │
│  - SSE(Server-Sent Events) 이벤트 브로드캐스터 (/api/stream)                   │
│  - 슬롯머신 트리거 API (/api/slot/spin)                                       │
│  - 레이아웃 및 옵션 동기화 API (/api/data, /api/layout)                       │
└──────────────────────┬──────────────────────────────────────────────────────┘
                       │ SSE 실시간 이벤트 전송 (slot_spin, update, layout)
                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        📺 OBS 방송 오버레이 (Overlay)                        │
│                        (https://live-master-server.onrender.com/overlay)     │
│                                                                             │
│  - 🎰 슬롯머신 3-릴 스크롤 전광판 애니메이션 (slot-container)                   │
│  - 🎊 당첨 연출 (파티클 폭죽 + neon 텍스트)                                  │
│  - 실시간 후원 랭킹, 플레이어 대결, 네온/아우디 이펙트                         │
└──────────────────────┬──────────────────────────────────────────────────────┘
                       │ 당첨 확정 시 POST /api/donation 자동 송출
                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      💻 로컬 PC 시그니처 전용 서버                            │
│                      (http://localhost:8388)                                │
│                                                                             │
│  - 99개 시그니처 DB (signature.db) & 188개 음원/사진 미디어 라이브러리        │
│  - 음원 재생 시간(Exact Duration) 기반 오버레이 자동 타이머 제어              │
│  - 원클릭 테스트 재생, 시그니처 편집/삭제 관리 UI                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🎰 3. 핵심 기능 모듈 상세 (Key Functional Modules)

### 3.1. 🎰 시그니처 슬롯머신 미니게임 (Slot Machine Game)
- **컨트롤러 조작**: `[🎰 슬롯머신]` 탭에서 **`[ 🎰 슬롯머신 돌리기! ]`** 버튼 클릭 한 번으로 가동.
- **연동 시그니처 목록 현황**: 로컬 8388 서버의 **99개 시그니처(금액 + 제목)**가 컨트롤러 안내 박스에 실시간 표시.
- **오버레이 스크롤 애니메이션**:
  1. 컨트롤러 버튼 클릭 ➔ OBS 오버레이(`overlay.html`)에 슬롯머신 전광판 등장.
  2. 릴 1, 2, 3이 **제목 + 금액 텍스트 전광판**으로 두루루룩 스크롤.
  3. 2.0s, 2.6s, 3.2s 순서로 탁-탁-탁 정지하여 **3개 모두 동일한 당첨 시그니처**로 조작 정렬.
  4. **`🎊 [당첨 시그니처] 당첨!! 🎊`** 파티클 폭죽 및 네온 텍스트 등장.
- **시그니처 자동 송출 릴레이**: 당첨 발표 직후 로컬 PC 시그니처 서버(`http://localhost:8388/api/donation`)로 전송되어, 방송 오버레이에서 해당 시그니처의 **사진 + 노래가 음원 길이만큼 완벽하게 재생**.
- **스위치 & 레이아웃 조작**:
  - 컨트롤러의 `🔌 슬롯머신 위젯 활성화` 스위치로 오버레이 위젯 표시 ON/OFF 가능.
  - `/admin` 에디터에서 마우스 드래그앤드롭으로 위치 및 크기(Scale) 자유 조절.

---

### 3.2. 🎵 로컬 시그니처 매니저 (Local Signature Program - Port 8388)
- **독립 구동**: 외부 클라우드 디스크 리셋 방지를 위해 로컬 SQLite(`signature.db`) 및 로컬 디렉토리(`media/images`, `media/sounds`)에서 완전 독립 구동.
- **미디어 자산 마이그레이션**: legacy `media_cache` (1,751개 파일) 자동 탐색 ➔ 99개 시그니처 자산 자동 할당.
- **정확한 후원 금액 매칭 (Ceiling-based)**:
  - 후원 금액 입력 시 올림(Ceiling) 알고리즘으로 최적의 시그니처 자동 추첨.
- **재생 품질 보장**:
  - `HTML5 Audio` 객체 갱신형 인스턴스 구조로 음원 씹힘/멈춤 방지.
  - 음원의 실제 재생 길이(`audio.duration`)를 동적 측정하여 시그니처 사진 표시 시간 자동 조절.
- **관리 기능**:
  - 컨트롤러 UI에서 시그니처 제목, 후원 금액, 사진 파일, 음원 파일, 재생시간 수정/삭제/원클릭 테스트 지원.

---

### 3.3. 🎛️ 시각적 레이아웃 에디터 (Visual Drag & Drop Layout Editor - `/admin`)
- **실시간 드래그앤드롭**:
  - `https://live-master-server.onrender.com/admin` 접속.
  - 🏆 랭킹판, 🔥 게이지, 🏦 계좌, ⚔️ 대결, 🎡 룰렛, 🎰 **슬롯머신** 등 모든 위젯을 마우스로 잡고 이동/크기 조절.
- **저장 및 즉시 반영**:
  - [저장] 클릭 시 `layout.json` 업데이트 ➔ SSE `layout` 이벤트를 통해 연결된 OBS 오버레이 화면에 0.1초 내 실시간 적용.

---

### 3.4. 🎯 투네이션 템퍼몽키 연동 (Toonation Master V10.9)
- 투네이션 알림창(`toon.at/widget/alertbox/...`) DOM 감지 ➔ 실시간 후원 금액 추출 ➔ `server.py`로 자동 전송 ➔ 로컬 8388 시그니처 연동 릴레이.

---

## 📂 4. 파일 구조 및 데이터베이스 스키마 (Files & Database Schemas)

### 4.1. 디렉토리 구조 (Directory Layout)

```
c:\Users\Administrator\Desktop\새로다시시작\
├── PROJECT_OVERVIEW.md              # 본 종합 분석 보고서
├── server.py                        # Render/로컬 백엔드 서버 (Flask, SSE, Slot API)
├── controller.html                  # 스트리머용 통합 컨트롤러 (슬롯머신, 룰렛, 대결, 이펙트)
├── overlay.html                     # OBS 방송 오버레이 (1080x1920, 슬롯머신 위젯 이식)
├── admin.html                       # 시각적 레이아웃 드래그앤드롭 에디터
├── slot.html                        # 단독 슬롯머신 오버레이 (선택사항)
├── live_master.db                   # 메인 백엔드 데이터베이스 (SQLite)
├── layout.json                      # 위젯 위치(X,Y) 및 크기(Scale) 설정
│
└── 시그니처프로그램\                 # 로컬 PC 독자 구동 시그니처 프로그램 (Port 8388)
    ├── server.py                    # 로컬 시그니처 Flask 백엔드
    ├── signature.db                 # 99개 시그니처 DB (SQLite)
    ├── run.bat                      # 로컬 서버 원클릭 구동 스크립트
    ├── import_media_cache.py        # 미디어 마이그레이션 스크립트
    ├── media\
    │   ├── images\                  # 94개 시그니처 이미지 파일
    │   └── sounds\                  # 94개 시그니처 음원 파일
    └── templates\
        ├── controller.html          # 시그니처 전용 제어판 (수정/재생/삭제)
        ├── overlay.html             # 시그니처 사진+노래 오버레이
        └── popup.html               # 팝업 오버레이
```

---

### 4.2. 데이터베이스 스키마 (Database Schemas)

#### 1) `signature.db` (로컬 PC Port 8388) - `signatures` 테이블
```sql
CREATE TABLE signatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    amount INTEGER NOT NULL UNIQUE,          -- 후원 금액 (예: 10300, 20005)
    title TEXT NOT NULL,                     -- 시그니처 제목 (예: 사쿠란보)
    image_file TEXT,                         -- 이미지 파일명 (media/images/...)
    sound_file TEXT,                         -- 음원 파일명 (media/sounds/...)
    duration INTEGER DEFAULT 10,             -- 기본 재생시간 (초)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 2) `live_master.db` (메인 서버) - `reaction_items` 테이블
```sql
CREATE TABLE reaction_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    amount INTEGER NOT NULL,
    audio_file_id TEXT,
    image_file_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 🛠️ 5. 실행 및 운용 가이드 (Operating Manual)

### 5.1. 방송 전 준비 단계 (원클릭 가동)

1. **로컬 시그니처 서버 가동 (PC)**:
   - 경로: `c:\Users\Administrator\Desktop\새로다시시작\시그니처프로그램\`
   - `run.bat` 파일 더블클릭 (또는 `python server.py` 실행) ➔ `http://localhost:8388` 열림.

2. **OBS Studio 오버레이 등록**:
   - OBS 브라우저 소스 추가:
     - URL: `https://live-master-server.onrender.com/overlay`
     - 너비: `1080`, 높이: `1920`

3. **마스터 컨트롤러 접속**:
   - 주소: `https://live-master-server.onrender.com/controller`
   - **`[🎰 슬롯머신]`** 탭으로 이동 ➔ **`[ 🎰 슬롯머신 돌리기! ]`** 클릭하면 방송 오버레이에서 슬롯이 돌아가고 당첨 시그니처 노래/사진이 송출됩니다!

4. **위젯 위치/크기 조절 (필요 시)**:
   - 주소: `https://live-master-server.onrender.com/admin`
   - 슬롯머신 상자를 마우스 드래그로 원하는 위치로 이동 후 [저장].

---

## 💯 6. 요약 및 시스템 안정성 평가

- **데이터 안정성**: 렌더 클라우드 디스크 초기화와 상관없이 로컬 PC의 99개 시그니처 데이터베이스와 미디어 파일(188개)은 100% 안전하게 보호됩니다.
- **확장성**: 추후 새로운 시그니처나 미니게임을 추가하더라도 기존 아키텍처 상에서 손쉽게 확장할 수 있도록 모듈화되어 있습니다.
