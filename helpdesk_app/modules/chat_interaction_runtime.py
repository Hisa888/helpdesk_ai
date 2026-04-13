from __future__ import annotations



def build_suggest_answer_for_runtime(*, user_q: str, hits, build_suggest_answer_panel, nohit_template):
    return build_suggest_answer_panel(user_q=user_q, hits=hits, nohit_template=nohit_template)



def render_input_support_sections(*, st, show_welcome: bool, render_nohit_extra_form, render_quick_start_compact) -> None:
    if st.session_state.get("pending_nohit_active"):
        render_nohit_extra_form(expanded=True)
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
    current_search_threshold,
    current_suggest_threshold,
    nohit_template,
    log_nohit,
    build_suggest_answer,
    fastlane_direct_answer,
    build_prompt,
    llm_answer_cached,
    log_interaction,
):
    user_q, used_pending = render_chat_input(st=st, placeholder=placeholder)
    if not user_q:
        return {"user_q": "", "used_pending": used_pending, "handled": False, "needs_rerun": False, "result": None}

    request_scroll_to_answer(st)
    append_user_message(st=st, user_q=user_q)

    result = process_user_query(
        st=st,
        user_q=user_q,
        try_ultrafast_answer=try_ultrafast_answer,
        retrieve_faq_cached=retrieve_faq_cached,
        faq_cache_token_getter=faq_cache_token_getter,
        ensure_faq_index_loaded=ensure_faq_index_loaded,
        render_match_bar=render_match_bar,
        current_search_threshold=current_search_threshold,
        current_suggest_threshold=current_suggest_threshold,
        nohit_template=nohit_template,
        log_nohit=log_nohit,
        build_suggest_answer=build_suggest_answer,
        fastlane_direct_answer=fastlane_direct_answer,
        build_prompt=build_prompt,
        llm_answer_cached=llm_answer_cached,
        log_interaction=log_interaction,
    )

    finalize_answer_cycle(
        st=st,
        user_q=user_q,
        result=result,
        render_answer_message=render_answer_message,
        render_used_hits_expander=render_used_hits_expander,
    )

    return {
        "user_q": user_q,
        "used_pending": used_pending,
        "handled": True,
        "needs_rerun": bool(result.get("was_nohit")),
        "result": result,
    }
