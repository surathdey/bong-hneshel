"""One-off script: generate Curry & Co. branded 1024x1024 app icon via Gemini Nano Banana."""
import asyncio, base64, os, sys
from pathlib import Path
sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")

from emergentintegrations.llm.chat import LlmChat, UserMessage

async def gen(prompt: str, out_path: Path):
    chat = LlmChat(
        api_key=os.environ["EMERGENT_LLM_KEY"],
        session_id=f"icon-{out_path.stem}",
        system_message="You produce production-quality app icons.",
    ).with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
    _t, imgs = await chat.send_message_multimodal_response(UserMessage(text=prompt))
    if not imgs:
        print(f"NO IMAGE for {out_path}")
        return
    raw = base64.b64decode(imgs[0]["data"])
    out_path.write_bytes(raw)
    print(f"OK -> {out_path} ({len(raw)//1024} KB)")


async def main():
    out_dir = Path("/app/frontend/assets/images")
    out_dir.mkdir(parents=True, exist_ok=True)

    icon_prompt = (
        "Design a modern, minimal MOBILE APP ICON for a Bengali & Indian food delivery brand called 'Curry & Co.'. "
        "Style: warm rustic terracotta orange background (#B14F36 to #D9724A gradient). "
        "In the center: a stylized illustration of a copper handi (traditional Indian curry pot) with steam rising, "
        "seen from a 3/4 top-down angle. Simple flat design, 2-color palette with cream accents. "
        "No text, no watermark, no letters. 1024x1024 pixels square. iOS-style rounded, appetizing, premium boutique feel. "
        "The icon should look great at 60x60 (home-screen size) too — high contrast silhouette, minimal detail."
    )
    await gen(icon_prompt, out_dir / "icon.png")

    # Adaptive icon for Android — same illustration but on solid brand color background
    adaptive_prompt = (
        "Same brand as previous request. Design the FOREGROUND layer of an Android adaptive icon: "
        "a stylized copper handi with steam rising, centered on a transparent-looking safe area. "
        "The illustration must be entirely within the CENTRAL 66% of a 1024x1024 canvas "
        "(Android crops the outer 33% into a circle/squircle). Cream & terracotta color palette, "
        "no background outside the illustration (it will be composited on a solid color). "
        "No text, appetizing, premium feel."
    )
    await gen(adaptive_prompt, out_dir / "adaptive-icon.png")

    # Splash — same handi, more artistic
    splash_prompt = (
        "Design a mobile app SPLASH SCREEN artwork for 'Curry & Co.', a Bengali & Indian food brand. "
        "Center: a beautifully illustrated stylized copper handi pot with warm steam rising, on a soft "
        "warm cream (#FAF9F6) background. Add subtle floating spice illustrations (star anise, cardamom pod, "
        "chili) very faintly in the corners for atmosphere. No text. 1024x1024 pixels. "
        "Elegant, restaurant-brand, welcoming feel. Central subject should be no larger than 40% of the canvas."
    )
    await gen(splash_prompt, out_dir / "splash-image.png")

    # Favicon — same but 512
    fav_prompt = icon_prompt + " Make it very simple, works at 32x32 size."
    await gen(fav_prompt, out_dir / "favicon.png")


if __name__ == "__main__":
    asyncio.run(main())
