"""One-off: generate a moody Bengali food background for the login screen and
save it as assets/brand/login-bg.png (replaces the solid-purple placeholder)."""
import asyncio, base64, os
from dotenv import load_dotenv
load_dotenv()
from emergentintegrations.llm.chat import LlmChat, UserMessage

KEY = os.environ["EMERGENT_LLM_KEY"]
OUT = "/app/frontend/assets/brand/login-bg.png"

PROMPT = (
    "Photorealistic, moody overhead food photograph of an authentic Bengali feast: "
    "a rich hilsa (ilish) fish mustard curry in a dark bowl and a plate of fragrant "
    "biryani with a boiled egg and tender meat, surrounded by small katoris of curries, "
    "steamed rice, lemon wedges and fresh green chillies, on a dark rustic wooden table. "
    "Warm cinematic side lighting, deep rich shadows, appetizing, restaurant-quality, "
    "tall vertical portrait composition, negative space toward the bottom, "
    "no text, no watermark, no people."
)

async def main():
    chat = (LlmChat(api_key=KEY, session_id="login-bg-gen",
                    system_message="You generate high-quality food photography.")
            .with_model("gemini", "gemini-3.1-flash-image-preview")
            .with_params(modalities=["image", "text"]))
    _t, images = await chat.send_message_multimodal_response(UserMessage(text=PROMPT))
    if not images:
        print("NO IMAGE"); return
    raw = base64.b64decode(images[0]["data"])
    with open(OUT, "wb") as f:
        f.write(raw)
    print("saved", OUT, len(raw), "bytes")

asyncio.run(main())
