#!/usr/bin/env python3
"""Analyze mouse-joining-incast probe sweep: FCT, slowdown, PFC, CC rate."""
from __future__ import annotations

import argparse
import os
from typing import Dict, List, Tuple

CC_FILE = {
    "pfc": "pfc",
    "dcqcn": "dcqcn",
    "timely": "timely",
    "hp": "hp95",
    "hp95": "hp95",
}

PROBE_TAGS = [
    ("32k", 32000, "sub_rtt"),
    ("64k", 64000, "sub_rtt"),
    ("128k", 128000, "near_rtt"),
    ("400k", 400000, "one_bdp"),
    ("1m", 1000000, "few_rtt"),
    ("2m", 2000000, "few_rtt"),
    ("5m", 5000000, "mid"),
    ("20m", 20000000, "large"),
]


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


def load_rate(path: str) -> List[dict]:
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for line in f:
            p = line.split()
            if len(p) < 7:
                continue
            rows.append(
                {
                    "t_ns": int(p[0]),
                    "dport": int(p[4]),
                    "rate_bps": int(p[5]),
                    "why": p[6],
                }
            )
    return rows


def rate_stats(events: List[dict], t0: int, t1: int) -> dict:
    xs = [e for e in events if t0 <= e["t_ns"] <= t1]
    if not xs:
        return {
            "n": 0,
            "start_g": 0.0,
            "min_g": 0.0,
            "end_g": 0.0,
            "first_cut_us": None,
            "series": [],
        }
    rates = [e["rate_bps"] / 1e9 for e in xs]
    start = rates[0]
    first_cut = None
    for e in xs:
        if e["rate_bps"] < 0.9 * xs[0]["rate_bps"] and e["why"] != "start":
            first_cut = (e["t_ns"] - t0) / 1e3
            break
    series = []
    last_g = None
    for e in xs:
        g = e["rate_bps"] / 1e9
        if last_g is None or abs(g - last_g) >= 1.0 or e["why"] in ("start", "done"):
            series.append((round((e["t_ns"] - t0) / 1e3, 1), round(g, 1), e["why"]))
            last_g = g
    return {
        "n": len(xs),
        "start_g": start,
        "min_g": min(rates),
        "end_g": rates[-1],
        "first_cut_us": first_cut,
        "series": series[:24],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mix", default="../simulation/mix")
    ap.add_argument("--topo", default="ft2_4l2s")
    ap.add_argument("--ccs", default="pfc,dcqcn,hp,timely")
    args = ap.parse_args()
    ccs = [c.strip() for c in args.ccs.split(",") if c.strip()]
    fair_g = 400.0 / 9.0  # 8 incast + 1 probe

    print(
        "size  regime    cc      fct_us  slow  gp_G  vs_fair  pfc  "
        "rate0  rate_min  rate_end  n_ev  cut_us"
    )
    rows_out = []
    for tag, size, regime in PROBE_TAGS:
        for cc in ccs:
            cctag = CC_FILE.get(cc, cc)
            prefix = "%s_%s_ft_probe_%s_flow_%s" % (args.mix, args.topo, tag, cctag)
            # files are mix/fct_topo_trace_cc.txt
            fct_p = os.path.join(
                args.mix, "fct_%s_ft_probe_%s_flow_%s.txt" % (args.topo, tag, cctag)
            )
            pfc_p = os.path.join(
                args.mix, "pfc_%s_ft_probe_%s_flow_%s.txt" % (args.topo, tag, cctag)
            )
            rate_p = os.path.join(
                args.mix, "rate_%s_ft_probe_%s_flow_%s.txt" % (args.topo, tag, cctag)
            )
            fct = [r for r in load_fct(fct_p) if r["dport"] == 100]
            if not fct:
                print("%-5s %-9s %-7s  MISSING %s" % (tag, regime, cc, fct_p))
                continue
            r = fct[0]
            gp = r["size"] * 8.0 / max(r["fct_ns"], 1) / 1e-9 / 1e9
            slow = r["fct_ns"] / max(r["standalone_ns"], 1)
            t0, t1 = r["start_ns"], r["start_ns"] + r["fct_ns"]
            pfc_n = sum(1 for e in load_pfc(pfc_p) if e[4] == 1 and t0 <= e[0] <= t1)
            rs = rate_stats([e for e in load_rate(rate_p) if e["dport"] == 100], t0, t1)
            cut = "-" if rs["first_cut_us"] is None else "%.1f" % rs["first_cut_us"]
            line = (
                "%-5s %-9s %-7s %7.1f %5.2f %5.1f %7.2f %4d  "
                "%5.1f %8.1f %8.1f %4d %s"
                % (
                    tag,
                    regime,
                    cc,
                    r["fct_ns"] / 1e3,
                    slow,
                    gp,
                    gp / fair_g,
                    pfc_n,
                    rs["start_g"],
                    rs["min_g"],
                    rs["end_g"],
                    rs["n"],
                    cut,
                )
            )
            print(line)
            rows_out.append((tag, regime, cc, r, gp, slow, pfc_n, rs))

    print("\n=== probe rate series (dport=100, t relative to start, Gbps) ===")
    for tag, regime, cc, r, gp, slow, pfc_n, rs in rows_out:
        if cc not in ("dcqcn", "hp", "pfc") or tag not in ("32k", "400k", "1m", "5m", "20m"):
            continue
        print("\n-- %s %s --" % (tag, cc))
        if not rs["series"]:
            print("  (no rate events; PFC has no per-QP rate)")
            continue
        for t_us, g, why in rs["series"]:
            print("  t=+%7.1fus  %7.1fG  %s" % (t_us, g, why))


if __name__ == "__main__":
    main()
