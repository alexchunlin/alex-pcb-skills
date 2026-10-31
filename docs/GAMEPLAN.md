# alex-pcb-skills: game plan

Agent-driven KiCad PCB design with a goal, a feedback loop, guardrails and a benchmark. The shape is
`~/code-stuff/alex-3d-skills` (design skill + review skill + resumable loop + replay bench + evidence log), ported
to electronics. Written 2026-10-31 at the start of the repo.

## 1. What transfers from alex-3d-skills, and what is different

The 3D repo was built by **harvesting a live loop**: run designer/reviewer agents on a real brief with no tools, log
every time sink and foot-gun with an ID (`A1-T3`), then build only the tools the evidence asks for, and gate each
tool with a replay bench (recall of reviewer findings up, false fails not up). Keep that method exactly.

| 3D | PCB equivalent | Status on this machine |
|---|---|---|
| headless Blender, 0.7 s start | `kicad-cli` 10.0.1 + bundled Python 3.9 with `pcbnew` | ERC 3 s, DRC with parity 17 s, 3D render 2 s, schematic SVG 1.5 s on the Plink board |
| `cadcheck` (built from scratch) | ERC + DRC exist already; **`pcbcheck` for intent** is the new piece | none yet |
| `cad q` one-shot measurements | `pcb q`: net width/length, pad-to-pad distance, decoupling distance, copper area, pin map | none yet |
| checks.json declares design intent | checks.json: rails, currents, buses, pin maps, keepouts, bring-up test points | none yet |
| STL contact sheet, renders | board renders per side, per-sheet schematic SVG, ibom | kicad-cli does all three |
| components.json (purchased parts) | parts library with LCSC/MPN, footprints, verified pinouts | pace-racer already has `specific-parts/` and the easyeda2kicad flow |
| reviewer rubric, 3 metrics | rubric: Electrical correctness, Manufacturability (fab + assembly + bring-up), Documentation/intent | none yet |
| replay bench against reviewer labels | replay bench against **real fab bugs** (below) plus planted bugs | labels exist in the two repos' history |

Differences that change the design:
- **Syntax checks exist, intent checks don't.** ERC/DRC are free and fast, but every real bug found in the two
  reference repos was invisible to them: Plink's IMU I2C address mismatch, missing back-power Schottky, unreadable
  silkscreen (commit 2179d08, 2024-11-11); Pace's ground-domain and shunt net-tie questions (decisions 0001-0003);
  Pace's errata (unspecified pin types, drifted library symbols, thin pour necks). ERC on the shipped Plink reports
  177 violations, 9 of them errors, so the raw count is noise, not signal. pcbcheck has to turn the brief into rows
  the same way cadcheck turned "removable" into a `slide_out` sweep.
- **Schematic entry is the hard interface.** Agents write code well and place 2D symbols badly. The 3D loop learned
  the same (one 84 KB script in one generation, 5.4 min). The schematic has to be authored netlist-first from code
  (one module per sheet, like `parts/<subsystem>.py`), with the drawn schematic as a generated view. Which library
  does that for KiCad 10 is decided in section 3.
- **Layout is a search problem with real tools.** Placement via `pcbnew` Python with constraints, routing via
  freerouting headless, and the agent fixes DRC. Humans keep veto on placement in the first runs.
- **Physics is cheap to compute and agents skip it.** Trace width vs current, copper pour thermal, LDO dissipation,
  buck component values (Plink's `WBOperatingValuesDesign4.csv` is a hand-exported WEBENCH run), I2C pull-up vs bus
  capacitance. These are the "minute granular calcs" to take off the engineer: each becomes a check row with a
  formula and a datasheet-cited limit, not prose.
- **Buy design margin so the agent's layout problem is deterministic.** Alex's position (2026-10-31): assembly, not
  FR4, drives board cost, so pay for layers (4, 6, maybe 8) and get routability instead of asking the model to solve a
  cramped board. The literature supports the premise that agents fail hardest at dense routing (OmniRouting 12.6% of
  nets zero-shot vs 93.6% human; PCB Gym 32% DRC-clean; PCBWorld 0.00 clean pass on medium boards). The plan adopts
  the principle as a guardrail called **design margin**, with layers as one of four knobs, and tests the layer knob
  in phase 6 rather than defaulting to 6 or 8. Arguments against "more layers by default", so the test is honest:
  1. Routing difficulty is mostly placement and pin escape, not layer count. Layers hide a bad floor plan instead of
     fixing it (long traces, poor return paths), and placement is where every benchmark shows agents weakest.
  2. Layers move the complexity from geometry, where DRC catches mistakes, to electrical topology, where it does
     not: layer assignment, return paths across plane splits, stitching, stackup symmetry. Those are exactly the
     "electrically sound" questions the loop wants certainty on, and they are quieter failures.
  3. Freerouting is headless and fast, and its failure modes (DSN rule loss, edge clearance, 25% non-clean) are not
     layer-bound. The loop's wall time and tokens go to schematic correctness and placement, so layers relieve the
     cheapest part of the problem.
  4. For QFN and 0603 boards like Plink (65 x 56 mm, 4 layers, routed by one person) 6 or 8 layers buys little; the
     gain is real for BGA escape, several isolated domains or controlled impedance.
  5. Motor-driver current wants copper weight and plane area, not inner layers at 0.5 oz.
  6. Buried signals are harder to probe at bring-up and harder for a human to review, and bring-up is where the
     loop learns. Planes inside, signals outside keeps both.
  7. Cost: at prototype quantity the layer delta is small and the premise holds; at volume the FR4 share stays while
     assembly per unit falls, and 6/8-layer stock stackups add lead time and limit impedance options.
  So: default **4 layers with a strict plane policy** (every signal layer adjacent to a solid reference plane, power
  on a plane or wide pour, plane layers carry no signal, via budget per net class), escalate to 6 on declared triggers
  (BGA or 0.4 mm pitch escape, 3 or more isolated domains, controlled impedance, a floor-plan congestion metric over a
  threshold), 8 only on a trigger plus a reviewer's reason. The other three margin knobs come first because they are
  cheaper and DRC-visible: board area (when mechanical allows), passive size (0603 over 0402), and clearances and
  widths well above the fab minimum. All four are declared in checks.json and enforced by pcbcheck; the fab rule pack
  is per stackup.
- **Two edit-safety rules the 3D loop never needed:** never script-edit a file KiCad has open (it rewrites from memory
  on save, Pace style guide), and every scripted schematic edit is gated by a netlist connectivity diff
  (`tools/verify_netlist.py` in pace-racer, which this repo adopts as prior art).

## 2. Target architecture

```
skills/
  kicad-design/            SKILL.md, reference/ (checks-config.md, footguns.md, calcs.md, fab-rules.md),
                           scripts/pcb (wrapper), pcbcheck.py, pcbq.py, pcblib/ (schematic-from-code, placement
                           helpers, fab exports), templates/project/
  pcb-design-review/       SKILL.md, checklist.md, rubric.md
templates/pcb-loop.workflow.js    plan -> build per sheet -> layout -> finish -> review, resumable, models per role
components/                parts.json with LCSC/MPN/pinout source, verified footprints
tools/bench/               replay.py, labels.json, corpus.json, cost telemetry (reuse alex-3d tools/transcript)
tools/verify_all.sh        re-proves every tool (the --changed selector is worth copying as is)
docs/FINDINGS.md           evidence log; every rule points at an ID
examples/                  archived attempts and the reference boards with labels
```

The loop (one attempt):
1. **Plan** (one agent, 10 min cap): brief -> block diagram, rails and budgets, bus map, connector pin map,
   per-sheet checks.json rows, progress.md. Nothing modelled until this is on disk.
2. **Build, one agent per sheet** (fresh context each): write `sheets/<name>.py`, generate the sheet, run ERC on the
   project, run `pcbcheck --only <sheet>`, fix every fail, append to progress.md.
3. **Layout** (one agent, or human-assisted in early runs): placement from the plan's floor plan, net classes from
   checks.json, autoroute, DRC with parity to zero errors, pcbcheck layout rows (widths, decoupling distance,
   creepage, silk).
4. **Finish**: renders, BOM with sourcing, fab package, bring-up checklist generated from test points, design log.
5. **Review** (independent agent, pcb-design-review): re-runs ERC/DRC/pcbcheck on a copy, audits every `accept`
   entry, measures with `pcb q`, scores against anchors, ranks issues with evidence and a fix.

Guardrails (mechanical, not prose):
- checks.json is the contract: every rail, current, bus, connector and test point is declared, and pcbcheck fails
  anything undeclared it finds (cadcheck's rule).
- Netlist diff gate on every scripted edit; KiCad-closed guard before any write.
- Fab rule set pinned per fab and stackup (JLC 4-layer first, 6 and 8 on trigger, 2-layer only for breakouts) as a
  `.kicad_dru` plus pcbcheck rows, and the design-margin policy above (planes, area, passive size, clearance) as rows.
- Reviewer scores only against anchors with measured numbers; "looks fine in the render" is a lead, not a finding.
- Resumable: every agent appends to progress.md; the loop resumes from attempt N.

## 3. Prior art to reuse vs build

Survey run 2026-10-31 (four sub-surveys, every claim fetched; the long form with URLs is `docs/SURVEY-2026-10-31.md`).
The decisive facts:

- **KiCad 10 has no headless edit API.** The IPC API needs the GUI open and has no schematic commands in 10; headless
  `kicad-cli api-server` and schematic IPC land in KiCad 11. SWIG `pcbnew` still works in 10 under the bundled
  Python 3.9 and is removed in 11. So every headless PCB write today is SWIG or direct `.kicad_pcb` text, and every
  schematic write is file-level. `pcblib` wraps that behind one interface so the KiCad 11 swap is one module.
- **Code-first schematic generation beats file generation by a wide margin.** Microsoft's SchGen measured 82% valid
  (ERC-passing) schematics from Python-on-KiCad-API code vs 10.5% from raw `.kicad_sch` generation. The 3D loop found
  the same thing for geometry. Agents write modules; the drawing is a generated view.
- **No fab exposes a DFM API** (JLC, PCBWay, Eurocircuits, OSH Park are all upload-and-click). Fab limits go in as
  `.kicad_dru` rule packs; `kicad-druid` already ships JLC/PCBWay packs per stackup. A rejected rule file makes
  `kicad-cli pcb drc` exit 0 with no output, so every DRC run carries a sentinel rule that must fire.
- **No public benchmark covers spec to KiCad schematic plus PCB with ERC, DRC and fab rules.** The nearest, EDA Bench
  (35 reconstruction tasks, ERC+DRC+ngspice oracle), tops out at 4.58%; PCBInnoBench (372 KiCad modification tasks) at
  22% with guidance. Layout agents are weak everywhere: PCB Gym 32% DRC-clean routed, OmniRouting 12.6% of nets
  zero-shot vs 93.6% human. The replay bench in section 4 is new ground, and the design bench should publish its tasks.
- **Routing is solved enough; placement is not.** freerouting v2.5.0 has native macOS binaries, a CLI, REST and MCP,
  and routes 75% of a 1,157-board corpus clean. KiCadRoutingTools (A*, reads/writes `.kicad_pcb`, macOS binaries,
  ships Claude skills) avoids the DSN round trip. Open-source placement is small annealers with no external
  benchmark; Quilter has no API, DeepPCB's is login-gated. Placement stays agent-planned plus human veto.

| Need | Reuse | Why not build |
|---|---|---|
| ERC, DRC, netlist, BOM, renders, fab exports | `kicad-cli` 10 (`--format json`, `--exit-code-violations`, `pcb export stats`), `.kicad_jobset` for the fab bundle | all headless, 1-17 s |
| Schematic from code | **bake-off in phase 0**: Diode `pcb`/Zener (KiCad-10 `.kicad_sch` and `.kicad_pcb`, `pcb layout`, `pcb route` via freerouting, `pcb sim` ngspice, JLC DFM pack, ships agent skills, MIT, v0.4.95 on 2026-10-29) vs SKiDL 3.0 (Python, KiCad 5-10 netlists, mature, weaker drawing) | atopile's CLI is in maintenance mode and moving to a hosted app; tscircuit stamps KiCad 9 format; kiutils/kicad-skip/kicad-sch-api are stale or have open corruption issues on KiCad 10 files |
| PCB read/write headless | SWIG `pcbnew` under KiCad's Python 3.9 now; `kipy` + `kicad-cli api-server` when KiCad 11 ships | `pcblib` is the only place that knows which |
| Fab rules | `kicad-druid` `.kicad_dru` packs (JLC/PCBWay, 2L-1oz to 6L) plus a sentinel rule; `kct check --mfr jlcpcb` as a second opinion | encodes the same tables we would type |
| Routing | freerouting 2.5.0 native binary via SWIG `ExportSpecctraDSN`/`ImportSpecctraSES`; KiCadRoutingTools as the no-DSN alternative | both measured on public corpora |
| Netlist diff gate | pace-racer `tools/verify_netlist.py` (connectivity as sets of (ref, pin)); `kigit` for git-revision semantic diff | 20 lines, already proven |
| Intent checks | **build `pcbcheck`.** Prior art to read first: `netspec` (pre-alpha contract checks: `net()`, `polarity()`, `forbid()`), `kicad-sch-lint` (19 readability checks, KiCad 10), `designguard` (decoupling, pull-up, IPC-2221 width heuristics), PCBSchemaGen's 5-layer structural verifier (MIT) | nothing mature checks decoupling distance, pull-ups, power tree, pin maps or bring-up coverage headless; all three are under 10 commits or 0.1.x |
| Placement | agent floor plan + `pcbnew` moves + KiCadRoutingTools `place_simple` / `kct optimize-placement` for triage | no open placer has an external benchmark; measure before trusting |
| SPICE | `kicad-cli sch export netlist --format spice` then Homebrew `ngspice -b -r` and our own raw parser | no `kicad-cli sim`; PySpice is pinned to ngspice 34 (2021) |
| Calcs (width vs current, LDO dissipation, buck ripple, pull-up vs bus C) | build as `pcbcheck` rows with the formula and the datasheet limit in the row | the "minute granular calcs"; `lineforge` covers impedance if needed |
| CI | KiBot in Docker (`ghcr.io/inti-cmnb/kicad10_auto_full`, amd64), as pace-racer already does | not native on macOS; local runs use kicad-cli jobsets |
| Agent integration | skills + `pcb` wrapper, like `cad`. No MCP server of our own | the 3D loop runs on skills; the MCP field churns (Konnect went closed-source 2026-10-26, kicad-mcp dormant). `rjwalters/kicad-tools` (`kct`, 0.26.0, MIT) overlaps most with what this repo builds: measure it in phase 0 before writing any placement or DRC-fix code |
| Benchmark corpora | PCBWorld's 679 KiCad boards (BSD-3) for routing, `bshada/open-schematics` (CC-BY, `.kicad_sch` plus `.kicad_pcb` pairs) for the planted-bug set | more boards than we will ever draw |
| Parts sourcing | jlcparts-derived SQLite/CSV (CDFER, jlcsearch) with no key; easyeda2kicad or JLC2KiCadLib for geometry, then a KLC check and a pad-vs-datasheet row; Digi-Key v4 over `requests` if non-LCSC parts are in scope | official LCSC/JLC APIs are approval-gated; converters lag KiCad 10 formats and invent courtyards, so the check is the value, not the fetch |
| Transcript telemetry | `alex-3d-skills/tools/transcript/cc_transcript.py` | already measures time split, tokens, doc reads |

## 3b. What the research literature says (AI for PCB design, as of Oct 2026)

Papers and whitepapers worth reading before building, with what each found and the dead ends. URLs are in
`docs/SURVEY-2026-10-31.md`.

**Schematic generation works when it is code, not drawings.**
- SchGen (Microsoft, May 2026): fine-tuned model writing Python against the KiCad API gets 82% ERC-valid / 60.5%
  functionally correct schematics; GPT-5.2 raw `.kicad_sch` generation collapses to 10.5% valid. Dataset of 2,105
  KiCad schematics (SparkFun) is MIT on Hugging Face.
- PCBSchemaGen (NeurIPS 2026): SKiDL code from NL spec, 227 tasks, deterministic 5-layer structural verifier (ERC
  invariants, pin roles, IC templates, motif subgraph isomorphism, power rules); frontier models reach 94% pass@1 on
  the easy set, 79% on the open-schematics-derived set. The verifier is the prior art for pcbcheck's schematic rows.
- HWE-Bench (Mar 2026): spec plus datasheets to schematic, scored by static rules then LTspice. Best model 8.15%
  overall even though 78% pass the static checks: **the gap is dynamic behaviour, not connectivity.** Argues for
  SPICE rows on the analog parts of a design, not just netlist rows.
- pcbGPT (May 2026): Python DSL to KiCad schematics, 20 embedded/IoT tasks, pass@1 0.90. Same conclusion as SchGen.
- TopoScope (NeurIPS 2026): training-free multi-IC schematic agent; CircuitLM (Jan 2026): multi-agent to
  CircuitJSON, ERC pass 88% but judge pass 53%.

**Layout is where everything fails, and more so with density.**
- PCB Gym (NeurIPS 2026 workshop): joint placement+routing from a Zener schematic, DRC-gated; frontier LLMs produce a
  DRC-clean fully routed board on 32.1% of attempts.
- PCBWorld (Jul 2026, LG AI, code BSD-3): routing as a Gym env over KiCad's own push-and-shove engine, 679 real
  `.kicad_pcb` boards. GPT-5.4 interactive routing: 0.65 clean pass on small boards, **0.00 on medium**; a PPO agent
  trained on synthetic boards beats freerouting (0.86 vs 0.80) on small real boards.
- OmniLayout / OmniRouting (Jul-Aug 2026, EAGLE data, 1,681 boards): best zero-shot model routes 12.6% of nets vs
  93.6% human; agentic tool use lifts it to about 28%; a classical router (PcbRouter) does 56%. Placement: GPT-5.5
  few-shot 62.6% end-to-end pass; agentic Claude overlap 0.004.
- EDA Bench (ICML 2026 workshop): rebuild 35 open-hardware KiCad projects, graded by ERC + DRC + ngspice on external
  I/O behaviour: best harness 4.58% (built 21/35, failed most functional checks).
- PCBInnoBench (NeurIPS 2026): 372 modification tasks on real KiCad projects; 22% pass@1 with expert trajectory
  guidance, 7.3% without. **Guidance (a documented process) triples the pass rate**, which is this repo's thesis.
- freerouting v2.5.0 benchmark (Oct 2026): 1,157 boards, 75% clean, tier A 452/453 clean, tier C 49%.
- PCB-Bench (ICLR 2026): QA about placement/routing, not generation. OmniSch: schematic image to netlist, symbol IoU
  under 0.3%, so **vision of schematics is a dead end for now; read the netlist.**

**Dead ends and cautions the papers report themselves.**
- LLM-as-judge for schematics agrees with human raters at about zero kappa (MultModLM, Jun 2026). Reviewer scores
  need measured anchors, as the 3D rubric already does.
- Raw file generation of `.kicad_sch` (SchGen) and LLM-drawn traces (every MCP server's own README) violate rules; the
  telagod skill's rule "never hand-route" is the community consensus.
- Vision-based schematic understanding is far from usable (OmniSch).
- Dataset quality: Masala-CHAI's audit found a quarter of its netlists unusable; AMSbench's HF card holds 161 of a
  claimed 8,000 rows. Build labels from boards that were fabbed and fixed, not scraped sets.
- Vendor demos (GPT-6 Astra routing posts, EEBench run by atopile with held-out tasks, Quilter's blog) are not
  benchmarks; EEBench excludes layout entirely.

**Analog and IC-side work that transfers.** AnalogCoder (AAAI 2025: NL to PySpice with ngspice in the loop, 20/24),
LaMAGIC (power-converter topology, 96%), AnalogGenie (topology generation), NetlistBench (netlist editing), and the
IC physical-design agent benches (PDAGENT-BENCH 42%, CLOSER-Bench) all use the same shape: executable oracle, pass@k,
tool feedback loop. VerilogEval is the methodology template (fixed sampling, iverilog oracle).

**Surveys:** "Agentic EDA: A Handoff Perspective" (Jun 2026, 115 systems) and the LLM-for-EDA survey (Jan 2025).

**Public datasets for the corpus:** `bshada/open-schematics` (about 84k `.kicad_sch` with matching `.kicad_pcb`,
CC-BY-4.0, provenance stripped), `microsoft/SchGen_dataset` (MIT), PCBWorld D3 (679 KiCad 9 boards, DRV-free),
PCB-Bench task 3 (174 OSHWHub projects), PCBSchemaGen benchmarks (MIT), `symbench/spice-datasets`.

## 4. Benchmark

Three tiers, mirroring tools/bench in alex-3d-skills.

**Tier 1, replay bench (no LLM).** Archived boards with labels; a tool commit is scored by which labels its report
catches (`recall_fail`, `recall_fw`, severity-weighted), what it flags that no label covers (`false_fails`), and the
untriaged warn noise (`noise_warns`). The gate for a PR that adds a check: recall up, false fails and noise not up.
Corpus to start:
- `motorgo-plink` pre-rework (64e0b5d, built June 2024) and the v1.0 rework (fb32540) and the Nov 2024 fixes
  (2179d08): labels = IMU I2C address mismatch, missing back-power Schottky, silk readability, plus the 6 unconnected
  items and 40 copper-edge errors DRC reports today.
- `pace-racer` V0R1 (built) vs V1R2: labels from `docs/errata.md`, `docs/decisions/`, `docs/bringup.md`.
- Planted-bug variants (the slide-gate idea): take a clean board and plant swapped I2C pins, a missing pull-up, a
  reversed diode, a 0.2 mm trace on a 3 A net, a decoupling cap 15 mm from its pin, a connector pin map off by one.
  Known truth, so it is the regression suite for pcbcheck.
Labels carry `id`, `severity`, `tool_catchable`, `source` (commit or doc line) and a locator (`{check, objects,
kind}`), exactly the 3D schema, so `replay.py` ports with the Blender runner swapped for kicad-cli.

**Tier 2, design bench (LLM, the expensive one).** A ladder of briefs, each with a known-good reference and a
reviewer rubric. Scores: reviewer anchors, ERC/DRC errors, pcbcheck fails, labelled-bug recurrence (did the agent
re-make Plink's I2C mistake?), wall time and tokens per attempt.
- Rung 1: a Qwiic sensor breakout (one IC, one connector, 2-layer). Shakes out the loop in hours.
- Rung 2: one DRV8874 motor channel with current sense and a buck (power, thermal, net classes, 4-layer).
- Rung 3: re-derive MotorGo Plink from a brief written from its README (the mm-launcher analogue).
- Rung 4 (later): Pace Racer's inverter sheet, 48 V, gate driver, shunts, isolation.

**Design-margin experiment (phase 6).** Same rung-2 netlist at 4, 6 and 8 layers, and separately at +20% board area
and at 0603 vs 0402 passives, under the plane policy: freerouting and KiCadRoutingTools clean-route rate, DRC errors,
via count, total length, reviewer electrical score (return paths, plane splits), bring-up probe coverage, and JLC
quote at 5 and 50 units. Decides which margin knob the loop turns first and whether layers earn their default.

**Literature baselines to compare against.** PCBSchemaGen's verifier and tasks (MIT) can run as a side bench for the
schematic path; PCBWorld's 679 boards give routing numbers comparable to the published freerouting and PPO rows.

**Tier 3, cost telemetry.** `alex-3d-skills/tools/transcript/cc_transcript.py` already digests transcripts (time
split, long generations, tokens, doc reads). Reuse it; add `pcb` subcommand recognition.

## 5. Phases

| # | Phase | Deliverable | Done when |
|---|---|---|---|
| 0 | **Done 2026-10-31.** Harvest baseline + bake-off | Rung-1 and rung-2 briefs. A no-tools designer/reviewer loop on rung 1 with the plain Workflow tool, run twice: once writing Zener for Diode `pcb`, once writing SKiDL plus `pcbnew`. Also run `kct audit`, `kct check --mfr jlcpcb` and `kicad-druid` on both reference boards. `docs/FINDINGS.md` A1 | FINDINGS R1-S1 and R1-Z1: SKiDL 9/8/8 in 49 min, Zener 8/8/8 in 57 min; 9 of 12 findings shared; Zener chosen provisionally; 8 ranked tool candidates in FINDINGS "Rung 1 conclusion" |
| 1 | `pcb` wrapper + `pcb q` (2-3 days) | `erc`, `drc`, `netlist`, `render`, `svg`, `stats`, `diff` (netlist connectivity), `q` measurements over pcbnew | verify_all runs them on both reference boards |
| 2 | pcbcheck v0 + checks.json schema (1 week) | the first 10-12 rows, each citing a FINDINGS or reference-repo bug: i2c addresses and pull-ups, decoupling distance, width vs current, back-feed protection, connector pin map vs a declared table, polarity and pin-1 silk, test points vs bring-up list, mounting-hole keepout, net-class coverage, undeclared rails | replay bench recall on the Plink and Pace labels, with false fails listed and explained |
| 3 | Schematic-from-code path (1 week) | `pcblib` sheet modules on the path phase 0 picked, project template, netlist diff gate, KiCad-closed guard | rung-1 board built from a brief by an agent end to end, ERC 0 errors |
| 4 | Design skill + review skill (3-4 days) | SKILL.md with workflow and footguns, reference docs, rubric with anchors, checklist | a reviewer agent scores rung 1 with measured evidence only |
| 5 | Loop template (2 days) | `templates/pcb-loop.workflow.js`, resumable, models per role, parallel sheet builders | rung 2 runs unattended to review |
| 6 | Layout tooling (1-2 weeks) | placement helpers over `pcbnew` (groups, keepouts, floor plan from the plan), freerouting 2.5.0 and KiCadRoutingTools wrappers measured against each other on rung 2, DRC fix loop with the sentinel rule, `.kicad_jobset` fab bundle | rung 2 reaches DRC 0 errors and a fab zip without a human touching the board |
| 7 | Rung 3 and harvest (ongoing) | re-derive Plink; FINDINGS A2..An; bench deltas per tool PR | reviewer scores 9/9/9 or the open list says why not |

Phase 0 started 2026-10-31 (briefs in `bench/design/`, measurements in `docs/FINDINGS.md` P0-T1..T9). Phase 0 before any tool code is deliberate: the 3D repo's rules all point at evidence, and the tools it built
without evidence (the ones push-assist never called) were wasted.

## 6. Open decisions for Alex

1. Layer policy: 4 by default with 6/8 on triggers (my recommendation, section 1) or 6 by default (Alex's lean).
   The phase-6 experiment decides; until then pin JLC's 4- and 6-layer stock stackups.
2. Who owns layout in the first runs: agent-only, or agent placement with a human veto before routing.
3. Whether firmware pin maps are an input (a header file the check reads) or an output (generated from the netlist,
   as pace-racer's `gen_readme.py` does). Both is cheap; the direction of truth matters.
4. Parts sourcing: LCSC-only (JLC assembly) or Digikey/Mouser too. Decides which API keys the sourcing check needs.
5. **Decided 2026-10-31: code is the source of truth.** Zener/SKiDL modules regenerate the KiCad files; human edits go back into code, as the 3D repo does. Placement and routing live in the `.kicad_pcb` and must survive a schematic regeneration. Diode's `pcb import` is the way back for human-drawn boards.

## 7. Survey

Full sub-survey reports with URLs: `docs/SURVEY-2026-10-31.md` (tooling and libraries, MCP servers and routers, checks beyond ERC/DRC, benchmarks, sourcing).
