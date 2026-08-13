"""애플리케이션 설정.

모든 경로/식별자는 환경변수로 교체 가능하다.
실제 로그인 연동 전까지는 DEMO_CARRIER_ID 를 현재 선사로 사용한다.
"""

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_DIR.parent
PROJECT_ROOT = BACKEND_DIR.parent

# UI 가 읽는 결과 정본. 이 아래에 주차별 폴더(W01_2025-07-01, W02_2025-07-08)가 있다.
#
# optimizer/AXIS_MOVEAI_MILP_v7_1_FINAL 은 MILP 패키지로 그대로 보존하지만
# 그 안의 05_RESULTS/AXIS_INTEGRATED (2026-08 합성 스냅샷)는 더 이상 UI 정본이 아니다.
_DEFAULT_RESULT_ROOT = PROJECT_ROOT / "reference_data" / "JULY_W1W2_RESULTS"

RESULT_ROOT = Path(
    os.environ.get("AXIS_RESULT_ROOT", str(_DEFAULT_RESULT_ROOT))
).resolve()

# MILP 패키지 경로 — 결과를 읽지 않고 코드/문서 참조용으로만 남긴다.
OPTIMIZER_PACKAGE_DIR = Path(
    os.environ.get(
        "AXIS_PACKAGE_DIR",
        str(PROJECT_ROOT / "optimizer" / "AXIS_MOVEAI_MILP_v7_1_FINAL"),
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
