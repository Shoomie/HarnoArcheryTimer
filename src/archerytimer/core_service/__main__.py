"""Core service entry point: ``python -m archerytimer.core_service``."""

from __future__ import annotations

import argparse
import gc
import logging
import os
import signal
import socket
import sys
import threading
from pathlib import Path
from typing import Any, Optional, Union

from archerytimer import __version__
from archerytimer.audio.audio_worker import AudioWorker, list_devices, make_backend
from archerytimer.audio.settings import FILE_NAME as AUDIO_FILE
from archerytimer.audio.settings import AudioSettingsStore
from archerytimer.audio.settings import from_table as audio_from_table
from archerytimer.common.clock import MonotonicClock
from archerytimer.common.paths import data_dir, setup_logging
from archerytimer.core.rules import load_sequences
from archerytimer.core_service.audio_control import AudioControl
from archerytimer.core_service.cluster import FOLLOW_FILE, FollowerService, FollowStore
from archerytimer.core_service.followers import FollowerRegistry
from archerytimer.core_service.inputs import parse_bindings
from archerytimer.core_service.meshfeed import master_id_from, radio_name
from archerytimer.core_service.netdisco import Beacon, LeaderBrowser
from archerytimer.core_service.node import (
    FILE_NAME as NODE_FILE,
)
from archerytimer.core_service.node import (
    NodeControl,
    NodeSettings,
    NodeStore,
)
from archerytimer.core_service.node import (
    from_table as node_from_table,
)
from archerytimer.core_service.radio_keys import FILE_NAME as RADIO_FILE
from archerytimer.core_service.radio_keys import RadioKeys
from archerytimer.core_service.radio_service import RadioFollowerService
from archerytimer.core_service.remotes import RemoteRegistry, RemoteStore
from archerytimer.core_service.roster import Roster
from archerytimer.core_service.service import CoreService
from archerytimer.hardware.discovery import make_port_factory
from archerytimer.ipc.transport import ConnectionClosed
from archerytimer.ipc.transport_socket import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    SocketListener,
    connect_socket,
)

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9 / 3.10
    import tomli as tomllib  # type: ignore[no-redef]

log = logging.getLogger("archerytimer.core")
DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "config" / "sequences"
DEFAULT_SETTINGS = Path(__file__).resolve().parents[3] / "config" / "default_settings.toml"


def raise_priority(nice: int, cpu: Optional[int]) -> None:
    """Best effort and platform guarded: never fatal."""
    try:
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.kernel32.SetPriorityClass(
                ctypes.windll.kernel32.GetCurrentProcess(),
                0x00008000,  # ABOVE_NORMAL_PRIORITY_CLASS
            )
        elif nice:
            os.nice(-abs(nice))
    except Exception as exc:
        log.info("could not raise priority: %s", exc)
    if cpu is not None and hasattr(os, "sched_setaffinity"):
        try:
            os.sched_setaffinity(0, {cpu})
        except OSError as exc:
            log.info("could not pin to cpu %s: %s", cpu, exc)


def build_audio(table: dict[str, Any]) -> AudioControl:
    """Sound control with local audio. Without a working audio device the local output is a
    silent no-op (MCU sound is unaffected)."""
    store = AudioSettingsStore(data_dir() / AUDIO_FILE)
    settings = store.load(audio_from_table(table))
    return AudioControl(
        AudioWorker(make_backend(settings.device)),
        store=store,
        settings=settings,
        devices=list_devices,
        backend_factory=make_backend,
    )


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG)
    ap.add_argument(
        "--leader",
        default="",
        help="HOST[:PORT] of the leader core, or 'radio': timer from the ESP32 radio only",
    )
    ap.add_argument(
        "--espnow",
        choices=["off", "bridge", "follow", "auto"],
        default=None,
        help="ESP-NOW role of the attached ESP32 (overrides [node] espnow)",
    )
    ap.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS)
    ap.add_argument(
        "--host",
        default=None,
        help=f"address to listen on (default: {DEFAULT_HOST}; 0.0.0.0 for a leader role)",
    )
    ap.add_argument("--tcp-port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--serial-port", default="", help="override USB discovery, e.g. COM7")
    ap.add_argument("--no-serial", action="store_true", help="run without lights hardware")
    ap.add_argument("--no-audio", action="store_true", help="no local sound (MCU sound unaffected)")
    ap.add_argument("--nice", type=int, default=5, help="priority boost (Linux), 0 to disable")
    ap.add_argument("--cpu", type=int, default=None, help="pin to this CPU (Linux)")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)

    log_path = setup_logging("core")
    sys.setswitchinterval(0.0005)
    raise_priority(args.nice, args.cpu)

    sequences = load_sequences(args.config_dir)
    bindings = {}
    settings: dict[str, Any] = {}
    if args.settings.exists():
        with args.settings.open("rb") as fh:
            settings = tomllib.load(fh)
        bindings = parse_bindings(settings.get("buttons", {}))
    table = settings.get("node", {})
    store = NodeStore(data_dir() / NODE_FILE)
    # Command-line flags beat the stored choice and lock it; the stored choice beats the TOML.
    locked = bool(args.leader or args.espnow or args.host)
    node_settings = store.load(node_from_table(table))
    if args.leader:
        node_settings = node_settings.updated({"node_role": "follower", "node_leader": args.leader})
    if args.espnow:
        node_settings = node_settings.updated({"espnow": args.espnow})
    if args.host and node_settings.role == "standalone":
        node_settings = node_settings.updated({"node_role": "leader"})

    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    restart = threading.Event()

    first = True
    while not stop.is_set():
        restart.clear()
        service = build_service(
            args, settings, bindings, sequences, node_settings, store, locked, restart.set
        )
        service.start()
        if first:
            first = False
            gc.collect()
            gc.freeze()
        log.info("core service running as %s, log %s", node_settings.role.upper(), log_path)
        try:
            while not stop.wait(0.2) and not restart.is_set():
                pass
        finally:
            log.info("shutting down: RED and silence")
            service.stop()
        if restart.is_set() and not stop.is_set():
            node_settings = store.load(node_settings)  # the stored wish becomes the active role
            log.info("restarting as %s", node_settings.role)
    return 0


def build_service(
    args: argparse.Namespace,
    settings: dict[str, Any],
    bindings: dict[str, Any],
    sequences: Any,
    node_settings: NodeSettings,
    store: NodeStore,
    locked: bool,
    on_apply: Any,
) -> Union[CoreService, FollowerService, RadioFollowerService]:
    clock = MonotonicClock()
    role = node_settings.role
    host = args.host or ("0.0.0.0" if role == "leader" else DEFAULT_HOST)
    listener = SocketListener(host, args.tcp_port)
    port_factory = None if args.no_serial else make_port_factory(args.serial_port)
    audio = None if args.no_audio else build_audio(settings.get("audio", {}))
    espnow = node_settings.espnow if (args.espnow or node_settings.espnow != "off") else None
    keys = RadioKeys(data_dir() / RADIO_FILE)
    name = node_settings.name or socket.gethostname()
    mesh_config = {"mkey": keys.mesh_key, "name": radio_name(name)}
    radio_only = role == "follower" and node_settings.leader == "radio"
    # Every core announces itself and listens, so the Timer network screen lists them all.
    browser = LeaderBrowser(own_id=keys.node_id)
    beacon = Beacon(
        args.tcp_port,
        name,
        node_id=keys.node_id,
        role="alone" if role == "standalone" else role,
        version=__version__,
    )
    live: dict[str, Any] = {}  # the service, once built (the node needs it for remote commands)

    registry: Optional[FollowerRegistry] = None  # the leader's list of followers and their rights

    def reset_key() -> None:
        worker = getattr(live.get("service"), "worker", None)
        new_key = keys.rotate()
        if registry is not None:
            registry.set_mesh_key(new_key)
        if worker is not None:
            worker.set_config("mkey", new_key)

    node = NodeControl(
        node_settings,
        store=store,
        browser=browser,
        beacon=beacon,
        locked=locked,
        on_apply=on_apply,
        node_id=keys.node_id,
        roster=Roster(keys.node_id),
        remotes=RemoteRegistry(clock, store=RemoteStore(data_dir() / "core_remotes.json")),
        submit_command=lambda cmd: live["service"].send(cmd),
        on_reset_key=reset_key,
        version=__version__,
    )
    service: Union[CoreService, FollowerService, RadioFollowerService]
    if radio_only:
        if port_factory is None:
            raise SystemExit("--leader radio needs the ESP32 (do not use --no-serial)")
        service = RadioFollowerService(
            clock,
            sequences,
            listener,
            port_factory,
            bindings=bindings,
            mesh_config=mesh_config,
            audio=audio,
            node=node,
            version=__version__,
        )
        log.info("running as RADIO-ONLY FOLLOWER (timer from the ESP32 radio)")
    elif role == "follower":

        def connect_leader() -> Any:
            addr = node_settings.leader
            if not addr and browser is not None:
                found = browser.leaders()
                addr = found[0]["addr"] if len(found) == 1 else ""
            if not addr:
                raise ConnectionClosed
            lhost, _, lport = addr.partition(":")
            return connect_socket(lhost, int(lport or DEFAULT_PORT))

        service = FollowerService(
            clock,
            connect_leader,
            listener,
            port_factory=port_factory,
            bindings=bindings,
            espnow=espnow,
            audio=audio,
            node=node,
            mesh_config=mesh_config,
            node_id=keys.node_id,
            node_name=name,
            access_store=FollowStore(data_dir() / FOLLOW_FILE),
            radio_keys=keys,
        )
        log.info("running as FOLLOWER of %s", node_settings.leader or "the leader found on the LAN")
    else:
        registry = FollowerRegistry(
            clock,
            path=data_dir() / "core_followers.json",
            mesh_key_hex=keys.mesh_key,
            leader_name=name,
        )
        service = CoreService(
            clock,
            sequences,
            listener,
            port_factory=port_factory,
            bindings=bindings,
            espnow=espnow,
            audio=audio,
            node=node,
            version=__version__,
            master_id=master_id_from(keys.node_id),
            master_session=keys.session,
            session_bump=keys.bump,
            followers=registry,
            mesh_config=mesh_config,
        )
        log.info("running as %s", "LEADER" if role == "leader" else "STANDALONE timer")
    live["service"] = service
    return service


if __name__ == "__main__":
    raise SystemExit(main())
