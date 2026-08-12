"""MILP 결과 → 정적 JSON 내보내기.

백엔드 API가 계산해서 내려주던 것과 **완전히 동일한 응답**을 파일로 뽑는다.
selectors 를 그대로 재사용하므로 화면에 표시되는 숫자는 동적 배포와 같다.

MILP 를 재실행해 05_RESULTS 가 갱신되면 이 스크립트를 다시 돌린 뒤 커밋한다.

    python scripts/export_static.py

핵심 원칙 (핸드오프 §10):
  현재 선사로 필터링·집계한 결과만 내보낸다.
  정적 배포에서는 내보낸 파일이 곧 공개이므로 타 선사 데이터가 섞이면 안 된다.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from moveai import config  # noqa: E402
from moveai.domain import CONTAINER_SIZES, HUBS  # noqa: E402
from moveai.result_store import store  # noqa: E402
from moveai.selectors import inventory as inv  # noqa: E402
from moveai.selectors import optimization as opt  # noqa: E402
from moveai.selectors import overview as ov  # noqa: E402

OUT_ROOT = PROJECT_ROOT / "frontend" / "public" / "data"
MODES = ["baseline", "postRail"]

# 내보낼 선사. 여러 선사를 배포하려면 여기에 추가한다.
# (각 선사는 자기 데이터만 담긴 파일을 받는다)
CARRIERS = [config.DEMO_CARRIER_ID]

_written: list[Path] = []


def write(relative: str, payload) -> None:
    path = OUT_ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=None, separators=(",", ":")),
        encoding="utf-8",
    )
    _written.append(path)


def build_meta() -> dict:
    """동적 배포의 /api/meta 와 같은 구조.

    정적 배포에는 dev mode carrier selector 가 없으므로 항상 꺼둔다.
    """
    summary = store.summary
    timeline = store.inventory_timeline
    candidate_source = summary.get("candidate_timetable_source")
    carrier_source = summary.get("carrier_data_source")

    return {
        "scenario": summary.get("scenario"),
        "horizonStart": timeline["timestamp"].min().isoformat(),
        "horizonEnd": timeline["timestamp"].max().isoformat(),
        "horizonDates": inv.horizon_dates(store),
        "carrierDataSource": carrier_source,
        "candidateTimetableSource": candidate_source,
        "isSyntheticCarrierData": carrier_source == "SYNTHETIC_CARRIER_LEVEL_DATA",
        "isPrototypeTimetable": candidate_source == "PROTOTYPE_SYNTHETIC",
        "allStagesProvenOptimal": bool(summary.get("all_stages_proven_optimal")),
        "carrierKorailViewConsistent": bool(
            summary.get("carrier_korail_view_consistent")
        ),
        "selectedTrainCount": summary.get("selected_train_count"),
        "recommendationCount": summary.get("recommendation_count"),
        "hubs": HUBS,
        "currentCarrierId": config.DEMO_CARRIER_ID,
        "devMode": False,
        "availableCarriers": [],
    }


def export_carrier(carrier_id: str) -> None:
    base = f"carrier/{carrier_id}"

    write(f"{base}/overview.json", ov.overview(store, carrier_id))

    write(
        f"{base}/optimization.json",
        {
            "carrierId": carrier_id,
            "needs": opt.service_needs(store, carrier_id),
            "recommendations": opt.recommendations(store, carrier_id),
            "impacts": opt.inventory_impacts(store, carrier_id),
            "serviceSummary": opt.carrier_service_summary(store, carrier_id),
        },
    )

    for size in CONTAINER_SIZES:
        for mode in MODES:
            write(
                f"{base}/inventory/{size}_{mode}.json",
                inv.weekly_matrix(store, carrier_id, size, mode),
            )
            for hub in HUBS:
                write(
                    f"{base}/inventory/{hub['code']}_{size}_{mode}_summary.json",
                    inv.hub_summary(store, carrier_id, hub["code"], size, mode),
                )

    for rec in opt.recommendations(store, carrier_id):
        rec_id = rec["recommendationId"]
        detail = opt.recommendation_detail(store, carrier_id, rec_id)
        write(f"{base}/optimization/recommendations/{rec_id}.json", detail)


def verify_no_other_carriers() -> None:
    """내보낸 파일에 다른 선사 식별자가 없는지 검증한다."""
    allowed = set(CARRIERS)
    others = [c for c in store.known_carriers() if c not in allowed]
    leaked: list[str] = []

    for path in _written:
        text = path.read_text(encoding="utf-8")
        for other in others:
            if other in text:
                leaked.append(f"{path.relative_to(OUT_ROOT)} <- {other}")

    if leaked:
        raise SystemExit(
            "타 선사 데이터가 포함되었습니다:\n  " + "\n  ".join(leaked)
        )
    print(f"  격리 검증 통과 (검사 대상 선사: {', '.join(others)})")


def main() -> None:
    health = store.health()
    if not health["ok"]:
        raise SystemExit(f"결과 파일 없음: {health['missing']}")

    if OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)

    write("meta.json", build_meta())
    for carrier_id in CARRIERS:
        export_carrier(carrier_id)

    verify_no_other_carriers()

    total = sum(p.stat().st_size for p in _written)
    print(f"  {len(_written)}개 파일 / {total / 1024:.1f} KB")
    print(f"  출력 위치: {OUT_ROOT}")


if __name__ == "__main__":
    main()
