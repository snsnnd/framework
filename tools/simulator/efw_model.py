"""EFW framework workload model, calibrated from on-hardware measurements.

Reference platform: CT117E-M4 (STM32G431RBT6), HSI 16MHz,
arm-none-eabi-gcc 10.3.1 -O2, measured 2026-09-12 with DWT cycle counter
(see hwtest_g431/REPORT.md for the full test report).

All costs are stored in CPU **cycles** so they scale to any core clock:
cycles were derived from nanosecond measurements at 16 MHz (cycles = ns * 16).

Measured anchors (10000-iteration on-silicon averages):
  efw_init()                       42 us
  sensor lookup, 3 entries     15 654 ns   (registry linear scan)
  sensor lookup, 32 entries   136 118 ns   -> ~4.16 us per extra entry
  PID run via registry         29 930 ns
  topic publish, 4 subs        10 769 ns
  event queue post+process     11 522 ns
  scheduler, 16 x 1ms tasks: 2786/2800 releases serviced in 200 ms

The model deliberately does NOT pretend to run EFW C code. It answers the
question the old idle-loop simulator could not: "given this app workload,
what fraction of the CPU does the EFW framework consume?"
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- calibrated costs in CPU cycles (Cortex-M4, gcc -O2) ---------------------
# cycles = measured_ns_at_16MHz * 16MHz / 1000 = ns * 0.016
def _c(ns16: float) -> int:
    return int(round(ns16 * 16.0 / 1000.0))

CYC = {
    "efw_init": _c(42 * 1000),
    "lookup_base": _c(15654),           # registry lookup + read cb, 3 entries
    "lookup_per_entry": _c(4157),       # each extra registry entry (linear scan)
    "pid_run": _c(29930),               # algo registry path incl. validation
    "pub_base": _c(2000),               # estimated base (see note)
    "pub_per_sub": _c(2192),            # calibrated so base+4*per == 10769ns
    "queue_roundtrip": _c(11522),
    "sched_tick_base": _c(800),         # estimated: tick() call overhead
    "sched_per_task": _c(1000),         # estimated: per-task scan+release
}

# note: pub_base/pub_per_sub are anchored on the 4-subscriber measurement
# (2000 + 4*2192 = 10769 ns); the split between base and per-sub is an
# assumption, the 4-sub total is measured.


@dataclass
class EFWWorkload:
    """Application workload description (per 1 ms scheduler tick)."""
    registry_entries: int = 8       # average registry depth for name lookups
    lookups_per_ms: int = 0         # efw_sensor_read / efw_algo_get calls
    pid_runs_per_ms: int = 0        # efw_algo_run PID calls (1kHz loop = 1)
    publishes_per_ms: int = 0       # efw_topic_publish calls
    pub_subscribers: int = 0
    queue_ops_per_ms: int = 0       # post+process roundtrips
    scheduler_tasks: int = 0        # registered scheduler tasks
    task_period_ms: int = 1

    def cycles_per_tick(self) -> int:
        """CPU cycles consumed by one 1 ms tick of this workload."""
        c = 0
        c += self.lookups_per_ms * (
            CYC["lookup_base"] + max(0, self.registry_entries - 3) * CYC["lookup_per_entry"]
        )
        c += self.pid_runs_per_ms * CYC["pid_run"]
        c += self.publishes_per_ms * (
            CYC["pub_base"] + self.pub_subscribers * CYC["pub_per_sub"]
        )
        c += self.queue_ops_per_ms * CYC["queue_roundtrip"]
        if self.scheduler_tasks:
            c += CYC["sched_tick_base"] + self.scheduler_tasks * CYC["sched_per_task"]
        return c


def simulate_efw(mcu, workload: EFWWorkload, duration_ms: int) -> dict:
    """Run the calibrated workload model against an MCUSimulator clock.

    Returns a report dict; also prints a human-readable summary.
    """
    sysclk = mcu.clock.sysclk_hz
    cycles_per_ms = sysclk // 1000

    per_tick = workload.cycles_per_tick()
    total_work = per_tick * duration_ms
    total_capacity = cycles_per_ms * duration_ms
    utilization = total_work / total_capacity if total_capacity else 0.0

    # per-op time at this clock
    ns = lambda cyc: cyc * 1e9 / sysclk  # noqa: E731

    report = {
        "workload": "efw",
        "chip": getattr(mcu, "chip_name", "?"),
        "sysclk_hz": sysclk,
        "duration_ms": duration_ms,
        "cycles_per_tick": per_tick,
        "capacity_cycles_per_tick": cycles_per_ms,
        "utilization": utilization,
        "headroom_pct": max(0.0, (1.0 - utilization) * 100.0),
        "over_budget": utilization > 1.0,
        "op_costs_ns": {
            "efw_init": ns(CYC["efw_init"]),
            "sensor_lookup": ns(CYC["lookup_base"]
                                + max(0, workload.registry_entries - 3) * CYC["lookup_per_entry"]),
            "pid_run": ns(CYC["pid_run"]),
            "publish_4subs": ns(CYC["pub_base"] + 4 * CYC["pub_per_sub"]),
            "queue_roundtrip": ns(CYC["queue_roundtrip"]),
        },
    }

    print("  EFW 工作负载模型（实机校准 @16MHz, CT117E-M4）")
    print(f"  芯片: {report['chip']}  SYSCLK: {sysclk/1e6:.0f} MHz")
    print(f"  每 1ms tick 框架开销: {per_tick} cycles / 容量 {cycles_per_ms} cycles")
    print(f"  CPU 利用率: {utilization*100:.1f}%   余量: {report['headroom_pct']:.1f}%")
    if report["over_budget"]:
        print("  !! 负载超出 1ms 预算，需要降低频率/优化或分频调度")
    print("  单次操作耗时（本时钟下）:")
    for k, v in report["op_costs_ns"].items():
        print(f"    {k:16s} {v/1000:8.2f} us")
    return report
