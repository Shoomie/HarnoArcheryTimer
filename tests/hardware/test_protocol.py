from __future__ import annotations

from pathlib import Path

import pytest

from archerytimer.hardware.protocol import (
    ERR_BAD_ARG,
    ERR_CHECKSUM,
    ERR_OVERFLOW,
    MAX_FRAME_BYTES,
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
    checksum,
    decode,
    encode,
    frame_fields,
)

VECTORS = Path(__file__).resolve().parents[2] / "firmware" / "test_vectors.txt"


def _load_vectors() -> list[tuple[str, str]]:
    out = []
    for raw in VECTORS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            frame, _, expected = line.partition(" => ")
            out.append((frame, expected))
    return out


VECTOR_CASES = _load_vectors()

ALL_FRAMES: list[Frame] = [
    Lights("G"),
    Lights("RY"),
    Lights("O"),
    Whistle(0),
    Whistle(5),
    Buzzer(True),
    Buzzer(False),
    Group("AB"),
    Remaining(87300),
    Heartbeat(7, "R", ""),
    Heartbeat(8, "G", "CD"),
    Hello(),
    HelloReply(1, "esp32s3-0.1.0", "LSBGT"),
    Ack(42),
    Error("CS"),
]


def test_vector_file_is_not_empty() -> None:
    assert len(VECTOR_CASES) > 50
    assert any(e.startswith("OK") for _, e in VECTOR_CASES)
    assert any(e.startswith("ERR") for _, e in VECTOR_CASES)


@pytest.mark.parametrize(("frame", "expected"), VECTOR_CASES)
def test_shared_vectors(frame: str, expected: str) -> None:
    verdict, _, rest = expected.partition(" ")
    if verdict == "ERR":
        with pytest.raises(ProtocolError) as info:
            decode(frame)
        assert info.value.code == rest
        return
    parsed = decode(frame)
    cmd, args = frame_fields(parsed)
    assert [cmd, *args] == [("" if f == "-" else f) for f in rest.split(" ")]
    assert encode(parsed) == frame.encode() + b"\n"


def test_checksum_known_values() -> None:
    assert checksum(b"") == 0
    assert checksum(b"L,G") == 0x27  # 0x4C ^ 0x2C ^ 0x47, worked by hand
    assert checksum(b"V") == 0x56


def test_encode_example() -> None:
    assert encode(Lights("G")) == b"$L,G*27\n"
    assert encode(Hello()) == b"$V*56\n"


@pytest.mark.parametrize("frame", ALL_FRAMES, ids=lambda f: type(f).__name__)
def test_round_trip(frame: Frame) -> None:
    data = encode(frame)
    assert data.endswith(b"\n")
    assert len(data) <= MAX_FRAME_BYTES
    assert decode(data) == frame
    assert decode(data.rstrip(b"\n")) == frame
    assert decode(data[:-1] + b"\r\n") == frame


def test_decode_accepts_str() -> None:
    assert decode("$L,G*27\n") == Lights("G")


def test_decode_non_ascii_is_malformed() -> None:
    with pytest.raises(ProtocolError) as info:
        decode("$L,å*00")
    assert info.value.code == "MF"


@pytest.mark.parametrize(
    "frame",
    [
        Lights(""),
        Lights("X"),
        Lights("GG"),
        Lights("OG"),
        Whistle(-1),
        Whistle(100),
        Remaining(-1),
        Remaining(2**32),
        Group(""),
        Group("ab"),
        Group("TOOLONGGRP"),
        Heartbeat(-1, "R", ""),
        Heartbeat(0, "R", "a,b"),
        HelloReply(1, "has space", "L"),
        HelloReply(1, "x", "Q"),
        Error("ZZ"),
    ],
)
def test_encode_rejects_invalid(frame: Frame) -> None:
    with pytest.raises(ProtocolError) as info:
        encode(frame)
    assert info.value.code == ERR_BAD_ARG


def test_max_length_boundary() -> None:
    # 59-byte body -> 63 content bytes + newline = exactly 64: accepted by the length check.
    body = b"X," + b"9" * 57
    ok_frame = b"$" + body + b"*" + f"{checksum(body):02X}".encode() + b"\n"
    assert len(ok_frame) == MAX_FRAME_BYTES
    with pytest.raises(ProtocolError) as info:
        decode(ok_frame)
    assert info.value.code == "UC"  # got past the length check
    body += b"9"
    too_long = b"$" + body + b"*" + f"{checksum(body):02X}".encode() + b"\n"
    with pytest.raises(ProtocolError) as info:
        decode(too_long)
    assert info.value.code == ERR_OVERFLOW


# --- FrameParser -------------------------------------------------------------------------


def test_parser_one_frame_per_feed() -> None:
    parser = FrameParser()
    assert parser.feed(b"$L,G*27\n") == [Lights("G")]
    assert parser.feed(b"$V*56\n") == [Hello()]


def test_parser_split_reads_at_every_byte() -> None:
    stream = encode(Lights("G")) + encode(Heartbeat(3, "R", "AB"))
    parser = FrameParser()
    out: list[Frame | ProtocolError] = []
    for i in range(len(stream)):
        out.extend(parser.feed(stream[i : i + 1]))
    assert out == [Lights("G"), Heartbeat(3, "R", "AB")]


def test_parser_several_frames_in_one_read() -> None:
    parser = FrameParser()
    out = parser.feed(encode(Lights("R")) + encode(Whistle(3)) + encode(Buzzer(True)))
    assert out == [Lights("R"), Whistle(3), Buzzer(True)]


def test_parser_resynchronizes_after_garbage() -> None:
    parser = FrameParser()
    out = parser.feed(b"\x00\xffjunk$L\n$L,G*27\n")
    assert isinstance(out[0], ProtocolError)
    assert out[0].code == "MF"
    assert out[1:] == [Lights("G")]


def test_parser_reports_bad_checksum_and_continues() -> None:
    parser = FrameParser()
    out = parser.feed(b"$L,G*26\n$L,G*27\n")
    assert isinstance(out[0], ProtocolError)
    assert out[0].code == ERR_CHECKSUM
    assert out[1] == Lights("G")


def test_parser_ignores_empty_lines_and_handles_crlf() -> None:
    parser = FrameParser()
    assert parser.feed(b"\n\r\n\n$L,G*27\r\n\n") == [Lights("G")]


def test_parser_overflow_discards_whole_line_then_recovers() -> None:
    parser = FrameParser()
    out = parser.feed(b"$" + b"A" * 500)
    assert out == []  # no newline yet; memory stays bounded
    out = parser.feed(b"A" * 500 + b"\n$L,G*27\n")
    assert len(out) == 2
    assert isinstance(out[0], ProtocolError)
    assert out[0].code == ERR_OVERFLOW
    assert out[1] == Lights("G")


def test_parser_buffer_stays_bounded() -> None:
    parser = FrameParser()
    for _ in range(1000):
        parser.feed(b"A" * 100)
    assert len(parser._buf) <= MAX_FRAME_BYTES
