# ADS131M04 four-channel simultaneous 24-bit ADC breakout

TI ADS131M04 on a 40 x 25.4 mm board: four differential channels sampled at the same instant, 24 bits, up to 64 kSPS, over SPI. For vibration, power and sensor logging. 8.192 MHz oscillator on board. Two 0.1 inch headers 0.9 inch apart straddle a breadboard.

| What | Value |
|---|---|
| Input | +/-1.2 V differential at gain 1, to +/-9.375 mV at gain 128. Absolute limits AGND - 1.3 V to AVDD at gain 1 to 4 |
| Filter | 1 k + 1 k + 10 nF C0G per channel, corner 7.96 kHz. Change the cap to 2.2 nF C0G (LCSC C33353) for 36 kHz |
| Noise | 10.68 uVrms at 16 kSPS, gain 1; 0.42 uVrms at 250 SPS, gain 32 to 128 (Table 7-1) |
| Power | VIN 3.3 to 5 V, about 11 mA. 3V3 pin is an output, 100 mA for your circuit |
| Logic | 3.3 V only, not 5 V tolerant |
| SPI | Mode 1, to 25 MHz SCLK. At 64 kSPS with 24-bit words, 9.2 MHz minimum |

| J2 pin | Name | Function | | J1 pin | Name | Function |
|---|---|---|---|---|---|---|
| 1 | VIN | 3.3 to 5 V in | | 1 | AIN0P | Channel 0 + |
| 2 | 3V3 | 3.3 V out | | 2 | AIN0N | Channel 0 - |
| 3 | GND | Ground | | 3 | GND | Ground |
| 4 | DIN | SPI data in | | 4 | AIN1N | Channel 1 - |
| 5 | DOUT | SPI data out | | 5 | AIN1P | Channel 1 + |
| 6 | SCLK | SPI clock | | 6 | GND | Ground |
| 7 | DRDY | Data ready, active low | | 7 | AIN2P | Channel 2 + |
| 8 | CS | Chip select, active low, 10 k pull-up | | 8 | AIN2N | Channel 2 - |
| 9 | SYNC | SYNC/RESET, active low, 10 k pull-up | | 9 | GND | Ground |
| 10 | GND | Ground | | 10 | AIN3N | Channel 3 - |
| | | | | 11 | AIN3P | Channel 3 + |

J1 follows the ADC's pin order, so channels 1 and 3 read N then P. Check the silk on the back.

SPI, so no I2C address and no Qwiic. Cut JP1 to turn the power LED off. For two boards to sample together, tie SYNC together and pulse it; each board has its own oscillator, so they drift apart by up to 40 ppm between pulses.

Hardware files: `layout/ads131m04_breakout/`, fabrication package in `fab/`. Source is `ads131m04_breakout.zen` and `blocks/`; `tools/regen.sh` rebuilds everything. Bring-up steps are in `BRINGUP.md`.
