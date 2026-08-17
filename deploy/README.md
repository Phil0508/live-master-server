# 오라클 클라우드(서울)로 옮기기 — 실행 순서

## 왜 옮기는가

서버가 오레곤(미국 서부)에 있고 사장님·투네이션·OBS·Supabase DB 는 전부 한국에 있다.
후원 한 건이 태평양을 두 번 건넌다.

**리전은 도쿄(`ap-tokyo-1`)로 간다.** 서울이 제일 가깝지만 무료 계정의 홈 영역으로
고를 수가 없다(가입 화면에서 Korea/Seoul 둘 다 검색 결과 없음). 오라클 문서상
Always Free 자원은 **홈 영역에만** 만들 수 있고 홈 영역은 **나중에 변경 불가**라,
이 계정에서 서울 무료 인스턴스는 앞으로도 불가능하다. 그 점을 알고 도쿄를 택했다.

사장님 PC 에서 각 리전까지 실측한 왕복 시간:

| 리전 | 왕복 | |
|---|---|---|
| 오레곤 (현재) | 840ms | |
| **도쿄 (선택)** | **396ms** | 2.1배 개선 |
| 오사카 | 508ms | |
| 서울 | 282ms | 무료로는 못 씀 |

| | 오레곤(현재) | 도쿄(이전 후 예상) |
|---|---|---|
| 후원 → 화면 반영 | p50 **473ms** · p95 672ms | 150~200ms |
| 첫 접속(콜드스타트) | 50초 | 없음 |

후원마다 하는 시그니처 조회도 지금은 오레곤↔서울 왕복인데, 도쿄↔서울로 짧아진다.

## 원칙: Render 는 끄지 않는다

옮기는 동안 **Render 는 그대로 살려둔다.** 오라클이 검증될 때까지 방송은 Render 로 한다.
전환은 마지막 단계(유저스크립트 주소 + OBS 소스)뿐이고, 되돌리기도 그 두 가지만 되돌리면 된다.

> ⚠️ **두 서버를 동시에 쓰지 말 것.** 둘 다 같은 Supabase DB 를 보는데, 각자 상태를
> 메모리에 캐시한다(`MEMORY_STATE`). 양쪽에 동시에 접속하면 한쪽의 낡은 캐시가
> 다른 쪽 변경을 덮어쓴다. **후원이 들어가는 곳은 언제나 한 곳이어야 한다.**

---

## 1단계 — 오라클 계정 (사장님만 가능)

https://signup.cloud.oracle.com

- **홈 영역(Home Region)을 `Japan East (Tokyo)` 로 선택.** 나중에 변경 불가.
  아래 "홈 영역을 변경할 수 없음을 인정" 체크박스도 함께 체크해야 넘어간다.
- 카드는 본인확인용. Always Free 자원만 쓰면 청구되지 않는다.

## 2단계 — 인스턴스 만들기

Compute → Instances → Create instance

| 항목 | 값 |
|---|---|
| 이미지 | **Ubuntu 24.04** (또는 22.04) |
| Shape | **VM.Standard.A1.Flex** · **2 OCPU / 12 GB** (Always Free) |
| 네트워킹 | 퍼블릭 IP **할당** |
| SSH 키 | 새로 생성 후 **개인키 파일 저장** (다시 못 받는다) |

> A1 은 인기가 많아 "Out of host capacity" 가 자주 뜬다. 시간을 두고 재시도하거나
> `VM.Standard.E2.1.Micro`(AMD, 1GB) 로 시작해도 이 앱에는 충분하다.
> 부하 테스트 기준 이 서버는 50~75MB 만 쓴다.

## 3단계 — 방화벽 (두 군데 다 열어야 한다)

여기서 막혀서 "서버는 떴는데 접속이 안 되는" 상황이 제일 흔하다.

1. **오라클 콘솔**: VCN → Security List → Ingress Rules 추가
   - Source `0.0.0.0/0`, TCP, Destination Port **80**
   - Source `0.0.0.0/0`, TCP, Destination Port **443**
2. **서버 안**: `setup.sh` 가 iptables 를 열어준다 (자동)

## 4단계 — 설치

```bash
ssh -i <개인키> ubuntu@<퍼블릭IP>
curl -fsSL https://raw.githubusercontent.com/Phil0508/live-master-server/main/deploy/setup.sh -o setup.sh
sudo bash setup.sh
```

## 5단계 — 비밀값 채우기

```bash
sudo nano /etc/livemaster.env
```

Render 대시보드 → `live-master-server` → Environment 에서 값을 복사해 온다
(값 옆 눈 아이콘을 누르면 보인다).

| 키 | 어디서 |
|---|---|
| `DATABASE_URL` | Render 에서 복사 (같은 Supabase 를 계속 쓴다 = 데이터 그대로) |
| `SUPABASE_URL` / `SUPABASE_SECRET_KEY` | Render 에서 복사 |
| `SESSION_SECRET` | 새로 정한다. **영문·숫자만** (한글은 HTTP 헤더에 못 실어 Bearer 요청이 깨진다) |
| `NVIDIA_API_KEY` | `NVIDIA_CREDENTIALS.txt` |

```bash
sudo systemctl restart livemaster caddy
sudo journalctl -u livemaster -n 30 --no-pager
```

## 6단계 — DNS 연결

내도메인.한국 → 도메인 관리 → **IP연결(A)** 에 오라클 퍼블릭 IP 를 넣는다.

```
엔젤컴퍼니.메인.한국  →  xn--9i1b547a0ublxlz4f.xn--h32bi4v.xn--3e0b707e
```

퍼진 뒤(수 분) Caddy 가 인증서를 자동 발급한다. 확인:

```bash
sudo journalctl -u caddy -n 50 --no-pager | grep -i certificate
```

> ⚠️ `메인.한국` 은 여러 사람이 나눠 쓰는 부모 도메인이라, Let's Encrypt 의
> **등록 도메인당 주 50장** 한도에 걸려 발급이 거부될 수 있다.
> 거부되면 일반 도메인(연 1~2만원)을 하나 사서 A 레코드만 바꾸면 된다.

## 7단계 — 검증 (전환 전에 반드시)

Render 는 아직 그대로 두고, 새 주소로만 확인한다.

- [ ] `https://엔젤컴퍼니.메인.한국/controller` 로그인 · 자물쇠 표시
- [ ] 오버레이가 뜨고 **SSE 가 붙는가** (조종실에서 점수를 주면 오버레이가 즉시 바뀌는지)
- [ ] 시그니처 재생 (소리·이미지가 Supabase 에서 내려오는지)
- [ ] `/api/server/status` 에서 `persistent_storage: true`, `weak_admin_secret: false`
- [ ] 후원 1건 테스트 → 대기함 도착 → 배정 → 점수 반영
- [ ] 응답 속도 체감 (오레곤 473ms 대비)

## 8단계 — 전환 (여기부터가 되돌릴 지점)

1. **유저스크립트** — `toonation_tampermonkey.user.js` 두 곳
   - `// @connect` 줄
   - `url: "https://.../api/donation"`
   → 템퍼몽키에서 설치된 스크립트를 직접 고치고 저장
2. **OBS 브라우저 소스** 전부 새 주소로 (오버레이·슬롯·알림창·시그니처 표시)
3. **북마크** (조종실·모바일·편집기)

> 코드 안에는 주소가 박혀 있지 않다. 모든 화면이 상대 경로(`/api/...`)를 쓴다.
> 그래서 바꿀 곳은 위 세 가지뿐이다.

## ⚠️ 유휴 인스턴스 회수 — 계속 신경 써야 하는 것

오라클은 **7일간 CPU(95백분위)·네트워크·메모리가 모두 20% 미만**이면 Always Free
인스턴스를 회수한다. 주 1회 4시간 방송이면 나머지 164시간이 유휴라 정책상 대상이다.

- 그래서 **Render 를 지우지 않고 남겨둔다.** 회수되면 주소만 되돌리면 방송은 된다.
- 회수는 방송 직전에 발견하는 게 최악이므로, **방송 전날 한 번 접속해서 살아 있는지 본다.**
- 정 불안하면 Pay As You Go 로 전환하는 방법이 있다. 오라클 문서상
  "Oracle doesn't charge for Always Free resources after you upgrade" 라
  업그레이드해도 Always Free 자원은 계속 무료다.

## 되돌리기

유저스크립트 주소와 OBS 소스를 `live-master-server.onrender.com` 으로 되돌리면 끝.
Render 는 계속 살아 있고 같은 DB 를 보므로 데이터도 그대로다.

## 평소 배포

```bash
cd /opt/livemaster && sudo -u livemaster git pull && sudo systemctl restart livemaster
```

> ⚠️ 위젯 배치(`layout.json`)는 저장소에 들어 있는 파일이다. 편집기에서 위치를 바꾸면
> 서버의 그 파일이 바뀌는데, 다음 배포 때 저장소 내용으로 되돌아간다.
> (Render 도 매 배포가 새 클론이라 지금까지 똑같았다)
> 배치를 영구히 남기려면 바꾼 뒤 `layout.json` 을 커밋해야 한다.

## 자주 보는 곳

```bash
sudo journalctl -u livemaster -f      # 서버 로그 (후원 처리 과정이 다 보인다)
sudo journalctl -u caddy -f           # 인증서·프록시
sudo systemctl status livemaster
```
