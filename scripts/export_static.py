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
from moveai.selectors import korail as kr  # noqa: E402
from moveai.selectors import optimization as opt  # noqa: E402
from moveai.selectors import overview as ov  # noqa: E402
from moveai.selectors import transport as tr  # noqa: E402

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

    # Rail vs Truck 비교 — rail 값은 canonical, truck 값만 data/ 입력
    write(f"{base}/transport_comparison.json", tr.transport_comparison(store, carrier_id))


def export_korail() -> None:
    """KORAIL Control Tower — 운영자 관점이므로 전 선사 배정을 포함한다."""
    write("korail/overview.json", kr.overview(store))
    write("korail/trains.json", {"trains": kr.trains(store)})
    write("korail/service_needs.json", kr.service_needs(store))
    write("korail/inventory.json", kr.hub_inventory(store))
    write("korail/station_operations.json", kr.station_operations(store))
    write("korail/insights.json", kr.operational_insights(store))

    for train in kr.trains(store):
        train_id = train["trainId"]
        write(f"korail/train_details/{train_id}.json", kr.train_detail(store, train_id))


def verify_consistency() -> None:
    """Single Source of Truth 정합성 검증.

    Σ Recommendation TEU == Σ Carrier Allocation TEU
                         == Σ Train Assigned TEU
                         == Rail Served TEU
    """
    summary = store.summary
    recs = store.all_recommendations
    alloc = store.carrier_allocation
    ops = store.train_operation_summary

    rec_teu = int(recs["quantity_teu"].sum())
    alloc_teu = int(alloc["teu"].sum())
    train_teu = int(ops["assigned_teu"].sum())
    served_teu = int(summary["rail_served_teu"])

    print("\n  [정합성] TEU 4중 검증")
    print(f"    Recommendation TEU  = {rec_teu}")
    print(f"    Allocation TEU      = {alloc_teu}")
    print(f"    Train Assigned TEU  = {train_teu}")
    print(f"    Rail Served TEU     = {served_teu}")

    if not (rec_teu == alloc_teu == train_teu == served_teu):
        raise SystemExit(
            f"TEU 불일치: rec={rec_teu} alloc={alloc_teu} "
            f"train={train_teu} served={served_teu}"
        )

    selected = set(ops["train_id"])
    rec_trains = set(recs["train_id"])
    if not rec_trains <= selected:
        raise SystemExit(f"선정 열차에 없는 train_id: {rec_trains - selected}")
    print(f"    recommendation train_id ⊆ 선정 열차 {sorted(selected)}  OK")

    # 열차별 allocation 합 == train assigned TEU
    per_train = alloc.groupby("train_id")["teu"].sum()
    for _, r in ops.iterrows():
        expected = int(r["assigned_teu"])
        actual = int(per_train.get(r["train_id"], 0))
        if expected != actual:
            raise SystemExit(
                f"{r['train_id']} allocation 합 {actual} != assigned {expected}"
            )
    print("    열차별 allocation 합 == assigned TEU  OK")


def verify_transport_join() -> None:
    """Transport 비교가 canonical recommendation 과 정확히 join 되는지 검증."""
    for carrier_id in CARRIERS:
        payload = tr.transport_comparison(store, carrier_id)
        rec_ids = {r["recommendationId"] for r in opt.recommendations(store, carrier_id)}
        row_ids = {r["recommendationId"] for r in payload["rows"]}

        if rec_ids != row_ids:
            raise SystemExit(
                f"{carrier_id} transport join 불일치: "
                f"누락={rec_ids - row_ids} 초과={row_ids - rec_ids}"
            )

        missing = payload["missingTruckComparison"]
        if missing:
            print(f"    경고: 트럭 비교값 없는 recommendation {missing}")

        # rail 측 값이 canonical 과 같은지 재확인
        raw = store.recommendations(carrier_id).set_index("recommendation_id")
        for row in payload["rows"]:
            src = raw.loc[row["recommendationId"]]
            assert row["boxes"] == int(src["quantity_boxes"])
            assert row["teu"] == int(src["quantity_teu"])
            assert row["trainId"] == src["train_id"]
            assert row["originHub"] == src["origin_hub"]
            assert row["destinationHub"] == src["destination_hub"]
            assert abs(row["railChargeKrw"] - float(src["estimated_rail_charge_krw"])) < 0.01

        print(f"    {carrier_id} transport join {len(row_ids)}건 · rail 값 canonical 일치  OK")


def verify_no_other_carriers() -> None:
    """내보낸 파일에 다른 선사 식별자가 없는지 검증한다."""
    allowed = set(CARRIERS)
    others = [c for c in store.known_carriers() if c not in allowed]
    leaked: list[str] = []

    # carrier/ 이하만 검사한다.
    # korail/ 은 운영자 관점이므로 전 선사 배정을 포함하는 것이 정상이다.
    checked = 0
    for path in _written:
        if "carrier" not in path.relative_to(OUT_ROOT).parts[:1]:
            continue
        checked += 1
        text = path.read_text(encoding="utf-8")
        for other in others:
            if other in text:
                leaked.append(f"{path.relative_to(OUT_ROOT)} <- {other}")

    if leaked:
        raise SystemExit(
            "선사 포털 파일에 타 선사 데이터가 포함되었습니다:\n  "
            + "\n  ".join(leaked)
        )
    print(f"\n  [격리] carrier/ {checked}개 파일에 {', '.join(others)} 미포함  OK")


def main() -> None:
    health = store.health()
    if not health["ok"]:
        raise SystemExit(f"결과 파일 없음: {health['missing']}")

    if OUT_ROOT.exists():
        shutil.rmtree(OUT_ROOT)

    write("meta.json", build_meta())
    for carrier_id in CARRIERS:
        export_carrier(carrier_id)
    export_korail()

    verify_consistency()
    print("\n  [Transport]")
    verify_transport_join()
    verify_no_other_carriers()

    total = sum(p.stat().st_size for p in _written)
    carrier_files = sum(1 for p in _written if "carrier" in p.relative_to(OUT_ROOT).parts[:1])
    korail_files = sum(1 for p in _written if "korail" in p.relative_to(OUT_ROOT).parts[:1])
    print(
        f"\n  {len(_written)}개 파일 / {total / 1024:.1f} KB"
        f"  (carrier {carrier_files} · korail {korail_files})"
    )
    print(f"  출력 위치: {OUT_ROOT}")


if __name__ == "__main__":
    main()
