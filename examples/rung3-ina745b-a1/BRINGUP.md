# Bring-up: INA745B power monitor

Tools: DMM, 3.3 V or 5 V supply with current limit, I2C host (Qwiic), a bench supply or battery and a load for the current path.
Test points: TP1 = GND, TP2 = 3V3, TP3 = VBUS. Header J3: 1 VIN, 2 3V3, 3 GND, 4 SCL, 5 SDA, 6 ALERT. Terminals: J4 = IS+, J5 = IS-.

1. **Visual.** U1 pin 1 dot at the IS+ side, on the row facing the header. JP1 closed, JP2 both links closed, JP3 and JP4 bridged to G, JP5 closed. J3 loose. J4 and J5 soldered on all four legs.
2. **Unpowered resistance.** TP2 to TP1: above 100 k (a short reads under 10 ohm). J4 to J5: 1.0 mOhm typical, 0.8 to 1.3 (four-wire only, a DMM reads its lead resistance). J4 to TP3: under 1 ohm with JP1 closed. J4 to TP1: above 100 k.
3. **Pull-ups.** Unpowered, SDA to 3V3 and SCL to 3V3 on J3: 10 k +/-1 %. ALERT to 3V3: 10 k.
4. **Power from Qwiic.** Connect the host on J1 or J2. TP2 3.3 V. Board current 2.0 mA typical: U1 0.64 mA, LED D2 1.3 mA, pull-ups idle. D2 lit. J3.1 (VIN) must read under 0.1 V: a higher reading means D1 is not blocking.
5. **Power from VIN.** Host off, 5.0 V on J3.1 with a 50 mA limit, GND on J3.3. TP2 3.30 V +/-1.5 %. With 3.3 V on VIN: TP2 about 3.0 V, still above the 2.7 V VS minimum.
6. **Bus scan.** Expect 0x40. Register 0x3E (MANUFACTURER_ID) reads 0x5449 ("TI").
7. **Address straps.** Cut JP3 1-2, bridge JP3 2-3: 0x41. Same on JP4 with JP3 restored: 0x44. Both moved: 0x45. A jumper with neither side bridged leaves the pin floating and the address undefined.
8. **Bus voltage.** Apply 12.0 V to J4, return to GND (common with the logic ground), J5 open. Register 0x05 VBUS reads 3840 (0x0F00) = 12.00 V at 3.125 mV/LSB, +/-0.3 % max (SBOSAC3B 5.5).
9. **Current at zero.** Same as step 8. Register 0x07 CURRENT reads within +/-52 LSB: +/-62.5 mA max offset at 1.2 mA/LSB. Typical +/-7.5 mA.
10. **Current at 10 A.** Load from J5 to the supply return, 10 A set by a calibrated supply. Register 0x07 reads 8333 (0x208D) +/-1.25 % +offset. Die temperature register 0x06, 125 m degC/LSB, reads ambient + about 6 K after two minutes.
11. **Current at 25 A.** With a current-limited supply, M4 ring lugs on 10 AWG (5 mm2) or heavier wire, still air. Wait 10 minutes. Die temperature register under 80 degC at 25 degC ambient (calculated 68 degC typical, 79 degC at the worst-case 1.3 mOhm). Above 90 degC: stop, the thermal model in DESIGN_LOG.md section 2 is wrong for this board.
12. **ALERT.** Write COL 0x0C with 5 A / 1.2 mA = 4167 (0x1047), set 6 A through the path: J3.6 goes low.
