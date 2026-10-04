# Shared brief for the Wave 1 agents (see 0003-mesh-parallel-workflow.md for the work packages)

Project: `E:\HarnoArcheryTimer`, archery timer with ESP32 mesh. You build ONE work package (WP) of the mesh v2 work.

Read first, in this order: `CLAUDE.md`, `structure.md`, `docs/decisions/0002-mesh-and-firmware-review.md`,
`docs/mesh.md`, the "Serial v2" section at the end of `docs/protocol.md`, then only your own area.

Frozen contracts (read, never edit; if something is wrong or missing, STOP that part and report it as a
contract gap): `docs/mesh.md`, `docs/protocol.md` (Serial v2), `firmware/test_vectors_v2.txt`,
`firmware/mesh_vectors.txt`, `firmware/arbiter_scenarios.txt`, `src/archerytimer/hardware/mesh_types.py`,
the mesh v2 builders at the end of `src/archerytimer/ipc/messages.py`.

Rules:
- Edit ONLY the files your WP owns (below). New files inside your own directories are fine. Other agents
  work at the same moment on the other WPs, so a file outside your list may change under you.
- Never edit: `core_service/service.py`, `cluster.py`, `__main__.py`, `ui_client/app.py`, `CLAUDE.md`,
  `structure.md`, the contracts above. Write what those files need as an "integration note" in your report.
- Never invent archery rules or timings. No git. Do NOT run the full test suite: run only your own tests, plus
  `ruff check` / `ruff format` on your files and `mypy` where strict applies (`core/`, `ipc/`,
  `hardware/protocol.py`). Python: `E:\HarnoArcheryTimer\.venv\Scripts\python.exe` (3.14).
- Standards (CLAUDE.md): type hints; `@dataclass(frozen=True, **SLOTS)`; inject clock/transport/serial port;
  tests use `FakeClock` and never sleep; no user-facing strings outside `locales/` (keep sv and en keys
  identical); `pathlib`; clean thread shutdown (RED and silence first). Match surrounding code style and comment density.
- Scratch/temporary files go in the scratchpad dir, never in the repo. Avoid giant shell heredocs; for
  multi-line edits use the Edit/Write tools or a small Python script file.
- Anything not compiled or not run on a real board is reported "not verified on hardware". Do not claim otherwise.
- Be fast: build the package, run your own checks once, report. Do not re-verify finished work.

Final report (under 200 words): files created/changed; tests run and result; contract gaps found;
integration notes for the integrator; anything left undone.
