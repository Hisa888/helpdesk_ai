from __future__ import annotations

"""LLM呼び出しの入口をまとめるファイル。

第四段階として、Groq / Ollama の切替と実際のチャット呼び出しを
このファイルに集約する。

設定の保存や読込は既存の settings_and_persistence に残し、
「どこでLLMを呼んでいるか」をまず明確にする安全寄りの分離。
"""

from types import SimpleNamespace


def build_faq_answer_messages(prompt: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": "あなたは情シス担当です。FAQの内容を優先し、必ず日本語で簡潔に回答してください。",
        },
        {"role": "user", "content": str(prompt or "")},
    ]


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
        provider = cfg.get("provider", "groq")
        if provider == "ollama":
            try:
                return ollama_chat(
                    requests=requests,
                    messages=messages,
                    model=cfg.get("ollama_model", "qwen2.5:7b"),
                    base_url=cfg.get("ollama_base_url", "http://localhost:11434"),
                )
            except Exception as e:
                st.warning(f"Ollama接続に失敗したためGroqに切り替えます: {e}")
        return base_llm_chat(messages)

    return SimpleNamespace(
        build_faq_answer_messages=build_faq_answer_messages,
        ollama_chat=ollama_chat,
        llm_chat=llm_chat,
    )


__all__ = [
    "build_faq_answer_messages",
    "ollama_chat",
    "create_llm_runtime",
]
