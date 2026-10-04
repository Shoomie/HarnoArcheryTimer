"""Python reference of the mesh arbiter (``docs/mesh.md`` section 4). Pure logic, times in ms.

Mirrors ``firmware/lib/meshcore``; ``firmware/arbiter_scenarios.txt`` is its executable definition
(``tools/mesh_sim/scenarios.py`` runs it). Also contains the CMD gate of the master node.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from archerytimer.hardware.mesh_codec import RESULT_DENIED
from archerytimer.hardware.mesh_types import (
    FLAG_EMERGENCY,
    NO_SOUND_AGE,
    RadioSound,
    RadioTimer,
    mask_allows,
)

LIVE_MS = 1000  # master live: a TIMER heard less than this ago
SWITCH_SILENCE_MS = 600
SWITCH_RANK_MS = 400
CONFLICT_ACTIVE_MS = 600
SOUND_REPLAY_GUARD_MS = 400
PEER_EXPIRY_MS = 6000
CMD_CACHE = 16

ROLE_M, ROLE_F, ROLE_E, ROLE_N = "M", "F", "E", "N"
LIGHT_BITS = {"G": 1, "Y": 2, "R": 4}


def lights_text(bits: int) -> str:
    return "".join(c for c, b in LIGHT_BITS.items() if bits & b) or "O"


def lights_bits(text: str) -> int:
    return 0 if text == "O" else sum(LIGHT_BITS[c] for c in text)


@dataclass
class _Master:
    master_id: int
    rank: int
    last: float
    prev: Optional[float] = None  # second most recent TIMER
    first: float = 0.0  # start of the current continuous run of frames
    src: bytes = b""
    timer: Optional[RadioTimer] = None
    rx_ms: float = 0.0
    sound_seq: Optional[int] = None  # last sound_seq acted on or recorded


@dataclass(frozen=True)
class SoundStart:
    t_ms: float
    count: int
    blast: int  # x10 ms
    gap: int  # x10 ms


@dataclass
class Peer:
    last: float
    rssi: int = 0


@dataclass
class Arbiter:
    role: str
    own_master_id: int = 0
    host_alive: bool = False
    host_lights: int = 0
    masters: dict[int, _Master] = field(default_factory=dict)
    followed: Optional[int] = None
    sounds: list[SoundStart] = field(default_factory=list)
    sound_stops: list[float] = field(
        default_factory=list
    )  # times of stops (count 0, new sound_seq)
    _pattern_end: float = -1.0  # end of the running pattern; negative = none
    peers: dict[bytes, Peer] = field(default_factory=dict)
    # master_id -> highest accepted session; "NVS": survives reboot()
    sessions: dict[int, int] = field(default_factory=dict)

    # --- inputs ---

    def reboot(self) -> None:
        """RAM state is lost, the persisted sessions are kept."""
        self.masters, self.followed, self.sounds, self.peers = {}, None, [], {}
        self.host_alive = False
        self.host_lights = 0

    def accept_session(self, master_id: int, session: int) -> bool:
        """Session rule (section 4): lower than the best accepted is dropped."""
        best = self.sessions.get(master_id, 0)
        if session < best:
            return False
        self.sessions[master_id] = session
        return True

    def set_host(self, alive: bool) -> None:
        self.host_alive = alive

    def set_host_lights(self, bits: int) -> None:
        self.host_lights = bits

    def on_hello(self, now: float, src: bytes) -> None:
        self.peers[src] = Peer(now)

    def on_timer(self, now: float, timer: RadioTimer, src: bytes = b"") -> None:
        if not self.accept_session(timer.master_id, timer.session):
            return  # replay of an older session: not heard, no outputs
        m = self.masters.get(timer.master_id)
        if m is None:
            m = _Master(timer.master_id, timer.rank, now, None, now, src)
            self.masters[timer.master_id] = m
        else:
            if now - m.last >= LIVE_MS:
                m.first = now  # a new continuous run
                m.prev = None
            else:
                m.prev = m.last
            m.last = now
        m.rank = timer.rank
        m.src = src
        m.timer = timer
        m.rx_ms = now
        self.tick(now)
        if self.followed == timer.master_id and self.role in (ROLE_E, ROLE_N):
            self._sound_from_timer(now, m, timer)

    def on_sound(self, now: float, sound: RadioSound) -> None:
        if not self.accept_session(sound.master_id, sound.session):
            return
        self.tick(now)
        if self.followed is None or sound.master_id != self.followed:
            return
        m = self.masters[self.followed]
        if m.sound_seq != sound.sound_seq:
            m.sound_seq = sound.sound_seq
            if sound.count:
                self._start(now, now, sound.count, sound.blast, sound.gap)
            else:
                self._stop(now)

    def _sound_from_timer(self, now: float, m: _Master, t: RadioTimer) -> None:
        if m.sound_seq is None:  # first TIMER of a newly followed master only records
            m.sound_seq = t.sound_seq
            return
        if t.sound_seq == m.sound_seq:
            return
        m.sound_seq = t.sound_seq
        if t.sound_count == 0:
            self._stop(now)  # a stop is the safe direction: no replay guard
        elif t.sound_age != NO_SOUND_AGE and t.sound_age < SOUND_REPLAY_GUARD_MS:
            self._start(now, now - t.sound_age, t.sound_count, t.sound_blast, t.sound_gap)

    def _start(self, now: float, began: float, count: int, blast: int, gap: int) -> None:
        self.sounds.append(SoundStart(now, count, blast, gap))
        self._pattern_end = began + count * blast * 10 + (count - 1) * gap * 10

    def _stop(self, now: float) -> None:
        self.sound_stops.append(now)
        self._pattern_end = -1.0

    def sound_active(self, now: float) -> bool:
        return now < self._pattern_end

    # --- following ---

    def _live(self, now: float, m: _Master) -> bool:
        return now - m.last < LIVE_MS

    @staticmethod
    def _best(cands: list[_Master]) -> _Master:
        return min(cands, key=lambda m: (-m.rank, m.master_id))

    def _set_followed(self, new: Optional[int]) -> None:
        if new != self.followed:
            self.followed = new
            if new is not None:
                self.masters[new].sound_seq = None  # a newly followed master only records

    def tick(self, now: float) -> None:
        """Re-evaluate the follow decision at ``now`` (the state is a function of time)."""
        for mac in [k for k, p in self.peers.items() if now - p.last >= PEER_EXPIRY_MS]:
            del self.peers[mac]
        if self.role == ROLE_M or self.role == ROLE_F:
            self._set_followed(None)
            return
        live = [m for m in self.masters.values() if self._live(now, m)]
        cur = self.masters.get(self.followed) if self.followed is not None else None
        if cur is None:
            self._set_followed(self._best(live).master_id if live else None)
            return
        others = [m for m in live if m.master_id != cur.master_id]
        if now - cur.last >= SWITCH_SILENCE_MS and others:
            self._set_followed(self._best(others).master_id)
        elif not self._live(now, cur) and not others:
            self._set_followed(None)
        else:
            higher = [m for m in others if m.rank > cur.rank and now - m.first >= SWITCH_RANK_MS]
            if higher:
                self._set_followed(self._best(higher).master_id)

    def follow(self, now: float) -> Optional[int]:
        self.tick(now)
        return self.followed

    def followed_timer(self, now: float) -> Optional[RadioTimer]:
        self.tick(now)
        m = self.masters.get(self.followed) if self.followed is not None else None
        return m.timer if m is not None and self._live(now, m) else None

    # --- outputs ---

    def failsafe(self, now: float) -> bool:
        if self.role in (ROLE_M, ROLE_F):
            return not self.host_alive
        return self.followed_timer(now) is None

    def lights(self, now: float) -> int:
        if self.failsafe(now):
            return LIGHT_BITS["R"]
        if self.role in (ROLE_M, ROLE_F):
            return self.host_lights
        t = self.followed_timer(now)
        assert t is not None
        if t.flags & FLAG_EMERGENCY:
            return LIGHT_BITS["R"]
        return t.lights

    def emergency(self, now: float) -> bool:
        t = self.followed_timer(now)
        return t is not None and bool(t.flags & FLAG_EMERGENCY)

    def tx_rank(self, now: float) -> int:
        if not self.host_alive:
            return 0
        return {ROLE_M: 2, ROLE_F: 1}.get(self.role, 0)

    def conflict(self, now: float) -> bool:
        active = {
            m.master_id
            for m in self.masters.values()
            if m.rank == 2
            and m.master_id != self.own_master_id
            and m.prev is not None
            and now - m.prev <= CONFLICT_ACTIVE_MS
        }
        if self.role == ROLE_M and self.host_alive:
            active.add(self.own_master_id)
        return len(active) >= 2

    def sound_started(self) -> int:
        return len(self.sounds)


# --- CMD gate (section 4, Commands) ---------------------------------------------------------


@dataclass
class CmdDecision:
    forward: bool  # hand to the host ($P,cmd)
    ack: Optional[int]  # result to send now (None = wait for the host)
    drop: bool = False


@dataclass
class RemoteEntry:
    mask: int
    last_counter: int = 0
    cache: dict[int, int] = field(default_factory=dict)  # counter -> result, small cache


@dataclass
class CmdGate:
    """Counter, permission and duplicate handling of the master node (keys: see the codec)."""

    remotes: dict[bytes, RemoteEntry] = field(default_factory=dict)

    def pair(self, mac: bytes, mask: int) -> None:
        self.remotes[mac] = RemoteEntry(mask)

    def unpair(self, mac: bytes) -> None:
        self.remotes.pop(mac, None)

    def decide(self, mac: bytes, counter: int, action: int, host_alive: bool) -> CmdDecision:
        r = self.remotes.get(mac)
        if r is None or not host_alive:
            return CmdDecision(False, None, drop=True)
        if counter in r.cache:  # duplicate: re-ACK from the cache, never forward twice
            res = r.cache[counter]
            return CmdDecision(False, res if res >= 0 else None)  # -1: host has not answered yet
        if counter <= r.last_counter:  # replay or stale
            return CmdDecision(False, None, drop=True)
        r.last_counter = counter
        if not mask_allows(r.mask, action):
            self._remember(r, counter, RESULT_DENIED)
            return CmdDecision(False, RESULT_DENIED)
        self._remember(r, counter, -1)  # pending until the host answers
        return CmdDecision(True, None)

    def host_result(self, mac: bytes, counter: int, result: int) -> None:
        r = self.remotes.get(mac)
        if r is not None:
            self._remember(r, counter, result)

    @staticmethod
    def _remember(r: RemoteEntry, counter: int, result: int) -> None:
        r.cache[counter] = result
        while len(r.cache) > CMD_CACHE:
            del r.cache[min(r.cache)]
