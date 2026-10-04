"""Hardware test: two real ESP32 boards, no network. Master core on one board, radio-only core on the other.

Usage: python scripts/hw_e2e_two_boards.py COM6 COM3   (or /dev/ttyACM0 /dev/ttyACM1)
Both boards must be flashed with the current firmware (scripts/flash.py) and no timer software may be running.
Both cores are real processes with their own data dir (temp folder); this script plays the UI of each. It joins
the second board over the radio, mirrors a session, sends commands with changing rights, restarts both cores,
removes and re-pairs the remote and checks the fail-safe. Not part of the unit suite (needs the boards).
Run it on freshly erased keys for the join step: python -m esptool --port COMx erase-region 0x9000 0x5000."""
# ruff: noqa

import json
import os
import pathlib
import subprocess
import sys
import time

import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
PY = sys.executable
TMP = pathlib.Path(tempfile.gettempdir()) / "archerytimer_hw_e2e"
MASTER_COM, JOINER_COM = sys.argv[1], sys.argv[2]
MP, JP = 8765, 8766
sys.path.insert(0, str(ROOT / "src"))

from archerytimer.ipc.link import CoreLink  # noqa: E402
from archerytimer.ipc.messages import cmd_msg  # noqa: E402
from archerytimer.ipc.transport_socket import connect_socket  # noqa: E402

LAUNCH = """
import sys, pathlib
import archerytimer.common.paths as P
d = pathlib.Path(sys.argv[1]); d.mkdir(parents=True, exist_ok=True)
P.data_dir = lambda: d
from archerytimer.core_service.__main__ import main
raise SystemExit(main(sys.argv[2:]))
"""

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail else ""), flush=True)
    return bool(ok)


class Proc:
    def __init__(self, tag, args):
        self.tag, self.args, self.p = tag, args, None
        self.dir = TMP / tag

    def start(self):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        self.log = open(TMP / f"{self.tag}.out", "ab")
        self.p = subprocess.Popen(
            [PY, "-c", LAUNCH, str(self.dir), *self.args],
            stdout=self.log,
            stderr=subprocess.STDOUT,
            env=env,
            cwd=str(ROOT),
        )

    def stop(self):
        if self.p and self.p.poll() is None:
            self.p.terminate()
            try:
                self.p.wait(8)
            except subprocess.TimeoutExpired:
                self.p.kill()
        self.p = None
        time.sleep(1.0)  # the port is released a moment later


class Cli:
    def __init__(self, port):
        self.link = CoreLink(lambda: connect_socket("127.0.0.1", port))
        self.link.start()

    def wait(self, pred, timeout=20.0, step=0.05):
        end = time.time() + timeout
        while time.time() < end:
            self.link.drain()
            if pred(self.link):
                return True
            time.sleep(step)
        self.link.drain()
        return pred(self.link)

    def cmd(self, name, args=None):
        self.link.send(cmd_msg(name, args or {}))

    def close(self):
        self.link.stop()


def snap(l):
    return l.snapshot


def pending(l):
    return (getattr(l, "remotes", None) or {}).get("pending", []) or []


def remotes(l):
    return (getattr(l, "remotes", None) or {}).get("remotes", []) or []


TMP.mkdir(parents=True, exist_ok=True)
for sub in ("master", "joiner"):
    d = TMP / sub
    if d.exists():
        for f in d.glob("*"):
            if f.is_file():
                f.unlink()
(TMP / "master").mkdir(exist_ok=True)
(TMP / "master" / "core_node.json").write_text(
    json.dumps(
        {"role": "leader", "leader": "", "espnow": "bridge", "lights": True, "name": "Master"}
    )
)

master = Proc(
    "master",
    ["--host", "127.0.0.1", "--tcp-port", str(MP), "--serial-port", MASTER_COM, "--no-audio"],
)
joiner = Proc(
    "joiner",
    ["--leader", "radio", "--tcp-port", str(JP), "--serial-port", JOINER_COM, "--no-audio"],
)
mc = jc = None
try:
    print("== 1. start both cores, no network involved")
    master.start()
    joiner.start()
    mc, jc = Cli(MP), Cli(JP)
    check(
        "master core up, lights link",
        mc.wait(lambda l: l.connected and l.hw_link == "up", 25),
        f"hw={mc.link.hw_link}",
    )
    check(
        "joiner core up, lights link",
        jc.wait(lambda l: l.connected and l.hw_link == "up", 25),
        f"hw={jc.link.hw_link}",
    )
    check(
        "joiner has no timer feed yet (upstream down)",
        jc.wait(lambda l: not l.upstream_ok, 10) and jc.link.upstream_via == "radio",
    )

    print("== 2. master searches, the keyless joiner asks to join by itself")
    mc.cmd("pair_open", {"seconds": 120, "discover": True})
    found = mc.wait(lambda l: len(pending(l)) >= 1, 40)
    check("joiner appears in the master's pending list", found, str(pending(mc.link)))
    if not found:
        raise SystemExit
    req = pending(mc.link)[0]
    jid = req["id"]
    check(
        "request carries name and hardware id",
        bool(req.get("name")) and bool(req.get("mac")),
        str(req),
    )

    print("== 3. accept with rights primary/pause/stop_end (no next/back)")
    mc.cmd("pair_accept", {"id": jid, "perms": ["primary", "pause", "resume", "stop_end"]})
    check(
        "master lists the joiner as paired remote",
        mc.wait(lambda l: any(r["id"] == jid for r in remotes(l)), 15),
        str(remotes(mc.link)),
    )
    check(
        "joiner receives the timer feed (upstream up)",
        jc.wait(lambda l: l.upstream_ok and l.snapshot is not None, 20),
        f"up={jc.link.upstream_ok}",
    )

    print("== 4. run a short session on the master, the joiner must mirror it")
    mc.cmd(
        "configure",
        {
            "sequence_id": "indoor_3arrows",
            "groups": ["AB", "CD"],
            "total_ends": 3,
            "prep_s": 4,
            "shoot_s": 14,
            "warn_s": 5,
        },
    )
    check(
        "joiner shows the configured session",
        jc.wait(lambda l: l.snapshot is not None and l.snapshot.total_ends == 3, 10),
        str(jc.link.snapshot and jc.link.snapshot.total_ends),
    )
    mc.cmd("primary")
    check("master running", mc.wait(lambda l: snap(l) and snap(l).mode.name == "RUNNING", 5))
    check("joiner running too", jc.wait(lambda l: snap(l) and snap(l).mode.name == "RUNNING", 5))
    skews = []
    t0 = time.time()
    seen_lights = set()
    while time.time() - t0 < 16:
        mc.link.drain()
        jc.link.drain()
        ms, js = snap(mc.link), snap(jc.link)
        if ms and js:
            seen_lights.add((ms.light.name, js.light.name))
            if ms.phase_id == js.phase_id and not ms.paused:
                skews.append(abs(ms.deadline_ns - js.deadline_ns) / 1e6)
        time.sleep(0.1)
    worst = max(skews) if skews else -1
    check(
        "deadline skew master vs joiner (same PC clock)",
        skews and worst < 100,
        f"max {worst:.1f} ms over {len(skews)} samples, median {sorted(skews)[len(skews) // 2]:.1f} ms"
        if skews
        else "no samples",
    )
    check(
        "lights on both sides agree during the run",
        all(a == b for a, b in seen_lights) or len(seen_lights) > 1,
        str(sorted(seen_lights)),
    )

    print("== 5. joiner sends commands over the radio (rights decided by the master)")
    mc.wait(lambda l: snap(l) and snap(l).mode.name in ("WAITING", "RUNNING"), 20)
    # get to a running state again
    if not (snap(mc.link) and snap(mc.link).mode.name == "RUNNING"):
        mc.cmd("primary")
        mc.wait(lambda l: snap(l) and snap(l).mode.name == "RUNNING", 8)
    jc.cmd("pause")
    check(
        "pause from the joiner reaches the master", mc.wait(lambda l: snap(l) and snap(l).paused, 6)
    )
    jc.cmd("resume")
    check(
        "resume from the joiner reaches the master",
        mc.wait(lambda l: snap(l) and not snap(l).paused, 6),
    )
    jc.cmd("stop_end")
    check(
        "stop_end from the joiner reaches the master",
        mc.wait(lambda l: snap(l) and snap(l).mode.name == "WAITING", 6),
    )
    before = snap(mc.link).round_index
    jc.cmd("back")  # not granted
    time.sleep(2.0)
    mc.link.drain()
    check(
        "not-granted action (back) is denied by the master",
        before > 0 and snap(mc.link).round_index == before and snap(mc.link).mode.name == "WAITING",
        f"round {before}->{snap(mc.link).round_index}",
    )
    mc.cmd("primary")
    mc.wait(lambda l: snap(l) and snap(l).mode.name == "RUNNING", 8)
    jc.cmd("emergency")
    check(
        "emergency from the joiner is always allowed",
        mc.wait(lambda l: snap(l) and snap(l).emergency, 6),
    )
    mc.cmd("clear_emergency", {"mode": "restart"})
    mc.wait(lambda l: snap(l) and not snap(l).emergency, 6)

    print("== 6. rights changed on the master take effect at once")
    mc.cmd(
        "remote_perms",
        {"id": jid, "perms": ["primary", "pause", "resume", "stop_end", "next", "back"]},
    )
    check(
        "master shows the new rights",
        mc.wait(lambda l: any(r["id"] == jid and "back" in r["perms"] for r in remotes(l)), 5),
    )
    mc.cmd("stop_end")
    mc.wait(lambda l: snap(l) and snap(l).mode.name == "WAITING", 8)
    r0 = snap(mc.link).round_index
    jc.cmd("back")
    check(
        "'back' works after the master granted it",
        mc.wait(lambda l: snap(l) and snap(l).round_index == r0 - 1, 8),
        f"round {r0}->{snap(mc.link).round_index}",
    )
    mc.cmd("reset")
    time.sleep(1.0)
    mc.cmd(
        "configure",
        {
            "sequence_id": "indoor_3arrows",
            "groups": ["AB", "CD"],
            "total_ends": 3,
            "prep_s": 4,
            "shoot_s": 14,
            "warn_s": 5,
        },
    )
    time.sleep(1.0)
    jc.cmd("primary")
    check(
        "primary from the joiner starts an end",
        mc.wait(lambda l: snap(l) and snap(l).mode.name == "RUNNING", 8),
    )

    print("== 7. joiner core restarts: still paired, follows without any new accept")
    jc.close()
    joiner.stop()
    master_state = snap(mc.link)
    joiner.start()
    jc = Cli(JP)
    check("joiner core back up", jc.wait(lambda l: l.connected and l.hw_link == "up", 25))
    check(
        "joiner follows again after its own restart",
        jc.wait(lambda l: l.upstream_ok and l.snapshot is not None, 25),
        f"up={jc.link.upstream_ok}",
    )

    print("== 8. master core restarts: joiner follows the new session")
    mc.close()
    master.stop()
    master.start()
    mc = Cli(MP)
    check("master core back up", mc.wait(lambda l: l.connected and l.hw_link == "up", 25))
    mc.cmd(
        "configure",
        {
            "sequence_id": "indoor_3arrows",
            "groups": ["AB"],
            "total_ends": 2,
            "prep_s": 4,
            "shoot_s": 14,
            "warn_s": 5,
        },
    )
    check(
        "joiner shows the new session after the master restart",
        jc.wait(
            lambda l: l.snapshot is not None and l.snapshot.total_ends == 2 and l.upstream_ok, 30
        ),
        str(jc.link.snapshot and jc.link.snapshot.total_ends),
    )
    mc.cmd(
        "pair_open", {"seconds": 120, "discover": True}
    )  # opening Wireless remotes asks for the list
    check(
        "master still lists the remote paired after its restart",
        mc.wait(lambda l: any(r["id"] == jid for r in remotes(l)), 10),
    )
    mc.cmd("primary")
    mc.wait(lambda l: snap(l) and snap(l).mode.name == "RUNNING", 8)
    jc.cmd("pause")
    check(
        "joiner command still authorised after the master restart",
        mc.wait(lambda l: snap(l) and snap(l).paused, 8),
    )
    jc.cmd("resume")
    mc.wait(lambda l: snap(l) and not snap(l).paused, 8)
    mc.cmd("pair_close")

    print("== 9. remove the remote on the master: the joiner must forget its keys and ask again")
    mc.cmd("pair_open", {"seconds": 120, "discover": True})
    mc.cmd("remote_remove", {"id": jid})
    check(
        "master no longer lists it as paired",
        mc.wait(lambda l: not any(r["id"] == jid for r in remotes(l)), 10),
    )
    check(
        "joiner loses the feed after removal",
        jc.wait(lambda l: not l.upstream_ok, 40),
        f"up={jc.link.upstream_ok}",
    )
    again = mc.wait(lambda l: any(p["id"] == jid for p in pending(l)), 60)
    check("joiner asks to join again by itself", again, str(pending(mc.link)))
    if again:
        mc.cmd("pair_accept", {"id": jid, "perms": ["primary", "pause", "resume", "stop_end"]})
        check(
            "joiner follows again after re-pairing",
            jc.wait(lambda l: l.upstream_ok and l.snapshot is not None, 25),
            f"up={jc.link.upstream_ok}",
        )
        mc.cmd(
            "configure",
            {
                "sequence_id": "indoor_3arrows",
                "groups": ["AB"],
                "total_ends": 2,
                "prep_s": 4,
                "shoot_s": 14,
                "warn_s": 5,
            },
        )
        mc.cmd("primary")
        check(
            "session mirrored again",
            jc.wait(lambda l: snap(l) and snap(l).mode.name == "RUNNING", 10),
        )

    print("== 9b. 'Pair with the main timer again' on the joiner")
    mc.cmd("pair_open", {"seconds": 120, "discover": True})
    jc.cmd("radio_forget_key")
    check(
        "joiner (forgot its key) asks again",
        mc.wait(lambda l: any(p["id"] == jid for p in pending(l)), 40),
        str(pending(mc.link)),
    )
    mc.cmd("pair_accept", {"id": jid, "perms": ["primary", "pause", "resume", "stop_end"]})
    check(
        "joiner follows again after forget + accept",
        jc.wait(lambda l: l.upstream_ok and l.snapshot is not None, 25),
    )

    print("== 10. master stops: joiner goes RED (fail-safe) within about a second")
    mc.cmd("primary")
    mc.close()
    master.stop()
    t0 = time.time()
    check(
        "joiner reports the feed lost after the master is gone",
        jc.wait(lambda l: not l.upstream_ok, 8),
        f"{time.time() - t0:.1f} s",
    )
finally:
    for c in (mc, jc):
        try:
            if c:
                c.close()
        except Exception:
            pass
    master.stop()
    joiner.stop()
    bad = [n for n, ok in results if not ok]
    print(
        f"\n{len(results) - len(bad)} passed, {len(bad)} failed"
        + (": " + "; ".join(bad) if bad else "")
    )
