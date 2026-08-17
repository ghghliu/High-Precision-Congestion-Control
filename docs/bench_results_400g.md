# P0 results @ 400G (buffer 32MB)

Command: `bash simulation/scripts/run_bench_p0.sh`

## B1 HoL (victim isolated from incast senders)

| CC | Victim slowdown | Victim goodput | PFC pauses | Notes |
|----|-----------------|----------------|------------|-------|
| **pfc** | 2.66× | 142 Gbps | **1766** (host0 victim: **239**, host1:765, host2:762) | Innocent victim sender is paused — pause propagates from shared Leaf0–Leaf1 hop |
| dcqcn | 4.35× | 87 Gbps | **0** | No PFC; ECN also rate-limits the victim on the shared fabric |

**Takeaway:** PFC HoL is confirmed by pause counts on victim host 0. DCQCN removes pauses but still taxes the victim via shared-path rate control.

## B2 Incast / recovery (7×5MB + 200KB probe @ t+200µs)

| CC | Incast med slowdown | Cohort agg goodput | Probe slowdown | PFC pauses |
|----|---------------------|--------------------|----------------|------------|
| pfc | 6.5× | **~395 Gbps** (~line rate) | **43×** (probe HoL'd) | 155 |
| **dcqcn** | **12.7×** | **193 Gbps** (~48% line rate) | ~1.0× | 0 |

**Takeaway:**

- **PFC:** keeps the pipe full for the incast cohort, but the mid-burst probe is head-of-line blocked (43×).
- **DCQCN:** eliminates PFC, yet AI/HAI recovery after CNP leaves the bottleneck ~half idle during the 5MB incast (slow convergence / under-utilization). That is the gap a new CC should close.

## Next

- Add HPCC as reference on the same two benches
- Fat-tree + WebSearch load sweep
- New CC goal: no (or rare) PFC/HoL **and** fast recovery so short/medium flows do not leave 400G idle
