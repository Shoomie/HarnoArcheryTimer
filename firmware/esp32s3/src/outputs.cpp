#include "outputs.h"

#include "beep.h"

// Pins: adjust to your rig, or override per board with -DPIN_GREEN=n etc. in platformio.ini.
// Light and horn outputs are active HIGH. FAULT_ACTIVE_LOW=1 for boards whose LED sinks.
#ifndef PIN_GREEN
#define PIN_GREEN 4
#endif
#ifndef PIN_YELLOW
#define PIN_YELLOW 5
#endif
#ifndef PIN_RED
#define PIN_RED 6
#endif
#ifndef PIN_HORN
#define PIN_HORN 7
#endif
#ifndef PIN_FAULT
#define PIN_FAULT 8
#endif
// PWM beeper (piezo, or a speaker behind a transistor). -1 = none. It sounds whenever the
// horn output is on (whistle blasts, $B buzzer, ESP-NOW sound) at BEEP_HZ.
#ifndef PIN_BEEP
#define PIN_BEEP -1
#endif
#ifndef BEEP_HZ
#define BEEP_HZ 2700  // typical piezo resonance; any 200..8000 works on a speaker
#endif
// 1 = play CHIME_BOOT once at power-up (confirms the beeper wiring). Off by default.
#ifndef BOOT_CHIME
#define BOOT_CHIME 0
#endif
#ifndef FAULT_ACTIVE_LOW
#define FAULT_ACTIVE_LOW 0
#endif

// Short rising two-note chime; copy this pattern to add more melodies.
static const Note CHIME_BOOT[] = {{1800, 90}, {0, 40}, {2700, 140}};

static bool lightG = false, lightY = false, lightR = true;
static bool hornRaw = false;
static int blastsLeft = 0;  // MCU-timed whistle pattern
static bool blastOn = false;
static uint32_t blastNextMs = 0;
static uint16_t blastMsCur = DEFAULT_BLAST_MS, gapMsCur = DEFAULT_GAP_MS;
static bool lightsEnabled = true, soundEnabled = true;
static bool overrideOn = false;
static uint8_t overrideMask = 0;

void outputsBegin() {
  pinMode(PIN_GREEN, OUTPUT);
  pinMode(PIN_YELLOW, OUTPUT);
  pinMode(PIN_RED, OUTPUT);
  pinMode(PIN_HORN, OUTPUT);
  pinMode(PIN_FAULT, OUTPUT);
  beepBegin(PIN_BEEP);
  outputsSafe();
  outputsApply();
#if BOOT_CHIME
  beepPlay(CHIME_BOOT, sizeof CHIME_BOOT / sizeof CHIME_BOOT[0]);
#endif
  outputsFault(false);
}

uint8_t outputsLightsMask() { return (lightG ? 1 : 0) | (lightY ? 2 : 0) | (lightR ? 4 : 0); }
void outputsSetLightsMask(uint8_t m) { lightG = m & 1; lightY = m & 2; lightR = m & 4; }
bool outputsHornRaw() { return hornRaw; }
void outputsSetHornRaw(bool on) { hornRaw = on; }

void outputsStopSound() {
  blastsLeft = 0;
  blastOn = false;
  hornRaw = false;
}

void outputsStartBlasts(int n, uint16_t blastMs, uint16_t gapMs) {
  if (n <= 0) { outputsStopSound(); return; }
  blastsLeft = n;  // restarts any pattern in progress
  blastMsCur = blastMs;
  gapMsCur = gapMs;
  blastOn = true;
  blastNextMs = millis() + blastMsCur;
}

void outputsSafe() {
  lightG = lightY = false;
  lightR = true;
  outputsStopSound();
}

void outputsSetEnabled(bool lights, bool sound) {
  lightsEnabled = lights;
  soundEnabled = sound;
}

void outputsSetOverrideLights(bool on, uint8_t mask) {
  overrideOn = on;
  overrideMask = mask;
}

bool outputsSoundActive() { return hornRaw || blastOn || blastsLeft > 0; }

void outputsApply() {
  const bool g = overrideOn ? (overrideMask & 1) : (lightsEnabled && lightG);
  const bool y = overrideOn ? (overrideMask & 2) : (lightsEnabled && lightY);
  const bool r = overrideOn ? (overrideMask & 4) : (lightsEnabled && lightR);
  digitalWrite(PIN_GREEN, g);
  digitalWrite(PIN_YELLOW, y);
  digitalWrite(PIN_RED, r);
  bool horn = soundEnabled && (hornRaw || blastOn);
  digitalWrite(PIN_HORN, horn);
  if (!beepSequenceActive()) {
    if (horn) beepTone(BEEP_HZ);
    else beepOff();
  }
}

void outputsFault(bool on) { digitalWrite(PIN_FAULT, on != (FAULT_ACTIVE_LOW != 0)); }

void outputsPoll() {
  beepPoll();
  if (blastsLeft <= 0) return;
  uint32_t now = millis();
  if ((int32_t)(now - blastNextMs) < 0) return;
  if (blastOn) {
    blastOn = false;
    if (--blastsLeft > 0) blastNextMs = now + gapMsCur;
  } else {
    blastOn = true;
    blastNextMs = now + blastMsCur;
  }
}
