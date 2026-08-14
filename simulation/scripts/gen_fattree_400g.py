#!/usr/bin/env python3
"""Generate a 400G 2-tier non-blocking fat-tree and microbenchmark flows.

Default fabric (1:1, no oversubscription):
  4 leaf, 2 spine
  each leaf: 16 x 400G host downlinks
  each leaf: 8 x 400G to spine0 + 8 x 400G to spine1  (16 uplinks)

Node IDs:
  hosts  0..63   leaf L host i  ->  host_id = L*16 + i
  leaves 64..67
  spines 68..69

Flows use a *subset* of hosts; unused NICs stay idle. The fabric remains 1:1.
"""
from __future__ import annotations

import argparse
import os

N_LEAF = 4
N_SPINE = 2
HOSTS_PER_LEAF = 16
LINKS_PER_LEAF_SPINE = 8  # 8*2 spines = 16 uplinks = 16 downlinks
BW = "400Gbps"
DELAY = "1000ns"
ERROR = "0"


def host_id(leaf: int, idx: int) -> int:
    return leaf * HOSTS_PER_LEAF + idx


def leaf_id(leaf: int) -> int:
    return N_LEAF * HOSTS_PER_LEAF + leaf


def spine_id(spine: int) -> int:
    return N_LEAF * HOSTS_PER_LEAF + N_LEAF + spine


def write_topology(path: str) -> None:
    n_host = N_LEAF * HOSTS_PER_LEAF
    n_sw = N_LEAF + N_SPINE
    n_node = n_host + n_sw
    n_link = n_host + N_LEAF * N_SPINE * LINKS_PER_LEAF_SPINE
    switches = [leaf_id(i) for i in range(N_LEAF)] + [spine_id(i) for i in range(N_SPINE)]
    links = []
    for leaf in range(N_LEAF):
        lid = leaf_id(leaf)
        for i in range(HOSTS_PER_LEAF):
            links.append((host_id(leaf, i), lid))
        for spine in range(N_SPINE):
            sid = spine_id(spine)
            for _ in range(LINKS_PER_LEAF_SPINE):
                links.append((lid, sid))
    assert len(links) == n_link
    with open(path, "w") as f:
        f.write("%d %d %d\n" % (n_node, n_sw, n_link))
        f.write(" ".join(str(s) for s in switches) + "\n")
        for a, b in links:
            f.write("%d %d %s %s %s\n" % (a, b, BW, DELAY, ERROR))
    print("wrote %s  nodes=%d switches=%d links=%d (hosts=%d)" % (path, n_node, n_sw, n_link, n_host))


def write_trace(path: str) -> None:
    sw = [leaf_id(i) for i in range(N_LEAF)] + [spine_id(i) for i in range(N_SPINE)]
    with open(path, "w") as f:
        f.write("%d\n" % len(sw))
        for s in sw:
            f.write("%d\n" % s)
    print("wrote %s  switch nodes %s" % (path, sw))


def write_flows(path: str, rows: list) -> None:
    with open(path, "w") as f:
        f.write("%d\n" % len(rows))
        for src, dst, dport, size, t in rows:
            f.write("%d %d 3 %d %d %.6f\n" % (src, dst, dport, size, t))
    print("wrote %s  %d flows" % (path, len(rows)))


def flows_pair2() -> list:
    """Two independent 20MB elephants on disjoint leaf1 dests.

    If parallel uplinks are routed, each should finish near standalone (~400G).
    If uplinks collapsed to one ECMP member, both share 400G and slowdown ~2x.
    """
    return [
        (host_id(0, 0), host_id(1, 0), 100, 20 * 1000 * 1000, 2.0),
        (host_id(0, 1), host_id(1, 1), 101, 20 * 1000 * 1000, 2.0),
    ]


def flows_hol() -> list:
    """PFC HoL on the destination leaf.

    16 senders x 2 QPs (32 flows) from leaf0+leaf3 onto leaf1 host0, so ECMP
    occupies the dest-leaf uplinks. Victim probes (4 QPs) start during the
    burst: leaf2 host0 -> leaf1 host1 (idle dest, same ToR). PFC on
    spine->leaf1 ingress then stalls some/all victim QPs (HoL).
    """
    senders = [host_id(0, i) for i in range(8)] + [host_id(3, i) for i in range(8)]
    rows = []
    dport = 200
    for src in senders:
        for _qp in range(2):
            rows.append((src, host_id(1, 0), dport, 4 * 1000 * 1000, 2.000000))
            dport += 1
    for qp in range(4):
        rows.append((host_id(2, 0), host_id(1, 1), 100 + qp, 3 * 1000 * 1000, 2.000300))
    return rows


def flows_outcast(n: int) -> list:
    """Source-side outcast HoL (the 1/N signature).

    N leaf0 hosts incast to dest C on leaf1. Host 0 *also* sends a victim
    flow to idle dest V on leaf2. When PFC pauses host 0's NIC (same PG),
    the victim is backpressured with the incast QP and gets ~1/N of 400G.
    """
    dest_c = host_id(1, 0)
    dest_v = host_id(2, 0)
    senders = [host_id(0, i) for i in range(n)]
    rows = []
    for i, src in enumerate(senders):
        rows.append((src, dest_c, 200 + i, 20 * 1000 * 1000, 2.000000))
    rows.append((senders[0], dest_v, 100, 10 * 1000 * 1000, 2.000200))
    return rows


def flows_incast(n: int, size: int = 5 * 1000 * 1000) -> list:
    """Many-to-one onto one 400G dest. Shows DCQCN slow rate recovery.

    Senders taken from leaf0 then leaf3 (cross-spine) so traffic uses the fabric.
    """
    dest = host_id(1, 0)
    senders = []
    for leaf in (0, 3, 2):
        for i in range(HOSTS_PER_LEAF):
            if len(senders) >= n:
                break
            h = host_id(leaf, i)
            if h != dest:
                senders.append(h)
        if len(senders) >= n:
            break
    rows = []
    for i, src in enumerate(senders):
        rows.append((src, dest, 200 + i, size, 2.0))
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mix", default=os.path.join(os.path.dirname(__file__), "..", "mix"))
    args = ap.parse_args()
    mix = os.path.abspath(args.mix)
    os.makedirs(mix, exist_ok=True)
    write_topology(os.path.join(mix, "ft2_4l2s.txt"))
    write_trace(os.path.join(mix, "trace_ft2.txt"))
    write_flows(os.path.join(mix, "ft_pair2_flow.txt"), flows_pair2())
    write_flows(os.path.join(mix, "ft_hol_flow.txt"), flows_hol())
    write_flows(os.path.join(mix, "ft_incast8_flow.txt"), flows_incast(8))
    write_flows(os.path.join(mix, "ft_incast16_flow.txt"), flows_incast(16))
    write_flows(os.path.join(mix, "ft_outcast4_flow.txt"), flows_outcast(4))
    write_flows(os.path.join(mix, "ft_outcast8_flow.txt"), flows_outcast(8))


if __name__ == "__main__":
    main()
