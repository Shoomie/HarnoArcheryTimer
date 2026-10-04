"""Radio-fed follower core: a software instance whose timer comes from the ESP32 mesh.

The MCU runs in serial role ``E`` (``docs/mesh.md`` section 6): it follows a master over the radio,
drives its *own* lights and sound, and forwards the radio frames to this host as ``$F`` (TIMER),
``$W`` (SOUND) and ``$J`` (SESSION). This class turns those frames back into the same
``Snapshot`` a leader's engine would publish, so the local UI needs no special case:

- deadlines are local: receive time plus ``remaining_ms`` (a paused or emergency phase keeps a
  fixed deadline and reports ``remaining_at_pause_ns``); no clock offset is involved;
- mode, phase, light, group, end and round come from TIMER plus the SESSION (sequence id, groups);
  without a matching SESSION the node reports "waiting for the main timer" (an idle, RED snapshot);
- no TIMER for 1 s: the link goes ``upstream=down`` and the snapshot light is RED (the MCU does the
  same on its outputs, so this class never writes lights or sound);
- commands from the UI and buttons are sent as ``$P,tx,<action>`` for the seven remote actions only;
  everything else is refused with a log line (the radio protocol has no reset, settings, ...).
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Mapping
from dataclasses import replace
from typing import Callable, Optional, Protocol, Union

from archerytimer.common.clock import NS_PER_MS, NS_PER_S, Clock
from archerytimer.core.models import Command, Light, Mode, Sequence, Snapshot, Whistle
from archerytimer.core.rules import apply_overrides
from archerytimer.hardware.mesh_types import (
    ACTION_CODES,
    FLAG_EMERGENCY,
    FLAG_PAUSED,
    KEEP,
    MODES,
    NO_SOUND_AGE,
    FeedSession,
    FeedSound,
    FeedTimer,
    MeshStatus,
    RadioSession,
    RadioSound,
    RadioTimer,
)
from archerytimer.hardware.serial_worker import LINK_UP
from archerytimer.ipc.messages import Message, link_msg, state_msg
from archerytimer.ipc.server import IpcServer
from archerytimer.ipc.transport import Listener

log = logging.getLogger("archerytimer.meshfollower")

FEED_GRACE_NS = NS_PER_S  # no TIMER for this long: RED, upstream down
SOUND_REPLAY_GUARD_MS = 400  # a sound seen in TIMER starts only if younger than this
JITTER_NS = 100 * NS_PER_MS  # deadline estimates closer than this are the same phase
_LIGHT_BITS = ((1, Light.GREEN), (2, Light.YELLOW), (4, Light.RED))

Feed = Union[FeedTimer, FeedSound, FeedSession]


class PairTx(Protocol):
    """What this class needs from the serial worker (WP-D): send a remote action over the radio."""

    def send_pair_tx(self, action: int) -> None: ...


def _light(bits: int) -> Light:
    for bit, light in _LIGHT_BITS:
        if bits & bit:
            return light
    return Light.RED  # nothing lit or unknown: the safe state


class MeshFollower:
    def __init__(
        self,
        clock: Clock,
        listener: Listener,
        sequences: Mapping[str, Sequence],
        tx: PairTx,
        *,
        serial_link: Callable[[], str] = lambda: LINK_UP,
        on_sound: Optional[Callable[[Whistle], None]] = None,
        version: str = "0.0.1",
        local_handler: Optional[Callable[[Message], bool]] = None,
    ) -> None:
        """``serial_link`` reports the MCU serial link (``up``/``down``). ``on_sound`` is optional:
        pass ``audio.submit`` to also play radio sounds on this host's speakers (the MCU already
        sounds its own horn)."""
        self._clock = clock
        self._sequences = dict(sequences)
        self._tx = tx
        self._serial_link = serial_link
        self._on_sound = on_sound
        self._local_handler = local_handler
        self.server = IpcServer(
            listener,
            {
                "type": "hello",
                "v": 1,
                "version": version,
                "caps": ["state", "cmd"],
                "sequences": {},
            },
            self._on_local_message,
            clock,
        )
        self._lock = threading.RLock()
        self._timer: Optional[RadioTimer] = None
        self._session: Optional[RadioSession] = None
        self._last_timer_ns = 0
        self._feed_ok = False
        self._status: Optional[MeshStatus] = None
        self._seq = 0
        self._key: Optional[tuple[object, ...]] = None
        self._deadline = 0
        self._last_sound: Optional[tuple[int, int]] = None  # (master_id, sound_seq)
        self._last_snap: Optional[Snapshot] = None
        self._stop = threading.Event()
        self._watchdog: Optional[threading.Thread] = None

    # ---------------------------------------------------------------- lifecycle

    def start(self) -> None:
        self.server.start()
        self._publish_all()
        self._watchdog = threading.Thread(target=self._watch, name="mesh-feed-watchdog")
        self._watchdog.start()

    def stop(self) -> None:
        self._stop.set()
        if self._watchdog:
            self._watchdog.join(timeout=2.0)
        self.server.stop()

    # ---------------------------------------------------------------- from the serial worker

    def on_feed(self, frame: Feed) -> None:
        """A ``$F`` / ``$W`` / ``$J`` frame from the MCU (serial reader thread). Never raises."""
        try:
            if isinstance(frame, FeedTimer):
                self._on_timer(RadioTimer.from_bytes(frame.payload))
            elif isinstance(frame, FeedSound):
                self._on_sound_frame(RadioSound.from_bytes(frame.payload))
            elif isinstance(frame, FeedSession):
                self._on_session(RadioSession.from_bytes(frame.payload))
        except ValueError as exc:
            log.warning("bad radio feed frame ignored: %s", exc)

    def on_status(self, status: MeshStatus) -> None:
        """``$O`` from the MCU."""
        with self._lock:
            self._status = status
        self._publish_link()

    def on_serial_link(self, _state: str = "") -> None:
        self._publish_link()

    def _on_timer(self, t: RadioTimer) -> None:
        now = self._clock.now_ns()
        with self._lock:
            self._timer = t
            self._last_timer_ns = now
            came_up = not self._feed_ok
            self._feed_ok = True
            self._sound_from_timer(t)
            snap = self._build(now)
        if came_up:
            self._publish_link()
        self._publish(snap)

    def _on_session(self, s: RadioSession) -> None:
        with self._lock:
            changed = s != self._session
            self._session = s
            if changed:
                log.info("session rev %d: %s, groups %s", s.rev, s.sequence_id, s.groups)
            snap = self._build(self._clock.now_ns()) if self._timer else None
        if snap is not None:
            self._publish(snap)

    def _on_sound_frame(self, s: RadioSound) -> None:
        with self._lock:
            key = (s.master_id, s.sound_seq)
            if key == self._last_sound:
                return
            self._last_sound = key
        self._play(s.count, s.blast, s.gap)

    def _sound_from_timer(self, t: RadioTimer) -> None:
        """A sound that started just before we heard it counts; an old one never does."""
        key = (t.master_id, t.sound_seq)
        if key == self._last_sound:
            return
        first = self._last_sound is None
        self._last_sound = key
        if first or t.sound_age == NO_SOUND_AGE or t.sound_age >= SOUND_REPLAY_GUARD_MS:
            return
        self._play(t.sound_count, t.sound_blast, t.sound_gap)

    def _play(self, count: int, blast: int, gap: int) -> None:
        if self._on_sound is not None and count:
            self._on_sound(Whistle(count, blast * 10, gap * 10))

    # ---------------------------------------------------------------- snapshot

    @property
    def waiting_for_main_timer(self) -> bool:
        """No TIMER with a matching SESSION yet: the UI shows 'waiting for main timer'."""
        with self._lock:
            return self._resolve() is None

    def _resolve(self) -> Optional[tuple[RadioTimer, RadioSession, Sequence]]:
        t, s = self._timer, self._session
        if t is None or s is None:
            return None
        if s.master_id != t.master_id or s.rev != t.session_rev:
            return None  # session_rev changed: wait for the new SESSION (repeats every 2 s)
        base = self._sequences.get(s.sequence_id)
        if base is None:
            return None
        seq = apply_overrides(
            base,
            None if s.prep_ms == KEEP else s.prep_ms * NS_PER_MS,
            None if s.shoot_ms == KEEP else s.shoot_ms * NS_PER_MS,
            None if s.warn_ms == KEEP else s.warn_ms * NS_PER_MS,
        )
        return t, s, seq

    def _build(self, now: int) -> Snapshot:
        """The snapshot for the newest TIMER (call under the lock)."""
        resolved = self._resolve()
        t = self._timer
        if resolved is None or t is None:
            self._key = None
            self._deadline = now
            return self._finish(
                Snapshot(
                    0,
                    Mode.IDLE,
                    "",
                    "",
                    now,
                    now,
                    False,
                    0,
                    Light.RED,
                    "",
                    0,
                    0,
                    False,
                    0,
                    0,
                    False,
                    self._serial_link(),
                )
            )
        _, s, seq = resolved
        paused = bool(t.flags & FLAG_PAUSED)
        emergency = bool(t.flags & FLAG_EMERGENCY)
        mode = Mode(MODES[t.mode]) if t.mode < len(MODES) else Mode.IDLE
        idx = min(t.phase, len(seq.phases) - 1)
        spec = seq.phases[idx]
        rem_ns = t.remaining_ms * NS_PER_MS
        frozen = paused or emergency
        key = (t.master_id, t.session_rev, mode, idx, t.round, paused, emergency)
        running = mode is Mode.RUNNING
        candidate = now + rem_ns if running else now
        # TIMER repeats share one remaining_ms, so later copies look later: keep the earliest
        # estimate, but follow a real jump (a phase that was extended, a resync).
        moved = candidate < self._deadline or candidate - self._deadline > JITTER_NS
        if key != self._key or (running and not frozen and moved):
            self._deadline = candidate
        self._key = key
        deadline = self._deadline
        n = max(1, len(s.groups))
        practice = (t.round // n) < s.practice_ends
        group = s.groups[t.group] if t.group < len(s.groups) else ""
        snap = Snapshot(
            seq=0,
            mode=mode,
            sequence_id=s.sequence_id,
            phase_id=spec.id,
            phase_start_ns=deadline - spec.duration_ns if running else deadline,
            deadline_ns=deadline,
            paused=paused,
            remaining_at_pause_ns=rem_ns if frozen and running else 0,
            light=_light(t.lights),
            group=group,
            end_no=t.end_no,
            total_ends=t.total_ends,
            practice=practice,
            round_index=t.round,
            total_rounds=t.total_rounds,
            emergency=emergency,
            link=self._serial_link(),
            planned_ns=max((p.duration_ns for p in seq.phases), default=0),
        )
        return self._finish(snap)

    def _finish(self, snap: Snapshot) -> Snapshot:
        if not self._feed_ok:
            snap = replace(snap, light=Light.RED)
        return snap

    def _publish(self, snap: Snapshot) -> None:
        """Publish when something visible changed; ``seq`` counts published changes."""
        with self._lock:
            last = self._last_snap
            if last is not None and replace(last, seq=0) == snap:
                return
            self._seq += 1
            snap = replace(snap, seq=self._seq)
            self._last_snap = snap
        self.server.publish(state_msg(snap))

    def _publish_all(self) -> None:
        with self._lock:
            snap = self._build(self._clock.now_ns())
        self._publish_link()
        self._publish(snap)

    def _publish_link(self) -> None:
        with self._lock:
            up = self._feed_ok
            st = self._status
        self.server.publish(
            link_msg(
                self._serial_link(),
                espnow={"mode": "follow", "peers": st.peers, "src": st.src} if st else None,
                upstream="up" if up else "down",
                via="radio",
            )
        )

    # ---------------------------------------------------------------- watchdog

    def check(self) -> None:
        """Fail safe: no TIMER for 1 s means RED and upstream down (the MCU does the same)."""
        with self._lock:
            if not self._feed_ok or self._clock.now_ns() - self._last_timer_ns < FEED_GRACE_NS:
                return
            log.warning("radio timer feed lost: showing RED")
            self._feed_ok = False
            self._key = None
            snap = self._build(self._clock.now_ns()) if self._timer else None
            if snap is not None and self._last_snap is not None:
                # keep what was on screen (mode, phase, ...) but RED, deadline untouched
                snap = replace(self._last_snap, light=Light.RED)
        self._publish_link()
        if snap is not None:
            self._publish(snap)

    def _watch(self) -> None:
        while not self._stop.wait(0.1):
            self.check()

    # ---------------------------------------------------------------- from local clients

    def _on_local_message(self, msg: Message) -> None:
        kind = msg.get("type")
        if self._local_handler is not None and self._local_handler(msg):
            return  # node role, sound and pairing settings belong to this device
        if kind == "cmd":
            self.forward(str(msg.get("name", "")), dict(msg.get("args") or {}))
        elif kind == "settings":
            log.info("settings are not allowed from a radio follower; ignored")

    def forward_command(self, cmd: Command) -> None:
        """For ``ButtonMap``: same path as an IPC command."""
        self.forward(cmd.name, dict(cmd.args))

    def forward(self, name: str, args: Optional[Mapping[str, object]] = None) -> bool:
        action = ACTION_CODES.get(name)
        if action is None:
            log.warning("command %r is not allowed from a radio follower", name)
            return False
        try:
            self._tx.send_pair_tx(action)
        except Exception:  # a dead serial link must not take the service down
            log.exception("could not send %s over the radio", name)
            return False
        return True


__all__ = ["MeshFollower", "PairTx"]
