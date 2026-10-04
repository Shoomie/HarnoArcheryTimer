// Mesh v2 node (docs/mesh.md): ESP-NOW transport, meshcore codec/arbiter, TIMER/SOUND/SESSION/HELLO transmit,
// roster, CMD gate and sender, pairing. This is the device side of firmware/lib/meshcore; main.cpp decides what
// the outputs do with `radioOutput()`, hostlink.cpp feeds the host inputs below. Single-threaded: everything runs
// from loop() except the ESP-NOW receive callback, which only fills a ring.
// Not verified on hardware (compile-only plus native tests of the pure logic).
#pragma once
#include <Arduino.h>

#include "hostmsg.h"
#include "mesh_arbiter.h"

// Receives host frame bodies ("O,M,H,...": no '$', checksum or newline); main.cpp adds the framing and writes serial.
typedef void (*HostFrameFn)(const char *body);

void radioBegin(HostFrameFn toHost);
void radioTick(uint32_t now, bool hostAlive);           // call every loop(), before reading radioOutput()
const mesh::ArbiterOutput &radioOutput();               // as of the last tick
bool radioTakeSoundStop();                              // true once per stop (count 0, new sound_seq) heard from the followed master
bool radioTakeSoundStart(mesh::SoundStart &s);          // a blast pattern the arbiter wants started (radio-driven roles)

// --- role ($R, legacy $M) ---------------------------------------------------------------------------------------
// role 'M' master, 'F' mirror, 'E' radio-fed host, 'N' none. M and F need the id and session from the host.
// `feed` = forward TIMER/SOUND/SESSION to the host as $F/$W/$Y (only meaningful for 'E').
bool radioSetRole(char role, uint32_t masterId, uint32_t session, bool feed);
char radioRole();
bool radioHostDrives();                                 // role M or F: the host owns lights and sound
void radioLegacyIdentity(uint32_t *masterId, uint32_t *session, bool bump);  // id from the MAC, session counter in NVS

// --- host input -------------------------------------------------------------------------------------------------
void radioHostLights(uint8_t mask);                     // $L, $H
void radioHostBuzz(bool on);                            // $B
void radioHostSound(uint8_t count, uint16_t blastMs, uint16_t gapMs);  // $S (0 = silence)
void radioHostTimer(const HostTimer &t, uint32_t now);  // $U
void radioHostSession(const HostSession &s);            // $J

// --- configuration ----------------------------------------------------------------------------------------------
void radioSetEnabled(bool on);                          // $C radio (also stored by main.cpp)
void radioSetChannel(uint8_t ch);                       // $C chan
void radioSetName(const char *name);                    // $C name
void radioSetCaps(bool lights, bool sound, bool buttons);  // what HELLO advertises
bool radioSetMeshKey(const uint8_t key[16]);            // $C mkey: stores and resets the radio network state
bool radioEnsureMeshKey();                              // creates a random mesh key if none exists (first leader)
const char *radioName();
uint8_t radioChannel();
bool radioEnabled();
bool radioActive();                                     // ESP-NOW is up
bool radioHasMeshKey();
uint8_t radioPeers();                                   // roster size, 0..99
uint32_t radioStatusMasterId();                         // master followed, or own id for M/F

// --- pairing, master side ($P) ----------------------------------------------------------------------------------
bool radioPairOpen(uint8_t seconds);
void radioPairClose();
bool radioPairAccept(const uint8_t mac[6], uint8_t mask);
bool radioPairReject(const uint8_t mac[6]);
bool radioPairDelete(const uint8_t mac[6]);
bool radioHostAck(const uint8_t mac[6], uint32_t counter, uint8_t result);

// --- remote side ------------------------------------------------------------------------------------------------
bool radioHasRemoteKey();
bool radioRemoteSend(uint8_t action);                   // button / $P,tx: false when this node cannot send CMD
void radioEnterPairing(bool force);                     // boot hold of buttons 1+2, or no key: PAIR_REQ mode
bool radioPairing();
void radioPairPress();                                  // a physical press: arms PAIR_REQ
