"""
AXIS v7.1 — Carrier Disaggregation Layer
=======================================

Aggregate Master Data (v8, 6 hubs, hourly) 를 Virtual Carrier 차원으로 분해한다.

설계 원칙 (프로젝트 통합계획 v3 §11-§21 준수)
---------------------------------------------
1. Aggregate Master Data 는 절대 변경하지 않는다.
   모든 (timestamp, hub, size) 에서 Σ_c = 원본 을 정확히 만족한다.
2. 거점별 carrier prior 는 서로 다르다 (§14).
   PNC / KITL 공개자료를 calibration prior 로만 사용하고,
   거점별 혼합계수 λ 로 6개 거점 각각 고유 profile 을 만든다 (§15).
3. Demand share 와 Supply share 를 동일 비율로 나누지 않는다 (§16, §17).
   선사별 "공급 거점 / 수요 거점" 역할을 명시적으로 정의하고
   multinomial-logit tilt 로 구조적 비대칭을 만든다.
4. carrier share 는 시간에 따라 천천히 변한다 (§18).
   6시간 block 단위 Dirichlet 섭동 + 고정 seed.
5. 컨테이너 개수는 정수이며 총량이 보존된다 (§19).
   Largest Remainder Method.

Virtual Carrier 해석 주의
-------------------------
CARRIER_A ~ CARRIER_F 는 익명 Virtual Carrier 이다 (§12).
공개자료의 점유율 *순위 shape* 만 차용했을 뿐,
특정 실제 선사를 지칭하지 않으며 전국 시장점유율로 해석해서도 안 된다.

출처
----
- Aggregate Master : AXIS_hourly_empty_demand_supply_v8_6hubs.xlsx
- PNC  Empty 현황  : https://svc.pncport.com/info/          (2026-08-09 snapshot)
- KITL 반출가능수량 : https://info.kitl.com/jsp/T05/banchul_allow.jsp (2026-08-09 snapshot)
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# 상수
# --------------------------------------------------------------------------
HUBS = ["UIWANG", "BUGANG", "YAKMOK", "BUSAN", "DONGSAN", "GWANGYANG"]
SIZES = ["20FT", "40FT"]
TEU = {"20FT": 1, "40FT": 2}
HUB_NAME = {
    "UIWANG": "의왕ICD(오봉역)",
    "BUGANG": "부강화물역 CY",
    "YAKMOK": "약목역 CY",
    "BUSAN": "부산신항",
    "DONGSAN": "동산역 CY",
    "GWANGYANG": "신광양항",
}

CARRIERS = ["CARRIER_A", "CARRIER_B", "CARRIER_C", "CARRIER_D", "CARRIER_E", "CARRIER_F"]

# --------------------------------------------------------------------------
# 거점별 calibration 혼합계수 λ  (통합계획 §14, §15)
#   P_hub = normalize( λ · P_PNC + (1-λ) · P_KITL )
#   λ 는 synthetic scenario parameter 이며 실측값이 아니다.
# --------------------------------------------------------------------------
HUB_LAMBDA = {
    "BUSAN": 1.00,      # PNC 공개자료 직접 사용
    "YAKMOK": 0.85,     # 경부축 내륙 — 부산권 영향 지배적이나 동일하지 않음
    "BUGANG": 0.55,     # 두 축 접속 중간거점 — 부산권 소폭 우세
    "UIWANG": 0.45,     # 두 corridor 접속 수도권 — 광양권 소폭 우세
    "DONGSAN": 0.15,    # 서남축 내륙 — 광양권 영향 지배적이나 동일하지 않음
    "GWANGYANG": 0.00,  # KITL 공개자료 직접 사용
}

HUB_SOURCE_TYPE = {
    "BUSAN": "PNC_CALIBRATED",
    "YAKMOK": "PNC_DERIVED_SYNTHETIC",
    "GWANGYANG": "KITL_CALIBRATED",
    "DONGSAN": "KITL_DERIVED_SYNTHETIC",
    "UIWANG": "BLENDED_SYNTHETIC",
    "BUGANG": "BLENDED_SYNTHETIC",
}

HUB_SOURCE_NOTE = {
    "BUSAN": "PNC 정보조회서비스 2026-08-09 Empty 현황 snapshot 의 점유율 shape 을 직접 사용. "
             "PNC 단일 터미널 시점자료이며 부산항 전체 재고나 전국 점유율이 아님.",
    "YAKMOK": "경부축 내륙거점. 부산권 prior 를 λ=0.85 로 혼합한 합성 profile. 실측값 아님.",
    "BUGANG": "경부/서남 두 축이 접속하는 중간거점. λ=0.55 혼합 합성 profile. 실측값 아님.",
    "UIWANG": "두 corridor 가 모두 접속하는 수도권 hub. λ=0.45 혼합 합성 profile. 실측값 아님.",
    "DONGSAN": "서남축 내륙거점. 광양권 prior 를 λ=0.15 로 혼합한 합성 profile. 실측값 아님.",
    "GWANGYANG": "KITL 광양 반출가능 공컨수량 2026-08-09 snapshot 의 점유율 shape 을 직접 사용. "
                 "데미지·홀딩·지정·선적·환적 제외 물량이며 yard stock 전체가 아님.",
}

# --------------------------------------------------------------------------
# 선사 역할 정의 (통합계획 §17)
#
#   선사는 자사 주력 항만/거점으로 공컨을 반입(return·sea inbound)하고,
#   자사 화주가 집중된 내륙 거점에서 픽업 수요가 발생한다.
#   따라서 (supply_base) 와 (demand_base) 가 서로 다른 거점일 때
#   선사 내부에서 구조적 재배치 수요가 발생한다.
#
#   이것이 AXIS 가 해결하려는 문제이며, 임의의 +N%p 가산이 아니라
#   역할 정의로부터 유도된다.
# --------------------------------------------------------------------------
#   CARRIER_F 는 계획서 §13 의 "Others" — 공개자료 상위 5사를 제외한 다수 소형선사의
#   풀(pool)이다. 여러 선사의 합이므로 단일한 supply/demand base 를 갖지 않는다.
#   따라서 role tilt 를 적용하지 않고 거점 prior 를 그대로 따른다.
#
#   주의(보수적 가정): 실제로는 다수의 소형선사이므로 각각은 열차 1편을 채울 수 없다.
#   이를 단일 carrier 로 묶으면 Carrier Separate 베이스라인이 실제보다 유리해지므로,
#   AXIS 통합효과를 과대평가하지 않는 방향(보수적)이다.
CARRIER_ROLE = {
    #             supply 우위      demand 우위     성격
    "CARRIER_A": ("BUSAN",        "YAKMOK"),     # 부산 반입 → 경부축 내륙 수요
    "CARRIER_B": ("UIWANG",       "BUGANG"),     # 수도권 반입 → 중부 수요
    "CARRIER_C": ("GWANGYANG",    "DONGSAN"),    # 광양 반입 → 서남축 내륙 수요
    "CARRIER_D": ("BUSAN",        "GWANGYANG"),  # 부산 반입 → 서남권 수요 (축 교차)
    "CARRIER_E": ("UIWANG",       "YAKMOK"),     # 수도권 반입 → 경부축 수요
    "CARRIER_F": (None,           None),         # Others pool — 구조적 편향 없음
}


@dataclass
class GenConfig:
    """데이터 생성 파라미터. 전량 metadata 에 기록된다."""
    random_seed: int = 20260810
    role_tilt: float = 1.10          # multinomial-logit tilt (exp(1.10) ≈ 3.0배 가중)
    block_hours: int = 6             # carrier share 변동 단위 (§18)
    ar1_rho: float = 0.75            # block 간 share 지속성 (1에 가까울수록 느리게 변동)
    ar1_sigma: float = 0.10          # block 충격 크기 (log-share 표준편차)
    source_week_start: str = "2025-05-05 00:00"
    target_week_start: str = "2026-08-10 00:00"
    horizon_hours: int = 168
    scenario: str = "AXIS_V7_1_2026-08-10"

    def as_rows(self) -> List[dict]:
        return [{"parameter": k, "value": v} for k, v in self.__dict__.items()]


# --------------------------------------------------------------------------
# 1. 공개자료 → PNC / KITL anchor prior
# --------------------------------------------------------------------------
def build_public_anchors(snapshot: pd.DataFrame) -> Tuple[Dict[str, np.ndarray], pd.DataFrame]:
    """
    공개 snapshot 에서 (source, size) 별 Top5 + Others 점유율 shape 을 만든다.

    선사 순번은 TEU 기준 순위로 정하여 20FT/40FT 간 동일 Virtual Carrier 가
    동일 순위를 갖도록 한다. 이 순번은 *shape* 만 의미하며 실선사 식별이 아니다.
    """
    anchors: Dict[str, np.ndarray] = {}
    audit_rows = []

    for source in ["PNC", "KITL"]:
        sub = snapshot[snapshot.source == source]
        # TEU 기준 순위 (20FT×1 + 40FT×2)
        teu = (
            sub.assign(teu=lambda d: d["count"] * d.container_size.map(TEU))
               .groupby("carrier_code").teu.sum()
               .sort_values(ascending=False)
        )
        top5 = list(teu.index[:5])

        for size in SIZES:
            s = sub[sub.container_size == size].set_index("carrier_code")["count"]
            counts = [float(s.get(code, 0.0)) for code in top5]
            others = float(s.sum() - sum(counts))
            vec = np.array(counts + [others], dtype=float)
            if vec.sum() <= 0:
                raise ValueError(f"empty snapshot for {source} {size}")
            vec = vec / vec.sum()
            anchors[(source, size)] = vec

            for i, (cid, share) in enumerate(zip(CARRIERS, vec)):
                audit_rows.append({
                    "source": source, "container_size": size, "virtual_carrier": cid,
                    "rank": i + 1 if i < 5 else "OTHERS",
                    "public_carrier_code": top5[i] if i < 5 else "OTHERS(pooled)",
                    "snapshot_count": counts[i] if i < 5 else others,
                    "anchor_share": round(float(share), 6),
                })

    return anchors, pd.DataFrame(audit_rows)


# --------------------------------------------------------------------------
# 2. 거점별 prior (λ 혼합)
# --------------------------------------------------------------------------
def build_hub_priors(anchors) -> Dict[Tuple[str, str], np.ndarray]:
    priors = {}
    for hub in HUBS:
        lam = HUB_LAMBDA[hub]
        for size in SIZES:
            vec = lam * anchors[("PNC", size)] + (1.0 - lam) * anchors[("KITL", size)]
            priors[(hub, size)] = vec / vec.sum()
    return priors


# --------------------------------------------------------------------------
# 3. 역할 tilt → demand share / supply share 분리
# --------------------------------------------------------------------------
def build_role_shares(priors, cfg: GenConfig):
    """
    multinomial-logit tilt:
        w[c,h] = P_hub[c] · exp(tilt · 1{h == base[c]})
        share  = w / Σ_c w

    demand 와 supply 가 서로 다른 base 를 쓰므로 구조적 비대칭이 발생한다.
    """
    d_share, s_share = {}, {}
    for hub in HUBS:
        for size in SIZES:
            p = priors[(hub, size)]
            wd = np.array([
                p[i] * np.exp(cfg.role_tilt if CARRIER_ROLE[c][1] == hub else 0.0)
                for i, c in enumerate(CARRIERS)
            ])
            ws = np.array([
                p[i] * np.exp(cfg.role_tilt if CARRIER_ROLE[c][0] == hub else 0.0)
                for i, c in enumerate(CARRIERS)
            ])
            d_share[(hub, size)] = wd / wd.sum()
            s_share[(hub, size)] = ws / ws.sum()
    return d_share, s_share


# --------------------------------------------------------------------------
# 4. 정수 배분 — Largest Remainder Method (§19)
# --------------------------------------------------------------------------
def largest_remainder(total: int, share: np.ndarray) -> np.ndarray:
    """Σ result == total 을 정확히 보장하는 단일시점 정수 배분 (초기재고용)."""
    if total <= 0:
        return np.zeros(len(share), dtype=int)
    raw = share * total
    base = np.floor(raw).astype(int)
    rem = total - base.sum()
    if rem > 0:
        order = np.argsort(-(raw - base))
        base[order[:rem]] += 1
    return base


class CarryAllocator:
    """
    시계열 정수 배분기 — Largest Remainder + 이월(carry-over).

    매시간 독립적으로 Largest Remainder 를 적용하면, 물량이 1~2 박스인 시점에서
    항상 share 가 가장 큰 선사가 가져가므로 소형 선사가 168시간 내내 0 을 받는
    구조적 배제가 발생한다. (v7 1차 생성에서 실측 확인: DONGSAN 에서 3개 선사가 0)

    따라서 "받아야 할 누적량(owed)" 을 유지하고 매 시점 owed 가 큰 선사부터
    1박스씩 배분한다.

    보장 사항
      - Σ alloc == total  (매 시점 정확한 총량 보존)
      - 누적 배분량이 누적 목표량을 추종 → 장기 share 가 설계 share 로 수렴
      - 소형 선사도 누적 owed 가 1 을 넘으면 반드시 배분받음
    """

    def __init__(self, n: int):
        self.owed = np.zeros(n, dtype=float)

    def allocate(self, total: int, share: np.ndarray) -> np.ndarray:
        alloc = np.zeros(len(share), dtype=int)
        if total <= 0:
            return alloc
        self.owed += share * float(total)
        for _ in range(int(total)):
            j = int(np.argmax(self.owed))
            alloc[j] += 1
            self.owed[j] -= 1.0
        return alloc


# --------------------------------------------------------------------------
# 5. 메인 생성 루틴
# --------------------------------------------------------------------------
def generate(master_path: Path, snapshot_path: Path, outdir: Path,
             cfg: GenConfig) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(cfg.random_seed)

    # ---- 5.1 Master Aggregate 로드 -------------------------------------
    xls = pd.ExcelFile(master_path)
    dem = xls.parse("HOURLY_DEMAND_WIDE")
    sup = xls.parse("HOURLY_SUPPLY_WIDE")
    inv = xls.parse("INITIAL_INVENTORY")
    dem["timestamp"] = pd.to_datetime(dem.timestamp)
    sup["timestamp"] = pd.to_datetime(sup.timestamp)

    src_week = pd.date_range(cfg.source_week_start, periods=cfg.horizon_hours, freq="h")
    tgt_week = pd.date_range(cfg.target_week_start, periods=cfg.horizon_hours, freq="h")

    dw = dem[dem.timestamp.isin(src_week)].sort_values("timestamp").reset_index(drop=True)
    sw = sup[sup.timestamp.isin(src_week)].sort_values("timestamp").reset_index(drop=True)
    if len(dw) != cfg.horizon_hours or len(sw) != cfg.horizon_hours:
        raise ValueError(f"source week incomplete: demand={len(dw)} supply={len(sw)}")

    # 초기재고 hub 코드 정규화 (master 는 UIWANG_ICD 형태)
    inv = inv.copy()
    inv["hub"] = inv.hub_code.str.replace(
        r"_(ICD|CY|NEW_PORT)$", "", regex=True)
    inv_map = {
        (r.hub, "20FT"): int(r.initial_20FT_boxes) for r in inv.itertuples()
    }
    inv_map.update({
        (r.hub, "40FT"): int(r.initial_40FT_boxes) for r in inv.itertuples()
    })
    for hub in HUBS:
        for size in SIZES:
            if (hub, size) not in inv_map:
                raise ValueError(f"master initial inventory missing: {hub} {size}")

    # ---- 5.2 prior / share 구성 ----------------------------------------
    snapshot = pd.read_csv(snapshot_path, encoding="utf-8-sig")
    anchors, anchor_audit = build_public_anchors(snapshot)
    priors = build_hub_priors(anchors)
    d_share, s_share = build_role_shares(priors, cfg)

    # ---- 5.3 6시간 block 별 carrier share 변동 (§18) ---------------------
    # 계획서 §18: 매시간 독립 random draw 금지. block 단위로 "천천히" 변동해야 한다.
    # 따라서 block 간 독립추출이 아니라 log-share 공간의 AR(1) 평균회귀 과정을 쓴다.
    #     z_b = (1-rho)·log(base) + rho·z_{b-1} + eps_b
    #     share_b = softmax(z_b)
    # rho 가 클수록 인접 block 간 변화가 작고, base 로 평균회귀하므로 장기 편향이 없다.
    n_block = int(np.ceil(cfg.horizon_hours / cfg.block_hours))

    def block_shares(base: np.ndarray) -> np.ndarray:
        """(n_block, n_carrier) — base 주변에서 천천히 변동하는 share 경로."""
        logb = np.log(np.maximum(base, 1e-9))
        z = logb.copy()
        out = np.empty((n_block, len(CARRIERS)))
        for b in range(n_block):
            z = (1.0 - cfg.ar1_rho) * logb + cfg.ar1_rho * z \
                + rng.normal(0.0, cfg.ar1_sigma, size=len(CARRIERS))
            w = np.exp(z - z.max())
            out[b] = w / w.sum()
        return out

    d_block = {key: block_shares(v) for key, v in d_share.items()}
    s_block = {key: block_shares(v) for key, v in s_share.items()}

    # ---- 5.4 시간별 정수 분해 -------------------------------------------
    plan_rows = []
    sfx = {"20FT": "20", "40FT": "40"}

    # (hub, size, flow) 별 이월 배분기. 시점 간 상태를 유지해야 하므로 루프 밖에서 생성.
    alloc_d = {(h, k): CarryAllocator(len(CARRIERS)) for h in HUBS for k in SIZES}
    alloc_ret = {(h, k): CarryAllocator(len(CARRIERS)) for h in HUBS for k in SIZES}
    alloc_sea = {(h, k): CarryAllocator(len(CARRIERS)) for h in HUBS for k in SIZES}

    for t in range(cfg.horizon_hours):
        blk = t // cfg.block_hours
        ts = tgt_week[t]
        src_ts = src_week[t]
        for hub in HUBS:
            for size in SIZES:
                agg_d = int(dw.loc[t, f"{hub}_{size}_BOX"])
                agg_ret = int(sw.loc[t, f"{hub}_RETURN{sfx[size]}"])
                agg_sea = int(sw.loc[t, f"{hub}_SEA{sfx[size]}"])

                a_d = alloc_d[(hub, size)].allocate(agg_d, d_block[(hub, size)][blk])
                a_ret = alloc_ret[(hub, size)].allocate(agg_ret, s_block[(hub, size)][blk])
                a_sea = alloc_sea[(hub, size)].allocate(agg_sea, s_block[(hub, size)][blk])

                for i, c in enumerate(CARRIERS):
                    plan_rows.append({
                        "scenario": cfg.scenario,
                        "carrier_id": c,
                        "timestamp": ts.strftime("%Y-%m-%d %H:%M"),
                        "source_pattern_timestamp": src_ts.strftime("%Y-%m-%d %H:%M"),
                        "hub_code": hub,
                        "hub_name": HUB_NAME[hub],
                        "container_size": size,
                        "demand": int(a_d[i]),
                        "supply_return": int(a_ret[i]),
                        "supply_sea_empty_inbound": int(a_sea[i]),
                        "supply_total": int(a_ret[i] + a_sea[i]),
                    })

    plan = pd.DataFrame(plan_rows)

    # ---- 5.5 초기재고 분해 ----------------------------------------------
    # 초기재고는 해당 거점에서의 공컨 반입·반납 활동에 비례하여 축적된다고 본다.
    # 따라서 supply-side share 를 사용한다 (섭동 없는 base share).
    inv_rows = []
    for hub in HUBS:
        for size in SIZES:
            alloc = largest_remainder(inv_map[(hub, size)], s_share[(hub, size)])
            for i, c in enumerate(CARRIERS):
                inv_rows.append({
                    "carrier_id": c, "hub_code": hub, "hub_name": HUB_NAME[hub],
                    "container_size": size, "initial_inventory": int(alloc[i]),
                })
    initial = pd.DataFrame(inv_rows)

    # ---- 5.6 metadata ----------------------------------------------------
    meta_rows = []
    for hub in HUBS:
        for size in SIZES:
            for i, c in enumerate(CARRIERS):
                meta_rows.append({
                    "carrier_id": c,
                    "hub_code": hub,
                    "hub_name": HUB_NAME[hub],
                    "container_size": size,
                    "base_prior_share": round(float(priors[(hub, size)][i]), 8),
                    "demand_share": round(float(d_share[(hub, size)][i]), 8),
                    "supply_share": round(float(s_share[(hub, size)][i]), 8),
                    "carrier_type": "OTHERS_POOL" if CARRIER_ROLE[c][0] is None else "MAJOR",
                    "supply_role_hub": CARRIER_ROLE[c][0] or "NONE",
                    "demand_role_hub": CARRIER_ROLE[c][1] or "NONE",
                    "is_supply_base": CARRIER_ROLE[c][0] == hub,
                    "is_demand_base": CARRIER_ROLE[c][1] == hub,
                    "source_type": HUB_SOURCE_TYPE[hub],
                    "source_note": HUB_SOURCE_NOTE[hub],
                    "lambda_value": HUB_LAMBDA[hub],
                    "role_tilt": cfg.role_tilt,
                    "random_seed": cfg.random_seed,
                })
    metadata = pd.DataFrame(meta_rows)

    # ---- 5.7 총량 보존 검증 (§21-1~3) ------------------------------------
    checks = []

    def add_check(name, ok, detail=""):
        checks.append({"check": name, "pass": bool(ok), "detail": str(detail)})

    # (timestamp × hub × size) 단위 정확 일치
    gd = plan.groupby(["timestamp", "hub_code", "container_size"]).agg(
        demand=("demand", "sum"),
        supply_return=("supply_return", "sum"),
        supply_sea=("supply_sea_empty_inbound", "sum"),
        supply_total=("supply_total", "sum"),
    ).reset_index()

    ref_rows = []
    for t in range(cfg.horizon_hours):
        ts = tgt_week[t].strftime("%Y-%m-%d %H:%M")
        for hub in HUBS:
            for size in SIZES:
                ref_rows.append({
                    "timestamp": ts, "hub_code": hub, "container_size": size,
                    "ref_demand": int(dw.loc[t, f"{hub}_{size}_BOX"]),
                    "ref_return": int(sw.loc[t, f"{hub}_RETURN{sfx[size]}"]),
                    "ref_sea": int(sw.loc[t, f"{hub}_SEA{sfx[size]}"]),
                })
    ref = pd.DataFrame(ref_rows)
    m = gd.merge(ref, on=["timestamp", "hub_code", "container_size"], how="outer")

    m["err_demand"] = m.demand - m.ref_demand
    m["err_return"] = m.supply_return - m.ref_return
    m["err_sea"] = m.supply_sea - m.ref_sea
    m["err_supply_total"] = m.supply_total - (m.ref_return + m.ref_sea)

    for col, label in [("err_demand", "aggregate_demand_preservation"),
                       ("err_return", "aggregate_supply_return_preservation"),
                       ("err_sea", "aggregate_supply_sea_preservation"),
                       ("err_supply_total", "aggregate_supply_total_preservation")]:
        bad = int((m[col] != 0).sum())
        add_check(label, bad == 0, f"mismatch_rows={bad}/{len(m)}")

    inv_chk = initial.groupby(["hub_code", "container_size"]).initial_inventory.sum()
    inv_bad = [(h, s, int(inv_chk.get((h, s), 0)), inv_map[(h, s)])
               for h in HUBS for s in SIZES
               if int(inv_chk.get((h, s), 0)) != inv_map[(h, s)]]
    add_check("aggregate_initial_inventory_preservation", not inv_bad, inv_bad)

    add_check("all_values_integer",
              bool((plan.demand % 1 == 0).all() and (plan.supply_total % 1 == 0).all()), "")
    add_check("no_negative_values",
              bool((plan.demand >= 0).all() and (plan.supply_total >= 0).all()
                   and (initial.initial_inventory >= 0).all()), "")
    add_check("horizon_168_hours", plan.timestamp.nunique() == cfg.horizon_hours,
              plan.timestamp.nunique())
    add_check("six_hubs", plan.hub_code.nunique() == 6, plan.hub_code.nunique())
    add_check("both_sizes", plan.container_size.nunique() == 2, plan.container_size.nunique())
    add_check("row_count",
              len(plan) == len(CARRIERS) * cfg.horizon_hours * 6 * 2, len(plan))

    # 6개 거점 prior 상이성 (§14)
    distinct = {tuple(np.round(priors[(h, "20FT")], 10)) for h in HUBS}
    add_check("six_hubs_distinct_prior", len(distinct) == 6, f"{len(distinct)}/6")

    # demand/supply share 구조적 비대칭 (§16, §17)
    gaps = []
    for hub in HUBS:
        for size in SIZES:
            gaps.append(float(np.abs(d_share[(hub, size)] - s_share[(hub, size)]).max()))
    add_check("demand_supply_structural_asymmetry", min(gaps) > 0.05,
              f"min_max_gap={min(gaps):.4f} mean={np.mean(gaps):.4f}")

    # carrier 과집중 여부 (§21-10)
    conc = plan.groupby("carrier_id").demand.sum()
    conc = conc / conc.sum()
    add_check("no_carrier_over_concentration", conc.max() < 0.5,
              f"max_share={conc.max():.4f}")

    # 시간적 연속성 (§18) — 설계 share 경로 기준.
    # 실현 count 기준 share 는 물량이 0~2박스인 block 에서 0/1 로 튀므로
    # 생성기의 설계 share 경로에서 인접 block 변동을 측정한다.
    step_max, step_mean = 0.0, []
    for paths in list(d_block.values()) + list(s_block.values()):
        if len(paths) < 2:
            continue
        step = np.abs(np.diff(paths, axis=0))
        step_max = max(step_max, float(step.max()))
        step_mean.append(float(step.mean()))
    add_check("temporal_continuity_block_share", step_max < 0.15,
              f"max_adjacent_block_change={step_max:.4f} mean={np.mean(step_mean):.4f} "
              f"(rho={cfg.ar1_rho}, sigma={cfg.ar1_sigma})")

    # 실현 share 가 설계 share 를 추종하는지 (이월 배분기 정상동작 확인).
    # 물량이 있는 (hub,size) 에서 설계 share 가 유의미한데 실현이 0 이면 구조적 배제.
    realized_dev, excluded = [], []
    for hub in HUBS:
        for size in SIZES:
            sub = plan[(plan.hub_code == hub) & (plan.container_size == size)]
            for flow, col, design in [("demand", "demand", d_share),
                                      ("supply", "supply_total", s_share)]:
                tot = sub[col].sum()
                if tot < len(CARRIERS):      # 표본이 너무 작으면 share 비교 무의미
                    continue
                got = sub.groupby("carrier_id")[col].sum().reindex(CARRIERS).fillna(0)
                rs = (got / tot).to_numpy()
                ds = design[(hub, size)]
                realized_dev.append(float(np.abs(rs - ds).max()))
                for i, c in enumerate(CARRIERS):
                    # 기대 배분량이 1박스 미만이면 0 이 나오는 것이 정상이다.
                    # (예: DONGSAN 40FT 주간 9박스 × share 4.6% = 0.41박스)
                    # 1박스 이상 받아야 하는데 0 인 경우만 구조적 배제로 본다.
                    if ds[i] * tot >= 1.0 and rs[i] == 0.0:
                        excluded.append(
                            f"{hub}/{size}/{flow}/{c} design={ds[i]:.3f} "
                            f"expected={ds[i]*tot:.1f}box realized=0")
    add_check("no_structural_carrier_exclusion", not excluded, excluded[:5])
    add_check("realized_share_tracks_design",
              bool(realized_dev) and max(realized_dev) < 0.10,
              f"max_deviation={max(realized_dev):.4f}" if realized_dev else "no sample")

    # 시간적 연속성 보조: block 경로가 base 로 평균회귀하는지 (장기 편향 없음)
    drift = []
    for key, paths in d_block.items():
        drift.append(float(np.abs(paths.mean(axis=0) - d_share[key]).max()))
    for key, paths in s_block.items():
        drift.append(float(np.abs(paths.mean(axis=0) - s_share[key]).max()))
    add_check("block_share_mean_reversion", max(drift) < 0.06,
              f"max_drift_from_base={max(drift):.4f}")

    checks_df = pd.DataFrame(checks)

    # ---- 5.8 출력 --------------------------------------------------------
    plan.to_csv(outdir / "AXIS_carrier_hourly_plan_v7_1.csv", index=False, encoding="utf-8-sig")
    initial.to_csv(outdir / "carrier_initial_inventory.csv", index=False, encoding="utf-8-sig")
    metadata.to_csv(outdir / "carrier_profile_metadata.csv", index=False, encoding="utf-8-sig")
    anchor_audit.to_csv(outdir / "PUBLIC_SNAPSHOT_ANCHOR.csv", index=False, encoding="utf-8-sig")
    checks_df.to_csv(outdir / "AGGREGATE_PRESERVATION_CHECK.csv", index=False, encoding="utf-8-sig")

    audit = pd.DataFrame(cfg.as_rows() + [
        {"parameter": "carriers", "value": "|".join(CARRIERS)},
        {"parameter": "hub_lambda", "value": json.dumps(HUB_LAMBDA)},
        {"parameter": "carrier_role", "value": json.dumps(
            {k: {"supply_base": v[0], "demand_base": v[1]} for k, v in CARRIER_ROLE.items()},
            ensure_ascii=False)},
        {"parameter": "generation_rule",
         "value": "share = normalize(P_hub * exp(role_tilt * 1{hub==base})); "
                  "log-share AR(1) mean-reverting path per 6h block "
                  "(z_b = (1-rho)*log(base) + rho*z_{b-1} + N(0,sigma)); "
                  "Largest Remainder integer split per (timestamp,hub,size)"},
        {"parameter": "master_file", "value": master_path.name},
        {"parameter": "snapshot_file", "value": snapshot_path.name},
    ])
    audit.to_csv(outdir / "DATA_GENERATION_AUDIT.csv", index=False, encoding="utf-8-sig")

    passed = int(checks_df["pass"].sum())
    return {
        "checks_passed": passed,
        "checks_total": len(checks_df),
        "all_pass": bool(checks_df["pass"].all()),
        "failed": checks_df[~checks_df["pass"]].to_dict("records"),
        "plan": plan, "initial": initial, "metadata": metadata,
        "d_share": d_share, "s_share": s_share, "priors": priors,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--seed", type=int, default=20260810)
    ap.add_argument("--role-tilt", type=float, default=1.10)
    ap.add_argument("--rho", type=float, default=0.75)
    ap.add_argument("--sigma", type=float, default=0.10)
    a = ap.parse_args()

    cfg = GenConfig(random_seed=a.seed, role_tilt=a.role_tilt,
                    ar1_rho=a.rho, ar1_sigma=a.sigma)
    res = generate(Path(a.master), Path(a.snapshot), Path(a.outdir), cfg)

    print(f"aggregate/structure checks: {res['checks_passed']}/{res['checks_total']}")
    if not res["all_pass"]:
        for f in res["failed"]:
            print("  FAIL:", f["check"], f["detail"])
        raise SystemExit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
