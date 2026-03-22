import os
import json
import requests

def _fallback_reply(messages):
    user_parts = []
    for m in messages or []:
        if isinstance(m, dict) and m.get("role") == "user":
            user_parts.append(str(m.get("content", "")))
    joined = "\n".join(user_parts).strip()
    if "JSON" in joined.upper() or "json" in joined:
        return "[]"
    return "FAQ候補をもとに回答を生成できる設定が未完了です。環境変数 GROQ_API_KEY を設定するとAI回答を有効化できます。"

def chat(messages):
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    model = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile").strip() or "llama-3.3-70b-versatile"
    if not api_key:
        return _fallback_reply(messages)

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
    }
    res = requests.post(url, headers=headers, json=payload, timeout=60)
    res.raise_for_status()
    data = res.json()
    return data["choices"][0]["message"]["content"]
