# 0003 – Parallel workflow for the mesh work (F0-F6 of 0002)

Goal: finish `0002` faster by running independent work packages (WPs) as parallel agents, without
them editing the same files or guessing each other's interfaces. The folder is **not a git repo**, so
worktree isolation is unavailable: isolation is by **file ownership** and by **frozen contracts**.

## Principle

1. **Wave 0 (me, serial, short):** freeze every interface the WPs share. Nothing else starts before this.
2. **Wave 1 (parallel):** WPs with disjoint file sets that only meet at the frozen contracts.
3. **Wave 2 (me, serial):** integration of the pieces, cross-checks, full test run once.
4. **Wave 3 (user, hardware):** bench, range, soak. Agents cannot do this.

## Wave 0: contracts (deliverables, all in the repo)

| Contract | File | Content |
| --- | --- | --- |
| Radio wire format v2 | `docs/mesh.md` | exact byte layouts of HELLO, TIMER, SOUND, CMD, CMD_ACK, SESSION, PAIR_*, ADMIN; HMAC input and key use; dedupe rule; arbiter rules; timing constants |
| Serial v2 | `docs/protocol.md` + `firmware/test_vectors.txt` | `$R $D $X $Y $P $C`, `$S` with blast/gap, `$N` v2, with vectors |
| Mesh vectors | `firmware/mesh_vectors.txt` | frame hex plus the key, expected parse, expected HMAC, for every type and for reject cases |
| Python types | `hardware/protocol.py` (dataclass stubs only), `ipc/messages.py` (builders only: `roster`, `pairing`, `remotes`, `conflict`) | signatures and fields; bodies raise `NotImplementedError` |
| `SESSION` contents | `docs/mesh.md` | resolves the open question: sequence id, groups, total/practice ends, prep/shoot/warn overrides, auto-advance |
| Ownership map | this file, below | who may edit what |

Wave 0 is the only place where cross-cutting decisions are made. If a WP finds a contract gap it
**stops and reports**; it does not patch the contract.

## Wave 1: work packages

| WP | Scope | Owns (only these) | Depends on | Done when |
| --- | --- | --- | --- | --- |
| **A** Firmware build + split (F0) | Make S3 and C3 build with PlatformIO; split `main.cpp` into `outputs`, `hostlink`, `radio`, `buttons`, `config`; fix findings 1, 2, 4, 8, 13, 14 in v1 behaviour; build flags for both boards | `firmware/esp32s3/src/*`, `firmware/esp32c3/*`, both `platformio.ini` | none (v1 code only) | `pio run` both boards clean |
| **B** Pure C++ mesh core | Frame codec, HMAC (mbedtls on device, small portable impl for native), dedupe with boot epoch, arbiter (stickiness, rank, conflict), sound-seq healing, pairing state machine; no Arduino includes | `firmware/lib/meshcore/**`, `firmware/test/native/**` | Wave 0 | `pio test -e native` passes `mesh_vectors.txt` |
| **C** Python mesh reference + simulator | Python codec matching the vectors (`hardware/mesh_codec.py`), lossy/bursty radio simulator with N nodes, reboots, partitions, two masters, remote commands; scenarios as tests | `src/archerytimer/hardware/mesh_codec.py`, `tools/mesh_sim/**`, `tests/mesh_sim/**` | Wave 0 | scenarios: no flip-flop, reboot < 1 s, emergency delivered at 30 % loss |
| **D** Serial v2 host side | `protocol.py` bodies for the new frames, `sim_device` support, `serial_worker` handshake (`$R`, `$C`), roster and feed events as typed queue items | `hardware/protocol.py`, `hardware/sim_device.py`, `hardware/serial_worker.py`, `tests/hardware/**` | Wave 0 | vectors replay, handshake tests with `sim_device` |
| **E** Core roster, remotes, takeover | Beacon v2, roster, conflict detection, remote registry with permissions and pairing flow (host side), manual takeover command, `source` for commands from remotes | `core_service/netdisco.py`, `node.py`, new `roster.py`, `remotes.py`, `tests/core_service/test_roster*.py`, `test_remotes*.py` | Wave 0 (IPC builders, D's types) | unit tests with fakes, no serial needed |
| **F** UI | Timer network screen, status chip, pairing dialog, remotes screen, takeover confirm, conflict banner; strings in both locales | `ui_client/screens/network.py`, new `screens/remotes.py`, `sections/status_bar.py`, `locales/sv.toml`, `locales/en.toml`, `tests/ui_client/**` | Wave 0 (IPC messages only) | screens render from fake messages, keys identical in sv/en |
| **G** MeshFollower service | `$X`/`$Y` to Snapshot rebuild (`remaining` to deadline), `SESSION` handling, commands back as CMD, fail-safe on lost feed | new `core_service/mesh_follower.py`, `tests/core_service/test_mesh_follower.py` | Wave 0 (D's types, SESSION spec) | follower UI snapshot matches a leader's within 5 ms in a fake-clock test |

Files that **no WP may edit** (integrator only, Wave 2): `core_service/service.py`, `cluster.py`,
`__main__.py`, `ipc/messages.py` bodies, `ui_client/app.py`, `CLAUDE.md`, `structure.md`, any file in the
Wave 0 contract list. A WP that needs a change there writes it as a short "integration note" at the end
of its report.

## Rules every agent gets

- Read first: `CLAUDE.md`, `structure.md`, `docs/decisions/0002-*`, `docs/mesh.md`, then only your area.
- Edit only files you own. New files in your directory are fine. Never touch contracts.
- Never invent archery rules or timings. No git. No full test suite: run **only your own tests**, plus
  ruff and mypy on your files (where mypy strict applies).
- Do not claim hardware behaviour. Anything uncompiled or unrun on a board is reported as "not verified".
- Coding standards of `CLAUDE.md` (frozen dataclasses with `SLOTS`, injectable clock, no sleeps in tests,
  no user-facing strings outside `locales/`).
- Report format (under 200 words): files changed, tests run and result, contract gaps found,
  integration notes for the integrator, anything left undone.

## Wave 2: integration (me)

1. Apply integration notes; wire D, E, G into `service.py`, `cluster.py`, `__main__.py`, `ui_client/app.py`.
2. Cross-check: run B's native tests and C's Python codec on the same vectors; run C's simulator against
   B's arbiter through the vectors (any mismatch is a bug in one of them, not in the contract).
3. Full suite once, ruff, mypy; update `docs/espnow.md` (replace by `docs/mesh.md`), `structure.md`,
   `CLAUDE.md` status; list "not verified on hardware".

## Order and speed-up

```text
Wave 0 ──┬─ A ──────────────┐
         ├─ B ──────────────┤
         ├─ C ──────────────┼─> Wave 2 ─> Wave 3 (hardware, user)
         ├─ D ──┬─ (E, G need D's types: they use the Wave 0 stubs, not D's code)
         ├─ E ──┤
         ├─ F ──┤
         └─ G ──┘
```

Seven WPs run at once. Expected critical path: Wave 0, then the longest WP (B or G), then Wave 2.
Risk: a contract that is wrong makes several WPs wrong at once, so Wave 0 gets a self-review (and a
read-only review agent over `mesh.md` and the vectors) before launching.

## Launch checklist

1. Wave 0 files written and reviewed.
2. Launch A-G in one message (background agents), each with the rules above and its row of the table.
3. Collect reports, resolve contract gaps in Wave 0 files, then run Wave 2.
