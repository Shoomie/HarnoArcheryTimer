"""Serial v2 on the simulated device and in the serial worker."""

from __future__ import annotations

import time
from typing import Callable

import pytest

from archerytimer.core.models import Whistle as EngineWhistle
from archerytimer.hardware.mesh_types import (
    Config,
    ConfigQuery,
    FeedSound,
    FeedTimer,
    MeshStatus,
    PairAccept,
    PairAck,
    PairClose,
    PairDelete,
    PairOpen,
    PairReject,
    PairRequest,
    PairState,
    PairTx,
    RemoteCommand,
    Role,
    RosterEntry,
    RosterGone,
    SessionInfo,
    TimerState,
)
from archerytimer.hardware.protocol import (
    FrameParser,
    Hello,
    HelloReply,
    ProtocolError,
    Whistle,
    encode,
)
from archerytimer.hardware.serial_worker import LINK_UP, SerialWorker
from archerytimer.hardware.sim_device import SimDevice, SimDeviceRunner, memory_port_pair

V2_CAPS = "LSBGTKWR"
MAC = "AABBCCDDEEFF"
TIMER = TimerState(1, 2, 87300, 3, 12, 0, 1, 4, 0, 5)
SESSION = SessionInfo(5, True, False, 12, 2, 0xFFFFFFFF, 0xFFFFFFFF, 0, 5000, "indoor_18", ("AB",))


def wait_for(cond: Callable[[], bool], timeout: float = 2.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.005)
    return cond()


def replies(dev: SimDevice, *frames: object) -> list[object]:
    parser = FrameParser()
    return parser.feed(dev.feed(b"".join(encode(f) for f in frames)))  # type: ignore[arg-type]


# --- simulated device ------------------------------------------------------------------------


def test_sim_reports_proto_2_with_cap_r() -> None:
    (reply,) = replies(SimDevice(caps=V2_CAPS), Hello())
    assert reply == HelloReply(2, "sim-0.1.0", V2_CAPS)


def test_sim_without_r_is_proto_1_and_rejects_v2_frames() -> None:
    dev = SimDevice()
    (err,) = replies(dev, Role("N"))
    assert getattr(err, "code", "") == "UC"
    assert dev.role is None


def test_sim_stores_config_and_echoes_it() -> None:
    dev = SimDevice(caps=V2_CAPS)
    assert replies(dev, Config("chan", "6")) == [Config("chan", "6")]
    assert replies(dev, Config("mkey", "0" * 32)) == [Config("mkey", "0" * 32)]
    out = replies(dev, ConfigQuery())
    assert Config("chan", "6") in out
    assert not any(isinstance(c, Config) and c.key == "mkey" for c in out)
    assert dev.mkey == "0" * 32


def test_sim_bad_config_is_an_error() -> None:
    dev = SimDevice(caps=V2_CAPS)
    out = FrameParser().feed(dev.feed(b"$C,chan,0*77\n"))
    assert isinstance(out[0], ProtocolError) is False
    assert getattr(out[0], "code", "") == "BA"


def test_sim_records_role_timer_session_pairing_and_whistle_timing() -> None:
    dev = SimDevice(caps=V2_CAPS)
    frames = [PairOpen(30), PairAccept(MAC, 0x7F), PairTx(4)]
    replies(dev, Role("M", 0xABCD, 7), TIMER, SESSION, *frames, Whistle(2, 9, 400, 600))
    assert dev.role == Role("M", 0xABCD, 7)
    assert dev.timer_state == TIMER and dev.session == SESSION
    assert dev.pairing == frames
    assert dev.whistle_timing == (400, 600) and dev.sound_events == [2]


def test_sim_emit_queues_mcu_frames() -> None:
    dev = SimDevice(caps=V2_CAPS)
    status = MeshStatus("M", "H", 2, False, 0xABCD, 1)
    dev.emit(status)
    dev.emit(RemoteCommand(MAC, 7, 1))
    assert FrameParser().feed(dev.take_pending()) == [status, RemoteCommand(MAC, 7, 1)]


# --- serial worker ---------------------------------------------------------------------------


class Rig:
    def __init__(self, device: SimDevice, **kw: object) -> None:
        self.device = device
        self.cb: dict[str, list[object]] = {
            k: [] for k in ("status", "roster", "feed", "pair", "cmd")
        }
        self.runners: list[SimDeviceRunner] = []
        self.worker = SerialWorker(
            self._factory,
            heartbeat_s=0.03,
            ack_timeout_s=0.3,
            backoff_s=(0.02,),
            on_mesh_status=self.cb["status"].append,
            on_roster=self.cb["roster"].append,
            on_feed=self.cb["feed"].append,
            on_pairing=self.cb["pair"].append,
            on_remote_command=self.cb["cmd"].append,
            **kw,  # type: ignore[arg-type]
        )

    def _factory(self):  # type: ignore[no-untyped-def]
        host, dev = memory_port_pair()
        self.runners.append(SimDeviceRunner(self.device, dev).start())
        return host

    def sent(self, letter: str) -> list[bytes]:
        return [
            e.data
            for e in list(self.device.log)
            if e.direction == "rx" and e.data[1:2] == letter.encode()
        ]

    def __enter__(self) -> Rig:
        self.worker.start()
        assert wait_for(lambda: self.worker.link == LINK_UP)
        return self

    def __exit__(self, *exc: object) -> None:
        self.worker.stop()
        for r in self.runners:
            r.stop()


def test_connect_sends_role_and_stored_config() -> None:
    dev = SimDevice(caps=V2_CAPS)
    with Rig(dev, role=Role("M", 0xABCD, 7), config={"chan": "6", "name": "Line-1"}) as rig:
        assert wait_for(lambda: dev.role == Role("M", 0xABCD, 7))
        assert wait_for(lambda: dev.config["chan"] == "6" and dev.config["name"] == "Line-1")
        assert rig.worker.mesh
        assert wait_for(lambda: rig.worker.device_config.get("chan") == "6")


def test_set_session_resends_role_while_running() -> None:
    dev = SimDevice(caps=V2_CAPS)
    with Rig(dev, role=Role("M", 0xABCD, 7)) as rig:
        assert wait_for(lambda: dev.role == Role("M", 0xABCD, 7))
        rig.worker.set_session(8)
        assert wait_for(lambda: dev.role == Role("M", 0xABCD, 8))


def test_on_connect_bumps_session_before_role_is_sent() -> None:
    dev = SimDevice(caps=V2_CAPS)
    counter = [7]

    def bump(role: Role) -> Role:
        counter[0] += 1
        return Role(role.role, role.master_id, counter[0])

    with Rig(dev, role=Role("M", 0xABCD, 7), on_connect=bump):
        assert wait_for(lambda: dev.role == Role("M", 0xABCD, 8))
        dev.role = None
        dev.session = None
    # a node without a master id (role E) is not offered to the hook
    dev2 = SimDevice(caps=V2_CAPS)
    with Rig(dev2, role=Role("E"), on_connect=bump):
        assert wait_for(lambda: dev2.role == Role("E"))
    assert counter[0] == 8


def test_default_role_is_none() -> None:
    dev = SimDevice(caps=V2_CAPS)
    with Rig(dev):
        assert wait_for(lambda: dev.role == Role("N"))


def test_proto_1_device_gets_no_v2_frames() -> None:
    dev = SimDevice(caps="LSBGTW")  # W but no R: proto 1
    with Rig(dev, role=Role("E"), config={"chan": "6"}) as rig:
        w = rig.worker
        w.send_timer_state(TIMER)
        w.send_session(SESSION)
        w.pair_open(30)
        w.set_config("chan", "7")
        w.set_role(Role("N"))
        w.query_config()
        w.submit(EngineWhistle(2, 500, 500))
        assert wait_for(lambda: dev.sound_events == [2])
        assert wait_for(lambda: (dev.last_heartbeat_seq or 0) >= 4)
        assert not w.mesh
        assert dev.whistle_timing is None
        for letter in "RCQUJP":
            assert rig.sent(letter) == []
        assert any(b.startswith(b"$S,2,") and b.count(b",") == 2 for b in rig.sent("S"))


def test_mesh_frames_become_typed_callbacks() -> None:
    dev = SimDevice(caps=V2_CAPS)
    with Rig(dev) as rig:
        frames = [
            MeshStatus("F", "H", 3, True, 0xABCD, 6),
            RosterEntry(MAC, "R", "K", 60, "1.2.3", "Finish"),
            RosterGone(MAC),
            FeedTimer(bytes(range(29))),
            FeedSound(bytes(range(12))),
            PairRequest(MAC, "Finish", "K"),
            PairState(True, 40),
            RemoteCommand(MAC, 7, 3),
        ]
        for f in frames:
            dev.emit(f)
        assert wait_for(lambda: len(rig.cb["cmd"]) == 1)
        assert rig.cb["status"] == [frames[0]] and rig.worker.mesh_status == frames[0]
        assert rig.cb["roster"] == frames[1:3]
        assert rig.cb["feed"] == frames[3:5]
        assert rig.cb["pair"] == frames[5:7]
        assert rig.cb["cmd"] == [frames[7]]


def test_timer_and_session_are_sent_and_repeated() -> None:
    dev = SimDevice(caps=V2_CAPS)
    with Rig(dev) as rig:
        rig.worker.send_timer_state(TIMER)
        rig.worker.send_session(SESSION)
        assert wait_for(lambda: dev.timer_state is not None and dev.session == SESSION)
        assert wait_for(lambda: len(rig.sent("U")) >= 4)  # change plus heartbeat repeats
        # The repeats count the remaining time down while running.
        assert dev.timer_state is not None and dev.timer_state.remaining_ms <= TIMER.remaining_ms
        assert len(rig.sent("J")) >= 1


def test_paused_timer_repeats_unchanged() -> None:
    dev = SimDevice(caps=V2_CAPS)
    paused = TimerState(1, 2, 5000, 1, 1, 0, 0, 0, 1, 1)
    with Rig(dev) as rig:
        rig.worker.send_timer_state(paused)
        assert wait_for(lambda: len(rig.sent("U")) >= 4)
        assert dev.timer_state == paused


def test_state_is_restored_after_reconnect() -> None:
    dev = SimDevice(caps=V2_CAPS)
    with Rig(dev, role=Role("E")) as rig:
        rig.worker.send_session(SESSION)
        assert wait_for(lambda: dev.session == SESSION)
        dev.session = None
        dev.role = None
        rig.worker.stop()
        rig.worker = SerialWorker(rig._factory, heartbeat_s=0.03, ack_timeout_s=0.3, role=Role("E"))
        rig.worker.send_session(SESSION)
        rig.worker.start()
        assert wait_for(lambda: dev.role == Role("E") and dev.session == SESSION)
        rig.worker.stop()


def test_pairing_methods_reach_the_device() -> None:
    dev = SimDevice(caps=V2_CAPS)
    with Rig(dev) as rig:
        w = rig.worker
        w.pair_open(60)
        w.pair_accept(MAC, 0x3F)
        w.pair_reject(MAC)
        w.pair_delete(MAC)
        w.pair_ack(MAC, 12, 0)
        w.pair_tx(5)
        w.pair_close()
        expected = [
            PairOpen(60),
            PairAccept(MAC, 0x3F),
            PairReject(MAC),
            PairDelete(MAC),
            PairAck(MAC, 12, 0),
            PairTx(5),
            PairClose(),
        ]
        assert wait_for(lambda: dev.pairing == expected)


def test_invalid_mesh_arguments_are_rejected_on_the_caller_thread() -> None:
    dev = SimDevice(caps=V2_CAPS)
    with Rig(dev) as rig:
        with pytest.raises(ProtocolError):
            rig.worker.pair_open(0)
        with pytest.raises(ProtocolError):
            rig.worker.set_config("chan", "99")


def test_set_config_is_echoed() -> None:
    dev = SimDevice(caps=V2_CAPS)
    with Rig(dev) as rig:
        rig.worker.set_config("sound", "0")
        assert wait_for(lambda: rig.worker.device_config.get("sound") == "0")
        assert dev.config["sound"] == "0"


def test_whistle_with_explicit_timing_on_a_w_mesh_device() -> None:
    dev = SimDevice(caps=V2_CAPS)
    with Rig(dev) as rig:
        rig.worker.submit(EngineWhistle(3, 700, 300))
        assert wait_for(lambda: dev.whistle_timing == (700, 300))
        assert wait_for(lambda: dev.sound_dupes >= 2)  # repeats of the same id
        assert all(b.startswith(b"$S,3,") and b.count(b",") == 4 for b in rig.sent("S"))


def test_whistle_with_unusable_timing_falls_back_to_id_only() -> None:
    dev = SimDevice(caps=V2_CAPS)
    with Rig(dev) as rig:
        rig.worker.submit(EngineWhistle(1, 705, 300))
        assert wait_for(lambda: dev.sound_events == [1])
        assert dev.whistle_timing is None
