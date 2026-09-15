"""
Render a 60-second AI-narrated sales reel from the phone-framed screenshots.

Pipeline:
1. Generate narration MP3 via Emergent's OpenAI TTS (tts-1-hd, "onyx").
2. Read narration duration.
3. Stretch each framed screenshot for its scene's fixed duration.
4. FFmpeg concat + audio overlay + subtle Ken-Burns zoom on each still.

Output: /app/docs/ops/marketing/curry_co_sales_reel.mp4
"""

import asyncio
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from emergentintegrations.llm.openai import OpenAITextToSpeech

load_dotenv("/app/backend/.env")

FRAMES_ROOT = Path("/app/docs/ops/marketing/screenshots_framed")
OUT_DIR = Path("/app/docs/ops/marketing")
TITLE_CARD = OUT_DIR / "reel_title.jpg"
OUTRO_CARD = OUT_DIR / "reel_outro.jpg"
NARRATION_MP3 = OUT_DIR / "sales_reel_narration.mp3"
VIDEO_OUT = OUT_DIR / "curry_co_sales_reel.mp4"
WORK_DIR = OUT_DIR / "_reel_build"
WORK_DIR.mkdir(exist_ok=True)

# Title (3 s silent) + narrated scenes + Outro (~5 s silent). Total ≈ narration + 8.
TITLE_DURATION = 3.0
OUTRO_DURATION = 5.0

# ---- Scene plan: 15 shots pacing to ~60s narration
SCENES = [
    # Customer app segment
    ("customer/02_home_hero.jpeg", 4.5),
    ("customer/03_home_featured.jpeg", 4.0),
    ("customer/07_menu_top.jpeg", 4.0),
    ("customer/10_catering_top.jpeg", 4.0),
    ("customer/15_cart_top.jpeg", 4.0),
    ("customer/17_cart_bottom.jpeg", 4.0),
    # Admin console segment
    ("admin/01_dashboard.jpeg", 4.5),
    ("admin/03_orders_top.jpeg", 4.0),
    ("admin/06_menu_weekly.jpeg", 4.0),
    ("admin/20_delivery.jpeg", 4.0),
    # Delivery segment
    ("delivery/01_dashboard.jpeg", 4.0),
    ("delivery/06_route_planner_address.jpeg", 4.0),
    ("delivery/07_route_optimized.jpeg", 5.0),
    ("delivery/08_route_stops.jpeg", 4.0),
    ("delivery/11_after_pickup.jpeg", 4.0),
]

SCRIPT = (
    "Meet Curry and Co, a Bengali cloud kitchen for the Greater Toronto Area, "
    "delivered end to end through three connected apps. "
    "First, the customer. They open the app, sign in with Google or continue as a guest, "
    "and land on this week's menu. Biryani, kosha mangsho, mishti doi. One tap to the bag. "
    "Catering packages, weekend delivery slots, coupons, loyalty points, and Interac or "
    "cash on delivery, all built in. "
    "Second, the admin console. Live revenue, active orders, and every customer at a glance. "
    "Publish the weekly menu, manage catering, and assign drivers in seconds. "
    "Third, the driver. Surath signs in and sees his live stops. Type a starting point, "
    "Google Places fires. Tap optimize, and the platform plots the fastest route on a "
    "live map with drag to reorder. One tap marks the order picked up, another starts "
    "the delivery. "
    "Curry and Co. Kitchen to doorstep, powered by one platform."
)


async def gen_narration() -> Path:
    api_key = os.getenv("EMERGENT_LLM_KEY")
    assert api_key, "EMERGENT_LLM_KEY missing in /app/backend/.env"
    tts = OpenAITextToSpeech(api_key=api_key)
    print("🎙  Generating narration via OpenAI tts-1-hd / onyx …")
    audio = await tts.generate_speech(
        text=SCRIPT,
        model="tts-1-hd",
        voice="onyx",
        speed=1.0,
        response_format="mp3",
    )
    NARRATION_MP3.write_bytes(audio)
    print(f"  ✓ {NARRATION_MP3}  ({len(audio) // 1024} KB)")
    return NARRATION_MP3


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ]
    )
    return float(out.strip())


def build_scenes(target_total: float):
    """Rescale scene durations so total ≈ narration length."""
    plan_total = sum(d for _, d in SCENES)
    scale = target_total / plan_total
    return [(p, round(d * scale, 3)) for p, d in SCENES]


def make_scene_clip(img: Path, duration: float, out_mp4: Path, idx: int):
    """
    Turn a still into an mp4 with subtle Ken-Burns zoom.
    Output: 1080×1920 (vertical) so it looks great on any social feed.
    Uses zoompan for smooth zoom-in.
    """
    # Scale phone-frame image to fit 1080x1920, pad edges. Slow Ken-Burns zoom.
    zoom_frames = int(duration * 30)
    vf = (
        f"scale='min(1080,iw*1920/ih)':'min(1920,ih*1080/iw)':force_original_aspect_ratio=decrease,"
        f"pad=1080:1920:(1080-iw)/2:(1920-ih)/2:color=0x1c1614,"
        f"setsar=1,"
        f"zoompan=z='min(zoom+0.0005,1.06)':d={zoom_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30"
    )
    cmd = [
        "ffmpeg", "-y", "-loop", "1", "-i", str(img),
        "-t", str(duration),
        "-vf", vf,
        "-r", "30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "20",
        str(out_mp4),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    # 1) Narration
    asyncio.run(gen_narration())
    audio_len = ffprobe_duration(NARRATION_MP3)
    print(f"  narration length: {audio_len:.2f}s")

    # 2) Rebuild scene list to match narration
    scenes = build_scenes(audio_len)
    print("\n🎬 Scene plan:")
    print(f"  {TITLE_DURATION:5.2f}s   TITLE CARD")
    for p, d in scenes:
        print(f"  {d:5.2f}s   {p}")
    print(f"  {OUTRO_DURATION:5.2f}s   OUTRO CARD")

    # 3) Render each scene mp4 (title, scenes, outro)
    print("\n🎞  Rendering scenes …")
    scene_files = []

    title_out = WORK_DIR / "scene_00_title.mp4"
    make_scene_clip(TITLE_CARD, TITLE_DURATION, title_out, 0)
    scene_files.append(title_out)
    print(f"  ✓ {title_out.name}")

    for i, (img_rel, dur) in enumerate(scenes):
        src = FRAMES_ROOT / img_rel
        out = WORK_DIR / f"scene_{i+1:02d}.mp4"
        make_scene_clip(src, dur, out, i + 1)
        scene_files.append(out)
        print(f"  ✓ {out.name}")

    outro_out = WORK_DIR / f"scene_{len(scenes)+1:02d}_outro.mp4"
    make_scene_clip(OUTRO_CARD, OUTRO_DURATION, outro_out, len(scenes) + 1)
    scene_files.append(outro_out)
    print(f"  ✓ {outro_out.name}")

    # 4) Concat via ffmpeg concat demuxer
    concat_file = WORK_DIR / "concat.txt"
    concat_file.write_text("".join(f"file '{p}'\n" for p in scene_files))
    stitched = WORK_DIR / "stitched.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c", "copy", str(stitched),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"\n🔗 Stitched → {stitched}")

    # 5) Mux with narration + delay it by title duration + subtle fades
    print("\n🔊 Muxing narration (offset by title card) …")
    delayed_narration = WORK_DIR / "narration_delayed.mp3"
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(NARRATION_MP3),
            "-af", f"adelay={int(TITLE_DURATION*1000)}|{int(TITLE_DURATION*1000)},"
                   f"afade=t=in:st={TITLE_DURATION}:d=0.4,"
                   f"afade=t=out:st={TITLE_DURATION + audio_len - 0.5}:d=0.5",
            str(delayed_narration),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(stitched),
            "-i", str(delayed_narration),
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            str(VIDEO_OUT),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    total_duration = TITLE_DURATION + audio_len + OUTRO_DURATION
    print(f"\n✅ Sales reel ready: {VIDEO_OUT}")
    print(f"   Duration: {total_duration:.1f}s  |  Size: {VIDEO_OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
