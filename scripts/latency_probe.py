"""Latency probe: state change -> bytes on the wire (-> device).

    python scripts/latency_probe.py              # simulated device, in-memory cable
    python scripts/latency_probe.py --port COM7  # real MCU: write latency + $V/$I round trip

Simulated mode timestamps both ends on one clock, so it shows host-side cost
(enqueue -> write returned -> device parsed). Real mode can only see the host side
plus the round trip of the hello exchange; half of it bounds the one-way latency.
One-way "MCU acts" time still needs a scope or logic analyser on the light GPIO.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time

from archerytimer.core.models import Light, LightChange
from archerytimer.hardware import protocol as p
from archerytimer.hardware.discovery import open_serial
from archerytimer.hardware.serial_worker import LINK_UP, SerialWorker
from archerytimer.hardware.sim_device import SimDevice, SimDeviceRunner, memory_port_pair


def summarize(name: str, values_ns: list[int]) -> None:
    if not values_ns:
        print(f"{name}: no samples")
        return
    v = sorted(values_ns)
    p99 = v[min(len(v) - 1, int(len(v) * 0.99))]
    print(
        f"{name:34s} n={len(v):4d}  p50={statistics.median(v) / 1e6:7.3f} ms  "
        f"p99={p99 / 1e6:7.3f} ms  max={v[-1] / 1e6:7.3f} ms"
    )


def wait_up(worker: SerialWorker) -> None:
    end = time.monotonic() + 5
    while worker.link != LINK_UP and time.monotonic() < end:
        time.sleep(0.01)
    if worker.link != LINK_UP:
        sys.exit("device did not connect")


def drive(worker: SerialWorker, count: int, gap_s: float) -> None:
    for i in range(count):
        worker.submit(LightChange(Light.GREEN if i % 2 == 0 else Light.RED))
        time.sleep(gap_s)


def run_sim(count: int, gap_s: float) -> None:
    device = SimDevice()
    host, dev = memory_port_pair()
    runner = SimDeviceRunner(device, dev, poll_s=0.001).start()
    worker = SerialWorker(lambda: host)
    worker.start()
    try:
        wait_up(worker)
        device.log.clear()
        worker.latencies.clear()
        drive(worker, count, gap_s)
        time.sleep(0.1)
    finally:
        worker.stop()
        runner.stop()
    summarize("enqueue -> write returned", [d - e for e, d in worker.latencies])
    rx = [e.t_ns for e in device.log if e.direction == "rx" and e.data.startswith(b"$L")]
    pairs = list(zip((e for e, _ in worker.latencies), rx))
    summarize("enqueue -> device parsed frame", [r - e for e, r in pairs])


def run_real(port: str, count: int, gap_s: float) -> None:
    worker = SerialWorker(lambda: open_serial(port))
    worker.start()
    try:
        wait_up(worker)
        worker.latencies.clear()
        drive(worker, count, gap_s)
    finally:
        worker.stop()
    summarize("enqueue -> write returned", [d - e for e, d in worker.latencies])
    sp = open_serial(port)
    rtts = []
    parser = p.FrameParser()
    try:
        for _ in range(count):
            t0 = time.monotonic_ns()
            sp.write(p.encode(p.Hello()))
            while True:
                if any(isinstance(f, p.HelloReply) for f in parser.feed(sp.read(64))):
                    break
                if time.monotonic_ns() - t0 > 500_000_000:
                    break
            rtts.append(time.monotonic_ns() - t0)
            time.sleep(gap_s)
    finally:
        sp.close()
    summarize("$V -> $I round trip", rtts)
    print("one-way upper bound is about half the round trip")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", default="")
    ap.add_argument("--count", type=int, default=200)
    ap.add_argument("--gap-ms", type=float, default=20)
    a = ap.parse_args()
    if a.port:
        run_real(a.port, a.count, a.gap_ms / 1000)
    else:
        run_sim(a.count, a.gap_ms / 1000)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
