# IM73D122 PDM Microphone Breakout

A 73 dB(A) SNR digital MEMS microphone on a 25.4 x 17.8 mm board, for far-field pickup. Infineon IM73D122V01: PDM output, 122 dBSPL acoustic overload, flat 20 Hz to 19 kHz, IP57 at the component. The sound port is a 0.8 mm hole through the board: sound enters from the **back**. On-board TPS7A2033 low-noise 3.3 V regulator (7 to 10 uVrms) so a noisy 5 V USB rail does not reach the mic. Two boards on one CLK and DATA make a stereo pair.

There is no I2C and no address. Data is 1-bit PDM; your host needs a PDM input (RP2040 PIO, nRF52840, ESP32-S3, STM32 with DFSDM or SAI).

## Pinout (J1, 0.1 in, left to right on the top view)

| Pin | Name | Dir | What it does |
|---|---|---|---|
| 1 | VIN | in | 3.3 to 5.5 V. Above 3.6 V the regulator has headroom and its noise rejection works |
| 2 | 3V3 | out | Regulated 3.3 V, 5 mA at most. With JP3 cut: input, 1.62 to 3.6 V direct |
| 3 | GND | | Ground |
| 4 | DATA | out | PDM data, 100 ohm series. Tri-state on the other channel's edge |
| 5 | CLK | in | PDM clock. 3.3 V logic, not 5 V tolerant. See table |
| 6 | SEL | in | L/R select. Tied low by JP2 as shipped |

| CLK | Mode | SNR | Current |
|---|---|---|---|
| 0.768 MHz | Low power | 69 dB(A) | 0.28 mA |
| 1.536 MHz | Normal | 71 dB(A) | 0.69 mA |
| 2.4 MHz | High perf | 72 dB(A) | 0.75 mA |
| 3.072 MHz | High perf | 73 dB(A) | 0.98 mA |
| 4.8 MHz | Ultrasonic | 72 dB(A) | 0.90 mA |

Clock duty 40 to 60 % up to 3 MHz, 48 to 52 % above. Clock edges 13 ns or faster.

## Jumpers

| Jumper | Shipped | Change it to |
|---|---|---|
| JP1 LED | bridged | Cut: power LED off, saves 1.3 mA |
| JP2 L/R | L (SEL low, DATA driven on the falling edge) | Cut, bridge R: SEL to 3V3, second channel, DC offset -40 instead of -80 dBFS. Cut only: drive SEL from a host |
| JP3 LDO | bridged | Cut: regulator disconnected, feed 3V3 directly at 1.62 to 3.6 V. Do this for a 1.8 V host |

**Power, one source at a time.** Shipped: VIN feeds the LDO, 3V3 is an output. With JP3 bridged never drive 3V3 from outside: the TPS7A20 must not see OUT above IN + 0.3 V. Cut JP3 first.

**Mounting.** Four M2.5 holes. Keep the back of the port open: pins down on a breadboard, the header's 2.5 mm plastic spacer is all the gap the port gets, so solder the header pins up, or expect the board to hear the breadboard. If you solder wires, do not pot or conformal-coat near the port. Use no-clean flux, do not wash, do not blow air into the hole, never ultrasonic clean.

Files: `fab/` Gerbers (`im73d122_mic_gerbers_order.zip`), JLC BOM and CPL; `BRINGUP.md`; `DESIGN_LOG.md`.
