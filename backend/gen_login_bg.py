"""One-off: generate a moody Bengali food background for the login screen and
save it as assets/brand/login-bg.png (replaces the solid-purple placeholder)."""
import asyncio, base64, os
from dotenv import load_dotenv
load_dotenv()
try:
    from emergentintegrations.llm.chat import LlmChat, UserMessage
except ImportError:
    LlmChat = None
    UserMessage = None

KEY = os.environ.get("EMERGENT_LLM_KEY", "")
OUT = "/app/frontend/assets/brand/login-bg.png"

PROMPT = (
    "Photorealistic, crisp, sharply focused overhead food photograph of a lavish plate "
    "of Kolkata-style mutton biryani as the clear hero in the centre: fragrant long-grain "
    "basmati rice with saffron strands, a tender piece of meat, a whole boiled egg and a "
    "golden fried potato, garnished with fried onions and mint. A few small katoris of "
    "curry, a hilsa fish piece, lemon wedges and green chillies sit around it on a dark "
    "rustic wooden table. Bright warm cinematic lighting, high detail, vibrant appetizing "
    "colours, tall vertical portrait composition with the biryani filling most of the "
    "frame, some darker negative space toward the bottom, no text, no watermark, no people."
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
