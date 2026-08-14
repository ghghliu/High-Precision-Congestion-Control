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
            "mean_g": 0.0,
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
    # Step-function time-weighted mean over the probe lifetime.
    acc = 0.0
    for i, e in enumerate(xs):
        ta = max(e["t_ns"], t0)
        tb = xs[i + 1]["t_ns"] if i + 1 < len(xs) else t1
        acc += e["rate_bps"] * max(0, tb - ta)
    dur = max(t1 - t0, 1)
    mean_g = acc / dur / 1e9
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
        "mean_g": mean_g,
        "first_cut_us": first_cut,
        "series": series[:32],
    }


def write_slowdown_svg(path: str, rows_out, ccs: List[str]) -> None:
    """Slowdown vs probe size, one polyline per CC. No extra deps."""
    colors = {"pfc": "#1f77b4", "dcqcn": "#d62728", "hp": "#2ca02c", "timely": "#ff7f0e"}
    tags = [t for t, _, _ in PROBE_TAGS]
    by_cc = {cc: {} for cc in ccs}
    for tag, _regime, cc, _r, _gp, slow, _pfc_n, _rs in rows_out:
        by_cc.setdefault(cc, {})[tag] = slow
    if not any(by_cc[c] for c in ccs if c in by_cc):
        return
    W, H, pad_l, pad_r, pad_t, pad_b = 720, 320, 56, 24, 28, 48
    plot_w, plot_h = W - pad_l - pad_r, H - pad_t - pad_b
    ymax = 1.0
    for cc in ccs:
        for v in by_cc.get(cc, {}).values():
            ymax = max(ymax, v)
    ymax = max(2.0, ymax * 1.15)

    def x_at(i: int) -> float:
        n = max(len(tags) - 1, 1)
        return pad_l + plot_w * i / n

    def y_at(v: float) -> float:
        return pad_t + plot_h * (1.0 - v / ymax)

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
        'viewBox="0 0 %d %d" font-family="sans-serif">' % (W, H, W, H),
        '<rect width="%d" height="%d" fill="#fff"/>' % (W, H),
        '<text x="%d" y="18" font-size="13">Probe slowdown vs size '
        "(vs empty-network FCT)</text>" % pad_l,
        '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#333"/>'
        % (pad_l, pad_t, pad_l, pad_t + plot_h),
        '<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#333"/>'
        % (pad_l, pad_t + plot_h, pad_l + plot_w, pad_t + plot_h),
    ]
    for tick in (1.0, ymax / 2, ymax):
        y = y_at(tick)
        parts.append(
            '<line x1="%d" y1="%.1f" x2="%d" y2="%.1f" stroke="#eee"/>'
            % (pad_l, y, pad_l + plot_w, y)
        )
        parts.append(
            '<text x="%d" y="%.1f" font-size="10" text-anchor="end">%.1fx</text>'
            % (pad_l - 6, y + 3, tick)
        )
    for i, tag in enumerate(tags):
        parts.append(
            '<text x="%.1f" y="%d" font-size="10" text-anchor="middle">%s</text>'
            % (x_at(i), pad_t + plot_h + 16, tag)
        )
    legend_x = pad_l + 8
    legend_y = pad_t + 8
    for cc in ccs:
        pts = []
        for i, tag in enumerate(tags):
            if tag in by_cc.get(cc, {}):
                pts.append("%.1f,%.1f" % (x_at(i), y_at(by_cc[cc][tag])))
        if len(pts) < 2:
            continue
        col = colors.get(cc, "#555")
        parts.append(
            '<polyline fill="none" stroke="%s" stroke-width="2" points="%s"/>'
            % (col, " ".join(pts))
        )
        for i, tag in enumerate(tags):
            if tag in by_cc.get(cc, {}):
                parts.append(
                    '<circle cx="%.1f" cy="%.1f" r="3" fill="%s"/>'
                    % (x_at(i), y_at(by_cc[cc][tag]), col)
                )
        parts.append(
            '<rect x="%d" y="%d" width="10" height="10" fill="%s"/>'
            % (legend_x, legend_y, col)
        )
        parts.append(
            '<text x="%d" y="%d" font-size="11">%s</text>'
            % (legend_x + 14, legend_y + 9, cc)
        )
        legend_x += 90
    parts.append("</svg>\n")
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write("".join(parts))


def write_markdown(path: str, rows_out, fair_g: float) -> None:
    lines = [
        "| size | regime | cc | fct_us | slowdown | goodput_G | vs_fair | pfc | "
        "rate0 | rate_min | rate_mean | rate_end | cut_us |",
        "|------|--------|----|--------|----------|-----------|---------|-----|"
        "-------|----------|-----------|----------|--------|",
    ]
    for tag, regime, cc, r, gp, slow, pfc_n, rs in rows_out:
        cut = "-" if rs["first_cut_us"] is None else "%.1f" % rs["first_cut_us"]
        lines.append(
            "| %s | %s | %s | %.1f | %.2f | %.1f | %.2f | %d | "
            "%.1f | %.1f | %.1f | %.1f | %s |"
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
                rs["mean_g"],
                rs["end_g"],
                cut,
            )
        )
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mix", default="../simulation/mix")
    ap.add_argument("--topo", default="ft2_4l2s")
    ap.add_argument("--ccs", default="pfc,dcqcn,hp,timely")
    ap.add_argument("--out-md", default="")
    ap.add_argument("--out-svg", default="")
    ap.add_argument("--out-svg-cc", default="")
    args = ap.parse_args()
    ccs = [c.strip() for c in args.ccs.split(",") if c.strip()]
    fair_g = 400.0 / 9.0  # 8 incast + 1 probe

    print(
        "size  regime    cc      fct_us  slow  gp_G  vs_fair  pfc  "
        "rate0  rate_min  rate_mean  rate_end  n_ev  cut_us"
    )
    rows_out = []
    for tag, size, regime in PROBE_TAGS:
        for cc in ccs:
            cctag = CC_FILE.get(cc, cc)
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
                "%5.1f %8.1f %9.1f %8.1f %4d %s"
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
                    rs["mean_g"],
                    rs["end_g"],
                    rs["n"],
                    cut,
                )
            )
            print(line)
            rows_out.append((tag, regime, cc, r, gp, slow, pfc_n, rs))

    print("\n=== probe rate series (dport=100, t relative to start, Gbps) ===")
    for tag, regime, cc, r, gp, slow, pfc_n, rs in rows_out:
        if cc not in ("dcqcn", "hp", "timely") or tag not in (
            "32k",
            "400k",
            "1m",
            "5m",
            "20m",
        ):
            continue
        print("\n-- %s %s --" % (tag, cc))
        if not rs["series"]:
            print("  (no rate events)")
            continue
        for t_us, g, why in rs["series"]:
            print("  t=+%7.1fus  %7.1fG  %s" % (t_us, g, why))

    if args.out_md:
        write_markdown(args.out_md, rows_out, fair_g)
        print("wrote %s" % args.out_md)
    if args.out_svg:
        write_slowdown_svg(args.out_svg, rows_out, ccs)
        print("wrote %s" % args.out_svg)
    if args.out_svg_cc:
        cc_only = [c for c in ccs if c != "pfc"]
        cc_rows = [x for x in rows_out if x[2] in cc_only]
        write_slowdown_svg(args.out_svg_cc, cc_rows, cc_only)
        print("wrote %s" % args.out_svg_cc)


if __name__ == "__main__":
    main()
