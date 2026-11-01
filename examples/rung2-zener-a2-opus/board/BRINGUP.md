# Bring-up: motor1 (single DRV8874 channel module, rev A)

Tools: bench supply with current limit, DMM, scope (10x probe), a 12 V brushed DC motor (stall <= 2 A), an MCU or a
3.3 V logic source on J3. Every step names the test point or header pin; expected values come from `checks.json`
`calcs` rows (cited in brackets).

Test points (all 1.5 mm pads, top side): **TP1** = VIN (after Q1), **TP2** = 5V, **TP3** = 3V3, **TP4** = SW (buck
switch node), **TP5** = IPROPI, **TP6** = nFAULT, **TP7** = GND, **TP8** = GND. VIN_RAW (before Q1) is J4 pin 2 (the + pad, lower one).
Control header J3 (2x5, pin 1 marked): 1 5V, 2 GND, 3 3V3, 4 ISENSE, 5 PWM, 6 DIR, 7 nSLEEP, 8 nFAULT, 9 ENC_A,
10 ENC_B. Encoder J2 (JST SH 5): 1 NC, 2 A, 3 B, 4 3V3, 5 GND.

1. **Visual.** U1 (TPS54620) and U2 (DRV8874) thermal pads soldered (X-ray or side view), Q1 pin 1 dot toward the
   board centre, D3/D4 cathode bars toward VIN, C17 + toward the bar on silk, J3 shroud key matches pin 1 mark,
   D1 green and D2 red LED cathodes as marked.
2. **Resistance, unpowered** (DMM, black on TP7): TP1 > 10 kOhm after C17 charges (a short reads < 10 Ohm),
   TP2 > 1 kOhm (feedback divider 62.3 kOhm plus U3 and loads), TP3 > 1 kOhm, J4 pin 2 to TP1 open in one direction,
   diode drop (0.5-0.7 V on diode test) from J4 pin 2 to TP1 (Q1 body diode). TP7 to TP8 < 1 Ohm.
3. **Reverse polarity.** Supply 12 V, limit 50 mA, applied reversed to J4: current < 1 mA, TP1 reads 0 V (Q1 off,
   body diode reverse biased). Remove.
4. **Power, no load.** 12 V, limit 200 mA, nSLEEP low (J3 pin 7 open: DRV8874 internal pull-down).
   Input current 10-40 mA. TP1 = 12 V minus < 0.05 V (Q1 enhanced, [p_fet]). TP2 = 4.98 V +/- 2 % [vout].
   TP3 = 3.30 V +/- 2 %. D1 (green) on [i_led_pwr_ma 2.1 mA]. D2 (red) off, TP6 = 3.3 V (nFAULT high).
5. **Buck waveform.** Scope on TP4 (ground spring to TP7): square wave 0 to 12 V at 698 kHz +/- 10 % [fsw_khz].
   TP2 AC-coupled: ripple < 50 mV p-p (calculated 6.9 mV [vout_ripple_mv]). Soft start on TP2: 0 to 5 V in about
   3.5 ms [t_ss_ms]. Repeat at 6 V and 17 V input: TP2 stays 4.9-5.1 V.
6. **5 V load.** 1.7 Ohm (3 A) on J3 pin 1 to pin 2, 12 V in: TP2 >= 4.9 V, input current about 1.4 A; U1 and L1
   below 70 degC after 2 min (thermal camera). At 6 V in the input current is about 2.8 A [i_in_6v].
7. **3.3 V load.** 6.6 Ohm (0.5 A) on J3 pin 3 to pin 2: TP3 >= 3.25 V; U3 tab < 100 degC [tj_ldo 116.5 degC at
   40 degC ambient is the worst case].
8. **Driver enable.** Motor on J1 (A = pin 1, B = pin 2). J3: nSLEEP (pin 7) = 3.3 V, DIR (pin 6) = 0,
   PWM (pin 5) = 0. TP6 stays 3.3 V. PWM 20 kHz 50 %: motor turns; DIR = 1 reverses it.
9. **Current sense.** Stall the motor (or a 5 Ohm 10 W resistor on J1 at 12 V with PWM 100 %, about 2.4 A minus
   Rds(on)): TP5 (IPROPI) and J3 pin 4 (ISENSE) read 1.245 V per A [v_sense_2a 2.49 V at 2 A]. With more than
   2.65 A demanded the driver chops and ISENSE stays <= 3.3 V [i_trip, v_sense_max]. ISENSE ripple at 20 kHz
   PWM attenuated by the 1.59 kHz filter [f_sense_hz].
10. **Fault.** Short J1 pin 1 to pin 2 briefly with PWM on: TP6 goes low, D2 (red) lights, the driver retries
    (IMODE = GND, auto retry). nFAULT sink current 1.7 mA [i_nfault_ma].
11. **Encoder.** Encoder on J2: J3 pin 9 / pin 10 toggle 0 to 3.3 V in quadrature when the shaft turns; with J2
    empty both read 3.3 V (10 kOhm pull-ups, 0.33 mA [i_enc_pullup_ma]).
