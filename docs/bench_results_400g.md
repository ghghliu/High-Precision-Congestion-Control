# P0 results @ 400G (buffer 32MB)

Command: `bash simulation/scripts/run_bench_p0.sh`

## B1 HoL

| CC | Victim slowdown | Victim goodput | PFC pauses | Notes |
|----|-----------------|----------------|------------|-------|
| **pfc** | **2.66×** | 142 Gbps | **1766** (host0:239, host1:765, host2:762) | Victim host **0 is paused** even though it only sends the victim flow — pause propagates from shared Leaf0–Leaf1 hop |
| dcqcn | 4.35× | 87 Gbps | **0** | No PFC; ECN rate-limits the shared fabric, victim also slowed |

**Takeaway:** PFC HoL is confirmed by pause counts on the innocent victim sender. DCQCN eliminates pauses but can leave the victim slower via rate reduction on the shared path.

## B2 Incast / recovery (7×5MB → one receiver)

| CC | Incast med slowdown | Per-flow avg goodput | Cohort agg goodput | PFC pauses |
|----|---------------------|----------------------|--------------------|------------|
| pfc | 6.45× | 56.9 Gbps | **397.7 Gbps** (~line rate) | 154 |
| **dcqcn** | **12.7×** | **29.2 Gbps** | **193.3 Gbps** (~48% of line rate) | 0 |

**Takeaway:** DCQCN avoids PFC but **under-utilizes** the 400G bottleneck during/after CNP response (AI=80Mb/s, RP_TIMER=300µs). This is the small/medium-flow slow-convergence problem to beat with a new CC.

## Next experiments

- Sweep probe start time during incast; add HPCC as reference upper bound
- Scale topology to fat-tree + WebSearch load
- New CC targeting: (1) minimal PFC / no HoL, (2) fast start/recovery for short flows without leaving bandwidth idle
