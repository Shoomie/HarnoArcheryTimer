// Persistent settings in NVS (namespace "archery"). Writes only on change (flash wear).
// Keys (max 15 chars): name, lights, sound, radio, remote, chan, btn1..btn4 ($C), mkey (mesh key, 16 B),
// rkey (own remote key, 16 B), rt0..rt7 (paired remotes), s0..s7 + sidx (highest accepted session per master),
// cnt (CMD counter high-water mark), lcnt (legacy session counter), espnow (legacy $M mode).
#pragma once
#include <Arduino.h>

void configBegin();
uint8_t configGetU8(const char *key, uint8_t def);
void configPutU8(const char *key, uint8_t value);  // no-op when unchanged
uint32_t configGetU32(const char *key, uint32_t def);
void configPutU32(const char *key, uint32_t value);  // no-op when unchanged
bool configGetBlob(const char *key, void *out, size_t len);  // true only when exactly `len` bytes are stored
void configPutBlob(const char *key, const void *data, size_t len);  // no-op when unchanged
bool configGetStr(const char *key, char *out, size_t cap);  // false when unset
void configPutStr(const char *key, const char *value);      // no-op when unchanged
bool configHas(const char *key);
void configRemove(const char *key);
