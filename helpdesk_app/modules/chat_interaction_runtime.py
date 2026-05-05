from __future__ import annotations

from helpdesk_app.modules.clarification_state import (
    clear_clarification,
    consume_clarification_followup,
    get_clarification_original_question,
    is_clarification_pending,
)


def build_suggest_answer_for_runtime(*, user_q: str, hits, build_suggest_answer_panel, nohit_template):
    return build_suggest_answer_panel(user_q=user_q, hits=hits, nohit_template=nohit_template)



def render_input_support_sections(*, st, show_welcome: bool, render_nohit_extra_form, render_quick_start_compact) -> None:
    if st.session_state.get("pending_nohit_active"):
        render_nohit_extra_form(expanded=False)
    if not show_welcome:
        render_quick_start_compact(st=st)



def handle_chat_interaction(
    *,
    st,
    placeholder: str,
    render_chat_input,
    request_scroll_to_answer,
    append_user_message,
    process_user_query,
    finalize_answer_cycle,
    render_answer_message,
    render_used_hits_expander,
    try_ultrafast_answer,
    retrieve_faq_cached,
    faq_cache_token_getter,
    ensure_faq_index_loaded,
    render_match_bar,
    current_search_settings,
    current_search_threshold,
    current_suggest_threshold,
    nohit_template,
    log_nohit,
    build_suggest_answer,
    fastlane_direct_answer,
    top_hit_is_ambiguous=None,
    build_prompt,
    llm_answer_cached,
    log_interaction,
    search_document_rag,
    answer_with_document_rag,
    doc_rag_threshold,
    llm_chat,
):
    user_q, used_pending = render_chat_input(st=st, placeholder=placeholder)
    if not user_q:
        return {"user_q": "", "used_pending": used_pending, "handled": False, "needs_rerun": False, "result": None}

    combined_user_q = user_q
    display_user_q = user_q
    skip_clarification = False
    if is_clarification_pending(st):
        original_user_q = get_clarification_original_question(st)
        combined_user_q = consume_clarification_followup(st=st, followup_text=user_q)
        # 補足回答時は、チャット履歴にも「元の質問 + 補足」を表示する。
        # これにより「アプリ」→「インストール」のような追加入力が無視されたように見える問題を防ぐ。
        if str(original_user_q or "").strip():
            display_user_q = f"{str(original_user_q).strip()}\n\n補足情報：{user_q}"
        skip_clarification = True

    append_user_message(st=st, user_q=display_user_q)
    with st.chat_message("user"):
        st.markdown(display_user_q)

    try:
        selected_faq = st.session_state.pop("pending_selected_faq", None) if used_pending else None
        if isinstance(selected_faq, dict) and str(selected_faq.get("question", "")).strip() == str(user_q or "").strip():
            row = dict(selected_faq.get("row", {}) or {})
            score = float(selected_faq.get("score", 1.0) or 1.0)
            answer_text = str(selected_faq.get("answer", "") or row.get("answer", "")).strip()
            if not answer_text:
                answer_text = "選択されたFAQに回答文が登録されていません。管理者画面でFAQの回答欄を確認してください。"
            try:
                render_match_bar(score, label="FAQ一致度（選択）")
            except Exception:
                pass
            try:
                category = str(row.get("category", ""))
                log_interaction(user_q, matched=True, best_score=score, category=category)
            except Exception:
                pass
            result = {
                "answer": answer_text,
                "best_score": score,
                "answer_threshold": float(current_search_threshold()),
                "suggest_threshold": float(current_suggest_threshold()),
                "used_hits": [(row, score)],
                "doc_hits": [],
                "used_doc_rag": False,
                "doc_best_score": 0.0,
                "was_nohit": False,
                "was_suggest": False,
                "answer_format": str(selected_faq.get("answer_format", row.get("answer_format", "markdown")) or "markdown"),
                "was_clarification": False,
                "suggestion_candidates": [],
            }
        else:
            result = process_user_query(
                st=st,
                user_q=combined_user_q,
                try_ultrafast_answer=try_ultrafast_answer,
                retrieve_faq_cached=retrieve_faq_cached,
                faq_cache_token_getter=faq_cache_token_getter,
                ensure_faq_index_loaded=ensure_faq_index_loaded,
                render_match_bar=render_match_bar,
                current_search_settings=current_search_settings,
                current_search_threshold=current_search_threshold,
                current_suggest_threshold=current_suggest_threshold,
                nohit_template=nohit_template,
                log_nohit=log_nohit,
                build_suggest_answer=build_suggest_answer,
                fastlane_direct_answer=fastlane_direct_answer,
                top_hit_is_ambiguous=top_hit_is_ambiguous,
                build_prompt=build_prompt,
                llm_answer_cached=llm_answer_cached,
                log_interaction=log_interaction,
                search_document_rag=search_document_rag,
                answer_with_document_rag=answer_with_document_rag,
                doc_rag_threshold=doc_rag_threshold,
                llm_chat=llm_chat,
                skip_clarification=skip_clarification,
            )
    except Exception:
        clear_clarification(st=st, reset_count=True)
        result = {
            "answer": "回答処理中にエラーが発生しました。質問内容を少し具体的にして、もう一度お試しください。",
            "best_score": 0.0,
            "answer_threshold": float(current_search_threshold()),
            "suggest_threshold": float(current_suggest_threshold()),
            "used_hits": [],
            "doc_hits": [],
            "used_doc_rag": False,
            "doc_best_score": 0.0,
            "was_nohit": True,
            "was_suggest": False,
            "answer_format": "markdown",
            "was_clarification": False,
        }

    finalize_answer_cycle(
        st=st,
        user_q=combined_user_q,
        result=result,
        render_answer_message=render_answer_message,
        render_used_hits_expander=render_used_hits_expander,
    )
    request_scroll_to_answer(st)

    return {
        "user_q": user_q,
        "used_pending": used_pending,
        "handled": True,
        # 回答後に「追加情報を記録（任意）」欄を必ず下側へ表示するため、
        # 通常回答でも一度 rerun して、回答履歴 → 根拠 → 追加情報フォームの順に再描画する。
        "needs_rerun": bool(result.get("was_nohit") or result.get("was_clarification") or result.get("was_suggest") or result.get("answer")),
        "result": result,
    }
