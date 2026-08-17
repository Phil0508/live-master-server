# Vultr 서울로 옮기기 — 실행 순서

## 📍 지금 어디까지 왔나 (2026-08-18)

서버는 다 섰고 검증도 끝났다. **남은 것은 후원 유입을 새 서버로 돌리는 것뿐이다.**

끝난 것: 서울 인스턴스 · HTTPS · SSE · Supabase 연결 · 8080 노출 차단 ·
상태 페이지(`/health`) · OBS `브라우저 3` 주소 변경 · 공개 기본 비밀번호 차단.

남은 것 네 가지 — **순서를 지켜야 한다.**

### 1. Render 에 `ADMIN_PASSWORD` 를 넣는다 ← 지금 로그인이 잠겨 있다

공개된 기본값 `0508` 을 서버가 거부하도록 바꿨기 때문에, 이걸 넣기 전에는
**Render 조종실에 아무도 못 들어간다(본인 포함).** 후원 유입·오버레이·SSE 는
영향 없다. Render → `live-master-server` → Environment → Edit → + Add.

### 2. 서울 서버를 최신 코드로 올린다

```bash
cd /opt/livemaster && sudo -u livemaster git fetch origin main && sudo -u livemaster git reset --hard origin/main && systemctl restart livemaster
```

이걸 해야 `/health` 와 `OTP_MASTER_CODE` 가 새 서버에서도 동작한다.
(원한다면 `/etc/livemaster.env` 에 `OTP_MASTER_CODE=...` 도 함께 추가)

### 3. 템퍼몽키 유저스크립트를 고친다 ← 이게 전환의 핵심

저장소 파일은 이미 바꿔놨지만, **템퍼몽키에 설치된 사본은 따로 고쳐야 한다.**
이걸 안 하면 후원은 계속 Render 로 들어간다. 고칠 곳은 두 줄(7단계 참고).

### 4. OBS 에서 `브라우저 3` 을 켜고 `브라우저 5` 를 끈다

> ⚠️ **3번보다 먼저 하면 안 된다.** 두 서버가 각자 상태를 메모리에 들고 있어서
> (`MEMORY_STATE`), 후원은 Render 로 들어가는데 화면만 서울을 보면
> **오버레이에 후원이 아예 안 뜬다.** 반드시 3번 다음이다.
>
> 지금은 `브라우저 3`(운영)이 꺼져 있고 `브라우저 5`(dev)가 켜져 있다.
> 둘 다 켜면 오버레이가 겹치므로 하나만 켤 것.

---

## 왜 옮기는가

서버가 오레곤(미국 서부)에 있고 사장님·투네이션·OBS·Supabase DB 는 전부 한국에 있다.
후원 한 건이 태평양을 두 번 건넌다.

사장님 PC 에서 각 후보까지 실측한 왕복 시간(TCP 핸드셰이크, 5회 중앙값):

| 후보 | 왕복 | |
|---|---|---|
| **Vultr 서울 (선택)** | **6.2ms** | |
| AWS 라이트세일 서울 | 5.6ms | 콘솔이 복잡해 제외 |
| Vultr 도쿄 | 36.0ms | 오라클로 가려던 곳 |
| Vultr 오사카 | 64.3ms | |
| 싱가포르 | 71.5ms | Render 유료의 한계 |

| | 오레곤(현재) | 서울(이전 후 예상) |
|---|---|---|
| 후원 → 화면 반영 | p50 **473ms** · p95 672ms | 100ms 안팎 |
| 첫 접속(콜드스타트) | 50초 | 없음 |

후원마다 하는 시그니처 조회도 지금은 오레곤↔서울 왕복인데, 서울 안에서 끝난다.

> 처음에는 오라클 클라우드 무료 티어(도쿄)로 가려 했으나 가입이 막혔다.
> 결과적으로 잘된 일이다 — 오라클 무료는 서울을 고를 수 없어 도쿄가 최선이었는데,
> Vultr 서울은 그보다 **6배 가깝고**, 7일 유휴 시 인스턴스를 회수하는 정책도 없다.
> 값은 월 $6 (약 8,000원).

## 원칙: Render 는 끄지 않는다

옮기는 동안 **Render 는 그대로 살려둔다.** 새 서버가 검증될 때까지 방송은 Render 로 한다.
전환은 마지막 단계(유저스크립트 주소 + OBS 소스)뿐이고, 되돌리기도 그 두 가지만 되돌리면 된다.

> ⚠️ **두 서버를 동시에 쓰지 말 것.** 둘 다 같은 Supabase DB 를 보는데, 각자 상태를
> 메모리에 캐시한다(`MEMORY_STATE`). 양쪽에 동시에 접속하면 한쪽의 낡은 캐시가
> 다른 쪽 변경을 덮어쓴다. **후원이 들어가는 곳은 언제나 한 곳이어야 한다.**

---

## 1단계 — 서버 만들기 (Vultr 콘솔)

Products → Compute → **Deploy Server**

| 항목 | 값 |
|---|---|
| 종류 | **Cloud Compute – Shared CPU** |
| CPU | Regular (Intel) — 제일 싸고 이 앱엔 충분 |
| Location | **Seoul** |
| Image | **Ubuntu 24.04 LTS x64** |
| Plan | **1 vCPU / 1 GB / 25 GB** (월 $6) |
| Auto Backups | **끈다** (월 $1.20 추가된다) |
| Hostname / Label | `livemaster` 등 알아볼 이름 |

> 부하 테스트 기준 이 서버는 메모리를 50~75MB 만 쓴다. 1GB 로 넉넉하다.

만들어지면 서버 상세 페이지에 **IP 주소**와 **root 비밀번호**가 나온다
(비밀번호는 눈 아이콘을 눌러야 보인다). 둘 다 적어둔다.

> Vultr 는 Firewall Group 을 따로 지정하지 않으면 포트가 열려 있다.
> 오라클처럼 콘솔에서 80/443 을 여는 절차가 **없다.**
>
> ⚠️ 그 말은 **모든 포트가 열려 있다**는 뜻이기도 하다. 앱이 쓰는 8080 이
> 인터넷에 그대로 노출돼 Caddy(HTTPS)를 건너뛰는 우회로가 생긴다 — 실제로 그랬다.
> `BIND_HOST=127.0.0.1` 이 그것을 막는다(5단계). 빼먹지 말 것.

## 2단계 — 접속

윈도우 PowerShell 을 열고:

```
ssh root@<IP주소>
```

처음 접속하면 `yes` 를 한 번 입력하고, 그 다음 root 비밀번호를 붙여넣는다.
(붙여넣어도 화면에는 아무것도 안 보인다. 정상이다.)

## 3단계 — 설치

```
curl -fsSL https://raw.githubusercontent.com/Phil0508/live-master-server/main/deploy/setup.sh -o setup.sh
sudo bash setup.sh
```

패키지 설치·코드 내려받기·파이썬 환경·서비스 등록·HTTPS(Caddy)까지 한 번에 끝난다.
여러 번 돌려도 안전하다.

## 4단계 — 비밀값 채우기

```
nano /etc/livemaster.env
```

Render 대시보드 → `live-master-server` → Environment 에서 값을 복사해 온다
(값 옆 눈 아이콘을 누르면 보인다).

| 키 | 어디서 |
|---|---|
| `DATABASE_URL` | Render 에서 복사 (같은 Supabase 를 계속 쓴다 = 데이터 그대로) |
| `SUPABASE_URL` / `SUPABASE_SECRET_KEY` | Render 에서 복사 |
| `SESSION_SECRET` | 새로 정한다. **영문·숫자만** (한글은 HTTP 헤더에 못 실어 Bearer 요청이 깨진다). 서버에서 `openssl rand -hex 24` |
| `ADMIN_PASSWORD` | 새로 정한다. ⚠️ **비워두면 기본값 `0508`** 이 쓰인다 (`server.py:142`) |
| `NVIDIA_API_KEY` | `NVIDIA_CREDENTIALS.txt` |
| `BIND_HOST` | **`127.0.0.1` 고정.** 없으면 8080 이 인터넷에 열려 HTTPS 를 우회당한다 |

> 2단계 인증(OTP)은 환경변수가 아니라 저장소의 `auth_config.json` 에서 온다.
> 거기 `totp_secret` 이 커밋돼 있어 **새 서버에서도 지금 쓰는 OTP 앱이 그대로 된다.**
> `TOTP_SECRET` 환경변수를 넣으면 그 값이 이기므로 건드리지 말 것.

### 🔑 OTP 마스터 코드

OTP 앱을 꺼내기 번거로울 때 쓰는 예비 열쇠다. `OTP_MASTER_CODE` 에 넣은 값을
로그인 화면의 **OTP 칸에 그대로 치면** 통과한다.

```
OTP_MASTER_CODE=원하는코드
```

> ⚠️ **값을 코드에 적지 않는다.** 이 저장소는 공개(public)라 소스에 적는 순간
> 누구나 읽을 수 있는 열쇠가 된다. 그래서 환경변수로만 받는다. 비워두면 기능이 꺼진다.
>
> ⚠️ 이 코드는 **두 번째 자물쇠를 통째로 대신한다.** 짧고 뻔한 값(생일·`0508` 등)을
> 쓰면 2단계 인증이 사실상 없는 것과 같아진다. 그래도 쓰겠다면 최소한
> `ADMIN_PASSWORD` 만은 길고 어렵게 둬야 한다 — 그게 유일하게 남는 자물쇠가 된다.
>
> 마스터 코드로 로그인하면 서버 로그에 접속 IP 와 함께 남는다.
> `journalctl -u livemaster | grep 마스터` 로 남이 썼는지 확인할 수 있다.

지금은 OTP 칸을 **비워두면 그냥 통과**한다(원래 동작). 잠그려면:

```
REQUIRE_OTP=1
```

> ⚠️ 켜기 전에 OTP 앱이나 마스터 코드로 **로그인이 되는지 먼저 확인할 것.**
> 확인 없이 켜면 방송 직전에 조종실에 못 들어가는 사고가 난다.

`Ctrl+O` → `Enter` 로 저장, `Ctrl+X` 로 나온다.

```
systemctl restart livemaster caddy
journalctl -u livemaster -n 30 --no-pager
```

## 5단계 — DNS 연결

내도메인.한국 → 도메인 관리 → **IP연결(A)** 에 Vultr 서버 IP 를 넣는다.

```
엔젤컴퍼니.메인.한국  →  xn--9i1b547a0ublxlz4f.xn--h32bi4v.xn--3e0b707e
```

퍼진 뒤(수 분) Caddy 가 인증서를 자동 발급한다. 확인:

```
journalctl -u caddy -n 50 --no-pager | grep -i certificate
```

> ⚠️ `메인.한국` 은 여러 사람이 나눠 쓰는 부모 도메인이라, Let's Encrypt 의
> **등록 도메인당 주 50장** 한도에 걸려 발급이 거부될 수 있다.
> 거부되면 일반 도메인(연 1~2만원)을 하나 사서 A 레코드만 바꾸면 된다.

## 6단계 — 검증 (전환 전에 반드시)

Render 는 아직 그대로 두고, 새 주소로만 확인한다.

- [ ] `https://엔젤컴퍼니.메인.한국/controller` 로그인 · 자물쇠 표시
- [ ] 오버레이가 뜨고 **SSE 가 붙는가** (조종실에서 점수를 주면 오버레이가 즉시 바뀌는지)
- [ ] 시그니처 재생 (소리·이미지가 Supabase 에서 내려오는지)
- [ ] `/api/server/status` 에서 `persistent_storage: true`, `weak_admin_secret: false`
- [ ] 후원 1건 테스트 → 대기함 도착 → 배정 → 점수 반영
- [ ] 응답 속도 체감 (오레곤 473ms 대비)

## 7단계 — 전환 (여기부터가 되돌릴 지점)

1. **유저스크립트** — `toonation_tampermonkey.user.js` (저장소 파일은 이미 바꿔뒀다)
   템퍼몽키에 **설치된** 스크립트는 따로 고쳐야 한다. 저장소 파일 내용을 그대로
   덮어쓰는 것이 가장 안전하다.
   - `@connect` 에 퓨니코드 도메인이 있는지
   - `url:` 이 새 주소인지
   → 되돌릴 때는 `url:` 한 줄만 아래 주석과 맞바꾸면 된다 (`@connect` 는 둘 다 넣어뒀다)

   > ⚠️ 한글 도메인은 **퓨니코드로** 적는다. 브라우저가 요청 직전에 어차피 그 형태로
   > 바꾸는데, 한글 그대로 두면 `@connect` 대조에 실패해 후원 전송이 통째로 막힌다.
   > `==UserScript==` 블록 안에 주석을 넣는 것도 금물이다.
2. **OBS 브라우저 소스** 전부 새 주소로 (오버레이·슬롯·알림창·시그니처 표시)
3. **북마크** (조종실·모바일·편집기)

> 코드 안에는 주소가 박혀 있지 않다. 모든 화면이 상대 경로(`/api/...`)를 쓴다.
> 그래서 바꿀 곳은 위 세 가지뿐이다.

## 되돌리기

유저스크립트 주소와 OBS 소스를 `live-master-server.onrender.com` 으로 되돌리면 끝.
Render 는 계속 살아 있고 같은 DB 를 보므로 데이터도 그대로다.

## 평소 배포

```
cd /opt/livemaster && sudo -u livemaster git pull && systemctl restart livemaster
```

> ⚠️ 위젯 배치(`layout.json`)는 저장소에 들어 있는 파일이다. 편집기에서 위치를 바꾸면
> 서버의 그 파일이 바뀌는데, 다음 배포 때 저장소 내용으로 되돌아간다.
> (Render 도 매 배포가 새 클론이라 지금까지 똑같았다)
> 배치를 영구히 남기려면 바꾼 뒤 `layout.json` 을 커밋해야 한다.

## 자주 보는 곳

```
journalctl -u livemaster -f      # 서버 로그 (후원 처리 과정이 다 보인다)
journalctl -u caddy -f           # 인증서·프록시
systemctl status livemaster
```

## ⚠️ 유료 서버라서 새로 생긴 것

- **결제가 끊기면 서버가 멈춘다.** Vultr 는 잔액이 떨어지면 인스턴스를 정지하고,
  그대로 두면 삭제한다. 잔액 알림 메일을 무시하지 말 것.
- 오라클과 달리 **유휴 회수는 없다.** 안 써도 꺼지지 않는다.
- Render 를 폴백으로 남겨두므로, 최악의 경우에도 주소만 되돌리면 방송은 된다.
