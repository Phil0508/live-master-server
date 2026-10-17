# -*- coding: utf-8 -*-
"""조각 · 명령 등록 — 불러오는 순서가 곧 방송 시작 · 끝 때 할 일의 순서다."""
from . import session  # noqa: F401
from . import players  # noqa: F401
from . import donation  # noqa: F401
from . import reaction  # noqa: F401
from . import show  # noqa: F401
from . import siggame  # noqa: F401
from . import roulette  # noqa: F401
from . import slot  # noqa: F401
from . import dicegame  # noqa: F401
from . import match  # noqa: F401
from . import quiz  # noqa: F401
from . import races  # noqa: F401
from . import extras  # noqa: F401
from . import donors  # noqa: F401
from . import media  # noqa: F401
from . import pinball  # noqa: F401
from . import ledger  # noqa: F401
from . import migrate  # noqa: F401
from . import toon_accounts  # noqa: F401
from . import legacy  # noqa: F401
from . import legacy_routes  # noqa: F401
from . import preflight  # noqa: F401
from . import announce  # noqa: F401
from . import ai_facts  # noqa: F401
from . import donor_memory  # noqa: F401
from . import ai  # noqa: F401
from . import ai_cmd  # noqa: F401  (🗣️ 말로 조종 — AI 가 명령으로 바꾸고 사람이 [실행] · 안전한 건 바로, 10-17)
from . import sigadmin  # noqa: F401
from . import more  # noqa: F401
from . import versions  # noqa: F401
from . import system  # noqa: F401
from . import settings2  # noqa: F401  (🎚️ 시그니처 보이는 모습 · 목록 개수 · 효과음 · 세이브 슬롯)
from . import lights  # noqa: F401  (💡 조명 — 네온 · 아우디 · 속도 · 색 슬롯 / ✨ 테마 연출 look.fx)
from . import autopilot  # noqa: F401  (🤖 무인 방송 — 후원 배정 · 금액 게임을 기계가: 끔 · 그림자 · 켬)
from . import endundo  # noqa: F401  (⏪ [방송 끝] 되살리기 — 끝내기 직전 조각을 장부에 · session.undo_end, sturdy 10-17)
from . import sigfx  # noqa: F401  (🎆 방송판 시그니처 미리받기 목록 · 📺 옛 /alertbox · /signature-display · /slot 이어주기)
from . import oldlayout  # noqa: F401  (📐 옛 위젯 자리 옮기기 · 🏺 모금함 깃발 왼쪽/오른쪽)
from . import cast  # noqa: F401  (💬 화면에 한마디 · ⬆ UP 자막 · 👑 조종실 후원 연출 — cast 조각)
from . import bank  # noqa: F401  (🏦 계좌 입금 추천 — 은행 확장 · 폰 앱 → 후원 콘솔 추천 카드, 옛 /api/bank/* 그대로)
from . import ops_public  # noqa: F401  (🌐 10-17 ops — 로그인 없는 바깥 주소: 시그리스트 · 오락실 순위 · 개인정보 · 약관)
from . import mask  # noqa: F401  (🙈 10-17 mask — 방송판 메시지 금칙어 · 전화 · 계좌 · 주소 ●●● · 후원마다 [가리기])
