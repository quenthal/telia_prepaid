#!/usr/bin/env python3
"""Tekee integraation brändikuvat Telian logosta (tools/telia_pebble.png).

    pip install pillow
    python3 tools/make_brand.py  ->  custom_components/telia_prepaid/brand/*.png

Home Assistant 2026.3+ lukee kuvat integraation brand/-kansiosta.
Koot: icon 256x256 (@2x 512x512), logo korkeus 128 (@2x 256), läpinäkyvä tausta.
"""
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "tools" / "telia_pebble.png"
OUT = ROOT / "custom_components" / "telia_prepaid" / "brand"
# Jos järjestelmässä ei ole DejaVua: BRAND_FONT=.../matplotlib/mpl-data/fonts/ttf/DejaVuSans-Bold.ttf
FONT = os.environ.get("BRAND_FONT", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

# Logon tekstin väri; kuvake on sama molemmissa teemoissa
THEMES = {"": (45, 32, 64), "dark_": (240, 236, 248)}


def load_source() -> Image.Image:
    img = Image.open(SOURCE).convert("RGBA")
    return img.crop(img.getchannel("A").getbbox())


def draw_icon(src: Image.Image, size: int) -> Image.Image:
    """Logo neliön keskelle kapealla reunuksella."""
    pebble = src.copy()
    inner = round(size * 0.94)
    pebble.thumbnail((inner, inner), Image.LANCZOS)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.alpha_composite(pebble, ((size - pebble.width) // 2, (size - pebble.height) // 2))
    return img


def draw_logo(src: Image.Image, height: int, text_color: tuple[int, int, int]) -> Image.Image:
    icon = draw_icon(src, height)
    font = ImageFont.truetype(FONT, int(height * 0.40))
    text = "Telia Prepaid"
    gap = int(height * 0.12)
    tw = int(ImageDraw.Draw(icon).textlength(text, font=font))
    img = Image.new("RGBA", (height + gap + tw + 4, height), (0, 0, 0, 0))
    img.alpha_composite(icon, (0, 0))
    ImageDraw.Draw(img).text((height + gap, height // 2), text, font=font, fill=text_color, anchor="lm")
    return img


def main() -> None:
    src = load_source()
    OUT.mkdir(parents=True, exist_ok=True)
    for prefix, text_color in THEMES.items():
        draw_icon(src, 256).save(OUT / f"{prefix}icon.png", optimize=True)
        draw_icon(src, 512).save(OUT / f"{prefix}icon@2x.png", optimize=True)
        draw_logo(src, 128, text_color).save(OUT / f"{prefix}logo.png", optimize=True)
        draw_logo(src, 256, text_color).save(OUT / f"{prefix}logo@2x.png", optimize=True)
    for f in sorted(OUT.iterdir()):
        with Image.open(f) as im:
            print(f"{f.name:20s} {im.size[0]}x{im.size[1]}")


if __name__ == "__main__":
    main()
