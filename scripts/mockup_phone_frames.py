"""
Wrap each screenshot in a subtle iPhone-14 style phone frame.

Adds:
- rounded black bezel with soft shadow
- top notch (Dynamic-Island style pill)
- side/volume buttons
- optional gradient background

Usage:
    python scripts/mockup_phone_frames.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

SRC_ROOT = Path("/app/docs/ops/marketing/screenshots")
OUT_ROOT = Path("/app/docs/ops/marketing/screenshots_framed")

# Design constants
SCREEN_W, SCREEN_H = 390, 844        # inner screen size (matches capture)
FRAME_PAD = 22                        # bezel thickness
CORNER_RADIUS = 60                    # outer bezel corner
INNER_CORNER = 44                     # inner screen corner
NOTCH_W, NOTCH_H = 118, 30            # Dynamic Island
SHADOW_BLUR = 40
SHADOW_OFFSET = (0, 20)

CANVAS_W = SCREEN_W + FRAME_PAD * 2 + 120  # extra room for background/shadow
CANVAS_H = SCREEN_H + FRAME_PAD * 2 + 160

BG_TOP = (28, 22, 20)      # warm charcoal
BG_BOTTOM = (58, 34, 20)   # brand cocoa


def make_bg(w, h):
    """Vertical gradient background."""
    bg = Image.new("RGB", (w, h), BG_TOP)
    draw = ImageDraw.Draw(bg)
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    return bg


def rounded_mask(size, radius):
    mask = Image.new("L", size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([(0, 0), size], radius=radius, fill=255)
    return mask


def frame_screenshot(src_path: Path, dst_path: Path):
    shot = Image.open(src_path).convert("RGB").resize((SCREEN_W, SCREEN_H))

    canvas = make_bg(CANVAS_W, CANVAS_H).convert("RGBA")

    # coords for the phone
    px = (CANVAS_W - SCREEN_W - FRAME_PAD * 2) // 2
    py = (CANVAS_H - SCREEN_H - FRAME_PAD * 2) // 2
    phone_w = SCREEN_W + FRAME_PAD * 2
    phone_h = SCREEN_H + FRAME_PAD * 2

    # --- SHADOW under the phone
    shadow = Image.new("RGBA", (CANVAS_W, CANVAS_H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(
        [
            (px + SHADOW_OFFSET[0], py + SHADOW_OFFSET[1]),
            (px + phone_w + SHADOW_OFFSET[0], py + phone_h + SHADOW_OFFSET[1]),
        ],
        radius=CORNER_RADIUS,
        fill=(0, 0, 0, 165),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(SHADOW_BLUR))
    canvas.alpha_composite(shadow)

    # --- BEZEL (black with subtle inner highlight)
    bezel = Image.new("RGBA", (phone_w, phone_h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bezel)
    # base bezel
    bd.rounded_rectangle([(0, 0), (phone_w, phone_h)], radius=CORNER_RADIUS, fill=(15, 15, 17, 255))
    # subtle outer highlight ring
    bd.rounded_rectangle([(0, 0), (phone_w, phone_h)], radius=CORNER_RADIUS, outline=(60, 60, 65, 255), width=1)
    # inner darker ring around screen
    bd.rounded_rectangle(
        [(FRAME_PAD - 3, FRAME_PAD - 3), (FRAME_PAD + SCREEN_W + 3, FRAME_PAD + SCREEN_H + 3)],
        radius=INNER_CORNER + 3,
        outline=(0, 0, 0, 255),
        width=3,
    )

    canvas.alpha_composite(bezel, dest=(px, py))

    # --- SCREEN (mask corners)
    screen_mask = rounded_mask((SCREEN_W, SCREEN_H), INNER_CORNER)
    shot_rgba = shot.convert("RGBA")
    shot_rgba.putalpha(screen_mask)
    canvas.alpha_composite(shot_rgba, dest=(px + FRAME_PAD, py + FRAME_PAD))

    # --- NOTCH (Dynamic Island)
    notch = Image.new("RGBA", (NOTCH_W, NOTCH_H), (0, 0, 0, 0))
    nd = ImageDraw.Draw(notch)
    nd.rounded_rectangle([(0, 0), (NOTCH_W, NOTCH_H)], radius=NOTCH_H // 2, fill=(0, 0, 0, 255))
    canvas.alpha_composite(
        notch,
        dest=(px + (phone_w - NOTCH_W) // 2, py + FRAME_PAD - 4),
    )

    # --- Side buttons (subtle)
    btn = ImageDraw.Draw(canvas)
    # left side: silent + volume up + volume down
    for cy in (py + 130, py + 200, py + 250):
        btn.rounded_rectangle(
            [(px - 3, cy), (px + 3, cy + (30 if cy != py + 130 else 20))],
            radius=3,
            fill=(35, 35, 38, 255),
        )
    # right side: power
    btn.rounded_rectangle(
        [(px + phone_w - 3, py + 170), (px + phone_w + 3, py + 240)],
        radius=3,
        fill=(35, 35, 38, 255),
    )

    canvas.convert("RGB").save(dst_path, "JPEG", quality=88, optimize=True)


def main():
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    (OUT_ROOT / "customer").mkdir(exist_ok=True)
    (OUT_ROOT / "delivery").mkdir(exist_ok=True)

    total = 0
    for sub in ("customer", "delivery", "admin"):
        src_dir = SRC_ROOT / sub
        if not src_dir.exists():
            continue
        dst_dir = OUT_ROOT / sub
        dst_dir.mkdir(exist_ok=True)
        for src in sorted(src_dir.glob("*.jpeg")):
            dst = dst_dir / src.name
            frame_screenshot(src, dst)
            total += 1
            print(f"  ✓ {sub}/{src.name}")
    print(f"\n✅ Framed {total} screenshots → {OUT_ROOT}")


if __name__ == "__main__":
    main()
