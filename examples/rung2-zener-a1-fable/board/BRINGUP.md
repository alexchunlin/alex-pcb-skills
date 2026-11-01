# Bring-up: motor channel module rev A

Tools: bench supply 6-17 V with current limit, DMM, scope, brushed DC motor, quadrature encoder on a JST SH 5-pin
cable, an MCU on the 2x5 header (PINMAP.md). Test points (all 1.5 mm pads, top): TP1 VIN (after Q1), TP2 SW, TP3 5V,
TP4 3V3, TP5 IPROPI, TP6 nFAULT, TP7 GND, TP8 GND. Connectors: J1 XT30 power in, J2 motor, J3 encoder, J4 control.

1. **Visual.** Pin-1 marks on J3 and J4, "+" at J1, U1/U2/U3 orientation, L1 seated, C1 polarity stripe toward GND.
   Do not apply 5 V to J4 pin 3 or 3.3 V to pin 1 from the MCU side while J1 is unpowered (outputs only).
2. **Resistance, unpowered.** TP1-TP7: > 10 kOhm after C1 charges (a short reads < 1 Ohm). TP3-GND > 1 kOhm.
   TP4-GND > 1 kOhm. J2 pins to GND: open (> 1 MOhm; the bridge is off).
3. **Reverse polarity.** Apply -12 V to J1 through a 100 mA current limit: current < 1 mA, TP1 reads ~0 V.
4. **Power, no load.** +12 V at J1, limit 300 mA. Expected: 20-40 mA (U1 asleep: nSLEEP pulled down), TP1 =
   VIN - 0.05 V, TP3 = 4.98 V +/- 0.1, TP4 = 3.30 V +/- 0.05, D1 green on, D2 off. Scope TP2: 480 kHz +/- 15 %
   square wave 0-12 V; TP3 AC ripple < 50 mVpp.
5. **Rails over the input range.** Repeat at 6 V and 17 V: TP3 within 4.9-5.1 V; the buck must start above 5.6 V
   and stop below 5.0 V (EN divider).
6. **5 V load.** 2 A electronic load on J4 pin 3: TP3 >= 4.90 V, U2 and L1 warm but < 60 C after 5 min.
7. **3.3 V load.** 300 mA on J4 pin 1: TP4 >= 3.25 V; U3 tab < 100 C (0.5 W).
8. **Driver enable.** MCU drives nSLEEP (J4.6) high, PWM (J4.4) low, DIR (J4.5) low: TP6 = 3.3 V (no fault),
   quiescent +4 mA. Motor on J2, PWM 20 kHz 25 % duty: motor turns; DIR high reverses it.
9. **Current sense.** With the motor stalled briefly at 1.0 A (supply reading): TP5 = 1.25 V +/- 10 %, J4.8 (ISENSE)
   the same after the 1k/100n filter; at 2.0 A, 2.49 V. ISENSE never above 3.0 V (VREF).
10. **Current limit and fault.** Short J2 briefly through a 1 Ohm resistor: the driver chops at 2.4 A (TP5 clamps at
    3.0 V), no fault. Dead short: nFAULT (TP6) goes low, D2 red lights, driver retries automatically.
11. **Encoder.** Encoder on J3 (pin 4 = 3.3 V, pin 5 = GND): spin the motor, J4.9/J4.10 show quadrature 0-3.3 V.
12. **Thermal.** 2 A continuous for 10 min at 12 V: U1 top < 85 C (expected ~80 C from 1.17 W / 36 C/W at 40 C ambient).
