#!/usr/bin/env python3
"""Piirtää integraation brändikuvat (oma kuvake: SIM-kortti + euro).

    pip install pillow
    python3 tools/make_brand.py  ->  custom_components/telia_prepaid/brand/*.png

Home Assistant 2026.3+ lukee kuvat integraation brand/-kansiosta.
Koot: icon 256x256 (@2x 512x512), logo korkeus 128 (@2x 256), läpinäkyvä tausta.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "custom_components" / "telia_prepaid" / "brand"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
SS = 4  # ylinäytteistys pehmeitä reunoja varten

THEMES = {
    "": {"card": (110, 40, 170), "card2": (153, 75, 214), "chip": (240, 196, 92),
         "line": (176, 132, 40), "euro": (255, 255, 255), "text": (45, 32, 64)},
    "dark_": {"card": (176, 120, 236), "card2": (206, 160, 250), "chip": (246, 210, 120),
              "line": (176, 132, 40), "euro": (40, 16, 70), "text": (240, 236, 248)},
}


def draw_icon(size: int, t: dict) -> Image.Image:
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # SIM-kortin muoto: pyöristetty suorakulmio, oikea yläkulma viistetty
    m = int(s * 0.12)
    left, top, right, bottom = int(s * 0.16), m, int(s * 0.84), s - m
    r = int(s * 0.07)
    cut = int(s * 0.18)
    body = Image.new("L", (s, s), 0)
    bd = ImageDraw.Draw(body)
    bd.rounded_rectangle((left, top, right, bottom), radius=r, fill=255)
    bd.polygon([(right - cut, top - 2), (right + 2, top - 2), (right + 2, top + cut)], fill=0)
    # Pystysuuntainen liukuväri
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    for y in range(s):
        k = y / s
        c = tuple(int(t["card2"][i] * (1 - k) + t["card"][i] * k) for i in range(3))
        gd.line([(0, y), (s, y)], fill=c + (255,))
    img.paste(grad, (0, 0), body)

    # Siru
    cw, ch = int(s * 0.36), int(s * 0.27)
    cx0 = (s - cw) // 2
    cy0 = int(s * 0.56)
    d.rounded_rectangle((cx0, cy0, cx0 + cw, cy0 + ch), radius=int(s * 0.035), fill=t["chip"])
    lw = max(SS, int(s * 0.012))
    d.line([(cx0 + cw // 3, cy0), (cx0 + cw // 3, cy0 + ch)], fill=t["line"], width=lw)
    d.line([(cx0 + 2 * cw // 3, cy0), (cx0 + 2 * cw // 3, cy0 + ch)], fill=t["line"], width=lw)
    d.line([(cx0, cy0 + ch // 2), (cx0 + cw, cy0 + ch // 2)], fill=t["line"], width=lw)

    # Euromerkki
    font = ImageFont.truetype(FONT, int(s * 0.30))
    d.text((s // 2, int(s * 0.36)), "€", font=font, fill=t["euro"], anchor="mm")

    return img.resize((size, size), Image.LANCZOS)


def draw_logo(height: int, t: dict) -> Image.Image:
    icon = draw_icon(height, t)
    font = ImageFont.truetype(FONT, int(height * 0.40))
    text = "Telia Prepaid"
    tw = int(ImageDraw.Draw(icon).textlength(text, font=font))
    img = Image.new("RGBA", (height + int(height * 0.12) + tw + 4, height), (0, 0, 0, 0))
    img.paste(icon, (0, 0), icon)
    ImageDraw.Draw(img).text(
        (height + int(height * 0.12), height // 2), text, font=font, fill=t["text"], anchor="lm"
    )
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for prefix, theme in THEMES.items():
        draw_icon(256, theme).save(OUT / f"{prefix}icon.png", optimize=True)
        draw_icon(512, theme).save(OUT / f"{prefix}icon@2x.png", optimize=True)
        draw_logo(128, theme).save(OUT / f"{prefix}logo.png", optimize=True)
        draw_logo(256, theme).save(OUT / f"{prefix}logo@2x.png", optimize=True)
    for f in sorted(OUT.iterdir()):
        with Image.open(f) as im:
            print(f"{f.name:20s} {im.size[0]}x{im.size[1]}")


if __name__ == "__main__":
    main()
