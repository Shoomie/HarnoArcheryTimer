#include "beep.h"

#include <esp32-hal-ledc.h>

static const uint8_t RES_BITS = 8;
static const uint8_t LEDC_CH = 0;  // used by core 2.x only; 3.x picks the channel from the pin

static int beepPin = -1;
static uint16_t curHz = 0;
static const Note *seq = nullptr;
static size_t seqLen = 0, seqPos = 0;
static uint32_t seqNextMs = 0;

static void hwTone(uint16_t hz, uint8_t duty) {
  if (beepPin < 0) return;
  if (hz == 0 || duty == 0) {
    if (curHz) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
      ledcWrite(beepPin, 0);
#else
      ledcWrite(LEDC_CH, 0);
#endif
    }
    curHz = 0;
    return;
  }
  uint32_t level = ((1u << RES_BITS) - 1) * (duty > 50 ? 50 : duty) / 100;  // above 50 % is quieter
  if (hz != curHz) {
#if ESP_ARDUINO_VERSION_MAJOR >= 3
    ledcChangeFrequency(beepPin, hz, RES_BITS);
#else
    ledcWriteTone(LEDC_CH, hz);
#endif
    curHz = hz;
  }
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcWrite(beepPin, level);
#else
  ledcWrite(LEDC_CH, level);
#endif
}

void beepBegin(int pin) {
  beepPin = pin;
  if (pin < 0) return;
#if ESP_ARDUINO_VERSION_MAJOR >= 3
  ledcAttach(pin, 2000, RES_BITS);
  ledcWrite(pin, 0);
#else
  ledcSetup(LEDC_CH, 2000, RES_BITS);
  ledcAttachPin(pin, LEDC_CH);
  ledcWrite(LEDC_CH, 0);
#endif
}

void beepTone(uint16_t hz, uint8_t dutyPercent) {
  seq = nullptr;  // direct control wins over a melody
  hwTone(hz, dutyPercent);
}

void beepOff() {
  seq = nullptr;
  hwTone(0, 0);
}

static void startNote() {
  const Note &n = seq[seqPos];
  hwTone(n.hz, 50);
  seqNextMs = millis() + n.ms;
}

void beepPlay(const Note *notes, size_t count) {
  if (beepPin < 0 || !notes || count == 0) return;
  seq = notes;
  seqLen = count;
  seqPos = 0;
  startNote();
}

void beepPoll() {
  if (!seq || (int32_t)(millis() - seqNextMs) < 0) return;
  if (++seqPos >= seqLen) {
    beepOff();
    return;
  }
  startNote();
}

bool beepSequenceActive() { return seq != nullptr; }
