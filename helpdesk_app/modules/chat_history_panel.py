from __future__ import annotations

from typing import Iterable, Mapping

from helpdesk_app.modules.contact_cta_panel import render_answer_contact_cta
from helpdesk_app.modules.faq_answer_renderer import render_answer_box


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
    if bool(st.session_state.get("demo_mode", True)):
        eyebrow = "Sales Demo Ready"
        title = "社内IT問い合わせの一次対応を、見せやすく・導入しやすく"
        body = "この画面は、実際の問い合わせ対応だけでなく、営業デモでも価値が伝わる構成です。FAQ検索、自己解決促進、問い合わせ標準化までを1つの画面で体験できます。"
    else:
        eyebrow = "Internal Helpdesk"
        title = "社内IT問い合わせを入力してください"
        body = "よくあるIT問い合わせに対して、FAQと社内ナレッジをもとに回答します。解決しない場合は、問い合わせに必要な情報を整理して案内します。"

    st.markdown(
        f"""
<div class="glass-card query-panel">
  <div class="eyebrow">{eyebrow}</div>
  <h3>{title}</h3>
  <p>{body}</p>
  <div class="demo-note">
    まずは <b>パスワードを忘れました</b> や <b>VPNにつながりません</b> など、よくある質問をそのまま入力してください。
  </div>
</div>
""",
        unsafe_allow_html=True,
    )


def render_chat_history(st, *, messages: Iterable[Mapping[str, object]]) -> None:
    message_list = list(messages or [])
    last_assistant_idx = -1
    for idx, message in enumerate(message_list):
        if str(message.get("role", "assistant")) == "assistant":
            last_assistant_idx = idx

    for idx, message in enumerate(message_list):
        role = str(message.get("role", "assistant"))
        content = str(message.get("content", ""))
        with st.chat_message(role):
            if role == "assistant":
                render_answer_box(
                    st,
                    answer=content,
                    answer_format=str(message.get("answer_format", "markdown")),
                    css_class="answerbox",
                )
                if idx == last_assistant_idx:
                    render_answer_contact_cta(
                        st=st,
                        was_nohit=bool(message.get("was_nohit", False)),
                        was_suggest=bool(message.get("was_suggest", False)),
                        used_doc_rag=bool(message.get("used_doc_rag", False)),
                        was_clarification=bool(message.get("was_clarification", False)),
                    )
            else:
                st.markdown(content, unsafe_allow_html=True)
