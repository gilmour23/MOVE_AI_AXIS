"""
현재 PROPOSAL 결과로부터 챗봇 협의 예시 JSON 을 생성한다.

v6.1 은 예시 JSON 의 proposal_uuid 가 하드코딩되어 있어 PROPOSAL 을 재생성하면
전부 stale 이 되었다. v7 은 실제 산출물에서 생성하므로 항상 유효하다.

생성 시나리오 (모든 action 유형을 1회 이상 포함):
    ACCEPT_SERVICE       서비스 수준 수락 (열차는 KORAIL 재배정 가능)
    ACCEPT_EXACT_PLAN    현재 source/train 까지 고정 수락
    MODIFY_SERVICE       수량·기한·source 조건 동시 수정
    REJECT_OPTION        이 옵션만 거절, 대안 탐색
    DECLINE_RAIL_SERVICE 이번 rail service 자체 거절
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def build(proposals_csv: Path, out: Path, negotiation_round: int = 2):
    with proposals_csv.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise SystemExit(f"no proposals in {proposals_csv}")

    rows.sort(key=lambda r: (r["carrier_id"], r["proposal_id"]))
    actions = []

    def ref(r):
        return {"proposal_id": r["proposal_id"], "proposal_uuid": r["proposal_uuid"],
                "proposal_version": int(r["proposal_version"])}

    # 현실적인 협의 라운드를 만든다.
    #
    # 모든 제안에 action 을 거는 것은 비현실적이며, 특히 다수 제안을 동시에
    # 거절·수정하면 남은 수락 물량을 싣던 열차가 최소 consolidation 요건을 잃어
    # "확정된 commitment 를 동시에 만족시킬 수 없는" 상태가 만들어진다.
    # (v7 은 이 경우 죽지 않고 COMMITMENT_NOT_SIMULTANEOUSLY_FEASIBLE 을 반환한다.)
    #
    # 데모용 기본 시나리오: 대부분 PENDING 으로 두고
    # 선사 한 곳씩만 대표 action 을 수행한다. 5개 action 유형을 모두 포함한다.
    by_carrier = {}
    for r in rows:
        by_carrier.setdefault(r["carrier_id"], []).append(r)
    carriers = sorted(by_carrier)

    plan = ["ACCEPT_SERVICE", "ACCEPT_EXACT_PLAN", "MODIFY_SERVICE",
            "REJECT_OPTION", "DECLINE_RAIL_SERVICE"]
    for idx, c in enumerate(carriers):
        props = by_carrier[c]
        kind = plan[idx % len(plan)]
        # 각 선사의 대표 제안 1건에만 action 을 건다
        target = max(props, key=lambda r: int(r["quantity"]))
        if kind == "MODIFY_SERVICE":
            q = max(int(target["quantity"]) - 1, 1)
            if q == int(target["quantity"]):
                kind = "ACCEPT_SERVICE"
            else:
                actions.append({**ref(target), "action": "MODIFY_SERVICE",
                                "constraints": {"quantity": q}, "commit": False})
                continue
        if kind in ("ACCEPT_SERVICE", "ACCEPT_EXACT_PLAN",
                    "REJECT_OPTION", "DECLINE_RAIL_SERVICE"):
            actions.append({**ref(target), "action": kind})

    obj = {"negotiation_round": negotiation_round, "proposal_actions": actions}
    out.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")

    counts = {}
    for a in actions:
        counts[a["action"]] = counts.get(a["action"], 0) + 1
    print(f"{out.name}: {len(actions)} actions {counts}")
    return obj


def build_accept_all(proposals_csv: Path, out: Path, negotiation_round: int = 2):
    with proposals_csv.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    obj = {"negotiation_round": negotiation_round, "proposal_actions": [
        {"proposal_id": r["proposal_id"], "proposal_uuid": r["proposal_uuid"],
         "proposal_version": int(r["proposal_version"]), "action": "ACCEPT_SERVICE"}
        for r in rows]}
    out.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{out.name}: {len(obj['proposal_actions'])} ACCEPT_SERVICE")
    return obj


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--proposals", required=True)
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args()
    d = Path(a.outdir)
    d.mkdir(parents=True, exist_ok=True)
    build(Path(a.proposals), d / "CHATBOT_MIXED_NEGOTIATION.json")
    build_accept_all(Path(a.proposals), d / "CHATBOT_ACCEPT_ALL_SERVICE.json")
