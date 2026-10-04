#include "config.h"

#include <Preferences.h>

static Preferences prefs;

void configBegin() { prefs.begin("archery", false); }

uint8_t configGetU8(const char *key, uint8_t def) { return prefs.getUChar(key, def); }

void configPutU8(const char *key, uint8_t value) {
  if (prefs.getUChar(key, (uint8_t)(value + 1)) != value) prefs.putUChar(key, value);
}

uint32_t configGetU32(const char *key, uint32_t def) { return prefs.getUInt(key, def); }

void configPutU32(const char *key, uint32_t value) {
  if (prefs.getUInt(key, value + 1) != value) prefs.putUInt(key, value);
}

bool configGetBlob(const char *key, void *out, size_t len) {
  if (prefs.getBytesLength(key) != len) return false;
  return prefs.getBytes(key, out, len) == len;
}

void configPutBlob(const char *key, const void *data, size_t len) {
  if (prefs.getBytesLength(key) == len) {
    uint8_t cur[64];
    if (len <= sizeof cur && prefs.getBytes(key, cur, len) == len && memcmp(cur, data, len) == 0) return;
  }
  prefs.putBytes(key, data, len);
}

bool configGetStr(const char *key, char *out, size_t cap) {
  if (!prefs.isKey(key)) return false;
  return prefs.getString(key, out, cap) > 0;
}

void configPutStr(const char *key, const char *value) {
  char cur[32];
  if (configGetStr(key, cur, sizeof cur) && strcmp(cur, value) == 0) return;
  prefs.putString(key, value);
}

bool configHas(const char *key) { return prefs.isKey(key); }

void configRemove(const char *key) { prefs.remove(key); }
