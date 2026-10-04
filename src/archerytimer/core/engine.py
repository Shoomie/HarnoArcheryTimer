"""Timer engine: a data-driven FSM with absolute deadlines.

The engine is single-threaded logic: callers feed it commands (``handle``) and call
``poll`` when ``next_due_ns`` has passed. ``EngineRunner`` (engine_runner.py) does that
in a thread. Phase boundaries are chained from the previous *deadline*, not from the
time the thread happened to wake, so late wake-ups never accumulate drift.

Events go to a single ``emit`` callback in this order per transition: hardware
(light, whistle/buzzer), then the state ``Snapshot``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Callable, Optional, Tuple

from archerytimer.common.clock import Clock
from archerytimer.core.models import (
    Buzzer,
    Command,
    EngineSettings,
    Event,
    Light,
    LightChange,
    Mode,
    PhaseSpec,
    Sequence,
    SessionConfig,
    Snapshot,
    Whistle,
)
from archerytimer.core.rules import apply_overrides
from archerytimer.core.scheduler import Scheduler

_NS_PER_MS = 1_000_000

# Scheduler item kinds
_PHASE_END = "phase_end"
_WARN = "warn"
_BUZZ = "buzz"
_AUTO_NEXT = "auto_next"

Item = Tuple[str, int]  # (kind, generation / payload)


class EngineError(ValueError):
    pass


class Engine:
    def __init__(
        self,
        clock: Clock,
        sequences: Mapping[str, Sequence],
        emit: Callable[[Event], None],
        settings: Optional[EngineSettings] = None,
        on_late: Optional[Callable[[str, int], None]] = None,
    ) -> None:
        self._clock = clock
        self._sequences = dict(sequences)
        self._emit = emit
        self._settings = settings or EngineSettings()
        self._on_late = on_late
        self._sched: Scheduler[Item] = Scheduler()
        self._buzz: Scheduler[Item] = Scheduler()  # host-timed blasts survive phase changes
        self._phase_gen = 0
        self._buzz_gen = 0
        self._seq = 0
        self._dirty = False

        self._config: Optional[SessionConfig] = None
        self._sequence: Optional[Sequence] = None
        self._mode = Mode.IDLE
        self._round = 0
        self._phase_idx = 0
        self._phase_start = 0
        self._deadline = 0
        self._paused = False
        self._remaining_at_pause = 0
        self._light = Light.RED
        self._emergency = False
        self._link = "unknown"

    # ------------------------------------------------------------------ public

    @property
    def settings(self) -> EngineSettings:
        return self._settings

    def next_due_ns(self) -> Optional[int]:
        a, b = self._sched.next_due(), self._buzz.next_due()
        if a is None or b is None:
            return a if b is None else b
        return min(a, b)

    def snapshot(self) -> Snapshot:
        cfg = self._config
        n_groups = len(cfg.groups) if cfg else 1
        total_rounds = self._total_rounds()
        end_idx = self._round // n_groups
        practice = bool(cfg) and end_idx < cfg.practice_ends  # type: ignore[union-attr]
        if cfg is None:
            end_no, total_ends = 0, 0
        elif practice:
            end_no, total_ends = end_idx + 1, cfg.practice_ends
        else:
            end_no, total_ends = end_idx - cfg.practice_ends + 1, cfg.total_ends
        phase = self._phase()
        return Snapshot(
            seq=self._seq,
            mode=self._mode,
            sequence_id=cfg.sequence_id if cfg else "",
            phase_id=phase.id if phase else "",
            phase_start_ns=self._phase_start,
            deadline_ns=self._deadline,
            paused=self._paused,
            remaining_at_pause_ns=self._remaining_at_pause,
            light=self._light,
            group=self._group(),
            end_no=min(end_no, total_ends) if self._mode is Mode.FINISHED else end_no,
            total_ends=total_ends,
            practice=practice,
            round_index=self._round,
            total_rounds=total_rounds,
            emergency=self._emergency,
            link=self._link,
            planned_ns=max((p.duration_ns for p in self._sequence.phases), default=0)
            if self._sequence
            else 0,
        )

    def configure(self, config: SessionConfig) -> None:
        """Set up a new session. Only allowed when no round is running."""
        if self._mode is Mode.RUNNING or self._emergency:
            raise EngineError("cannot configure while a round is running")
        if config.sequence_id not in self._sequences:
            raise EngineError(f"unknown sequence {config.sequence_id!r}")
        if (
            not config.groups
            or config.total_ends < 0
            or config.practice_ends < 0
            or config.total_ends + config.practice_ends < 1
        ):
            raise EngineError("invalid session config")
        self._sched.clear()
        self._config = config
        self._sequence = apply_overrides(
            self._sequences[config.sequence_id], config.prep_ns, config.shoot_ns, config.warn_ns
        )
        self._round = 0
        self._phase_idx = 0
        self._paused = False
        self._mode = Mode.WAITING
        self._set_light(Light.RED)
        self._publish()

    def set_link(self, status: str) -> None:
        if status != self._link:
            self._link = status
            self._dirty = True
            self._publish()

    def handle(self, cmd: Command) -> None:
        """Apply an operator command. Unknown or inapplicable commands are ignored."""
        now = self._clock.now_ns()
        name = cmd.name
        if name == "link":  # from the serial worker, routed through the engine thread
            self.set_link(str(cmd.args.get("status", "unknown")))
        elif name == "settings":
            self._apply_settings(cmd.args)
        elif name == "emergency":
            self._emergency_stop(now)
        elif name == "clear_emergency":
            self._clear_emergency(now, restart=cmd.args.get("mode") == "restart")
        elif self._emergency:
            pass  # everything else is locked out until the emergency is cleared
        elif name == "configure":
            cfg = cmd.args.get("config")
            if isinstance(cfg, SessionConfig):
                self.configure(cfg)
        elif name == "primary":
            self._primary(now)
        elif name == "start":
            self._start_round(now)
        elif name == "pause":
            self._pause(now)
        elif name == "resume":
            self._resume(now)
        elif name == "stop_end":
            self._stop_end(now)
        elif name == "next":
            self._skip(now)
        elif name == "back":
            self._back()
        elif name == "reset":
            self._reset()
        self._publish()

    def _apply_settings(self, args: Mapping[str, object]) -> None:
        changes: dict[str, object] = {}
        for key in ("emergency_blasts", "blast_ms", "gap_ms"):
            if isinstance(args.get(key), int) and int(args[key]) >= 0:  # type: ignore[call-overload]
                changes[key] = args[key]
        if args.get("whistle_timing") in ("mcu", "host"):
            changes["whistle_timing"] = args["whistle_timing"]
        if (
            isinstance(args.get("pause_light"), str)
            and str(args["pause_light"]) in Light.__members__
        ):
            changes["pause_light"] = Light[str(args["pause_light"])]
        if changes:
            self._settings = replace(self._settings, **changes)  # type: ignore[arg-type]

    def poll(self) -> None:
        """Fire every overdue event, in order. Call whenever ``next_due_ns`` has passed."""
        now = self._clock.now_ns()
        while True:
            sd, bd = self._sched.next_due(), self._buzz.next_due()
            if sd is not None and sd <= now and (bd is None or sd <= bd):
                due = self._sched.pop_due(now)
            else:
                due = self._buzz.pop_due(now)
            if due is None:
                break
            when, (kind, payload) = due
            late = now - when
            if self._on_late and late > self._settings.late_threshold_ns:
                self._on_late(kind, late)
            if kind == _PHASE_END and payload == self._phase_gen:
                self._enter_next_phase(when)
            elif kind == _WARN and payload == self._phase_gen:
                self._warn()
            elif kind == _BUZZ and payload & 0xFFFF == self._buzz_gen:
                self._emit(Buzzer(bool(payload >> 16)))
            elif kind == _AUTO_NEXT and payload == self._phase_gen:
                self._start_round(when)
        self._publish()

    def shutdown(self) -> None:
        """Fail-safe: RED and silence, whatever the state."""
        self._sched.clear()
        self._buzz.clear()
        self._buzz_gen += 1
        self._emit(LightChange(Light.RED))
        self._emit(Whistle(0, 0, 0))
        self._emit(Buzzer(False))

    # ------------------------------------------------------------ transitions

    def _primary(self, now: int) -> None:
        """The one obvious action: start the waiting round, or resume a paused one.

        Used by keyboards, clickers, button boxes and GPIO alike, so every input device
        agrees on what "next" means. Never acts during an emergency or mid-round.
        """
        if self._mode is Mode.WAITING:
            self._start_round(now)
        elif self._mode is Mode.RUNNING and self._paused:
            self._resume(now)

    def _start_round(self, now: int) -> None:
        if self._mode is not Mode.WAITING or self._sequence is None:
            return
        self._mode = Mode.RUNNING
        self._begin_phase(0, now)

    def _begin_phase(self, idx: int, start_ns: int) -> None:
        spec = self._sequence.phases[idx]  # type: ignore[union-attr]
        self._phase_gen += 1
        self._phase_idx = idx
        self._phase_start = start_ns
        self._deadline = start_ns + spec.duration_ns
        self._paused = False
        self._set_light(spec.light)
        if spec.whistle_on_start:
            self._whistle(spec.whistle_on_start, start_ns)
        if spec.duration_ns == 0:
            self._complete_round(start_ns)
            return
        self._schedule_phase(spec, self._deadline, self._deadline - start_ns)

    def _schedule_phase(self, spec: PhaseSpec, deadline: int, remaining: int) -> None:
        self._sched.push(deadline, (_PHASE_END, self._phase_gen))
        if spec.warn_at_ns is not None and spec.warn_at_ns < spec.duration_ns:
            if remaining <= spec.warn_at_ns:
                self._set_light(spec.warn_light)
            else:
                self._sched.push(deadline - spec.warn_at_ns, (_WARN, self._phase_gen))

    def _enter_next_phase(self, at_ns: int) -> None:
        nxt = self._phase_idx + 1
        if nxt >= len(self._sequence.phases):  # type: ignore[union-attr]
            self._complete_round(at_ns)
        else:
            self._begin_phase(nxt, at_ns)

    def _warn(self) -> None:
        self._set_light(self._phase().warn_light)  # type: ignore[union-attr]

    def _complete_round(self, at_ns: int) -> None:
        """Round over: light is already RED from the END phase."""
        self._phase_gen += 1
        self._deadline = at_ns
        self._advance_round(at_ns, auto=True)

    def _advance_round(self, at_ns: int, auto: bool) -> None:
        self._paused = False
        if self._round + 1 >= self._total_rounds():
            self._mode = Mode.FINISHED
            return
        self._round += 1
        self._mode = Mode.WAITING
        cfg = self._config
        if auto and cfg is not None and cfg.auto_advance:
            self._sched.push(at_ns + cfg.auto_advance_delay_ns, (_AUTO_NEXT, self._phase_gen))

    def _stop_end(self, now: int) -> None:
        """Operator stop: jump to the last phase (normally END: RED + 3 blasts)."""
        if self._mode is not Mode.RUNNING:
            return
        self._sched.clear()
        self._begin_phase(len(self._sequence.phases) - 1, now)  # type: ignore[union-attr]

    def _skip(self, now: int) -> None:
        if self._mode is Mode.RUNNING:
            self._cancel_phase()
            self._set_light(Light.RED)
            self._whistle(0, now)
            self._advance_round(now, auto=False)
        elif self._mode is Mode.WAITING:
            self._phase_gen += 1  # drop a pending auto-advance
            self._sched.clear()
            self._advance_round(now, auto=False)

    def _back(self) -> None:
        if self._mode is Mode.WAITING and self._round > 0:  # FINISHED: use reset
            self._phase_gen += 1
            self._sched.clear()
            self._round -= 1

    def _reset(self) -> None:
        self._cancel_phase()
        self._whistle(0, 0)
        self._round = 0
        self._phase_idx = 0
        self._paused = False
        self._mode = Mode.WAITING if self._config else Mode.IDLE
        self._set_light(Light.RED)

    def _pause(self, now: int) -> None:
        if self._mode is not Mode.RUNNING or self._paused:
            return
        self._sched.clear()
        self._phase_gen += 1
        self._remaining_at_pause = max(0, self._deadline - now)
        self._paused = True
        self._set_light(self._settings.pause_light)

    def _resume(self, now: int) -> None:
        if self._mode is not Mode.RUNNING or not self._paused:
            return
        self._resume_phase(now)

    def _resume_phase(self, now: int) -> None:
        spec = self._phase()
        assert spec is not None
        self._paused = False
        self._phase_gen += 1
        self._deadline = now + self._remaining_at_pause
        self._phase_start = self._deadline - spec.duration_ns
        self._set_light(spec.light)
        self._schedule_phase(spec, self._deadline, self._remaining_at_pause)

    def _emergency_stop(self, now: int) -> None:
        if self._emergency:
            return
        if self._mode is Mode.RUNNING and not self._paused:
            self._remaining_at_pause = max(0, self._deadline - now)
        elif self._mode is not Mode.RUNNING:
            self._remaining_at_pause = 0
        self._cancel_phase()
        self._emergency = True
        self._set_light(Light.RED)
        self._whistle(self._settings.emergency_blasts, now)

    def _clear_emergency(self, now: int, restart: bool) -> None:
        if not self._emergency:
            return
        self._emergency = False
        self._whistle(0, now)
        if self._mode is Mode.RUNNING and not restart:
            self._paused = True  # resumes via an explicit "resume"; light stays RED
            self._set_light(self._settings.pause_light)
        else:
            self._paused = False
            if self._mode is Mode.RUNNING:
                self._mode = Mode.WAITING  # same round again
            self._set_light(Light.RED)

    # ---------------------------------------------------------------- helpers

    def _cancel_phase(self) -> None:
        self._sched.clear()
        self._phase_gen += 1

    def _phase(self) -> Optional[PhaseSpec]:
        if self._sequence is None:
            return None
        return self._sequence.phases[self._phase_idx]

    def _total_rounds(self) -> int:
        cfg = self._config
        if cfg is None:
            return 0
        return (cfg.practice_ends + cfg.total_ends) * len(cfg.groups)

    def _group(self) -> str:
        cfg = self._config
        if cfg is None:
            return ""
        n = len(cfg.groups)
        end_idx, slot = divmod(self._round, n)
        shift = end_idx if cfg.alternate_order else 0
        return cfg.groups[(slot + shift) % n]

    def _set_light(self, light: Light) -> None:
        if light is not self._light:
            self._light = light
            self._emit(LightChange(light))
        self._dirty = True

    def _whistle(self, count: int, at_ns: int) -> None:
        s = self._settings
        self._dirty = True
        if s.whistle_timing == "mcu":
            self._emit(Whistle(count, s.blast_ms, s.gap_ms))
            return
        self._buzz_gen += 1
        self._buzz.clear()
        self._emit(Buzzer(False))
        gen = self._buzz_gen & 0xFFFF
        t = at_ns
        for _ in range(count):
            self._buzz.push(t, (_BUZZ, (1 << 16) | gen))
            t += s.blast_ms * _NS_PER_MS
            self._buzz.push(t, (_BUZZ, gen))
            t += s.gap_ms * _NS_PER_MS

    def _publish(self) -> None:
        if self._dirty:
            self._dirty = False
            self._seq += 1
            self._emit(self.snapshot())
