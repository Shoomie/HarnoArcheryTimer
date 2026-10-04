#include "meshglue.h"

#include <WiFi.h>
#include <esp_random.h>
#include <mbedtls/md.h>

#include "config.h"
#include "mesh_crypto.h"

// --- HMAC-SHA256 through mbedtls (meshcore is built with -DMESHCORE_EXTERNAL_HMAC) -------------------------------
// One reusable context: hmac_sha256 is only ever called from the Arduino loop task (receive decode, frame encode,
// pairing), never from the WiFi callback.
namespace mesh {
void hmac_sha256(const uint8_t *key, size_t key_len, const Part *parts, size_t n_parts, uint8_t out[32]) {
  static mbedtls_md_context_t ctx;
  static bool ready = false;
  memset(out, 0, 32);  // a failure leaves a tag that never verifies
  const mbedtls_md_info_t *info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  if (!ready) {
    mbedtls_md_init(&ctx);
    if (!info || mbedtls_md_setup(&ctx, info, 1) != 0) return;
    ready = true;
  }
  if (mbedtls_md_hmac_starts(&ctx, key, key_len) != 0) return;
  for (size_t i = 0; i < n_parts; i++)
    if (parts[i].n && mbedtls_md_hmac_update(&ctx, parts[i].p, parts[i].n) != 0) return;
  mbedtls_md_hmac_finish(&ctx, out);
}
}  // namespace mesh

void meshRandom(uint8_t *out, size_t n) {
  const bool rfWasOff = WiFi.getMode() == WIFI_OFF;
  if (rfWasOff) WiFi.mode(WIFI_STA);  // entropy source needs the RF subsystem running
  esp_fill_random(out, n);
  if (rfWasOff) WiFi.mode(WIFI_OFF);
}

// --- session store ------------------------------------------------------------------------------------------------
static void sessionKey(uint8_t i, char *k) { snprintf(k, 4, "s%u", i); }

bool NvsSessionStore::load(uint32_t master_id, uint32_t *session) {
  for (uint8_t i = 0; i < 8; i++) {
    char k[4];
    uint32_t rec[2];
    sessionKey(i, k);
    if (configGetBlob(k, rec, sizeof rec) && rec[0] == master_id) {
      *session = rec[1];
      return true;
    }
  }
  return false;
}

void NvsSessionStore::save(uint32_t master_id, uint32_t session) {
  int slot = -1;
  for (uint8_t i = 0; i < 8 && slot < 0; i++) {
    char k[4];
    uint32_t rec[2];
    sessionKey(i, k);
    if (configGetBlob(k, rec, sizeof rec) && rec[0] == master_id) slot = i;
  }
  if (slot < 0) {  // a new master: round robin over the 8 slots
    uint8_t next = configGetU8("sidx", 0) & 7;
    slot = next;
    configPutU8("sidx", (uint8_t)((next + 1) & 7));
  }
  char k[4];
  const uint32_t rec[2] = {master_id, session};
  sessionKey((uint8_t)slot, k);
  configPutBlob(k, rec, sizeof rec);
}

// --- keys ---------------------------------------------------------------------------------------------------------
bool keysLoadMesh(uint8_t out[16]) { return configGetBlob("mkey", out, 16); }
void keysStoreMesh(const uint8_t key[16]) { configPutBlob("mkey", key, 16); }
void keysClearMesh() { configRemove("mkey"); }
bool keysLoadRemote(uint8_t out[16]) { return configGetBlob("rkey", out, 16); }
void keysStoreRemote(const uint8_t key[16]) { configPutBlob("rkey", key, 16); }
void keysClearRemote() { configRemove("rkey"); }

// Remote record: mac 6 | key 16 | mask 1 | last_counter 4 (LE) = 27 bytes
static const size_t REC_LEN = 27;
static void remoteSlotKey(uint8_t i, char *k) { snprintf(k, 4, "rt%u", i); }

void keysLoadRemotes(mesh::CmdGate &gate) {
  for (uint8_t i = 0; i < mesh::kMaxRemotes; i++) {
    char k[4];
    uint8_t rec[REC_LEN];
    remoteSlotKey(i, k);
    if (!configGetBlob(k, rec, REC_LEN)) continue;
    uint32_t counter = rec[23] | (rec[24] << 8) | ((uint32_t)rec[25] << 16) | ((uint32_t)rec[26] << 24);
    gate.addRemote(rec, rec + 6, rec[22], counter);
  }
}

void keysSaveRemote(const mesh::RemoteEntry &e) {
  int slot = -1, freeSlot = -1;
  for (uint8_t i = 0; i < mesh::kMaxRemotes; i++) {
    char k[4];
    uint8_t rec[REC_LEN];
    remoteSlotKey(i, k);
    if (!configGetBlob(k, rec, REC_LEN)) {
      if (freeSlot < 0) freeSlot = i;
    } else if (memcmp(rec, e.mac, 6) == 0) {
      slot = i;
    }
  }
  if (slot < 0) slot = freeSlot;
  if (slot < 0) return;
  uint8_t rec[REC_LEN];
  memcpy(rec, e.mac, 6);
  memcpy(rec + 6, e.key, 16);
  rec[22] = e.mask;
  for (int b = 0; b < 4; b++) rec[23 + b] = (uint8_t)(e.last_counter >> (8 * b));
  char k[4];
  remoteSlotKey((uint8_t)slot, k);
  configPutBlob(k, rec, REC_LEN);
}

void keysEraseRemote(const uint8_t mac[6]) {
  for (uint8_t i = 0; i < mesh::kMaxRemotes; i++) {
    char k[4];
    uint8_t rec[REC_LEN];
    remoteSlotKey(i, k);
    if (configGetBlob(k, rec, REC_LEN) && memcmp(rec, mac, 6) == 0) configRemove(k);
  }
}

// --- CMD counter --------------------------------------------------------------------------------------------------
static const uint32_t CNT_BLOCK = 32;
static uint32_t cntMark = 0;
static bool cntLoaded = false;

uint32_t keysCmdCounterStart() {
  cntMark = configGetU32("cnt", 0);
  cntLoaded = true;
  return cntMark;  // everything below the mark may have been used; CmdSender::begin() hands out mark + 1 first
}

void keysCmdCounterReserve(uint32_t used_next) {
  if (!cntLoaded) keysCmdCounterStart();
  if (used_next <= cntMark) return;
  cntMark = used_next + CNT_BLOCK;
  configPutU32("cnt", cntMark);
}
