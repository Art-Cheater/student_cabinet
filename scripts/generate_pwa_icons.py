#!/usr/bin/env python3
"""Generate PWA PNG icons from brand colors."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'static' / 'icons'
BLUE = (0, 57, 166)
GOLD = (255, 215, 0)
WHITE = (255, 255, 255)


def draw_icon(size: int, path: Path) -> None:
    img = Image.new('RGB', (size, size), BLUE)
    draw = ImageDraw.Draw(img)
    bar_h = max(4, size // 22)
    draw.rectangle((0, 0, size, bar_h), fill=GOLD)
    text = 'ВГУ'
    font_size = size // 4
    try:
        font = ImageFont.truetype('arial.ttf', font_size)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - tw) / 2, (size - th) / 2 + bar_h), text, fill=WHITE, font=font)
    img.save(path, 'PNG')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    draw_icon(192, OUT / 'icon-192.png')
    draw_icon(512, OUT / 'icon-512.png')
    print('Wrote', OUT / 'icon-192.png', OUT / 'icon-512.png')


if __name__ == '__main__':
    main()
