from __future__ import annotations

import sys
import time

import pytest

from archerytimer.common.clock import NS_PER_S, FakeClock
from archerytimer.hardware.protocol import (
    PROTOCOL_VERSION,
    Ack,
    Buzzer,
    Error,
    Frame,
    FrameParser,
    Group,
    Heartbeat,
    Hello,
    HelloReply,
    Lights,
    ProtocolError,
    Remaining,
    Whistle,
    encode,
)
from archerytimer.hardware.sim_device import (
    SimDevice,
    SimDeviceRunner,
    memory_port_pair,
    open_pty,
)


def parse(data: bytes) -> list[Frame | ProtocolError]:
    return FrameParser().feed(data)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(start_ns=1_000 * NS_PER_S)


@pytest.fixture
def dev(clock: FakeClock) -> SimDevice:
    return SimDevice(clock)


def send(dev: SimDevice, *frames: Frame) -> list[Frame | ProtocolError]:
    return parse(dev.feed(b"".join(encode(f) for f in frames)))


def test_boots_into_safe_state(dev: SimDevice) -> None:
    assert dev.lights == "R"
    assert not dev.buzzer
    assert dev.whistle == 0
    assert not dev.fault


def test_hello_handshake(dev: SimDevice) -> None:
    assert send(dev, Hello()) == [HelloReply(PROTOCOL_VERSION, "sim-0.1.0", "LSBGT")]


def test_commands_set_state_without_reply(dev: SimDevice) -> None:
    out = send(dev, Lights("G"), Group("AB"), Remaining(90_000), Buzzer(True), Whistle(2))
    assert out == []
    assert dev.lights == "G"
    assert dev.group == "AB"
    assert dev.remaining_ms == 90_000
    assert dev.buzzer
    assert dev.whistle == 2


def test_silence_command_stops_sound(dev: SimDevice) -> None:
    send(dev, Buzzer(True), Whistle(3))
    send(dev, Whistle(0))
    assert dev.whistle == 0
    assert not dev.buzzer
    assert dev.sound_events == [3, 0]


def test_heartbeat_is_acked_and_asserts_state(dev: SimDevice) -> None:
    assert send(dev, Heartbeat(17, "Y", "CD")) == [Ack(17)]
    assert dev.lights == "Y"
    assert dev.group == "CD"
    assert dev.last_heartbeat_seq == 17


def test_repeated_frames_are_idempotent(dev: SimDevice) -> None:
    for _ in range(5):
        send(dev, Lights("G"), Group("AB"), Buzzer(False))
    assert (dev.lights, dev.group, dev.buzzer) == ("G", "AB", False)


def test_heartbeat_heals_a_dropped_light_command(dev: SimDevice) -> None:
    send(dev, Lights("R"))
    dev.drop_frames(1)
    send(dev, Lights("G"))  # lost on the wire
    assert dev.lights == "R"
    send(dev, Heartbeat(1, "G", ""))  # next heartbeat re-asserts the full state
    assert dev.lights == "G"


def test_bad_checksum_gets_error_reply_and_changes_nothing(dev: SimDevice) -> None:
    assert parse(dev.feed(b"$L,G*26\n")) == [Error("CS")]
    assert dev.lights == "R"


def test_unknown_command_and_bad_argument(dev: SimDevice) -> None:
    assert parse(dev.feed(b"$X,1*" + _cs(b"X,1") + b"\n")) == [Error("UC")]
    assert parse(dev.feed(b"$L,Q*" + _cs(b"L,Q") + b"\n")) == [Error("BA")]
    assert dev.lights == "R"


def test_overflow_gets_error_reply(dev: SimDevice) -> None:
    assert parse(dev.feed(b"$" + b"A" * 200 + b"\n")) == [Error("OV")]


def test_framing_garbage_is_silent(dev: SimDevice) -> None:
    assert dev.feed(b"garbage\n\r\n$L,G\n") == b""


def test_mcu_to_host_frame_is_rejected(dev: SimDevice) -> None:
    assert send(dev, Ack(1)) == [Error("UC")]


def test_unsupported_capability_is_rejected(clock: FakeClock) -> None:
    dev = SimDevice(clock, caps="L")
    assert send(dev, Hello()) == [HelloReply(PROTOCOL_VERSION, "sim-0.1.0", "L")]
    assert send(dev, Buzzer(True)) == [Error("UC")]
    assert not dev.buzzer
    assert send(dev, Heartbeat(1, "G", "AB")) == [Ack(1)]
    assert dev.group == ""  # no group capability


def test_mute_device_acts_but_never_replies(dev: SimDevice) -> None:
    dev.mute = True
    assert dev.feed(encode(Hello()) + encode(Lights("G"))) == b""
    assert dev.lights == "G"


def test_corrupted_reply_fails_checksum(dev: SimDevice) -> None:
    dev.corrupt_replies(1)
    out = parse(dev.feed(encode(Heartbeat(1, "G", ""))))
    assert len(out) == 1
    assert isinstance(out[0], ProtocolError)
    assert out[0].code == "CS"
    assert send(dev, Heartbeat(2, "G", "")) == [Ack(2)]  # only the next reply was damaged


def test_log_records_timestamps(dev: SimDevice, clock: FakeClock) -> None:
    send(dev, Lights("G"))
    clock.advance(5_000_000)
    send(dev, Heartbeat(1, "G", ""))
    rx = [e for e in dev.log if e.direction == "rx"]
    assert [e.data for e in rx] == [encode(Lights("G")), encode(Heartbeat(1, "G", ""))]
    assert rx[1].t_ns - rx[0].t_ns == 5_000_000
    assert [e.direction for e in dev.log][-1] == "tx"


# --- watchdog ----------------------------------------------------------------------------


def test_watchdog_forces_red_and_silence(dev: SimDevice, clock: FakeClock) -> None:
    send(dev, Lights("G"), Buzzer(True), Whistle(2))
    clock.advance(999_000_000)
    assert not dev.poll()
    assert dev.lights == "G"
    clock.advance(1_000_000)  # exactly 1 s since the last valid frame
    assert dev.poll()
    assert dev.fault
    assert dev.lights == "R"
    assert not dev.buzzer
    assert dev.whistle == 0
    assert dev.watchdog_trips == 1
    assert not dev.poll()  # trips once per silence
    assert dev.watchdog_trips == 1


def test_heartbeats_keep_the_watchdog_quiet(dev: SimDevice, clock: FakeClock) -> None:
    send(dev, Lights("G"))
    for seq in range(50):  # 10 s of 200 ms heartbeats
        clock.advance(200_000_000)
        send(dev, Heartbeat(seq, "G", ""))
        assert not dev.poll()
    assert dev.lights == "G"
    assert dev.watchdog_trips == 0


def test_invalid_frames_do_not_feed_the_watchdog(dev: SimDevice, clock: FakeClock) -> None:
    send(dev, Lights("G"))
    clock.advance(600_000_000)
    dev.feed(b"$L,G*26\n")  # bad checksum
    clock.advance(600_000_000)
    assert dev.poll()


def test_watchdog_trips_after_boot_with_no_traffic(dev: SimDevice, clock: FakeClock) -> None:
    clock.advance(NS_PER_S)
    assert dev.poll()


def test_valid_frame_clears_fault_and_state_returns_on_assert(
    dev: SimDevice, clock: FakeClock
) -> None:
    send(dev, Lights("G"))
    clock.advance(2 * NS_PER_S)
    dev.poll()
    assert dev.fault
    send(dev, Heartbeat(1, "G", ""))
    assert not dev.fault
    assert dev.lights == "G"


def test_custom_watchdog_timeout(clock: FakeClock) -> None:
    dev = SimDevice(clock, watchdog_ns=50_000_000)
    clock.advance(49_000_000)
    assert not dev.poll()
    clock.advance(1_000_000)
    assert dev.poll()


# --- threaded runner and ports -----------------------------------------------------------


def _read_frames(host, count: int, deadline_s: float = 2.0) -> list[Frame | ProtocolError]:  # type: ignore[no-untyped-def]
    parser = FrameParser()
    out: list[Frame | ProtocolError] = []
    end = time.monotonic() + deadline_s
    host.timeout = 0.05
    while len(out) < count and time.monotonic() < end:
        out.extend(parser.feed(host.read(256)))
    return out


def test_runner_over_memory_port() -> None:
    host, device_end = memory_port_pair()
    dev = SimDevice()
    with SimDeviceRunner(dev, device_end):
        host.write(encode(Hello()))
        assert _read_frames(host, 1) == [HelloReply(PROTOCOL_VERSION, "sim-0.1.0", "LSBGT")]
        host.write(encode(Heartbeat(9, "G", "AB")))
        assert _read_frames(host, 1) == [Ack(9)]
    assert dev.lights == "G"
    host.close()


def test_runner_watchdog_in_real_time() -> None:
    host, device_end = memory_port_pair()
    dev = SimDevice(watchdog_ns=30_000_000)
    with SimDeviceRunner(dev, device_end):
        host.write(encode(Lights("G")))
        end = time.monotonic() + 2.0
        while not dev.fault and time.monotonic() < end:
            time.sleep(0.005)
    assert dev.fault
    assert dev.lights == "R"


def test_runner_stops_when_cable_unplugged() -> None:
    host, device_end = memory_port_pair()
    runner = SimDeviceRunner(SimDevice(), device_end).start()
    host.close()
    runner.stop()
    assert not device_end.is_open


@pytest.mark.skipif(sys.platform == "win32", reason="pty is POSIX only")
def test_runner_over_pty() -> None:
    import serial  # pyserial

    port, path = open_pty()
    dev = SimDevice()
    with SimDeviceRunner(dev, port), serial.Serial(path, 115200, timeout=0.05) as host:
        host.write(encode(Hello()))
        assert _read_frames(host, 1) == [HelloReply(PROTOCOL_VERSION, "sim-0.1.0", "LSBGT")]
    port.close()


def test_open_pty_unavailable_on_windows() -> None:
    if sys.platform != "win32":
        pytest.skip("only meaningful on Windows")
    with pytest.raises(OSError):
        open_pty()


def _cs(body: bytes) -> bytes:
    from archerytimer.hardware.protocol import checksum

    return f"{checksum(body):02X}".encode()
