# ESP-NOW sync between ESP32 devices

Nearby ESP32 boards running this firmware (`firmware/esp32s3/`, also built for the C3 Super
Mini) can follow the timer's lights and sound without WiFi, a router or a computer, and can
send button presses back. Not verified on hardware yet: the firmware has never been compiled.

## Roles (`$M,<n>`, stored in the MCU's flash)

| n | Mode | Outputs come from | Transmits state |
| --- | --- | --- | --- |
| 0 | `off` | host (serial) | no |
| 1 | `bridge` | host | yes, to nearby devices; also relays their buttons to the host |
| 2 | `follow` | nearby devices (host frames are ACKed but ignored) | no |
| 3 | `auto` | host while it is alive, otherwise nearby devices | yes, while the host is alive |

Typical set-ups:

- **Computer with lights, others nearby without a computer:** the computer's ESP32 in `bridge`
  (or `auto`), the others built as `esp32s3-standalone` / `esp32c3-standalone` (default `follow`).
- **Redundancy:** `auto` on every device with a host. If its host dies, it keeps following
  whoever is still transmitting instead of going dark.
- **Isolation:** `off` on a device that should only ever obey its own host.

A host picks the mode with `--espnow`, `[node] espnow` or a `settings` IPC message, and the
serial worker re-sends it on every reconnect. The MCU reports `$N,<mode>,<peers>,<src>`
(`src` = `H` host, `E` ESP-NOW, `N` none) about once a second; the core forwards it in the
`link` IPC message so the status screen can show it.

## Over the air

Broadcast frames, channel `ESPNOW_CHANNEL` (default 1, same on all devices), 16 bytes:

```text
0 magic 0xA7 | 1 version 1 | 2 type | 3 src node id | 4-5 net key (LE) | 6-7 seq (LE)
8..14 payload | 15 XOR of bytes 0..14
```

| Type | Payload | Sent |
| --- | --- | --- |
| 1 STATE | lights mask (G=1 Y=2 R=4), buzzer | on change and every 200 ms |
| 2 SOUND | count, blast ms / 10, gap ms / 10 | per whistle event |
| 3 BUZZ | on | per change |
| 4 BTN | slot, id, down | per button edge, only by devices with no host |

Every frame is sent immediately and repeated twice 3 ms later (broadcast has no ACK);
receivers drop repeats by sequence number. Events use the same timing as the serial path, so
expect about a millisecond of air latency.

- **Who is followed:** devices follow the STATE source with the lowest node id, and switch only
  after it has been quiet for 1.5 s. A bridge that hears a lower id transmitting stays quiet,
  so two bridges never fight. (Node id = hash of the MAC, 1..250; override with `-DNODE_ID`.)
- **Fail-safe:** no active source for 1 s (host or ESP-NOW, per the mode) means RED, silence
  and a blinking fault LED.
- **Buttons from a box with no host:** broadcast as BTN with a slot (`-DESPNOW_SLOT=1..8`, unique
  per device); the bridge relays them to its host as `$K,<slot*10+id>`, so slot 2 button 3 is
  `mcu:23` in `[buttons]`. Local buttons on a device with a host stay `mcu:1..9`.
- **Net key:** `-DESPNOW_NET_KEY=0x....` separates two installations in range of each other.
  It is **not** authentication: anyone with the firmware can send frames. Don't rely on it for
  safety against a hostile neighbour.

## Build

```text
cd firmware/esp32s3 && pio run -e esp32-s3-devkitc-1      # with a host on USB
cd firmware/esp32s3 && pio run -e esp32-s3-standalone     # no host, follows nearby devices
cd firmware/esp32c3 && pio run -e esp32c3-supermini       # or esp32c3-standalone
```

Supports Arduino-ESP32 core 2.x and 3.x (receive-callback signature differs; handled with a
version check). If a build fails on the callback or `esp_mac.h`, pin the platform version.

## Known limits

- Range is that of ESP-NOW (tens to a couple of hundred metres line of sight); not measured.
- It shares the 2.4 GHz band with WiFi: use the same channel on every device and keep any
  WiFi network on that channel too, or expect interference.
- Distance and walls untested; a lost SOUND frame is only protected by the two repeats.
