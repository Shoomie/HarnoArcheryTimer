# ADR 0002: ESP32 mesh, named master, paired remotes

- Status: accepted and implemented (2026-10)
- Wire format and rules: [`docs/mesh.md`](../mesh.md). Serial side: [`docs/protocol.md`](../protocol.md).

## Context

The first radio design (broadcast frames, lowest node id wins, one shared network key) had problems that matter on a
shooting line: a rebooted transmitter was ignored by its listeners until its sequence number caught up, two nodes could
hash to the same id, the "master" was whoever had the lowest hash rather than the device the operator chose, one lost
frame could drop a whistle or an emergency button press, and nothing was authenticated. It also could not synchronize
a *software* timer, because frames only carried lights and buzzer.

## Decisions

1. **One firmware image.** Behaviour comes from stored configuration (name, lights/sound/remote/radio on or off,
   channel, mesh key) and from the role the host declares with `$R` at every connect: `M` master, `F` mirror of a
   LAN leader, `E` radio-fed host, `N` none. With no host the node follows the radio. With nothing live for 1 s:
   RED and silent.
2. **Named master.** Every timer frame carries a random `master_id` and a rank (2 leader engine, 1 mirror). Nodes keep
   following the live master they have (stickiness) and switch only after silence or to a higher rank, never to a
   lower id just because it is lower. Two rank-2 masters are a **conflict**: nobody flips, the UI shows a banner
   naming both.
3. **Identity is the MAC** from the receive callback, not a field in the frame. Dedupe key is
   `(mac, boot epoch, seq)`, so a reboot is accepted at once.
4. **Authentication.** Every frame carries an 8-byte truncated HMAC-SHA256 under a per-installation **mesh key**.
   Remote commands are signed with a **per-remote key**. Keys are exchanged by X25519 during **pairing**, which the
   operator accepts in the UI, identified by name and MAC. No physical button press is needed on the remote.
5. **Remote rights are per remote**, set by the master's operator. A remote may only ever send primary, pause, resume,
   stop end, next, back or emergency; reset, quit, clear-emergency and settings never travel by radio. Emergency is
   always allowed for a paired remote. Remote buttons have a fixed pinout and fixed actions
   (1 start/next, 2 pause, 3 stop end, 4 emergency).
6. **Events heal themselves.** The timer heartbeat carries the sound sequence and age, so a missed whistle frame is
   recovered without replaying an old one. Emergency is a latched flag, not an event. After any change toward the
   safe state the master resends the timer frame every 50 ms for 500 ms. Silence propagates to every follower.
7. **Replay protection.** A persisted **session counter** (owned by the master's core, +1 at every core start and
   serial connect) lets every node drop frames from an earlier session, including across a node reboot.
8. **Radio-fed software follower.** A computer can show and operate the timer with nothing but its ESP32 on the radio
   (`--leader radio`): the node forwards timer, sound and session frames to the host, which rebuilds a snapshot, and
   the host's commands go back out as `CMD` from a paired remote.
9. **Single hop, manual takeover.** Relaying is specified but not built. "Make this device the main timer" (with a
   confirm) is the takeover; there is no automatic failover (open question: who may become master).
10. **Software side.** Every core broadcasts a UDP beacon (role, name, follows, session state). The timer-network
    roster lists LAN cores, radio modules and remotes in plain words and raises the conflict banner.
    A new LAN follower is *pending* (watch only) until approved on the leader, which then hands it a per-follower key
    and the radio mesh key.
11. **Fixed radio channel**, configurable over USB (`$C,chan`), no scan.

## Consequences

- Core, firmware and the Python mesh simulator share frame vectors (`firmware/mesh_vectors.txt`,
  `firmware/test_vectors_v2.txt`) and arbiter scenarios (`firmware/arbiter_scenarios.txt`), so the C++ and Python
  implementations cannot drift apart silently.
- The key agreement is not authenticated against an active attacker inside the pairing window; the operator's accept
  is the countermeasure.
- Range and latency are those of single-hop ESP-NOW. Anything beyond is future work.
