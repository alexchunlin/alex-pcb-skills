# Board brief: INA745B 35 A digital power monitor

Read `BRIEF-common.md` first. Part: TI INA745BIRELR, VQFN-14 3 x 5 mm, 0.6 mm pitch, LCSC C35213810 (13,165 in stock on 2026-11-04; re-check). No shunt to choose: the sense element is
in the package. Datasheet: https://www.ti.com/lit/ds/symlink/ina745b.pdf . Near products on the market are the INA228 and INA238 breakouts, with an external shunt.

- **Function:** high-side or low-side power and energy monitor over I2C, bus up to 40 V. Qwiic, header, alert pin on the header, A0/A1 address straps on solder jumpers giving at least four addresses.
- **Current path:** this board's point. IS+ and IS- sit on the package's short edges, so the current funnels into a 3 mm edge past 0.6 mm signal pads. Two screw terminals or large plated pads on opposite edges, the path between them as pours on as many layers as the calculation asks. This overrides the common stackup: the high-current path may cut the outer ground fill, and the inner planes may give way under it if the calculation needs them, with the reason in the log. The part senses internally, so no Kelvin tracks are needed, but the signal pads and their tracks must stay clear of the current path's heat and field.
- **Rating:** state the board's continuous current rating from your own numbers (track and pour temperature rise, via count, terminal rating, the datasheet's current-vs-temperature limit), not the part's headline 35 A. Run `pcb irdrop` on the path. 2 oz outer copper is allowed if you use the matching rule pack.
- **Size:** up to 40 x 25.4 mm if the terminals need it.
- **Logic:** VS at 3.3 V from the Qwiic or header rail. If bus voltage reaches 40 V, spell out the creepage between the bus copper and the logic side for that voltage.
