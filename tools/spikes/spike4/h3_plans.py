"""Spike #4 (H3): agent-written guide corridors on the Opus attempt-2 placement (plan_bench base, Alex's stackup).

  python3 -I tools/spikes/spike4/h3_plans.py RULES.json OUT_DIR     writes opus2-split, -guided and -guided1 .json

Both plans keep the rules plan's feeds and thermal vias and split its power wave into one wave per guided net (VIN,
5V, MOTOR_A, MOTOR_B; KRT's --guide-corridor takes one waypoint list per run), then the rest of the power wave
(VIN_RAW), sense and rest as in the rules plan. `split` has no guides (the control for the wave split itself), `guided`
draws the corridors below, written by reading the pad positions of the archived placement (pcb q pads), the way a
designer would sketch them: VIN from Q1's source pins up between Q1 and the input caps, one branch west to the DRV8874's
VM pin, one east past C2/C1 to the buck's PVIN; 5V from L1 down along the output caps to the LDO, and up the right side
to J3.1; the motor outputs straight west from U2 to J1.
"""
import json, sys
from pathlib import Path

GUIDES = {
    "VIN": [[[123.0, 123.9], [122.0, 119.8], [118.6, 117.4], [118.0, 115.2]],
            [[123.0, 123.9], [125.6, 119.8], [128.5, 118.4], [129.8, 117.5]]],
    "5V": [[[135.5, 126.5], [135.5, 128.9], [131.0, 128.9], [130.6, 133.0], [131.3, 137.8]],
           [[135.5, 126.5], [137.6, 125.0], [140.2, 121.0], [143.2, 117.3]]],
    "MOTOR_A": [[[116.7, 109.1], [111.0, 109.6], [105.6, 110.3]]],
    "MOTOR_B": [[[117.4, 114.9], [111.0, 114.3], [105.6, 113.8]]],
}


# a second sketch with one chain per net (KRT concatenates every polyline on User.1 into one waypoint list, so two chains
# from Q1 make the list jump back), and a 900 s wave timeout: the two-chain VIN and 5V waves both hit the 300 s limit
GUIDES_1 = {
    "VIN": [[[118.0, 115.2], [118.6, 117.4], [122.0, 119.8], [123.0, 123.9], [125.6, 119.8], [128.5, 118.4], [129.8, 117.5]]],
    "5V": [[[143.2, 117.3], [140.2, 121.0], [137.6, 125.0], [135.5, 126.5], [135.5, 128.9], [131.0, 128.9], [130.6, 133.0], [131.3, 137.8]]],
    "MOTOR_A": GUIDES["MOTOR_A"], "MOTOR_B": GUIDES["MOTOR_B"],
}


def main():
    rules = json.load(open(sys.argv[1]))
    out = Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    power = next(w for w in rules["waves"] if w["name"] == "power")
    rest_power = [n for n in power["nets"] if n not in GUIDES]
    for name, guides, extra in (("split", None, {}), ("guided", GUIDES, {}), ("guided1", GUIDES_1, {"timeout_s": 900})):
        waves = [{"name": n.lower(), "nets": [n], **({"guides": guides[n]} if guides else {}), **extra} for n in GUIDES]
        if rest_power:
            waves.append({**power, "nets": rest_power})
        waves += [w for w in rules["waves"] if w["name"] != "power"]
        json.dump({**rules, "waves": waves}, open(out / f"opus2-{name}.json", "w"), indent=1)
        print(out / f"opus2-{name}.json")


if __name__ == "__main__":
    main()
