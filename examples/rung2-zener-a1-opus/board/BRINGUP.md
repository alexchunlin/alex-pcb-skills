# Bring-up: motor channel module (rev A)

Tools: bench supply 6-17 V with current limit, DMM, scope (10x probe), a 12 V brushed motor (< 2 A stall) and an
MCU board on J3. Test points (1.5 mm pads, refdes on silk): TP1 = VIN, TP2 = 5V, TP3 = 3V3, TP4 = SW node,
TP5 = IPROPI, TP6 = nFAULT, TP7 = GND, TP8 = GND. Header J3 pins as in PINMAP.md.

1. **Visual.** J4 "+" pin 1 (VIN) on the left of the power terminal, J1 motor terminal, J3 pin 1 mark, J2 orientation.
   U2 exposed pad soldered (X-ray or check the bottom vias show solder wicking). C10 is on the bottom side under U2.
2. **Rail resistance, unpowered** (DMM, black on TP7): TP1 VIN > 10 kOhm (C17 charging up; < 10 Ohm = short);
   TP2 5V > 1 kOhm (R4+R5 = 63.6 kOhm in parallel with loads); TP3 3V3 > 1 kOhm; TP4 SW > 1 kOhm.
3. **Reverse polarity** (current limit 100 mA): apply -12 V on J4. Expected supply current < 1 mA, TP1 ~ 0 V.
   Q1 body diode is reversed and VGS ~ 0 V.
4. **Power** (limit 200 mA, 12 V on J4, J3 unconnected, no motor): supply current about 15-30 mA.
   TP1 = 11.95-12.0 V (Q1 drop 4 A x 14 mOhm = 56 mV at full load, calcs p_fet_4a_w);
   TP2 = 5.09 V +/- 2 % (calcs vout_5v 5.088 V); TP3 = 3.30 V +/- 2 %; green D1 on, red D3 off; TP6 nFAULT = 3.3 V.
5. **UVLO.** Ramp the supply from 0 V: the buck starts at TP1 = 5.2 V (calcs v_uvlo_start 5.193 V) and stops at 4.7 V
   falling (v_uvlo_stop 4.671 V).
6. **Switch node.** Scope TP4 with the probe ground spring on TP8: 1.53 MHz (calcs f_sw_khz 1529), duty 42 % at 12 V.
   5V ripple at TP2 with a 1 A load: < 20 mV p-p (calcs vout_ripple_mv 7.1 mV at 3 A, 17 V).
7. **Header outputs.** J3.1 (5V_HDR) = 4.7-4.8 V at no load (B5819W drop), J3.3 = 3.3 V, J3.8 nFAULT = 3.3 V.
8. **Driver idle.** nSLEEP (J3.7) low: VIN current falls back to the step-4 value; nFAULT high.
   nSLEEP high, PWM low: TP5 IPROPI = 0 V.
9. **Motor.** Motor on J1, nSLEEP high, DIR high, PWM 20 kHz 50 %: motor turns; DIR low reverses it.
   TP5 / J3.4 ISENSE = 1.247 V per A of motor current (calcs v_sense_2a 2.493 V at 2 A).
   Stall the motor: current regulation holds the peak at 2.41 A (calcs i_trip_a 2.406 A) and ISENSE stays <= 3.0 V
   (v_ipropi_max); U2 case < 80 degC after 30 s (thermal pad: 6 vias, row thermal_vias:U2).
10. **Fault.** Short J1 pins through a 0.1 Ohm resistor briefly with PWM on: nFAULT (TP6) goes low, D3 lights,
    the driver retries automatically (IMODE 20 kOhm, R15).
