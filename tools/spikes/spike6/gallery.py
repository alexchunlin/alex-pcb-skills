#!/usr/bin/env python3
"""One contact sheet per board for a PR or issue: 3D top and bottom, then each copper layer.
  uv run --with matplotlib --with pillow python3 -I tools/spikes/spike6/gallery.py NAME BOARD.kicad_pcb OUT.png [TITLE]
"""
import os, subprocess, sys, tempfile
sys.path.insert(0, "/Users/alxchunlin/code-stuff/alex-style-guide/matplotlib")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import alex_style as ax
from PIL import Image

CLI = "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"


def sh(*a):
    r = subprocess.run(a, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def main():
    name, board, out = sys.argv[1:4]
    title = sys.argv[4] if len(sys.argv) > 4 else name
    d = tempfile.mkdtemp(prefix="gallery-")
    panels = []
    for side in ("top", "bottom"):
        f = os.path.join(d, side + ".png")
        sh(CLI, "pcb", "render", "--side", side, "--width", "1100", "--height", "900", "--zoom", "1.45", "--quality", "high", "--background", "opaque", "-o", f, board)
        panels.append((side.upper(), f))
    text = open(board, errors="ignore").read(6000)
    n = "In2.Cu" in text
    for lay in ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"] if n else ["F.Cu", "B.Cu"]:
        pdf = os.path.join(d, lay + ".pdf")
        sh(CLI, "pcb", "export", "pdf", "--layers", f"{lay},Edge.Cuts", "--mode-single", "-o", pdf, board)
        png = os.path.join(d, lay)
        sh("pdftoppm", "-png", "-r", "300", "-singlefile", pdf, png)
        im = Image.open(png + ".png").convert("RGB")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        from PIL import ImageChops
        bb = ImageChops.difference(im, bg).getbbox()
        if bb:
            m = 30
            im = im.crop((max(bb[0] - m, 0), max(bb[1] - m, 0), bb[2] + m, bb[3] + m))
        im.save(png + ".png")
        panels.append((lay.upper(), png + ".png"))
    ax.use("dark")
    rows = 2 if len(panels) > 3 else 1
    cols = 3
    fig, axs = plt.subplots(rows, cols, figsize=(16, 5.2 * rows))
    axs = axs.ravel() if hasattr(axs, "ravel") else [axs]
    for a, (t, f) in zip(axs, panels):
        a.imshow(Image.open(f)); a.set_title(t, fontsize=11, loc="left"); a.set_xticks([]); a.set_yticks([])
        for s in a.spines.values():
            s.set_visible(False)
    for a in list(axs)[len(panels):]:
        a.set_visible(False)
    fig.suptitle(title.upper(), fontsize=14, x=0.02, ha="left", weight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.97))
    fig.savefig(out, dpi=110)
    print("wrote", out, os.path.getsize(out) // 1024, "kB")


if __name__ == "__main__":
    main()
