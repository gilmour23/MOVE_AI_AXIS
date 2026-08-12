from __future__ import annotations

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
    from axis_params_v7 import load_rail_params
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
    candidate_rows=[]; stop_rows=[]; segment_rows=[]; formation_rows=[]
    cid=0
    for path in unique_service_paths():
        segs = path_segments(path)
        family = service_family(path)
        dist = sum(SEGMENT_DISTANCE[s] for s in segs)
        for day in range(math.ceil(horizon_h/24)):
            for hr in DEPARTURE_HOURS:
                origin_slot = day*24+hr
                if origin_slot >= horizon_h: continue
                elapsed = 0.0
                # v7 (review finding #9): 출발역 상차시간을 0 으로 두지 않는다.
                # load_slot = 상차 개시 시각. 공컨은 이 시점에 거점에 있어야 한다.
                load_open = origin_slot - math.ceil(ORIGIN_LOADING_H - 1e-10)
                if load_open < 0:
                    continue
                arr_slot = {path[0]: origin_slot}
                dep_slot = {path[0]: origin_slot}
                load_slot = {path[0]: load_open}
                for a,b in segs:
                    elapsed += SEGMENT_DISTANCE[(a,b)]/AVG_SPEED_KMPH
                    arr_slot[b] = origin_slot + math.ceil(elapsed - 1e-10)
                    if b != path[-1]:
                        # 중간역: 하화 + 상차 작업시간을 확보한 뒤 출발
                        load_slot[b] = arr_slot[b]
                        elapsed += INTERMEDIATE_HANDLING_H
                        dep_slot[b] = origin_slot + math.ceil(elapsed - 1e-10)
                    else:
                        dep_slot[b] = arr_slot[b]
                        load_slot[b] = arr_slot[b]
                # avail_slot = 도착 후 하화까지 끝나 화주가 실제로 쓸 수 있는 시각
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
                    "origin_departure_time":(start+timedelta(hours=origin_slot)).strftime("%Y-%m-%d %H:%M"),
                    "destination_arrival_time":(start+timedelta(hours=arr_slot[path[-1]])).strftime("%Y-%m-%d %H:%M"),
                    "service_distance_km":round(dist,1),
                    "timetable_basis":"PROTOTYPE_6H_SYNTHETIC",
                })
                for seqno, hub in enumerate(path,1):
                    stop_rows.append({
                        "train_id":train_id,"stop_sequence":seqno,"hub_code":hub,"hub_name":HUB_NAME[hub],
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
                # 50-wagon is kept only as a Gyeongbu scenario option.
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


def diagnose_commitment_conflict(meta, lo, up, integ, time_limit=120):
    """
    협의 결과가 infeasible 할 때, 어떤 Carrier Commitment 를 동시에 만족시킬 수 없는지 찾는다.

    배경: 선사가 수락한 물량은 하한(lb)으로 들어간다. 그런데 같은 라운드에서 다른 선사가
    거절·수정하면 그 물량을 싣던 열차가 최소 consolidation 요건을 못 채워 운행할 수 없게 되고,
    결과적으로 수락 물량을 실을 방법이 사라져 모델 전체가 infeasible 이 된다.

    이는 실제 서비스 상황이므로 죽는 대신 "확정할 수 없는 commitment" 를 보고해야 한다.
    여기서는 commitment 하한을 완화한 모델을 다시 풀어 부족분을 계산한다.
    """
    accepted=meta.get("accepted_by_need",{})
    if not accepted:
        return None
    by_need=defaultdict(list)
    for a in meta["assignments"]: by_need[a.need_id].append(a)

    n=len(lo)
    rows=SparseRows(n)
    A=meta["A"].tocsr(); lb=np.array(meta["lb"]); ub=np.array(meta["ub"])
    # commitment 하한만 제거한 행렬을 다시 만든다.
    keep=[]
    acc_rowsets={}
    for nid,q in accepted.items():
        if q>0 and by_need.get(nid):
            acc_rowsets[frozenset(a.var for a in by_need[nid])]=q
    for r in range(A.shape[0]):
        cols=frozenset(A.indices[A.indptr[r]:A.indptr[r+1]].tolist())
        if cols in acc_rowsets and lb[r]==acc_rowsets[cols] and not np.isfinite(ub[r]):
            continue   # commitment lower bound row
        keep.append(r)
    A2=A[keep]; lb2=lb[keep]; ub2=ub[keep]

    c=np.zeros(n)
    for nid,q in accepted.items():
        for a in by_need.get(nid,[]):
            c[a.var]=-float(TEU[a.size])      # 수락 물량을 최대한 실어본다
    res=milp(c,integrality=integ,bounds=Bounds(lo,up),
             constraints=LinearConstraint(A2,lb2,ub2),
             options={"time_limit":time_limit,"mip_rel_gap":0.01})
    if res.x is None:
        return {"diagnosis":"UNAVAILABLE","reason":res.message[:200]}
    shortfall=[]
    for nid,q in sorted(accepted.items()):
        got=int(round(sum(res.x[a.var] for a in by_need.get(nid,[]))))
        if got<q:
            nd=meta["need_by_id"][nid]
            shortfall.append({"need_id":nid,"carrier_id":nd["carrier_id"],
                              "destination":nd["destination"],
                              "container_size":nd["container_size"],
                              "committed_boxes":q,"deliverable_boxes":got,
                              "unconfirmable_boxes":q-got})
    total=sum(s["unconfirmable_boxes"]*TEU[s["container_size"]] for s in shortfall)
    return {"diagnosis":"COMMITMENT_SHORTFALL",
            "unconfirmable_commitment_teu":total,
            "affected_needs":len(shortfall),
            "examples":shortfall[:10]}


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
    "MIN_INVENTORY_AT_TIME": {"target_time"},
    "MIN_INVENTORY_RANGE":   {"start_time","end_time"},
    "MAX_INVENTORY":         {"start_time","end_time"},
    "BLOCK_OUTBOUND":        {"start_time","end_time"},
}
POLICY_REQUIRED = {
    "MIN_INVENTORY_AT_TIME": {"carrier_id","rule_type","hub_code","container_size","value","target_time"},
    "MIN_INVENTORY_RANGE":   {"carrier_id","rule_type","hub_code","container_size","value"},
    "MAX_INVENTORY":         {"carrier_id","rule_type","hub_code","container_size","value"},
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
            elif rt=="BLOCK_OUTBOUND":
                key=(c,h,k)
                prev=outbound.get(key)
                outbound[key]=(min(prev[0],v),s0,s1) if prev else (v,s0,s1)
            norm.update(start_time=st.strftime("%Y-%m-%d %H:%M"),
                        end_time=en.strftime("%Y-%m-%d %H:%M"),target_time="")
        active.append(norm)

    return {"lb":lb,"ub":ub,"outbound_cap":outbound,"active":active}


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
    # Chatbot quantity adjustments can add an explicit extra service need without inventing safety stock.
    # Example: proposal was 8 boxes and carrier asks for 12 -> chatbot emits additional_needs quantity=4.
    for extra in policies_obj.get("additional_needs", []):
        ts=datetime.strptime(extra["due_time"], "%Y-%m-%d %H:%M")
        if ts not in tmap:
            raise ValueError(f"additional need due_time outside horizon: {extra['due_time']}")
        q=int(extra["quantity"])
        if q<=0: continue
        nid += 1
        k=extra["container_size"]
        needs.append({
            "need_id":f"NEED{nid:04d}","carrier_id":extra["carrier_id"],"destination":extra["destination"],
            "destination_name":HUB_NAME[extra["destination"]],"container_size":k,"quantity":q,"teu":q*TEU[k],
            "due_time":ts.strftime("%Y-%m-%d %H:%M"),"due_slot":tmap[ts],"priority":int(extra.get("priority",1)),
            "need_reason":"CHATBOT_ADDITIONAL_QUANTITY","inventory_lb":0,
        })

    if outdir:
        write_csv(outdir/"SERVICE_NEED.csv", needs)
        write_csv(outdir/"BASELINE_AND_SOURCE_CAPACITY.csv", baseline_rows)
    return {
        "timestamps":timestamps,"tmap":tmap,"carriers":carriers,"hubs":hubs,"sizes":sizes,
        "demand":demand,"supply":supply,"lb":lb,"needs":needs,"source_cap":source_cap,
        "baseline_rows":baseline_rows,"baseline_stock":baseline_stock,
        "inventory_ub":inv_ub,"outbound_cap":outbound_cap,"active_policies":pol["active"],
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


def _candidate_inputs_match(indir: Path, start: datetime, horizon_h: int) -> bool:
    """True only if an existing candidate timetable was generated for this exact week."""
    path=indir/"TRAIN_CANDIDATE.csv"
    if not path.exists(): return False
    try:
        with path.open(encoding="utf-8-sig",newline="") as f:
            deps=[datetime.strptime(r["origin_departure_time"],"%Y-%m-%d %H:%M")
                  for r in csv.DictReader(f)]
    except (KeyError,ValueError,OSError):
        return False
    if not deps: return False
    end=start+timedelta(hours=horizon_h-1)
    return min(deps)>=start and max(deps)<=end and min(deps)==start


def read_candidate_inputs(indir: Path):
    cand={}
    with (indir/"TRAIN_CANDIDATE.csv").open(encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f):
            cand[r["train_id"]]={
                "family":r["service_family"],"path":tuple(r["path"].split("|")),
                "origin_departure":datetime.strptime(r["origin_departure_time"],"%Y-%m-%d %H:%M"),
                "distance":float(r["service_distance_km"]),
            }
    arr=defaultdict(dict); dep=defaultdict(dict); ldg=defaultdict(dict); avl=defaultdict(dict)
    with (indir/"TRAIN_STOP_TIME.csv").open(encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f):
            arr[r["train_id"]][r["hub_code"]]=int(r["arrival_slot"])
            dep[r["train_id"]][r["hub_code"]]=int(r["departure_slot"])
            ldg[r["train_id"]][r["hub_code"]]=int(r["load_start_slot"])
            avl[r["train_id"]][r["hub_code"]]=int(r["available_slot"])
    segs=defaultdict(list)
    with (indir/"TRAIN_SEGMENT.csv").open(encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f):
            segs[r["train_id"]].append((int(r["segment_sequence"]),(r["from_hub"],r["to_hub"])))
    forms=defaultdict(list)
    with (indir/"TRAIN_FORMATION_OPTION.csv").open(encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f): forms[r["train_id"]].append(r["formation_id"])
    trains=[]
    for tid,c in cand.items():
        trains.append(Train(tid,c["family"],c["path"],c["origin_departure"],c["distance"],arr[tid],dep[tid],
                            tuple(s for _,s in sorted(segs[tid])),tuple(forms[tid]),
                            ldg[tid],avl[tid]))
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


def load_negotiation(path: Optional[Path]):
    obj=read_json(path,{"negotiation_round":1,"proposal_actions":[]})
    return obj, obj.get("proposal_actions",[]), int(obj.get("negotiation_round",1))


def _proposal_allocations(pr):
    allocs=[]
    if pr.get("need_allocation"):
        for token in pr["need_allocation"].split("|"):
            if not token: continue
            nid,qtxt=token.split(":",1); allocs.append((nid,int(qtxt)))
    elif pr.get("need_id"):
        allocs=[(pr["need_id"],int(pr["quantity"]))]
    return allocs


def _action_constraints(ac):
    """Normalize legacy single-field actions and v6.1 MODIFY_SERVICE into one constraint dict."""
    action=ac.get("action")
    if action=="MODIFY_SERVICE":
        c=dict(ac.get("constraints") or {})
        c["commit"]=bool(ac.get("commit",False))
        return c
    c={"commit":bool(ac.get("commit",False))}
    if action=="CHANGE_QUANTITY": c["quantity"]=int(ac["quantity"])
    elif action=="CHANGE_LATEST_ARRIVAL": c["latest_arrival"]=ac["latest_arrival"]
    elif action=="SET_EARLIEST_ARRIVAL": c["earliest_arrival"]=ac["earliest_arrival"]
    elif action=="SET_MAX_EARLINESS": c["max_earliness_hours"]=float(ac["max_earliness_hours"])
    elif action=="BLOCK_ORIGIN": c["blocked_origins"]=[ac["origin"]]
    return c


def _parse_time_in_horizon(txt: str, service, field: str):
    ts=datetime.strptime(txt,"%Y-%m-%d %H:%M")
    if ts not in service["tmap"]:
        raise ValueError(f"{field} outside horizon: {txt}")
    return ts, service["tmap"][ts]


def build_milp(service, trains, min_load_factor=0.5, proposal_reference: Optional[Path]=None, actions_path: Optional[Path]=None,
               run_mode: str="PROPOSAL", operations_obj: Optional[dict]=None,
               default_max_earliness: Optional[float]=None, carrier_subset: Optional[set]=None):
    run_mode=run_mode.upper()
    if run_mode not in {"PROPOSAL","NEGOTIATION","FINAL"}:
        raise ValueError(f"unsupported run_mode: {run_mode}")
    operations_obj=operations_obj or {}

    # Reference proposals from the previous negotiation round.
    proposal_ref={}
    if proposal_reference and proposal_reference.exists():
        with proposal_reference.open(encoding="utf-8-sig",newline="") as f:
            for r in csv.DictReader(f): proposal_ref[r["proposal_id"]]=r
    negotiation_obj,actions,negotiation_round=load_negotiation(actions_path)

    # v6.1 supports one compound MODIFY_SERVICE object per proposal. Legacy multiple actions are also merged sequentially.
    actions_by_pid=defaultdict(list)
    for ac in actions:
        pid=ac.get("proposal_id")
        if pid: actions_by_pid[pid].append(ac)

    needs=[dict(r) for r in service["needs"]]
    # Scenario B (Carrier Separate) reuses the identical need set but optimizes one
    # carrier at a time, so trains are never shared between carriers.
    if carrier_subset is not None:
        needs=[r for r in needs if r["carrier_id"] in carrier_subset]
    source_cap=service["source_cap"]; timestamps=service["timestamps"]
    need_by_id={r["need_id"]:r for r in needs}

    # Effective service conditions MUST be applied before candidate assignments are generated.
    # This is the v6.1 fix that allows a relaxed latest-arrival to expand the train search space.
    effective_due={nid:int(nd["due_slot"]) for nid,nd in need_by_id.items()}
    effective_earliest={nid:0 for nid in need_by_id}
    max_earliness={nid:None for nid in need_by_id}
    blocked_origins=defaultdict(set)

    accepted_by_need=defaultdict(int)
    declined_by_need=defaultdict(int)
    forced_service_by_need={}
    exact_requests=[]
    reject_option_requests=[]
    action_audit=[]
    proposal_states=[]
    action_extra_need={}

    def merged_constraints(pid):
        merged={"blocked_origins":[]}
        commit=False
        for ac in actions_by_pid.get(pid,[]):
            c=_action_constraints(ac)
            commit=commit or bool(c.pop("commit",False))
            for k,v in c.items():
                if k=="blocked_origins":
                    merged.setdefault(k,[]).extend(v or [])
                else:
                    merged[k]=v
        merged["blocked_origins"]=sorted(set(merged.get("blocked_origins",[])))
        merged["commit"]=commit
        return merged

    # First pass: states, time/origin constraints, quantity modifications, commitments.
    for pid,pr in proposal_ref.items():
        acs=actions_by_pid.get(pid,[])
        for ac in acs:
            if ac.get("proposal_uuid") and pr.get("proposal_uuid") and ac["proposal_uuid"]!=pr["proposal_uuid"]:
                raise ValueError(f"stale proposal_uuid for {pid}")
            if ac.get("proposal_version") is not None and pr.get("proposal_version") not in {None,""}:
                if int(ac["proposal_version"])!=int(pr["proposal_version"]):
                    raise ValueError(f"stale proposal_version for {pid}: {ac['proposal_version']} != {pr['proposal_version']}")
        primary=acs[-1] if acs else None
        act=primary.get("action") if primary else None
        constraints=merged_constraints(pid)
        allocs=_proposal_allocations(pr)
        if not allocs:
            proposal_states.append({"proposal_id":pid,"carrier_id":pr.get("carrier_id"),"state":"PENDING","action":"NONE",
                                    "negotiation_round":negotiation_round,"final_eligible":False})
            continue
        need_ids={nid for nid,_ in allocs if nid in need_by_id}

        # Update time windows BEFORE assignment generation.
        if constraints.get("latest_arrival"):
            ts,slot=_parse_time_in_horizon(constraints["latest_arrival"],service,"latest_arrival")
            for nid in need_ids:
                nd=need_by_id[nid]
                nd.setdefault("original_due_time",nd["due_time"])
                nd["due_time"]=ts.strftime("%Y-%m-%d %H:%M"); nd["due_slot"]=slot
                effective_due[nid]=slot
        if constraints.get("earliest_arrival"):
            _,slot=_parse_time_in_horizon(constraints["earliest_arrival"],service,"earliest_arrival")
            for nid in need_ids: effective_earliest[nid]=max(effective_earliest.get(nid,0),slot)
        if constraints.get("max_earliness_hours") is not None:
            hours=float(constraints["max_earliness_hours"])
            if hours<0: raise ValueError("max_earliness_hours must be nonnegative")
            for nid in need_ids: max_earliness[nid]=hours
        for o in constraints.get("blocked_origins",[]):
            for nid in need_ids: blocked_origins[nid].add(o)

        old_q=sum(q for _,q in allocs)
        target_allocs=list(allocs)
        new_q=int(constraints["quantity"]) if constraints.get("quantity") is not None else old_q
        if new_q<0: raise ValueError(f"negative quantity for {pid}")
        if new_q != old_q:
            # Keep earlier-due original allocation first if carrier reduces quantity.
            alloc_sorted=sorted(allocs,key=lambda z:(need_by_id[z[0]]["due_slot"],z[0]))
            target_allocs=[]; remain=min(new_q,old_q)
            for nid,q in alloc_sorted:
                take=min(q,remain)
                if take>0: target_allocs.append((nid,take))
                remain-=take
            if new_q>old_q:
                delta=new_q-old_q
                due_txt=constraints.get("latest_arrival") or pr.get("latest_need_due") or pr.get("earliest_need_due")
                due,slot=_parse_time_in_horizon(due_txt,service,"MODIFY_SERVICE quantity due")
                base_id=f"QINC_{pid}"; suffix=1; nid=base_id
                while nid in need_by_id:
                    suffix+=1; nid=f"{base_id}_{suffix}"
                k=pr["container_size"]
                extra={"need_id":nid,"carrier_id":pr["carrier_id"],"destination":pr["destination"],
                       "destination_name":HUB_NAME[pr["destination"]],"container_size":k,"quantity":delta,
                       "teu":delta*TEU[k],"due_time":due.strftime("%Y-%m-%d %H:%M"),"due_slot":slot,
                       "priority":1,"need_reason":"CHATBOT_MODIFY_SERVICE_QUANTITY_INCREASE","inventory_lb":0}
                needs.append(extra); need_by_id[nid]=extra
                effective_due[nid]=slot
                effective_earliest[nid]=0
                max_earliness[nid]=constraints.get("max_earliness_hours")
                blocked_origins[nid].update(constraints.get("blocked_origins",[]))
                if constraints.get("earliest_arrival"):
                    _,es=_parse_time_in_horizon(constraints["earliest_arrival"],service,"earliest_arrival")
                    effective_earliest[nid]=es
                target_allocs.append((nid,delta)); action_extra_need[pid]=(nid,delta)

            # Removed amount is not re-proposed in this negotiation round.
            #
            # v7 fix (review finding #4): v6.1 additionally wrote the *kept* amount into
            # forced_service_by_need and later constrained the NEED TOTAL to exactly that
            # value. When one need was split across several proposals, reducing one
            # proposal silently deleted the untouched allocations of the other proposals.
            # Reproduced: NEED0039 (3 boxes over PROP0013+PROP0016) lost 2 instead of 1.
            #
            # The reduction is already fully expressed by declined_by_need (an upper
            # bound on that need). Commitment, if any, is expressed by accepted_by_need
            # (a lower bound). No need-level equality is required or correct.
            target_map=defaultdict(int)
            for nid,q in target_allocs: target_map[nid]+=q
            for nid,q in allocs:
                removed=q-target_map.get(nid,0)
                if removed>0: declined_by_need[nid]+=removed

        commit=bool(constraints.get("commit",False))
        if act in {"ACCEPT_SERVICE","ACCEPT_EXACT_PLAN"}: commit=True

        if act=="DECLINE_RAIL_SERVICE":
            for nid,q in allocs: declined_by_need[nid]+=q
        elif commit:
            for nid,q in target_allocs: accepted_by_need[nid]+=q

        # Store exact/reject option requests for post-assignment constraints.
        if act=="ACCEPT_EXACT_PLAN": exact_requests.append((pid,pr,target_allocs))
        if act=="REJECT_OPTION": reject_option_requests.append((pid,pr,allocs))

        if not acs:
            state="PENDING"
        elif act=="ACCEPT_SERVICE": state="ACCEPTED_SERVICE"
        elif act=="ACCEPT_EXACT_PLAN": state="ACCEPTED_EXACT_PLAN"
        elif act=="REJECT_OPTION": state="ALTERNATIVE_REQUESTED"
        elif act=="DECLINE_RAIL_SERVICE": state="DECLINED"
        elif act in {"MODIFY_SERVICE","CHANGE_QUANTITY","CHANGE_LATEST_ARRIVAL","SET_EARLIEST_ARRIVAL","SET_MAX_EARLINESS","BLOCK_ORIGIN"}:
            state="MODIFIED_ACCEPTED" if commit else "MODIFIED_PENDING"
        else: state="PENDING"
        proposal_states.append({"proposal_id":pid,"carrier_id":pr.get("carrier_id"),"state":state,
                                "action":act or "NONE","negotiation_round":negotiation_round,
                                "final_eligible":state in {"ACCEPTED_SERVICE","ACCEPTED_EXACT_PLAN","MODIFIED_ACCEPTED"}})
        if acs:
            action_audit.append({"proposal_id":pid,"action":"+".join(a.get("action","") for a in acs),"applied":True,
                                 "reason":"conditions_normalized_before_candidate_generation"})

    # Rebuild defaults for extra needs and derive earliest windows from max-earliness AFTER effective due changes.
    # v7: a service-wide default max-earliness may be applied when the carrier has not
    # set one. v6.1 had no default, so empties could arrive up to 132h before they were
    # needed (review finding #1). The default is a scenario parameter, not a KORAIL rule.
    for nid,nd in need_by_id.items():
        effective_due.setdefault(nid,int(nd["due_slot"]))
        effective_earliest.setdefault(nid,0)
        max_earliness.setdefault(nid,None)
        if max_earliness[nid] is None and default_max_earliness is not None:
            max_earliness[nid]=float(default_max_earliness)
        if max_earliness[nid] is not None:
            effective_earliest[nid]=max(effective_earliest[nid],max(0,effective_due[nid]-int(math.ceil(max_earliness[nid]))))
        if effective_earliest[nid] > effective_due[nid]:
            raise ValueError(f"arrival window infeasible for {nid}: earliest>{effective_due[nid]}")

    # Candidate assignment variables.
    assignments=[]; idx=0; U={}
    for n in needs:
        U[n["need_id"]]=idx; idx+=1

    for n in needs:
        nid=n["need_id"]; c=n["carrier_id"]; k=n["container_size"]; d=n["destination"]
        due=int(effective_due[nid]); earliest=int(effective_earliest[nid])
        for p in trains:
            if d not in p.path: continue
            # v7: 도착이 아니라 "하화 완료 = 실제 사용 가능 시각" 으로 기한을 판정한다.
            avail_t=p.avail_slot.get(d,p.arr_slot[d])
            arr_t=p.arr_slot[d]
            if avail_t>due or avail_t<earliest: continue
            dpos=p.path.index(d)
            for o in p.path[:dpos]:
                if o in blocked_origins[nid]: continue
                # v7: 공컨은 출발이 아니라 "상차 개시" 시점에 거점에 있어야 한다.
                load_t=p.load_slot.get(o,p.dep_slot[o])
                if source_cap[(c,o,k,load_t)] <= 0: continue
                segs=subpath_segments(p.path,o,d)
                if not segs: continue
                assignments.append(AssignVar(idx,nid,c,k,o,d,p.train_id,load_t,avail_t,segs,fare_per_box(o,d,k)))
                idx+=1

    # Eligible quantity used only for safe pruning. FINAL uses only committed quantity.
    eligible_qty={}
    for nd in needs:
        nid=nd["need_id"]; total=nd["quantity"]
        if run_mode=="FINAL": q=accepted_by_need.get(nid,0)
        else: q=max(total-declined_by_need.get(nid,0),0)
        eligible_qty[nid]=q

    if min_load_factor is not None and min_load_factor > 0:
        pmap={p.train_id:p for p in trains}
        by_t_need=defaultdict(list)
        for a in assignments: by_t_need[(a.train_id,a.need_id)].append(a)
        potential=defaultdict(float)
        for (tid,nid),alist in by_t_need.items():
            if eligible_qty.get(nid,0)<=0: continue
            nd=need_by_id[nid]
            best_dist=max(sum(SEGMENT_DISTANCE[s] for s in a.segments) for a in alist)
            potential[tid] += eligible_qty[nid]*TEU[nd["container_size"]]*best_dist
        feasible_tids=set()
        for tid,val in potential.items():
            p=pmap[tid]; total_dist=sum(SEGMENT_DISTANCE[s] for s in p.segments)
            min_cap=min(FORMATION[f]["capacity_teu"] for f in p.formations)
            if val + 1e-9 >= float(min_load_factor)*min_cap*total_dist:
                feasible_tids.add(tid)
        assignments=[a for a in assignments if a.train_id in feasible_tids]

    idx=len(U)
    for a in assignments: a.var=idx; idx+=1
    relevant_train_ids=sorted({a.train_id for a in assignments})
    train_by_id={p.train_id:p for p in trains if p.train_id in set(relevant_train_ids)}
    Y={}; Z={}
    for tid in relevant_train_ids:
        Y[tid]=idx; idx+=1
        for f in train_by_id[tid].formations:
            Z[(tid,f)]=idx; idx+=1

    nvars=idx
    lo=np.zeros(nvars); up=np.full(nvars,np.inf); integ=np.ones(nvars,dtype=int)
    for tid,v in Y.items(): up[v]=1
    for key,v in Z.items(): up[v]=1
    for a in assignments: up[a.var]=need_by_id[a.need_id]["quantity"]
    for need_id,v in U.items(): up[v]=need_by_id[need_id]["quantity"]

    rows=SparseRows(nvars)
    by_need=defaultdict(list); by_source=defaultdict(list); by_train_seg=defaultdict(list); by_train=defaultdict(list)
    for a in assignments:
        by_need[a.need_id].append(a); by_source[(a.carrier,a.origin,a.size)].append(a); by_train[a.train_id].append(a)
        for seg in a.segments: by_train_seg[(a.train_id,seg)].append(a)

    # 1. Need conservation.
    for need in needs:
        coeff={U[need["need_id"]]:1}
        for a in by_need[need["need_id"]]: coeff[a.var]=1
        rows.add(coeff,lb=need["quantity"],ub=need["quantity"])

    # 2. Cumulative source release capacity.
    for key,alist in by_source.items():
        c,o,k=key; dep_times=sorted({a.dep_slot for a in alist})
        if not dep_times: continue
        check_times=set(dep_times); prev=None
        for t in range(min(dep_times),len(timestamps)):
            cap=source_cap[(c,o,k,t)]
            if prev is not None and cap < prev: check_times.add(t)
            prev=cap
        check_times.add(len(timestamps)-1)
        for t in sorted(check_times):
            coeff={a.var:1 for a in alist if a.dep_slot<=t}
            if coeff: rows.add(coeff,ub=source_cap[(c,o,k,t)])

    # 3. Formation selection.
    for tid in relevant_train_ids:
        coeff={Y[tid]:-1}
        for f in train_by_id[tid].formations: coeff[Z[(tid,f)]]=1
        rows.add(coeff,lb=0,ub=0)

    # 4. Segment capacity.
    for tid in relevant_train_ids:
        p=train_by_id[tid]
        for seg in p.segments:
            coeff={}
            for a in by_train_seg[(tid,seg)]: coeff[a.var]=TEU[a.size]
            for f in p.formations: coeff[Z[(tid,f)]]=-FORMATION[f]["capacity_teu"]
            rows.add(coeff,ub=0)

    # 5. Minimum distance-weighted load factor scenario.
    if min_load_factor is not None and min_load_factor>0:
        alpha=float(min_load_factor)
        for tid in relevant_train_ids:
            p=train_by_id[tid]; total_dist=sum(SEGMENT_DISTANCE[s] for s in p.segments)
            coeff=defaultdict(float)
            for a in by_train[tid]:
                used_dist=sum(SEGMENT_DISTANCE[s] for s in a.segments)
                coeff[a.var]+=TEU[a.size]*used_dist
            for f in p.formations: coeff[Z[(tid,f)]]-=alpha*FORMATION[f]["capacity_teu"]*total_dist
            rows.add(dict(coeff),lb=0)

    # 6. Optional KORAIL operational constraints.
    # v7 (지시서 Phase 7): 데이터가 없으면 NOT_APPLIED_NO_DATA 로 명시 기록한다.
    operational_audit=[]
    for kind in ("path_slot_capacity","resource_capacity"):
        if not operations_obj.get(kind):
            operational_audit.append({
                "type":kind.upper(),"status":"NOT_APPLIED_NO_DATA",
                "rule":"KORAIL 실제 운영자원 데이터가 제공되지 않아 비활성. "
                       "구조는 구현되어 있으며 값만 넣으면 즉시 적용된다."})
    for rule in operations_obj.get("path_slot_capacity",[]):
        st=datetime.strptime(rule["start_time"],"%Y-%m-%d %H:%M"); en=datetime.strptime(rule["end_time"],"%Y-%m-%d %H:%M")
        coeff={}
        for tid,p in train_by_id.items():
            if not (st <= p.origin_departure <= en): continue
            if not family_matches(p.family, rule.get("service_family")): continue
            if rule.get("origin_terminal") and p.path[0]!=rule["origin_terminal"]: continue
            if rule.get("destination_terminal") and p.path[-1]!=rule["destination_terminal"]: continue
            coeff[Y[tid]]=1
        if coeff:
            rows.add(coeff,ub=int(rule["max_trains"]))
            operational_audit.append({"type":"PATH_SLOT_CAPACITY","status":"APPLIED","matched_trains":len(coeff),"limit":int(rule["max_trains"]),"rule":json.dumps(rule,ensure_ascii=False)})

    # Hourly locomotive / wagon availability. Train is active from origin departure through destination arrival.
    for rule in operations_obj.get("resource_capacity",[]):
        st,stslot=_parse_time_in_horizon(rule["start_time"],service,"resource start_time")
        en,enslot=_parse_time_in_horizon(rule["end_time"],service,"resource end_time")
        for t in range(stslot,enslot+1):
            active=[]
            for tid,p in train_by_id.items():
                dep0=p.dep_slot[p.path[0]]; arrn=p.arr_slot[p.path[-1]]
                if dep0<=t<=arrn: active.append(tid)
            if not active: continue
            if rule.get("available_locomotives") is not None:
                rows.add({Y[tid]:1 for tid in active},ub=int(rule["available_locomotives"]))
            if rule.get("available_wagons") is not None:
                coeff={}
                for tid in active:
                    for f in train_by_id[tid].formations: coeff[Z[(tid,f)]]=FORMATION[f]["wagons"]
                rows.add(coeff,ub=int(rule["available_wagons"]))
        operational_audit.append({"type":"RESOURCE_CAPACITY","status":"APPLIED","matched_time_slots":enslot-stslot+1,
                                  "limit":json.dumps({k:rule.get(k) for k in ["available_wagons","available_locomotives"]},ensure_ascii=False),
                                  "rule":json.dumps(rule,ensure_ascii=False)})

    # 7. Exact accept / option reject after candidate regeneration.
    assignment_lookup=defaultdict(list)
    for a in assignments: assignment_lookup[(a.need_id,a.origin,a.train_id)].append(a)
    unpreservable_exact=[]
    for pid,pr,allocs in exact_requests:
        found=[]
        for nid,q in allocs:
            vars_=assignment_lookup.get((nid,pr["origin"],pr["train_id"]),[])
            if vars_: found.append((vars_[0],q))
        if len(found)!=len(allocs):
            # v7: 확정 물량이 적어 해당 열차가 최소 consolidation 요건을 잃는 것은
            # 정상적인 서비스 상황이다 (소규모 수락만으로 전용열차를 강제 운행하지 않음).
            # FINAL 에서는 예외를 던지지 않고 "확정 불가 commitment" 로 보고한다.
            unpreservable_exact.append({
                "proposal_id":pid,"carrier_id":pr.get("carrier_id"),
                "origin":pr.get("origin"),"destination":pr.get("destination"),
                "container_size":pr.get("container_size"),"train_id":pr.get("train_id"),
                "boxes":sum(q for _,q in allocs),
                "reason":"EXACT_PLAN_TRAIN_NO_LONGER_AVAILABLE"})
            if run_mode!="FINAL":
                raise AxisRequestError(
                    "EXACT_PLAN_NOT_PRESERVABLE",
                    f"고정 수락한 계획({pid})을 변경된 조건에서 유지할 수 없습니다. "
                    "같은 라운드의 다른 선사 조정으로 해당 열차가 최소 consolidation 요건을 "
                    "잃었습니다. 재협의가 필요합니다.",
                    detail={"proposal_id":pid,"train_id":pr.get("train_id"),
                            "carrier_id":pr.get("carrier_id"),
                            "min_load_factor":min_load_factor},
                    alternatives=[
                        {"action":"USE_ACCEPT_SERVICE",
                         "note":"열차 고정 없이 서비스 수준만 수락하면 KORAIL 이 다른 열차로 재배정할 수 있습니다."},
                        {"action":"LOWER_MIN_CONSOLIDATION_LEVEL","current":min_load_factor}])
            continue
        for a,q in found: rows.add({a.var:1},lb=q,ub=q)
    for pid,pr,allocs in reject_option_requests:
        for nid,q in allocs:
            vars_=assignment_lookup.get((nid,pr["origin"],pr["train_id"]),[])
            for a in vars_: rows.add({a.var:1},lb=0,ub=0)

    # 6b. Physical conflict — one departure per (origin terminal, departure slot).
    #
    # v7 (review finding #20): v6.1 had nothing stopping the model from opening
    # UIWANG->BUGANG, UIWANG->YAKMOK and UIWANG->BUSAN all at 00:00 on the same day.
    # Those are three trains leaving the same terminal on the same trunk in the same hour.
    # This is always on: it is a physical fact, not an optional KORAIL data input.
    conflict_groups=defaultdict(list)
    for tid,p in train_by_id.items():
        conflict_groups[(p.path[0],p.dep_slot[p.path[0]])].append(tid)
    conflicts=0
    for key,tids in sorted(conflict_groups.items()):
        if len(tids)>1:
            rows.add({Y[t]:1 for t in tids},ub=1); conflicts+=1
    if conflicts:
        operational_audit.append({"type":"DEPARTURE_SLOT_CONFLICT","status":"APPLIED",
                                  "constrained_groups":conflicts,
                                  "rule":"at most one new train per (origin_terminal, departure_slot)"})

    # Shared trunk occupancy: trains running the same physical trunk segment in the
    # same hour also conflict, even when they start from different terminals.
    trunk_groups=defaultdict(list)
    for tid,p in train_by_id.items():
        for seg in p.segments:
            if seg in SHARED_TRUNK_SEGMENTS:
                trunk_groups[(seg,p.dep_slot[seg[0]])].append(tid)
    trunk_conflicts=0
    for key,tids in sorted(trunk_groups.items(), key=lambda kv:(kv[0][0],kv[0][1])):
        if len(tids)>1:
            rows.add({Y[t]:1 for t in tids},ub=1); trunk_conflicts+=1
    if trunk_conflicts:
        operational_audit.append({"type":"SHARED_TRUNK_CONFLICT","status":"APPLIED",
                                  "constrained_groups":trunk_conflicts,
                                  "rule":"at most one new train per shared trunk segment per hour"})

    # 7b. Carrier inventory policy — MAX_INVENTORY (Policy Type C).
    # The model has no inventory variable, so the bound is applied to the physical
    # no-rail baseline stock plus everything rail delivers up to that hour:
    #     baseline_stock[c,h,k,t] + sum(arrivals with dest=h, arr_slot <= t) <= UB
    inv_ub=service.get("inventory_ub",{}) or {}
    by_dest=defaultdict(list)
    for a in assignments: by_dest[(a.carrier,a.destination,a.size)].append(a)
    baseline_stock=service.get("baseline_stock",{})
    policy_audit=[]
    for (c,h,k,t),cap in sorted(inv_ub.items()):
        alist=[a for a in by_dest.get((c,h,k),[]) if a.arr_slot<=t]
        if not alist: continue
        stock=baseline_stock.get((c,h,k,t),0)
        rows.add({a.var:1 for a in alist},ub=max(cap-stock,0))
    if inv_ub:
        policy_audit.append({"policy":"MAX_INVENTORY","constrained_slots":len(inv_ub)})

    # 7c. Carrier inventory policy — BLOCK_OUTBOUND (Policy Type E).
    for (c,h,k),(cap,s0,s1) in sorted(service.get("outbound_cap",{}).items()):
        alist=[a for a in by_source.get((c,h,k),[]) if s0<=a.dep_slot<=s1]
        if not alist: continue
        rows.add({a.var:1 for a in alist},ub=cap)
        policy_audit.append({"policy":"BLOCK_OUTBOUND","carrier":c,"hub":h,
                             "size":k,"max_boxes":cap,"candidate_vars":len(alist)})

    # 8. Commitment-state constraints.
    for nd in needs:
        nid=nd["need_id"]; coeff={a.var:1 for a in by_need[nid]}
        if not coeff: continue
        total_q=nd["quantity"]; accepted=accepted_by_need.get(nid,0); declined=declined_by_need.get(nid,0)
        if accepted>total_q: raise ValueError(f"accepted quantity exceeds need {nid}: {accepted}>{total_q}")
        # v7: bounds only. accepted -> lower bound, declined -> upper bound.
        # No need-level equality (see the quantity-modification fix above).
        if run_mode=="FINAL":
            rows.add(coeff,lb=0,ub=accepted)
        else:
            if accepted>0: rows.add(coeff,lb=accepted)
            if declined>0: rows.add(coeff,ub=max(total_q-declined,0))

    A=rows.matrix(); lb=np.array(rows.lb); ub=np.array(rows.ub)
    meta={"needs":needs,"need_by_id":need_by_id,"assignments":assignments,"U":U,"Y":Y,"Z":Z,
          "trains":train_by_id,"by_train":by_train,"by_train_seg":by_train_seg,
          "A":A,"lb":lb,"ub":ub,"timestamps":timestamps,"source_cap":source_cap,"action_audit":action_audit,
          "proposal_states":proposal_states,"accepted_by_need":dict(accepted_by_need),"declined_by_need":dict(declined_by_need),
          "run_mode":run_mode,"min_load_factor":min_load_factor,"effective_due":effective_due,
          "effective_earliest":effective_earliest,"blocked_origins":{k:sorted(v) for k,v in blocked_origins.items()},
          "negotiation_round":negotiation_round,"proposal_ref":proposal_ref,"operational_audit":operational_audit,
          "operations_active":bool(operations_obj.get("path_slot_capacity") or operations_obj.get("resource_capacity")),
          "active_policies":service.get("active_policies",[]),"policy_audit":policy_audit,
          "unpreservable_exact":unpreservable_exact}
    return meta,lo,up,integ

def solve_lex(meta,lo,up,integ,time_limit=90,mip_gap=0.001,verbose=False,
              strict_stages=("Z1_unserved_teu","Z2_train_count")):
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
    for tid,v in meta["Y"].items(): c3[v]=meta["trains"][tid].service_distance_km
    r3=solve(c3,e2,"Z3_train_km")
    z3=float(c3@r3.x)
    e3=e2+[({i:float(c3[i]) for i in np.flatnonzero(c3)},-np.inf,z3+1e-4)]

    # Z4 wagon-km: avoid oversized formations.
    c4=np.zeros(n)
    for (tid,f),v in meta["Z"].items(): c4[v]=FORMATION[f]["wagons"]*meta["trains"][tid].service_distance_km
    r4=solve(c4,e3,"Z4_wagon_km")
    z4=float(c4@r4.x)
    e4=e3+[({i:float(c4[i]) for i in np.flatnonzero(c4)},-np.inf,z4+1e-4)]

    # Z5 customer-service timing: among identical operating resources, avoid moving empties excessively early.
    # Measured as TEU-hours between train arrival and the need due time.
    c5=np.zeros(n)
    for a in meta["assignments"]:
        due=meta["need_by_id"][a.need_id]["due_slot"]
        c5[a.var]=TEU[a.size]*max(due-a.arr_slot,0)
    r5=solve(c5,e4,"Z5_earliness_teu_hours")
    z5=float(c5@r5.x)
    e5=e4+[({i:float(c5[i]) for i in np.flatnonzero(c5)},-np.inf,z5+1e-4)]

    # Z6 customer rail charge tie-breaker only after service and KORAIL operating resources/timing are fixed.
    c6=np.zeros(n)
    for a in meta["assignments"]: c6[a.var]=a.fare
    r6=solve(c6,e5,"Z6_rail_charge_krw")
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
    r7=solve(c7,e6,"Z7_deterministic_tiebreak")
    final=r7

    summary={"unserved_teu":z1,"train_count":z2,"train_km":round(z3,3),"wagon_km":round(z4,3),
             "earliness_teu_hours":round(z5,3),"rail_charge_krw":round(z6,2),
             "tiebreak_index":round(float(c7@final.x),3),
             "all_stages_proven_optimal":True,
             "solver_stage_count":len(audit)}
    return final,summary,audit

def extract(meta,result,summary,outdir:Path,scenario:str,solver_audit=None):
    outdir.mkdir(parents=True,exist_ok=True); x=result.x
    positive=[]
    for a in meta["assignments"]:
        q=int(round(x[a.var]))
        if q>0: positive.append((a,q))
    selected={tid:p for tid,p in meta["trains"].items() if x[meta["Y"][tid]]>0.5}
    chosen={}
    for tid,p in selected.items():
        for f in p.formations:
            if x[meta["Z"][(tid,f)]]>0.5: chosen[tid]=f; break

    # Internal proposal detail: one exact assignment per need event.
    detail_rows=[]
    for i,(a,q) in enumerate(sorted(positive,key=lambda z:(z[0].carrier,z[0].train_id,z[0].need_id,z[0].origin)),1):
        nd=meta["need_by_id"][a.need_id]; p=meta["trains"][a.train_id]
        earliest_slot=meta.get("effective_earliest",{}).get(a.need_id,0)
        detail_rows.append({
            "detail_id":f"DETAIL{i:04d}","need_id":a.need_id,"carrier_id":a.carrier,
            "origin":a.origin,"destination":a.destination,"container_size":a.size,"quantity":q,"teu":q*TEU[a.size],
            "original_need_due_time":nd.get("original_due_time",nd["due_time"]),
            "effective_need_due_time":nd["due_time"],
            "earliest_allowed_arrival":meta["timestamps"][earliest_slot].strftime("%Y-%m-%d %H:%M"),
            "train_id":a.train_id,
            "departure_time":meta["timestamps"][a.dep_slot].strftime("%Y-%m-%d %H:%M"),
            "arrival_time":meta["timestamps"][a.arr_slot].strftime("%Y-%m-%d %H:%M"),
            "earliness_hours":int(max(nd["due_slot"]-a.arr_slot,0)),
            "estimated_rail_charge_krw":round(q*a.fare,2),
        })
    write_csv(outdir/"CARRIER_PROPOSAL_DETAIL.csv",detail_rows)

    # User-facing carrier proposal: aggregate needs sharing carrier/origin/destination/size/train.
    groups=defaultdict(list)
    for r in detail_rows:
        groups[(r["carrier_id"],r["origin"],r["destination"],r["container_size"],r["train_id"])].append(r)
    prop_rows=[]
    for i,(key,rs) in enumerate(sorted(groups.items()),1):
        c,o,d,k,tid=key; p=meta["trains"][tid]
        qty=sum(r["quantity"] for r in rs); teu=sum(r["teu"] for r in rs)
        due_times=sorted(r["effective_need_due_time"] for r in rs)
        proposal_status = "FINALIZED" if meta.get("run_mode")=="FINAL" else ("UPDATED_PROPOSAL" if meta.get("run_mode")=="NEGOTIATION" else "PROPOSED")
        need_ids={r["need_id"] for r in rs}
        parent_ids=[]
        for old_pid,old_pr in meta.get("proposal_ref",{}).items():
            if old_pr.get("carrier_id")!=c: continue
            old_need_ids={nid for nid,_ in _proposal_allocations(old_pr)}
            if need_ids & old_need_ids: parent_ids.append(old_pid)
        round_no=int(meta.get("negotiation_round",1))
        need_alloc="|".join(f'{r["need_id"]}:{r["quantity"]}' for r in rs)
        # v7 (review finding #2): the UUID key deliberately excludes need_allocation.
        # In v6.1 any reshuffle of boxes between needs of the same carrier/OD/train
        # minted a new UUID and invalidated every stored chatbot action.
        # The service identity a carrier negotiates over is
        # (carrier, origin, destination, size, train, round) - not the internal split.
        puuid=str(uuid.uuid5(uuid.NAMESPACE_URL,f"AXIS|{round_no}|{c}|{o}|{d}|{k}|{tid}"))
        prop_rows.append({
            "proposal_id":f"PROP{i:04d}","proposal_uuid":puuid,"negotiation_round":round_no,"proposal_version":round_no,
            "parent_proposal_id":"|".join(sorted(parent_ids)),"status":proposal_status,"carrier_id":c,
            "origin":o,"origin_name":HUB_NAME[o],"destination":d,"destination_name":HUB_NAME[d],
            "container_size":k,"quantity":qty,"teu":teu,"earliest_need_due":due_times[0],"latest_need_due":due_times[-1],
            "train_id":tid,"train_origin":p.path[0],"train_destination":p.path[-1],"train_path":" > ".join(p.path),
            "departure_time":rs[0]["departure_time"],"arrival_time":rs[0]["arrival_time"],
            "max_earliness_hours":max(r["earliness_hours"] for r in rs),"min_earliness_hours":min(r["earliness_hours"] for r in rs),
            "estimated_rail_charge_krw":round(sum(r["estimated_rail_charge_krw"] for r in rs),2),
            "need_allocation":need_alloc,
        })
    write_csv(outdir/"CARRIER_PROPOSALS.csv",prop_rows)
    for c in sorted({r["carrier_id"] for r in prop_rows}):
        write_csv(outdir/f"CARRIER_PROPOSALS_{c}.csv",[r for r in prop_rows if r["carrier_id"]==c])

    served_by_need_pre=defaultdict(int)
    for a,q in positive: served_by_need_pre[a.need_id]+=q
    unserved=[]; noncommitted=[]
    for need_id,v in meta["U"].items():
        nd=meta["need_by_id"][need_id]; total_q=nd["quantity"]; served_q=served_by_need_pre.get(need_id,0)
        if meta.get("run_mode")=="FINAL":
            accepted_q=meta.get("accepted_by_need",{}).get(need_id,0)
            unconfirmed=max(accepted_q-served_q,0)
            if unconfirmed>0:
                unserved.append({**nd,"commitment_quantity":accepted_q,"korail_confirmed_quantity":served_q,
                                 "rail_unserved_quantity":unconfirmed,"rail_unserved_teu":unconfirmed*TEU[nd["container_size"]],
                                 "unserved_reason":"ACCEPTED_BUT_NOT_KORAIL_CONFIRMED"})
            nc=max(total_q-accepted_q,0)
            if nc>0:
                noncommitted.append({**nd,"noncommitted_quantity":nc,"noncommitted_teu":nc*TEU[nd["container_size"]],
                                     "status":"NOT_IN_FINAL_PLAN_WITHOUT_CARRIER_COMMITMENT"})
        else:
            q=int(round(x[v]))
            if q>0:
                unserved.append({**nd,"rail_unserved_quantity":q,"rail_unserved_teu":q*TEU[nd["container_size"]],
                                 "unserved_reason":"FORECAST_NEED_NOT_RAIL_ASSIGNED"})
    write_csv(outdir/"RAIL_UNSERVED.csv",unserved)
    write_csv(outdir/"NONCOMMITTED_FORECAST_NEED.csv",noncommitted)

    # Segment loads and train plan.
    segload=defaultdict(int); stop_load=defaultdict(int); stop_unload=defaultdict(int); train_carriers=defaultdict(set)
    for a,q in positive:
        train_carriers[a.train_id].add(a.carrier)
        stop_load[(a.train_id,a.origin)] += q*TEU[a.size]
        stop_unload[(a.train_id,a.destination)] += q*TEU[a.size]
        for seg in a.segments: segload[(a.train_id,seg)] += q*TEU[a.size]

    train_rows=[]; segment_rows=[]; stop_rows=[]
    for tid,p in selected.items():
        f=chosen[tid]; cap=FORMATION[f]["capacity_teu"]
        loads=[]; dw_numer=0; dist_total=0
        for si,seg in enumerate(p.segments,1):
            l=segload[(tid,seg)]; d=SEGMENT_DISTANCE[seg]; loads.append(l); dw_numer += l*d; dist_total += d
            segment_rows.append({"train_id":tid,"segment_sequence":si,"from_hub":seg[0],"to_hub":seg[1],"load_teu":l,
                                 "capacity_teu":cap,"load_factor":round(l/cap,4),"segment_distance_km":d})
        plan_status={"PROPOSAL":"PROVISIONAL","NEGOTIATION":"NEGOTIATION_REOPT","FINAL":"FINAL_OPERATION"}.get(meta.get("run_mode"),"PROVISIONAL")
        train_rows.append({
            "train_id":tid,"plan_status":plan_status,"service_family":p.family,"origin_terminal":p.path[0],"destination_terminal":p.path[-1],
            "path":" > ".join(p.path),"origin_departure_time":p.origin_departure.strftime("%Y-%m-%d %H:%M"),
            "formation_id":f,"wagon_count":FORMATION[f]["wagons"],"capacity_teu":cap,"service_distance_km":p.service_distance_km,
            "peak_load_teu":max(loads) if loads else 0,"peak_load_factor":round(max(loads)/cap,4) if loads else 0,
            "distance_weighted_load_factor":round(dw_numer/(cap*dist_total),4) if dist_total else 0,
            "participating_carriers":len(train_carriers[tid]),"carrier_list":"|".join(sorted(train_carriers[tid])),
        })
        for seqno,hub in enumerate(p.path,1):
            stop_rows.append({"train_id":tid,"stop_sequence":seqno,"hub_code":hub,"hub_name":HUB_NAME[hub],
                              "arrival_time":meta["timestamps"][p.arr_slot[hub]].strftime("%Y-%m-%d %H:%M"),
                              "departure_time":meta["timestamps"][p.dep_slot[hub]].strftime("%Y-%m-%d %H:%M"),
                              "load_teu":stop_load[(tid,hub)],"unload_teu":stop_unload[(tid,hub)]})
    write_csv(outdir/"KORAIL_TRAIN_PLAN.csv",train_rows)
    write_csv(outdir/"SEGMENT_LOAD.csv",segment_rows)
    write_csv(outdir/"STOP_WORK_PLAN.csv",stop_rows)

    # Need service summary.
    need_service=[]
    served_by_need=served_by_need_pre
    for nd in meta["needs"]:
        nid=nd["need_id"]; served=served_by_need[nid]; raw_un=int(round(x[meta["U"][nid]]))
        accepted=meta.get("accepted_by_need",{}).get(nid,0)
        confirmed=min(served,accepted) if meta.get("run_mode")=="FINAL" else 0
        unconfirmed=max(accepted-confirmed,0) if meta.get("run_mode")=="FINAL" else 0
        noncommitted=max(nd["quantity"]-accepted,0) if meta.get("run_mode")=="FINAL" else 0
        need_service.append({**nd,"rail_served_quantity":served,"rail_served_teu":served*TEU[nd["container_size"]],
                             "raw_forecast_unserved_quantity":raw_un,"raw_forecast_unserved_teu":raw_un*TEU[nd["container_size"]],
                             "carrier_commitment_quantity":accepted,"korail_confirmed_quantity":confirmed,
                             "korail_unconfirmed_commitment_quantity":unconfirmed,"noncommitted_quantity":noncommitted})
    write_csv(outdir/"SERVICE_NEED_RESULT.csv",need_service)
    write_csv(outdir/"CHATBOT_ACTION_AUDIT.csv",meta["action_audit"])
    write_csv(outdir/"OPERATIONAL_CONSTRAINT_AUDIT.csv",meta.get("operational_audit",[]))
    write_csv(outdir/"CARRIER_COMMITMENT_STATUS.csv",meta.get("proposal_states",[]))
    write_csv(outdir/"SOLVER_AUDIT.csv",solver_audit or [])
    write_csv(outdir/"UNPRESERVABLE_EXACT_PLAN.csv",meta.get("unpreservable_exact",[]))
    write_csv(outdir/"INVENTORY_POLICY_AUDIT.csv",meta.get("policy_audit",[]))
    (outdir/"ACTIVE_POLICY.json").write_text(
        json.dumps({"scenario":scenario,"active_policies":meta.get("active_policies",[])},
                   ensure_ascii=False,indent=2),encoding="utf-8")

    requested_teu=sum(n["teu"] for n in meta["needs"])
    served_teu=sum(r["rail_served_teu"] for r in need_service)
    # TEU-km: actually transported TEU weighted by the physical distance travelled.
    teu_km=sum(q*TEU[a.size]*sum(SEGMENT_DISTANCE[s] for s in a.segments) for a,q in positive)
    avg_carriers_per_train=(sum(r["participating_carriers"] for r in train_rows)/len(train_rows)
                            if train_rows else 0.0)
    avg_load_factor=(sum(r["distance_weighted_load_factor"] for r in train_rows)/len(train_rows)
                     if train_rows else 0.0)
    committed_boxes=sum(meta.get("accepted_by_need",{}).values())
    committed_teu=sum(meta["accepted_by_need"].get(n["need_id"],0)*TEU[n["container_size"]] for n in meta["needs"])
    confirmed_committed_teu=0
    for n in meta["needs"]:
        nid=n["need_id"]; accepted_q=meta.get("accepted_by_need",{}).get(nid,0)
        confirmed_q=min(served_by_need.get(nid,0),accepted_q)
        confirmed_committed_teu += confirmed_q*TEU[n["container_size"]]
    unconfirmed_committed_teu=max(committed_teu-confirmed_committed_teu,0)
    final={**summary,"scenario":scenario,"run_mode":meta.get("run_mode"),"requested_teu":requested_teu,"served_teu":served_teu,
           "committed_boxes":committed_boxes,"committed_teu":committed_teu,
           "korail_confirmed_committed_teu":confirmed_committed_teu,
           "korail_unconfirmed_committed_teu":unconfirmed_committed_teu,
           "commitment_confirmation_rate":round(confirmed_committed_teu/committed_teu,4) if committed_teu else 1.0,
           "forecast_unserved_teu":max(requested_teu-served_teu,0),
           "final_commitment_unserved_teu":unconfirmed_committed_teu if meta.get("run_mode")=="FINAL" else None,
           "forecast_need_rail_coverage":round(served_teu/requested_teu,4) if requested_teu else 1.0,
           "rail_coverage":(round(confirmed_committed_teu/committed_teu,4) if meta.get("run_mode")=="FINAL" and committed_teu else (round(served_teu/requested_teu,4) if requested_teu else 1.0)),
           "proposal_count":len(prop_rows),"selected_train_count":len(train_rows),
           "teu_km":round(teu_km,1),
           "avg_carriers_per_train":round(avg_carriers_per_train,3),
           "avg_distance_weighted_load_factor":round(avg_load_factor,4),
           "negotiation_round":int(meta.get("negotiation_round",1)),
           "operational_constraints_active":bool(meta.get("operations_active",False)),
           "active_policy_count":len(meta.get("active_policies",[])),
           # v7 metadata (지시서 §4): this is a one-way planning model.
           "return_wagon_movement_included":False,
           "expected_korail_revenue_krw":round(sum(r["estimated_rail_charge_krw"] for r in prop_rows),2)}
    (outdir/"SUMMARY.json").write_text(json.dumps(final,ensure_ascii=False,indent=2),encoding="utf-8")
    return final


def create_accept_all_actions(proposals_csv: Path, out: Path, exact: bool=False):
    actions=[]
    action_name="ACCEPT_EXACT_PLAN" if exact else "ACCEPT_SERVICE"
    if proposals_csv.exists():
        with proposals_csv.open(encoding="utf-8-sig",newline="") as f:
            for r in csv.DictReader(f): actions.append({"proposal_id":r["proposal_id"],"action":action_name})
    obj={"negotiation_round":2,"proposal_actions":actions}
    out.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")
    return obj

def run(hourly_path:Path, initial_path:Path, root:Path, min_load_factor=0.5, policies_path:Optional[Path]=None,
        proposal_reference:Optional[Path]=None, actions_path:Optional[Path]=None, operations_path:Optional[Path]=None,
        scenario="PROPOSAL", run_mode="PROPOSAL", time_limit=90, mip_gap=0.001, verbose=False,
        max_earliness=None, carrier_subset=None, params_xlsx:Optional[Path]=None,
        origin_loading_h=None, intermediate_handling_h=None, destination_unloading_h=None):
    root.mkdir(parents=True,exist_ok=True)
    configure_params(params_xlsx,origin_loading_h,intermediate_handling_h,destination_unloading_h)
    hourly=read_hourly(hourly_path); initial=read_initial(initial_path)
    timestamps=sorted({r["timestamp"] for r in hourly})
    input_dir=root/"MODEL_INPUTS"
    # v7: regenerate the candidate timetable whenever it does not match the input week
    # (review finding #18: v6.1 only checked file existence and silently reused a stale
    # timetable when the planning week changed).
    if not _candidate_inputs_match(input_dir,timestamps[0],len(timestamps)):
        generate_candidate_inputs(timestamps[0],len(timestamps),input_dir)
    policies=read_json(policies_path,{"inventory_policies":[]})
    service=generate_service_needs(hourly,initial,policies,input_dir)
    trains=read_candidate_inputs(input_dir)
    operations=read_json(operations_path,{"path_slot_capacity":[],"resource_capacity":[]})
    meta,lo,up,integ=build_milp(service,trains,min_load_factor,proposal_reference,actions_path,
                                run_mode,operations,max_earliness,carrier_subset)
    # FINAL 에서 후보가 0 인 것은 오류가 아니라 정상 결과다.
    # "확정 물량이 최소 consolidation 요건에 못 미치면 KORAIL 이 전용열차를 강제 운행하지 않는다"
    # 는 서비스 원칙 그대로이며, 확정 불가 물량은 korail_unconfirmed_committed_teu 로 보고된다.
    if not meta["assignments"] and run_mode!="FINAL":
        raise diagnose_infeasibility(service,meta,max_earliness,min_load_factor)
    try:
        result,summary,solver_audit=solve_lex(meta,lo,up,integ,time_limit,mip_gap,verbose)
    except ModelInfeasible as exc:
        diag=diagnose_commitment_conflict(meta,lo,up,integ)
        if diag and diag.get("diagnosis")=="COMMITMENT_SHORTFALL":
            raise AxisRequestError(
                "COMMITMENT_NOT_SIMULTANEOUSLY_FEASIBLE",
                "이번 라운드에서 확정된 Carrier Commitment 를 동시에 만족시키는 "
                "철도운영계획이 존재하지 않습니다. 같은 라운드의 다른 선사 거절·수정으로 "
                "해당 물량을 싣던 열차가 최소 consolidation 요건을 충족하지 못하게 되었습니다.",
                detail={"stage":exc.stage,**diag,
                        "min_load_factor":min_load_factor,
                        "max_earliness_hours":max_earliness},
                alternatives=[
                    {"action":"LOWER_MIN_CONSOLIDATION_LEVEL","current":min_load_factor,
                     "note":"최소 적재율을 낮추면 해당 열차를 개설할 수 있습니다."},
                    {"action":"RELAX_MAX_EARLINESS","current":max_earliness,
                     "note":"조기도착 허용을 늘리면 다른 열차에 합칠 수 있습니다."},
                    {"action":"REVIEW_COMMITMENT",
                     "note":"확정 불가 물량은 FINAL 에서 korail_unconfirmed_committed_teu 로 보고됩니다."}]
            ) from exc
        raise AxisRequestError(
            "MODEL_INFEASIBLE",
            "현재 조건 조합에서는 실행 가능한 철도운영계획이 존재하지 않습니다.",
            detail={"stage":exc.stage,"solver_message":exc.solver_message[:200],
                    "min_load_factor":min_load_factor,
                    "max_earliness_hours":max_earliness},
            alternatives=[{"action":"LOWER_MIN_CONSOLIDATION_LEVEL","current":min_load_factor},
                          {"action":"RELAX_MAX_EARLINESS","current":max_earliness}]) from exc
    except RuntimeError as exc:
        raise AxisRequestError(
            "SOLVER_LIMIT_REACHED",
            "제한 시간 안에 최적해를 증명하지 못했습니다. 결과를 최적해로 제시할 수 없습니다.",
            detail={"solver_message":str(exc)[:300],"time_limit_sec":time_limit},
            alternatives=[{"action":"INCREASE_TIME_LIMIT","current":time_limit},
                          {"action":"TIGHTEN_MAX_EARLINESS","current":max_earliness,
                           "note":"조기도착 상한을 두면 후보 조합이 줄어 최적성 증명이 쉬워집니다."}]
        ) from exc
    summary["default_max_earliness_hours"]=max_earliness
    summary["origin_loading_h"]=ORIGIN_LOADING_H
    summary["intermediate_handling_h"]=INTERMEDIATE_HANDLING_H
    summary["destination_unloading_h"]=DESTINATION_UNLOADING_H
    out=root/scenario
    res=extract(meta,result,summary,out,scenario,solver_audit)
    write_csv(out/"RAIL_PARAMETER_PROVENANCE.csv",PARAMS.provenance)
    write_csv(out/"DISTANCE_VALIDATION.csv",
              [c for c in PARAMS.validation if c["check"]!="_deltas"])
    write_csv(out/"DISTANCE_PHYSICAL_VS_TARIFF.csv",
              [c for c in PARAMS.validation if c["check"]=="_deltas"][0]["detail"])
    return res


def _main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--hourly",required=True); ap.add_argument("--initial",required=True); ap.add_argument("--root",required=True)
    ap.add_argument("--min-load-factor",type=float,default=0.5)
    ap.add_argument("--policies"); ap.add_argument("--proposal-reference"); ap.add_argument("--actions"); ap.add_argument("--operations")
    ap.add_argument("--scenario",default="PROPOSAL"); ap.add_argument("--run-mode",choices=["PROPOSAL","NEGOTIATION","FINAL"],default="PROPOSAL")
    ap.add_argument("--time-limit",type=float,default=300); ap.add_argument("--mip-gap",type=float,default=0.001)
    ap.add_argument("--max-earliness",type=float,default=None,
                    help="Default max hours a container may arrive before its due time. "
                         "Omit for unrestricted (v6.1 behaviour).")
    ap.add_argument("--carrier",action="append",default=None,
                    help="Restrict optimisation to these carriers (Carrier Separate baseline).")
    ap.add_argument("--params",default=None,help="AXIS_rail_OD_parameters_v1.xlsx")
    ap.add_argument("--origin-loading-h",type=float,default=None)
    ap.add_argument("--intermediate-handling-h",type=float,default=None)
    ap.add_argument("--destination-unloading-h",type=float,default=None)
    ap.add_argument("--verbose",action="store_true")
    a=ap.parse_args()
    summ=run(Path(a.hourly),Path(a.initial),Path(a.root),a.min_load_factor,Path(a.policies) if a.policies else None,
             Path(a.proposal_reference) if a.proposal_reference else None,Path(a.actions) if a.actions else None,
             Path(a.operations) if a.operations else None,a.scenario,a.run_mode,a.time_limit,a.mip_gap,a.verbose,
             a.max_earliness,set(a.carrier) if a.carrier else None,
             Path(a.params) if a.params else None,
             a.origin_loading_h,a.intermediate_handling_h,a.destination_unloading_h)
    print(json.dumps(summ,ensure_ascii=False,indent=2))


def main():
    try:
        _main()
    except (AxisRequestError,PolicyValidationError) as exc:
        # 챗봇 backend 가 그대로 소비할 수 있는 구조화 결과. raw traceback 금지.
        print(json.dumps(exc.as_dict(),ensure_ascii=False,indent=2))
        raise SystemExit(2)

if __name__=="__main__": main()
