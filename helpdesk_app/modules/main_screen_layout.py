from __future__ import annotations

from typing import Any, Callable


def ensure_main_screen_session_state(
    *,
    st,
    SEARCH_SETTINGS,
    DEFAULT_SEARCH_THRESHOLD: float,
    DEFAULT_SUGGEST_THRESHOLD: float,
    _sanitize_search_settings: Callable[[dict], dict],
    sanitize_llm_settings: Callable[[dict], dict],
    LLM_SETTINGS: dict,
    ensure_chat_session_state: Callable,
    ensure_quick_start_session_state: Callable,
    ensure_scroll_state: Callable,
    clean_legacy_bootstrap_messages: Callable,
) -> None:
    if "used_hits" not in st.session_state:
        st.session_state.used_hits = []

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "pending_q" not in st.session_state:
        st.session_state.pending_q = ""

    if "search_threshold" not in st.session_state:
        st.session_state.search_threshold = float(
            SEARCH_SETTINGS.get("answer_threshold", DEFAULT_SEARCH_THRESHOLD)
        )

    if "suggest_threshold" not in st.session_state:
        st.session_state.suggest_threshold = float(
            SEARCH_SETTINGS.get("suggest_threshold", DEFAULT_SUGGEST_THRESHOLD)
        )

    if "search_settings" not in st.session_state:
        st.session_state.search_settings = _sanitize_search_settings(SEARCH_SETTINGS)
    if "llm_settings" not in st.session_state:
        st.session_state.llm_settings = sanitize_llm_settings(LLM_SETTINGS)

    ensure_chat_session_state(st)
    ensure_quick_start_session_state(st)
    ensure_scroll_state(st)

    st.session_state["messages"] = clean_legacy_bootstrap_messages(
        st.session_state.get("messages", [])
    )


def render_main_screen_layout(
    *,
    st,
    components,
    is_welcome_state: Callable,
    render_welcome_prompt: Callable,
    render_quick_start_hero: Callable,
    render_chat_history: Callable,
    render_nohit_extra_form_panel: Callable,
    update_nohit_record: Callable,
    render_input_support_sections: Callable,
    render_quick_start_compact: Callable,
    handle_chat_interaction: Callable,
    render_chat_input_panel: Callable,
    request_scroll_to_answer: Callable,
    append_user_message: Callable,
    process_user_query: Callable,
    finalize_answer_cycle: Callable,
    render_answer_message: Callable,
    render_used_hits_expander_panel: Callable,
    render_match_bar: Callable,
    try_ultrafast_answer: Callable,
    retrieve_faq_cached: Callable,
    faq_cache_token_getter: Callable,
    ensure_faq_index_loaded: Callable,
    current_search_settings: Callable[[], dict],
    current_search_threshold: Callable[[], float],
    current_suggest_threshold: Callable[[], float],
    nohit_template: str,
    log_nohit: Callable,
    build_suggest_answer_for_runtime: Callable,
    build_suggest_answer_panel: Callable,
    _fastlane_direct_answer: Callable,
    build_prompt: Callable,
    llm_answer_cached: Callable,
    log_interaction: Callable,
    search_document_rag: Callable,
    answer_with_document_rag: Callable,
    doc_rag_threshold: float,
    llm_chat: Callable,
    maybe_scroll_to_latest_answer: Callable,
) -> dict[str, Any]:
    show_welcome = is_welcome_state(st.session_state.get("messages", []))

    if show_welcome:
        render_welcome_prompt(st)
        render_quick_start_hero(st=st)

    render_chat_history(st, messages=st.session_state.get("messages", []))

    def render_nohit_extra_form(info: dict | None = None, expanded: bool = True):
        return render_nohit_extra_form_panel(
            st=st,
            update_nohit_record=update_nohit_record,
            info=info,
            expanded=expanded,
        )

    render_input_support_sections(
        st=st,
        show_welcome=show_welcome,
        render_nohit_extra_form=render_nohit_extra_form,
        render_quick_start_compact=render_quick_start_compact,
    )

    interaction_result = handle_chat_interaction(
        st=st,
        placeholder="情シス問い合わせを入力してください",
        render_chat_input=render_chat_input_panel,
        request_scroll_to_answer=request_scroll_to_answer,
        append_user_message=append_user_message,
        process_user_query=process_user_query,
        finalize_answer_cycle=finalize_answer_cycle,
        render_answer_message=render_answer_message,
        render_used_hits_expander=lambda **kwargs: render_used_hits_expander_panel(
            st=st,
            render_match_bar=render_match_bar,
            **kwargs,
        ),
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
        build_suggest_answer=lambda user_q, hits: build_suggest_answer_for_runtime(
            user_q=user_q,
            hits=hits,
            build_suggest_answer_panel=build_suggest_answer_panel,
            nohit_template=nohit_template,
        ),
        fastlane_direct_answer=_fastlane_direct_answer,
        build_prompt=build_prompt,
        llm_answer_cached=llm_answer_cached,
        log_interaction=log_interaction,
        search_document_rag=search_document_rag,
        answer_with_document_rag=answer_with_document_rag,
        doc_rag_threshold=doc_rag_threshold,
        llm_chat=llm_chat,
    )

    if interaction_result.get("needs_rerun"):
        st.rerun()

    maybe_scroll_to_latest_answer(st=st, components=components)

    return {
        "show_welcome": show_welcome,
        "interaction_result": interaction_result,
    }
