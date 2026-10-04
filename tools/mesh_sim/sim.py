"""Discrete-event simulator of the mesh v2 network (``docs/mesh.md``).

Nodes exchange real encoded frames (``hardware/mesh_codec``) over a lossy radio. Time is a fake
clock in integer microseconds that only moves when ``Sim.run_until`` pops events: nothing here
ever sleeps.
Roles: ``MasterNode`` (role M, or F with rank 1), ``FollowerNode`` (role N/E), ``RemoteNode``.
"""

from __future__ import annotations

import heapq
import random
from dataclasses import dataclass, field
from functools import partial
from typing import Callable, Optional

from archerytimer.hardware import mesh_codec as mc
from archerytimer.hardware.mesh_types import (
    ACTION_CODES,
    EMERGENCY_ACTION,
    FLAG_EMERGENCY,
    NO_SOUND_AGE,
    RadioSound,
    RadioTimer,
)
from tools.mesh_sim.arbiter import Arbiter, CmdGate

US = 1000  # microseconds per ms
REPEATS_MS = (0, 3, 15, 40)  # first send and repeats of one frame (same seq)
HEARTBEAT_MS = 200
HELLO_MS = 2000
CMD_RETRY_MS = 15
CMD_GIVE_UP_MS = 250
SAFETY_REPEAT_MS = 50  # after a change toward the safe state: resend every 50 ms ...
SAFETY_REPEAT_FOR_MS = 500  # ... for 500 ms (same frame, same seq)
HOST_LATENCY_MS = 1.0  # master node to host and back for a forwarded command

MESH_KEY = bytes(range(16))


class Sim:
    """Event queue plus a seeded RNG. ``now_us`` is the only clock."""

    def __init__(self, seed: int = 0) -> None:
        self.now_us = 0
        self.rng = random.Random(seed)
        self._q: list[tuple[int, int, Callable[[], None]]] = []
        self._n = 0

    @property
    def now_ms(self) -> float:
        return self.now_us / US

    def at(self, delay_ms: float, fn: Callable[[], None]) -> None:
        self._n += 1
        heapq.heappush(self._q, (self.now_us + int(delay_ms * US), self._n, fn))

    def run_until(self, t_ms: float) -> None:
        end = int(t_ms * US)
        while self._q and self._q[0][0] <= end:
            self.now_us, _, fn = heapq.heappop(self._q)
            fn()
        self.now_us = max(self.now_us, end)

    def run_for(self, ms: float) -> None:
        self.run_until(self.now_ms + ms)


class BurstChannel:
    """Gilbert-Elliott in time: alternating good and bad stretches (exponential lengths)."""

    def __init__(self, rng: random.Random, mean_good_ms: float, mean_bad_ms: float) -> None:
        self._rng = rng
        self._good, self._bad = mean_good_ms * US, mean_bad_ms * US
        self._until = int(rng.expovariate(1 / self._good))
        self._is_bad = False

    def is_bad(self, t_us: int) -> bool:
        while t_us >= self._until:
            self._is_bad = not self._is_bad
            mean = self._bad if self._is_bad else self._good
            self._until += max(1, int(self._rng.expovariate(1 / mean)))
        return self._is_bad


DropFilter = Callable[[bytes, bytes, bytes], bool]  # (src, dst, data) -> drop


class Radio:
    """One broadcast domain. Partitions: nodes only hear nodes of their own group."""

    def __init__(
        self,
        sim: Sim,
        loss: float = 0.0,
        burst: Optional[BurstChannel] = None,
        latency_ms: tuple[float, float] = (0.3, 2.0),
        dup: float = 0.0,
    ) -> None:
        self.sim = sim
        self.loss, self.burst, self.latency_ms, self.dup = loss, burst, latency_ms, dup
        self.nodes: dict[bytes, Node] = {}
        self.group: dict[bytes, int] = {}
        self.drop_filter: Optional[DropFilter] = None
        self.capture: list[tuple[int, bytes, bytes]] = []  # (t_us, src, data), for replay tests
        self.sent = 0

    def attach(self, node: Node) -> None:
        self.nodes[node.mac] = node
        self.group.setdefault(node.mac, 0)

    def partition(self, groups: list[list[bytes]]) -> None:
        for i, g in enumerate(groups):
            for mac in g:
                self.group[mac] = i

    def heal(self) -> None:
        for mac in self.group:
            self.group[mac] = 0

    def send(self, src: bytes, data: bytes, spoofed: bool = False) -> None:
        self.sent += 1
        if not spoofed:
            self.capture.append((self.sim.now_us, src, data))
        bad = self.burst.is_bad(self.sim.now_us) if self.burst else False
        for mac, node in self.nodes.items():
            if mac == src or self.group[mac] != self.group.get(src, 0):
                continue
            if bad or self.sim.rng.random() < self.loss:
                continue
            if self.drop_filter and self.drop_filter(src, mac, data):
                continue
            copies = 2 if self.dup and self.sim.rng.random() < self.dup else 1
            for _ in range(copies):
                lat = self.sim.rng.uniform(*self.latency_ms)
                self.sim.at(lat, partial(node.on_radio, src, data))

    def inject(self, src_mac: bytes, data: bytes) -> None:
        """An attacker (or a replay) transmits ``data`` claiming ``src_mac``."""
        self.send(src_mac, data, spoofed=True)


def mac_of(n: int) -> bytes:
    return bytes([0x02, 0, 0, 0, 0, n])


class Node:
    """Common radio plumbing: epoch/seq, signing, repeats, receive path, reboot."""

    def __init__(
        self, sim: Sim, radio: Radio, mac: bytes, keys: mc.KeyRing, name: str = ""
    ) -> None:
        self.sim, self.radio, self.mac, self.keys, self.name = sim, radio, mac, keys, name
        self.dedupe = mc.Dedupe()
        self.up = True
        self.boots = 0
        self.epoch = 0
        self.seq = 0
        self._gen = 0  # invalidates scheduled work of a previous boot
        self.rx_log: list[tuple[int, int]] = []  # (t_us, ptype) of accepted frames
        radio.attach(self)
        self._boot()

    # --- lifecycle ---
    def _boot(self) -> None:
        self.boots += 1
        self._gen += 1
        self.epoch = self.sim.rng.randrange(1, 0x10000)
        self.seq = 0
        self.dedupe = mc.Dedupe()
        self.on_boot()

    def reboot(self, down_ms: float = 100.0) -> None:
        self.up = False
        self._gen += 1

        def come_up() -> None:
            self.up = True
            self._boot()

        self.sim.at(down_ms, come_up)

    def on_boot(self) -> None:
        pass

    def later(self, delay_ms: float, fn: Callable[[], None]) -> None:
        """Schedule work that dies with the current boot."""
        gen = self._gen
        self.sim.at(delay_ms, lambda: fn() if gen == self._gen and self.up else None)

    # --- tx ---
    def build(self, payload: mc.Payload, key: bytes, new_seq: bool = True) -> bytes:
        if new_seq:
            self.seq = (self.seq + 1) & 0xFFFF
        return mc.encode(mc.make_frame(payload, self.epoch, self.seq), key, self.mac)

    def burst(self, data: bytes) -> None:
        """First send and repeats of one frame (same seq) at 0, 3, 15, 40 ms."""
        for d in REPEATS_MS:
            self.later(d, partial(self.radio.send, self.mac, data))

    # --- rx ---
    def on_radio(self, src: bytes, data: bytes) -> None:
        if not self.up:
            return
        frame = mc.try_decode(data, src, self.keys)
        if frame is None or not self.dedupe.accept(src, frame.epoch, frame.seq):
            return
        self.rx_log.append((self.sim.now_us, frame.ptype))
        self.on_frame(src, frame)

    def on_frame(self, src: bytes, frame: mc.MeshFrame) -> None:
        pass

    def hello_loop(self, role: int, master_id: int, arb: Optional[Arbiter]) -> None:
        def send() -> None:
            now = self.sim.now_ms
            conflict = int(arb.conflict(now)) if arb else 0
            h = mc.RadioHello(0x0B, role, 0, conflict, master_id, (0, 3, 0), self.name[:12])
            self.burst(self.build(h, self.keys.mesh_key))
            self.later(HELLO_MS + self.sim.rng.uniform(0, 250), send)

        self.later(self.sim.rng.uniform(0, 250), send)


@dataclass
class HostModel:
    """Stand-in for the engine on the host behind a master node."""

    alive: bool = True
    lights: int = 4  # R
    flags: int = 0
    mode: int = 1
    phase: int = 0
    remaining_at_ms: float = 0.0
    remaining_ms: int = 30000
    sound_seq: int = 0
    sound_count: int = 0
    sound_start_us: Optional[int] = None
    executed: list[tuple[int, bytes, int, int]] = field(default_factory=list)


class MasterNode(Node):
    """Role M (rank 2) or, with ``rank=1``, role F mirroring a leader's ``master_id``."""

    def __init__(
        self, sim: Sim, radio: Radio, mac: bytes, master_id: int, rank: int = 2, name: str = ""
    ) -> None:
        self.master_id, self.rank = master_id, rank
        self.session = (
            1  # the core's persisted counter (bumped by the test on a "serial reconnect")
        )
        self.host = HostModel()
        self._sound_stopped = False
        self._sent_red = True
        self._sent_emergency = False
        self.gate = CmdGate()
        self.sessions: dict[int, int] = {}  # persisted in NVS
        self.arb = Arbiter("M" if rank == 2 else "F", master_id, True, sessions=self.sessions)
        self.sound_log: list[int] = []
        super().__init__(sim, radio, mac, mc.KeyRing(MESH_KEY), name)

    def pair_remote(self, mac: bytes, key: bytes, mask: int) -> None:
        self.keys.remote_keys = {**self.keys.remote_keys, mac: key}
        self.gate.pair(mac, mask)

    def on_boot(self) -> None:
        self.arb = Arbiter(
            "M" if self.rank == 2 else "F", self.master_id, self.host.alive, sessions=self.sessions
        )
        self.arb.set_host_lights(self.host.lights)
        self.hb_token = 0
        self.later(0, self.send_timer)
        self.hello_loop(2 if self.rank == 2 else 1, self.master_id, self.arb)

    # --- host side ---
    def host_changed(self) -> None:
        self.arb.set_host(self.host.alive)
        self.arb.set_host_lights(self.host.lights)
        self.send_timer()

    def set_emergency(self, on: bool) -> None:
        self.host.flags = (
            (self.host.flags | FLAG_EMERGENCY) if on else (self.host.flags & ~FLAG_EMERGENCY)
        )
        if on:
            self.host.lights = 4
        self.host_changed()

    def stop_sound(self) -> None:
        """The sound ends early (safety direction): the TIMER is repeated like an emergency."""
        h = self.host
        h.sound_seq = (h.sound_seq + 1) & 0xFF  # a stop is a new sound event
        h.sound_count = 0
        h.sound_start_us = None
        self._sound_stopped = True
        if h.alive and self.up:
            s = RadioSound(self.master_id, h.sound_seq, 0, 50, 50, session=self.session)
            self.burst(self.build(s, self.keys.mesh_key))
        self.send_timer()

    def play_sound(self, count: int, blast: int = 50, gap: int = 50) -> None:
        h = self.host
        h.sound_seq = (h.sound_seq + 1) & 0xFF
        h.sound_count = count
        h.sound_start_us = self.sim.now_us
        self.sound_log.append(self.sim.now_us)
        if h.alive and self.up:
            s = RadioSound(self.master_id, h.sound_seq, count, blast, gap, session=self.session)
            self.burst(self.build(s, self.keys.mesh_key))
            self.send_timer()

    def _timer_payload(self) -> RadioTimer:
        h = self.host
        age = NO_SOUND_AGE
        if h.sound_start_us is not None:
            age = min((self.sim.now_us - h.sound_start_us) // US, NO_SOUND_AGE - 1)
        return RadioTimer(
            self.master_id, self.rank, h.lights, h.flags, h.mode, h.phase, h.remaining_ms,
            1, 12, 0, 1, 4, 0, h.sound_seq, h.sound_count, 50, 50, age, self.session,
        )  # fmt: skip

    def send_timer(self) -> None:
        """TIMER on any change and every 200 ms after the last one (restarts the heartbeat)."""
        if not self.up:
            return
        self.hb_token += 1
        token = self.hb_token
        if self.host.alive:
            data = self.build(self._timer_payload(), self.keys.mesh_key)
            self.burst(data)
            self._safety_repeats(data)
        self.later(HEARTBEAT_MS, lambda: self.send_timer() if token == self.hb_token else None)

    def _safety_repeats(self, data: bytes) -> None:
        """Lights to RED, emergency latch set or sound stopped: resend this TIMER (same seq)."""
        h = self.host
        red = bool(h.lights & 4)
        emergency = bool(h.flags & FLAG_EMERGENCY)
        safe = (red and not self._sent_red) or (emergency and not self._sent_emergency)
        safe = safe or self._sound_stopped
        self._sent_red, self._sent_emergency, self._sound_stopped = red, emergency, False
        if safe:
            for t in range(SAFETY_REPEAT_MS, SAFETY_REPEAT_FOR_MS + 1, SAFETY_REPEAT_MS):
                self.later(t, partial(self.radio.send, self.mac, data))

    # --- radio side ---
    def on_frame(self, src: bytes, frame: mc.MeshFrame) -> None:
        now = self.sim.now_ms
        p = frame.payload
        if isinstance(p, RadioTimer):
            self.arb.on_timer(now, p, src)
        elif isinstance(p, mc.RadioCmd):
            self._on_cmd(src, p)

    def _on_cmd(self, src: bytes, cmd: mc.RadioCmd) -> None:
        d = self.gate.decide(src, cmd.counter, cmd.action, self.host.alive)
        if d.drop:
            return
        if d.ack is not None:
            self._ack(src, cmd.counter, d.ack)
        if d.forward:

            def host_exec() -> None:
                self.host.executed.append((self.sim.now_us, src, cmd.action, cmd.counter))
                if cmd.action == EMERGENCY_ACTION:
                    self.set_emergency(True)
                self.gate.host_result(src, cmd.counter, mc.RESULT_DONE)
                self._ack(src, cmd.counter, mc.RESULT_DONE)

            self.later(HOST_LATENCY_MS, host_exec)

    def _ack(self, target: bytes, counter: int, result: int) -> None:
        ack = mc.RadioCmdAck(target, counter, result)
        self.burst(self.build(ack, self.keys.mesh_key))


class FollowerNode(Node):
    """Role N (or E): follows a master through the arbiter and records its outputs."""

    def __init__(self, sim: Sim, radio: Radio, mac: bytes, role: str = "N", name: str = "") -> None:
        self.role = role
        self.sessions: dict[int, int] = {}  # persisted in NVS: survives reboot
        self.arb = Arbiter(role, sessions=self.sessions)
        self.follow_log: list[tuple[int, Optional[int]]] = []
        self.lights_log: list[tuple[int, int]] = []
        self.first_emergency_us: Optional[int] = None
        self.sound_log: list[tuple[int, int]] = []
        self.stop_log: list[int] = []  # sim times (us) at which a stop reached the arbiter
        super().__init__(sim, radio, mac, mc.KeyRing(MESH_KEY), name)

    def on_boot(self) -> None:
        self.arb = Arbiter(self.role, sessions=self.sessions)
        self.first_emergency_us = None
        self._sample()
        self.hello_loop(0, 0, self.arb)

    def _sample(self) -> None:
        now = self.sim.now_ms
        f = self.arb.follow(now)
        if not self.follow_log or self.follow_log[-1][1] != f:
            self.follow_log.append((self.sim.now_us, f))
        lt = self.arb.lights(now)
        if not self.lights_log or self.lights_log[-1][1] != lt:
            self.lights_log.append((self.sim.now_us, lt))
        self.later(5, self._sample)

    def lights_at_now(self) -> int:
        return self.arb.lights(self.sim.now_ms)

    def on_frame(self, src: bytes, frame: mc.MeshFrame) -> None:
        now = self.sim.now_ms
        p = frame.payload
        n_before = self.arb.sound_started()
        stops_before = len(self.arb.sound_stops)
        if isinstance(p, RadioTimer):
            self.arb.on_timer(now, p, src)
            seen = p.flags & FLAG_EMERGENCY and self.arb.follow(now) == p.master_id
            if seen and self.first_emergency_us is None:
                self.first_emergency_us = self.sim.now_us
        elif isinstance(p, RadioSound):
            self.arb.on_sound(now, p)
        elif isinstance(p, mc.RadioHello):
            self.arb.on_hello(now, src)
        for s in self.arb.sounds[n_before:]:
            self.sound_log.append((self.sim.now_us, s.count))
        self.stop_log.extend([self.sim.now_us] * (len(self.arb.sound_stops) - stops_before))


class RemoteNode(Node):
    """A paired remote: HMAC with its own key, persisted counter, retransmit until CMD_ACK."""

    def __init__(self, sim: Sim, radio: Radio, mac: bytes, key: bytes, name: str = "") -> None:
        self.key = key
        self.counter = 0  # persisted: survives reboot
        self.acked: dict[int, tuple[int, int]] = {}  # counter -> (t_us, result)
        self.sent_counters: list[int] = []
        super().__init__(sim, radio, mac, mc.KeyRing(MESH_KEY), name)

    def send_cmd(self, action: int, counter: Optional[int] = None) -> int:
        """Send a command; retransmit every 15 ms (new seq, same counter) until ACK, max 250 ms."""
        if counter is None:
            self.counter += 1
            counter = self.counter
        self.sent_counters.append(counter)
        cmd = mc.RadioCmd(counter, action)
        first = self.build(cmd, self.key)
        self.burst(first)
        for t in range(2 * CMD_RETRY_MS, CMD_GIVE_UP_MS + 1, CMD_RETRY_MS):

            def retry(cmd: mc.RadioCmd = cmd) -> None:
                if cmd.counter not in self.acked:
                    self.radio.send(self.mac, self.build(cmd, self.key))

            self.later(t, retry)
        return counter

    def send_named(self, action: str) -> int:
        return self.send_cmd(ACTION_CODES[action])

    def on_frame(self, src: bytes, frame: mc.MeshFrame) -> None:
        p = frame.payload
        if isinstance(p, mc.RadioCmdAck) and p.target_mac == self.mac:
            self.acked.setdefault(p.counter, (self.sim.now_us, p.result))
