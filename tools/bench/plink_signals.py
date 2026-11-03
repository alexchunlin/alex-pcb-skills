#!/usr/bin/env python3
"""The MotorGo Plink (4-channel DRV8874 + TPS54620 + ESP32-S3) as a routing benchmark: writes tools/bench/plink/checks.json
(rails, feeds, thermal vias, currents, the SIG-1 `signals` block, the judge blocks). The board itself is read-only at
/tmp/pcb-ref/motorgo-plink-hardware (tools/bench/README.md); the bench copies it. Currents are assumptions stated here:
the Plink has no current budget in its docs, so 1.5 A per channel continuous and 1.5 A into the buck (6 A at the jack).

  python3 -I tools/bench/plink_signals.py          # writes the config and prints `pcb signals` on it
"""
import json, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PCB = ROOT / "skills/kicad-design/scripts/pcb"
OUT = ROOT / "tools/bench/plink/checks.json"
NETLIST = Path("/tmp/alexpcb-sig/plink/motorgo_plink.xml")

ESP = 3        # ns, assumption: ESP32-S3 GPIO at the default drive strength, 3.3 V CMOS
USB_FS = 4     # ns, USB full-speed edge, spec minimum 4 ns (the ESP32-S3 native USB is full speed, 12 Mb/s)
NFAULT = 20    # ns, assumption: DRV8874 open-drain pull-down, no spec
SW = 3         # ns, assumption as rung 2: the TPS54620 datasheet gives no SW edge rate
GPIO_SRC = f"assumption: ESP32-S3 GPIO, 3.3 V CMOS edge {ESP} ns at the default drive strength"
CH = {"U3": ("m2", "Rp1", "Rmode1", "R10", "R11", "C5", "C3"), "U4": ("m1", "Rp2", "Rmode2", "R12", "R13", "C9", "C7"),
      "U5": ("m3", "Rp3", "Rmode3", "R14", "R15", "C13", "C11"), "U9": ("m4", "Rp4", "Rmode4", "R36", "R37", "C28", "C26")}
MOTOR_OUT = {"U4": "motor_controls1", "U3": "motor_controls2", "U5": "motor_controls3", "U9": "motor_controls4"}

sig = {"_about": "SIG-1 for the Plink: driver edge per net with the source of the number; `pcb signals` computes knee and bucket. "
                 "Every rise time is a stated assumption except USB full speed (spec 4-20 ns) and the DRV8874 OUTx 150 ns."}
# ESP32 GPIO outputs: motor control, encoder chip selects, I2C (the open-drain fall is the GPIO's own edge), UART, LEDs
for u, (m, rp, rmode, rpu, rpm, cfly, cvcp) in CH.items():
    sig[f"{m}_EN"] = {"driver": f"U1 GPIO -> {u}.1 EN/IN1 (PWM)", "t_rise_ns": ESP, "source": GPIO_SRC, "victim": False}
    sig[f"{m}_PH"] = {"driver": f"U1 GPIO -> {u}.2 PH/IN2", "t_rise_ns": ESP, "source": GPIO_SRC, "victim": False}
    sig[f"Net-({u}-IPROPI)"] = {"driver": f"{u}.6 IPROPI current mirror into {rp} 4.87k", "t_rise_ns": 150,
                               "source": "follows the bridge current, which steps at the OUTx edge (DRV8874 tRISE 150 ns); weak aggressor",
                               "victim": True, "note": "analog, 4.87k source impedance, ADC input on U1"}
    sig[f"Net-({u}-nFAULT)"] = {"driver": f"{u}.4 open-drain (fall); {rpu} 10k pull-up to +5V (rise); nSLEEP tied to it", "t_rise_ns": NFAULT,
                               "source": f"assumption: DRV8874 open-drain pull-down into ~20 pF, {NFAULT} ns; rise is the RC", "victim": False,
                               "slowed_by": [f"{rpu} 10k pull-up (rise only)"]}
    sig[f"Net-({u}-IMODE)"] = {"driver": f"{rmode} to GND (DC config)", "t_rise_ns": None, "source": "DC", "victim": False}
    sig[f"Net-({u}-PMODE)"] = {"driver": f"{rpm} to +5V (DC config)", "t_rise_ns": None, "source": "DC", "victim": False}
    sig[f"Net-({u}-CPH)"] = {"driver": f"{u}.13 charge-pump switch into {cfly} 22 nF", "t_rise_ns": 2000,
                            "source": "no edge spec; slew bound by I/C, tens of mA into 22 nF over ~5 V >= 2 us; fVCP 400 kHz", "victim": False}
    sig[f"Net-({u}-CPL)"] = {"driver": f"{u}.14 charge-pump switch into {cfly} 22 nF", "t_rise_ns": 2000, "source": "as CPH", "victim": False}
    sig[f"Net-({u}-VCP)"] = {"driver": f"{u}.12 VCP into {cvcp} 100 nF (VM + ~5 V)", "t_rise_ns": None, "source": "DC with 400 kHz ripple", "victim": False}
    sub = MOTOR_OUT[u]
    for pin, net in (("10", f"/{sub}/motor_out1"), ("8", f"/{sub}/motor_out2")):
        sig[net] = {"driver": f"{u}.{pin} OUTx (DRV8874)", "t_rise_ns": 150, "source": "DRV8874 datasheet tRISE/tFALL 150 ns (OUTx 10-90 %, VM 24 V)",
                    "victim": False, "note": "1.5 A edges: the magnetic aggressor for the IPROPI nets, not a fast one"}
for i, j in ((1, "J14"), (2, "J16"), (3, "J18"), (4, "J20")):
    sig[f"/connectors.enc{i}.cs"] = {"driver": f"U1 GPIO -> {j}.1 (encoder chip select / enable)", "t_rise_ns": ESP, "source": GPIO_SRC, "victim": False}
for n, r in (("/connectors.enc_scl", "R32"), ("/connectors.enc_sda", "R33"), ("/i2c_1.scl", "R39"), ("/i2c_1.sda", "R38"), ("scl", "R31"), ("sda", "R30")):
    sig[n] = {"driver": f"U1 GPIO open-drain (fall), {r} pull-up to +3.3V (rise); I2C", "t_rise_ns": ESP,
              "source": f"the fall is the GPIO's own edge ({GPIO_SRC}); the rise is the pull-up RC", "victim": False,
              "slowed_by": [f"{r} pull-up (rise only)"], "note": "I2C at 400 kHz; four JST drops on the encoder bus"}
for n, pin in (("gpio43", "U0TXD"), ("gpio44", "U0RXD")):
    sig[n] = {"driver": f"U1.{pin} UART, LED through 1k", "t_rise_ns": ESP, "source": GPIO_SRC, "victim": False}
for n in ("gpio21", "gpio35", "gpio36", "gpio37", "gpio38", "gpio39", "gpio40", "gpio41", "gpio42", "gpio47", "gpio48"):
    sig[n] = {"driver": "U1 GPIO to the J4/J7 headers (spare I/O)", "t_rise_ns": ESP, "source": GPIO_SRC + "; use unknown, the edge is the GPIO's",
              "victim": False, "note": "spare header I/O: bucket by the driver's edge, a slower use would relax it"}
sig["Net-(D1-K)"] = {"driver": "gpio44 through LED D1 and R1 1k", "t_rise_ns": ESP, "source": "follows the UART edge through the LED", "victim": False}
sig["Net-(D2-K)"] = {"driver": "gpio43 through LED D2 and R2 1k", "t_rise_ns": ESP, "source": "follows the UART edge through the LED", "victim": False}
sig["Net-(D3-K)"] = {"driver": "+3.3V through LED D3 and R3 1k (power LED)", "t_rise_ns": None, "source": "DC", "victim": False}
sig["boot"] = {"driver": "R8 5.1k pull-up, button J2, header pin; GPIO0 strap", "t_rise_ns": None, "source": "button and RC at boot only", "victim": False}
sig["reset"] = {"driver": "R9 5.1k pull-up, button J3, header pin; EN", "t_rise_ns": None, "source": "button and RC", "victim": False}
for n in ("p26", "p31", "p32", "p33", "p35", "p36", "p37", "p38", "p40"):
    sig[n] = {"driver": "none on this board: J4 to J7 pass-through", "t_rise_ns": None, "source": "no driver on the board", "victim": False}
# USB full speed: a 90 ohm pair at 12 Mb/s; edges 4-20 ns by the spec, taken at the fast end
for n, where in (("usb_d+", "U1.14 USB_D+ to R6 0R"), ("usb_d-", "U1.13 USB_D- to R7 0R"), ("Net-(R6-Pad2)", "R6 to U2.6 (USBLC6)"),
                 ("Net-(R7-Pad2)", "R7 to U2.4 (USBLC6)"), ("Net-(J1-DP1)", "U2.1 to J1 DP1/DP2"), ("Net-(J1-DN1)", "U2.3 to J1 DN1/DN2")):
    sig[n] = {"driver": where, "t_rise_ns": USB_FS, "source": "USB 2.0 full speed, driver edge 4-20 ns by the spec, 4 ns taken",
              "victim": False, "note": "differential pair, 90 ohm; route as a pair (bucket 3 by edge, the pair rule from USB)"}
sig["Net-(J1-CC1)"] = {"driver": "R4 5.1k to GND (USB-C sink CC)", "t_rise_ns": None, "source": "DC", "victim": False}
sig["Net-(J1-CC2)"] = {"driver": "R5 5.1k to GND (USB-C sink CC)", "t_rise_ns": None, "source": "DC", "victim": False}
# buck
sig["Net-(C22-Pad1)"] = {"driver": "U6.11/12 PH (TPS54620 internal FETs): the switch node", "t_rise_ns": SW,
                         "source": f"assumption: no SW edge spec in the datasheet, {SW} ns as rung 2", "victim": False, "note": "SW; In1 is its return"}
sig["Net-(U6-BOOT)"] = {"driver": "U6.13 BOOT, rides on SW through C22", "t_rise_ns": SW, "source": "same edge as SW", "victim": False}
sig["Net-(C23-Pad1)"] = {"rail": True, "driver": "L1.2: the buck output before D4 ORs it onto +5V", "source": "rail: judged by irdrop and currents"}
for n, d in (("Net-(U6-COMP)", "U6.8 COMP error amplifier output, R19 3.92k"), ("Net-(C1-Pad1)", "COMP through R19: C1 68 pF / C20 6.8 nF"),
             ("Net-(U6-VSENSE)", "+5V side through R24 53.6k / R25 10k"), ("Net-(U6-RT/CLK)", "U6.1 RT bias through R18 53.6k"),
             ("Net-(U6-SS/TR)", "U6.9 SS into C18 2.2 nF"), ("Net-(U6-EN)", "+BATT through R16 102k / R17 36.5k (UVLO)")):
    sig[n] = {"driver": d, "t_rise_ns": None, "source": "DC or slow analog", "victim": True}
# IMUs
sig["Net-(U10-C1)"] = {"driver": "U10.4 C1 (LIS3MDL internal cap pin)", "t_rise_ns": None, "source": "DC", "victim": False}
sig["Net-(U10-SD0/SA1)"] = {"driver": "R46 address strap", "t_rise_ns": None, "source": "DC", "victim": False}
sig["Net-(U11-SDO/SA0)"] = {"driver": "R49 address strap", "t_rise_ns": None, "source": "DC", "victim": False}
sig["Net-(U11-CS)"] = {"driver": "R50 pull-up (I2C mode)", "t_rise_ns": None, "source": "DC", "victim": False}

cfg = {
    "_about": "MotorGo Plink v1 as a routing benchmark (tools/bench/plink_signals.py writes this). The board is the designer's; "
              "the bench keeps its placement and pours and re-routes. Currents are assumptions: 1.5 A per channel, 1.5 A into the buck.",
    "project": "motorgo_plink routing bench",
    "policy": {"clearance_mm": 0.12, "track_mm": 0.12, "via_drill_mm": 0.3, "via_dia_mm": 0.4, "hole_clearance_mm": 0.25, "silk_text_mm": 0.8,
               "_why": "the designer's own setup: JLC 4-layer minimums"},
    "rails": {"+BATT": {"v": 12.0, "source": "J11 DC jack, 6-17 V"}, "+5V": {"v": 5.0, "source": "U6 TPS54620 through D4, or USB VBUS"},
              "Net-(C23-Pad1)": {"v": 5.3, "source": "U6 buck output before D4"}, "+3.3V": {"v": 3.3, "source": "U8 AMS1117-3.3"}, "GND": {}},
    "copper_oz": {"outer": 1.0, "inner": 0.5}, "rise_c": 20,
    "currents": {"+BATT": 6.0, "+5V": 3.0, "Net-(C23-Pad1)": 3.0, "+3.3V": 0.5,
                 **{f"/{s}/motor_out{i}": 1.5 for s in MOTOR_OUT.values() for i in (1, 2)}},
    "feeds": [*[{"pad": f"{u}.11", "amps": 1.5, "within_mm": 3.5, "_why": "VM"} for u in CH],
              *[{"pad": f"{u}.{p}", "amps": 1.5, "within_mm": 3.5, "_why": "OUTx"} for u in CH for p in ("8", "10")],
              {"pad": "U6.4,5,6", "amps": 1.5, "within_mm": 3.5, "_why": "PVIN"}, {"pad": "L1.2", "amps": 3.0, "within_mm": 3.5, "_why": "buck output"},
              {"pad": "J11.1", "amps": 6.0, "within_mm": 4.0, "_why": "the jack"}],
    "thermal_vias": {**{u: {"pad": "17", "min": 9, "within_mm": 3.0} for u in CH}, "U6": {"pad": "15", "min": 4, "within_mm": 1.5}},
    "refplane": {"ground": "GND"}, "return_via": {"ground": "GND"},
    "exposure": {"aggressors": ["Net-(C22-Pad1)"] + [f"/{s}/motor_out{i}" for s in MOTOR_OUT.values() for i in (1, 2)], "within_mm": 1.0, "victim_weight": 3},
    "signals": sig,
}
OUT.parent.mkdir(parents=True, exist_ok=True)
json.dump(cfg, open(OUT, "w"), indent=1); open(OUT, "a").write("\n")
if NETLIST.exists():
    p = subprocess.run([str(PCB), "signals", str(OUT), "--netlist", str(NETLIST)], capture_output=True, text=True)
    print(p.stdout[-1500:], p.stderr[-300:])
