// Device glue for firmware/lib/meshcore (README "Device must implement"): clock, RNG, session store in NVS, key storage.
// The HMAC itself (mbedtls, -DMESHCORE_EXTERNAL_HMAC) lives in meshglue.cpp too.
#pragma once
#include <Arduino.h>

#include "mesh_cmd.h"
#include "mesh_session.h"

// Monotonic milliseconds, the value handed to every meshcore call.
inline uint32_t meshNowMs() { return millis(); }

// Hardware random bytes (esp_fill_random). The RF subsystem supplies the entropy: if WiFi is off the helper brings
// it up for the call and turns it off again, so keys never come from the pseudo-random fallback.
void meshRandom(uint8_t *out, size_t n);

// Highest accepted session per master_id in NVS (slots s0..s7, round robin); the arbiter writes only when it rises.
class NvsSessionStore : public mesh::SessionStore {
 public:
  bool load(uint32_t master_id, uint32_t *session) override;
  void save(uint32_t master_id, uint32_t session) override;
};

// Keys. Mesh key (16 B) and own remote key (16 B, a paired remote) live in NVS ("mkey", "rkey").
bool keysLoadMesh(uint8_t out[16]);
void keysStoreMesh(const uint8_t key[16]);
bool keysLoadRemote(uint8_t out[16]);
void keysStoreRemote(const uint8_t key[16]);
void keysClearRemote();

// The master's table of paired remotes (rt0..rt7: mac, key, permission mask, last counter).
void keysLoadRemotes(mesh::CmdGate &gate);
void keysSaveRemote(const mesh::RemoteEntry &entry);  // by MAC; first free slot for a new one
void keysEraseRemote(const uint8_t mac[6]);

// A remote's own CMD counter. `cnt` in NVS is a high-water mark (the counters actually used stay below it), so a
// reboot continues above everything ever sent without writing flash on every press.
uint32_t keysCmdCounterStart();                  // value to hand to CmdSender (the stored high-water mark)
void keysCmdCounterReserve(uint32_t used_next);  // call BEFORE sending `used_next`; extends the mark in blocks
