#!/usr/bin/env python3
"""
build_marketing_video.py
========================
Compose a 60-70 second polished vertical marketing video (1080x1920,
9:16, 30 fps) from a set of phone screenshots.

Pipeline:
  1. For each scene, render a full-bleed 1080x1920 PNG "poster":
       - Warm gradient background matching the tenant brand
       - Rounded-corner phone silhouette with the screenshot inside
       - Feature caption baked in above the phone
       - Small tagline below
  2. Feed the 8 posters to ffmpeg, which applies:
       - Ken Burns (slow zoom-in) via zoompan
       - `xfade` cross-fade transitions between scenes
       - Fade-in on the first scene, fade-out on the last
  3. Muxes into an mp4 (H.264, yuv420p, +faststart) ready for
     Instagram Reels / TikTok / WhatsApp Status.

No audio: keep it a silent showcase so the user can drop music of their
choice later.

Usage:
    python scripts/build_marketing_video.py

Output:
    /app/docs/ops/marketing/curry_co_showcase.mp4
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ─── Paths ─────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent
SHOTS_DIR = Path("/tmp/marketing/shots")
BUILD_DIR = Path("/tmp/marketing/build")
OUT_DIR   = REPO_ROOT / "docs" / "ops" / "marketing"

BUILD_DIR.mkdir(parents=True, exist_ok=True)
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── Video params ──────────────────────────────────────────────────────
W, H = 1080, 1920         # portrait, phone-native
FPS = 30
SCENE_SEC = 8             # each scene visible for 8 s (before xfade)
XFADE = 0.6               # cross-fade duration (s)

# ─── Brand palette (from brand.config.js — Curry & Co.) ────────────────
PRIMARY      = (177, 79, 54)     # #B14F36
PRIMARY_DARK = (143, 62, 41)     # #8F3E29
CREAM        = (255, 249, 235)   # warm off-white
INK          = (30, 22, 18)      # near-black caption ink
GOLD         = (226, 163, 35)    # #E2A323

# ─── Fonts ─────────────────────────────────────────────────────────────
# Bundled with Debian: FreeSans* covers everything with clean geometry.
FONT_BOLD_PATH = "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
FONT_REG_PATH  = "/usr/share/fonts/truetype/freefont/FreeSans.ttf"
# Fallback if missing
if not Path(FONT_BOLD_PATH).exists():
    FONT_BOLD_PATH = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    FONT_REG_PATH  = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD_PATH if bold else FONT_REG_PATH
    return ImageFont.truetype(path, size)


# ─── Gradient background ───────────────────────────────────────────────
def gradient_bg() -> Image.Image:
    """Warm diagonal gradient — primary dark at the top-left corner
    fading into cream at bottom-right, with a subtle radial highlight
    behind the phone."""
    im = Image.new("RGB", (W, H), CREAM)
    px = im.load()
    for y in range(H):
        # blend PRIMARY_DARK → CREAM diagonally, biased so the top is deeper
        t = min(1.0, (y / (H * 0.85)))
        r = int(PRIMARY_DARK[0] * (1 - t) + CREAM[0] * t)
        g = int(PRIMARY_DARK[1] * (1 - t) + CREAM[1] * t)
        b = int(PRIMARY_DARK[2] * (1 - t) + CREAM[2] * t)
        for x in range(W):
            # slight rightward warm shift (adds diagonal feel)
            k = 1 - (x / (W * 8))  # tiny
            px[x, y] = (int(r * k), int(g * k), int(b * k))

    # Soft radial glow behind where the phone sits
    glow = Image.new("L", (W, H), 0)
    gd = ImageDraw.Draw(glow)
    cx, cy = W // 2, int(H * 0.6)
    gd.ellipse((cx - 520, cy - 780, cx + 520, cy + 780), fill=90)
    glow = glow.filter(ImageFilter.GaussianBlur(180))
    highlight = Image.new("RGB", (W, H), (255, 240, 210))
    im = Image.composite(highlight, im, glow)
    return im


# ─── Phone frame + screenshot ──────────────────────────────────────────
def rounded_mask(size: Tuple[int, int], radius: int) -> Image.Image:
    """Return an L-mode alpha mask with the given corner radius."""
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle((0, 0, size[0] - 1, size[1] - 1), radius=radius, fill=255)
    return m


def compose_phone(screenshot_path: Path, target_w: int = 700) -> Image.Image:
    """Return an RGBA phone image (bezel + notch + screenshot inside)
    at target_w pixels wide. Aspect: iPhone 15-ish (~1:2.16)."""
    shot = Image.open(screenshot_path).convert("RGB")
    # Screenshot came from a 390x844 viewport — resize preserving aspect.
    sw = target_w - 40  # 20 px bezel each side
    sh = int(sw * (shot.height / shot.width))
    shot = shot.resize((sw, sh), Image.LANCZOS)
    # Screen mask with slight rounding (inner)
    screen_mask = rounded_mask(shot.size, radius=42)

    # Phone body (bezel)
    ph_w, ph_h = target_w, sh + 80  # 40 px top/bottom bezel
    phone = Image.new("RGBA", (ph_w, ph_h), (0, 0, 0, 0))
    body = Image.new("RGB", (ph_w, ph_h), (16, 12, 10))
    body_mask = rounded_mask((ph_w, ph_h), radius=64)
    phone.paste(body, (0, 0), body_mask)

    # Screenshot inside
    inner = Image.new("RGB", shot.size, (0, 0, 0))
    inner.paste(shot, (0, 0), screen_mask)
    phone.paste(inner, (20, 40), screen_mask)

    # Dynamic-island / notch pill
    notch_w, notch_h = 140, 26
    notch_x = (ph_w - notch_w) // 2
    notch_y = 58
    notch = Image.new("RGBA", (notch_w, notch_h), (0, 0, 0, 0))
    ImageDraw.Draw(notch).rounded_rectangle(
        (0, 0, notch_w - 1, notch_h - 1), radius=13, fill=(4, 4, 4, 255)
    )
    phone.alpha_composite(notch, (notch_x, notch_y))

    return phone


def drop_shadow(phone: Image.Image, blur: int = 40, opacity: int = 150) -> Image.Image:
    """Return an RGBA-shadow image sized to hold phone + shadow padding."""
    pad = blur * 2
    shadow = Image.new("RGBA", (phone.width + pad, phone.height + pad), (0, 0, 0, 0))
    body_mask = rounded_mask(phone.size, radius=64)
    dark = Image.new("RGBA", phone.size, (0, 0, 0, opacity))
    shadow.paste(dark, (pad // 2, pad // 2 + 12), body_mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    return shadow


# ─── Text helpers ──────────────────────────────────────────────────────
def draw_text_centered(im: Image.Image, text: str, y: int, size: int, color, bold=True, max_width: int = W - 120):
    d = ImageDraw.Draw(im)
    f = font(size, bold=bold)
    # Simple word-wrap
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if d.textlength(test, font=f) <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    for i, line in enumerate(lines):
        tw = d.textlength(line, font=f)
        d.text(((W - tw) // 2, y + i * (size + 6)), line, font=f, fill=color)
    return y + len(lines) * (size + 6)


def draw_pill(im: Image.Image, text: str, y: int, size: int, color, bg):
    d = ImageDraw.Draw(im)
    f = font(size, bold=True)
    tw = d.textlength(text, font=f)
    pw, ph = int(tw) + 44, size + 22
    x = (W - pw) // 2
    d.rounded_rectangle((x, y, x + pw, y + ph), radius=ph // 2, fill=bg)
    d.text((x + 22, y + 10), text, font=f, fill=color)
    return y + ph


# ─── Scene composer ────────────────────────────────────────────────────
def build_scene_intro() -> Image.Image:
    """Title card — bold hero, brand name, tagline."""
    im = gradient_bg().convert("RGBA")

    # Center brand logo circle
    logo_size = 260
    logo = Image.new("RGBA", (logo_size, logo_size), (0, 0, 0, 0))
    d = ImageDraw.Draw(logo)
    d.ellipse((0, 0, logo_size, logo_size), fill=PRIMARY)
    f_c = font(160, bold=True)
    tw = d.textlength("C", font=f_c)
    d.text(((logo_size - tw) // 2, (logo_size - 160) // 2 - 20), "C", font=f_c, fill=CREAM)
    im.alpha_composite(logo, ((W - logo_size) // 2, 520))

    draw_pill(im, "SUPARNA DEY PLATFORM", 850, 26, CREAM, PRIMARY_DARK)
    draw_text_centered(im, "Curry & Co.", 950, 130, CREAM, bold=True)
    draw_text_centered(im, "Bengali kitchen. Delivered.",
                       1120, 46, CREAM, bold=False)
    draw_text_centered(im, "A rotating weekly menu of Kolkata classics — every Friday & Saturday, across the GTA.",
                       1240, 34, (255, 245, 225), bold=False)
    return im.convert("RGB")


def build_scene_feature(screenshot: Path, headline: str, sub: str, pill: str) -> Image.Image:
    im = gradient_bg().convert("RGBA")

    # Pill at top
    draw_pill(im, pill, 90, 26, CREAM, PRIMARY_DARK)

    # Headline
    y = draw_text_centered(im, headline, 170, 78, CREAM, bold=True)
    y = draw_text_centered(im, sub, y + 24, 34, (255, 240, 210), bold=False)

    # Phone
    phone = compose_phone(screenshot, target_w=680)
    shadow = drop_shadow(phone, blur=50, opacity=130)
    phone_y = y + 80
    im.alpha_composite(shadow, ((W - shadow.width) // 2, phone_y - 30))
    im.alpha_composite(phone, ((W - phone.width) // 2, phone_y))

    # Footer brand line
    draw_text_centered(im, "curry & co.  ·  suparna dey platform",
                       H - 90, 24, (255, 235, 205), bold=False)
    return im.convert("RGB")


def build_scene_outro() -> Image.Image:
    im = gradient_bg().convert("RGBA")
    draw_pill(im, "AVAILABLE NOW", 700, 30, CREAM, PRIMARY_DARK)
    draw_text_centered(im, "Get the app.", 800, 130, CREAM, bold=True)
    draw_text_centered(im, "iOS · Android · Web", 970, 48, (255, 240, 210), bold=False)

    # Feature bullets
    bullets = [
        "•  Weekly rotating menu",
        "•  Combo builder & catering",
        "•  Google Maps address autocomplete",
        "•  Real-time driver tracking",
        "•  COD, Interac, Card payments",
    ]
    y = 1120
    for b in bullets:
        draw_text_centered(im, b, y, 36, CREAM, bold=False)
        y += 60
    draw_text_centered(im, "curryco.ca  ·  hello@curryandco.com",
                       H - 120, 30, (255, 235, 205), bold=False)
    return im.convert("RGB")


# ─── Scene list ────────────────────────────────────────────────────────
SCENES = [
    ("intro",       None,                             None,                     None,                       None),
    ("feature",     SHOTS_DIR / "01_hero.jpg",        "Slow-cooked stories",     "Weekly Bengali specials, fresh every Friday & Saturday.",  "THE APP"),
    ("feature",     SHOTS_DIR / "02_menu.jpg",        "A rotating weekly menu",  "Chicken Biryani. Shorshe Ilish. Kosha Mangsho. All week, all fresh.", "MENU"),
    ("feature",     SHOTS_DIR / "03_combo.jpg",       "Build your own combo",    "Pick 3 dishes at one flat price. Repeats allowed.",         "COMBOS"),
    ("feature",     SHOTS_DIR / "04_catering.jpg",    "Catering that scales",    "Kolkata-style feasts for gatherings of 10 to 500.",         "CATERING"),
    ("feature",     SHOTS_DIR / "07_dp_queue.jpg",    "Delivery, one tap away",  "A dedicated driver app with live GPS & one-tap status.",    "DELIVERY"),
    ("feature",     SHOTS_DIR / "08_dp_route.jpg",    "Optimized routes",        "Drivers plan the fastest run across the GTA in one click.", "ROUTING"),
    ("outro",       None,                              None,                     None,                       None),
]


def build_all_scene_pngs() -> List[Path]:
    paths: List[Path] = []
    for idx, (kind, shot, head, sub, pill) in enumerate(SCENES):
        out = BUILD_DIR / f"scene_{idx:02d}.png"
        print(f"  [{idx+1}/{len(SCENES)}] {kind:8s} → {out.name}")
        if kind == "intro":
            img = build_scene_intro()
        elif kind == "outro":
            img = build_scene_outro()
        else:
            if not shot or not shot.exists():
                raise FileNotFoundError(f"Missing screenshot: {shot}")
            img = build_scene_feature(shot, head, sub, pill)
        img.save(out, "PNG")
        paths.append(out)
    return paths


# ─── ffmpeg orchestration ──────────────────────────────────────────────
def render_video(scene_pngs: List[Path]) -> Path:
    """Build the mp4 by chaining `xfade` transitions between scenes,
    with a Ken Burns zoompan applied to each poster."""
    out = OUT_DIR / "curry_co_showcase.mp4"
    n = len(scene_pngs)

    # Total playtime per input clip (before xfade)
    scene_frames = SCENE_SEC * FPS

    # Build filter_complex
    inputs: List[str] = []
    for p in scene_pngs:
        inputs.extend(["-loop", "1", "-t", str(SCENE_SEC + 1), "-i", str(p)])

    # Each input gets a zoompan + scale to final size.
    parts: List[str] = []
    for i in range(n):
        # Slow zoom from 1.00 → 1.08 across the scene
        zp = (
            f"[{i}:v]"
            f"scale=1620:2880:force_original_aspect_ratio=increase,"
            f"crop=1620:2880,"
            f"zoompan=z='min(zoom+0.0015,1.08)':d={scene_frames}:s={W}x{H}:fps={FPS},"
            f"format=yuv420p,"
            f"setpts=PTS-STARTPTS,"
            f"trim=duration={SCENE_SEC},"
            f"format=yuv420p"
            f"[v{i}]"
        )
        parts.append(zp)

    # Chain xfade transitions
    chain = ""
    for i in range(n - 1):
        left = f"[v{i}]" if i == 0 else f"[t{i-1}]"
        offset = (SCENE_SEC - XFADE) * (i + 1) - (XFADE * i)
        # Simpler: cumulative offset
        offset = (i + 1) * SCENE_SEC - (i + 1) * XFADE
        chain += (
            f"{left}[v{i+1}]xfade=transition=fade:duration={XFADE}:offset={offset}[t{i}];"
        )
    # last output name
    final_label = f"[t{n-2}]" if n >= 2 else f"[v0]"

    filter_graph = ";".join(parts) + (";" + chain.rstrip(";") if chain else "")

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_graph,
        "-map", final_label,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-crf", "20",
        "-preset", "medium",
        "-movflags", "+faststart",
        "-r", str(FPS),
        str(out),
    ]

    print("\n→ Running ffmpeg …")
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("stdout:\n", r.stdout[-1500:])
        print("stderr:\n", r.stderr[-1500:])
        raise SystemExit("ffmpeg failed")
    return out


def main() -> int:
    if not SHOTS_DIR.exists():
        raise SystemExit(f"Missing screenshots dir: {SHOTS_DIR}")

    print("Rendering scene posters:")
    scene_pngs = build_all_scene_pngs()

    out = render_video(scene_pngs)
    size_mb = out.stat().st_size / 1_000_000
    dur = len(SCENES) * SCENE_SEC - (len(SCENES) - 1) * XFADE
    print(f"\n✓ Wrote {out}  ({size_mb:.1f} MB, ~{dur:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
