"""
AXIS v7.1 — Synthetic role_tilt downstream sensitivity  (지시서 §17)

`role_tilt` 는 synthetic carrier 의 거점별 수급 비대칭을 만드는 scenario parameter 다.
실측치가 아니다.

이 스크립트는 tilt 값을 바꿔 **데이터를 다시 생성한 뒤 최종 결과까지 내려가며**
AXIS 통합효과가 이 값에 얼마나 의존하는지 측정한다.

목적:
    "Synthetic 불균형을 임의로 크게 만들어서 AXIS 효과를 만든 것 아닌가?"
    라는 질문에 데이터로 답하기 위함이다.
"""
from __future__ import annotations

import argparse
import shutil
import tempfile
from pathlib import Path

import axis_data_gen_v7_1 as gen
import axis_milp_v7_1 as m
import axis_baselines_v7_1 as bl


def run_one(tilt, master, snapshot, params, min_lf, max_earliness,
            time_limit, mip_gap, workdir: Path, candidates: Path | None = None):
    out = {"role_tilt": tilt}
    data_dir = workdir / f"t{tilt}"
    cfg = gen.GenConfig(role_tilt=tilt)
    res = gen.generate(master, snapshot, data_dir, cfg)
    out["data_checks_pass"] = bool(res["all_pass"])

    hourly = data_dir / "AXIS_carrier_hourly_plan_v7_1.csv"
    initial = data_dir / "carrier_initial_inventory.csv"
    m.validate_carrier_inputs(hourly, initial)

    b = bl.run_baselines(hourly, initial, workdir / f"bl{tilt}", min_lf,
                         max_earliness, time_limit, mip_gap, None, params, candidates, True)
    A, B, C = b["scenarios"]["A"], b["scenarios"]["B"], b["scenarios"]["C"]
    out.update({
        "service_need_teu": b["total_service_need_teu"],
        "service_need_count": b["total_service_need_count"],
        "separate_rail_served_teu": B["rail_served_teu"],
        "separate_train_count": B["train_count"],
        "separate_teu_km": B["teu_km"],
        "integrated_rail_served_teu": C["rail_served_teu"],
        "integrated_train_count": C["train_count"],
        "integrated_load_factor": C["avg_distance_weighted_load_factor"],
        "integrated_avg_carriers_per_train": C["avg_carriers_per_train"],
        "integrated_train_km": C["train_km"],
        "integrated_wagon_km": C["wagon_km"],
        "integrated_teu_km": C["teu_km"],
        "no_repositioning_unserved_teu": A["rail_unserved_teu"],
        "integration_gain_teu": C["rail_served_teu"] - B["rail_served_teu"],
        "integration_gain_ratio": (round(C["rail_served_teu"] / B["rail_served_teu"], 3)
                                   if B["rail_served_teu"] else None),
    })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", required=True)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--params", default=None)
    ap.add_argument("--candidates", default=None)
    ap.add_argument("--out", required=True, help="output CSV path")
    ap.add_argument("--tilts", default="0.55,1.10,1.65")
    ap.add_argument("--min-load-factor", type=float, default=0.5)
    ap.add_argument("--max-earliness", type=float, default=72.0)
    ap.add_argument("--time-limit", type=float, default=900)
    ap.add_argument("--mip-gap", type=float, default=0.001)
    a = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="axis_tilt_"))
    rows = []
    try:
        for t in [float(x) for x in a.tilts.split(",")]:
            print("running role_tilt =", t, flush=True)
            rows.append(run_one(t, Path(a.master), Path(a.snapshot),
                                Path(a.params) if a.params else None,
                                a.min_load_factor, a.max_earliness,
                                a.time_limit, a.mip_gap, tmp,
                                Path(a.candidates) if a.candidates else None))
            m.write_csv(Path(a.out), rows)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("ROLE_TILT_SENSITIVITY_DONE")


if __name__ == "__main__":
    main()
