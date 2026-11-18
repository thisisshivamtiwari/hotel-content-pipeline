"""Draw the image post (1080x1350) and a reel animatic (540x960 MP4) from a pack, in the hotel's brand colours.

The animatic is what an editor cuts against: each scene is a card naming the footage shot to drop in, with the
on-screen text where it will sit. No stock photos or generated images are used, so nothing in a render can show
something the hotel doesn't have.
"""

import json
import shutil
import subprocess
import tempfile
import textwrap
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import checks, experiment

OUT = experiment.ROOT / "renders"
FONTS = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
SOURCE = ("sonnet-5.5", "full", 0)


def font(size: int):
    for path in FONTS:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    h = hex_colour.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t: float):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b, strict=True))


def _text(draw, xy, text, size, fill, width_chars):
    y = xy[1]
    f = font(size)
    for line in textwrap.wrap(text, width_chars):
        draw.text((xy[0], y), line, font=f, fill=fill)
        y += int(size * 1.2)
    return y


def image_post(brief: dict, pack: dict, path: Path) -> None:
    primary, accent = _rgb(brief["brand"]["primary"]), _rgb(brief["brand"]["accent"])
    img = Image.new("RGB", (1080, 1350), primary)
    d = ImageDraw.Draw(img)
    d.rectangle((60, 60, 1020, 860), fill=_mix(primary, (255, 255, 255), 0.18))
    _text(d, (100, 420), "photo slot: " + brief["footage"][0], 34, _mix(primary, (255, 255, 255), 0.6), 40)
    d.rectangle((60, 900, 200, 912), fill=accent)
    y = _text(d, (60, 950), pack["image_post"]["headline"], 72, (255, 255, 255), 24)
    _text(d, (60, y + 20), pack["image_post"]["subline"], 40, accent, 44)
    _text(d, (60, 1260), f"{brief['name']} · {brief['town']}", 30, _mix(primary, (255, 255, 255), 0.7), 60)
    img.save(path)


def reel(brief: dict, pack: dict, path: Path) -> None:
    primary, accent = _rgb(brief["brand"]["primary"]), _rgb(brief["brand"]["accent"])
    with tempfile.TemporaryDirectory() as tmp:
        lines = []
        for i, scene in enumerate(pack["reel"]["scenes"]):
            img = Image.new("RGB", (540, 960), _mix(primary, (255, 255, 255), 0.12 * (i % 2)))
            d = ImageDraw.Draw(img)
            d.rectangle((30, 30, 510, 600), outline=_mix(primary, (255, 255, 255), 0.5), width=3)
            _text(d, (60, 290), "footage: " + scene["shot"], 26, _mix(primary, (255, 255, 255), 0.6), 30)
            d.rectangle((30, 660, 110, 668), fill=accent)
            _text(d, (30, 690), scene["on_screen_text"], 44, (255, 255, 255), 20)
            _text(d, (30, 900), f"{brief['name']}  ·  {i + 1}/{len(pack['reel']['scenes'])}", 20, accent, 50)
            frame = Path(tmp) / f"s{i}.png"
            img.save(frame)
            lines += [f"file '{frame}'", f"duration {scene['seconds']}"]
        lines.append(f"file '{frame}'")
        (Path(tmp) / "list.txt").write_text("\n".join(lines) + "\n")
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(Path(tmp) / "list.txt"),
             "-vf", "fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "28", str(path)],
            check=True,
        )  # fmt: skip


def main() -> None:
    rows = [json.loads(line) for line in (experiment.RESULTS / "packs.jsonl").read_text().splitlines()]
    briefs = checks.load_briefs()
    OUT.mkdir(exist_ok=True)
    timings = []
    for r in rows:
        if (r["model"], r["arm"], r["sample"]) != SOURCE or not isinstance(r["pack"], dict):
            continue
        brief = briefs[r["hotel"]]
        t0 = time.perf_counter()
        image_post(brief, r["pack"], OUT / f"{r['hotel']}-post.png")
        t1 = time.perf_counter()
        if shutil.which("ffmpeg"):
            reel(brief, r["pack"], OUT / f"{r['hotel']}-reel.mp4")
        t2 = time.perf_counter()
        timings.append({"hotel": r["hotel"], "image_s": round(t1 - t0, 3), "reel_s": round(t2 - t1, 3)})
    (experiment.RESULTS / "render.json").write_text(json.dumps({"source": SOURCE, "renders": timings}, indent=1) + "\n")
    print(json.dumps(timings, indent=1))
