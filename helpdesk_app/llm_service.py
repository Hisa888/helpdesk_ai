from __future__ import annotations

"""LLM呼び出しの入口をまとめるファイル。

FAQ/RAGの検索結果を最優先し、LLMは原則として「検索結果の文章整形」にだけ使う。
Gemini Flash Lite / Groq / Ollama を切り替え可能。
"""

from types import SimpleNamespace
import os


def build_faq_answer_messages(prompt: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "あなたは情シス担当です。FAQ・社内ドキュメント検索結果の内容だけを根拠に、"
                "必ず日本語で簡潔に回答してください。検索結果に無い内容は推測して補完せず、"
                "分からない場合は『確認が必要です』と伝えてください。"
            ),
        },
        {"role": "user", "content": str(prompt or "")},
    ]


def _message_text(messages) -> str:
    parts: list[str] = []
    for msg in messages or []:
        if not isinstance(msg, dict):
            continue
        role = str(msg.get("role", "user"))
        content = str(msg.get("content", ""))
        if content.strip():
            parts.append(f"[{role}]\n{content}")
    return "\n\n".join(parts).strip()


def _get_secret(st, name: str, default: str = "") -> str:
    """Streamlit Secrets と環境変数の両方から安全に読む。"""
    value = None
    try:
        value = st.secrets.get(name, None)  # type: ignore[attr-defined]
    except Exception:
        value = None
    if value is None:
        value = os.environ.get(name, default)
    return str(value or default).strip()


def gemini_chat(*, st, requests, messages, model: str) -> str:
    """Gemini API を REST で呼ぶ。追加SDK不要（requestsだけで動作）。"""
    api_key = _get_secret(st, "GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY が未設定です")

    model_name = str(model or "gemini-2.5-flash-lite").strip() or "gemini-2.5-flash-lite"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
    prompt = _message_text(messages)
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.8,
            "maxOutputTokens": 1024,
        },
    }
    resp = requests.post(url, json=payload, timeout=(5, 60))
    resp.raise_for_status()
    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        return ""
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict)).strip()
    return text


def ollama_chat(*, requests, messages, model: str, base_url: str) -> str:
    url = str(base_url or "http://localhost:11434").rstrip("/") + "/api/chat"
    payload = {"model": model or "qwen2.5:7b", "messages": messages, "stream": False}
    resp = requests.post(url, json=payload, timeout=(5, 120))
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        msg = data.get("message")
        if isinstance(msg, dict) and msg.get("content") is not None:
            return str(msg.get("content")).strip()
        if data.get("response") is not None:
            return str(data.get("response")).strip()
    return ""


def create_llm_runtime(*, st, requests, current_llm_settings, base_llm_chat):
    def llm_chat(messages):
        cfg = current_llm_settings()
        provider = str(cfg.get("provider", "gemini")).strip().lower() or "gemini"

        if provider == "gemini":
            try:
                return gemini_chat(
                    st=st,
                    requests=requests,
                    messages=messages,
                    model=cfg.get("gemini_model", "gemini-2.5-flash-lite"),
                )
            except Exception as e:
                st.warning(f"Gemini接続に失敗したため、既存LLMに切り替えます: {e}")
                return base_llm_chat(messages)

        if provider == "ollama":
            try:
                return ollama_chat(
                    requests=requests,
                    messages=messages,
                    model=cfg.get("ollama_model", "qwen2.5:7b"),
                    base_url=cfg.get("ollama_base_url", "http://localhost:11434"),
                )
            except Exception as e:
                st.warning(f"Ollama接続に失敗したため、既存LLMに切り替えます: {e}")
                return base_llm_chat(messages)

        return base_llm_chat(messages)

    return SimpleNamespace(
        build_faq_answer_messages=build_faq_answer_messages,
        gemini_chat=gemini_chat,
        ollama_chat=ollama_chat,
        llm_chat=llm_chat,
    )


__all__ = [
    "build_faq_answer_messages",
    "gemini_chat",
    "ollama_chat",
    "create_llm_runtime",
]
