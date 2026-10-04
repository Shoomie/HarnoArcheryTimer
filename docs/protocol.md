# Serial protocol (v1 and v2)

Version 1 is the base protocol (lights, sound, heartbeat, buttons). Version 2 adds the wireless mesh frames and is
described in the last section; a device reports which one it speaks in `$I`.

Host (Pi or PC) to microcontroller (MCU) link for lights and sound. Line-based ASCII with an
NMEA-style XOR checksum, readable in any serial terminal and easy to parse on an Arduino.

- Reference implementation: `src/archerytimer/hardware/protocol.py` (pure functions).
- Shared test vectors: `firmware/test_vectors.txt` (v1) and `firmware/test_vectors_v2.txt` (v2), replayed by the Python tests
  and by the native firmware tests.
- Simulated MCU: `src/archerytimer/hardware/sim_device.py`.

## Transport

115200 baud, 8N1 (ignored by native USB CDC). Prefer boards with native USB for latency.

## Frame format

```text
$<CMD>[,<arg>...]*<XX>\n
```

- `<CMD>` is one letter. Arguments are comma-separated ASCII, no spaces needed.
- `XX` is two **uppercase** hex digits: the XOR of every byte between `$` and `*`.
  Example: `$L,G*27`, because `0x4C ^ 0x2C ^ 0x47 = 0x27`.
- The terminator is `\n`. A receiver also accepts `\r\n` and ignores empty lines.
- A whole frame including the `\n` is at most **64 bytes**.
- Only printable ASCII (0x20-0x7E) is allowed between `$` and `*`; `$` and `*` themselves
  may not appear there.
- Integers are canonical decimal: digits only, no sign, no leading zeros.

The receiver resynchronizes on every `\n`: whatever came before it is one candidate frame,
and a bad one is discarded without affecting the next.

## Commands

| Direction | Frame | Arguments | Meaning |
| --- | --- | --- | --- |
| Host to MCU | `$L,<state>` | `G`, `Y`, `R`, `O` (off), or a combination of unique `G`/`Y`/`R` such as `RY` | Lights. The MCU decides which combinations it can show. |
| Host to MCU | `$S,<n>[,<id>]` | 0-99, id 1-255 | Play `n` blasts, timed by the MCU. `0` means silence now. The optional id (capability `W`) lets the MCU ignore host repeats. |
| Host to MCU | `$B,<0\|1>` | `0` or `1` | Raw buzzer or horn off or on, for host-timed sound. |
| Host to MCU | `$G,<name>` | 1-8 characters of `A-Z0-9` | Line-group indicator (`AB`, `CD`...). |
| Host to MCU | `$T,<ms>` | 0 to 4294967295 | Remaining milliseconds, for an MCU-driven digit display. |
| Host to MCU | `$H,<seq>,<L>,<G>` | seq 0 to 4294967295, light state as `$L`, group as `$G` or empty | Heartbeat carrying the full current state. |
| Host to MCU | `$V` | none | Hello and version request. |
| MCU to host | `$I,<proto>,<fw>,<caps>` | proto 0-255, fw up to 16 characters of `A-Za-z0-9._+-`, caps a subset of `LSBGTKNWR` (may be empty) | Hello reply. |
| MCU to host | `$A,<seq>` | seq as in the heartbeat | Acknowledges that heartbeat. |
| Host to MCU | `$M,<n>` | 0 off, 1 bridge, 2 follow, 3 auto | Set the ESP-NOW role (needs capability `N`); the MCU stores it. Legacy alias of `$R` (see Serial v2 and `docs/mesh.md`). |
| MCU to host | `$N,<mode>,<peers>,<src>` | mode 0-3, peers 0-99 devices heard, src `H` host / `E` ESP-NOW / `N` none | ESP-NOW status, sent on change and about once a second. |
| MCU to host | `$K,<id>,<0\|1>` | id 1-99, `1` = went down, `0` = went up | Button event from an input pin on the MCU (needs capability `K`). Sent on every debounced edge; the host decides what a press, hold or release means. |
| MCU to host | `$E,<code>` | `CS`, `UC`, `BA` or `OV` | The MCU rejected a frame. |

Capability letters: `L` lights, `S` MCU-timed whistle, `B` buzzer, `G` group, `T` remaining time,
`K` the MCU reports button events (`$K`), `N` ESP-NOW sync (`$M`, `$N`), `W` repeat-safe whistle ids and timings (`$S`), `R` mesh v2.
A command whose capability the MCU lacks is answered with `$E,UC`.

## Error codes

Checks run in this order, and the first failure decides the code:

| Code | Meaning | On the wire? |
| --- | --- | --- |
| `OV` | Frame longer than 64 bytes including the newline | Yes, `$E,OV` |
| `MF` | Malformed framing: missing `$` or `*XX`, lowercase hex, stray delimiter, non-ASCII | No, silently dropped |
| `CS` | Checksum mismatch | Yes, `$E,CS` |
| `UC` | Unknown command letter (or a capability the MCU lacks) | Yes, `$E,UC` |
| `BA` | Wrong argument count or an invalid argument | Yes, `$E,BA` |

A frame that fails any check must not change MCU state.

## Behavior

- **Idempotent assertions.** Repeating a state frame (`L`, `B`, `G`, `T`, `H`) is always
  safe. See "`$S` is an event" below for `$S`.
- **Immediate sends.** State changes go out at once as one frame each, never batched behind
  other traffic.
- **Heartbeat.** The host sends `$H` every 200 ms, re-asserting lights and group, so a
  dropped frame heals within 200 ms. The MCU replies `$A,<seq>`. Only heartbeats are
  acknowledged; other commands get a reply only on error.
- **Watchdog.** If the MCU sees no valid host frame for about 1 s, it forces lights to RED,
  stops all sound and, if it can, blinks a fault indicator. Only frames that decode
  correctly count. The next valid frame clears the fault, and the host then re-asserts the
  full state. An MCU boots into the same safe state (RED, silent).
- **Connect sequence.** Open the port, send `$V`, expect `$I` within 500 ms, push the full
  state, then start heartbeats. The host handles proto 1 and 2 and sends the v2 frames only to proto 2 devices.
- **Reconnect.** The host discovers the port by USB VID/PID with a manual override, and
  reconnects with backoff after an unplug.

## `$S` is an event: ids heal a lost frame

`$S,<n>` starts `n` blasts, so repeating it would replay them. Devices with capability `W` therefore
accept `$S,<n>,<id>` (id 1-255, never 0) and ignore a frame whose id equals the last one they acted on.
The host repeats each whistle frame 40 ms and 120 ms later, so a lost frame is healed and a repeat is
harmless. Devices without `W` get the plain `$S,<n>` once. `$S,0` (silence) is always safe to repeat.
See `docs/audio.md`.

## Examples

```text
host -> $V*56
mcu  -> $I,1,esp32s3-0.1.0,LSBGT*21
host -> $H,1,R,*07
mcu  -> $A,1*5C
host -> $L,G*27          lights green
host -> $S,1*4E          one blast: start shooting
host -> $H,2,G,AB*12     next heartbeat re-asserts green and group AB
```

Related frames are covered in `firmware/test_vectors.txt`.

## Serial v2 (mesh; radio side in `docs/mesh.md`)

`$I` reports proto `2` and capability `R` (mesh v2) on devices that implement this section; a host treats
proto 1 as a device without it and sends none of the frames below. All v1 behaviour is unchanged.
Binary data is **uppercase hex**. `<mac>` = 12 hex digits, `<id>` = 8 hex digits (never `00000000` when sent
by a host). **Long commands** `J F W Y D P` may be up to 160 bytes including the newline; every other
command keeps the 64-byte limit (OV rules otherwise as in v1).

| Dir | Frame | Arguments | Meaning |
| --- | --- | --- | --- |
| H to M | `$R,<role>[,<id>,<session>]` | `M` master (id and session required: the host's own master id and its persisted session counter u32 >= 1), `F` mirror (id and session of the leader it follows, required), `E` radio-fed host, `N` none (no id or session for `E`/`N`) | Role in the mesh. Sent in every connect sequence; replaces `$M` (still accepted: 0 off to `N`, 1 bridge to `M`/`F`, 2 follow to `E`, 3 auto to `M`). |
| H to M | `$C,<key>,<value>` (the MCU never reveals `mkey`: it answers `$C,mkey,` + 32 zeros) | `name` 1-12 of `A-Za-z0-9_-`; `lights` `sound` `radio` `remote` `0\|1`; `chan` 1-13; `mkey` 32 hex; `btn1`..`btn4` action 0-7 (0 none, 1-7 as in mesh.md) | Store configuration in NVS. The MCU answers with the same `$C` frame on success, `$E,BA` otherwise. |
| H to M | `$Q` | none | Ask for the whole configuration; the MCU sends one `$C` per key (`mkey` is never sent back). |
| H to M | `$U,<mode>,<phase>,<rem_ms>,<end>,<ends>,<group>,<round>,<rounds>,<flags>,<rev>` | mode 0-3, phase/end/ends/group/round/rounds/rev 0-255, rem_ms u32, flags 0-7 | Timer state for the radio TIMER frame (role `M`/`F`). Sent with every heartbeat and on change. `rem_ms` is valid at the moment the frame is received; the MCU adds its own elapsed time when it transmits (unless paused, flags bit0). |
| H to M | `$J,<rev>,<flags>,<ends>,<pract>,<prep>,<shoot>,<warn>,<delay>,<seq>,<groups>` | as the SESSION frame; times in ms, `4294967295` keeps the sequence's value; `<seq>` is 1-16 of `A-Za-z0-9_-`; `<groups>` is `AB:CD:...` (1-8, each 1-8 of `A-Z0-9`) | Session for the radio SESSION frame. Sent on change and every 2 s. |
| H to M | `$P,open,<s>` / `close` | s 1-120 | Pairing window. |
| H to M | `$P,accept,<mac>,<mask>` / `reject,<mac>` / `del,<mac>` | mask 2 hex digits (bit n-1 = action n) | Operator's decision, remove a remote. |
| H to M | `$P,ack,<mac>,<counter>,<result>` | result 0 done, 1 denied | The host's answer to a remote command; the MCU sends CMD_ACK. |
| H to M | `$P,tx,<action>` | 1-7 | A radio-fed host sends a command through the mesh as a paired remote. |
| H to M | `$S,<n>,<id>,<blast_ms>,<gap_ms>` | blast and gap 10-2000, multiples of 10 | `$S` with explicit timing (needs `W`). 1, 2 and 4 arguments are valid; 3 stays an error. |
| M to H | `$O,<role>,<src>,<peers>,<conflict>,<id>,<chan>` | role `M F E N`, src `H E N`, conflict 0/1, id master followed or own (`00000000` none) | Status v2, on change and about once a second. Replaces `$N` on proto 2. |
| M to H | `$D,<mac>,<kind>,<caps>,<rssi>,<fw>,<name>` or `$D,<mac>,gone` | kind `N` node, `R` remote, `M` master, `F` mirror, `E` radio-fed host; caps subset of `LSBKR` or `-`; rssi = dBm magnitude 0-127; fw `a.b.c`; name or `-` | Roster change. |
| M to H | `$F,<hex>` / `$W,<hex>` / `$Y,<hex>` | TIMER / SOUND / SESSION payload (no header, no tag) | Radio feed for role `E`. |
| M to H | `$P,req,<mac>,<name>,<caps>` | | A remote asks to pair. |
| M to H | `$P,cmd,<mac>,<action>,<counter>` | action 1-7 | A paired remote's command (already checked against its key, counter and mask). |
| M to H | `$P,paired,<mac>` / `$P,state,<open>,<seconds_left>` | | Pairing finished, window state. |
