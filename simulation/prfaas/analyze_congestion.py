#!/usr/bin/env python3
"""FCT, fair-share slowdown, PFC and egress-queue summary for congestion runs."""

import json
import os
import sys
from collections import defaultdict

KMIN_PER_GBPS = 4.0
KMAX_PER_GBPS = 16.0
DCTCP_K_PER_GBPS = 3.0


def percentile(vals, q):
    if not vals:
        return None
    vals = sorted(vals)
    if len(vals) == 1:
        return vals[0]
    idx = (len(vals) - 1) * q
    lo = int(idx)
    hi = min(lo + 1, len(vals) - 1)
    frac = idx - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def parse_fct(path):
    rows = []
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return rows
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) != 8:
                continue
            _sip, _dip, _sport, dport, size, start, fct, standalone = parts
            rows.append({
                "dport": int(dport),
                "size": int(size),
                "start_ns": int(start),
                "fct_ns": int(fct),
                "standalone_ns": int(standalone),
            })
    return rows


def parse_pfc(path):
    events = []
    if not os.path.exists(path):
        return events
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) != 5:
                continue
            t, node, _nt, iface, typ = parts
            events.append((int(t), int(node), int(iface), int(typ)))
    return events


def pause_stats(events, wan_sw, wan_if):
    pauses = sum(1 for e in events if e[3] == 1)
    resumes = sum(1 for e in events if e[3] == 0)
    wan = [e for e in events if e[1] == wan_sw and e[2] == wan_if]
    wan_pauses = sum(1 for e in wan if e[3] == 1)
    # Pair pause/resume on the WAN egress in time order.
    open_at = None
    held = 0
    for t, _n, _i, typ in wan:
        if typ == 1 and open_at is None:
            open_at = t
        elif typ == 0 and open_at is not None:
            held += t - open_at
            open_at = None
    return {
        "pauses": pauses,
        "resumes": resumes,
        "wan_pauses": wan_pauses,
        "wan_pause_us": held / 1e3,
    }


def last_qlen(path):
    current = {}
    last = {}
    if not os.path.exists(path):
        return {}
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
            current[(int(parts[0]), int(parts[1]))] = [int(x) for x in parts[2:]]
    return current or last


def qstats(hist, kmin_kb, kmax_kb):
    total = sum(hist) if hist else 0
    if total == 0:
        return None
    return {
        "samples": total,
        "max_kb": len(hist) - 1,
        "mean_kb": sum(i * c for i, c in enumerate(hist)) / float(total),
        "frac_nonzero": (total - hist[0]) / float(total) if hist else 0.0,
        "frac_ge_kmin": sum(hist[kmin_kb:]) / float(total) if len(hist) > kmin_kb else 0.0,
        "frac_ge_kmax": sum(hist[kmax_kb:]) / float(total) if len(hist) > kmax_kb else 0.0,
    }


def summarize(job, out_dir):
    tag = job["tag"]
    fct_rows = parse_fct(os.path.join(out_dir, "fct_%s.txt" % tag))
    by_src = defaultdict(list)
    # Sport is assigned by the simulator; group by start (all 0) and size pattern.
    # Requests are distinguished by destination port base and by source IP.
    # The printed sip encodes node id in the low bytes of 0x0b000001 + id*0x100.
    for row in fct_rows:
        # Recover src from the first field when re-parsed below.
        pass
    parsed = []
    path = os.path.join(out_dir, "fct_%s.txt" % tag)
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                parts = line.split()
                if len(parts) != 8:
                    continue
                sip = int(parts[0], 16)
                src = (sip >> 8) & 0xffff
                parsed.append({
                    "src": src,
                    "dport": int(parts[3]),
                    "size": int(parts[4]),
                    "fct_ns": int(parts[6]),
                    "standalone_ns": int(parts[7]),
                })
    groups = defaultdict(list)
    for row in parsed:
        groups[row["src"]].append(row)
    link_bps = job["wan_gbps"] * 1e9
    n_flows = len(job["requests"])
    flow_done = []
    for req in job["requests"]:
        qps = groups.get(req["src"], [])
        if len(qps) != len(req["conn_bytes"]):
            flow_done.append({"src": req["src"], "kind": req["kind"], "missing": True})
            continue
        fct = max(q["fct_ns"] for q in qps)
        base = qps[0]["standalone_ns"] - qps[0]["size"] * 8000000000 // int(link_bps)
        if base < 0:
            base = 0
        fair = base + req["total_bytes"] * 8000000000 // int(link_bps / n_flows)
        flow_done.append({
            "src": req["src"],
            "kind": req["kind"],
            "bytes": req["total_bytes"],
            "fct_us": fct / 1e3,
            "gbps": req["total_bytes"] * 8.0 / fct,
            "fair_slowdown": fct / float(fair) if fair else None,
            "missing": False,
        })
    ok = [r for r in flow_done if not r.get("missing")]
    makespan = max((r["fct_us"] for r in ok), default=0.0)
    total_bytes = sum(r["bytes"] for r in ok)
    agg_gbps = (total_bytes * 8.0 / (makespan * 1e3)) if makespan else 0.0
    slows = [r["fair_slowdown"] for r in ok if r["fair_slowdown"] is not None]
    gbps = [r["gbps"] for r in ok]
    pfc = pause_stats(parse_pfc(os.path.join(out_dir, "pfc_%s.txt" % tag)), job["wan_sw"], job["wan_if"])
    hist = last_qlen(os.path.join(out_dir, "qlen_%s.txt" % tag)).get((job["wan_sw"], job["wan_if"]), [])
    if job["cc"] == "dctcp":
        kmin = int(round(DCTCP_K_PER_GBPS * job["wan_gbps"]))
        kmax = kmin
    else:
        kmin = int(round(KMIN_PER_GBPS * job["wan_gbps"]))
        kmax = int(round(KMAX_PER_GBPS * job["wan_gbps"]))
    return {
        "tag": tag,
        "kind": job["kind"],
        "cc": job["cc"],
        "k": job["k"],
        "n_conn": job["n_conn"],
        "km": job["km"],
        "wan_gbps": job["wan_gbps"],
        "prefix_mib": job["prefix_mib"],
        "flows_done": len(ok),
        "flows": n_flows,
        "agg_gbps": agg_gbps,
        "link_util": agg_gbps / job["wan_gbps"] if job["wan_gbps"] else None,
        "gbps_min": min(gbps) if gbps else None,
        "gbps_p50": percentile(gbps, 0.5),
        "fair_slowdown_mean": (sum(slows) / len(slows)) if slows else None,
        "fair_slowdown_p50": percentile(slows, 0.5),
        "fair_slowdown_max": max(slows) if slows else None,
        "makespan_ms": makespan / 1e3,
        "pfc_pauses": pfc["pauses"],
        "pfc_resumes": pfc["resumes"],
        "wan_pauses": pfc["wan_pauses"],
        "wan_pause_us": pfc["wan_pause_us"],
        "wan_queue": qstats(hist, kmin, kmax),
        "kmin_kb": kmin,
        "per_flow": ok,
    }


def main():
    out_dir = sys.argv[1]
    jobs = json.load(open(os.path.join(out_dir, "jobs.json")))["jobs"]
    rows = []
    for job in jobs:
        fct = os.path.join(out_dir, "fct_%s.txt" % job["tag"])
        if not os.path.exists(fct):
            continue
        rows.append(summarize(job, out_dir))
    dest = os.path.join(out_dir, "summary.json")
    with open(dest, "w") as f:
        json.dump(rows, f)
    print("summarized", len(rows))
    for r in rows:
        q = r["wan_queue"] or {}
        print("%-40s done %d/%d agg %6.1f util %5.2f slow %5.2f pfc %5d wan_pause %5d qmax %s kmin_frac %.3f" % (
            r["tag"], r["flows_done"], r["flows"], r["agg_gbps"], r["link_util"] or -1,
            r["fair_slowdown_mean"] or -1, r["pfc_pauses"], r["wan_pauses"],
            q.get("max_kb"), q.get("frac_ge_kmin", 0)))


if __name__ == "__main__":
    main()
