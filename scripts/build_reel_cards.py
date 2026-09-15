"""
Generate brand title + outro cards (1080x1920) for the sales reel.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def load_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for c in candidates:
        p = Path(c)
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def gradient_bg(w, h, top, bottom):
    bg = Image.new("RGB", (w, h), top)
    d = ImageDraw.Draw(bg)
    for y in range(h):
        t = y / max(1, h - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        d.line([(0, y), (w, y)], fill=(r, g, b))
    return bg


def title_card(text_top, text_main, text_sub, out_path):
    W, H = 1080, 1920
    img = gradient_bg(W, H, (28, 22, 20), (80, 42, 22))
    d = ImageDraw.Draw(img)

    # Brand chip (circle with C)
    cx, cy, r = W // 2, 700, 90
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(199, 84, 46, 255))
    fbig = load_font(110, bold=True)
    bbox = d.textbbox((0, 0), "C", font=fbig)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    d.text((cx - tw // 2 - bbox[0], cy - th // 2 - bbox[1] - 6), "C", fill=(255, 255, 255), font=fbig)

    # Kicker
    f_kicker = load_font(38, bold=True)
    tw, th = d.textbbox((0, 0), text_top, font=f_kicker)[2:]
    d.text(((W - tw) // 2, 880), text_top, fill=(230, 180, 120), font=f_kicker)

    # Main
    f_main = load_font(96, bold=True)
    tw, th = d.textbbox((0, 0), text_main, font=f_main)[2:]
    d.text(((W - tw) // 2, 950), text_main, fill=(255, 255, 255), font=f_main)

    # Sub
    f_sub = load_font(42, bold=False)
    tw, th = d.textbbox((0, 0), text_sub, font=f_sub)[2:]
    d.text(((W - tw) // 2, 1090), text_sub, fill=(220, 220, 220), font=f_sub)

    img.save(out_path, "JPEG", quality=90)
    print(f"  ✓ {out_path}")


def outro_card(text_main, text_sub, out_path):
    W, H = 1080, 1920
    img = gradient_bg(W, H, (28, 22, 20), (60, 32, 20))
    d = ImageDraw.Draw(img)

    # Brand chip
    cx, cy, r = W // 2, 780, 90
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(199, 84, 46, 255))
    fbig = load_font(110, bold=True)
    bbox = d.textbbox((0, 0), "C", font=fbig)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    d.text((cx - tw // 2 - bbox[0], cy - th // 2 - bbox[1] - 6), "C", fill=(255, 255, 255), font=fbig)

    f_main = load_font(92, bold=True)
    tw = d.textbbox((0, 0), text_main, font=f_main)[2]
    d.text(((W - tw) // 2, 950), text_main, fill=(255, 255, 255), font=f_main)

    f_sub = load_font(44, bold=False)
    tw = d.textbbox((0, 0), text_sub, font=f_sub)[2]
    d.text(((W - tw) // 2, 1080), text_sub, fill=(220, 180, 130), font=f_sub)

    # Tagline pill
    tag = "curryandco.ca"
    f_tag = load_font(38, bold=True)
    tw = d.textbbox((0, 0), tag, font=f_tag)[2]
    pad_x, pad_y = 40, 20
    px = (W - tw) // 2
    py = 1220
    d.rounded_rectangle((px - pad_x, py - pad_y, px + tw + pad_x, py + 55), radius=40, fill=(255, 255, 255, 255))
    d.text((px, py - 6), tag, fill=(28, 22, 20), font=f_tag)

    img.save(out_path, "JPEG", quality=90)
    print(f"  ✓ {out_path}")


if __name__ == "__main__":
    out = Path("/app/docs/ops/marketing")
    title_card(
        "BENGALI CLOUD KITCHEN · GTA",
        "Curry & Co.",
        "Kitchen to doorstep, one platform.",
        out / "reel_title.jpg",
    )
    outro_card(
        "Curry & Co.",
        "Kitchen to doorstep.",
        out / "reel_outro.jpg",
    )
