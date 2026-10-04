// Archery Timer reference firmware, ESP32-S3 and ESP32-C3: serial protocol v1 + v2 and the mesh v2 radio.
// Lights on GPIO, MCU-timed whistle, host-timed buzzer, optional PWM beeper, buttons, 1 s watchdog, hello handshake.
//
// Modules: outputs (lights/horn/beeper/fault LED), hostlink (serial; frame logic in lib/hostcore), radio (mesh v2 node on
// lib/meshcore), meshglue (clock/HMAC/RNG/NVS keys), buttons, config (NVS). This file wires them together and applies
// the arbiter's decision (docs/mesh.md section 4) to the pins:
//   role M / F (set by `$R`): the host owns lights and sound; the node transmits TIMER/SOUND/SESSION to the mesh
//   role E / N: the best live master on the radio drives the outputs (E also forwards its frames to the host)
//   v1 hosts that never send `$R` get the documented `$M` mapping (0 off, 1 bridge, 2 follow, 3 auto)
// Fail-safe: no live source for 1 s -> RED, silence, blink the fault LED.
#include <Arduino.h>

#include "buttons.h"
#include "config.h"
#include "hostcore.h"
#include "hostlink.h"
#include "mesh_config.h"
#include "mesh_frame.h"
#include "meshglue.h"
#include "outputs.h"
#include "radio.h"
#include "version.h"

static const char *FW_VERSION = FW_VERSION_STR;
static const char *CAPS = "LSBKNWR";  // lights, MCU-timed whistle, buzzer, buttons, ESP-NOW (legacy $M), whistle ids, mesh v2

// Legacy ESP-NOW mode on first boot: 0 off, 1 bridge, 2 follow, 3 auto. A device with no host attached (a stand-alone
// light box) should be built with 2. A v1 host can change it ($M); a v2 host uses $R instead.
#ifndef ESPNOW_DEFAULT_MODE
#define ESPNOW_DEFAULT_MODE 0
#endif

static const uint32_t WATCHDOG_MS = 1000;
static const uint32_t EMERGENCY_HOLD_MS = 1000;  // a remote's own emergency press keeps its outputs safe this long

static bool lightsOn = true, soundOn = true, remoteOn = false;
static uint8_t btnAction[4] = {0, 0, 0, 0};
static bool legacyHost = true;  // no `$R` seen yet: report status as `$N`
static uint8_t legacyMode = ESPNOW_DEFAULT_MODE;
static uint32_t lastStatusMs = 0;
static char lastStatusBody[48] = "";
static uint32_t safeHoldUntil = 0;

static bool hostAliveNow() { return hostlinkAlive(WATCHDOG_MS); }

// --- legacy `$M` -----------------------------------------------------------------------------------------------
// 0 off -> host drives, radio off; 1 bridge and 3 auto -> master with an id derived from the MAC; 2 follow -> E without
// forwarding (a v1 host does not understand `$F`). The mesh needs a key: the first bridge creates one.
static void applyLegacyMode(uint8_t m, bool fromHost) {
  legacyMode = m;
  if (fromHost) {
    configPutU8("espnow", m);
    configPutU8("radio", m != 0 ? 1 : 0);
    if (m == 1 || m == 3) radioEnsureMeshKey();
    radioSetEnabled(m != 0);
  }
  uint32_t id, session;
  radioLegacyIdentity(&id, &session, true);  // a restarted master must be newer than its last session
  if (m == 2) radioSetRole('E', 0, 0, false);
  else radioSetRole('M', id, session, false);
}

// --- host handlers (serial) -----------------------------------------------------------------------------------
static void onHostLights(uint8_t mask) { radioHostLights(mask); }  // applied through the arbiter (roles M, F)

static void onHostSound(int n, uint16_t blastMs, uint16_t gapMs) {
  if (!radioHostDrives()) return;
  if (blastMs == 0) blastMs = DEFAULT_BLAST_MS;  // host sent no timing
  if (gapMs == 0) gapMs = DEFAULT_GAP_MS;
  outputsStartBlasts(n, blastMs, gapMs);
  radioHostSound((uint8_t)(n < 0 ? 0 : n), blastMs, gapMs);
}

static void onHostBuzz(bool on) {
  if (!radioHostDrives()) return;
  outputsSetHornRaw(on);
  radioHostBuzz(on);
}

static bool onHostMode(uint8_t m) {
  if (!legacyHost) return true;  // a v2 host chose its role with `$R`; a stray `$M` changes nothing
  applyLegacyMode(m, true);
  return true;
}

static bool onHostRole(char role, uint32_t id, uint32_t session) {
  if (!radioSetRole(role, id, session, role == 'E')) return false;
  legacyHost = false;
  return true;
}

static void sendConfigNumber(const char *key, uint32_t v) {
  char b[12];
  snprintf(b, sizeof b, "%lu", (unsigned long)v);
  hostlinkSendConfig(key, b);
}

static void onConfigQuery() {
  hostlinkSendConfig("name", radioName());
  sendConfigNumber("lights", lightsOn);
  sendConfigNumber("sound", soundOn);
  sendConfigNumber("radio", radioEnabled());
  sendConfigNumber("remote", remoteOn);
  sendConfigNumber("chan", radioChannel());
  for (int i = 0; i < 4; i++) {
    char key[5];
    snprintf(key, sizeof key, "btn%d", i + 1);
    sendConfigNumber(key, btnAction[i]);
  }
  // the mesh key is never sent back
}

static void applyCaps() {
  outputsSetEnabled(lightsOn, soundOn);
  radioSetCaps(lightsOn, soundOn, remoteOn);
}

static bool onHostConfig(const char *key, const char *value) {
  uint32_t n = 0;
  if (!strcmp(key, "name")) {
    configPutStr("name", value);
    radioSetName(value);
  } else if (!strcmp(key, "lights")) {
    lightsOn = value[0] == '1';
    configPutU8("lights", lightsOn);
    applyCaps();
  } else if (!strcmp(key, "sound")) {
    soundOn = value[0] == '1';
    configPutU8("sound", soundOn);
    applyCaps();
  } else if (!strcmp(key, "radio")) {
    configPutU8("radio", value[0] == '1');
    radioSetEnabled(value[0] == '1');
  } else if (!strcmp(key, "remote")) {
    remoteOn = value[0] == '1';
    configPutU8("remote", remoteOn);
    applyCaps();
  } else if (!strcmp(key, "chan")) {
    if (!hostcore::parseUint(value, 13, n) || n < 1) return false;
    configPutU8("chan", (uint8_t)n);
    radioSetChannel((uint8_t)n);
  } else if (!strcmp(key, "mkey")) {
    uint8_t k[16];
    size_t len = 0;
    if (!hostcore::hexDecode(value, k, sizeof k, len) || len != 16) return false;
    radioSetMeshKey(k);
    memset(k, 0, sizeof k);
    if (!configHas("radio")) radioSetEnabled(true);  // provisioning a key means the radio is wanted
  } else if (!strncmp(key, "btn", 3) && key[3] >= '1' && key[3] <= '4' && !key[4]) {
    if (!hostcore::parseUint(value, 7, n)) return false;
    btnAction[key[3] - '1'] = (uint8_t)n;
    configPutU8(key, (uint8_t)n);
  } else {
    return false;
  }
  return true;
}

static void onTimerState(const HostTimer &t) { radioHostTimer(t, millis()); }
static void onSession(const HostSession &s) { radioHostSession(s); }

static void holdSafe() { safeHoldUntil = millis() + EMERGENCY_HOLD_MS; }

static bool onPairTx(uint8_t action) {
  if (!radioRemoteSend(action)) return false;
  if (action == mesh::kActionEmergency) holdSafe();
  return true;
}

static bool onPairOpen(uint8_t s) { return radioPairOpen(s); }
static void onPairClose() { radioPairClose(); }
static bool onPairAccept(const uint8_t mac[6], uint8_t mask) { return radioPairAccept(mac, mask); }
static bool onPairReject(const uint8_t mac[6]) { return radioPairReject(mac); }
static bool onPairDelete(const uint8_t mac[6]) { return radioPairDelete(mac); }
static bool onPairAck(const uint8_t mac[6], uint32_t counter, uint8_t result) { return radioHostAck(mac, counter, result); }

// --- buttons ---------------------------------------------------------------------------------------------------
// Host alive: every debounced edge goes to the host as `$K` (it decides press / hold / release). No host: a press sends
// the configured action (`$C btn1..4`) as a CMD frame with this node's remote key. While pairing a press only arms it.
static void onButtonEdge(uint8_t id, bool down) {
  if (radioPairing()) {
    if (down) radioPairPress();
    return;
  }
  if (hostAliveNow()) {
    char b[16];
    if (hostcore::fmtButton(b, sizeof b, id, down)) hostlinkSendFrame(b);
    return;
  }
  if (!down || !remoteOn || id < 1 || id > 4) return;
  const uint8_t action = btnAction[id - 1];
  if (action == 0) return;
  // A remote's own emergency press turns its own outputs safe at once (RED, silent); everything else waits for the master.
  if (radioRemoteSend(action) && action == mesh::kActionEmergency) holdSafe();
}

// Buttons 1 and 2 held for 3 s at power-up (lights blink), or a remote with no keys at all: pairing mode.
static void bootPairing() {
  delay(30);  // let the pull-ups settle
  if (buttonsHeld(1) && buttonsHeld(2)) {
    const uint32_t t0 = millis();
    while (buttonsHeld(1) && buttonsHeld(2)) {
      const uint32_t el = millis() - t0;
      outputsSetOverrideLights(true, ((el / 250) % 2) ? 7 : 0);
      outputsApply();
      if (el >= 3000) {
        radioEnterPairing(true);
        break;
      }
      delay(10);
    }
    outputsSetOverrideLights(false, 0);
  } else if (!radioHasMeshKey() && remoteOn) {
    radioEnterPairing(false);
  }
}

// --- status to the host ----------------------------------------------------------------------------------------
static void statusTick(uint32_t now, const mesh::ArbiterOutput &o) {
  if (!hostAliveNow()) return;
  const char src = o.failsafe ? 'N' : (radioHostDrives() ? 'H' : 'E');
  char body[48];
  size_t n;
  if (legacyHost) {
    if (legacyMode == 0) return;  // v1: status only while ESP-NOW is on
    n = hostcore::fmtEspNowStatus(body, sizeof body, legacyMode, radioPeers(), src);
  } else {
    n = hostcore::fmtMeshStatus(body, sizeof body, radioRole(), src, radioPeers(), o.conflict, radioStatusMasterId(),
                                radioChannel());
  }
  if (!n) return;
  if (strcmp(body, lastStatusBody) != 0 || now - lastStatusMs >= 1000) {
    hostlinkSendFrame(body);
    strcpy(lastStatusBody, body);
    lastStatusMs = now;
  }
}

void setup() {
  outputsBegin();
  configBegin();
  lightsOn = configGetU8("lights", 1) != 0;
  soundOn = configGetU8("sound", 1) != 0;
  remoteOn = configGetU8("remote", 0) != 0;
  for (int i = 0; i < 4; i++) {
    char key[5];
    snprintf(key, sizeof key, "btn%d", i + 1);
    btnAction[i] = configGetU8(key, 0);
    if (btnAction[i] > 7) btnAction[i] = 0;
  }
  buttonsBegin(onButtonEdge);
  HostHandlers hh = {onHostLights, onHostSound, onHostBuzz,   onHostMode,  onHostRole,   onHostConfig,
                     onConfigQuery, onTimerState, onSession, onPairOpen, onPairClose, onPairAccept,
                     onPairReject,  onPairDelete, onPairAck, onPairTx};
  hostlinkBegin(hh, FW_VERSION, CAPS);
  radioBegin(hostlinkSendFrame);
  applyCaps();
  legacyMode = configGetU8("espnow", ESPNOW_DEFAULT_MODE);
  if (legacyMode > 3) legacyMode = ESPNOW_DEFAULT_MODE;
  // Radio wanted: the stored `$C radio` choice, else on when a key is present or a legacy mode asks for it.
  radioSetEnabled(configHas("radio") ? configGetU8("radio", 1) != 0 : (legacyMode != 0 || radioHasMeshKey()));
  applyLegacyMode(legacyMode, false);
  bootPairing();
}

void loop() {
  hostlinkPoll();
  const uint32_t now = millis();
  radioTick(now, hostAliveNow());
  buttonsPoll();
  outputsPoll();

  const mesh::ArbiterOutput &o = radioOutput();
  mesh::SoundStart snd;
  const bool sndStart = radioTakeSoundStart(snd);
  const bool sndStop = radioTakeSoundStop();
  if (o.failsafe) {
    outputsSafe();  // nobody is in charge: RED and silent
  } else {
    outputsSetLightsMask(o.lights);
    if (!radioHostDrives()) {  // radio-driven roles: the master's buzzer flag and blast patterns
      outputsSetHornRaw(o.buzzer);
      if (sndStop)
        outputsStopSound();  // the master silenced the sound: stop the pattern and the raw horn at once (safe direction)
      // Replay guard (docs/mesh.md section 4): the arbiter already drops TIMER sounds older than 400 ms; the check
      // here keeps the guard in force whatever feeds the start. A stop in the same pass wins (silence is safe).
      else if (sndStart && snd.age_ms < mesh::kSoundReplayGuardMs)
        outputsStartBlasts(snd.count, snd.blast ? (uint16_t)snd.blast * 10 : DEFAULT_BLAST_MS,
                           snd.gap ? (uint16_t)snd.gap * 10 : DEFAULT_GAP_MS);
    }
  }
  if ((int32_t)(safeHoldUntil - now) > 0) outputsSafe();  // own emergency press: safe until the master confirms

  statusTick(now, o);
  // Pairing: all three lights blink so the operator sees the box waiting; otherwise the normal outputs.
  outputsSetOverrideLights(radioPairing(), ((now / 250) % 2) ? 7 : 0);
  outputsApply();
  // Fault LED: slow blink = no source (fail-safe).
  outputsFault(o.failsafe && ((now / 250) % 2));
}
