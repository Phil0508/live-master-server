# 🖥️🍎 윈도우·맥 양쪽에서 작업하기

사장님: *"상황에 따라 양쪽에서 작업하고 싶어."*

방송 서버는 리눅스(Vultr 서울)에서 돌고, 코드는 전부 깃허브에 있습니다.
어느 쪽 컴퓨터에서 고치든 `main` 에 올리면 2분 안에 방송 서버에 반영됩니다.

## 맥에서 처음 시작할 때

```bash
# ⚠️ 클론하기 '전에' 이것부터. 아래 '줄바꿈' 항목을 꼭 읽어주세요.
git config --global core.autocrlf input

git clone https://github.com/Phil0508/live-master-server.git
cd live-master-server
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python tests/runall.py        # 40항목. 아무 설정 없이 돌아야 정상입니다
```

## ⚠️ 줄바꿈 — 여기가 제일 위험합니다

이 저장소는 **파일마다 줄바꿈이 다릅니다.**

| 파일 | 줄바꿈 |
|---|---|
| `server.py` · `controller.html` · `admin.html` | CRLF |
| `overlay.html` | LF + **NULL 바이트 2개** |
| `deploy/*.sh` · `deploy/*.service` | LF 고정 (`.gitattributes` 가 강제) |

`core.autocrlf` 가 맞지 않으면 파일이 **통째로 바뀐 것처럼** 보이고, 실제로 줄바꿈이
뒤집힌 적이 있습니다. `.gitattributes` 에 `* text=auto` 를 넣지 마세요 —
`overlay.html` 의 NULL 바이트 때문에 git 이 그 파일을 바이너리로 다루고 있고,
전체 정규화를 켜면 그게 깨집니다.

## 저장소에 없는 것 — 직접 옮겨야 합니다

- `NVIDIA_CREDENTIALS.txt` — AI 검사·오토파일럿
- `SUPABASE_CREDENTIALS.txt` — 시그니처 저장소
- `layout.json` — 방송 화면 배치 (서버가 스스로 씁니다)

없어도 대부분의 작업과 검사는 됩니다.

## 서버 접속

```bash
ssh live      # ~/.ssh/config 에 등록해 두면 비밀번호 없이
```

맥에서는 키를 새로 만들어 서버에 한 번 넣어야 합니다:

```bash
ssh-keygen -t ed25519 -C "livemaster-mac"
cat ~/.ssh/id_ed25519.pub | ssh root@141.164.51.198 \
  "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```

그리고 `~/.ssh/config` 에:

```
Host live
    HostName 141.164.51.198
    User root
    IdentityFile ~/.ssh/id_ed25519
    ServerAliveInterval 30
```

## 검사가 어디서 도는가

검사는 **임시 폴더**에 서버 사본을 만들어 돌립니다 (`/tmp/livemaster-sandbox`).
저장소를 더럽히지 않고, 저장소가 git 이라는 사실에도 영향받지 않습니다.
다른 곳에 두고 싶으면 `LM_SANDBOX` 로 바꿉니다.

검사가 저장소를 찾는 순서는 ① `LM_PROJECT_ROOT` ② 파일 위치에서 위로 올라가기 입니다.
그래서 저장소 안에서든 밖으로 복사해서든 똑같이 돕니다.
