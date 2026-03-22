import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

if not api_key:
    raise RuntimeError("GROQ_API_KEY が .env から読めていません")

client = Groq(api_key=api_key)

res = client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": "あなたは情シスヘルプデスクです。必ず日本語のみで答えてください。"},
        {"role": "user", "content": "VPNにつながりません。最初に確認することを3つ、箇条書きで教えて。"},
    ],
    temperature=0.2,
)

print("✅ Groq OK")
print(res.choices[0].message.content)