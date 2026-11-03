#!/bin/sh
# Rebuilds docs/img/{hero.gif,route.gif,motor-iso.png,qwiic-iso.png,results.png} from the archived boards.
# Needs kicad-cli, ffmpeg, gifsicle, pdftoppm, the .venv (matplotlib, Pillow) and KiCadRoutingTools under /tmp/pcb-ref.
set -e
R=$(cd "$(dirname "$0")/../.." && pwd); S=$R/skills/kicad-design/scripts; K=/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli
F=/Users/alxchunlin/code-stuff/alex-style-guide/fonts; T=${TMPDIR:-/tmp}/pcb-readme-img; rm -rf "${T:?}"; mkdir -p "$T/spin" "$T/route"
MOTOR=$R/examples/rung2-zener-a2-opus/board/motor1.kicad_pcb; QWIIC=$R/examples/rung1-zener-a2-sonnet/board/qwiic_imu.kicad_pcb

# stills
$K pcb render --side top --width 1400 --height 900 --quality high --background opaque --floor --perspective --zoom 0.85 --rotate "-35,0,30" -o $R/docs/img/motor-iso.png $MOTOR
$K pcb render --side top --width 1200 --height 800 --quality high --background opaque --floor --perspective --zoom 0.7 --rotate "-35,0,30" -o $R/docs/img/qwiic-iso.png $QWIIC

# turntable
for i in $(seq 0 35); do $K pcb render --side top --width 800 --height 520 --quality high --background opaque --floor --perspective --zoom 0.95 --rotate "-35,0,$((i*10))" -o $T/spin/f$(printf %02d $i).png $MOTOR >/dev/null; done
ffmpeg -y -loglevel error -framerate 12 -i $T/spin/f%02d.png -vf "fps=10,scale=640:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4" $T/spin.gif
gifsicle -O3 --lossy=60 -o $R/docs/img/hero.gif $T/spin.gif

# routing demo: strip the designer's copper, route it, show F.Cu and B.Cu without the pours
cp $MOTOR ${MOTOR%.kicad_pcb}.kicad_pro $T/route/; cd $T/route
$S/pcb route strip motor1.kicad_pcb --out placed.kicad_pcb
$S/pcb route auto placed.kicad_pcb --engine krt --out routed.kicad_pcb --pack jlcpcb --work $T/route/work || true   # exit 1 unless clean; route.json has the verdict
for n in placed routed; do
  $S/pcb py $R/tools/readme/nozones.py $PWD/$n.kicad_pcb $PWD/${n}_nz.kicad_pcb
  $K pcb export pdf --layers "F.Cu,B.Cu,Edge.Cuts" --erd --ev --mode-single --scale 0 --bg-color "#141516" -o $PWD/${n}_nz.pdf ${n}_nz.kicad_pcb
  pdftoppm -png -r 110 -singlefile ${n}_nz.pdf ${n}_nz
done
$R/.venv/bin/python3 - "$F" <<'PY'
import sys, json
from PIL import Image, ImageDraw, ImageFont
F = sys.argv[1] + "/"
r = json.load(open("route.json")); fin = r["final"]
f1 = ImageFont.truetype(F + "RobotoCondensed-700.ttf", 30); f2 = ImageFont.truetype(F + "RobotoMono-500.ttf", 22)
def cap(src, dst, t1, t2):
    im = Image.open(src).convert("RGB"); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, im.width, 96], fill=(20, 21, 22))
    d.text((40, 16), t1, font=f1, fill=(232, 232, 232)); d.text((40, 58), t2, font=f2, fill=(160, 160, 160))
    im.save(dst)
cap("placed_nz.png", "frame_a.png", "PLACED BY THE DESIGNER, COPPER STRIPPED", f"{r['start']['airwires']} airwires, pours hidden in this view")
verdict = "CLEAN" if r["clean"] else "NOT CLEAN: " + ", ".join(f"{v} {k}" for k, v in fin["new_errors"].items()) + ", handed to the designer"
cap("routed_nz.png", "frame_b.png", f"pcb route auto, {r['wall_s']} s", f"{fin['airwires']} airwires, {fin['vias']} vias, verdict {verdict}")
PY
ffmpeg -y -loglevel error -loop 1 -t 2.5 -i frame_a.png -loop 1 -t 4 -i frame_b.png -filter_complex "[0][1]concat=n=2:v=1:a=0,fps=2,scale=900:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=64[p];[s1][p]paletteuse=dither=none" route.gif
gifsicle -O3 -o $R/docs/img/route.gif route.gif

# results chart
cd $R && .venv/bin/python3 tools/readme/results_chart.py
ls -la $R/docs/img
