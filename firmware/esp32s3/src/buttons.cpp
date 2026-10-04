#include "buttons.h"

// Button inputs, wired between the pin and GND (internal pull-up). -1 = unused.
#ifndef PIN_BTN1
#define PIN_BTN1 9
#endif
#ifndef PIN_BTN2
#define PIN_BTN2 10
#endif
#ifndef PIN_BTN3
#define PIN_BTN3 11
#endif
#ifndef PIN_BTN4
#define PIN_BTN4 12
#endif

static const int BTN_PINS[] = {PIN_BTN1, PIN_BTN2, PIN_BTN3, PIN_BTN4};
static const int NUM_BTN = sizeof(BTN_PINS) / sizeof(BTN_PINS[0]);
static const uint32_t DEBOUNCE_MS = 20;
static bool btnState[NUM_BTN];  // debounced: true = pressed
static bool btnRaw[NUM_BTN];
static uint32_t btnChangedMs[NUM_BTN];
static ButtonEdgeFn edgeFn = nullptr;

void buttonsBegin(ButtonEdgeFn onEdge) {
  edgeFn = onEdge;
  for (int i = 0; i < NUM_BTN; ++i)
    if (BTN_PINS[i] >= 0) pinMode(BTN_PINS[i], INPUT_PULLUP);
}

void buttonsPoll() {
  uint32_t now = millis();
  for (int i = 0; i < NUM_BTN; ++i) {
    if (BTN_PINS[i] < 0) continue;
    bool raw = digitalRead(BTN_PINS[i]) == LOW;
    if (raw != btnRaw[i]) {
      btnRaw[i] = raw;
      btnChangedMs[i] = now;
    } else if (raw != btnState[i] && now - btnChangedMs[i] >= DEBOUNCE_MS) {
      btnState[i] = raw;
      if (edgeFn) edgeFn(i + 1, raw);
    }
  }
}

bool buttonsHeld(uint8_t id) {
  if (id < 1 || id > NUM_BTN || BTN_PINS[id - 1] < 0) return false;
  return digitalRead(BTN_PINS[id - 1]) == LOW;
}
