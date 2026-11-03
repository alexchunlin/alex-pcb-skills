#!/usr/bin/env python3
"""Signal classification for the three rung-2 boards (SIG-1): writes the `signals` block into each example's checks.json.

The boards share one topology (DRV8874 channel, TPS54620 buck, AMS1117 LDO, AO4407A ideal diode) with different net
names and reference designators, so the facts live here once per role and are written per board with that board's
names. Rise times come from the datasheet where it gives one (DRV8874 tRISE/tFALL 150 ns, fVCP 400 kHz) and are stated
assumptions everywhere else; `pcb signals` computes the knee and bucket. Re-run after changing a fact:

  python3 -I tools/bench/rung2_signals.py            # writes examples/rung2-*/checks.json
  python3 -I tools/bench/rung2_signals.py --print    # the table per board, nothing written
"""
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PCB = ROOT / "skills/kicad-design/scripts/pcb"

MCU_EDGE = 3        # ns, assumption: 3.3 V CMOS GPIO (ESP32 class) behind the control header, no series R on the board
ENC_EDGE = 10       # ns, assumption: push-pull CMOS encoder output; an open-collector hall encoder is 100 ns-1 us
NFAULT_FALL = 20    # ns, assumption: open-drain pull-down into ~20 pF (header, LED, test point); no spec in the datasheet
SW_EDGE = 3         # ns, assumption: no edge spec in the TPS54620 datasheet (min on-time 94 ns is the nearest number);
                    # 2-5 ns on the SW node of monolithic sync bucks of this class
LOAD_PF = 20        # header-side load behind the encoder series R: ribbon + MCU input

GPIO_SRC = f"assumption: MCU GPIO behind the control header, 3.3 V CMOS edge {MCU_EDGE} ns; no series R on the board or the cable"


def rss(*t):
    return round(sum(x * x for x in t) ** 0.5, 1)


def entries(b):
    """b: per-board names and refs. Returns {net: entry} in the canonical order."""
    enc_series_ns = 2.2 * 1e3 * LOAD_PF * 1e-3  # 2.2 RC, 1k into LOAD_PF pF, in ns
    enc_hdr = rss(ENC_EDGE, enc_series_ns)
    e = {
        "_about": "SIG-1: per-net driver edge, with the source of the number; `pcb signals` computes knee (0.5/t_rise) and bucket. "
                  "Rails are judged by irdrop/currents, not knee. Assumptions are marked; replace them with measured edges when a scope is on the board.",
        b["SW"]: {"driver": "U1.11/12 PH (TPS54620 internal FETs)", "t_rise_ns": SW_EDGE,
                  "source": f"assumption: the TPS54620 datasheet gives no SW edge rate (min on-time 94 ns is the nearest number); "
                            f"monolithic 6 A sync bucks measure 2-5 ns on SW, {SW_EDGE} ns taken", "victim": False,
                  "note": "the aggressor the stackup policy is built around; In1 is its return"},
        b["BOOT"]: {"driver": f"U1.13 BOOT, rides on SW through {b['boot_cap']}", "t_rise_ns": SW_EDGE,
                    "source": "same edge as SW (the bootstrap cap ties the node to SW)", "victim": False},
        b["PWM"]: {"driver": "MCU GPIO on J3 -> U2.1 EN/IN1", "t_rise_ns": MCU_EDGE, "source": GPIO_SRC, "victim": False,
                   "slowed_by": [], "note": "U2.1 has only the internal 100 k pull-down; a 100 R + 100 pF RC at the header would make it 22 ns (bucket 2)"},
        b["DIR"]: {"driver": "MCU GPIO on J3 -> U2.2 PH/IN2", "t_rise_ns": MCU_EDGE, "source": GPIO_SRC, "victim": False,
                   "note": "toggles rarely; the bucket follows the edge, not the rate"},
        b["nSLEEP"]: {"driver": "MCU GPIO on J3 -> U2.3 nSLEEP", "t_rise_ns": MCU_EDGE, "source": GPIO_SRC, "victim": False,
                      "note": "toggles rarely; the bucket follows the edge, not the rate"},
        b["ENC_A_IN"]: {"driver": "encoder output on J2.2", "t_rise_ns": ENC_EDGE,
                        "source": f"assumption: push-pull 3.3 V CMOS encoder output, {ENC_EDGE} ns (the brief names no encoder); "
                                  "an open-collector hall encoder would be 100 ns-1 us (bucket 1-2)", "victim": False,
                        "slowed_by": ([f"{b['enc_pu'][0]} pull-up (rise only, open-collector encoders)"] if b.get("enc_pu") else [])},
        b["ENC_B_IN"]: {"driver": "encoder output on J2.3", "t_rise_ns": ENC_EDGE,
                        "source": f"assumption: as ENC_A_IN", "victim": False,
                        "slowed_by": ([f"{b['enc_pu'][1]} pull-up (rise only, open-collector encoders)"] if b.get("enc_pu") else [])},
        b["ENC_A"]: {"driver": f"ENC_A_IN through {b['enc_r'][0]} 1k", "t_rise_ns": enc_hdr,
                     "source": f"{b['enc_r'][0]} 1k into the header-side load (~{LOAD_PF} pF ribbon + MCU input): 2.2 RC = {enc_series_ns:g} ns, "
                               f"root-sum-square with the {ENC_EDGE} ns source edge", "victim": False, "slowed_by": [f"{b['enc_r'][0]} 1k series"]},
        b["ENC_B"]: {"driver": f"ENC_B_IN through {b['enc_r'][1]} 1k", "t_rise_ns": enc_hdr, "source": "as ENC_A", "victim": False,
                     "slowed_by": [f"{b['enc_r'][1]} 1k series"]},
        b["MOTOR_A"]: {"driver": "U2.8 OUT1 (DRV8874)", "t_rise_ns": 150, "source": "DRV8874 datasheet tRISE/tFALL 150 ns (OUTx 10-90 %, VM 24 V)",
                       "victim": False, "note": "2 A edges: the magnetic aggressor for the sense nets (victim spacing), not a fast one"},
        b["MOTOR_B"]: {"driver": "U2.10 OUT2 (DRV8874)", "t_rise_ns": 150, "source": "DRV8874 datasheet tRISE/tFALL 150 ns (OUTx 10-90 %, VM 24 V)",
                       "victim": False, "note": "as MOTOR_A"},
        b["nFAULT"]: {"driver": f"U2.4 open-drain (fall); {b['nfault_pu']} 10k pull-up to 3V3 (rise)", "t_rise_ns": NFAULT_FALL,
                      "source": f"assumption: no nFAULT edge spec in the DRV8874 datasheet; open-drain pull-down into ~20 pF taken as {NFAULT_FALL} ns; "
                                f"the rise is {b['nfault_pu']} x ~20 pF ~ 0.4 us", "victim": False, "slowed_by": [f"{b['nfault_pu']} 10k pull-up (rise only)"]},
        b["LED_FAULT"]: {"driver": f"nFAULT through the fault LED {b['led_fault'][0]} (cathode on nFAULT); {b['led_fault'][1]} from 3V3", "t_rise_ns": NFAULT_FALL,
                         "source": "follows nFAULT's fall through the LED (series part)", "victim": False},
        b["LED_PWR"]: {"driver": f"5V through {b['led_pwr']} (DC)", "t_rise_ns": None, "source": "DC", "victim": False},
        b["IPROPI"]: {"driver": f"U2.6 IPROPI current mirror into {b['ipropi_r']} 2.74k", "t_rise_ns": 150,
                      "source": "the mirror follows the bridge current, which steps at the OUTx edge (tRISE 150 ns); weak aggressor (IIPROPI <= 3 mA)",
                      "victim": True, "note": "analog, 2.74k source impedance, ~1.2 V/A; noise here is current-regulation error"},
        b["ISENSE"]: {"driver": f"IPROPI through {b['isense_rc'][0]} 1k / {b['isense_rc'][1]} {b['isense_rc'][2]}", "t_rise_ns": b["isense_t"],
                      "source": f"RC {b['isense_rc'][3]}, 2.2 RC", "victim": True, "slowed_by": [f"{b['isense_rc'][0]} 1k + {b['isense_rc'][1]} {b['isense_rc'][2]}"],
                      "note": "ADC line to the header; high impedance"},
        b["VSENSE"]: {"driver": f"5V through the feedback divider {b['fb']} (DC)", "t_rise_ns": None, "source": "DC feedback node", "victim": True,
                      "note": "error-amplifier input, ~8 k source impedance; noise here is duty-cycle noise"},
        b["COMP"]: {"driver": "U1.8 COMP error-amplifier output", "t_rise_ns": None, "source": "compensation node, bandwidth about the crossover (tens of kHz)",
                    "victim": True},
        b["COMP_RC"]: {"driver": f"COMP through {b['comp_r']}", "t_rise_ns": None, "source": "as COMP", "victim": True},
        b["RT"]: {"driver": f"U1.1 RT/CLK bias through {b['rt_r']} (DC)", "t_rise_ns": None, "source": "DC; the resistor sets fsw", "victim": True,
                  "note": "high-impedance node; pickup here is frequency jitter"},
        b["SS"]: {"driver": f"U1.9 SS into {b['ss_c']} (slow ramp)", "t_rise_ns": None, "source": "soft-start ramp, milliseconds", "victim": True,
                  "note": "mild victim: matters at start-up only"},
        b["CPH"]: {"driver": f"U2.13 CPH charge-pump switch into {b['fly_c']} 22 nF", "t_rise_ns": 2000,
                   "source": "no edge spec; slew bound by I/C: tens of mA into 22 nF over ~5 V is >= 2 us; fVCP 400 kHz (datasheet)", "victim": False},
        b["CPL"]: {"driver": f"U2.14 CPL charge-pump switch into {b['fly_c']} 22 nF", "t_rise_ns": 2000, "source": "as CPH", "victim": False},
        b["VCP"]: {"driver": f"U2.12 VCP charge-pump output into {b['vcp_c']} (VM + ~5 V)", "t_rise_ns": None, "source": "DC with 400 kHz ripple", "victim": False},
        b["GATE"]: {"driver": f"Q1.4 gate: {b['gate_r']} 100k to GND" + (f", {b['gate_z']} zener clamp" if b.get("gate_z") else "") + " (DC)",
                    "t_rise_ns": None, "source": "DC", "victim": False},
    }
    for net, extra in b.get("extra", {}).items():
        e[net] = extra
    return e


BOARDS = {
    "rung2-zener-a2-opus": dict(
        SW="SW", BOOT="BOOT", PWM="PWM", DIR="DIR", nSLEEP="nSLEEP", ENC_A_IN="ENC_A_IN", ENC_B_IN="ENC_B_IN", ENC_A="ENC_A", ENC_B="ENC_B",
        MOTOR_A="MOTOR_A", MOTOR_B="MOTOR_B", nFAULT="nFAULT", LED_FAULT="LED_FAULT", LED_PWR="LED_PWR", IPROPI="IPROPI", ISENSE="ISENSE",
        VSENSE="VSENSE", COMP="COMP", COMP_RC="COMP_RC", RT="RT", SS="SS", CPH="CPH", CPL="CPL", VCP="VCP", GATE="Q1_GATE",
        boot_cap="C4 100 nF", enc_pu=("R5 10k", "R6 10k"), enc_r=("R7", "R8"), nfault_pu="R12", led_fault=("D2", "R13 1k"), led_pwr="R9 1k",
        ipropi_r="R10", isense_rc=("R11", "C14", "100 nF", "100 us"), isense_t=220000, fb="R1 52.3k / R2 10k", comp_r="R3 2.2k", rt_r="R4 68.1k",
        ss_c="C9 10 nF", fly_c="C13", vcp_c="C12 100 nF", gate_r="R14", gate_z="D3",
    ),
    "rung2-zener-a1-opus": dict(
        SW="SW", BOOT="buck.BUCK_BOOT", PWM="PWM", DIR="DIR", nSLEEP="nSLEEP", ENC_A_IN="connectors.ENC_A_IN", ENC_B_IN="connectors.ENC_B_IN",
        ENC_A="ENC_A", ENC_B="ENC_B", MOTOR_A="MOTOR_A", MOTOR_B="MOTOR_B", nFAULT="nFAULT", LED_FAULT="driver.FAULT_LED_A", LED_PWR="buck.PWR_LED_A",
        IPROPI="IPROPI", ISENSE="ISENSE", VSENSE="buck.BUCK_FB", COMP="buck.BUCK_COMP", COMP_RC="buck.BUCK_COMPZ", RT="buck.BUCK_RT", SS="buck.BUCK_SS",
        CPH="driver.DRV_CPH", CPL="driver.DRV_CPL", VCP="driver.DRV_VCP", GATE="power_in.Q1_GATE",
        boot_cap="C5 100 nF", enc_pu=("R8 10k", "R9 10k"), enc_r=("R10", "R11"), nfault_pu="R16", led_fault=("D3", "R18 1k"), led_pwr="R7 1k",
        ipropi_r="R14", isense_rc=("R17", "C14", "10 nF", "10 us"), isense_t=22000, fb="R4 53.6k / R5 10k", comp_r="R6 2.37k", rt_r="R3 30.1k",
        ss_c="C4 10 nF", fly_c="C13", vcp_c="C12 100 nF", gate_r="R19", gate_z=None,
        extra={
            "buck.BUCK_EN": {"driver": "VIN through R1 102k / R2 30.1k (UVLO divider, DC)", "t_rise_ns": None, "source": "DC", "victim": True,
                             "note": "mild victim: 23 k node sets the UVLO threshold"},
            "driver.DRV_VREF": {"driver": "3V3 through R12 1k / R13 10k (DC)", "t_rise_ns": None, "source": "DC", "victim": True,
                                "note": "sets the current-regulation threshold"},
            "driver.DRV_IMODE": {"driver": "R15 20k to GND (DC config pin)", "t_rise_ns": None, "source": "DC", "victim": False},
        },
    ),
    "rung2-zener-a1-sonnet": dict(
        SW="SW", BOOT="buck.BOOT", PWM="PWM", DIR="DIR", nSLEEP="nSLEEP", ENC_A_IN="connectors.ENC_A_J", ENC_B_IN="connectors.ENC_B_J",
        ENC_A="ENC_A", ENC_B="ENC_B", MOTOR_A="MOTOR_A", MOTOR_B="MOTOR_B", nFAULT="nFAULT", LED_FAULT="LED_FLT_A", LED_PWR="LED_PWR_A",
        IPROPI="IPROPI", ISENSE="ISENSE", VSENSE="buck.FB", COMP="buck.COMP", COMP_RC="buck.COMP_R", RT="buck.RT", SS="buck.SS",
        CPH="driver.CPH", CPL="driver.CPL", VCP="driver.VCP", GATE="power_in.GATE",
        boot_cap="C1 100 nF", enc_pu=None, enc_r=("R7", "R8"), nfault_pu="R9", led_fault=("D1", "R1 470"), led_pwr="R2 1k",
        ipropi_r="R10", isense_rc=("R11", "C12", "100 nF", "100 us"), isense_t=220000, fb="R5 52.3k / R4 10k", comp_r="R3 1.37k", rt_r="R6 100k",
        ss_c="C10 10 nF", fly_c="C11", vcp_c="C13 100 nF", gate_r="R12", gate_z=None,
        extra={
            "VIN_EXT": {"rail": True, "driver": "J4 input before Q1 (ideal diode)", "source": "rail: judged by irdrop and currents"},
        },
    ),
}


def main():
    pr = "--print" in sys.argv
    for board, b in BOARDS.items():
        d = ROOT / "examples" / board
        cfg_path = d / "checks.json"
        raw = open(cfg_path).read()
        cfg = json.loads(raw)
        cfg["signals"] = entries(b)
        if not pr:
            # keep the file's own indent and trailing newline so the diff is the block alone
            ind = len(raw.split("\n")[1]) - len(raw.split("\n")[1].lstrip(" "))
            open(cfg_path, "w").write(json.dumps(cfg, indent=ind or 2) + ("\n" if raw.endswith("\n") else ""))
            src = cfg_path
        else:
            src = Path("/tmp") / f"signals-{board}.json"
            json.dump(cfg, open(src, "w"))
        xml = next((d / "board").glob("*.xml"))
        print(f"== {board}")
        p = subprocess.run([str(PCB), "signals", str(src), "--netlist", str(xml), "--md"], capture_output=True, text=True)
        print(p.stdout, p.stderr)


if __name__ == "__main__":
    main()
