"""
AXIS MOVE-AI MILP v7.1 — Joint Multi-Carrier Optimization

AXIS 는 각 선사가 제출한 거점별·시간별·규격별 공컨 재고·수요·공급 계획과
KORAIL 의 운행 가능한 철도 서비스 후보를 통합하여, 복수 선사의 공컨 재배치 수요를
하나의 MILP 에서 공동 최적화한다.

    Carrier A..F  자체 Inventory / Demand / Supply 제출
                    +
    KORAIL Operational Inputs (운행가능 시간대·경로·열차후보·편성조건·선로자원)
                    ↓
            Joint Multi-Carrier MILP   (one-shot)
                    ↓
    Carrier Recommendation   +   KORAIL Integrated Train Operation Plan

두 산출물은 서로 다른 최적화 결과가 아니라 **동일 solution 의 두 관점**이다.

v7.1 에서 제거한 것
-------------------
PROPOSAL → NEGOTIATION → FINAL 상태기계와 그에 딸린
ACCEPT / DECLINE / MODIFY / REJECT_OPTION / commitment / proposal_version /
negotiation_round / counterproposal / stale proposal 처리를 전부 제거했다.
협상은 상용화 단계의 운영 프로세스이며 이번 연구 범위가 아니다.
(참고 구현은 future_extensions/negotiation_legacy/ 에 보관)

핵심 원칙
---------
- 선사별 공컨 ownership 엄격 유지. A 재고는 A 수요에만 사용된다.
- 선사 간 공유되는 것은 재고가 아니라 KORAIL 열차 capacity 이다.
- 선사별 개별 최적화 후 합산이 아니라, 같은 planning cycle 의 모든 Service Need 를
  하나의 MILP 에서 동시에 고려한다.

현재 데이터는 Synthetic Carrier-Level Data 이며 후보 시간표는 Prototype Synthetic 이다.
실제 선사 제출 데이터와 KORAIL feasible path 로 동일 schema 교체가 가능하다.
"""
from __future__ import annotations

# Canonical v7.1 core module. Keep this filename aligned with all runners.

import argparse
import csv
import json
import math
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy.sparse import coo_matrix, csr_matrix, vstack

TEU = {"20FT": 1, "40FT": 2}
HUB_NAME = {
    "UIWANG": "의왕ICD(오봉역)",
    "BUGANG": "부강화물역 CY",
    "YAKMOK": "약목역 CY",
    "BUSAN": "부산신항",
    "DONGSAN": "동산역 CY",
    "GWANGYANG": "신광양항",
}

# v7 (review finding #7, 지시서 Phase 5-1):
# 거리는 두 종류이며 이름부터 분리한다. 값은 axis_params_v7 이 채운다.
#   SEGMENT_DISTANCE = physical_distance_km  (열차 주행거리, 정차역 인입선 포함)
#   OD_DISTANCE      = tariff_distance_km    (코레일 영업거리, 운임 전용)
# 두 값의 차이는 부강 인입선 왕복(5.8km)으로 전부 설명되며 runtime 에 검증한다.
SEGMENT_DISTANCE = {}
OD_DISTANCE = {}
EMPTY_RATE = {}
MIN_CHARGE_KM = 100.0
AVG_SPEED_KMPH = 68.37960339943344
ORIGIN_LOADING_H = 3.0
INTERMEDIATE_HANDLING_H = 3.0
DESTINATION_UNLOADING_H = 3.0
PARAMS = None


def configure_params(xlsx: Optional[Path]=None, origin_loading_h=None,
                     intermediate_handling_h=None, destination_unloading_h=None):
    """Load rail reference parameters and publish them as module-level constants."""
    global PARAMS, SEGMENT_DISTANCE, OD_DISTANCE, EMPTY_RATE, MIN_CHARGE_KM
    global AVG_SPEED_KMPH, ORIGIN_LOADING_H, INTERMEDIATE_HANDLING_H, DESTINATION_UNLOADING_H
    from axis_params_v7_1 import load_rail_params
    PARAMS = load_rail_params(xlsx, origin_loading_h, intermediate_handling_h,
                              destination_unloading_h)
    failed = [c for c in PARAMS.validation if c["check"] != "_deltas" and not c["pass"]]
    if failed:
        raise ValueError("rail parameter validation failed: " +
                         "; ".join(f'{c["check"]}: {c["detail"]}' for c in failed))
    SEGMENT_DISTANCE = PARAMS.physical_km
    OD_DISTANCE = PARAMS.tariff_km
    EMPTY_RATE = {k: PARAMS.empty_rate(k) for k in TEU}
    MIN_CHARGE_KM = PARAMS.min_charge_km
    AVG_SPEED_KMPH = PARAMS.avg_speed_kmph
    ORIGIN_LOADING_H = PARAMS.origin_loading_h
    INTERMEDIATE_HANDLING_H = PARAMS.intermediate_handling_h
    DESTINATION_UNLOADING_H = PARAMS.destination_unloading_h
    return PARAMS

GYEONGBU_S = ["UIWANG", "BUGANG", "YAKMOK", "BUSAN"]
SOUTHWEST_S = ["UIWANG", "BUGANG", "DONGSAN", "GWANGYANG"]
CORRIDORS = [GYEONGBU_S, list(reversed(GYEONGBU_S)), SOUTHWEST_S, list(reversed(SOUTHWEST_S))]

FORMATION = {
    "F33": {"wagons": 33, "capacity_teu": 66},
    "F40": {"wagons": 40, "capacity_teu": 80},
    "F50": {"wagons": 50, "capacity_teu": 100},
}

# Prototype timetable candidate departure hours (scenario, not a KORAIL timetable).
DEPARTURE_HOURS = (0, 6, 12, 18)


def write_csv(path: Path, rows: List[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields=[]; seen=set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k); fields.append(k)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)


def read_json(path: Optional[Path], default):
    if path is None or not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def fare_per_box(origin: str, destination: str, size: str) -> float:
    km = max(OD_DISTANCE[(origin, destination)], MIN_CHARGE_KM)
    return km * EMPTY_RATE[size]


def read_hourly(path: Path):
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            rows.append({
                "carrier": r["carrier_id"],
                "timestamp": datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M"),
                "hub": r["hub_code"],
                "size": r["container_size"],
                "demand": int(r["demand"]),
                "supply": int(r["supply_total"]),
            })
    return rows


def read_initial(path: Path):
    out = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            out[(r["carrier_id"], r["hub_code"], r["container_size"])] = int(r["initial_inventory"])
    return out


def contiguous_subpaths(seq: List[str]):
    out = []
    for i in range(len(seq)-1):
        for j in range(i+1, len(seq)):
            out.append(tuple(seq[i:j+1]))
    return out


def unique_service_paths():
    seen = set(); out = []
    for seq in CORRIDORS:
        for p in contiguous_subpaths(seq):
            if p not in seen:
                seen.add(p); out.append(p)
    return out


def path_segments(path: Tuple[str, ...]):
    return tuple((path[i], path[i+1]) for i in range(len(path)-1))


def service_family(path: Tuple[str, ...]):
    """
    v7 (review finding #19): 의왕-부강 단독 구간을 'COMMON' 으로 분류하면
    path_slot_capacity 의 service_family 필터(GYEONGBU / SOUTHWEST)에 걸리지 않아
    56편이 선로용량 제약을 완전히 우회했다.

    의왕-부강은 두 corridor 가 공유하는 trunk 이므로 'TRUNK' 로 명시하고,
    slot 규칙 매칭에서는 두 축 모두에 포함되도록 한다 (families() 참조).
    """
    s = set(path)
    if "YAKMOK" in s or "BUSAN" in s:
        return "GYEONGBU"
    if "DONGSAN" in s or "GWANGYANG" in s:
        return "SOUTHWEST"
    return "TRUNK"


def family_matches(train_family: str, rule_family: str) -> bool:
    """Shared trunk services belong to both corridors for slot-capacity purposes."""
    if not rule_family:
        return True
    if train_family == "TRUNK":
        return rule_family in ("GYEONGBU", "SOUTHWEST", "TRUNK")
    return train_family == rule_family


# 두 corridor 가 물리적으로 공유하는 구간. 중복열차 conflict 판정에 사용한다.
SHARED_TRUNK_SEGMENTS = {("UIWANG", "BUGANG"), ("BUGANG", "UIWANG")}


def generate_candidate_inputs(start: datetime, horizon_h: int, outdir: Path):
    """
    Prototype 후보 시간표 생성.

    v7.1-patch: 같은 물리경로에 대해 **정차패턴 변형**을 생성한다.
    중간역은 WORK_STOP(상하차 가능, 3시간 작업) 또는 PASS_THROUGH(통과, 0시간)다.
    이전에는 모든 중간역에 무조건 3시간이 붙어, 상하차가 없는 역에서도
    운송이 지연되는 비현실적인 시간표만 존재했다.

    출발역·도착역은 항상 WORK_STOP 이다.
    """
    candidate_rows=[]; stop_rows=[]; segment_rows=[]; formation_rows=[]
    cid=0
    for path in unique_service_paths():
        segs = path_segments(path)
        family = service_family(path)
        dist = sum(SEGMENT_DISTANCE[s] for s in segs)
        inter = path[1:-1]
        # 중간역별 정차/통과 조합. 중간역이 없으면 조합은 1가지.
        for mask in range(1 << len(inter)):
            work = {path[0], path[-1]}
            work |= {h for i, h in enumerate(inter) if (mask >> i) & 1}
            pattern = "".join("S" if h in work else "P" for h in path)
            for day in range(math.ceil(horizon_h/24)):
                for hr in DEPARTURE_HOURS:
                    origin_slot = day*24+hr
                    if origin_slot >= horizon_h: continue
                    elapsed = 0.0
                    load_open = origin_slot - math.ceil(ORIGIN_LOADING_H - 1e-10)
                    if load_open < 0:
                        continue
                    arr_slot = {path[0]: origin_slot}
                    dep_slot = {path[0]: origin_slot}
                    load_slot = {path[0]: load_open}
                    for a,b in segs:
                        elapsed += SEGMENT_DISTANCE[(a,b)]/AVG_SPEED_KMPH
                        arr_slot[b] = origin_slot + math.ceil(elapsed - 1e-10)
                        if b != path[-1] and b in work:
                            # 작업하는 중간역에서만 하화+상차 시간을 확보한다.
                            load_slot[b] = arr_slot[b]
                            elapsed += INTERMEDIATE_HANDLING_H
                            dep_slot[b] = origin_slot + math.ceil(elapsed - 1e-10)
                        else:
                            # 통과역 또는 종착역: 추가 정차시간 없음.
                            dep_slot[b] = arr_slot[b]
                            load_slot[b] = arr_slot[b]
                    avail_slot = {h: arr_slot[h] + math.ceil(DESTINATION_UNLOADING_H - 1e-10)
                                  for h in path}
                    if avail_slot[path[-1]] >= horizon_h:
                        continue
                    cid += 1
                    train_id=f"CAND{cid:04d}"
                    candidate_rows.append({
                        "train_id":train_id,
                        "service_family":family,
                        "origin_terminal":path[0],
                        "destination_terminal":path[-1],
                        "path":"|".join(path),
                        "work_stops":"|".join(h for h in path if h in work),
                        "stop_pattern":pattern,
                        "work_stop_count":len(work),
                        "origin_departure_time":(start+timedelta(hours=origin_slot)).strftime("%Y-%m-%d %H:%M"),
                        "destination_arrival_time":(start+timedelta(hours=arr_slot[path[-1]])).strftime("%Y-%m-%d %H:%M"),
                        "service_distance_km":round(dist,1),
                        "candidate_source":"PROTOTYPE_SYNTHETIC",
                        "timetable_basis":"PROTOTYPE_6H_SYNTHETIC",
                    })
                    for seqno, hub in enumerate(path,1):
                        stop_rows.append({
                            "train_id":train_id,"stop_sequence":seqno,"hub_code":hub,"hub_name":HUB_NAME[hub],
                            "stop_type":"WORK_STOP" if hub in work else "PASS_THROUGH",
                            "load_start_time":(start+timedelta(hours=load_slot[hub])).strftime("%Y-%m-%d %H:%M"),
                            "arrival_time":(start+timedelta(hours=arr_slot[hub])).strftime("%Y-%m-%d %H:%M"),
                            "departure_time":(start+timedelta(hours=dep_slot[hub])).strftime("%Y-%m-%d %H:%M"),
                            "available_time":(start+timedelta(hours=avail_slot[hub])).strftime("%Y-%m-%d %H:%M"),
                            "load_start_slot":load_slot[hub],"arrival_slot":arr_slot[hub],
                            "departure_slot":dep_slot[hub],"available_slot":avail_slot[hub],
                        })
                    for seqno,(a,b) in enumerate(segs,1):
                        segment_rows.append({
                            "train_id":train_id,"segment_sequence":seqno,"from_hub":a,"to_hub":b,
                            "segment_distance_km":SEGMENT_DISTANCE[(a,b)]
                        })
                    forms=["F33","F40"]
                    if family == "GYEONGBU": forms.append("F50")
                    for f in forms:
                        formation_rows.append({
                            "train_id":train_id,"formation_id":f,"wagon_count":FORMATION[f]["wagons"],
                            "capacity_teu":FORMATION[f]["capacity_teu"],
                            "basis":"RESEARCH_SCENARIO_OPTION"
                        })
    write_csv(outdir/"TRAIN_CANDIDATE.csv", candidate_rows)
    write_csv(outdir/"TRAIN_STOP_TIME.csv", stop_rows)
    write_csv(outdir/"TRAIN_SEGMENT.csv", segment_rows)
    write_csv(outdir/"TRAIN_FORMATION_OPTION.csv", formation_rows)
    return candidate_rows, stop_rows, segment_rows, formation_rows


class ModelInfeasible(RuntimeError):
    """Raised when a lexicographic stage proves the model infeasible."""
    def __init__(self, stage, message):
        self.stage=stage; self.solver_message=message
        super().__init__(f"stage '{stage}' infeasible: {message}")


class AxisRequestError(Exception):
    """
    Structured, chatbot-facing failure (지시서 Phase 8).

    선사가 불가능한 조건을 넣었을 때 Python raw exception 으로 죽지 않고
    LLM 이 그대로 설명할 수 있는 구조를 반환한다.
    LLM 은 이 결과를 설명만 하며 스스로 숫자나 새 열차안을 만들지 않는다.
    """
    def __init__(self, reason_code, message, detail=None, alternatives=None):
        self.reason_code=reason_code; self.message=message
        self.detail=detail or {}; self.alternatives=alternatives or []
        super().__init__(f"[{reason_code}] {message}")

    def as_dict(self):
        return {"status":"INFEASIBLE","reason_code":self.reason_code,
                "message":self.message,"detail":self.detail,
                "alternatives":self.alternatives}


def diagnose_infeasibility(service, meta_or_needs, max_earliness=None, min_load_factor=None):
    """Turn a failed/empty model into an actionable structured explanation."""
    needs=meta_or_needs if isinstance(meta_or_needs,list) else meta_or_needs.get("needs",[])
    total=sum(n["teu"] for n in needs)
    alts=[]
    if min_load_factor:
        alts.append({"action":"LOWER_MIN_CONSOLIDATION_LEVEL",
                     "current":min_load_factor,
                     "note":"최소 적재율을 낮추면 열차 개설이 가능해질 수 있습니다."})
    if max_earliness is not None:
        alts.append({"action":"RELAX_MAX_EARLINESS","current":max_earliness,
                     "note":"조기도착 허용 시간을 늘리면 더 많은 물량을 한 열차에 모을 수 있습니다."})
    alts.append({"action":"RELAX_LATEST_ARRIVAL",
                 "note":"기한을 늦추면 후보 열차가 늘어납니다."})
    return AxisRequestError(
        "NO_FEASIBLE_RAIL_SERVICE",
        "현재 조건에서는 최소 consolidation 요건을 만족하는 신규 공컨 전용열차를 "
        "구성할 수 없습니다.",
        detail={"service_need_teu":total,"service_need_count":len(needs),
                "max_earliness_hours":max_earliness,"min_load_factor":min_load_factor},
        alternatives=alts)



class PolicyValidationError(ValueError):
    """Structured policy schema error. Chatbot backend surfaces this to the carrier."""
    def __init__(self, reason_code, message, rule=None, detail=None):
        self.reason_code=reason_code; self.message=message
        self.rule=rule; self.detail=detail or {}
        super().__init__(f"[{reason_code}] {message}")

    def as_dict(self):
        return {"status":"INVALID_POLICY","reason_code":self.reason_code,
                "message":self.message,"rule":self.rule,"detail":self.detail}


# Canonical Inventory Policy schema. See 01_DOCS/INVENTORY_POLICY_SCHEMA.md.
# Unknown rule_type or unknown key is a hard error - never silently skipped (v7 requirement).
POLICY_COMMON_KEYS = {"rule_id","carrier_id","rule_type","hub_code","container_size",
                      "value","hard_constraint","note"}
POLICY_RULE_KEYS = {
    "MIN_INVENTORY_AT_TIME":      {"target_time"},
    "MIN_INVENTORY_RANGE":        {"start_time","end_time"},
    "MAX_INVENTORY":              {"start_time","end_time"},
    # v7.1 정본 명칭. BLOCK_OUTBOUND 는 v7 호환 별칭.
    "ORIGIN_RELEASE_RESTRICTION": {"start_time","end_time"},
    "BLOCK_OUTBOUND":             {"start_time","end_time"},
}
POLICY_REQUIRED = {
    "MIN_INVENTORY_AT_TIME": {"carrier_id","rule_type","hub_code","container_size","value","target_time"},
    "MIN_INVENTORY_RANGE":   {"carrier_id","rule_type","hub_code","container_size","value"},
    "MAX_INVENTORY":         {"carrier_id","rule_type","hub_code","container_size","value"},
    "ORIGIN_RELEASE_RESTRICTION": {"carrier_id","rule_type","hub_code","container_size","value"},
    "BLOCK_OUTBOUND":        {"carrier_id","rule_type","hub_code","container_size","value"},
}
# Declared in the schema doc but deliberately not implemented in the v7 MVP.
POLICY_NOT_IMPLEMENTED = {"TARGET_INVENTORY"}


def parse_policies(policies_obj, timestamps, carriers=None, hubs=None, sizes=None):
    """
    Validate and compile inventory policies.

    Returns dict with
      lb           : (carrier,hub,size,t) -> minimum inventory
      ub           : (carrier,hub,size,t) -> maximum inventory
      outbound_cap : (carrier,hub,size) -> (max_boxes, start_slot, end_slot)
      active       : list of normalized rule dicts (ACTIVE_POLICY output)

    Raises PolicyValidationError on any schema problem. Silent skipping is forbidden.
    """
    tmap={ts:i for i,ts in enumerate(timestamps)}
    lb=defaultdict(int); ub={}; outbound={}; active=[]

    raw=policies_obj.get("inventory_policies", [])
    if not isinstance(raw, list):
        raise PolicyValidationError("SCHEMA_TYPE_ERROR","inventory_policies must be a list",
                                    detail={"got":type(raw).__name__})

    def _time(rule, field, default=None):
        if field not in rule or rule[field] in (None,""):
            if default is not None: return default
            raise PolicyValidationError("MISSING_FIELD",
                f"'{field}' is required for rule_type={rule.get('rule_type')}", rule=rule)
        try:
            ts=datetime.strptime(rule[field], "%Y-%m-%d %H:%M")
        except (ValueError,TypeError):
            raise PolicyValidationError("BAD_TIME_FORMAT",
                f"'{field}' must be 'YYYY-MM-DD HH:MM'", rule=rule, detail={"got":rule.get(field)})
        if ts not in tmap:
            raise PolicyValidationError("TIME_OUTSIDE_HORIZON",
                f"'{field}' is outside the planning horizon", rule=rule,
                detail={"got":rule[field],
                        "horizon":[timestamps[0].strftime("%Y-%m-%d %H:%M"),
                                   timestamps[-1].strftime("%Y-%m-%d %H:%M")]})
        return ts

    for idx,p in enumerate(raw):
        if not isinstance(p, dict):
            raise PolicyValidationError("SCHEMA_TYPE_ERROR",
                f"inventory_policies[{idx}] must be an object", detail={"got":type(p).__name__})
        rt=p.get("rule_type")
        if rt is None:
            legacy = "type" if "type" in p else ("hub" if "hub" in p else None)
            raise PolicyValidationError("MISSING_FIELD",
                "'rule_type' is required" + (f" (found legacy key '{legacy}')" if legacy else ""),
                rule=p, detail={"expected_keys":sorted(POLICY_REQUIRED)})
        if rt in POLICY_NOT_IMPLEMENTED:
            raise PolicyValidationError("RULE_TYPE_NOT_IMPLEMENTED",
                f"rule_type '{rt}' is defined in the schema but not implemented in v7",
                rule=p, detail={"implemented":sorted(POLICY_RULE_KEYS)})
        if rt not in POLICY_RULE_KEYS:
            raise PolicyValidationError("UNKNOWN_RULE_TYPE",
                f"unknown rule_type '{rt}'", rule=p,
                detail={"supported":sorted(POLICY_RULE_KEYS),
                        "not_implemented":sorted(POLICY_NOT_IMPLEMENTED)})

        allowed=POLICY_COMMON_KEYS | POLICY_RULE_KEYS[rt]
        unknown=sorted(set(p) - allowed)
        if unknown:
            raise PolicyValidationError("UNKNOWN_FIELD",
                f"unknown field(s) {unknown} for rule_type={rt}", rule=p,
                detail={"allowed":sorted(allowed)})
        missing=sorted(POLICY_REQUIRED[rt] - set(p))
        if missing:
            raise PolicyValidationError("MISSING_FIELD",
                f"missing required field(s) {missing} for rule_type={rt}", rule=p)

        c=p["carrier_id"]; h=p["hub_code"]; k=p["container_size"]
        if carriers is not None and c not in carriers:
            raise PolicyValidationError("UNKNOWN_CARRIER", f"unknown carrier_id '{c}'",
                                        rule=p, detail={"known":sorted(carriers)})
        if hubs is not None and h not in hubs:
            raise PolicyValidationError("UNKNOWN_HUB", f"unknown hub_code '{h}'",
                                        rule=p, detail={"known":sorted(hubs)})
        if sizes is not None and k not in sizes:
            raise PolicyValidationError("UNKNOWN_CONTAINER_SIZE", f"unknown container_size '{k}'",
                                        rule=p, detail={"known":sorted(sizes)})
        try:
            v=int(p["value"])
        except (TypeError,ValueError):
            raise PolicyValidationError("BAD_VALUE","'value' must be an integer",
                                        rule=p, detail={"got":p.get("value")})
        if v<0:
            raise PolicyValidationError("BAD_VALUE","'value' must be nonnegative", rule=p)
        if p.get("hard_constraint") is False:
            raise PolicyValidationError("SOFT_CONSTRAINT_NOT_SUPPORTED",
                "hard_constraint=false (soft target) is not implemented in v7; "
                "use MIN_INVENTORY_* for a hard bound", rule=p)

        norm={"rule_id":p.get("rule_id",f"POL-{idx+1:03d}"),"carrier_id":c,"rule_type":rt,
              "hub_code":h,"container_size":k,"value":v,"hard_or_soft":"HARD"}

        if rt=="MIN_INVENTORY_AT_TIME":
            ts=_time(p,"target_time"); t=tmap[ts]
            lb[(c,h,k,t)]=max(lb[(c,h,k,t)],v)
            norm.update(start_time="",end_time="",target_time=ts.strftime("%Y-%m-%d %H:%M"))
        else:
            st=_time(p,"start_time",default=timestamps[0])
            en=_time(p,"end_time",default=timestamps[-1])
            if st>en:
                raise PolicyValidationError("BAD_TIME_RANGE","start_time must be <= end_time", rule=p)
            s0,s1=tmap[st],tmap[en]
            if rt=="MIN_INVENTORY_RANGE":
                for t in range(s0,s1+1): lb[(c,h,k,t)]=max(lb[(c,h,k,t)],v)
            elif rt=="MAX_INVENTORY":
                for t in range(s0,s1+1):
                    key=(c,h,k,t); ub[key]=min(ub.get(key,v),v)
            elif rt in ("ORIGIN_RELEASE_RESTRICTION","BLOCK_OUTBOUND"):
                key=(c,h,k)
                prev=outbound.get(key)
                outbound[key]=(min(prev[0],v),s0,s1) if prev else (v,s0,s1)
            norm.update(start_time=st.strftime("%Y-%m-%d %H:%M"),
                        end_time=en.strftime("%Y-%m-%d %H:%M"),target_time="")
        active.append(norm)

    # v7.1-patch: 정책 간 논리적 충돌을 MILP 이전에 감지한다.
    # (팀 피드백: MIN 재고와 MAX 재고/반출제한을 동시에 넣으면 infeasible 이 될 수 있음)
    conflicts = []
    for (c, h, k, t), lo_v in lb.items():
        hi_v = ub.get((c, h, k, t))
        if hi_v is not None and lo_v > hi_v:
            conflicts.append({"type": "MIN_ABOVE_MAX", "carrier_id": c, "hub_code": h,
                              "container_size": k,
                              "time": timestamps[t].strftime("%Y-%m-%d %H:%M"),
                              "min_inventory": lo_v, "max_inventory": hi_v})
    for (c, h, k), (cap, s0, s1) in outbound.items():
        if cap == 0:
            need_min = [t for (cc, hh, kk, t), v in lb.items()
                        if (cc, hh, kk) == (c, h, k) and v > 0 and s0 <= t <= s1]
            if need_min:
                conflicts.append({
                    "type": "OUTBOUND_BLOCKED_BUT_MIN_REQUIRED", "carrier_id": c,
                    "hub_code": h, "container_size": k,
                    "note": "이 거점의 반출이 완전 차단되어 있는데 같은 기간에 "
                            "최소재고 정책이 걸려 있습니다. 다른 거점에서만 공급 가능합니다."})
    if conflicts:
        hard = [x for x in conflicts if x["type"] == "MIN_ABOVE_MAX"]
        if hard:
            raise PolicyValidationError(
                "POLICY_CONFLICT",
                "동시에 만족할 수 없는 재고정책이 있습니다. "
                "MIN_INVENTORY 값이 같은 시점의 MAX_INVENTORY 값을 초과합니다.",
                detail={"conflicts": hard[:10], "conflict_count": len(hard)})

    return {"lb":lb,"ub":ub,"outbound_cap":outbound,"active":active,
            "policy_warnings":conflicts}


def generate_service_needs(hourly_rows, initial, policies_obj, outdir: Optional[Path]=None):
    timestamps=sorted({r["timestamp"] for r in hourly_rows})
    tmap={ts:i for i,ts in enumerate(timestamps)}
    carriers=sorted({r["carrier"] for r in hourly_rows})
    hubs=sorted({r["hub"] for r in hourly_rows})
    sizes=sorted({r["size"] for r in hourly_rows})
    demand=defaultdict(int); supply=defaultdict(int)
    for r in hourly_rows:
        t=tmap[r["timestamp"]]
        demand[(r["carrier"],r["hub"],r["size"],t)] = r["demand"]
        supply[(r["carrier"],r["hub"],r["size"],t)] = r["supply"]
    pol=parse_policies(policies_obj,timestamps,set(carriers),set(hubs),set(sizes))
    lb=pol["lb"]; inv_ub=pol["ub"]; outbound_cap=pol["outbound_cap"]
    policy_warnings=pol.get("policy_warnings",[])

    needs=[]; baseline_rows=[]; source_cap={}; baseline_stock={}
    nid=0
    for c in carriers:
        for h in hubs:
            for k in sizes:
                # Physical no-rail baseline for source-release protection.
                physical_stock=initial[(c,h,k)]
                # Virtual target-fulfilled stock for incremental service-need generation.
                target_stock=initial[(c,h,k)]
                for t,ts in enumerate(timestamps):
                    d=demand[(c,h,k,t)]; s=supply[(c,h,k,t)]; target_lb=lb[(c,h,k,t)]

                    # Physical baseline: no rail, unmet demand is lost, stock cannot be negative.
                    physical_available=physical_stock+s
                    physical_unmet=max(d-physical_available,0)
                    physical_stock=max(physical_available-d,0)
                    release=max(physical_stock-target_lb,0)
                    source_cap[(c,h,k,t)] = release
                    baseline_stock[(c,h,k,t)] = physical_stock

                    # Need generation: assume earlier generated needs are fulfilled so each gap is incremental.
                    target_available=target_stock+s
                    gap=max(d+target_lb-target_available,0)
                    if gap>0:
                        nid += 1
                        needs.append({
                            "need_id":f"NEED{nid:04d}","carrier_id":c,"destination":h,
                            "destination_name":HUB_NAME[h],"container_size":k,"quantity":int(gap),
                            "teu":int(gap)*TEU[k],"due_time":ts.strftime("%Y-%m-%d %H:%M"),"due_slot":t,
                            "priority":1,"need_reason":"MIN_INVENTORY_POLICY" if target_lb>0 and physical_unmet==0 else "FORECAST_STOCKOUT",
                            "inventory_lb":target_lb,
                        })
                        target_available += gap
                    target_stock = target_available-d

                    baseline_rows.append({
                        "carrier_id":c,"timestamp":ts.strftime("%Y-%m-%d %H:%M"),"hub_code":h,"container_size":k,
                        "demand":d,"external_supply":s,"no_rail_inventory_end":physical_stock,
                        "no_rail_unmet":physical_unmet,"inventory_lb":target_lb,
                        "source_release_capacity_cumulative":release,
                    })
    # v7.1: 챗봇 수량조정(additional_needs)은 협상 계층이므로 제거했다.
    # Service Need 는 오직 선사가 제출한 재고·수요·공급과 사전 재고정책에서만 유도된다.

    if outdir:
        write_csv(outdir/"SERVICE_NEED.csv", needs)
        write_csv(outdir/"BASELINE_AND_SOURCE_CAPACITY.csv", baseline_rows)
    return {
        "timestamps":timestamps,"tmap":tmap,"carriers":carriers,"hubs":hubs,"sizes":sizes,
        "demand":demand,"supply":supply,"lb":lb,"needs":needs,"source_cap":source_cap,
        "baseline_rows":baseline_rows,"baseline_stock":baseline_stock,
        "initial_inventory":dict(initial),
        "inventory_ub":inv_ub,"outbound_cap":outbound_cap,"active_policies":pol["active"],
        "policy_warnings":policy_warnings,
    }


@dataclass
class Train:
    train_id: str
    family: str
    path: Tuple[str,...]
    origin_departure: datetime
    service_distance_km: float
    arr_slot: Dict[str,int]
    dep_slot: Dict[str,int]
    segments: Tuple[Tuple[str,str],...]
    formations: Tuple[str,...]
    load_slot: Dict[str,int] = field(default_factory=dict)   # 상차 개시 (재고 필요 시각)
    avail_slot: Dict[str,int] = field(default_factory=dict)  # 하화 완료 (사용 가능 시각)
    candidate_source: str = "PROTOTYPE_SYNTHETIC"            # PROTOTYPE_SYNTHETIC | KORAIL_FEASIBLE_PATH
    # v7.1-patch: 후보 파일이 제공한 train-specific 물리거리·편성 spec.
    # 외부 KORAIL feasible path 가 prototype network 와 다른 값을 가져도 그대로 반영된다.
    segment_km: Dict[Tuple[str,str],float] = field(default_factory=dict)
    formation_spec: Dict[str,dict] = field(default_factory=dict)
    # v7.1-patch: 상하차가 가능한 역. 통과역은 여기 포함되지 않는다.
    work_stops: Tuple[str,...] = ()
    # Original minute-resolution timetable is preserved for user-facing output.
    # Integer slots remain the sole feasibility representation used by the MILP.
    actual_load_start_time: Dict[str,datetime] = field(default_factory=dict)
    actual_arrival_time: Dict[str,datetime] = field(default_factory=dict)
    actual_departure_time: Dict[str,datetime] = field(default_factory=dict)
    actual_available_time: Dict[str,datetime] = field(default_factory=dict)

    def can_work(self, hub: str) -> bool:
        return hub in self.work_stops if self.work_stops else True

    def seg_km(self, seg) -> float:
        """이 열차 후보가 신고한 구간 물리거리. 없으면 network 기본값."""
        v = self.segment_km.get(seg)
        return float(v) if v is not None else float(SEGMENT_DISTANCE[seg])

    def path_km(self, segs=None) -> float:
        return sum(self.seg_km(x) for x in (segs if segs is not None else self.segments))

    def wagons(self, f: str) -> int:
        spec = self.formation_spec.get(f)
        return int(spec["wagon_count"]) if spec else int(FORMATION[f]["wagons"])

    def capacity(self, f: str) -> int:
        spec = self.formation_spec.get(f)
        return int(spec["capacity_teu"]) if spec else int(FORMATION[f]["capacity_teu"])


def _candidate_inputs_match(indir: Path, start: datetime, horizon_h: int) -> bool:
    """
    기존 prototype 후보를 재사용해도 되는지 판정한다.

    v7.1-patch (지시서 §2): 이전에는 `min(departure) == horizon start` 를 요구했으나,
    prototype 생성기는 출발역 상차 3시간을 반영하므로 첫 열차가 horizon 시작시각에
    존재할 수 없다. 정상 후보가 mismatch 로 판정되어 재생성되는 문제가 있었다.

    이제는 "모든 후보 시각이 이 계획주간 안에 있는가" 만 검사한다.
    첫 열차가 06:00 이어도 정상이다.

    주의: 이 함수는 **prototype 재사용 판정 전용**이다.
    외부 --candidates 는 절대 이 경로를 타지 않으며 덮어써지지 않는다.
    """
    path = indir / "TRAIN_CANDIDATE.csv"
    if not path.exists():
        return False
    try:
        with path.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
            deps = [datetime.strptime(r["origin_departure_time"], "%Y-%m-%d %H:%M")
                    for r in rows]
    except (KeyError, ValueError, OSError):
        return False
    if not deps:
        return False
    end = start + timedelta(hours=horizon_h - 1)
    return min(deps) >= start and max(deps) <= end


def read_candidate_inputs(indir: Path):
    cand={}
    with (indir/"TRAIN_CANDIDATE.csv").open(encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f):
            cand[r["train_id"]]={
                "family":r["service_family"],"path":tuple(r["path"].split("|")),
                "origin_departure":datetime.strptime(r["origin_departure_time"],"%Y-%m-%d %H:%M"),
                "distance":float(r["service_distance_km"]),
                # 실제 서비스에서는 KORAIL_FEASIBLE_PATH 로 교체된다.
                "candidate_source":r.get("candidate_source","PROTOTYPE_SYNTHETIC"),
                # v7.1-patch: 상하차 가능역. 미기재면 전 정차역이 작업역(하위호환).
                "work_stops":tuple((r.get("work_stops") or "").split("|"))
                              if r.get("work_stops") else tuple(r["path"].split("|")),
            }
    arr=defaultdict(dict); dep=defaultdict(dict); ldg=defaultdict(dict); avl=defaultdict(dict)
    actual_ldg=defaultdict(dict); actual_arr=defaultdict(dict)
    actual_dep=defaultdict(dict); actual_avl=defaultdict(dict)

    def _actual_time(row, actual_name, legacy_name):
        raw = row.get(actual_name) or row.get(legacy_name)
        if not raw:
            return None
        return datetime.strptime(raw, "%Y-%m-%d %H:%M")

    with (indir/"TRAIN_STOP_TIME.csv").open(encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f):
            tid, hub = r["train_id"], r["hub_code"]
            arr[tid][hub]=int(r["arrival_slot"])
            dep[tid][hub]=int(r["departure_slot"])
            ldg[tid][hub]=int(r["load_start_slot"])
            avl[tid][hub]=int(r["available_slot"])
            for target, actual_name, legacy_name in (
                    (actual_ldg, "actual_load_start_time", "load_start_time"),
                    (actual_arr, "actual_arrival_time", "arrival_time"),
                    (actual_dep, "actual_departure_time", "departure_time"),
                    (actual_avl, "actual_available_time", "available_time")):
                value = _actual_time(r, actual_name, legacy_name)
                if value is not None:
                    target[tid][hub] = value
    segs=defaultdict(list); segkm=defaultdict(dict)
    with (indir/"TRAIN_SEGMENT.csv").open(encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f):
            pair=(r["from_hub"],r["to_hub"])
            segs[r["train_id"]].append((int(r["segment_sequence"]),pair))
            # v7.1-patch: CSV 의 실제 구간거리를 읽어 train 에 저장한다.
            if r.get("segment_distance_km") not in (None,""):
                segkm[r["train_id"]][pair]=float(r["segment_distance_km"])
    forms=defaultdict(list); fspec=defaultdict(dict)
    with (indir/"TRAIN_FORMATION_OPTION.csv").open(encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f):
            fid=r["formation_id"]
            forms[r["train_id"]].append(fid)
            # v7.1-patch: CSV 의 wagon_count / capacity_teu 가 정본이다.
            if r.get("wagon_count") not in (None,"") and r.get("capacity_teu") not in (None,""):
                fspec[r["train_id"]][fid]={"wagon_count":int(float(r["wagon_count"])),
                                           "capacity_teu":int(float(r["capacity_teu"]))}
    trains=[]
    for tid,c in cand.items():
        trains.append(Train(tid,c["family"],c["path"],c["origin_departure"],c["distance"],arr[tid],dep[tid],
                            tuple(s for _,s in sorted(segs[tid])),tuple(forms[tid]),
                            ldg[tid],avl[tid],c.get("candidate_source","PROTOTYPE_SYNTHETIC"),
                            dict(segkm[tid]),dict(fspec[tid]),c.get("work_stops",()),
                            dict(actual_ldg[tid]), dict(actual_arr[tid]),
                            dict(actual_dep[tid]), dict(actual_avl[tid])))
    return trains


def subpath_segments(path: Tuple[str,...], o: str, d: str):
    i=path.index(o); j=path.index(d)
    if i>=j: return None
    return tuple((path[k],path[k+1]) for k in range(i,j))


class SparseRows:
    def __init__(self,n):
        self.n=n; self.ri=[]; self.ci=[]; self.da=[]; self.lb=[]; self.ub=[]
    def add(self, coeff: Dict[int,float], lb=-np.inf, ub=np.inf):
        r=len(self.lb)
        for c,v in coeff.items():
            if abs(v)>1e-12:
                self.ri.append(r); self.ci.append(c); self.da.append(float(v))
        self.lb.append(float(lb)); self.ub.append(float(ub))
    def matrix(self):
        return coo_matrix((self.da,(self.ri,self.ci)),shape=(len(self.lb),self.n)).tocsr()


def add_rows(A,lb,ub,extra,n):
    if not extra: return A,lb,ub
    rr=SparseRows(n)
    for coeff,l,u in extra: rr.add(coeff,l,u)
    return vstack([A,rr.matrix()]).tocsr(), np.concatenate([lb,np.array(rr.lb)]), np.concatenate([ub,np.array(rr.ub)])


@dataclass
class AssignVar:
    var: int
    need_id: str
    carrier: str
    size: str
    origin: str
    destination: str
    train_id: str
    dep_slot: int
    arr_slot: int
    segments: Tuple[Tuple[str,str],...]
    fare: float


def _parse_time_in_horizon(txt: str, service, field: str):
    ts=datetime.strptime(txt,"%Y-%m-%d %H:%M")
    if ts not in service["tmap"]:
        raise ValueError(f"{field} outside horizon: {txt}")
    return ts, service["tmap"][ts]



def solve_lex(meta,lo,up,integ,time_limit=900,mip_gap=0.001,verbose=False,
              strict_stages=("Z1_unserved_teu","Z2_train_count"),strict_lexicographic=False):
    """
    Lexicographic solve with per-stage solver audit.

    v7 changes (review finding #15, 지시서 Phase 6):
      - every stage records status / gap / objective / runtime into SOLVER_AUDIT
      - a stage that is not proven optimal raises instead of being silently accepted
        (v6.1 only checked `res.x is None`, so a time-limited solution was treated
        as optimal and then frozen as an equality for later stages)
      - integer-valued core objectives (Z1, Z2) are solved with mip_rel_gap = 0
      - a deterministic tie-break stage is appended so alternative optima collapse
        to one canonical solution (review finding #2)
    """
    A=meta["A"]; lb=meta["lb"]; ub=meta["ub"]; n=len(lo)
    audit=[]
    # v7.1-patch (지시서 §18): strict mode 에서는 모든 lexicographic stage 를
    # mip_rel_gap = 0 으로 풀어 각 stage 의 incumbent 가 exact optimum 임을 보장한다.
    if strict_lexicographic:
        strict_stages=("Z1_unserved_teu","Z2_train_count","Z3_train_km","Z4_wagon_km",
                       "Z5_earliness_teu_hours","Z6_rail_charge_krw","Z7_deterministic_tiebreak")

    def solve(c,extra,name,gap=None):
        AA,ll,uu=add_rows(A,lb,ub,extra,n)
        opts={"time_limit":time_limit,
              "mip_rel_gap":(mip_gap if gap is None else gap),
              "disp":verbose}
        t0=time.perf_counter()
        res=milp(c,integrality=integ,bounds=Bounds(lo,up),
                 constraints=LinearConstraint(AA,ll,uu),options=opts)
        rt=time.perf_counter()-t0
        audit.append({"stage":name,"status":int(res.status),"success":bool(res.success),
                      "message":res.message,
                      "objective":(float(c@res.x) if res.x is not None else None),
                      "mip_gap_requested":(mip_gap if gap is None else gap),
                      "mip_gap_achieved":getattr(res,"mip_gap",None),
                      "mip_dual_bound":getattr(res,"mip_dual_bound",None),
                      "runtime_sec":round(rt,3),"rows":int(AA.shape[0]),"cols":n})
        # HiGHS via scipy: 0 == proven optimal, 1 == iteration/time limit, 2 == infeasible.
        if res.status==2:
            raise ModelInfeasible(name,res.message)
        if res.status!=0 or res.x is None:
            raise RuntimeError(
                f"stage '{name}' not proven optimal (status={res.status}): {res.message}. "
                "A time-limited or infeasible stage must not be frozen into later stages; "
                "raise --time-limit or relax the model.")
        return res

    # Z1 carrier service: unserved TEU. Integer-valued -> require proven optimum.
    c1=np.zeros(n)
    for need_id,v in meta["U"].items():
        nd=meta["need_by_id"][need_id]
        c1[v]=nd["priority"]*TEU[nd["container_size"]]
    r1=solve(c1,[],"Z1_unserved_teu",gap=0.0 if "Z1_unserved_teu" in strict_stages else None)
    z1=round(float(c1@r1.x),6)
    e1=[({i:float(c1[i]) for i in np.flatnonzero(c1)},z1-1e-6,z1+1e-6)]

    # Z2 train count: consolidate carriers on as few new trains as possible at the same service level.
    c2=np.zeros(n)
    for v in meta["Y"].values(): c2[v]=1
    r2=solve(c2,e1,"Z2_train_count",gap=0.0 if "Z2_train_count" in strict_stages else None)
    z2=int(round(float(c2@r2.x)))
    e2=e1+[({i:float(c2[i]) for i in np.flatnonzero(c2)},z2,z2)]

    # Z3 train-km: avoid unnecessarily long terminal-to-terminal services.
    c3=np.zeros(n)
    for tid,v in meta["Y"].items(): c3[v]=meta["trains"][tid].path_km()
    r3=solve(c3,e2,"Z3_train_km",gap=0.0 if "Z3_train_km" in strict_stages else None)
    z3=float(c3@r3.x)
    e3=e2+[({i:float(c3[i]) for i in np.flatnonzero(c3)},-np.inf,z3+1e-4)]

    # Z4 wagon-km: avoid oversized formations.
    c4=np.zeros(n)
    for (tid,f),v in meta["Z"].items():
        p=meta["trains"][tid]; c4[v]=p.wagons(f)*p.path_km()
    r4=solve(c4,e3,"Z4_wagon_km",gap=0.0 if "Z4_wagon_km" in strict_stages else None)
    z4=float(c4@r4.x)
    e4=e3+[({i:float(c4[i]) for i in np.flatnonzero(c4)},-np.inf,z4+1e-4)]

    # Z5 customer-service timing: among identical operating resources, avoid moving empties excessively early.
    # Measured as TEU-hours between train arrival and the need due time.
    c5=np.zeros(n)
    for a in meta["assignments"]:
        due=meta["need_by_id"][a.need_id]["due_slot"]
        c5[a.var]=TEU[a.size]*max(due-a.arr_slot,0)
    r5=solve(c5,e4,"Z5_earliness_teu_hours",gap=0.0 if "Z5_earliness_teu_hours" in strict_stages else None)
    z5=float(c5@r5.x)
    e5=e4+[({i:float(c5[i]) for i in np.flatnonzero(c5)},-np.inf,z5+1e-4)]

    # Z6 customer rail charge tie-breaker only after service and KORAIL operating resources/timing are fixed.
    c6=np.zeros(n)
    for a in meta["assignments"]: c6[a.var]=a.fare
    r6=solve(c6,e5,"Z6_rail_charge_krw",gap=0.0 if "Z6_rail_charge_krw" in strict_stages else None)
    z6=float(c6@r6.x)
    e6=e5+[({i:float(c6[i]) for i in np.flatnonzero(c6)},-np.inf,z6+1e-2)]

    # Z7 deterministic tie-break (review finding #2).
    #
    # Every operational objective above is already fixed by e6, so this stage cannot
    # change any reported KPI - it only selects one canonical solution among the
    # alternative optima that Z1..Z6 leave open.
    #
    # The weight is a strictly increasing rank over a canonical sort key that depends
    # only on model content (never on dict/solver iteration order), so the chosen
    # solution is stable across runs, machines and HiGHS versions.
    c7=np.zeros(n)
    order=sorted(meta["assignments"],
                 key=lambda a:(a.carrier,a.need_id,a.destination,a.origin,a.train_id,a.size))
    for rank,a in enumerate(order,1): c7[a.var]=float(rank)
    torder=sorted(meta["Y"]) if meta["Y"] else []
    for rank,tid in enumerate(torder,1): c7[meta["Y"][tid]]=float(rank)*1e-3
    # v7.1-patch: tie-break 는 항상 gap 0 으로 끝내야 정규해가 유일하게 고정된다.
    r7=solve(c7,e6,"Z7_deterministic_tiebreak",gap=0.0)
    final=r7

    summary={"unserved_teu":z1,"train_count":z2,"train_km":round(z3,3),"wagon_km":round(z4,3),
             "earliness_teu_hours":round(z5,3),"rail_charge_krw":round(z6,2),
             "tiebreak_index":round(float(c7@final.x),3),
             "all_stages_proven_optimal":True,
             "solver_stage_count":len(audit),
             "strict_lexicographic":bool(strict_lexicographic),
             "solver_exactness":("EXACT_ALL_STAGES" if strict_lexicographic
                                 else "APPROXIMATE_WITHIN_GAP_Z3_TO_Z6")}
    return final,summary,audit


# ===========================================================================
# v7.1-PATCH — 입력 검증 / 후보 보호 / 설명 데이터
# ===========================================================================
HUB_CODES = set(HUB_NAME)
SIZE_CODES = set(TEU)


class InputValidationError(ValueError):
    """구조화된 입력 검증 오류. Python KeyError 대신 이것을 반환한다."""

    def __init__(self, reason_code, message, detail=None, errors=None):
        self.reason_code = reason_code
        self.message = message
        self.detail = detail or {}
        self.errors = errors or []
        super().__init__(f"[{reason_code}] {message}")

    def as_dict(self):
        return {"status": "INVALID_INPUT", "reason_code": self.reason_code,
                "message": self.message, "detail": self.detail,
                "errors": self.errors[:50]}


def validate_carrier_inputs(hourly_path: Path, initial_path: Path) -> dict:
    """
    선사가 제출한 파일에 대한 사전 검증 (지시서 §7).

    synthetic 데이터는 생성기가 감사하지만, 실제 선사 제출 파일은 이 계층을 통과해야 한다.
    실패 시 InputValidationError(structured) 를 던진다.
    """
    errors = []

    req_h = {"carrier_id", "timestamp", "hub_code", "container_size", "demand", "supply_total"}
    req_i = {"carrier_id", "hub_code", "container_size", "initial_inventory"}

    def _rows(path, required, label):
        if not Path(path).exists():
            raise InputValidationError("FILE_NOT_FOUND", f"{label} file not found",
                                       detail={"path": str(path)})
        with Path(path).open(encoding="utf-8-sig", newline="") as f:
            rd = csv.DictReader(f)
            cols = set(rd.fieldnames or [])
            missing = sorted(required - cols)
            if missing:
                raise InputValidationError(
                    "MISSING_COLUMNS", f"{label} is missing required column(s) {missing}",
                    detail={"path": str(path), "found": sorted(cols)})
            return list(rd)

    hrows = _rows(hourly_path, req_h, "carrier hourly plan")
    irows = _rows(initial_path, req_i, "carrier initial inventory")
    if not hrows:
        errors.append("carrier hourly plan must contain at least one data row")
    if not irows:
        errors.append("carrier initial inventory must contain at least one data row")

    def _int(v, where, field):
        try:
            f = float(v)
        except (TypeError, ValueError):
            errors.append(f"{where}: {field}='{v}' is not numeric")
            return None
        if abs(f - round(f)) > 1e-9:
            errors.append(f"{where}: {field}={v} must be an integer (container count)")
            return None
        if f < 0:
            errors.append(f"{where}: {field}={v} must be nonnegative")
            return None
        return int(round(f))

    seen = set()
    carriers_h, hubs_h, sizes_h, stamps = set(), set(), set(), set()
    for i, r in enumerate(hrows, 2):
        where = f"hourly row {i}"
        carrier = (r.get("carrier_id") or "").strip()
        if not carrier:
            errors.append(f"{where}: carrier_id must be a nonblank string")
        try:
            ts = datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            errors.append(f"{where}: timestamp '{r.get('timestamp')}' must be 'YYYY-MM-DD HH:MM'")
            continue
        if r["hub_code"] not in HUB_CODES:
            errors.append(f"{where}: unknown hub_code '{r['hub_code']}'")
        if r["container_size"] not in SIZE_CODES:
            errors.append(f"{where}: unknown container_size '{r['container_size']}'")
        key = (carrier, ts, r["hub_code"], r["container_size"])
        if key in seen:
            errors.append(f"{where}: duplicate (carrier,timestamp,hub,size) {key}")
        seen.add(key)
        _int(r["demand"], where, "demand")
        _int(r["supply_total"], where, "supply_total")
        if carrier:
            carriers_h.add(carrier)
        hubs_h.add(r["hub_code"])
        sizes_h.add(r["container_size"]); stamps.add(ts)

    if hubs_h != HUB_CODES:
        errors.append(f"hourly hub set must equal the six AXIS hubs: "
                      f"missing={sorted(HUB_CODES - hubs_h)} "
                      f"extra={sorted(hubs_h - HUB_CODES, key=str)}")
    if sizes_h != SIZE_CODES:
        errors.append(f"hourly container_size set must equal {sorted(SIZE_CODES)}: "
                      f"missing={sorted(SIZE_CODES - sizes_h)} "
                      f"extra={sorted(sizes_h - SIZE_CODES, key=str)}")

    if stamps:
        ordered = sorted(stamps)
        gaps = [(ordered[i - 1], ordered[i]) for i in range(1, len(ordered))
                if (ordered[i] - ordered[i - 1]) != timedelta(hours=1)]
        if gaps:
            errors.append(f"hourly timestamps are not continuous at 1h: "
                          f"{[(str(a), str(b)) for a, b in gaps[:3]]}")
        expected = len(carriers_h) * len(hubs_h) * len(sizes_h) * len(ordered)
        if len(seen) != expected:
            errors.append(f"incomplete carrier x hub x size x time grid: "
                          f"{len(seen)} rows, expected {expected}")

    iseen = set(); carriers_i = set()
    for i, r in enumerate(irows, 2):
        where = f"initial row {i}"
        carrier = (r.get("carrier_id") or "").strip()
        if not carrier:
            errors.append(f"{where}: carrier_id must be a nonblank string")
        if r["hub_code"] not in HUB_CODES:
            errors.append(f"{where}: unknown hub_code '{r['hub_code']}'")
        if r["container_size"] not in SIZE_CODES:
            errors.append(f"{where}: unknown container_size '{r['container_size']}'")
        key = (carrier, r["hub_code"], r["container_size"])
        if key in iseen:
            errors.append(f"{where}: duplicate (carrier,hub,size) {key}")
        iseen.add(key)
        _int(r["initial_inventory"], where, "initial_inventory")
        if carrier:
            carriers_i.add(carrier)

    hubs_i = {r.get("hub_code") for r in irows}
    sizes_i = {r.get("container_size") for r in irows}
    if hubs_i != HUB_CODES:
        errors.append(f"initial hub set must equal the six AXIS hubs: "
                      f"missing={sorted(HUB_CODES - hubs_i)} "
                      f"extra={sorted(hubs_i - HUB_CODES, key=str)}")
    if sizes_i != SIZE_CODES:
        errors.append(f"initial container_size set must equal {sorted(SIZE_CODES)}: "
                      f"missing={sorted(SIZE_CODES - sizes_i)} "
                      f"extra={sorted(sizes_i - SIZE_CODES, key=str)}")

    if carriers_h and carriers_i and carriers_h != carriers_i:
        errors.append(f"carrier set mismatch: hourly={sorted(carriers_h)} "
                      f"initial={sorted(carriers_i)}")
    for c in sorted(carriers_h):
        for h in sorted(HUB_CODES):
            for k in sorted(SIZE_CODES):
                if (c, h, k) not in iseen:
                    errors.append(f"initial inventory missing for {(c, h, k)}")

    if errors:
        raise InputValidationError(
            "CARRIER_INPUT_INVALID",
            f"선사 제출 데이터 검증에서 {len(errors)}건의 문제가 발견되었습니다.",
            detail={"hourly": str(hourly_path), "initial": str(initial_path),
                    "error_count": len(errors)}, errors=errors)

    return {"carriers": sorted(carriers_h), "hubs": sorted(hubs_h),
            "sizes": sorted(sizes_h), "timestamps": len(stamps),
            "rows": len(hrows), "initial_rows": len(irows)}


def validate_candidate_inputs(indir: Path, timestamps=None) -> dict:
    """
    KORAIL candidate 4개 파일의 cross-file 검증 (지시서 §9).
    외부 파일이 잘못되면 synthetic 으로 덮어쓰지 않고 여기서 명확히 실패시킨다.
    """
    indir = Path(indir)
    errors = []
    need = ["TRAIN_CANDIDATE.csv", "TRAIN_STOP_TIME.csv",
            "TRAIN_SEGMENT.csv", "TRAIN_FORMATION_OPTION.csv"]
    missing = [f for f in need if not (indir / f).exists()]
    if missing:
        raise InputValidationError("CANDIDATE_FILE_MISSING",
                                   f"candidate directory is missing {missing}",
                                   detail={"dir": str(indir), "required": need})

    def rows(name):
        with (indir / name).open(encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    cand, stop, seg, form = (rows(n) for n in need)
    for name, data in zip(need, (cand, stop, seg, form)):
        if not data:
            errors.append(f"{name}: file must contain at least one data row")

    cpaths, sources, source_by_train = {}, set(), {}
    cids = []
    for i, r in enumerate(cand, 2):
        tid = r.get("train_id")
        if not tid:
            errors.append(f"TRAIN_CANDIDATE row {i}: missing train_id"); continue
        if tid in cpaths:
            errors.append(f"TRAIN_CANDIDATE row {i}: duplicate train_id {tid}"); continue
        path = tuple((r.get("path") or "").split("|"))
        if len(path) < 2 or any(h not in HUB_CODES for h in path):
            errors.append(f"{tid}: invalid path {r.get('path')}")
        if r.get("origin_terminal") and path and r["origin_terminal"] != path[0]:
            errors.append(f"{tid}: origin_terminal != path[0]")
        if r.get("destination_terminal") and path and r["destination_terminal"] != path[-1]:
            errors.append(f"{tid}: destination_terminal != path[-1]")
        try:
            if float(r["service_distance_km"]) <= 0:
                errors.append(f"{tid}: service_distance_km must be > 0")
        except (KeyError, TypeError, ValueError):
            errors.append(f"{tid}: service_distance_km missing or non-numeric")
        src = r.get("candidate_source") or ""
        if not src:
            errors.append(f"{tid}: candidate_source is required")
        ws = [h for h in (r.get("work_stops") or "").split("|") if h]
        if src == "KORAIL_FEASIBLE_PATH" and not ws:
            errors.append(f"{tid}: KORAIL_FEASIBLE_PATH requires explicit work_stops")
        if ws:
            if not set(ws) <= set(path):
                errors.append(f"{tid}: work_stops {ws} not a subset of path")
            if path and (path[0] not in ws or path[-1] not in ws):
                errors.append(f"{tid}: origin and destination must be work stops")
        sources.add(src)
        source_by_train[tid] = src
        cpaths[tid] = path
        cids.append(tid)

    horizon = None
    if timestamps:
        horizon = (timestamps[0], timestamps[-1])

    stops = defaultdict(list)
    for i, r in enumerate(stop, 2):
        tid = r.get("train_id")
        if tid not in cpaths:
            errors.append(f"TRAIN_STOP_TIME row {i}: unknown train_id {tid}"); continue
        try:
            stops[tid].append((int(r["stop_sequence"]), r["hub_code"],
                               int(r["load_start_slot"]), int(r["arrival_slot"]),
                               int(r["departure_slot"]), int(r["available_slot"])))
        except (KeyError, TypeError, ValueError):
            errors.append(f"TRAIN_STOP_TIME row {i}: missing/invalid slot column")
        if source_by_train.get(tid) == "KORAIL_FEASIBLE_PATH":
            for col in ("actual_load_start_time", "actual_arrival_time",
                        "actual_departure_time", "actual_available_time"):
                raw = r.get(col)
                try:
                    datetime.strptime(raw or "", "%Y-%m-%d %H:%M")
                except (TypeError, ValueError):
                    errors.append(f"{tid}/{r.get('hub_code')}: {col} is required as YYYY-MM-DD HH:MM")
    for tid, path in cpaths.items():
        st = sorted(stops.get(tid, []))
        if [x[1] for x in st] != list(path):
            errors.append(f"{tid}: stop hub order {[x[1] for x in st]} != path {list(path)}")
            continue
        if [x[0] for x in st] != list(range(1, len(st) + 1)):
            errors.append(f"{tid}: stop_sequence is not 1..n")
        prev_dep = None
        for idx, (_, hub, ld, ar, dp, av) in enumerate(st):
            if ld > dp:
                errors.append(f"{tid}/{hub}: load_start_slot > departure_slot")
            if idx > 0 and ar > dp:
                errors.append(f"{tid}/{hub}: arrival_slot > departure_slot")
            if av < ar:
                errors.append(f"{tid}/{hub}: available_slot < arrival_slot")
            if prev_dep is not None and ar < prev_dep:
                errors.append(f"{tid}/{hub}: arrival_slot precedes previous departure")
            prev_dep = dp
            if timestamps is not None:
                for nm, v in (("load_start", ld), ("arrival", ar),
                              ("departure", dp), ("available", av)):
                    if not (0 <= v < len(timestamps)):
                        errors.append(f"{tid}/{hub}: {nm}_slot {v} outside planning horizon "
                                      f"0..{len(timestamps) - 1}")

    segs = defaultdict(list)
    for i, r in enumerate(seg, 2):
        tid = r.get("train_id")
        if tid not in cpaths:
            errors.append(f"TRAIN_SEGMENT row {i}: unknown train_id {tid}"); continue
        try:
            d = float(r["segment_distance_km"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"TRAIN_SEGMENT row {i}: segment_distance_km missing/non-numeric")
            continue
        if d <= 0:
            errors.append(f"TRAIN_SEGMENT row {i}: segment_distance_km must be > 0")
        segs[tid].append((int(r["segment_sequence"]), (r["from_hub"], r["to_hub"]), d))
    cand_dist = {r["train_id"]: float(r["service_distance_km"])
                 for r in cand if r.get("train_id") and r.get("service_distance_km")}
    for tid, path in cpaths.items():
        sg = sorted(segs.get(tid, []))
        expect = [(path[i], path[i + 1]) for i in range(len(path) - 1)]
        if [x[1] for x in sg] != expect:
            errors.append(f"{tid}: segment pairs {[x[1] for x in sg]} != path consecutive {expect}")
            continue
        if [x[0] for x in sg] != list(range(1, len(sg) + 1)):
            errors.append(f"{tid}: segment_sequence is not 1..n")
        total = sum(x[2] for x in sg)
        declared = cand_dist.get(tid)
        if declared is not None and abs(total - declared) > 0.05:
            errors.append(f"{tid}: service_distance_km {declared} != Σ segment_distance_km "
                          f"{round(total, 3)} (tolerance 0.05km)")

    fseen = set(); fcount = defaultdict(int)
    for i, r in enumerate(form, 2):
        tid = r.get("train_id")
        if tid not in cpaths:
            errors.append(f"TRAIN_FORMATION_OPTION row {i}: unknown train_id {tid}"); continue
        fid = r.get("formation_id")
        if (tid, fid) in fseen:
            errors.append(f"{tid}: duplicate formation_id {fid}")
        fseen.add((tid, fid)); fcount[tid] += 1
        for col in ("wagon_count", "capacity_teu"):
            try:
                if float(r[col]) <= 0:
                    errors.append(f"{tid}/{fid}: {col} must be > 0")
            except (KeyError, TypeError, ValueError):
                errors.append(f"{tid}/{fid}: {col} missing or non-numeric")
    for tid in cpaths:
        if fcount.get(tid, 0) < 1:
            errors.append(f"{tid}: needs at least one formation option")

    for label, ids in (("stop", set(stops)), ("segment", set(segs)),
                       ("formation", {t for t, _ in fseen})):
        if ids != set(cpaths):
            errors.append(f"train_id set mismatch between candidate and {label} file: "
                          f"only_in_candidate={sorted(set(cpaths) - ids)[:5]} "
                          f"only_in_{label}={sorted(ids - set(cpaths))[:5]}")

    if errors:
        raise InputValidationError(
            "CANDIDATE_INPUT_INVALID",
            f"KORAIL candidate 파일 검증에서 {len(errors)}건의 문제가 발견되었습니다. "
            "외부 후보는 자동 보정하거나 synthetic 으로 대체하지 않습니다.",
            detail={"dir": str(indir), "error_count": len(errors)}, errors=errors)

    return {"train_count": len(cpaths), "candidate_sources": sorted(sources),
            "horizon": [str(horizon[0]), str(horizon[1])] if horizon else None}


def _candidate_sources(trains) -> List[str]:
    srcs = {getattr(p, "candidate_source", "PROTOTYPE_SYNTHETIC") for p in trains}
    srcs.discard("")
    return sorted(srcs)


def _candidate_source_label(meta, trains=None) -> str:
    """실제로 선택된 후보열차의 source 에서 유도한다 (지시서 §11)."""
    if trains is None:
        trains = meta.get("trains", {}).values()
    srcs = set(_candidate_sources(trains))
    srcs.discard("")
    if not srcs:
        return "NONE"
    return srcs.pop() if len(srcs) == 1 else "MIXED"


def diagnose_unserved_reasons(service, trains, needs, min_load_factor,
                              default_max_earliness, assignments):
    """
    미배정 원인 중 **사전 검사로 증명 가능한 것만** 분류한다 (지시서 §15).
    나머지는 UNSERVED_AFTER_JOINT_OPTIMIZATION 으로 남기고 단정하지 않는다.
    """
    source_cap = service["source_cap"]
    assigned_needs = {a.need_id for a in assignments}
    reason = {}
    for n in needs:
        nid = n["need_id"]
        if nid in assigned_needs:
            continue
        c, k, d = n["carrier_id"], n["container_size"], n["destination"]
        due = int(n["due_slot"])
        earliest = (max(0, due - int(math.ceil(float(default_max_earliness))))
                    if default_max_earliness is not None else 0)
        time_ok, source_ok = False, False
        for p in trains:
            if d not in p.path or not p.can_work(d):
                continue
            avail = p.avail_slot.get(d, p.arr_slot[d])
            if avail > due or avail < earliest:
                continue
            time_ok = True
            dpos = p.path.index(d)
            for o in p.path[:dpos]:
                if not p.can_work(o):
                    continue
                lt = p.load_slot.get(o, p.dep_slot[o])
                if source_cap.get((c, o, k, lt), 0) > 0:
                    source_ok = True
                    break
            if source_ok:
                break
        if not time_ok:
            reason[nid] = "NO_TIME_COMPATIBLE_TRAIN"
        elif not source_ok:
            reason[nid] = "NO_SOURCE_RELEASE_CAPACITY"
        else:
            reason[nid] = "NO_CANDIDATE_AFTER_CONSOLIDATION_PRUNING"
    return reason


def build_inventory_timeline(service, positive, meta):
    """
    최적화 후 시간별 재고 timeline (지시서 §12).
    replay 순서는 TIME_SLOT_CONVENTION.md 와 동일하다.
        1) external supply  2) rail inbound  3) demand  4) rail outbound release
    """
    ts = service["timestamps"]
    demand, supply = service["demand"], service["supply"]
    inbound = defaultdict(int)
    outbound = defaultdict(int)
    for a, q in positive:
        inbound[(a.carrier, a.destination, a.size, a.arr_slot)] += q
        outbound[(a.carrier, a.origin, a.size, a.dep_slot)] += q

    initial = {}
    for row in service["baseline_rows"]:
        key = (row["carrier_id"], row["hub_code"], row["container_size"])
        initial.setdefault(key, None)

    rows = []
    impact = []
    for c in service["carriers"]:
        for h in service["hubs"]:
            for k in service["sizes"]:
                stock = service["initial_inventory"][(c, h, k)]
                base_stock = stock
                base_short = 0
                post_short = 0
                min_base = base_stock
                min_post = stock
                for t, stamp in enumerate(ts):
                    d = demand[(c, h, k, t)]
                    s = supply[(c, h, k, t)]
                    inb = inbound.get((c, h, k, t), 0)
                    outb = outbound.get((c, h, k, t), 0)

                    base_avail = base_stock + s
                    b_unmet = max(d - base_avail, 0)
                    base_stock = max(base_avail - d, 0)
                    base_short += b_unmet
                    min_base = min(min_base, base_stock)

                    avail = stock + s + inb
                    p_unmet = max(d - avail, 0)
                    stock = max(avail - d, 0) - outb
                    post_short += p_unmet
                    min_post = min(min_post, stock)

                    rows.append({
                        "carrier_id": c, "timestamp": stamp.strftime("%Y-%m-%d %H:%M"),
                        "hub_code": h, "container_size": k,
                        "demand": d, "external_supply": s,
                        "rail_inbound_boxes": inb, "rail_outbound_boxes": outb,
                        "baseline_inventory": base_stock,
                        "post_rail_inventory": stock,
                        "baseline_unmet_demand": b_unmet,
                        "post_rail_unmet_demand": p_unmet})
                impact.append({
                    "carrier_id": c, "hub_code": h, "container_size": k,
                    "baseline_stockout_boxes": base_short,
                    "post_rail_stockout_boxes": post_short,
                    "stockout_reduction_boxes": base_short - post_short,
                    "minimum_baseline_inventory": min_base,
                    "minimum_post_rail_inventory": min_post,
                    "rail_inbound_boxes": sum(v for (cc, hh, kk, _), v in inbound.items()
                                              if (cc, hh, kk) == (c, h, k)),
                    "rail_outbound_boxes": sum(v for (cc, hh, kk, _), v in outbound.items()
                                               if (cc, hh, kk) == (c, h, k))})
    return rows, impact


# ===========================================================================
# Joint Multi-Carrier MILP
# ===========================================================================
def build_milp(service, trains, min_load_factor=0.5, operations_obj=None,
               default_max_earliness=None, carrier_subset=None):
    """
    같은 planning cycle 에 제출된 모든 선사의 Service Need 를 하나의 MILP 로 구성한다.
    선사별로 따로 풀어 합치는 구조가 아니다.

    변수
        x[r,o,p]  Service Need r 을 origin o 에서 train p 로 몇 박스 운송하는지
        u[r]      철도로 배정되지 않은 Service Need
        y[p]      candidate train p 를 실제 운행하는지
        z[p,m]    train p 가 formation m 을 사용하는지

    carrier_subset 은 연구용 Carrier Separate baseline 전용이며,
    실제 서비스 흐름에서는 항상 None (전체 선사 공동 최적화) 이다.
    """
    operations_obj = operations_obj or {}

    needs = [dict(r) for r in service["needs"]]
    if carrier_subset is not None:
        needs = [r for r in needs if r["carrier_id"] in carrier_subset]
    source_cap = service["source_cap"]
    timestamps = service["timestamps"]
    need_by_id = {r["need_id"]: r for r in needs}

    # 도착 시간창. 선사가 사전 제출한 정책 외에 서비스 전역 조기도착 상한을 둔다.
    effective_due = {nid: int(nd["due_slot"]) for nid, nd in need_by_id.items()}
    effective_earliest = {}
    for nid, nd in need_by_id.items():
        due = effective_due[nid]
        if default_max_earliness is not None:
            effective_earliest[nid] = max(0, due - int(math.ceil(float(default_max_earliness))))
        else:
            effective_earliest[nid] = 0
        if effective_earliest[nid] > due:
            raise ValueError(f"arrival window infeasible for {nid}")

    # ---- Candidate assignment 변수 ----------------------------------------
    assignments = []
    idx = 0
    U = {}
    for n in needs:
        U[n["need_id"]] = idx
        idx += 1

    for n in needs:
        nid = n["need_id"]
        c = n["carrier_id"]
        k = n["container_size"]
        d = n["destination"]
        due = int(effective_due[nid])
        earliest = int(effective_earliest[nid])
        for p in trains:
            # v7.1-patch: 통과역에서는 내릴 수 없다.
            if d not in p.path or not p.can_work(d):
                continue
            avail_t = p.avail_slot.get(d, p.arr_slot[d])      # 하화 완료 = 사용 가능
            if avail_t > due or avail_t < earliest:
                continue
            dpos = p.path.index(d)
            for o in p.path[:dpos]:
                # v7.1-patch: 통과역에서는 실을 수 없다.
                if not p.can_work(o):
                    continue
                load_t = p.load_slot.get(o, p.dep_slot[o])    # 상차 개시 = 재고 필요
                if source_cap[(c, o, k, load_t)] <= 0:
                    continue
                segs = subpath_segments(p.path, o, d)
                if not segs:
                    continue
                assignments.append(AssignVar(idx, nid, c, k, o, d, p.train_id,
                                             load_t, avail_t, segs, fare_per_box(o, d, k)))
                idx += 1

    # ---- 최소 consolidation 을 만족할 수 없는 후보열차 사전 제거 -----------
    # 달성 가능한 최대 적재(상한) 기준이므로 최적해를 배제하지 않는다.
    if min_load_factor is not None and min_load_factor > 0:
        pmap = {p.train_id: p for p in trains}
        by_t_need = defaultdict(list)
        for a in assignments:
            by_t_need[(a.train_id, a.need_id)].append(a)
        potential = defaultdict(float)
        for (tid, nid), alist in by_t_need.items():
            nd = need_by_id[nid]
            p = pmap[tid]
            best = max(p.path_km(a.segments) for a in alist)
            potential[tid] += nd["quantity"] * TEU[nd["container_size"]] * best
        feasible = set()
        for tid, val in potential.items():
            p = pmap[tid]
            total = p.path_km()
            min_cap = min(p.capacity(f) for f in p.formations)
            if val + 1e-9 >= float(min_load_factor) * min_cap * total:
                feasible.add(tid)
        assignments = [a for a in assignments if a.train_id in feasible]

    idx = len(U)
    for a in assignments:
        a.var = idx
        idx += 1
    relevant = sorted({a.train_id for a in assignments})
    train_by_id = {p.train_id: p for p in trains if p.train_id in set(relevant)}
    Y = {}
    Z = {}
    for tid in relevant:
        Y[tid] = idx
        idx += 1
        for f in train_by_id[tid].formations:
            Z[(tid, f)] = idx
            idx += 1

    nvars = idx
    lo = np.zeros(nvars)
    up = np.full(nvars, np.inf)
    integ = np.ones(nvars, dtype=int)
    for v in Y.values():
        up[v] = 1
    for v in Z.values():
        up[v] = 1
    for a in assignments:
        up[a.var] = need_by_id[a.need_id]["quantity"]
    for nid, v in U.items():
        up[v] = need_by_id[nid]["quantity"]

    rows = SparseRows(nvars)
    by_need = defaultdict(list)
    by_source = defaultdict(list)
    by_train_seg = defaultdict(list)
    by_train = defaultdict(list)
    for a in assignments:
        by_need[a.need_id].append(a)
        by_source[(a.carrier, a.origin, a.size)].append(a)
        by_train[a.train_id].append(a)
        for seg in a.segments:
            by_train_seg[(a.train_id, seg)].append(a)

    # 1. Need conservation
    for nd in needs:
        coeff = {U[nd["need_id"]]: 1}
        for a in by_need[nd["need_id"]]:
            coeff[a.var] = 1
        rows.add(coeff, lb=nd["quantity"], ub=nd["quantity"])

    # 2. Source release capacity — carrier ownership 보호
    #    A 선사 재고는 A 선사 Need 에만 쓰이며, 자체 수요를 훼손하지 않는 범위에서만 반출된다.
    for (c, o, k), alist in by_source.items():
        dep_times = sorted({a.dep_slot for a in alist})
        if not dep_times:
            continue
        check = set(dep_times)
        prev = None
        for t in range(min(dep_times), len(timestamps)):
            cap = source_cap[(c, o, k, t)]
            if prev is not None and cap < prev:
                check.add(t)
            prev = cap
        check.add(len(timestamps) - 1)
        for t in sorted(check):
            coeff = {a.var: 1 for a in alist if a.dep_slot <= t}
            if coeff:
                rows.add(coeff, ub=source_cap[(c, o, k, t)])

    # 3. Formation selection
    for tid in relevant:
        coeff = {Y[tid]: -1}
        for f in train_by_id[tid].formations:
            coeff[Z[(tid, f)]] = 1
        rows.add(coeff, lb=0, ub=0)

    # 4. Segment capacity — 여러 선사 공컨이 같은 구간 capacity 를 공동사용한다
    for tid in relevant:
        p = train_by_id[tid]
        for seg in p.segments:
            coeff = {}
            for a in by_train_seg[(tid, seg)]:
                coeff[a.var] = TEU[a.size]
            for f in p.formations:
                coeff[Z[(tid, f)]] = -p.capacity(f)
            rows.add(coeff, ub=0)

    # 5. Minimum Consolidation Level Scenario (KORAIL 공식 손익분기 기준이 아님)
    if min_load_factor is not None and min_load_factor > 0:
        alpha = float(min_load_factor)
        for tid in relevant:
            p = train_by_id[tid]
            total = p.path_km()
            coeff = defaultdict(float)
            for a in by_train[tid]:
                coeff[a.var] += TEU[a.size] * p.path_km(a.segments)
            for f in p.formations:
                coeff[Z[(tid, f)]] -= alpha * p.capacity(f) * total
            rows.add(dict(coeff), lb=0)

    # 6. 물리적 중복열차 제한 — 데이터 유무와 무관한 사실이므로 항상 활성
    operational_audit = []
    conflict = defaultdict(list)
    for tid, p in train_by_id.items():
        conflict[(p.path[0], p.dep_slot[p.path[0]])].append(tid)
    n_conf = 0
    for key, tids in sorted(conflict.items()):
        if len(tids) > 1:
            rows.add({Y[t]: 1 for t in tids}, ub=1)
            n_conf += 1
    if n_conf:
        operational_audit.append({
            "type": "DUPLICATE_CANDIDATE_GUARD_DEPARTURE_SLOT", "status": "APPLIED",
            "constrained_groups": n_conf,
            "scope": "PROTOTYPE_DUPLICATE_CANDIDATE_GUARD",
            "rule": "at most one new train per (origin_terminal, departure_slot). "
                    "NOT a full track-occupancy / headway model."})
    trunk = defaultdict(list)
    for tid, p in train_by_id.items():
        for seg in p.segments:
            if seg in SHARED_TRUNK_SEGMENTS:
                trunk[(seg, p.dep_slot[seg[0]])].append(tid)
    n_trunk = 0
    for key, tids in sorted(trunk.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        if len(tids) > 1:
            rows.add({Y[t]: 1 for t in tids}, ub=1)
            n_trunk += 1
    if n_trunk:
        operational_audit.append({
            "type": "DUPLICATE_CANDIDATE_GUARD_SHARED_TRUNK", "status": "APPLIED",
            "constrained_groups": n_trunk,
            "scope": "PROTOTYPE_DUPLICATE_CANDIDATE_GUARD",
            "rule": "at most one new train per shared trunk segment per hour. "
                    "NOT a full track-occupancy / headway model."})

    # 7. KORAIL Operational Inputs (실제 데이터가 있을 때만 활성)
    for kind in ("path_slot_capacity", "resource_capacity"):
        if not operations_obj.get(kind):
            operational_audit.append({
                "type": kind.upper(), "status": "NOT_APPLIED_NO_DATA",
                "rule": "KORAIL 실제 운영자원 데이터가 제공되지 않아 비활성. "
                        "구조는 구현되어 있으며 값만 넣으면 즉시 적용된다."})
    for rule in operations_obj.get("path_slot_capacity", []):
        st = datetime.strptime(rule["start_time"], "%Y-%m-%d %H:%M")
        en = datetime.strptime(rule["end_time"], "%Y-%m-%d %H:%M")
        coeff = {}
        for tid, p in train_by_id.items():
            if not (st <= p.origin_departure <= en):
                continue
            if not family_matches(p.family, rule.get("service_family")):
                continue
            if rule.get("origin_terminal") and p.path[0] != rule["origin_terminal"]:
                continue
            if rule.get("destination_terminal") and p.path[-1] != rule["destination_terminal"]:
                continue
            coeff[Y[tid]] = 1
        if coeff:
            rows.add(coeff, ub=int(rule["max_trains"]))
            operational_audit.append({
                "type": "PATH_SLOT_CAPACITY", "status": "APPLIED",
                "matched_trains": len(coeff), "limit": int(rule["max_trains"]),
                "rule": json.dumps(rule, ensure_ascii=False)})
    for rule in operations_obj.get("resource_capacity", []):
        _, s0 = _parse_time_in_horizon(rule["start_time"], service, "resource start_time")
        _, s1 = _parse_time_in_horizon(rule["end_time"], service, "resource end_time")
        for t in range(s0, s1 + 1):
            # v7.1-patch (지시서 §19): 자원은 출발~도착이 아니라
            # 출발역 상차개시 ~ 도착역 하화완료 까지 점유된다.
            active = []
            for tid, p in train_by_id.items():
                lo_t = p.load_slot.get(p.path[0], p.dep_slot[p.path[0]])
                hi_t = p.avail_slot.get(p.path[-1], p.arr_slot[p.path[-1]])
                if lo_t <= t <= hi_t:
                    active.append(tid)
            if not active:
                continue
            if rule.get("available_locomotives") is not None:
                rows.add({Y[tid]: 1 for tid in active},
                         ub=int(rule["available_locomotives"]))
            if rule.get("available_wagons") is not None:
                coeff = {}
                for tid in active:
                    p = train_by_id[tid]
                    for f in p.formations:
                        coeff[Z[(tid, f)]] = p.wagons(f)
                rows.add(coeff, ub=int(rule["available_wagons"]))
        operational_audit.append({
            "type": "RESOURCE_CAPACITY", "status": "APPLIED",
            "matched_time_slots": s1 - s0 + 1,
            "rule": json.dumps(rule, ensure_ascii=False)})

    # 8. 선사가 계획 실행 전에 제출한 재고정책 (사후 협상 기능이 아니다)
    policy_audit = []
    inv_ub = service.get("inventory_ub", {}) or {}
    baseline_stock = service.get("baseline_stock", {})
    by_dest = defaultdict(list)
    for a in assignments:
        by_dest[(a.carrier, a.destination, a.size)].append(a)
    for (c, h, k, t), cap in sorted(inv_ub.items()):
        alist = [a for a in by_dest.get((c, h, k), []) if a.arr_slot <= t]
        if not alist:
            continue
        rows.add({a.var: 1 for a in alist},
                 ub=max(cap - baseline_stock.get((c, h, k, t), 0), 0))
    if inv_ub:
        policy_audit.append({"policy": "MAX_INVENTORY", "constrained_slots": len(inv_ub)})
    for (c, h, k), (cap, s0, s1) in sorted(service.get("outbound_cap", {}).items()):
        alist = [a for a in by_source.get((c, h, k), []) if s0 <= a.dep_slot <= s1]
        if not alist:
            continue
        rows.add({a.var: 1 for a in alist}, ub=cap)
        policy_audit.append({"policy": "ORIGIN_RELEASE_RESTRICTION", "carrier": c,
                             "hub": h, "size": k, "max_boxes": cap,
                             "candidate_vars": len(alist)})

    A = rows.matrix()
    meta = {"needs": needs, "need_by_id": need_by_id, "assignments": assignments,
            "U": U, "Y": Y, "Z": Z, "trains": train_by_id,
            "by_train": by_train, "by_train_seg": by_train_seg,
            "A": A, "lb": np.array(rows.lb), "ub": np.array(rows.ub),
            "timestamps": timestamps, "source_cap": source_cap,
            "min_load_factor": min_load_factor,
            "effective_due": effective_due, "effective_earliest": effective_earliest,
            "operational_audit": operational_audit, "policy_audit": policy_audit,
            "active_policies": service.get("active_policies", []),
            "operations_active": bool(operations_obj.get("path_slot_capacity")
                                      or operations_obj.get("resource_capacity")),
            "carrier_subset": sorted(carrier_subset) if carrier_subset else None,
            "default_max_earliness": default_max_earliness}
    return meta, lo, up, integ


# ===========================================================================
# Output — 동일 solution 의 두 관점
# ===========================================================================
def extract(meta, result, summary, outdir: Path, scenario: str, solver_audit=None,
            service=None, unserved_reason=None):
    unserved_reason = unserved_reason or {}
    """
    하나의 MILP solution 에서
      - 선사 관점 : CARRIER_RECOMMENDATIONS / _DETAIL / RECOMMENDATION_EXPLANATION_CONTEXT
      - KORAIL 관점 : KORAIL_TRAIN_PLAN / CARRIER_ALLOCATION / STOP_WORK_PLAN / SEGMENT_LOAD
    을 생성한다. 두 관점의 물량 합계는 정의상 일치하며 SUMMARY 에서 검증한다.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    x = result.x
    positive = [(a, int(round(x[a.var]))) for a in meta["assignments"]
                if int(round(x[a.var])) > 0]
    selected = {tid: p for tid, p in meta["trains"].items() if x[meta["Y"][tid]] > 0.5}
    chosen = {}
    for tid, p in selected.items():
        for f in p.formations:
            if x[meta["Z"][(tid, f)]] > 0.5:
                chosen[tid] = f
                break

    ts = meta["timestamps"]

    def _actual(values, hub, model_slot):
        return values.get(hub, ts[model_slot])

    def _fmt(value):
        return value.strftime("%Y-%m-%d %H:%M")

    train_carriers = defaultdict(set)
    for a, q in positive:
        train_carriers[a.train_id].add(a.carrier)

    # ---- 구간 적재 / 상하차 ------------------------------------------------
    segload = defaultdict(int)
    stop_load = defaultdict(int)
    stop_unload = defaultdict(int)
    train_size_boxes = defaultdict(int)
    for a, q in positive:
        stop_load[(a.train_id, a.origin)] += q * TEU[a.size]
        stop_unload[(a.train_id, a.destination)] += q * TEU[a.size]
        train_size_boxes[(a.train_id, a.size)] += q
        for seg in a.segments:
            segload[(a.train_id, seg)] += q * TEU[a.size]

    train_rows = []
    segment_rows = []
    stop_rows = []
    train_lf = {}
    for tid, p in sorted(selected.items()):
        f = chosen[tid]
        cap = p.capacity(f)
        loads = []
        dw = 0.0
        dist = 0.0
        for si, seg in enumerate(p.segments, 1):
            l = segload[(tid, seg)]
            d = p.seg_km(seg)
            loads.append(l)
            dw += l * d
            dist += d
            segment_rows.append({
                "train_id": tid, "segment_sequence": si,
                "segment": f"{seg[0]}>{seg[1]}",
                "from_hub": seg[0], "to_hub": seg[1],
                "loaded_teu": l, "capacity_teu": cap,
                "load_factor": round(l / cap, 4),
                "physical_distance_km": d})
        lf = round(dw / (cap * dist), 4) if dist else 0.0
        train_lf[tid] = lf
        assigned = sum(q * TEU[a.size] for a, q in positive if a.train_id == tid)
        actual_origin_departure = _actual(
            p.actual_departure_time, p.path[0], p.dep_slot[p.path[0]])
        actual_final_arrival = _actual(
            p.actual_arrival_time, p.path[-1], p.arr_slot[p.path[-1]])
        actual_dwell_minutes = round(sum(
            max((_actual(p.actual_departure_time, h, p.dep_slot[h])
                 - _actual(p.actual_arrival_time, h, p.arr_slot[h])).total_seconds(), 0) / 60
            for h in p.path[1:-1]), 1)
        model_transit_hours = p.arr_slot[p.path[-1]] - p.dep_slot[p.path[0]]
        model_dwell_hours = sum(p.dep_slot[h] - p.arr_slot[h] for h in p.path[1:-1])
        train_rows.append({
            "train_id": tid, "route": " > ".join(p.path), "service_family": p.family,
            "origin_terminal": p.path[0], "destination_terminal": p.path[-1],
            "origin_departure": _fmt(actual_origin_departure),
            "final_arrival": _fmt(actual_final_arrival),
            "actual_origin_departure": _fmt(actual_origin_departure),
            "actual_final_arrival": _fmt(actual_final_arrival),
            "model_origin_departure_slot": p.dep_slot[p.path[0]],
            "model_final_arrival_slot": p.arr_slot[p.path[-1]],
            "model_origin_departure_time": _fmt(ts[p.dep_slot[p.path[0]]]),
            "model_final_arrival_time": _fmt(ts[p.arr_slot[p.path[-1]]]),
            "formation": f, "wagons": p.wagons(f), "capacity_teu": cap,
            "total_assigned_teu": assigned,
            "peak_load_teu": max(loads) if loads else 0,
            "distance_weighted_load_factor": lf,
            "participating_carrier_count": len(train_carriers[tid]),
            "train_km": round(dist, 1),
            "wagon_km": round(p.wagons(f) * dist, 1),
            "candidate_source": getattr(p, "candidate_source", "PROTOTYPE_SYNTHETIC"),
            "work_stops": "|".join(p.work_stops) if p.work_stops else " > ".join(p.path),
            "work_stop_count": len(p.work_stops) if p.work_stops else len(p.path),
            "actual_transit_minutes": round(
                (actual_final_arrival - actual_origin_departure).total_seconds() / 60, 1),
            "actual_dwell_minutes": actual_dwell_minutes,
            "model_transit_hours": model_transit_hours,
            "model_dwell_hours": model_dwell_hours,
            "transit_hours": model_transit_hours,
            "dwell_hours": model_dwell_hours,
            "20ft_boxes": train_size_boxes[(tid, "20FT")],
            "40ft_boxes": train_size_boxes[(tid, "40FT")],
            "total_container_boxes": (train_size_boxes[(tid, "20FT")]
                                      + train_size_boxes[(tid, "40FT")])})
        for seqno, hub in enumerate(p.path, 1):
            stop_rows.append({
                "train_id": tid, "stop_sequence": seqno, "hub": hub,
                "hub_name": HUB_NAME[hub],
                "stop_type": "WORK_STOP" if p.can_work(hub) else "PASS_THROUGH",
                "load_start": _fmt(_actual(p.actual_load_start_time, hub,
                                             p.load_slot.get(hub, p.dep_slot[hub]))),
                "arrival": _fmt(_actual(p.actual_arrival_time, hub, p.arr_slot[hub])),
                "departure": _fmt(_actual(p.actual_departure_time, hub, p.dep_slot[hub])),
                "available": _fmt(_actual(p.actual_available_time, hub,
                                            p.avail_slot.get(hub, p.arr_slot[hub]))),
                "actual_load_start_time": _fmt(_actual(
                    p.actual_load_start_time, hub, p.load_slot.get(hub, p.dep_slot[hub]))),
                "actual_arrival_time": _fmt(_actual(p.actual_arrival_time, hub, p.arr_slot[hub])),
                "actual_departure_time": _fmt(_actual(p.actual_departure_time, hub, p.dep_slot[hub])),
                "actual_available_time": _fmt(_actual(
                    p.actual_available_time, hub, p.avail_slot.get(hub, p.arr_slot[hub]))),
                "model_load_start_slot": p.load_slot.get(hub, p.dep_slot[hub]),
                "model_arrival_slot": p.arr_slot[hub],
                "model_departure_slot": p.dep_slot[hub],
                "model_available_slot": p.avail_slot.get(hub, p.arr_slot[hub]),
                "load_teu": stop_load[(tid, hub)],
                "unload_teu": stop_unload[(tid, hub)]})

    write_csv(outdir / "KORAIL_TRAIN_PLAN.csv", train_rows)
    write_csv(outdir / "FINAL_TRAIN_OPERATION_SUMMARY.csv", [{
        "train_id": r["train_id"], "candidate_source": r["candidate_source"],
        "route": r["route"], "actual_origin_departure": r["actual_origin_departure"],
        "actual_final_arrival": r["actual_final_arrival"], "formation": r["formation"],
        "wagons": r["wagons"], "capacity_teu": r["capacity_teu"],
        "assigned_teu": r["total_assigned_teu"],
        "load_factor": r["distance_weighted_load_factor"],
        "participating_carrier_count": r["participating_carrier_count"],
        "20ft_boxes": r["20ft_boxes"], "40ft_boxes": r["40ft_boxes"],
        "total_container_boxes": r["total_container_boxes"]} for r in train_rows])
    write_csv(outdir / "SEGMENT_LOAD.csv", segment_rows)
    write_csv(outdir / "STOP_WORK_PLAN.csv", stop_rows)

    # ---- KORAIL 관점: 열차별 선사 배분 --------------------------------------
    alloc = defaultdict(int)
    for a, q in positive:
        alloc[(a.train_id, a.carrier, a.origin, a.destination, a.size)] += q
    alloc_rows = [{"train_id": t, "carrier_id": c, "origin": o, "destination": d,
                   "container_size": k, "boxes": q, "teu": q * TEU[k]}
                  for (t, c, o, d, k), q in sorted(alloc.items())]
    write_csv(outdir / "CARRIER_ALLOCATION.csv", alloc_rows)

    # ---- 선사 관점: Recommendation detail ----------------------------------
    detail_rows = []
    for i, (a, q) in enumerate(sorted(positive, key=lambda z: (z[0].carrier, z[0].need_id,
                                                               z[0].origin, z[0].train_id)), 1):
        nd = meta["need_by_id"][a.need_id]
        p = meta["trains"][a.train_id]
        detail_rows.append({
            "detail_id": f"DETAIL{i:04d}", "need_id": a.need_id, "carrier_id": a.carrier,
            "origin_hub": a.origin, "origin_name": HUB_NAME[a.origin],
            "destination_hub": a.destination, "destination_name": HUB_NAME[a.destination],
            "container_size": a.size, "quantity_boxes": q, "quantity_teu": q * TEU[a.size],
            "train_id": a.train_id,
            "load_start_time": _fmt(_actual(p.actual_load_start_time, a.origin, a.dep_slot)),
            "departure_time": _fmt(_actual(
                p.actual_departure_time, a.origin, p.dep_slot[a.origin])),
            "arrival_time": _fmt(_actual(
                p.actual_arrival_time, a.destination, p.arr_slot[a.destination])),
            "available_time": _fmt(_actual(
                p.actual_available_time, a.destination, a.arr_slot)),
            "model_load_start_slot": a.dep_slot,
            "model_departure_slot": p.dep_slot[a.origin],
            "model_arrival_slot": p.arr_slot[a.destination],
            "model_available_slot": a.arr_slot,
            "service_due_time": nd["due_time"],
            "earliness_hours": int(max(nd["due_slot"] - a.arr_slot, 0)),
            "physical_distance_km": round(p.path_km(a.segments), 1),
            "tariff_distance_km": OD_DISTANCE[(a.origin, a.destination)],
            "estimated_rail_charge_krw": round(q * a.fare, 2)})
    write_csv(outdir / "CARRIER_RECOMMENDATION_DETAIL.csv", detail_rows)

    # ---- 선사 관점: Recommendation (선사/OD/규격/열차 단위 집계) -------------
    groups = defaultdict(list)
    for r in detail_rows:
        groups[(r["carrier_id"], r["origin_hub"], r["destination_hub"],
                r["container_size"], r["train_id"])].append(r)
    rec_rows = []
    for i, (key, rs) in enumerate(sorted(groups.items()), 1):
        c, o, d, k, tid = key
        rec_rows.append({
            "recommendation_id": f"REC{i:04d}", "carrier_id": c,
            "container_size": k,
            "quantity_boxes": sum(r["quantity_boxes"] for r in rs),
            "quantity_teu": sum(r["quantity_teu"] for r in rs),
            "origin_hub": o, "origin_name": HUB_NAME[o],
            "destination_hub": d, "destination_name": HUB_NAME[d],
            "train_id": tid,
            "departure_time": rs[0]["departure_time"],
            "arrival_time": rs[0]["arrival_time"],
            "available_time": rs[0]["available_time"],
            # v7.1-patch (지시서 §14): 여러 due 가 한 recommendation 에 묶일 수 있으므로
            # 단일 due 로 표기하지 않고 건수와 범위를 함께 제공한다.
            "need_count": len(rs),
            "service_due_time_earliest": min(r["service_due_time"] for r in rs),
            "service_due_time_latest": max(r["service_due_time"] for r in rs),
            "physical_distance_km": rs[0]["physical_distance_km"],
            "tariff_distance_km": rs[0]["tariff_distance_km"],
            "estimated_rail_charge_krw": round(sum(r["estimated_rail_charge_krw"] for r in rs), 2),
            # 공동운송 여부는 집계정보로만 노출한다. 타 선사 배분은 비공개.
            "participating_carrier_count": len(train_carriers[tid]),
            "train_load_factor": train_lf.get(tid, 0.0),
            "max_earliness_hours": max(r["earliness_hours"] for r in rs),
            "need_ids": "|".join(sorted({r["need_id"] for r in rs}))})
    write_csv(outdir / "CARRIER_RECOMMENDATIONS.csv", rec_rows)
    for c in sorted({r["carrier_id"] for r in rec_rows}):
        write_csv(outdir / f"CARRIER_RECOMMENDATIONS_{c}.csv",
                  [r for r in rec_rows if r["carrier_id"] == c])

    # ---- 챗봇용 read-only 설명 근거 (계산된 값만 기록) -----------------------
    served_by_need = defaultdict(int)
    for a, q in positive:
        served_by_need[a.need_id] += q
    # 같은 (carrier, origin, size) 에서 load 시각 순으로 누적 반출량을 계산해 둔다.
    cum_out = defaultdict(int)
    out_seq = defaultdict(list)
    for a, q in positive:
        out_seq[(a.carrier, a.origin, a.size)].append((a.dep_slot, a.train_id, q))
    for key in out_seq:
        out_seq[key].sort()

    ctx_rows = []
    for r in rec_rows:
        nids = r["need_ids"].split("|")
        linked = [meta["need_by_id"][n] for n in nids if n in meta["need_by_id"]]
        p = meta["trains"][r["train_id"]]
        load_slot = p.load_slot.get(r["origin_hub"], p.dep_slot.get(r["origin_hub"], 0))
        key = (r["carrier_id"], r["origin_hub"], r["container_size"])
        cap = int(meta["source_cap"].get((*key, load_slot), 0))
        used_through = sum(q for sl, _, q in out_seq.get(key, []) if sl <= load_slot)
        ctx_rows.append({
            "recommendation_id": r["recommendation_id"], "carrier_id": r["carrier_id"],
            "destination_hub": r["destination_hub"], "container_size": r["container_size"],
            # v7.1-patch (지시서 §13-A): "그 시점 목적지 예상부족" 이라고 단정하지 않는다.
            # 이 recommendation 에 연결된 Service Need 의 합계라는 의미로 이름을 바꿨다.
            # 실제 post-rail 재고부족은 CARRIER_INVENTORY_TIMELINE.csv 에서 조회한다.
            "linked_service_need_teu": sum(n["teu"] for n in linked),
            "linked_need_count": len(linked),
            "linked_need_due_min": min((n["due_time"] for n in linked), default=""),
            "linked_need_due_max": max((n["due_time"] for n in linked), default=""),
            "origin_hub": r["origin_hub"],
            # v7.1-patch (지시서 §13-B): 누적 방출가능량과 이미 배정된 양을 분리한다.
            "source_release_capacity_cumulative_boxes": cap,
            "assigned_outbound_cumulative_boxes_through_load": int(used_through),
            "source_release_remaining_after_assignment_boxes": int(cap - used_through),
            "recommended_boxes": r["quantity_boxes"],
            "recommended_teu": r["quantity_teu"],
            "train_id": r["train_id"],
            "train_load_factor": r["train_load_factor"],
            "participating_carrier_count": r["participating_carrier_count"],
            "service_due_time_earliest": r["service_due_time_earliest"],
            "service_due_time_latest": r["service_due_time_latest"],
            "arrival_time": r["arrival_time"],
            "available_time": r["available_time"],
            "earliness_hours": r["max_earliness_hours"],
            "physical_distance_km": r["physical_distance_km"],
            "tariff_distance_km": r["tariff_distance_km"],
            "estimated_rail_charge_krw": r["estimated_rail_charge_krw"]})
    write_csv(outdir / "RECOMMENDATION_EXPLANATION_CONTEXT.csv", ctx_rows)
    # v7.1-patch (지시서 §23): 선사별 격리 context. 타 선사 정보가 들어가면 안 된다.
    for c in sorted({r["carrier_id"] for r in ctx_rows}):
        write_csv(outdir / f"RECOMMENDATION_EXPLANATION_CONTEXT_{c}.csv",
                  [r for r in ctx_rows if r["carrier_id"] == c])

    # ---- Service Need 결과 --------------------------------------------------
    need_rows = []
    unserved_rows = []
    for nd in meta["needs"]:
        nid = nd["need_id"]
        served = served_by_need[nid]
        un = int(round(x[meta["U"][nid]]))
        need_rows.append({**nd, "rail_served_boxes": served,
                          "rail_served_teu": served * TEU[nd["container_size"]],
                          "rail_unserved_boxes": un,
                          "rail_unserved_teu": un * TEU[nd["container_size"]]})
        if un > 0:
            unserved_rows.append({**nd, "rail_unserved_boxes": un,
                                  "rail_unserved_teu": un * TEU[nd["container_size"]],
                                  # v7.1-patch: 수학적으로 증명할 수 없는 단일 원인을 단정하지 않는다.
                                  # 아래 pre-check 로 확인 가능한 범위만 분류한다.
                                  "reason": unserved_reason.get(
                                      nid, "UNSERVED_AFTER_JOINT_OPTIMIZATION"),
                                  "reason_is_proven_cause": False})
    write_csv(outdir / "SERVICE_NEED_RESULT.csv", need_rows)
    write_csv(outdir / "RAIL_UNSERVED.csv", unserved_rows)

    # ---- 선사별 서비스 성과 (지시서 §16) -----------------------------------
    per = defaultdict(lambda: {"need": 0, "served": 0, "recs": 0, "charge": 0.0,
                               "trains": set()})
    for nd in meta["needs"]:
        per[nd["carrier_id"]]["need"] += nd["teu"]
    for r in need_rows:
        per[r["carrier_id"]]["served"] += r["rail_served_teu"]
    for r in rec_rows:
        e = per[r["carrier_id"]]
        e["recs"] += 1
        e["charge"] += r["estimated_rail_charge_krw"]
        e["trains"].add(r["train_id"])
    svc_rows = []
    for c in sorted(per):
        e = per[c]
        svc_rows.append({
            "carrier_id": c, "service_need_teu": e["need"],
            "rail_served_teu": e["served"],
            "rail_unserved_teu": max(e["need"] - e["served"], 0),
            "rail_coverage": round(e["served"] / e["need"], 4) if e["need"] else 1.0,
            "recommendation_count": e["recs"],
            "assigned_train_count": len(e["trains"]),
            "estimated_tariff_based_rail_charge_krw": round(e["charge"], 2)})
    write_csv(outdir / "CARRIER_SERVICE_SUMMARY.csv", svc_rows)
    covs = [r["rail_coverage"] for r in svc_rows]
    fairness = {
        "max_carrier_coverage": round(max(covs), 4) if covs else 0.0,
        "min_carrier_coverage": round(min(covs), 4) if covs else 0.0,
        "coverage_stdev": round(
            (sum((x - sum(covs) / len(covs)) ** 2 for x in covs) / len(covs)) ** 0.5, 4)
        if covs else 0.0}

    # ---- 최적화 후 재고 timeline (지시서 §12) -------------------------------
    inv_rows, impact_rows = ([], [])
    if service is not None:
        inv_rows, impact_rows = build_inventory_timeline(service, positive, meta)
        write_csv(outdir / "CARRIER_INVENTORY_TIMELINE.csv", inv_rows)
        write_csv(outdir / "INVENTORY_IMPACT_SUMMARY.csv", impact_rows)

    # ---- 감사 --------------------------------------------------------------
    write_csv(outdir / "SOLVER_AUDIT.csv", solver_audit or [])
    write_csv(outdir / "OPERATIONAL_CONSTRAINT_AUDIT.csv", meta.get("operational_audit", []))
    write_csv(outdir / "INVENTORY_POLICY_AUDIT.csv", meta.get("policy_audit", []))
    (outdir / "ACTIVE_POLICY.json").write_text(
        json.dumps({"scenario": scenario, "active_policies": meta.get("active_policies", [])},
                   ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- SUMMARY -----------------------------------------------------------
    requested = sum(n["teu"] for n in meta["needs"])
    served = sum(r["rail_served_teu"] for r in need_rows)
    teu_km = sum(q * TEU[a.size] * meta["trains"][a.train_id].path_km(a.segments)
                 for a, q in positive)
    lfs = [r["distance_weighted_load_factor"] for r in train_rows]
    pcs = [r["participating_carrier_count"] for r in train_rows]
    rec_teu = sum(r["quantity_teu"] for r in rec_rows)
    alloc_teu = sum(r["teu"] for r in alloc_rows)
    final = {**summary, "scenario": scenario,
             "service_need_teu": requested, "service_need_count": len(meta["needs"]),
             "rail_served_teu": served, "rail_unserved_teu": max(requested - served, 0),
             "rail_coverage": round(served / requested, 4) if requested else 1.0,
             "selected_train_count": len(train_rows),
             "recommendation_count": len(rec_rows),
             "teu_km": round(teu_km, 1),
             "avg_distance_weighted_load_factor": round(sum(lfs) / len(lfs), 4) if lfs else 0.0,
             "avg_carriers_per_train": round(sum(pcs) / len(pcs), 3) if pcs else 0.0,
             "estimated_rail_charge_krw": round(
                 sum(r["estimated_rail_charge_krw"] for r in rec_rows), 2),
             "20ft_boxes": sum(r["quantity_boxes"] for r in detail_rows
                                if r["container_size"] == "20FT"),
             "40ft_boxes": sum(r["quantity_boxes"] for r in detail_rows
                                if r["container_size"] == "40FT"),
             "total_container_boxes": sum(r["quantity_boxes"] for r in detail_rows),
             # 완료조건: 선사 관점 합계 == KORAIL 관점 합계 == 실제 서비스 물량
             "carrier_recommendation_teu": rec_teu,
             "korail_allocation_teu": alloc_teu,
             "carrier_korail_view_consistent": bool(rec_teu == alloc_teu == served),
             "operational_constraints_active": bool(meta.get("operations_active", False)),
             "active_policy_count": len(meta.get("active_policies", [])),
             "carrier_subset": meta.get("carrier_subset"),
             "default_max_earliness_hours": meta.get("default_max_earliness"),
             "min_load_factor": meta.get("min_load_factor"),
             "return_wagon_movement_included": False,
             # v7.1-patch (지시서 §11): 하드코딩하지 않고 실제 선택된 후보에서 유도한다.
             "candidate_input_sources": _candidate_sources(meta.get("trains", {}).values()),
             "selected_train_sources": _candidate_sources(selected.values()),
             "candidate_timetable_source": _candidate_source_label(meta, selected.values()),
             "carrier_data_source": meta.get("carrier_data_source",
                                             "SYNTHETIC_CARRIER_LEVEL_DATA"),
             # v7.1-patch (지시서 §22): 공표 운임표 기반 추정액이며 실제 수익이 아니다.
             "revenue_definition": "TARIFF_BASED_ESTIMATED_RAIL_CHARGE_NOT_PROFIT",
             "deprecated_aliases": {
                 "expected_korail_revenue_krw": "estimated_rail_charge_krw",
                 "estimated_tariff_based_rail_revenue_krw": "estimated_rail_charge_krw"},
             "carrier_coverage_fairness": fairness,
             "post_rail_inventory_timeline_rows": len(inv_rows),
             "post_rail_inventory_min": (min((r["post_rail_inventory"] for r in inv_rows),
                                             default=None) if inv_rows else None)}
    (outdir / "SUMMARY.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    return final


# ===========================================================================
# One-shot run
# ===========================================================================
def run(hourly_path: Path, initial_path: Path, root: Path, min_load_factor=0.5,
        policies_path: Optional[Path] = None, operations_path: Optional[Path] = None,
        scenario="AXIS_INTEGRATED", time_limit=900, mip_gap=0.001, verbose=False,
        max_earliness=72.0, carrier_subset=None, params_xlsx: Optional[Path] = None,
        origin_loading_h=None, intermediate_handling_h=None, destination_unloading_h=None,
        candidates_dir: Optional[Path] = None, strict_lexicographic=False,
        validate_inputs=True):
    """
    Carrier Input Data -> Service Need -> KORAIL Candidate Trains
    -> Joint Multi-Carrier MILP -> single optimal solution
    -> Carrier Recommendation + KORAIL Integrated Operation Plan
    """
    root.mkdir(parents=True, exist_ok=True)
    configure_params(params_xlsx, origin_loading_h, intermediate_handling_h,
                     destination_unloading_h)
    # v7.1-patch (지시서 §7): 선사 제출 데이터 사전검증. 실패 시 structured error.
    if validate_inputs:
        validate_carrier_inputs(hourly_path, initial_path)
    hourly = read_hourly(hourly_path)
    initial = read_initial(initial_path)
    timestamps = sorted({r["timestamp"] for r in hourly})

    # KORAIL 운행가능 열차 후보.
    # v7.1-patch (지시서 §2): 외부 --candidates 가 주어지면 **절대 덮어쓰지 않는다.**
    # 잘못된 후보는 자동보정·synthetic 재생성으로 숨기지 않고 검증 오류로 반환한다.
    if candidates_dir is not None:
        input_dir = Path(candidates_dir)
        validate_candidate_inputs(input_dir, timestamps)
    else:
        input_dir = root / "MODEL_INPUTS"
        if not _candidate_inputs_match(input_dir, timestamps[0], len(timestamps)):
            generate_candidate_inputs(timestamps[0], len(timestamps), input_dir)

    policies = read_json(policies_path, {"inventory_policies": []})
    # v7.1-patch (지시서 §24.3): 실행 중 생성물은 후보 디렉터리에 쓰지 않는다.
    # 외부 KORAIL candidate 폴더를 절대 오염시키지 않기 위함이다.
    run_inputs = root / "_RUN_MODEL_INPUTS"
    service = generate_service_needs(hourly, initial, policies, run_inputs)
    trains = read_candidate_inputs(input_dir)
    operations = read_json(operations_path, {"path_slot_capacity": [], "resource_capacity": []})

    meta, lo, up, integ = build_milp(service, trains, min_load_factor, operations,
                                     max_earliness, carrier_subset)
    if not meta["assignments"]:
        raise diagnose_infeasibility(service, meta, max_earliness, min_load_factor)
    try:
        result, summary, solver_audit = solve_lex(meta, lo, up, integ, time_limit,
                                                  mip_gap, verbose,
                                                  strict_lexicographic=strict_lexicographic)
    except ModelInfeasible as exc:
        raise AxisRequestError(
            "MODEL_INFEASIBLE",
            "현재 조건 조합에서는 실행 가능한 철도운영계획이 존재하지 않습니다.",
            detail={"stage": exc.stage, "solver_message": exc.solver_message[:200],
                    "min_load_factor": min_load_factor,
                    "max_earliness_hours": max_earliness},
            alternatives=[{"action": "LOWER_MIN_CONSOLIDATION_LEVEL", "current": min_load_factor},
                          {"action": "RELAX_MAX_EARLINESS", "current": max_earliness}]) from exc
    except RuntimeError as exc:
        raise AxisRequestError(
            "SOLVER_LIMIT_REACHED",
            "제한 시간 안에 최적해를 증명하지 못했습니다. 결과를 최적해로 제시할 수 없습니다.",
            detail={"solver_message": str(exc)[:300], "time_limit_sec": time_limit},
            alternatives=[{"action": "INCREASE_TIME_LIMIT", "current": time_limit},
                          {"action": "TIGHTEN_MAX_EARLINESS", "current": max_earliness}]) from exc

    summary["origin_loading_h"] = ORIGIN_LOADING_H
    summary["intermediate_handling_h"] = INTERMEDIATE_HANDLING_H
    summary["destination_unloading_h"] = DESTINATION_UNLOADING_H
    out = root / scenario
    unserved_reason = diagnose_unserved_reasons(
        service, trains, meta["needs"], min_load_factor, max_earliness, meta["assignments"])
    res = extract(meta, result, summary, out, scenario, solver_audit,
                  service=service, unserved_reason=unserved_reason)
    write_csv(out / "RAIL_PARAMETER_PROVENANCE.csv", PARAMS.provenance)
    write_csv(out / "DISTANCE_VALIDATION.csv",
              [c for c in PARAMS.validation if c["check"] != "_deltas"])
    write_csv(out / "DISTANCE_PHYSICAL_VS_TARIFF.csv",
              [c for c in PARAMS.validation if c["check"] == "_deltas"][0]["detail"])
    return res


def _main():
    ap = argparse.ArgumentParser(
        description="AXIS v7.1 — Joint Multi-Carrier empty-container rail optimization (one-shot)")
    ap.add_argument("--hourly", required=True, help="carrier-submitted hourly plan CSV")
    ap.add_argument("--initial", required=True, help="carrier initial inventory CSV")
    ap.add_argument("--root", required=True)
    ap.add_argument("--scenario", default="AXIS_INTEGRATED")
    ap.add_argument("--min-load-factor", type=float, default=0.5)
    ap.add_argument("--max-earliness", type=float, default=72.0)
    ap.add_argument("--time-limit", type=float, default=900)
    ap.add_argument("--mip-gap", type=float, default=0.001)
    ap.add_argument("--policies", default=None)
    ap.add_argument("--operations", default=None)
    ap.add_argument("--params", default=None)
    ap.add_argument("--candidates", default=None,
                    help="KORAIL feasible train candidate directory (defaults to root/MODEL_INPUTS)")
    ap.add_argument("--carrier", action="append", default=None,
                    help="research baseline only: restrict to these carriers")
    ap.add_argument("--origin-loading-h", type=float, default=None)
    ap.add_argument("--intermediate-handling-h", type=float, default=None)
    ap.add_argument("--destination-unloading-h", type=float, default=None)
    ap.add_argument("--strict-lexicographic", action="store_true",
                    help="every lexicographic stage with mip_rel_gap=0 (canonical run)")
    ap.add_argument("--no-input-validation", action="store_true",
                    help="skip carrier input pre-validation (not recommended)")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    summ = run(Path(a.hourly), Path(a.initial), Path(a.root), a.min_load_factor,
               Path(a.policies) if a.policies else None,
               Path(a.operations) if a.operations else None,
               a.scenario, a.time_limit, a.mip_gap, a.verbose,
               a.max_earliness, set(a.carrier) if a.carrier else None,
               Path(a.params) if a.params else None,
               a.origin_loading_h, a.intermediate_handling_h, a.destination_unloading_h,
               Path(a.candidates) if a.candidates else None,
               a.strict_lexicographic, not a.no_input_validation)
    print(json.dumps(summ, ensure_ascii=False, indent=2))


def main():
    try:
        _main()
    except (AxisRequestError, PolicyValidationError, InputValidationError) as exc:
        print(json.dumps(exc.as_dict(), ensure_ascii=False, indent=2))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
