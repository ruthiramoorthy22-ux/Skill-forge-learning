"""Renders the course certificate. The design is a template image (the built-in Skill Forge Learning design, or one the
admin uploaded). Only four things are drawn on it: the student name, the course title, the date and the certificate id.
Where each text goes (position, size, colour, font) is a small config stored with the template, so any uploaded design
works. Positions are fractions of the image (0..1), so the config does not depend on the image resolution."""
import io
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

ASSETS = Path(__file__).parent / "assets"
DEFAULT_TEMPLATE = ASSETS / "certificate_default.png"
FONTS = {
    "serif_bold": ASSETS / "fonts" / "SourceSerif_Bold.ttf",
    "serif": ASSETS / "fonts" / "SourceSerif_Regular.ttf",
    "sans_bold": ASSETS / "fonts" / "Inter_700Bold.ttf",
    "sans_semibold": ASSETS / "fonts" / "Inter_600SemiBold.ttf",
    "sans": ASSETS / "fonts" / "Inter_400Regular.ttf",
}
FIELD_NAMES = ("name", "course", "date", "cert_id")

# Positions measured on the built-in template (1344 x 896). x, y = centre of the text and its baseline.
DEFAULT_FIELDS = {
    "name":    {"x": 0.5, "y": 0.333, "size": 0.085, "color": "#0A1A5C", "font": "serif_bold", "max_width": 0.62, "prefix": "", "visible": True},
    "course":  {"x": 0.5, "y": 0.546, "size": 0.066, "color": "#0A1A5C", "font": "serif_bold", "max_width": 0.72, "prefix": "", "visible": True},
    "date":    {"x": 0.5, "y": 0.922, "size": 0.026, "color": "#0A1A5C", "font": "serif", "max_width": 0.22, "prefix": "Date: ", "visible": True},
    "cert_id": {"x": 0.5, "y": 0.966, "size": 0.015, "color": "#5A6987", "font": "sans", "max_width": 0.5, "prefix": "Certificate ID: ", "visible": True},
}
SAMPLE_NAME = "Your Name Here"


def clean_fields(raw: Optional[dict]) -> dict:
    """Merges admin input over the defaults and clamps every value, so a bad config can never break rendering."""
    out = {}
    raw = raw if isinstance(raw, dict) else {}
    for key in FIELD_NAMES:
        base, given = dict(DEFAULT_FIELDS[key]), raw.get(key) if isinstance(raw.get(key), dict) else {}
        f = {**base}
        for k, lo, hi in (("x", 0.0, 1.0), ("y", 0.0, 1.0), ("size", 0.008, 0.25), ("max_width", 0.05, 1.0)):
            try:
                f[k] = min(hi, max(lo, float(given.get(k, base[k]))))
            except (TypeError, ValueError):
                pass
        c = given.get("color", base["color"])
        f["color"] = c if isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) else base["color"]
        f["font"] = given.get("font") if given.get("font") in FONTS else base["font"]
        p = given.get("prefix", base["prefix"])
        f["prefix"] = p[:30] if isinstance(p, str) else base["prefix"]
        f["visible"] = bool(given.get("visible", True))
        out[key] = f
    return out


@lru_cache(maxsize=1)
def default_template() -> Image.Image:
    return Image.open(DEFAULT_TEMPLATE).convert("RGB")


def _hex(c: str) -> Tuple[int, int, int]:
    return int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)


def _fit(draw: ImageDraw.ImageDraw, text: str, font_key: str, size: int, max_width: int, min_size: int = 10):
    while size > min_size:
        font = ImageFont.truetype(str(FONTS[font_key]), size)
        if draw.textlength(text, font=font) <= max_width:
            return font
        size -= 1
    return ImageFont.truetype(str(FONTS[font_key]), min_size)


def render_certificate(student_name: str, course_title: str, completed_on: date, certificate_id: str,
                       template: Optional[Tuple[Image.Image, dict]] = None) -> Image.Image:
    """template = (image, fields) of the active design; the built-in design is used when it is None."""
    base, fields = template if template is not None else (default_template(), DEFAULT_FIELDS)
    fields = clean_fields(fields)
    img = base.copy()
    d = ImageDraw.Draw(img)
    w, h = img.size
    values = {
        "name": student_name.strip()[:60],
        "course": course_title.strip()[:90],
        "date": f"{completed_on.day:02d} {completed_on.strftime('%b')} {completed_on.year}",
        "cert_id": certificate_id,
    }
    for key in FIELD_NAMES:
        f = fields[key]
        if not f["visible"] or not values[key]:
            continue
        text = f["prefix"] + values[key]
        font = _fit(d, text, f["font"], max(10, round(f["size"] * h)), round(f["max_width"] * w))
        d.text((round(f["x"] * w), round(f["y"] * h)), text, font=font, fill=_hex(f["color"]), anchor="ms")
    return img


def to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def to_pdf(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PDF", resolution=150.0)
    return buf.getvalue()
