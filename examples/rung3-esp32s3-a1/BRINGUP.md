# Bring-up: ESP32-S3 devkit rev A

Refs are printed on the bottom silk. Do these in order; stop at the first wrong reading. Bench supply current-limited unless a step says USB.

## 1. Before power
| Step | Where | Expect |
|---|---|---|
| 1.1 | Look at U1 under a loupe. J5 orientation: terminal 4 at the south inner land. U2 tab soldered. | No bridges on the 0.4 mm pins |
| 1.2 | Ohms TP2 (3V3) to TP3 (GND) | above 1 k after settling, not a short |
| 1.3 | Ohms TP1 (5V) to TP3 | above 1 k |
| 1.4 | Ohms TP4 (VBUS) to TP3 | above 1 k |

## 2. First power, bench 5 V at 100 mA limit on TP1, GND on TP3
| Step | Measure | Expect |
|---|---|---|
| 2.1 | Supply current | 30 to 90 mA once booted, blank flash loops in ROM |
| 2.2 | TP2 | 3.267 to 3.333 V (1 %) |
| 2.3 | C13 pad 1 (VDD_SPI) | about 3.3 V less the RSPI drop, above 3.0 V (HDG 1.3.2) |
| 2.4 | C7 pad 1 (VDD3P3) | same as TP2 within 20 mV |
| 2.5 | LED1 | on, about 1.3 mA. Cut JP1 to disable |
| 2.6 | U2 tab temperature after 1 min | near ambient |

## 3. USB
| Step | Action | Expect |
|---|---|---|
| 3.1 | Plug USB-C. TP4 | 4.75 to 5.25 V |
| 3.2 | TP1 | TP4 less 0.2 to 0.5 V, the D1 drop |
| 3.3 | Hold SW2 (BOOT), tap SW1 (RST), release SW2 | Host shows a USB JTAG/serial device, VID 303A PID 1001 |

## 4. First register read
```
esptool.py --port <port> chip_id
esptool.py --port <port> read_mem 0x40001000
esptool.py --port <port> flash_id
```
Expected: `Chip is ESP32-S3`, features line lists embedded flash 4 MB and embedded PSRAM 2 MB, `read_mem` returns `0x00000009`, the ESP32-S3 chip-detect value, and `flash_id` reports 4 MB. Then flash a blink on GPIO9: LED2 follows, about 1.2 mA.

## 5. Peripherals
- I2C: with JP2 bridged, GPIO17 and GPIO18 idle at 3.3 V through 10 k. Plug a Qwiic device into J4, run an I2C scan on SDA 17, SCL 18.
- Reset: EN at J1.20 falls to 0 V on SW1 and rises with a 10 ms time constant.
- PSRAM: an ESP-IDF build with quad SPIRAM reports 2 MB at boot.

## 6. Crystal
Run `Certification and Test Tool` in TX tone mode at 2442 MHz (HDG 1.3.5). Read the frequency offset on a spectrum analyser. Target +/-10 ppm, 24 kHz at 2.4 GHz. Positive offset: load too small, raise C15 and C16. Negative: lower them. Start 12 pF.

## 7. RF tuning
Parts: chip CLC C20, L3, C21; antenna CLC C22, R12, C23. Tuning follows HDG 1.3.6.
1. **Antenna first.** Remove L3. Solder a 50 ohm pigtail to the RF1 side of R12 and the ground beside it, calibrated to that plane. Measure S11 at 2.40 to 2.50 GHz through R12 0 ohm. Target -10 dB across the band (Johanson spec) with the board in its enclosure. The land inset of 0.4 mm and the 26 mm board width will move it from the datasheet's plot.
2. If the dip sits low or high, fit C22, C23 and swap R12 for an inductor. Start with C23 0.5 pF, or R12 1.0 nH. Move one part at a time. Series L lowers the resonance; shunt C at the antenna lowers it too.
3. **Chip match.** Refit L3, leave the antenna path disconnected at R12 with a 50 ohm load there. Target S11 near 35 + j0 ohm looking from the chip side, and S21 better than -35 dB at 4.8 and 7.2 GHz (HDG 1.3.6). Range: C20 and C21 1.2 to 1.8 pF, L3 2.0 to 3.0 nH.
4. Conducted power check with the Certification and Test Tool: 802.11b 1 Mbps about 21 dBm at the antenna path (DS).
5. Burst test: 802.11b TX continuous at full power. TP2 stays above 3.0 V, U2 stays below 90 C. Peak draw 340 mA from the chip (DS table 5-7).

Refs named here for the silk row: C7 C13 L1 D1 U1 U2 U3 J3 J4 J5 Y1 SW1 SW2 TP1 TP2 TP3 TP4 LED1 LED2 JP1 JP2 C20 L3 C21 C22 R12 C23.
