"""This installation's radio identity: the mesh key, a stable node id and the session counter.

The mesh key (16 random bytes) is generated on first start and pushed to the MCU with ``$C,mkey`` on
every connect. "Reset radio network" replaces it: every paired remote and every other module must be
set up again. The ``session`` counter (u32 >= 1) is the replay protection of ``docs/mesh.md``
section 4: it is incremented at every core start and at every serial connect, and written before it
is used. A missing or damaged file gives a new node id (so a new master id) and the counter restarts
at 1. See ``docs/mesh.md``.
"""

from __future__ import annotations

import json
import logging
import secrets
import threading
from pathlib import Path
from typing import Optional

log = logging.getLogger("archerytimer.radio_keys")

FILE_NAME = "core_radio.json"
SESSION_MAX = 0xFFFF_FFFF


class RadioKeys:
    def __init__(self, path: Optional[Path]) -> None:
        self._path = path
        self._lock = threading.Lock()
        self.node_id = secrets.token_hex(4)
        self.mesh_key = secrets.token_hex(16).upper()
        self.session = 1
        self._load()

    def _load(self) -> None:
        if self._path is None or not self._path.exists():
            self._save()  # new identity, session 1
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            node_id, key = str(data["node_id"]), str(data["mesh_key"]).upper()
            if len(key) != 32 or int(key, 16) < 0 or not node_id:
                raise ValueError("bad radio identity")
            stored = int(data.get("session", 0))
            if stored < 0 or stored > SESSION_MAX:
                raise ValueError("bad session counter")
            self.node_id, self.mesh_key = node_id, key
            self.session = stored + 1  # this core start
            if self.session > SESSION_MAX:  # exhausted: a fresh master id starts over
                self.node_id, self.session = secrets.token_hex(4), 1
            self._save()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            log.warning("new radio identity, damaged %s: %r", self._path, exc)
            self.node_id = secrets.token_hex(4)
            self.mesh_key = secrets.token_hex(16).upper()
            self.session = 1
            self._save()

    def _save(self) -> None:
        if self._path is None:
            return
        try:
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(
                    {"node_id": self.node_id, "mesh_key": self.mesh_key, "session": self.session}
                ),
                encoding="utf-8",
            )
            tmp.replace(self._path)
        except OSError as exc:
            log.warning("cannot save radio identity: %s", exc)

    def bump(self) -> int:
        """A new session (at every serial connect): persisted first, then returned for use."""
        with self._lock:
            self.session = min(self.session + 1, SESSION_MAX)  # 4 billion connects: unreachable
            self._save()
            return self.session

    def set_mesh_key(self, key_hex: str) -> None:
        """Adopt the key of another network (a follower joining a leader); persisted."""
        key = str(key_hex).strip().upper()
        if len(key) != 32 or any(c not in "0123456789ABCDEF" for c in key):
            raise ValueError("mesh key must be 32 hex digits")
        with self._lock:
            self.mesh_key = key
            self._save()
        log.info("radio network key adopted from the leader")

    def rotate(self) -> str:
        """A new mesh key; returns it (the caller pushes it to the MCU)."""
        self.mesh_key = secrets.token_hex(16).upper()
        self._save()
        log.info("radio network key replaced")
        return self.mesh_key
