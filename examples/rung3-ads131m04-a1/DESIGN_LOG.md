# Design log: ADS131M04 breakout rev A

All numbers from `pcb` tools are in SUMMARY.md; each calculation here is a `calcs` row in `checks.json`. ADC datasheet is SBAS890D (docs/ads131m04.pdf). LDO: docs/tps7a20.pdf. Oscillator: YXC YSO110TR, docs/yxc_ot2ji.pdf.

## 1. Plan

### Rails and current budget
| Rail | Source | Max load | Note |
|---|---|---|---|
| VIN | J2.1, 3.3 to 5 V | 11.5 mA + user 3V3 load | U2 IN and EN |
| 3V3 | U2 TPS7A2033, 300 mA | 11.5 mA (`i_3v3_ma`): IAVDD 4.0, IDVDD 0.5, Y1 5.0, D1 1.3, pull-ups 0.66 with both lines low | DVDD and Y1 |
| AVDD | 3V3 through FB1 | 4.0 mA | drop 1.8 mV (`fb_drop_mv`) |
| CAP | U1 internal, 1.8 V | none | 220 nF only |

`currents` rows: VIN 0.15 A, 3V3 0.12 A, AVDD 0.01 A. Rail tracks are 0.3 to 0.4 mm.

### Two sources
The common brief's Qwiic path does not exist on this board: SPI, no Qwiic (board brief). VIN is the only source, so nothing can back-feed from a second supply. The J2.2 3V3 pin is an output. TPS7A20 has no reverse blocking; its 6.3.7 limits reverse current to 5 % of rated, 15 mA, for a short time, so README calls the pin an output and the back silk says so by labelling VIN as the input.

### Connector tables
J1 and J2 tables: README and `connectors` rows. J1 is 1x11, J2 is 1x10, both PZ254V 2.54 mm, shipped loose, DNP in the CPL.

### Jumpers
JP1 2-pad bridged: 3V3 to the LED chain, cut to disable. The vendored footprint is renamed `..._Bridged12_...` so `pcb check` reads its shipped state; copper is the stock KiCad part.

### Parts, verified live on 2026-11-04 (`tools/verify_parts.py`, raw in docs/parts_verified.json)
| Ref | MPN | Maker | LCSC | Class | Stock | Footprint check |
|---|---|---|---|---|---|---|
| U1 | ADS131M04IPWR | TI | C2862562 | extended | 1,074 | KiCad Texas_PW0020A; pads 1.5 x 0.45 at x +/-2.9, 20 pads, pin 1 top-left, same as TI land pattern 20X (1.5), 20X (0.45), (5.8). `pcb q pads U1`: pin 1 at (114.075, 115.6) after rotation, pin order W to E on the south row |
| U2 | TPS7A2033PDBVR | TI | C2862740 | extended | 133,557 | KiCad SOT-23-5, 5 pads; 1 IN, 2 GND, 3 EN, 4 NC, 5 OUT per Pin Functions SOT-23 |
| Y1 | OT2JI-111-8.192M | YXC | C7425393 | extended | 4,494 | Vendored from KiCad's Abracon ASE with the pads changed to YXC's 3.2 x 2.5 land: 1.3 x 1.2, gaps 0.8 and 0.7 (pad centres +/-1.05, +/-0.95). 4 pads, 1 tri-state, 2 GND, 3 OUT, 4 VDD, counter-clockwise from the top |
| C1 C2 C4 | CL10A105KB8NNNC 1 uF 50 V X5R | Samsung | C15849 | basic | 12,143,340 | stock C_0603 |
| C3 | CL10B224KA8NNNC 220 nF 25 V X7R | Samsung | C21120 | basic | 923,219 | stock C_0603 |
| C5 | CL10A106KP8NNNC 10 uF 10 V X5R | Samsung | C19702 | basic | 10,976,460 | stock C_0603 |
| C6 | CC0603KRX7R9BB104 100 nF 50 V | YAGEO | C14663 | basic | 37,533,176 | stock C_0603 |
| C7-C10 | GRM1885C1H103JA01D 10 nF 50 V C0G | Murata | C85973 | extended | 262,268 | stock C_0603 |
| R1-R8 R13 | 0603WAF1001T5E 1 k | UNI-ROYAL | C21190 | basic | 28,487,671 | stock R_0603 |
| R9-R12 R14-R16 | 0603WAF470JT5E 47 ohm | UNI-ROYAL | C23182 | basic | 1,436,987 | stock R_0603 |
| R17 R18 | 0603WAF1002T5E 10 k | UNI-ROYAL | C25804 | basic | 44,419,718 | stock R_0603 |
| FB1 | GZ1608D601TF | Sunlord | C1002 | basic | 514,451 | stock L_0603 |
| D1 | KT-0603R red | KENTO | C2286 | basic | 6,728,625 | stock LED_0603, pad 1 cathode. Not checked against a drawing: JLC's preview must confirm polarity |
| J1 | PZ254V-11-11P | XFCN | C2840011 | loose | 21,008 | stock 1x11, silk removed |
| J2 | PZ254V-11-10P | XFCN | C492409 | loose | 35,150 | stock 1x10, silk removed |

C1 and C2 are X5R where 11.1 says "for example, X7R grade". The 11.1 rule against high-K caps names Y5V; the 50 V rating keeps bias derating low at 3.3 V; the part is basic, X7R 0603 1 uF is extended. C7 to C10 are C0G, which 11.1 requires.

### Floor plan
Analog south, digital north, ADC between, power west. U1 is rotated so pins 1 to 10 face J1 and pins 11 to 20 face J2. J1 and J2 sit on the same 2.54 mm grid 22.86 mm apart. Mounting holes at the mid-points of the short edges, because the corners are taken by the header rows.

### Stackup and margins
JLC 4-layer stock, F.Cu signal and fill, In1 and In2 solid GND, B.Cu rail and fill. Clearance 0.2, track 0.2 (signals) and 0.25 default class, via 0.6/0.3, hole clearance 0.3, edge 0.4, silk 0.15, text 1.0. JLC floor 0.09/0.09/0.45/0.2.

## 2. Decisions with numbers

### Ground: the datasheet against two solid planes
11.1: "dedicate an entire PCB layer to a ground plane". It offers separate planes only when a dedicated plane "may not be practical", and then a direct connection at the ADC. 10.3: analog and digital ground "connected together as close to the device as possible". Figure 11-1 partitions by placement, analog left, digital right. This board needs no split: one GND net, In1 and In2 solid. The two agree. Partition comes from placement. Pin 2 (AGND) and pin 19 (DGND) join under the package with a 0.3 mm track and two vias to the planes at (114.725, 114.0) and (114.725, 111.4), so the tie is at the device and the plane is unbroken. `refplane`: every net 0.0 mm off solid ground. `pcb q coverage U1`: In1 and In2 100.0 %.

### Separation
Every analog input net is F.Cu only, zero vias, under solid In1, and all of it south of U1. Every digital net is north of U1. `exposure` at 1.0 mm, aggressors SCLK, SCLK_R, CLK_OSC, CLKIN, victims weighted 3: 0 mm on all 16 AIN nets. Rerun at 5.5 mm (`/tmp`, not a deliverable): 0.3 to 0.5 mm on 7 nets, all at the U1 pin row. `pcb q dist`: U1.14 SCLK to U1.9 AIN3N 4.43 mm edge; U1.17 CLKIN to U1.3 AIN0P 4.32 mm edge; R14 to U1.3 7.51 mm; Y1 OUT to U1.3 8.00 mm.

### Antialias filter and data rate
Figure 9-1 values kept: 1 k each leg, 10 nF across. fc = 1 / (2 pi x 2 k x 10 nF) = 7.96 kHz (`fc_hz`). Chosen rate 16 kSPS, OSR 256, Nyquist 8 kHz (`fc_over_nyquist_16k` 0.995), noise 10.68 uVrms at gain 1 (Table 7-1). The band the digital filter cannot reject is around fMOD 4.096 MHz (8.3.7): one pole gives 54.2 dB there (`atten_fmod_db`).

The brief's 64 kSPS still runs, at 12.35 dB down at 32 kHz with these caps (`atten_32k_db`). A logger that wants the full band changes C7 to C10 to 2.2 nF C0G, LCSC C33353, 2,738 in stock: 36.2 kHz (`fc_wide_hz`). Figure 9-1 is stated as sufficient across CLKIN 2 to 8.2 MHz and I kept it as stock because the brief ranks datasheet notes first. Noise at 64 kSPS is 75.34 uVrms, against 21.31 at 32 kSPS, so the 16 kSPS corner suits most users.

Series R cost: 2 k against Zin 330 k at gain 1 to 4 (Equation 4) is 0.606 % gain error (`gain_err_pct`), corrected by the GCAL registers. Thermal noise of 2 k over the filter bandwidth 0.64 uVrms (`r_noise_uv`), small against 10.68.

Channel skew: the ADC samples together, but each RC delay is 2 k x 10 nF = 20 us with C +/-5 % and R +/-1 %, so filter tolerance gives up to 2.4 us between channels at frequencies well under the corner. For phase work, calibrate with the PHASEn registers or fit 1 % C0G.

Fault current: 1 k in series with the ESD diodes (8.3.1) holds 10 mA (6.1) at about 10 V past the rails. No TVS: leakage would add offset through the 1 k.

### Input connector: 0.1 inch header, not 3.5 mm screw terminal
Eight signal pins and three grounds at 2.54 mm take 25.4 mm. Eight 3.5 mm positions take 28 mm and the body about 7 mm of a 25.4 mm board, which is what the filter band needs. J1 makes the second row of a 0.9 inch breadboard straddle. Screw terminals can be added on a carrier; a header cannot be recovered from a terminal block. Pin order follows the ADC, P N, GND, N P, so no pair crosses and no input takes a via.

### LDO and AVDD noise
TPS7A2033PDBVR. VN 10 uVrms at 1 mA, 10 Hz to 100 kHz, in the VOUT = 2.8 V row, the closest listed. PSRR at 20 mA, VIN = VOUT + 1 V: 95 dB at 100 Hz and 1 kHz, 75 dB at 10 kHz and 100 kHz, 45 dB at 1 MHz. So across the ADC's band of 250 Hz to 32 kHz supply ripple falls 75 dB or more at the LDO.
ADC side: AVDD PSRR 75 dB at dc, 78 dB at 50/60 Hz (6.5). 10 uV through 75 dB is 1.78 nVrms input-referred (`ldo_noise_rti_nv`), 236 times below the lowest noise in Table 7-1, 0.42 uVrms (`ldo_margin_vs_adc`). ADC PSRR is not specified above 60 Hz; I assumed 75 dB holds across the band, and a fall of 40 dB would still leave the LDO term 2.4 times under 0.42 uV.
At VIN = 3.3 V the LDO sits in dropout, about 5 mV at 11.5 mA, and PSRR is gone: the LDO's PSRR rows need 0.3 V to 1 V of headroom. The board still runs (AVDD limit 2.7 V). Use 5 V for the numbers above. Not worked around: a 3.0 V rail would hold regulation from 3.3 V, but then a 3.3 V host exceeds DVDD + 0.3 V at the limit.
FB1 separates the ADC's AVDD from Y1's 8 MHz current on 3V3. Dissipation 19.5 mW at 5 V (`p_ldo_mw`), TJ 88.9 degC at 85 degC ambient with RthJA 200 K/W (`tj_ldo`). C5 10 uF X5R holds COUT above the 0.47 uF effective minimum (note 3); C4 1 uF.

### Clock
C7425393 re-checked: YSO110TR, 3.2 x 2.5, 1.8 to 3.3 V, CMOS, duty 45 to 55 % (ADS limit 40 to 60), rise 4 ns max, 0.7 ps jitter (12 kHz to 20 MHz), 5 mA max. Tri-state pin to 3V3. Note 1 requires 0.01 to 0.1 uF at VDD: C6 100 nF, 1.53 mm. R14 47 ohm source termination at the oscillator (11.1: "a source-termination resistor placed at the clock buffer"). CLK_OSC 2.3 mm, CLKIN 3.0 mm, both F.Cu, no via.

### Digital
47 ohm in all six lines (Figure 11-1: "Terminate long digital input lines with resistors"), placed in line under the header columns. 10 k pull-ups on CS and SYNC/RESET at the ADC side: both idle high with no host, as 9.1.1 and 9.1.3 require. SCLK and DIN have none: a connected host drives them; 9.1.1's "do not float" applies with no host attached, as leakage only.
64 kSPS needs 9.216 MHz SCLK at 24-bit words (`sclk_min_mhz_64k`), under the 25 MHz limit (tc(SC) 40 ns).
No level shifting: a shifter adds an edge source beside the ADC and a 3.3 V host needs none. 5 V hosts are out, README and back silk say so.

### Thermal connections
J1 pins 3, 6 and 9 have solid zone connections on purpose: on F.Cu the tracks above and the board edge below left one spoke, a `starved_thermal` DRC error. They join four planes, so they take more heat to solder by hand. J2 keeps thermal relief.

### Autorouter
Not used. All 192 tracks are in `tools/layout_board.py`: 30 of 36 routed nets are analog, SPI or clock with their paths chosen, and the rest are short rails. `pcb q ratsnest` reads 0 open.

## 3. Datasheet layout requirements

| Section | Requirement | Where met |
|---|---|---|
| 5, Table 5-1 | AVDD 1 uF to AGND, DVDD 1 uF to DGND, CAP 220 nF to DGND | C1, C2, C3; `decoupling` rows 1.81, 1.88, 1.77 mm |
| 8.3.5 | LVCMOS clock on CLKIN continuously | Y1 |
| 9.1.1 | Do not float digital inputs; DRDY may float | CS and SYNC pull-ups; DRDY floats with no host |
| 9.1.2, Figure 9-1 | RC filter per channel, 1 k, 10 nF | R1-R8, C7-C10 |
| 10.1 | 220 nF on CAP at DVDD > 2.7 V | C3 |
| 10.2 | Any sequence; inputs must not exceed supplies | One rail; README states input limits |
| 10.3 | Bypass as close as possible, low impedance; ground tied at device | Under-body tie; C1 GND via 0.80 mm |
| 10.3 | Avoid vias between bypass caps and pins in sensitive systems | C1, C2, C3 reach their pins on F.Cu with no via |
| 11.1 | Dedicated ground plane | In1, In2 |
| 11.1 | Route digital away from analog inputs | `exposure` 0 mm |
| 11.1 | C0G on analog inputs, ceramic on supplies | C7-C10, C1-C6 |
| 11.1 | Clock free of overshoot, source termination | R14 |
| Figure 11-1 | Analog and digital partitioned, RC per channel, digital series R | Floor plan |
| PW0020A | Land pattern, non-solder-mask-defined preferred | KiCad Texas_PW0020A, no EP on this package |
| YXC page 3 | 3225 land pattern, VDD bypass | Vendored footprint, C6 |
| TPS7A20 | CIN at IN, COUT at OUT, ESR under 100 mohm | C4 1.71 mm, C5 1.69 mm, ceramic |

No thermal pad on the TSSOP (Table 5-1 lists it for WQFN only), so no thermal vias and no `thermal_vias` row. No current over 150 mA, so no `feeds` or `irdrop` rows.

## 4. Open issues
- `pcb dfm --offline` exits non-zero with 0 errors and 2 not evaluated: it cannot attribute JP1's bridge copper (front-end.md lists this).
- The `refstat` and `basic_parts` rows need `tools/bench`, which PATH.md puts off limits. Class counts above are from the live query: 6 extended SMT lines were reduced to 4 (U1, U2, Y1, C7-C10).
- Top silk carries J2 pins 4 to 10 in a row south of the SPI fan, not beside the pins: series R and Y1 hold the space under the header. J2 pins 1 to 3 and J1 pin names are on the back only; top has channel numbers on J1.
- No reverse-polarity protection on VIN. The brief does not ask for it, and a series diode would cost 0.3 V at the 3.3 V input.
