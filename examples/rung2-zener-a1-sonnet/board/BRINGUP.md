# Bring-up: rung2_motor (single brushed-DC channel)

Silk references: J4 power in (screw terminal, VIN+ left pad, GND below), J1 motor (MOT A top, MOT B bottom), J2 encoder
(JST, silk N A B + G along the pins), J3 control header (pin map in PINMAP.md), Q1 reverse-polarity MOSFET, U1 buck,
U2 DRV8874, U3 LDO. Expected readings come from the `calcs` rows in checks.json and the datasheets in docs/.

## Test points
| TP | Net | Where |
|---|---|---|
| TP1 | VIN (after Q1) | top left, above J4 |
| TP2 | 5V | top right, above the inductor |
| TP3 | 3V3 | LDO tab, right of U3 |
| TP4 | SW (buck switch node) | top, above U1 |
| TP5 | IPROPI (before the 1k/100 nF filter) | bottom centre |
| TP6 | nFAULT | bottom right |
| TP7 | GND | bottom left |
| TP8 | GND | bottom left, next to TP7 |

## Steps (bench supply with current limit, DMM on TP7, scope on TP4)
1. Unpowered: J4 pin 2 to TP7 below 1 ohm; VIN (TP1) to TP7 above 1 kohm (no short); 5V (TP2) to TP7 above 1 kohm.
2. Reverse polarity: supply set to 12 V, limit 100 mA, connected backwards (+ on GND pad). Expected: TP1 about 0 V
   (below 0.1 V), supply current below 1 mA (Q1 body diode blocks, gate sits at the board GND which is the supply +).
3. Correct polarity, 12 V, limit 300 mA, motor and encoder unplugged, nSLEEP low. Expected: TP1 11.9 to 12.0 V;
   green power LED lit; TP2 4.90 to 5.10 V (calc: 4.984 V nominal); TP3 3.25 to 3.35 V; supply current below 100 mA.
4. Buck: scope on TP4. Expected: 12 V amplitude square wave, 480 kHz (period 2.08 us), duty about 42 percent
   (5/12) at light load; ripple on TP2 below 50 mV peak to peak (calc 16 mV).
5. Soft start: power-cycle with the scope on TP2: rise time about 3.5 ms (10 nF soft-start capacitor, 2.3 uA, 0.8 V).
6. Sweep VIN 6 V to 17 V: TP2 stays 4.90 to 5.10 V, TP3 stays 3.25 to 3.35 V. Below about 4.5 V the buck stops.
7. Control header with a multimeter on J3: pin 1 3.3 V, pin 4 5 V, pin 2 GND. TP6 3.3 V (pull-up), red fault LED off.
8. Drive: connect a motor to J1, nSLEEP high, DIR low, PWM 20 kHz 50 percent at 12 V. Expected: motor turns;
   J3 pin 6 (ISENSE) at DC equals TP5 within 1 percent and reads 1.25 V per amp (2 A reads 2.49 V,
   calc: 2 A x 455 uA/A x 2.74 k); direction flips with DIR.
9. Current limit: stall the motor. Expected: TP5 and ISENSE rise to at most 3.3 V (VREF clamp, ITRIP calc 2.65 A),
   nFAULT may pulse low and the red fault LED flickers; ISENSE never exceeds 3.3 V.
10. Thermal: 2 A for 10 minutes. Expected U2 case about 70 degC or less in 25 degC room (calc Tj 68 degC at 40 degC
    ambient; 0.8 W); U3 case below 100 degC with 500 mA on 3V3 (calc Tj 116 degC worst case at 40 degC ambient).
11. Encoder: plug a 3.3 V encoder into J2: J2 pin 4 3.3 V, pin 5 GND; a 3.3 V edge on J2 pin 2 appears on J3 pin 8
    (through 1 kohm), same for pin 3 and J3 pin 10.
12. 4 A input budget: at 6 V in, 3 A on 5V plus the motor leaves 1.2 A for the motor (calc motor_a_max_at_6v).
