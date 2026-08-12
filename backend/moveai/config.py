"""애플리케이션 설정.

모든 경로/식별자는 환경변수로 교체 가능하다.
실제 로그인 연동 전까지는 DEMO_CARRIER_ID 를 현재 선사로 사용한다.
"""

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

_DEFAULT_PACKAGE = PROJECT_ROOT / "optimizer" / "AXIS_MOVEAI_MILP_v7_1_FINAL"

OPTIMIZER_PACKAGE_DIR = Path(
    os.environ.get("AXIS_PACKAGE_DIR", str(_DEFAULT_PACKAGE))
).resolve()

SCENARIO = os.environ.get("AXIS_SCENARIO", "AXIS_INTEGRATED")

RESULT_DIR = Path(
    os.environ.get(
        "AXIS_RESULT_DIR",
        str(OPTIMIZER_PACKAGE_DIR / "05_RESULTS" / SCENARIO),
    )
).resolve()

INPUT_DIR = Path(
    os.environ.get(
        "AXIS_INPUT_DIR",
        str(OPTIMIZER_PACKAGE_DIR / "03_INPUT_DATA"),
    )
).resolve()

# 로그인 연동 전 데모용 기본 선사.
DEMO_CARRIER_ID = os.environ.get("DEMO_CARRIER_ID", "CARRIER_A")

# dev mode 에서만 carrier selector 를 노출한다 (실제 선사 화면에는 없음).
DEV_MODE = os.environ.get("DEV_MODE", "true").lower() in {"1", "true", "yes"}

# 챗봇 API. 미설정 시 /api/chat 은 503 CHAT_API_NOT_CONFIGURED 를 반환한다.
CHAT_API_URL = os.environ.get("CHAT_API_URL", "").strip()
CHAT_API_KEY = os.environ.get("CHAT_API_KEY", "").strip()

CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if o.strip()
]
