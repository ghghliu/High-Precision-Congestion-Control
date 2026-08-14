#!/usr/bin/env python3
"""Analyze 400G 2-tier fat-tree benches (pair2 / HoL / incast)."""
from __future__ import annotations

import argparse
import os
from collections import defaultdict
from typing import Dict, List, Tuple

CC_FILE = {
    "pfc": "pfc",
    "dcqcn": "dcqcn",
    "timely": "timely",
    "hp": "hp95",
    "hp95": "hp95",
}


def load_fct(path: str) -> List[dict]:
    rows = []
    if not os.path.exists(path):
        print("  missing %s" % path)
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


def pct(xs: List[float], p: float) -> float:
    if not xs:
        return 0.0
    ys = sorted(xs)
    i = int(round(p * (len(ys) - 1)))
    return ys[i]


def summarize(rows: List[dict], label: str) -> None:
    if not rows:
        print("  [%s] no flows completed" % label)
        return
    fcts = [r["fct_ns"] for r in rows]
    slows = [r["fct_ns"] / max(r["standalone_ns"], 1) for r in rows]
    gps = [r["size"] * 8.0 / (r["fct_ns"] * 1e-9) / 1e9 for r in rows if r["fct_ns"] > 0]
    print(
        "  [%s] n=%d fct_us(min/med/max)=%.1f/%.1f/%.1f "
        "slowdown(med/p95)=%.2f/%.2f avg_goodput_Gbps=%.2f"
        % (
            label,
            len(rows),
            min(fcts) / 1e3,
            pct(fcts, 0.5) / 1e3,
            max(fcts) / 1e3,
            pct(slows, 0.5),
            pct(slows, 0.95),
            sum(gps) / len(gps) if gps else 0.0,
        )
    )


def paths(mix: str, topo: str, trace: str, cc: str) -> Tuple[str, str]:
    tag = CC_FILE.get(cc, cc)
    fct = os.path.join(mix, "fct_%s_%s_%s.txt" % (topo, trace, tag))
    pfc = os.path.join(mix, "pfc_%s_%s_%s.txt" % (topo, trace, tag))
    return fct, pfc


def cohort_util(rows: List[dict], link_gbps: float = 400.0) -> None:
    if not rows:
        return
    start = min(r["start_ns"] for r in rows)
    end = max(r["start_ns"] + r["fct_ns"] for r in rows)
    total_b = sum(r["size"] for r in rows)
    makespan = max(end - start, 1)
    agg = total_b * 8.0 / makespan
    print(
        "  cohort makespan_us=%.1f agg_goodput_Gbps=%.2f (%.0f%% of %.0fG dest)"
        % (makespan / 1e3, agg, 100.0 * agg / link_gbps, link_gbps)
    )


def analyze_pair2(mix: str, topo: str, ccs: List[str]) -> None:
    print("=== pair2: two disjoint 20MB elephants (routing / 1:1 sanity) ===")
    for cc in ccs:
        fct, pfc = paths(mix, topo, "ft_pair2_flow", cc)
        rows = load_fct(fct)
        print("\n-- %s --" % cc)
        summarize(rows, "both")
        ps = pfc_stats(load_pfc(pfc))
        print("  PFC pause=%d by_node=%s" % (ps["pause_events"], ps["pause_by_node"]))
        for r in rows:
            gp = r["size"] * 8.0 / max(r["fct_ns"], 1) / 1e-9 / 1e9
            print(
                "  dport=%d slowdown=%.2fx goodput=%.1fGbps fct_us=%.1f"
                % (r["dport"], r["fct_ns"] / max(r["standalone_ns"], 1), gp, r["fct_ns"] / 1e3)
            )


def analyze_hol(mix: str, topo: str, ccs: List[str]) -> None:
    print("\n=== hol: 16:1 incast + innocent victim on same dest leaf ===")
    for cc in ccs:
        fct, pfc = paths(mix, topo, "ft_hol_flow", cc)
        rows = load_fct(fct)
        print("\n-- %s --" % cc)
        victim = [r for r in rows if r["dport"] == 100]
        incast = [r for r in rows if r["dport"] != 100]
        summarize(victim, "victim")
        summarize(incast, "incast")
        ps = pfc_stats(load_pfc(pfc))
        print("  PFC pause=%d by_node=%s" % (ps["pause_events"], ps["pause_by_node"]))
        if victim:
            v = victim[0]
            print(
                "  victim slowdown=%.2fx fct_us=%.1f standalone_us=%.1f"
                % (v["fct_ns"] / max(v["standalone_ns"], 1), v["fct_ns"] / 1e3, v["standalone_ns"] / 1e3)
            )
        cohort_util(incast)


def analyze_incast(mix: str, topo: str, trace: str, n: int, ccs: List[str]) -> None:
    print("\n=== incast%d: many-to-one onto one 400G dest (convergence) ===" % n)
    for cc in ccs:
        fct, pfc = paths(mix, topo, trace, cc)
        rows = load_fct(fct)
        print("\n-- %s --" % cc)
        summarize(rows, "incast")
        ps = pfc_stats(load_pfc(pfc))
        print("  PFC pause=%d by_node=%s" % (ps["pause_events"], ps["pause_by_node"]))
        cohort_util(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mix", default="../simulation/mix")
    ap.add_argument("--topo", default="ft2_4l2s")
    ap.add_argument("--ccs", default="pfc,dcqcn,hp,timely")
    args = ap.parse_args()
    ccs = [c.strip() for c in args.ccs.split(",") if c.strip()]
    analyze_pair2(args.mix, args.topo, ccs)
    analyze_hol(args.mix, args.topo, ccs)
    analyze_incast(args.mix, args.topo, "ft_incast8_flow", 8, ccs)
    analyze_incast(args.mix, args.topo, "ft_incast16_flow", 16, ccs)


if __name__ == "__main__":
    main()
