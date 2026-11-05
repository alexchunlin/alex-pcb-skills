# Bring-up: ADS131M04 breakout rev A

Tools: bench supply with current limit, DMM, 100 MHz scope, a 3.3 V SPI host. Test points: TP1 GND, TP2 3V3, TP3 AVDD. Header J2: 1 VIN, 2 3V3, 3 GND, 4 DIN, 5 DOUT, 6 SCLK, 7 DRDY, 8 CS, 9 SYNC, 10 GND. Header J1: 1 AIN0P, 2 AIN0N, 3 GND, 4 AIN1N, 5 AIN1P, 6 GND, 7 AIN2P, 8 AIN2N, 9 GND, 10 AIN3N, 11 AIN3P.

Host logic is 3.3 V only: DVDD + 0.3 V is the absolute limit on CS, SCLK, DIN and SYNC (SBAS890D 6.1). Keep a 5 V host off J2 pins 4 to 9.

1. **Visual.** U1 pin 1 mark toward the west end of the south row, by the TP3 side. U2 and Y1 dots to their silk marks. D1 cathode to the south. JP1 bridged. J1 and J2 are loose headers: solder them, square pad is pin 1 on both.
2. **Rails, unpowered.** DMM from TP1 to J2.1 (VIN), TP2 and TP3. Expected above 1 kohm on each, settling upward as the bypass caps charge. Below 10 ohm is a short: stop.
3. **Power.** 5.0 V on J2.1 and J2.3, limit 30 mA. Expected input current 7 to 11.5 mA with D1 lit (U1 3.9 mA typical, Y1 up to 5 mA, D1 1.3 mA). Above 20 mA: stop and find it.
4. **Rails, powered.** TP2 3.3 V, limits 3.25 to 3.35 V (TPS7A20 tolerance 1.5 %). TP3 within 3 mV of TP2 (450 mohm ferrite at 4 mA). U1 pin 18: 1.8 V. D1 lit; cut JP1 and the input current drops 1.3 mA.
5. **Repeat at VIN = 3.3 V.** TP2 follows VIN less about 5 mV (dropout scales from 145 mV at 300 mA). The board runs; the LDO has no headroom and passes supply noise, so use 5 V for the noise figures in step 9.
6. **Clock.** Probe U1 pin 17 with a short ground lead to TP1: 8.192 MHz, 0 to 3.3 V, duty 45 to 55 %. Frequency within 8.192 MHz +/- 164 Hz (20 ppm over temperature).
7. **DRDY without any host.** Scope J2.7. Falling edges at 2 kHz: the output FIFO is full because nothing reads it, datasheet Table 9-1. Reading every frame brings it to 4 kHz, the default OSR 1024 rate.
8. **First register read.** SPI mode 1 (CPOL 0, CPHA 1), 1 MHz to start, default 24-bit words, six words per frame, CS low for the whole frame. Frame 1: command `A0 00 00` (RREG address 0, one register), then five words of zeros. Frame 2: NULL `00 00 00` and zeros. First word back in frame 2 is the ID register: **`24 xx 00`**, top byte 0x24 (bits 15:12 = 0010, CHANCNT = 0100); the low byte is reserved and may change. `A0 80 00` reads STATUS: **`05 00 00`** after reset. RESET command `00 11 00` with a full six-word frame answers `FF 24 00` in the next frame.
9. **Noise floor.** Short J1.1 to J1.2 and to J1.3 with a wire. Default gain 1, 4 kSPS: read 1 s of channel 0. Expected mean within +/- 1300 codes (offset +/- 175 uV typical, 143 nV per code), standard deviation about 37 codes (5.35 uVrms, Table 7-1). Repeat on channels 1 to 3 at J1.4/J1.5, J1.7/J1.8, J1.10/J1.11.
10. **Full-scale check.** 1.000 V from a calibrated source between J1.1 (+) and J1.2 (-), with J1.2 tied to J1.3. Expected code 6.95 million, within 0.3 %: 1.000 / 1.2 x 8388607 = 6990506, less 0.6 % for 2 kohm against 330 kohm (Equation 4), less gain error 0.1 %.
11. **Filter.** Sine 100 mVrms sweep on channel 0 at 64 kSPS (OSR 64): -3 dB at 7.96 kHz +/- 10 %, -12.4 dB at 32 kHz.
12. **Simultaneity.** Same sine into all four channels, 1 kHz: the ADC samples together, and the filters set the skew: each RC delay is 20 us, C +/-5 % and R +/-1 %, so channels agree within 2.4 us.
