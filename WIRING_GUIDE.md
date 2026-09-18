# Wiring & Circuit Guide

## Hardware: Arduino Uno + INA219 + DHT11 + LDR

---

## Pin Connections

### INA219 Current/Voltage/Power Sensor (I2C)

| INA219 Pin | Arduino Pin | Notes |
|:---|:---|:---|
| VCC | 5V | Sensor logic power |
| GND | GND | Common ground |
| SDA | A4 | I2C data line |
| SCL | A5 | I2C clock line |
| VIN+ | Solar Panel (+) terminal | High-side power measurement input |
| VIN- | Load positive terminal | Load supply (connect a small resistor or LED as test load) |

### DHT11 Temperature & Humidity Sensor

| DHT11 Pin | Arduino Pin | Notes |
|:---|:---|:---|
| VCC (Pin 1) | 5V | Sensor power |
| DATA (Pin 2) | D2 | Digital data line (firmware uses bit-bang, no library needed) |
| NC (Pin 3) | — | Not connected |
| GND (Pin 4) | GND | Common ground |

A 10kΩ pull-up resistor between DATA and VCC is recommended but optional
(the firmware's internal pull-up usually works for short wire runs).

### LDR Light Intensity Sensor (Voltage Divider)

```
    5V ──── [ LDR ] ──┬── Arduino A0
                       │
                   [ 10kΩ ]
                       │
                      GND
```

The analog voltage at A0 ranges from 0 (dark) to ~1023 (bright sunlight).

---

## Circuit Schematic

```
  ┌──────────────────────────────────────────────────────────┐
  │                    ARDUINO UNO R3                         │
  │                                                          │
  │   A0 ←── LDR voltage divider junction                    │
  │   A4 (SDA) ←→ INA219 SDA                                │
  │   A5 (SCL) ←→ INA219 SCL                                │
  │   D2 ←── DHT11 DATA pin                                 │
  │                                                          │
  │   USB ←═══════════════════════════→ PC (Python/Streamlit)│
  │         (115200 baud, JSON packets)                      │
  └──────────────────────────────────────────────────────────┘

  Solar Panel (+) ──→ INA219 VIN+ ──→ INA219 VIN- ──→ Load ──→ GND
                      (measurement point)
```

---

## Bill of Materials

| Part | Approx Price (INR) |
|:---|:---|
| Arduino Uno R3 (CH340) | ₹350-450 |
| INA219 I2C Sensor Module | ₹140-200 |
| DHT11 Temperature/Humidity Sensor | ₹40-60 |
| LDR 5mm Photoresistor | ₹5 |
| 10kΩ Resistor (1/4W) | ₹2 |
| 5V/1W Mini Solar Panel | ₹120-180 |
| 400-pt Breadboard | ₹70-100 |
| Jumper Wires (M-M, M-F) | ₹50-80 |
| USB Type-B Cable | ₹30 |
| **Total** | **~₹800-1,100** |

If reusing parts from a previous project, the only new purchase
needed is the DHT11 sensor (~₹50).
