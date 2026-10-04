from __future__ import annotations

from pathlib import Path

import pytest

from archerytimer.hardware.mesh_types import (
    Config,
    ConfigQuery,
    FeedSession,
    FeedSound,
    FeedTimer,
    MeshStatus,
    PairAccept,
    PairAck,
    PairClose,
    PairDelete,
    PairDone,
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
    MAX_LONG_FRAME_BYTES,
    Frame,
    FrameParser,
    HelloReply,
    ProtocolError,
    Whistle,
    decode,
    encode,
    frame_fields,
)

VECTORS = Path(__file__).resolve().parents[2] / "firmware" / "test_vectors_v2.txt"


def _load() -> list[tuple[str, str]]:
    out = []
    for raw in VECTORS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            frame, _, expected = line.partition(" => ")
            out.append((frame, expected))
    return out


CASES = _load()


def test_vector_file_is_loaded() -> None:
    assert len(CASES) > 90
    assert any(e.startswith("ERR OV") for _, e in CASES)


@pytest.mark.parametrize(("frame", "expected"), CASES)
def test_v2_vectors(frame: str, expected: str) -> None:
    verdict, _, rest = expected.partition(" ")
    if verdict == "ERR":
        with pytest.raises(ProtocolError) as info:
            decode(frame)
        assert info.value.code == rest
        return
    parsed = decode(frame)
    cmd, args = frame_fields(parsed)  # wire strings: an empty caps or name stays "-"
    assert [cmd, *args] == rest.split(" ")
    assert encode(parsed) == frame.encode() + b"\n"


ALL_V2: list[Frame] = [
    Role("M", 0xABCD, 7),
    Role("E"),
    Config("chan", "6"),
    ConfigQuery(),
    TimerState(1, 2, 87300, 3, 12, 0, 1, 4, 3, 5),
    SessionInfo(5, True, True, 12, 2, 0xFFFFFFFF, 0xFFFFFFFF, 0, 5000, "indoor_18", ("AB", "CD")),
    PairOpen(60),
    PairClose(),
    PairAccept("AABBCCDDEEFF", 0x7F),
    PairReject("AABBCCDDEEFF"),
    PairDelete("AABBCCDDEEFF"),
    PairAck("AABBCCDDEEFF", 12, 1),
    PairTx(4),
    PairRequest("AABBCCDDEEFF", "Finish", "K"),
    RemoteCommand("AABBCCDDEEFF", 7, 12),
    PairDone("AABBCCDDEEFF"),
    PairState(True, 45),
    MeshStatus("M", "H", 3, False, 0xABCD, 1),
    RosterEntry("AABBCCDDEEFF", "N", "", 45, "0.2.0", ""),
    RosterGone("AABBCCDDEEFF"),
    FeedTimer(bytes(range(29))),
    FeedSound(bytes(range(12))),
    FeedSession(b"\x0a\x0b"),
    Whistle(3, 200, 300, 700),
    HelloReply(2, "esp-0.3.0", "LSBKNWR"),
]


@pytest.mark.parametrize("frame", ALL_V2, ids=lambda f: type(f).__name__)
def test_round_trip(frame: Frame) -> None:
    assert decode(encode(frame)) == frame


def test_typed_parse() -> None:
    assert decode("$R,M,0000ABCD,7*00") == Role("M", 0xABCD, 7)
    assert decode("$S,1,7,500,500*55") == Whistle(1, 7, 500, 500)
    assert decode(encode(Whistle(2, 9))) == Whistle(2, 9, None, None)
    d = decode("$D,AABBCCDDEEFF,N,LSB,45,0.2.0,-*49")
    assert d == RosterEntry("AABBCCDDEEFF", "N", "LSB", 45, "0.2.0", "")


def test_whistle_timing_needs_id_and_both_values() -> None:
    for bad in (Whistle(1, None, 500, 500), Whistle(1, 3, 500, None)):
        with pytest.raises(ProtocolError):
            encode(bad)
    with pytest.raises(ProtocolError):
        encode(Whistle(1, 3, 505, 500))


def test_long_frame_limit() -> None:
    session = SessionInfo(1, False, False, 1, 0, 1, 2, 3, 4, "x" * 16, ("ABCDEFGH",) * 8)
    data = encode(session)
    assert 64 < len(data) <= MAX_LONG_FRAME_BYTES
    assert decode(data) == session
    # A short command at the same size is an overflow.
    with pytest.raises(ProtocolError) as info:
        decode(b"$C,name," + b"A" * 70 + b"*00\n")
    assert info.value.code == "OV"


def test_frame_parser_reads_long_frames_and_resyncs() -> None:
    session = SessionInfo(1, False, True, 1, 0, 1, 2, 3, 4, "free", ("AB", "CD", "EF", "GH"))
    data = encode(session)
    junk = b"$J," + b"5" * 200 + b"\n"
    parser = FrameParser()
    out = parser.feed(data[:50]) + parser.feed(data[50:] + junk + encode(PairClose()))
    assert out[0] == session
    assert isinstance(out[1], ProtocolError) and out[1].code == "OV"
    assert out[2] == PairClose()


def test_v1_short_frame_still_limited_to_64() -> None:
    parser = FrameParser()
    out = parser.feed(b"$L," + b"G" * 80 + b"\n")
    assert isinstance(out[0], ProtocolError) and out[0].code == "OV"
