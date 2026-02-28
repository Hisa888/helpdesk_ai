import os
import requests
import streamlit as st

def get_env(name: str, default: str = "") -> str:
    # Streamlit Cloudのsecrets → 環境変数 の順で読む
    try:
        if hasattr(st, "secrets") and name in st.secrets:
            return str(st.secrets[name])
    except Exception:
        pass
    return os.getenv(name, default)

def chat(messages):
    """LLM ルータ（groq or ollama）。障害時も落とさずメッセージを返す。"""
    provider = get_env("LLM_PROVIDER", "ollama").lower()

    # =========================
    # Groq (Cloud)
    # =========================
    if provider == "groq":
        try:
            from groq import Groq
        except Exception:
            return "groq パッケージが見つかりません。requirements.txt に groq を追加してください。"

        api_key = get_env("GROQ_API_KEY")
        model = get_env("GROQ_MODEL", "llama-3.1-8b-instant")

        if not api_key:
            return "GROQ_API_KEY が未設定です（Streamlit Secrets か環境変数に設定してください）。"

        try:
            client = Groq(api_key=api_key)
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
            )
            return response.choices[0].message.content
        except Exception:
            return "Groq 呼び出しでエラーが発生しました（APIキー/モデル名/ネットワークを確認してください）。"

    # =========================
    # Ollama (Local)
    # =========================
    base_url = get_env("OLLAMA_BASE_URL", "http://localhost:11434")
    model = get_env("OLLAMA_MODEL", "phi3:mini")

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.2},
    }

    try:
        r = requests.post(f"{base_url}/api/chat", json=payload, timeout=120)
        r.raise_for_status()
        return r.json()["message"]["content"]
    except Exception:
        return "Ollamaに接続できません（Cloudでは通常Ollamaは使えません。LLM_PROVIDER=groq を推奨）。"
