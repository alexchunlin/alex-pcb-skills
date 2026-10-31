# No way to express a PWR_FLAG: every `Component()` needs a footprint, so ERC reports `power_pin_not_driven`

**Version** pcb 0.4.95, KiCad 10.0.1.

**What happens** A board powered through a connector (Qwiic: 3V3 and GND arrive on passive connector pins) has
no `power_out` pin on its rails, so ERC reports `power_pin_not_driven` on every `power_in` pin (2 errors on the
rung-1 board). KiCad's answer is a `PWR_FLAG` symbol on each rail. In Zener a `Component()` without a footprint
is rejected, and a PWR_FLAG symbol with a footprint-less `power_out` pin aborts the schematic exporter
("visible terminal belongs to 0 islands").

**Expected** A `PowerFlag(net)` (or `Net(..., power_source=True)`) that places a PWR_FLAG on the schematic and
nothing on the board; or `Component(footprint=None)` allowed for symbols KiCad treats as virtual.

**Workaround** Designers typed a test-point pin `power_out` (which leaves a `pin_to_pin` warning against any
bidirectional pin on the same net), or a post-processor adds a PWR_FLAG plus global label per net ERC lists as
undriven.
