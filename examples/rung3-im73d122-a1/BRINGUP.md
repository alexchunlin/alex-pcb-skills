# Bring-up: IM73D122 PDM microphone breakout rev A

Tools: DMM, 5 V bench supply with a 20 mA limit, loupe, a host with a PDM input (RP2040 PIO, nRF52840 PDM, ESP32-S3 I2S-PDM) or a 3.3 V logic analyser.
Refdes on silk: J1 on top; U1, U2, D1, JP1 to JP3, TP1, TP2 in the legend on the back. TP1 = 3V3, TP2 = GND. J1: 1 VIN, 2 3V3, 3 GND, 4 DATA, 5 CLK, 6 SEL.
Do not wash this board, ever. Do not blow air at the port. Do not run ultrasonic cleaning (datasheet section 7).

1. **Visual, port first.** From the back, look into the 0.8 mm port under a loupe with a light. Expected: the hole is open and round, with the grey of the mic's own port visible behind it, no flux film, no solder bead, no mask skin. Record pass or fail per board. Any residue here is the wash and flux open question in `SUMMARY.md`; a blocked board fails step 9.
2. **Visual, rest.** U1 pin 1 dot lower left on the top view (next to the silk dot). U2 pin 1 mark top left. JP1, JP3 bridged. JP2 bridged on the L side. J1 loose. D1 cathode to the GND end.
3. **Header.** Cover the port on the back with polyimide tape before soldering J1. No-clean flux only. Peel the tape. Repeat step 1.
4. **Rail resistance, unpowered.** TP1 to TP2: expected above 100 kOhm (the only DC path is D1, off at DMM voltage, and U1, whose VDD pin charges as caps do). A reading under 100 Ohm is a short. J1.1 to TP2: same.
5. **Strap.** J1.6 to TP2: under 1 Ohm with JP2 shipped (L).
6. **First power.** 5.0 V on J1.1, 20 mA limit, CLK not driven. Expected: 1.3 mA +/- 0.5 (D1 lit; U1 with CLK floating is not specified, up to 50 uA), TP1 3.30 V +/- 0.05 (TPS7A20 1.5 % tolerance, 3.25 to 3.35 V), D1 on.
7. **Clock.** 3.072 MHz, 48 to 52 % duty (Table 5, above 3 MHz) on J1.5, 3.3 V logic. Add 1.0 mA typ, 1.12 mA max (Fig 8, Table 6). Total at the supply 2.3 mA +/- 0.5. Expected: scope on J1.4 shows data within 20 ms of the clock start (Table 6 startup), idle tone (alternating 1s and 0s) in the first 3 ms.
8. **First read: this part has no registers.** The equivalent of a WHO_AM_I read is a PDM capture. Sample DATA on the rising CLK edge (SEL low: U1 drives on the falling edge, Table 8). Decimate by 64 to 48 kHz. In a quiet room expect a mean bit density of 0.5 within 0.01 (DC offset -80 dBFS, Table 7, SEL low) and RMS noise near -99 dBFS(A) from the -26 dBFS sensitivity and 73 dB(A) SNR. Stuck high or low means no clock at U1 or a bad U1 joint.
9. **Function.** 1 kHz at 94 dBSPL (calibrator with a 3 mm adapter on the back over the port): -26 dBFS +/- 1 dB (Table 3). Read more than 3 dB low means the port is partly blocked. Compare the 10 kHz level against 1 kHz as well: a partly blocked port loses highs first.
10. **Second channel.** Cut JP2 L link, bridge R. Same capture on the other clock edge. DC offset moves to -40 dBFS (Table 7). Expect the 1 kHz level unchanged within 0.5 dB.
11. **Cut jumpers.** Cut JP1: D1 off, supply current falls by 1.3 mA. To feed 3V3 directly, cut JP3 first, leave VIN open, feed J1.2 with 1.62 to 3.6 V. Logic on CLK must match that voltage.
