from __future__ import annotations

from typing import Iterable, Mapping


def clean_legacy_bootstrap_messages(messages: Iterable[Mapping[str, object]]) -> list[dict]:
    cleaned: list[dict] = []
    for message in list(messages or []):
        role = str(message.get("role", ""))
        content = str(message.get("content", ""))
        is_legacy_bootstrap = (
            role == "assistant"
            and "情シス問い合わせAI" in content
            and "起動確認OK" in content
        )
        if is_legacy_bootstrap:
            continue
        cleaned.append(dict(message))
    return cleaned


def is_welcome_state(messages: Iterable[Mapping[str, object]]) -> bool:
    return len(list(messages or [])) == 0


def render_welcome_prompt(st) -> None:
    st.markdown(
        '<div class="glass-card query-panel"><div class="eyebrow">AI Demo</div><h3>情シスの問い合わせをそのまま入力してください</h3><p>例：パスワードを忘れました / VPNにつながらない / ディスプレイが真っ暗です</p></div>',
        unsafe_allow_html=True,
    )


def render_chat_history(st, *, messages: Iterable[Mapping[str, object]]) -> None:
    for message in messages or []:
        with st.chat_message(str(message.get("role", "assistant"))):
            st.markdown(str(message.get("content", "")), unsafe_allow_html=True)
