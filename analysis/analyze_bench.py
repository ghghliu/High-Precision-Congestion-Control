#!/usr/bin/env python3
"""Summarize PFC vs DCQCN microbenchmark outputs (HoL + small-flow)."""
from __future__ import annotations

import argparse
import os
from collections import defaultdict
from typing import Dict, List, Tuple


def load_fct(path: str) -> List[dict]:
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) < 8:
                continue
            rows.append(
                {
                    "sip": p[0],
                    "dip": p[1],
                    "sport": int(p[2]),
                    "dport": int(p[3]),
                    "size": int(p[4]),
                    "start_ns": int(p[5]),
                    "fct_ns": int(p[6]),
                    "standalone_ns": int(p[7]),
                }
            )
    return rows


def load_pfc(path: str) -> List[Tuple[int, int, int, int, int]]:
    """Return (t_ns, node, node_type, ifindex, type) where type 1=pause, 0=resume."""
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) < 5:
                continue
            rows.append(tuple(int(x) for x in p[:5]))
    return rows


def pfc_stats(rows) -> dict:
    pauses = [r for r in rows if r[4] == 1]
    resumes = [r for r in rows if r[4] == 0]
    by_node: Dict[int, int] = defaultdict(int)
    for r in pauses:
        by_node[r[1]] += 1
    return {
        "pause_events": len(pauses),
        "resume_events": len(resumes),
        "pause_by_node": dict(sorted(by_node.items())),
    }


def summarize_flows(rows: List[dict], label: str) -> None:
    if not rows:
        print(f"  [{label}] no flows completed")
        return
    fcts = sorted(r["fct_ns"] for r in rows)
    slows = sorted(r["fct_ns"] / max(r["standalone_ns"], 1) for r in rows)
    goodputs = []
    for r in rows:
        if r["fct_ns"] > 0:
            # bits/s
            goodputs.append(r["size"] * 8.0 / (r["fct_ns"] * 1e-9))
    avg_gp = sum(goodputs) / len(goodputs) if goodputs else 0.0
    print(
        f"  [{label}] n={len(rows)} "
        f"fct_ns(min/med/max)={fcts[0]}/{fcts[len(fcts)//2]}/{fcts[-1]} "
        f"slowdown(med/p95)={slows[len(slows)//2]:.2f}/{slows[int(0.95*(len(slows)-1))]:.2f} "
        f"avg_goodput_Gbps={avg_gp/1e9:.2f}"
    )


def analyze_hol(mix_dir: str, ccs: List[str]) -> None:
    print("=== B1 HoL (shared fabric link pause blocks victim) ===")
    for cc in ccs:
        fct = load_fct(os.path.join(mix_dir, f"fct_bench_hol_bench_hol_flow_{cc}.txt"))
        pfc = load_pfc(os.path.join(mix_dir, f"pfc_bench_hol_bench_hol_flow_{cc}.txt"))
        print(f"\n-- {cc} --")
        victim = [r for r in fct if r["dport"] == 100]
        congest = [r for r in fct if r["dport"] != 100]
        summarize_flows(victim, "victim 0->3")
        summarize_flows(congest, "incast ->4")
        ps = pfc_stats(pfc)
        print(
            f"  PFC pause={ps['pause_events']} resume={ps['resume_events']} "
            f"by_node={ps['pause_by_node']}"
        )
        if victim and victim[0]["standalone_ns"] > 0:
            v = victim[0]
            print(
                f"  victim slowdown={v['fct_ns']/v['standalone_ns']:.2f}x "
                f"(fct={v['fct_ns']}ns standalone={v['standalone_ns']}ns)"
            )


def analyze_sf(mix_dir: str, ccs: List[str]) -> None:
    print("\n=== B2 Small-flow (elephant + late short flows) ===")
    for cc in ccs:
        fct = load_fct(os.path.join(mix_dir, f"fct_bench_sf_bench_sf_flow_{cc}.txt"))
        pfc = load_pfc(os.path.join(mix_dir, f"pfc_bench_sf_bench_sf_flow_{cc}.txt"))
        print(f"\n-- {cc} --")
        elephant = [r for r in fct if r["size"] >= 1_000_000]
        small = [r for r in fct if r["size"] < 1_000_000]
        summarize_flows(elephant, "elephant")
        summarize_flows(small, "small")
        ps = pfc_stats(pfc)
        print(
            f"  PFC pause={ps['pause_events']} resume={ps['resume_events']} "
            f"by_node={ps['pause_by_node']}"
        )
        if small:
            # Ideal 100KB @ 400G ~= 2us + RTT; report how far we are from standalone
            avg_slow = sum(r["fct_ns"] / max(r["standalone_ns"], 1) for r in small) / len(small)
            print(f"  small-flow avg slowdown vs standalone={avg_slow:.2f}x")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mix", default="../simulation/mix")
    ap.add_argument("--ccs", default="pfc,dcqcn")
    args = ap.parse_args()
    ccs = [c.strip() for c in args.ccs.split(",") if c.strip()]
    analyze_hol(args.mix, ccs)
    analyze_sf(args.mix, ccs)


if __name__ == "__main__":
    main()
