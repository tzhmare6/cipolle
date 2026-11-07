"""Zeichnet das Hintergrundbild des Disk-Images: packaging/dmg-background.tiff

Aufruf auf dem Mac, mit Pillow: python packaging/make_dmg_background.py
Die TIFF-Datei enthält eine normale und eine doppelt so grosse Fassung für Retina.
Die Positionen müssen zu ICONS in build-dmg.sh passen.
"""

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Höher als das Fenster, damit auch ohne Pfad- und Statusleiste kein Rand entsteht.
WIDTH, HEIGHT = 640, 460
APP, LINK = (160, 185), (480, 185)  # Mitte der beiden Symbole
ICON = 128

TOP = (255, 250, 240)
BOTTOM = (246, 230, 198)
ORANGE = (226, 112, 42)
INK = (59, 42, 32)
MUTED = (122, 106, 92)

FONTS = Path("/System/Library/Fonts/Supplemental")
HERE = Path(__file__).resolve().parent


def draw(scale: int) -> Image.Image:
    def s(value: float) -> int:
        return round(value * scale)

    image = Image.new("RGB", (s(WIDTH), s(HEIGHT)))
    canvas = ImageDraw.Draw(image)
    for y in range(s(HEIGHT)):
        t = y / (s(HEIGHT) - 1)
        canvas.line([(0, y), (s(WIDTH), y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(TOP, BOTTOM)))

    title = ImageFont.truetype(str(FONTS / "Arial Rounded Bold.ttf"), s(22))
    canvas.text((s(WIDTH / 2), s(46)), "Cipolle installieren", font=title, fill=INK, anchor="mm")

    # Pfeil zwischen den Symbolen, mit etwas Abstand zu ihnen.
    y = s(APP[1])
    start, end = s(APP[0] + ICON / 2 + 22), s(LINK[0] - ICON / 2 - 22)
    width = s(9)
    canvas.line([(start, y), (end - s(16), y)], fill=ORANGE, width=width)
    canvas.ellipse([start - width // 2, y - width // 2, start + width // 2, y + width // 2], fill=ORANGE)
    canvas.polygon([(end, y), (end - s(26), y - s(19)), (end - s(26), y + s(19))], fill=ORANGE)

    hint = ImageFont.truetype(str(FONTS / "Arial.ttf"), s(14))
    # Der Finder blendet je nach Einstellung Pfad- und Statusleiste ein, sie verdecken
    # die unteren rund 56 Punkte des Fensters. Der Text steht darum über dieser Zone.
    canvas.text((s(WIDTH / 2), s(318)), "Ziehe Cipolle auf «Applications», um es zu installieren.",
                font=hint, fill=MUTED, anchor="mm")
    return image


def main() -> None:
    with tempfile.TemporaryDirectory() as folder:
        normal, retina = Path(folder) / "background.png", Path(folder) / "background@2x.png"
        draw(1).save(normal, dpi=(72, 72))
        draw(2).save(retina, dpi=(144, 144))
        target = HERE / "dmg-background.tiff"
        subprocess.run(["tiffutil", "-cathidpicheck", str(normal), str(retina), "-out", str(target)], check=True)
    print(f"Fertig: {target}")


if __name__ == "__main__":
    main()
