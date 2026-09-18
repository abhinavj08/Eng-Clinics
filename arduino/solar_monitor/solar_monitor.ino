/*
 * Solar Panel Monitor — Data Acquisition Firmware
 * Reads PV electrical parameters (INA219), ambient conditions (DHT11, LDR)
 * and streams JSON telemetry over USB serial for the Python ML pipeline.
 *
 * Hardware: Arduino Uno R3 / Nano / Mega
 * Sensors:  INA219 (I2C), DHT11 (D2), LDR + 10k divider (A0)
 * Baud:     115200
 */

#include <Wire.h>
#include <Adafruit_INA219.h>

// ── DHT11 minimal bit-bang driver (no external library needed) ──────────
#define DHT_PIN 2
#define DHT_OK       0
#define DHT_CHECKSUM 1
#define DHT_TIMEOUT  2

struct DhtReading {
  float temp_c;
  float humidity;
  uint8_t status;
};

DhtReading readDHT11() {
  DhtReading r = {0, 0, DHT_TIMEOUT};
  uint8_t bits[5] = {0};

  // Send start signal
  pinMode(DHT_PIN, OUTPUT);
  digitalWrite(DHT_PIN, LOW);
  delay(20);
  digitalWrite(DHT_PIN, HIGH);
  delayMicroseconds(30);
  pinMode(DHT_PIN, INPUT);

  // Wait for sensor response
  unsigned long t0 = micros();
  while (digitalRead(DHT_PIN) == HIGH) {
    if (micros() - t0 > 100) return r;
  }
  t0 = micros();
  while (digitalRead(DHT_PIN) == LOW) {
    if (micros() - t0 > 100) return r;
  }
  t0 = micros();
  while (digitalRead(DHT_PIN) == HIGH) {
    if (micros() - t0 > 100) return r;
  }

  // Read 40 data bits
  for (int i = 0; i < 40; i++) {
    t0 = micros();
    while (digitalRead(DHT_PIN) == LOW) {
      if (micros() - t0 > 80) return r;
    }
    unsigned long pulse_start = micros();
    t0 = micros();
    while (digitalRead(DHT_PIN) == HIGH) {
      if (micros() - t0 > 80) return r;
    }
    unsigned long pulse_len = micros() - pulse_start;
    bits[i / 8] <<= 1;
    if (pulse_len > 40) bits[i / 8] |= 1;
  }

  // Verify checksum
  uint8_t checksum = bits[0] + bits[1] + bits[2] + bits[3];
  if ((checksum & 0xFF) != bits[4]) {
    r.status = DHT_CHECKSUM;
    return r;
  }

  r.humidity = (float)bits[0] + (float)bits[1] * 0.1;
  r.temp_c   = (float)bits[2] + (float)bits[3] * 0.1;
  r.status   = DHT_OK;
  return r;
}

// ── Sensor objects ──────────────────────────────────────────────────────
Adafruit_INA219 ina219;
bool ina_ok = false;

const uint8_t PIN_LDR = A0;

// Filtered sensor state
float pv_v = 0, pv_i = 0, pv_p = 0;
float temp_c = 25.0, humidity = 50.0;
int   light_adc = 500;

// EMA smoothing
const float A = 0.3;
float fv = 0, fi = 0, fp = 0, fl = 500.0;

// Timing
unsigned long t_sample = 0;
unsigned long t_dht    = 0;
const unsigned long DT_SAMPLE = 2000;  // 2-second main telemetry cycle
const unsigned long DT_DHT    = 3000;  // DHT11 needs >=2s between reads

String rx_buf = "";

void setup() {
  Serial.begin(115200);
  rx_buf.reserve(48);

  Wire.begin();
  if (ina219.begin()) {
    ina_ok = true;
    ina219.setCalibration_32V_2A();
  }

  pinMode(PIN_LDR, INPUT);
  delay(300);
  Serial.println(F("{\"status\":\"INIT_OK\",\"fw\":\"solar_monitor_v1.0\"}"));
}

void loop() {
  // Handle incoming commands
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (rx_buf.length() > 0) {
        // Echo ACK for host sync
        Serial.print(F("{\"ack\":\""));
        Serial.print(rx_buf);
        Serial.println(F("\"}"));
        rx_buf = "";
      }
    } else if (rx_buf.length() < 40) {
      rx_buf += c;
    }
  }

  unsigned long now = millis();

  // Read DHT11 (slow sensor, separate timer)
  if (now - t_dht >= DT_DHT) {
    t_dht = now;
    DhtReading d = readDHT11();
    if (d.status == DHT_OK) {
      temp_c   = d.temp_c;
      humidity = d.humidity;
    }
  }

  // Main sample + transmit cycle
  if (now - t_sample >= DT_SAMPLE) {
    t_sample = now;

    // Read LDR
    int raw_ldr = analogRead(PIN_LDR);
    fl = (A * raw_ldr) + ((1.0 - A) * fl);
    light_adc = (int)fl;

    // Read INA219
    if (ina_ok) {
      float bus = ina219.getBusVoltage_V();
      float shunt_mv = ina219.getShuntVoltage_mV();
      float v = bus + (shunt_mv / 1000.0);
      float i = ina219.getCurrent_mA();
      float p = ina219.getPower_mW();
      if (i < 0) i = 0;
      if (p < 0) p = 0;

      fv = (A * v) + ((1.0 - A) * fv);
      fi = (A * i) + ((1.0 - A) * fi);
      fp = (A * p) + ((1.0 - A) * fp);
    } else {
      // Estimation fallback when INA219 not populated
      fv = (light_adc / 1023.0) * 5.5;
      fi = (light_adc / 1023.0) * 260.0;
      fp = fv * fi;
    }

    pv_v = fv;
    pv_i = fi;
    pv_p = fp;

    // Derived: power-to-light ratio (mW per ADC unit of light)
    float pl_ratio = (light_adc > 10) ? (pv_p / light_adc) : 0.0;

    // Transmit JSON
    Serial.print(F("{\"ts\":"));
    Serial.print(now);
    Serial.print(F(",\"v\":"));
    Serial.print(pv_v, 2);
    Serial.print(F(",\"i\":"));
    Serial.print(pv_i, 1);
    Serial.print(F(",\"p\":"));
    Serial.print(pv_p, 1);
    Serial.print(F(",\"t\":"));
    Serial.print(temp_c, 1);
    Serial.print(F(",\"h\":"));
    Serial.print(humidity, 1);
    Serial.print(F(",\"l\":"));
    Serial.print(light_adc);
    Serial.print(F(",\"plr\":"));
    Serial.print(pl_ratio, 3);
    Serial.print(F(",\"ina\":"));
    Serial.print(ina_ok ? F("true") : F("false"));
    Serial.println(F("}"));
  }
}
