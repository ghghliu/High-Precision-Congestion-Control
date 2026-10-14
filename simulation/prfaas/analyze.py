#!/usr/bin/env python3
"""Summarize FCT, PFC and switch-queue outputs for the PrfaaS runs."""

import argparse
import json
import os
from collections import defaultdict


BOTTLENECK_BPS = 100e9
# Egress kmin/kmax on the 100 Gbps WAN port, in KB buckets (qlen/1000).
KMIN_KB = 400
KMAX_KB = 1600
# Switch 9's 5th Qbb device is the WAN egress. Device 0 is loopback.
WAN_SW = 9
WAN_IF = 5


def percentile(sorted_vals, q):
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = (len(sorted_vals) - 1) * q
    lo = int(math_floor(idx))
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def math_floor(x):
    return int(x) if x >= 0 else int(x) - 1


def parse_fct(path):
    rows = []
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return rows
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) != 8:
                continue
            sip, dip, sport, dport, size, start, fct, standalone = parts
            rows.append({
                "dport": int(dport),
                "size": int(size),
                "start_ns": int(start),
                "fct_ns": int(fct),
                "standalone_ns": int(standalone),
            })
    return rows


def parse_pfc(path):
    pauses = 0
    resumes = 0
    by_node = defaultdict(lambda: [0, 0])
    if not os.path.exists(path):
        return {"pauses": 0, "resumes": 0, "by_node": {}}
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) != 5:
                continue
            _t, node, _ntype, _if, typ = parts
            typ = int(typ)
            node = int(node)
            if typ == 1:
                pauses += 1
                by_node[node][0] += 1
            elif typ == 0:
                resumes += 1
                by_node[node][1] += 1
    return {
        "pauses": pauses,
        "resumes": resumes,
        "by_node": {str(k): {"pause": v[0], "resume": v[1]} for k, v in by_node.items()},
    }


def last_qlen_block(path):
    """Return the last dumped histogram: (switch, ifindex) -> [counts]."""
    if not os.path.exists(path):
        return {}
    current = {}
    last = {}
    with open(path) as f:
        for line in f:
            if line.startswith("time:"):
                if current:
                    last = current
                current = {}
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            key = (int(parts[0]), int(parts[1]))
            current[key] = [int(x) for x in parts[2:]]
    if current:
        last = current
    return last


def qlen_stats(hist):
    total = sum(hist)
    if total == 0:
        return None
    above0 = total - (hist[0] if hist else 0)
    above_kmin = sum(hist[KMIN_KB:]) if len(hist) > KMIN_KB else 0
    above_kmax = sum(hist[KMAX_KB:]) if len(hist) > KMAX_KB else 0
    max_kb = len(hist) - 1
    # Mean KB using bucket index as the lower edge.
    mean_kb = sum(i * c for i, c in enumerate(hist)) / float(total)
    return {
        "samples": total,
        "max_kb": max_kb,
        "mean_kb": mean_kb,
        "frac_nonzero": above0 / float(total),
        "frac_ge_kmin": above_kmin / float(total),
        "frac_ge_kmax": above_kmax / float(total),
    }


def group_requests(fct_rows, manifest):
    """Match QPs back to requests by start time, src is implicit in dport grouping.

    Manifest conn dports are 100+conn. Starts are identical across the QPs of
    one request. Multiple requests can share a start only if n_req is 0.
    We key by (start_ns rounded, dport set) using manifest order.
    """
    by_start = defaultdict(list)
    for row in fct_rows:
        by_start[row["start_ns"]].append(row)
    out = []
    for req in manifest["requests"]:
        start_ns = int(round(req["start"] * 1e9))
        # ns-3 Seconds() may not land on the exact integer. Find the nearest.
        if start_ns not in by_start:
            if not by_start:
                continue
            nearest = min(by_start, key=lambda s: abs(s - start_ns))
            if abs(nearest - start_ns) > 1000:
                out.append({"request_id": req["request_id"], "missing": True})
                continue
            start_ns = nearest
        qps = by_start[start_ns]
        if len(qps) != len(req["conn_bytes"]):
            # Same start should be unique per request under uniform arrivals.
            pass
        fcts = [q["fct_ns"] for q in qps]
        stands = [q["standalone_ns"] for q in qps]
        req_fct = max(fcts) if fcts else None
        ideal = None
        if req_fct is not None and stands:
            # Standalone of the largest QP assumes it gets the full 100 Gbps.
            # Ideal request time is one RTT plus the whole KV at 100 Gbps.
            # Recover base RTT from a QP: standalone = rtt + bytes*8e9/bw.
            q0 = qps[0]
            # bytes * 8e9 / bw = standalone - rtt. bw is 100 Gbps.
            # Use total bytes directly.
            # base rtt = standalone - size * 8e9 / 100e9, from the first QP,
            # but header inflation is inside standalone. Approximate ideal as
            # max(standalone) * (total/max_piece) is wrong.
            # ideal_ns = base_rtt + total_bytes * 8 / BOTTLENECK.
            base = q0["standalone_ns"] - q0["size"] * 8000000000 // int(BOTTLENECK_BPS)
            ideal = base + req["total_bytes"] * 8000000000 // int(BOTTLENECK_BPS)
        gbps = None
        if req_fct:
            gbps = req["total_bytes"] * 8.0 / req_fct
        out.append({
            "request_id": req["request_id"],
            "tokens": req["tokens"],
            "total_bytes": req["total_bytes"],
            "n_qp": len(qps),
            "request_fct_us": None if req_fct is None else req_fct / 1e3,
            "ideal_us": None if ideal is None else ideal / 1e3,
            "slowdown": None if not req_fct or not ideal else req_fct / float(ideal),
            "gbps": gbps,
            "qp_slowdowns": [q["fct_ns"] / float(q["standalone_ns"]) for q in qps],
            "missing": len(qps) != len(req["conn_bytes"]),
        })
    return out


def summarize_job(out_dir, job, manifest):
    tag = job["tag"]
    fct_rows = parse_fct(os.path.join(out_dir, "fct_%s.txt" % tag))
    pfc = parse_pfc(os.path.join(out_dir, "pfc_%s.txt" % tag))
    qlens = last_qlen_block(os.path.join(out_dir, "qlen_%s.txt" % tag))
    wan = qlen_stats(qlens.get((WAN_SW, WAN_IF), []))
    ports = []
    for key, hist in sorted(qlens.items()):
        st = qlen_stats(hist)
        if st and st["max_kb"] > 0:
            ports.append({"switch": key[0], "ifindex": key[1], **st})
    reqs = group_requests(fct_rows, manifest)
    done = [r for r in reqs if r.get("slowdown") is not None]
    slows = sorted(r["slowdown"] for r in done)
    qp_slows = sorted(s for r in done for s in r["qp_slowdowns"])
    gbps = [r["gbps"] for r in done if r["gbps"] is not None]
    return {
        "tag": tag,
        "cc": job["cc"],
        "n_conn": job["n_conn"],
        "km": job["km"],
        "qp_finished": len(fct_rows),
        "qp_expected": manifest["n_conn"] * len(manifest["requests"]) if False else job["n_conn"] * len(manifest["requests"]),
        "requests_done": len(done),
        "requests": len(manifest["requests"]),
        "slowdown_mean": None if not slows else sum(slows) / len(slows),
        "slowdown_p50": percentile(slows, 0.50),
        "slowdown_p90": percentile(slows, 0.90),
        "gbps_mean": None if not gbps else sum(gbps) / len(gbps),
        "qp_slowdown_mean": None if not qp_slows else sum(qp_slows) / len(qp_slows),
        "pfc_pauses": pfc["pauses"],
        "pfc_resumes": pfc["resumes"],
        "pfc_by_node": pfc["by_node"],
        "wan_queue": wan,
        "busy_ports": ports,
        "per_request": done,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    with open(os.path.join(args.out, "jobs.json")) as f:
        jobs = json.load(f)["jobs"]
    manifests = {}
    summaries = []
    for job in jobs:
        n_conn = job["n_conn"]
        if n_conn not in manifests:
            with open(os.path.join(args.out, "manifest_c%d.json" % n_conn)) as f:
                manifests[n_conn] = json.load(f)
        fct_path = os.path.join(args.out, "fct_%s.txt" % job["tag"])
        if not os.path.exists(fct_path):
            continue
        summaries.append(summarize_job(args.out, job, manifests[n_conn]))
    dest = os.path.join(args.out, "summary.json")
    with open(dest, "w") as f:
        json.dump(summaries, f)
    print("summarized %d jobs -> %s" % (len(summaries), dest))
    for row in summaries:
        wan = row["wan_queue"] or {}
        print("%-22s req %d/%d slowdown mean %.3f p90 %.3f pfc %d wan_max_kB %s ge_kmin %.4f" % (
            row["tag"], row["requests_done"], row["requests"],
            row["slowdown_mean"] or -1, row["slowdown_p90"] or -1,
            row["pfc_pauses"], wan.get("max_kb"), wan.get("frac_ge_kmin", 0)))


if __name__ == "__main__":
    main()
