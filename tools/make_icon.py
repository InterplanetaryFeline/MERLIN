"""Draw MERLIN's icon: a rocket wearing a wizard's hat, as one black silhouette. Writes the Windows icon and the
page's favicon.

    python tools/make_icon.py

The shape is drawn as a mask at 1024 px - black where the silhouette is, clear where the porthole, the hat's band
and stars and the gap above the flame are cut out - upright, then turned to fly up and to the right, and scaled
down so every size Windows asks for is smooth. The output files are committed; run this again only to change
the drawing.
"""
from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "src", "launch_vehicle", "gui_static")
S = 1024
INK = (17, 17, 17)                     # near black, the way a black glyph prints
HALO = (255, 255, 255)                 # the outline that keeps it visible on a dark taskbar
HALO_PX = 29                           # its width at 1024 px: about one pixel at 32 px
ON, OFF = 255, 0


def star(cx, cy, r_out, r_in, n=5, rot=-90.0):
    pts = []
    for i in range(2 * n):
        r = r_out if i % 2 == 0 else r_in
        a = math.radians(rot + i * 180.0 / n)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def sparkle(cx, cy, r):
    """A four-pointed twinkle, pinched in the middle."""
    return star(cx, cy, r, r * 0.28, n=4, rot=-90.0)


def rocket_with_hat() -> Image.Image:
    """The upright figure, nose at the top: the hat sits where the nose cone would be."""
    m = Image.new("L", (S, S), OFF)
    d = ImageDraw.Draw(m)
    cx = S / 2

    # hull: long and slim, swelling a little below the hat and rounded at the base
    hull = [(cx - 100, 860), (cx - 118, 720), (cx - 116, 560), (cx - 98, 450), (cx - 74, 390),
            (cx + 74, 390), (cx + 98, 450), (cx + 116, 560), (cx + 118, 720), (cx + 100, 860)]
    d.polygon(hull, fill=ON)
    d.ellipse([cx - 100, 820, cx + 100, 890], fill=ON)
    # swept fins, a clear gap between each and the hull so they read at small sizes
    for sgn in (-1, 1):
        d.polygon([(cx + sgn * 134, 640), (cx + sgn * 270, 800), (cx + sgn * 280, 930),
                   (cx + sgn * 150, 860), (cx + sgn * 134, 850)], fill=ON)
    # nozzle, then the flame below a clear gap, hollowed like a crescent
    d.polygon([(cx - 62, 880), (cx + 62, 880), (cx + 78, 915), (cx - 78, 915)], fill=ON)
    d.polygon([(cx - 64, 945), (cx + 64, 945), (cx + 8, 1015), (cx, 1022), (cx - 8, 1015)], fill=ON)
    d.polygon([(cx - 24, 945), (cx + 24, 945), (cx, 985)], fill=OFF)
    # porthole
    d.ellipse([cx - 56, 520, cx + 56, 632], fill=OFF)

    # the hat: a wide brim with a highlight, then a tall cone leaning a little, ending in a point
    d.ellipse([cx - 230, 340, cx + 230, 440], fill=ON)
    d.arc([cx - 196, 354, cx + 196, 426], start=25, end=155, fill=OFF, width=16)
    d.polygon([(cx - 150, 380), (cx + 150, 380), (cx + 80, 230), (cx + 50, 120), (cx + 30, 30),
               (cx - 10, 110), (cx - 60, 200)], fill=ON)
    # the band: two clear stripes across the base of the cone
    d.polygon([(cx - 142, 340), (cx + 142, 340), (cx + 134, 322), (cx - 134, 322)], fill=OFF)
    d.polygon([(cx - 126, 300), (cx + 126, 300), (cx + 118, 284), (cx - 118, 284)], fill=OFF)
    # stars cut out of the cone
    d.polygon(star(cx - 32, 220, 40, 16), fill=OFF)
    d.polygon(sparkle(cx + 46, 242, 28), fill=OFF)
    d.polygon(star(cx + 16, 140, 24, 10, rot=-70), fill=OFF)
    return m


def draw() -> Image.Image:
    fig = rocket_with_hat().rotate(-40, resample=Image.BICUBIC, expand=True)
    box = fig.getbbox()
    fig = fig.crop(box)
    # centred in the square with a small margin: just the rocket and its hat
    scale = (S - 2 * HALO_PX - 20) / max(fig.size)
    fig = fig.resize((round(fig.width * scale), round(fig.height * scale)), Image.LANCZOS)
    mask = Image.new("L", (S, S), OFF)
    mask.paste(fig, ((S - fig.width) // 2, (S - fig.height) // 2))
    # a white outline just outside the black, so the silhouette shows on dark backgrounds too; it also rims the
    # porthole, the stars and the band, which helps them read there
    # grown evenly in every direction (blur, then cut at a threshold) rather than in squares, then softened a touch
    halo = mask.filter(ImageFilter.GaussianBlur(HALO_PX / 2)).point(lambda v: 255 if v > 6 else 0)
    halo = halo.filter(ImageFilter.GaussianBlur(1.5))
    img = Image.new("RGBA", (S, S), HALO + (0,))
    img.putalpha(halo)
    ink = Image.new("RGBA", (S, S), INK + (0,))
    ink.putalpha(mask)
    img.alpha_composite(ink)
    return img


def main() -> None:
    big = draw()
    sizes = [16, 24, 32, 48, 64, 128, 256]
    big.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT, "merlin.ico"), sizes=[(s, s) for s in sizes])
    big.resize((256, 256), Image.LANCZOS).save(os.path.join(OUT, "merlin.png"))
    big.resize((64, 64), Image.LANCZOS).save(os.path.join(OUT, "favicon.png"))
    print("wrote merlin.ico, merlin.png and favicon.png in", OUT)


if __name__ == "__main__":
    main()
