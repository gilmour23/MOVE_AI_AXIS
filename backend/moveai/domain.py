"""도메인 상수 및 공용 헬퍼.

CSV 컬럼명은 이 계층과 selectors 계층에서만 다룬다. (핸드오프 §27)
"""

from __future__ import annotations

from datetime import datetime

# 6개 hub 는 고정이며 표시 순서도 이 순서를 따른다. (핸드오프 §13)
HUBS: list[dict[str, str]] = [
    {"code": "UIWANG", "name": "의왕ICD(오봉역)", "shortName": "의왕ICD"},
    {"code": "BUGANG", "name": "부강화물역 CY", "shortName": "부강"},
    {"code": "YAKMOK", "name": "약목역 CY", "shortName": "약목"},
    {"code": "DONGSAN", "name": "동산역 CY", "shortName": "동산"},
    {"code": "BUSAN", "name": "부산신항", "shortName": "부산신항"},
    {"code": "GWANGYANG", "name": "신광양항", "shortName": "신광양항"},
]

HUB_ORDER = [h["code"] for h in HUBS]
HUB_NAME = {h["code"]: h["name"] for h in HUBS}
HUB_SHORT_NAME = {h["code"]: h["shortName"] for h in HUBS}

CONTAINER_SIZES = ["20FT", "40FT"]

KOREAN_WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]

# 재고 모드별 CSV 컬럼 매핑. baseline = 재배치 전, postRail = 재배치 후.
MODE_COLUMNS = {
    "baseline": {
        "inventory": "baseline_inventory",
        "unmet": "baseline_unmet_demand",
        "stockout": "baseline_stockout_boxes",
        "minInventory": "minimum_baseline_inventory",
    },
    "postRail": {
        "inventory": "post_rail_inventory",
        "unmet": "post_rail_unmet_demand",
        "stockout": "post_rail_stockout_boxes",
        "minInventory": "minimum_post_rail_inventory",
    },
}


def weekday_ko(value: datetime | str) -> str:
    """datetime 또는 'YYYY-MM-DD' 문자열을 한글 요일로 변환한다 (KST 기준)."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value[:10])
    return KOREAN_WEEKDAYS[value.weekday()]


def hub_name(code: str) -> str:
    return HUB_NAME.get(code, code)


def hub_short_name(code: str) -> str:
    return HUB_SHORT_NAME.get(code, code)


def hub_sort_key(code: str) -> int:
    try:
        return HUB_ORDER.index(code)
    except ValueError:
        return len(HUB_ORDER)
