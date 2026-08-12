"""Overview 페이지 selector (핸드오프 §15).

Overview 도 재고 페이지와 일관되도록 baseline(재배치 전) 기준으로 집계한다.
"""

from __future__ import annotations

from moveai.domain import CONTAINER_SIZES, HUBS
from moveai.result_store import ResultStore
from moveai.selectors import inventory as inv
from moveai.selectors import optimization as opt


def overview(store: ResultStore, carrier_id: str, preview_limit: int = 5) -> dict:
    matrices = {
        size: inv.weekly_matrix(store, carrier_id, size, "baseline")
        for size in CONTAINER_SIZES
    }

    by_hub: dict[str, dict] = {}
    for size, matrix in matrices.items():
        for hub in matrix["hubs"]:
            entry = by_hub.setdefault(
                hub["hubCode"],
                {
                    "hubCode": hub["hubCode"],
                    "hubName": hub["hubName"],
                    "sizes": {},
                },
            )
            daily = hub["daily"]
            entry["sizes"][size] = {
                "weekEndInventory": daily[-1]["closingInventory"] if daily else 0,
                "weeklyShortage": hub["weeklyUnmetDemand"],
                "minimumInventory": min(
                    (d["closingInventory"] for d in daily), default=0
                ),
            }

    hubs = []
    for meta in HUBS:
        entry = by_hub.get(
            meta["code"],
            {"hubCode": meta["code"], "hubName": meta["name"], "sizes": {}},
        )
        for size in CONTAINER_SIZES:
            entry["sizes"].setdefault(
                size,
                {"weekEndInventory": 0, "weeklyShortage": 0, "minimumInventory": 0},
            )
        entry["hubName"] = meta["name"]
        entry["shortName"] = meta["shortName"]
        entry["hasShortage"] = any(
            entry["sizes"][size]["weeklyShortage"] > 0 for size in CONTAINER_SIZES
        )
        hubs.append(entry)

    recommendations = opt.recommendations(store, carrier_id)

    return {
        "carrierId": carrier_id,
        "hubs": hubs,
        "recommendationPreview": recommendations[:preview_limit],
        "recommendationTotalCount": len(recommendations),
        "serviceSummary": opt.carrier_service_summary(store, carrier_id),
    }
