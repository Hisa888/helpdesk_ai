from __future__ import annotations

from typing import Iterable, Mapping

from helpdesk_app.modules.contact_cta_panel import render_answer_contact_cta
from helpdesk_app.modules.faq_answer_renderer import render_answer_box
from helpdesk_app.modules.answer_panel import render_maybe_candidate_buttons, render_used_hits_expander
from helpdesk_app.modules.ui_helpers import render_match_bar


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
                # 「もしかしてこれですか？」候補は、回答後に画面上へ戻っても消えないよう、
                # 最後のassistantメッセージだけでなく、候補表示メッセージには常に再描画する。
                # key_prefix に履歴番号を入れて、同じFAQ候補が複数回出てもキー重複しないようにする。
                if bool(message.get("was_suggest", False)):
                    render_maybe_candidate_buttons(
                        st,
                        suggestion_candidates=message.get("suggestion_candidates", []),
                        user_q=str(message.get("user_q", "")),
                        key_prefix=f"history_{idx}",
                    )

                # 回答が正しいとは限らないため、通常回答・候補回答・RAG回答・該当なしの
                # どの問い合わせでも、必ず根拠確認用のアコーディオンを表示する。
                # 以前は回答直後だけ表示され、rerun後の履歴再描画では消えていた。
                if not bool(message.get("was_clarification", False)):
                    render_used_hits_expander(
                        st=st,
                        render_match_bar=render_match_bar,
                        used_hits=message.get("used_hits", []),
                        best_score=float(message.get("best_score", 0.0) or 0.0),
                        answer_threshold=float(message.get("answer_threshold", 0.0) or 0.0),
                        was_nohit=bool(message.get("was_nohit", False)) or not bool(message.get("used_hits") or message.get("doc_hits")),
                        doc_hits=message.get("doc_hits", []),
                        used_doc_rag=bool(message.get("used_doc_rag", False)),
                        doc_best_score=float(message.get("doc_best_score", 0.0) or 0.0),
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
